"""Section 7: concurrent analysts. Run ONE database service at a time.

Workloads (run separately): Q4 depth 10 and Q7 length-only bound 6 (SQL version
selected in Section 6.3: bidirectional), cycling sets A-B-C. 1, 4, 8 and 16 client
processes, one persistent connection each, three repetitions per combination.

Each client warms up A-B-C once, then waits at a Barrier. At release a common start
time is set and the deadline is 15 s later. Clients start A-B-C cycles until the
deadline, finish any started cycle, and submit each next request immediately.
Query timeout 60 s. Correctness is checked after timing.

  # PostgreSQL running, Neo4j STOPPED
  .venv\\Scripts\\python.exe loadtest.py --engine pg
  # Neo4j running, PostgreSQL STOPPED
  .venv\\Scripts\\python.exe loadtest.py --engine neo
  # any time: summary table + plots
  .venv\\Scripts\\python.exe loadtest.py --summary

Raw requests: results/loadtest/requests_<engine>.csv; summary: results/loadtest/summary.csv
"""
import argparse
import csv
import json
import math
import multiprocessing as mp
import socket
import statistics
import sys
import threading
import time
from datetime import datetime

CLIENTS = (1, 4, 8, 16)
REPEATS = 3
WINDOW_S = 15
TIMEOUT_S = 60
CYCLE = ("A", "B", "C")
WORKLOADS = ("Q4-d10", "Q7-b6")
PORTS = {"pg": 5432, "neo": 7687}


def case_for(workload, set_name, q7_sql="bidirectional"):
    import cases
    if workload == "Q4-d10":
        return cases.by_id(f"Q4-{set_name}-d10")
    return cases.by_id(f"Q7-{set_name}-b6", q7_sql)


def worker(engine, workload, client_id, barrier, start_value, out_queue):
    import db
    from neo4j import Query

    plan = {s: case_for(workload, s) for s in CYCLE}
    if engine == "pg":
        db.run_pg(f"SET statement_timeout = '{TIMEOUT_S}s'")

    def call(c):
        if engine == "pg":
            return db.run_pg(c.sql, c.params)
        return [tuple(r.values()) for r in db.neo().run(Query(c.cypher, timeout=TIMEOUT_S), c.params)]

    for s in CYCLE:                         # warm-up A-B-C once, untimed
        call(plan[s])

    barrier.wait()                          # released together; start time set by the barrier action
    start_wall = start_value.value
    deadline = start_wall + WINDOW_S
    records = []
    cycle_no = 0
    while time.time() < deadline:           # start cycles until the deadline...
        cycle_no += 1
        for s in CYCLE:                     # ...and finish any cycle already started
            c = plan[s]
            t_sub = time.time()
            t0 = time.perf_counter()
            status, rows, error = "ok", None, ""
            try:
                rows = db.normalize(call(c))
            except Exception as exc:
                text = f"{type(exc).__name__}: {exc}".replace("\n", " ")[:200]
                status = "timeout" if any(k in text for k in ("QueryCanceled", "statement timeout",
                                                               "TransactionTimedOut", "timed out")) else "error"
                error = text
                if engine == "neo":
                    db.close()
            latency = time.perf_counter() - t0
            records.append({"client": client_id, "cycle": cycle_no, "set": s, "case": c.case_id,
                            "submitted_offset_s": round(t_sub - start_wall, 4),
                            "latency_ms": round(latency * 1000, 3), "status": status,
                            "result": json.dumps(rows, default=str) if rows is not None else "",
                            "error": error})
    end_wall = time.time()
    db.close()
    out_queue.put({"client": client_id, "records": records, "end_offset_s": end_wall - start_wall})


class SetStart:
    """Barrier action (picklable for Windows spawn): records the common start time."""

    def __init__(self, value):
        self.value = value

    def __call__(self):
        self.value.value = time.time()


def sample_cpu(stop, samples):
    import psutil
    psutil.cpu_percent(None)
    while not stop.is_set():
        samples.append(psutil.cpu_percent(interval=0.5))


