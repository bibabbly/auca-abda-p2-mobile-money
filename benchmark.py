"""Sections 6.2 / 6.3: time a fixed selection of cases on ONE database service at a time.

Same machine, persistent connection, fixed resource settings, base data only.
Per case: 3 untimed warm-ups (180 s limit each), then 5 measured runs (60 s limit
each), timed with perf_counter from submission until the final row is received.
Errors and timeouts are recorded separately, never as completed timings. Answers
are compared with the 61-case reference outside the timer.

  # PostgreSQL running, Neo4j STOPPED
  .venv\\Scripts\\python.exe benchmark.py --engine pg                    # 21 cases (plain Q7 SQL)
  .venv\\Scripts\\python.exe benchmark.py --engine pg --cases q7revised  # 6.3: 4 revised Q7 cases
  # Neo4j running, PostgreSQL STOPPED
  .venv\\Scripts\\python.exe benchmark.py --engine neo                   # 21 cases
  # any time
  .venv\\Scripts\\python.exe benchmark.py --summary

Raw runs: results/benchmark/runs_<engine>_<cases>.csv; summary: results/benchmark/summary.csv
"""
import argparse
import csv
import json
import socket
import statistics
import sys
from datetime import datetime
from time import perf_counter

from neo4j import Query

import cases
import config
import db

OUT = config.RESULTS_DIR / "benchmark"
WARMUPS, RUNS = 3, 5
WARMUP_TIMEOUT, MEASURED_TIMEOUT = 180, 60
PORTS = {"pg": 5432, "neo": 7687}
FIELDS = ["case", "question", "set", "params", "engine", "sql_version", "phase", "run", "start_cat",
          "duration_ms", "rows", "status", "correct", "error"]


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def reference_answers():
    path = config.RESULTS_DIR / "compare_61_plain.json"
    if not path.exists():
        return {}
    ref = {}
    for r in json.loads(path.read_text(encoding="utf-8")):
        ref[r["case"]] = json.dumps(r["neo4j"], default=str)
    return ref


def set_pg_timeout(seconds):
    db.run_pg(f"SET statement_timeout = '{int(seconds)}s'")


def execute(engine, case, timeout):
    """Return (rows, seconds) or raise. Timer covers submission to final-row receipt."""
    if engine == "pg":
        start = perf_counter()
        rows = db.run_pg(case.sql, case.params)
        return rows, perf_counter() - start
    session = db.neo()
    start = perf_counter()
    rows = [tuple(r.values()) for r in session.run(Query(case.cypher, timeout=timeout), case.params)]
    return rows, perf_counter() - start


def classify(exc):
    text = f"{type(exc).__name__}: {exc}".replace("\n", " ")[:300]
    timed_out = any(k in text for k in ("QueryCanceled", "statement timeout", "TransactionTimedOut",
                                        "timed out", "Timeout", "terminated"))
    return ("timeout" if timed_out else "error"), text


def run_case(engine, case, ref, writer):
    sql_version = case.extra.get("q7_sql", "") if engine == "pg" else ""
    base = {"case": case.case_id, "question": case.question, "set": case.set_name,
            "params": json.dumps(case.params), "engine": engine, "sql_version": sql_version}
    measured_ms, statuses, last_rows = [], [], None
    for phase, count, timeout in (("warmup", WARMUPS, WARMUP_TIMEOUT), ("measured", RUNS, MEASURED_TIMEOUT)):
        if engine == "pg":
            set_pg_timeout(timeout)
        for i in range(1, count + 1):
            row = {**base, "phase": phase, "run": i,
                   "start_cat": datetime.now(db.CAT).isoformat(timespec="milliseconds")}
            try:
                rows, seconds = execute(engine, case, timeout)
                row.update(duration_ms=round(seconds * 1000, 3), rows=len(rows), status="ok", error="")
                last_rows = rows
            except Exception as exc:  # timeouts/errors are kept, never counted as timings
                status, text = classify(exc)
                row.update(duration_ms="", rows="", status=status, error=text)
                if engine == "neo":
                    db.close()       # reopen the session after a failed transaction
            # correctness is checked after the timer has stopped
            if row["status"] == "ok" and case.case_id in ref:
                row["correct"] = json.dumps(db.normalize(last_rows), default=str) == ref[case.case_id]
            else:
                row["correct"] = ""
            writer.writerow(row)
            if phase == "measured":
                statuses.append(row["status"])
                if row["status"] == "ok":
                    measured_ms.append(row["duration_ms"])
    med = statistics.median(measured_ms) if measured_ms else None
    print(f"{case.case_id:<12}{engine:<5}{sql_version:<14}"
          f"{(f'{med:,.1f}' if med is not None else '-'):>12} ms median   "
          f"ok={statuses.count('ok')} timeout={statuses.count('timeout')} error={statuses.count('error')}",
          flush=True)


