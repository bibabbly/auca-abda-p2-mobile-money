"""Section 4: run the Q1 to Q3 SQL/Cypher pairs, compare, save full outputs and the Q2 chart.

  .venv\\Scripts\\python.exe run_section4.py q1
  .venv\\Scripts\\python.exe run_section4.py q2
  .venv\\Scripts\\python.exe run_section4.py q3
  .venv\\Scripts\\python.exe run_section4.py          # all three

Full outputs go to results/section4/, the chart to results/charts/q2_daily.png.
"""
import csv
import json
import sys
import time

import db
import config
from queries import QUERIES

OUT = config.RESULTS_DIR / "section4"


def run_pair(name, params):
    sql, cypher = QUERIES[name]
    t0 = time.perf_counter()
    pg_rows = db.normalize(db.run_pg(sql, params), sort=False)
    t1 = time.perf_counter()
    neo_rows = db.normalize(db.run_neo(cypher, params), sort=False)
    t2 = time.perf_counter()
    return pg_rows, neo_rows, sorted(pg_rows) == sorted(neo_rows), t1 - t0, t2 - t1


def save_rows(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def q1():
    print("Q1 Account activity: outgoing transfers 09:45:00 <= t < 10:45:00 CAT\n")
    print(QUERIES["Q1"][0], QUERIES["Q1"][1], sep="\n")
    print(f"{'set':<4}{'account':>8}  {'window CAT':<33}{'start':>11}{'end':>11}"
          f"{'PG count':>10}{'PG RWF':>13}{'Neo count':>11}{'Neo RWF':>13}  match")
    print("-" * 120)
    out = []
    for s in db.SETS:
        p = db.set_params(s)
        pg_rows, neo_rows, match, *_ = run_pair("Q1", p)
        (pc, pt), (nc, nt) = pg_rows[0], neo_rows[0]
        window = f"{db.cat_time(p['start'])} - {db.cat_time(p['end'])[11:]}"
        print(f"{s:<4}{p['account']:>8}  {window:<33}{p['start']:>11}{p['end']:>11}"
              f"{pc:>10,}{pt:>13,}{nc:>11,}{nt:>13,}  {'OK' if match else 'DIFF'}")
        out.append({"set": s, **p, "postgres": [pc, pt], "neo4j": [nc, nt], "match": match})
    (OUT / "q1.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return all(r["match"] for r in out)


def q2():
    print("Q2 Daily activity by CAT day, full month\n")
    print(QUERIES["Q2"][0], QUERIES["Q2"][1], sep="\n")
    pg_rows, neo_rows, match, pg_s, neo_s = run_pair("Q2", {})
    audit = json.loads((config.RESULTS_DIR / "capture_audit.json").read_text(encoding="utf-8"))
    cap = audit["streams"]["transfers"]["audit"]

    print(f"{'date (CAT)':<12}{'PG count':>12}{'PG total RWF':>18}{'Neo count':>12}{'Neo total RWF':>18}  match")
    print("-" * 80)
    for (d, c, t), (nd, nc, nt) in zip(pg_rows, neo_rows):
        print(f"{d:<12}{c:>12,}{t:>18,}{nc:>12,}{nt:>18,}  {'OK' if (d, c, t) == (nd, nc, nt) else 'DIFF'}")
    print("-" * 80)
    checks = {
        "days PostgreSQL": (len(pg_rows), 30),
        "days Neo4j": (len(neo_rows), 30),
        "sum count PostgreSQL": (sum(r[1] for r in pg_rows), cap["count"]),
        "sum count Neo4j": (sum(r[1] for r in neo_rows), cap["count"]),
        "sum RWF PostgreSQL": (sum(r[2] for r in pg_rows), cap["sum_amount_rwf"]),
        "sum RWF Neo4j": (sum(r[2] for r in neo_rows), cap["sum_amount_rwf"]),
        "first day": (pg_rows[0][0], "2026-09-01"),
        "last day": (pg_rows[-1][0], "2026-09-30"),
    }
    ok = match
    for label, (got, want) in checks.items():
        ok &= got == want
        print(f"{label:<24}{got:>22,}  vs capture {want:>22,}  {'OK' if got == want else 'MISMATCH'}"
              if isinstance(got, int) else f"{label:<24}{got:>22}  expected {want:>22}  "
              f"{'OK' if got == want else 'MISMATCH'}")
    print(f"PostgreSQL rows == Neo4j rows: {match}   (single untimed run: PG {pg_s:.1f} s, Neo4j {neo_s:.1f} s)")

    save_rows(OUT / "q2_postgres.csv", ["day", "transfers", "total_rwf"], pg_rows)
    save_rows(OUT / "q2_neo4j.csv", ["day", "transfers", "total_rwf"], neo_rows)
    plot_q2(pg_rows)
    return ok


def plot_q2(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from datetime import date

    days = [date.fromisoformat(r[0]) for r in rows]
    counts = [r[1] / 1e3 for r in rows]
    values = [r[2] / 1e9 for r in rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    ax1.bar(days, counts, color="#3b6ea5")
    ax1.set_ylabel("Transfers per day (thousands)")
    ax1.set_title("Q2 Daily transfer activity, September 2026 (CAT days)")
    ax1.set_ylim(min(counts) * 0.995, max(counts) * 1.002)
    ax2.plot(days, values, marker="o", color="#c0504d")
    ax2.set_ylabel("Transfer value per day (billion RWF)")
    ax2.set_xlabel("Date (Africa/Kigali)")
    for ax in (ax1, ax2):
        ax.grid(axis="y", alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    path = config.RESULTS_DIR / "charts" / "q2_daily.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"Chart saved: {path}")


def q3():
    print("Q3 Shared devices with overlapping observation days (review account excluded)\n")
    print(QUERIES["Q3"][0], QUERIES["Q3"][1], sep="\n")
    summary = []
    for s in db.SETS:
        p = db.set_params(s)
        pg_rows, neo_rows, match, *_ = run_pair("Q3", p)
        print(f"Set {s}  account {p['account']}:  PostgreSQL {len(pg_rows)} rows, Neo4j {len(neo_rows)} rows  "
              f"{'OK' if match else 'DIFF'}")
        print(f"   {'other_account':>13}{'device_id':>11}  {'access_type':<16}{'start':>6}{'end':>5}")
        for r in pg_rows:
            print(f"   {r[0]:>13}{r[1]:>11}  {r[2]:<16}{r[3]:>6}{r[4]:>5}")
        save_rows(OUT / f"q3_{s}_postgres.csv",
                  ["other_account", "device_id", "access_type", "overlap_start", "overlap_end"], pg_rows)
        save_rows(OUT / f"q3_{s}_neo4j.csv",
                  ["other_account", "device_id", "access_type", "overlap_start", "overlap_end"], neo_rows)
        summary.append({"set": s, "account": p["account"], "postgres_rows": len(pg_rows),
                        "neo4j_rows": len(neo_rows), "match": match})
    print("\nQ3 summary")
    print(f"{'set':<5}{'account':>8}{'PG rows':>9}{'Neo rows':>10}  match")
    for r in summary:
        print(f"{r['set']:<5}{r['account']:>8}{r['postgres_rows']:>9}{r['neo4j_rows']:>10}  "
              f"{'OK' if r['match'] else 'DIFF'}")
    (OUT / "q3_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return all(r["match"] for r in summary)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = [a.lower() for a in sys.argv[1:]] or ["q1", "q2", "q3"]
    results = {}
    for name in wanted:
        print("=" * 120)
        results[name] = {"q1": q1, "q2": q2, "q3": q3}[name]()
        print()
    db.close()
    print("Section 4:", ", ".join(f"{k.upper()} {'PASSED' if v else 'FAILED'}" for k, v in results.items()))
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