def run_test(engine, workload, n_clients, repetition, reference):
    ctx = mp.get_context("spawn")
    start_value = ctx.Value("d", 0.0)
    barrier = ctx.Barrier(n_clients, action=SetStart(start_value))
    out_queue = ctx.Queue()
    procs = [ctx.Process(target=worker, args=(engine, workload, i, barrier, start_value, out_queue))
             for i in range(n_clients)]
    for p in procs:
        p.start()

    stop, cpu = threading.Event(), []
    sampler = threading.Thread(target=sample_cpu, args=(stop, cpu), daemon=True)
    while start_value.value == 0.0 and any(p.is_alive() for p in procs):
        time.sleep(0.01)
    sampler.start()
    results = [out_queue.get() for _ in procs]
    for p in procs:
        p.join()
    stop.set()
    sampler.join()

    from zoneinfo import ZoneInfo
    started = datetime.fromtimestamp(start_value.value, tz=ZoneInfo("Africa/Kigali"))
    records = [r for res in results for r in res["records"]]
    elapsed = max(res["end_offset_s"] for res in results)
    for r in records:                         # correctness checked after timing
        r["correct"] = r["status"] == "ok" and r["result"] == reference[r["case"]]
    ok_lat = sorted(r["latency_ms"] for r in records if r["status"] == "ok")
    correct = sum(r["correct"] for r in records)
    p95 = ok_lat[math.ceil(0.95 * len(ok_lat)) - 1] if ok_lat else None
    rep = {"engine": engine, "workload": workload, "clients": n_clients, "repetition": repetition,
           "start_cat": started.isoformat(timespec="seconds"),
           "requests": len(records), "correct": correct,
           "wrong": sum(r["status"] == "ok" and not r["correct"] for r in records),
           "errors": sum(r["status"] == "error" for r in records),
           "timeouts": sum(r["status"] == "timeout" for r in records),
           "elapsed_s": round(elapsed, 3), "throughput_rps": round(correct / elapsed, 3),
           "median_ms": round(statistics.median(ok_lat), 3) if ok_lat else None,
           "p95_ms": p95, "cpu_avg_pct": round(statistics.mean(cpu), 1) if cpu else None,
           "cpu_max_pct": max(cpu) if cpu else None}
    for r in records:
        r.update(engine=engine, workload=workload, clients=n_clients, repetition=repetition)
    return rep, records


def load_reference():
    import config
    ref = {}
    for r in json.loads((config.RESULTS_DIR / "compare_61_plain.json").read_text(encoding="utf-8")):
        ref[r["case"]] = json.dumps(r["neo4j"], default=str)
    return ref


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def run_engine(engine, allow_both):
    import config
    other = "neo" if engine == "pg" else "pg"
    if not port_open(PORTS[engine]):
        sys.exit(f"{engine} is not running")
    if port_open(PORTS[other]) and not allow_both:
        sys.exit(f"Stop {'Neo4j' if other == 'neo' else 'PostgreSQL'} first (one database service at a time).")
    out = config.RESULTS_DIR / "loadtest"
    out.mkdir(parents=True, exist_ok=True)
    reference = load_reference()
    rep_path, req_path = out / f"repetitions_{engine}.csv", out / f"requests_{engine}.csv"
    rep_fields = ["engine", "workload", "clients", "repetition", "start_cat", "requests", "correct", "wrong",
                  "errors", "timeouts", "elapsed_s", "throughput_rps", "median_ms", "p95_ms",
                  "cpu_avg_pct", "cpu_max_pct"]
    req_fields = ["engine", "workload", "clients", "repetition", "client", "cycle", "set", "case",
                  "submitted_offset_s", "latency_ms", "status", "correct", "error"]
    print(f"Load test {engine}: workloads {WORKLOADS}, clients {CLIENTS}, {REPEATS} repetitions, "
          f"{WINDOW_S} s window (Q7 SQL: bidirectional)")
    print(f"{'workload':<9}{'clients':>8}{'rep':>4}{'requests':>10}{'correct':>9}{'err':>5}{'t/o':>5}"
          f"{'elapsed s':>10}{'req/s':>9}{'median ms':>11}{'p95 ms':>10}{'CPU avg/max %':>15}")
    with open(rep_path, "w", newline="", encoding="utf-8") as fr, \
         open(req_path, "w", newline="", encoding="utf-8") as fq:
        wr = csv.DictWriter(fr, fieldnames=rep_fields)
        wq = csv.DictWriter(fq, fieldnames=req_fields, extrasaction="ignore")
        wr.writeheader()
        wq.writeheader()
        for workload in WORKLOADS:
            for n in CLIENTS:
                for rep_no in range(1, REPEATS + 1):
                    rep, records = run_test(engine, workload, n, rep_no, reference)
                    wr.writerow(rep)
                    wq.writerows(records)
                    fr.flush()
                    print(f"{workload:<9}{n:>8}{rep_no:>4}{rep['requests']:>10}{rep['correct']:>9}"
                          f"{rep['errors']:>5}{rep['timeouts']:>5}{rep['elapsed_s']:>10.2f}"
                          f"{rep['throughput_rps']:>9.2f}{rep['median_ms'] or 0:>11.1f}{rep['p95_ms'] or 0:>10.1f}"
                          f"{str(rep['cpu_avg_pct']) + '/' + str(rep['cpu_max_pct']):>15}", flush=True)
    print(f"Saved {rep_path} and {req_path}")