def benchmark(engine, which, q7_sql, allow_both):
    other = "neo" if engine == "pg" else "pg"
    if not port_open(PORTS[engine]):
        sys.exit(f"{engine} is not running on port {PORTS[engine]}")
    if port_open(PORTS[other]) and not allow_both:
        sys.exit(f"Stop {'Neo4j' if other == 'neo' else 'PostgreSQL'} first: timings must run "
                 f"with one database service at a time (or pass --allow-both for a dry run).")
    selected = cases.q7_revised() if which == "q7revised" else cases.timing_21(q7_sql)
    ref = reference_answers()
    OUT.mkdir(parents=True, exist_ok=True)
    label = which if which == "q7revised" else f"timing21{'_' + q7_sql if q7_sql != 'plain' else ''}"
    path = OUT / f"runs_{engine}_{label}.csv"
    print(f"Benchmark {engine} / {label}: {len(selected)} cases x ({WARMUPS} warm-ups + {RUNS} measured)")
    print(f"started {datetime.now(db.CAT):%Y-%m-%d %H:%M:%S} CAT -> {path}")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for case in selected:
            run_case(engine, case, ref, writer)
            f.flush()
    db.close()
    print(f"finished {datetime.now(db.CAT):%Y-%m-%d %H:%M:%S} CAT")


def summary():
    runs = []
    for p in sorted(OUT.glob("runs_*.csv")):
        with open(p, encoding="utf-8", newline="") as f:
            runs += list(csv.DictReader(f))
    groups = {}
    for r in runs:
        if r["phase"] != "measured":
            continue
        key = (r["case"], r["engine"], r["sql_version"])
        groups.setdefault(key, []).append(r)

    def stats(rows):
        ms = [float(r["duration_ms"]) for r in rows if r["status"] == "ok"]
        return {"median": statistics.median(ms) if ms else None, "min": min(ms) if ms else None,
                "max": max(ms) if ms else None, "ok": len(ms),
                "timeout": sum(r["status"] == "timeout" for r in rows),
                "error": sum(r["status"] == "error" for r in rows),
                "correct": all(r["correct"] == "True" for r in rows if r["status"] == "ok")}

    order = [c.case_id for c in cases.timing_21()]
    lines = []
    for case_id in order:
        neo = groups.get((case_id, "neo", ""))
        for version in ("", "plain", "bidirectional"):
            pgr = groups.get((case_id, "pg", version))
            if not pgr:
                continue
            ps, ns = stats(pgr), stats(neo) if neo else None
            ratio = (ps["median"] / ns["median"]) if ns and ps["median"] and ns["median"] else None
            lines.append({"case": case_id, "pg_sql": version or "-", "pg": ps, "neo": ns, "ratio": ratio})
        if neo and not any((case_id, "pg", v) in groups for v in ("", "plain", "bidirectional")):
            lines.append({"case": case_id, "pg_sql": "-", "pg": None, "neo": stats(neo), "ratio": None})

    def fmt(v):
        return "-" if v is None else f"{v:,.1f}"

    head = (f"{'case':<12}{'PG SQL':<14}{'PG median':>11}{'PG min':>10}{'PG max':>10}{'PG ok/to/err':>13}"
            f"{'Neo median':>12}{'Neo min':>10}{'Neo max':>10}{'Neo ok/to/err':>14}{'PG/Neo':>9}")
    print("Medians, minimums and maximums in milliseconds over 5 measured runs; "
          "timeouts/errors counted separately")
    print(head)
    print("-" * len(head))
    with open(OUT / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case", "pg_sql", "pg_median_ms", "pg_min_ms", "pg_max_ms", "pg_ok", "pg_timeout", "pg_error",
                    "pg_correct", "neo_median_ms", "neo_min_ms", "neo_max_ms", "neo_ok", "neo_timeout",
                    "neo_error", "neo_correct", "pg_neo_median_ratio"])
        for ln in lines:
            ps, ns = ln["pg"], ln["neo"]
            pcount = f"{ps['ok']}/{ps['timeout']}/{ps['error']}" if ps else "-"
            ncount = f"{ns['ok']}/{ns['timeout']}/{ns['error']}" if ns else "-"
            ratio = f"{ln['ratio']:.2f}" if ln["ratio"] else "-"
            print(f"{ln['case']:<12}{ln['pg_sql']:<14}{fmt(ps and ps['median']):>11}{fmt(ps and ps['min']):>10}"
                  f"{fmt(ps and ps['max']):>10}{pcount:>13}{fmt(ns and ns['median']):>12}"
                  f"{fmt(ns and ns['min']):>10}{fmt(ns and ns['max']):>10}{ncount:>14}{ratio:>9}")
            w.writerow([ln["case"], ln["pg_sql"]]
                       + ([ps["median"], ps["min"], ps["max"], ps["ok"], ps["timeout"], ps["error"], ps["correct"]]
                          if ps else [""] * 7)
                       + ([ns["median"], ns["min"], ns["max"], ns["ok"], ns["timeout"], ns["error"], ns["correct"]]
                          if ns else [""] * 7)
                       + [ln["ratio"] if ln["ratio"] else ""])
    bad = [ln["case"] for ln in lines
           if (ln["pg"] and not ln["pg"]["correct"]) or (ln["neo"] and not ln["neo"]["correct"])]
    print(f"\nAll completed runs returned the reference answer: {'YES' if not bad else 'NO -> ' + ', '.join(bad)}")
    print(f"Saved {OUT / 'summary.csv'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("pg", "neo"))
    parser.add_argument("--cases", choices=("timing21", "q7revised"), default="timing21")
    parser.add_argument("--q7", choices=("plain", "bidirectional"), default="plain")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--allow-both", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)  # 1 warm-up + 1 run, testing only
    args = parser.parse_args()
    if args.dry_run:
        global WARMUPS, RUNS, OUT
        WARMUPS, RUNS, OUT = 1, 1, config.ROOT / "scratch" / "benchmark_dry"
    if args.summary:
        summary()
    elif args.engine:
        benchmark(args.engine, args.cases, args.q7, args.allow_both)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