def summary():
    import config
    out = config.RESULTS_DIR / "loadtest"
    reps = []
    for p in sorted(out.glob("repetitions_*.csv")):
        with open(p, encoding="utf-8", newline="") as f:
            reps += list(csv.DictReader(f))
    groups = {}
    for r in reps:
        groups.setdefault((r["engine"], r["workload"], int(r["clients"])), []).append(r)

    def med(rows, key):
        vals = [float(r[key]) for r in rows if r[key] not in ("", "None")]
        return statistics.median(vals) if vals else None

    lines = []
    print("Median of 3 repetitions per combination")
    print(f"{'engine':<7}{'workload':<9}{'clients':>8}{'req/s':>9}{'median ms':>11}{'p95 ms':>10}"
          f"{'errors':>8}{'timeouts':>9}{'CPU avg %':>10}{'CPU max %':>10}")
    for key in sorted(groups):
        rows = groups[key]
        ln = {"engine": key[0], "workload": key[1], "clients": key[2],
              "throughput_rps": med(rows, "throughput_rps"), "median_ms": med(rows, "median_ms"),
              "p95_ms": med(rows, "p95_ms"), "errors": med(rows, "errors"), "timeouts": med(rows, "timeouts"),
              "cpu_avg_pct": med(rows, "cpu_avg_pct"), "cpu_max_pct": med(rows, "cpu_max_pct"),
              "repetitions": len(rows)}
        lines.append(ln)
        print(f"{ln['engine']:<7}{ln['workload']:<9}{ln['clients']:>8}{ln['throughput_rps']:>9.2f}"
              f"{ln['median_ms']:>11.1f}{ln['p95_ms']:>10.1f}{ln['errors']:>8.0f}{ln['timeouts']:>9.0f}"
              f"{ln['cpu_avg_pct'] or 0:>10.1f}{ln['cpu_max_pct'] or 0:>10.1f}")
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lines[0]))
        w.writeheader()
        w.writerows(lines)
    plot(lines)
    print(f"Saved {out / 'summary.csv'}")


def plot(lines):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import config
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for engine, color in (("pg", "#3b6ea5"), ("neo", "#c0504d")):
        for workload, style in (("Q4-d10", "-"), ("Q7-b6", "--")):
            pts = sorted((ln["clients"], ln) for ln in lines if ln["engine"] == engine and ln["workload"] == workload)
            if not pts:
                continue
            xs = [c for c, _ in pts]
            label = f"{'PostgreSQL' if engine == 'pg' else 'Neo4j'} {workload}"
            axes[0].plot(xs, [ln["throughput_rps"] for _, ln in pts], style, marker="o", color=color, label=label)
            axes[1].plot(xs, [ln["p95_ms"] for _, ln in pts], style, marker="o", color=color, label=label)
    axes[0].set_ylabel("Throughput (correct requests / s)")
    axes[1].set_ylabel("p95 latency (ms)")
    axes[1].set_yscale("log")
    for ax, title in zip(axes, ("Throughput vs clients", "p95 latency vs clients")):
        ax.set_xlabel("Concurrent clients")
        ax.set_xticks(CLIENTS)
        ax.set_title(title)
        ax.grid(alpha=0.3, which="both")
        ax.legend()
    fig.tight_layout()
    path = config.RESULTS_DIR / "charts" / "loadtest.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"Chart saved: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("pg", "neo"))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--allow-both", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)  # testing only
    args = parser.parse_args()
    if args.dry_run:
        global CLIENTS, REPEATS, WINDOW_S
        CLIENTS, REPEATS, WINDOW_S = (1, 4), 1, 3
    if args.summary:
        summary()
    elif args.engine:
        run_engine(args.engine, args.allow_both)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
