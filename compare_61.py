"""Section 6.1: check that both databases answer all 61 cases identically.

Every result row is fetched, integers are normalized and rows sorted before
exact comparison. Q7 lengths are compared separately from the validity of a
supporting path. Two answers are also re-derived independently from the
captured CSV files in plain Python (one device overlap, one chain/cycle).

  .venv\\Scripts\\python.exe compare_61.py                    # Q7 with the plain SQL
  .venv\\Scripts\\python.exe compare_61.py --q7 bidirectional # Section 6.3 recheck

Saves results/compare_61_<q7>.csv and .json.
"""
import argparse
import csv
import json
import sys
import time
from collections import Counter

import cases
import config
import db
import queries as q
from run_section5 import verify_path


def compare_all(q7_sql):
    results = []
    for c in cases.all_61(q7_sql):
        t0 = time.perf_counter()
        pg_rows = db.normalize(db.run_pg(c.sql, c.params))
        t1 = time.perf_counter()
        neo_rows = db.normalize(db.run_neo(c.cypher, c.params))
        t2 = time.perf_counter()
        match = pg_rows == neo_rows
        r = {"case": c.case_id, "question": c.question, "set": c.set_name,
             "postgres_rows": len(pg_rows), "neo4j_rows": len(neo_rows),
             "status": "MATCH" if match else "MISMATCH",
             "pg_seconds": round(t1 - t0, 3), "neo_seconds": round(t2 - t1, 3),
             "postgres": pg_rows, "neo4j": neo_rows}
        if c.question == "Q7":
            r["length_pg"], r["length_neo"] = pg_rows[0][0], neo_rows[0][0]
            r["status"] = "LENGTH MATCH" if match else "LENGTH MISMATCH"
            if match and r["length_pg"] is not None:
                accounts, ids = db.run_neo(q.q7_path_cypher(c.extra["bound"]),
                                           {"account": c.params["account"],
                                            "destination": c.params["destination"]})[0]
                checks, _ = verify_path(accounts, ids, c.params["account"], c.params["destination"],
                                        r["length_pg"])
                r["path"] = {"accounts": accounts, "transfer_ids": ids, "checks": checks}
                r["path_status"] = "PATH VALID" if all(checks.values()) else "PATH INVALID"
            else:
                r["path_status"] = "no route" if match else "-"
        print(f"{r['case']:<12}{r['postgres_rows']:>6}{r['neo4j_rows']:>6}  {r['status']:<16}"
              f"{r.get('path_status', ''):<14}{r['pg_seconds']:>8.2f}{r['neo_seconds']:>8.2f}", flush=True)
        results.append(r)
    return results


# ---------------------------------------------------------------- independent CSV checks
def read_csv(name):
    with open(config.CSV_DIR / f"{name}.csv", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def check_device_overlap(q3_row, account):
    """Recompute one Q3 row from account_devices.csv and devices.csv."""
    other, device, access, start, end = q3_row
    obs = {(int(r["account_id"]), int(r["device_id"])): (int(r["first_day"]), int(r["last_day"]))
           for r in read_csv("account_devices") if int(r["device_id"]) == device}
    access_csv = next(r["access_type"] for r in read_csv("devices") if int(r["device_id"]) == device)
    (f1, l1), (f2, l2) = obs[(account, device)], obs[(other, device)]
    got = (max(f1, f2), min(l1, l2))
    ok = got == (start, end) and got[0] <= got[1] and access_csv == access
    print(f"  CSV account_devices: account {account} on device {device} days [{f1},{l1}]; "
          f"account {other} days [{f2},{l2}]")
    print(f"  CSV devices: device {device} access_type={access_csv}")
    print(f"  overlap from CSV = [{got[0]},{got[1]}]   database row = [{start},{end}]   "
          f"{'OK' if ok else 'MISMATCH'}")
    return ok


def check_cycle(ids, account, start, end):
    """Re-verify one Q6 cycle by streaming transfers.csv in Python."""
    wanted = set(ids)
    found = {}
    for r in read_csv("transfers"):
        tid = int(r["transfer_id"])
        if tid in wanted:
            found[tid] = (int(r["sender_id"]), int(r["receiver_id"]), int(r["occurred_at"]), int(r["amount_rwf"]))
            if len(found) == len(wanted):
                break
    rows = [found[i] for i in ids]
    for tid, (s, rcv, t, amt) in zip(ids, rows):
        print(f"  CSV transfer {tid}: {s} -> {rcv}  {db.cat_time(t)} CAT  {amt:,} RWF")
    checks = {
        "starts at review account": rows[0][0] == account,
        "returns to review account at the end": rows[-1][1] == account,
        "no earlier return": all(r[1] != account for r in rows[:-1]),
        "consecutive (receiver = next sender)": all(a[1] == b[0] for a, b in zip(rows, rows[1:])),
        "strictly increasing time": all(a[2] < b[2] for a, b in zip(rows, rows[1:])),
        "inside review hour": all(start <= r[2] < end for r in rows),
        "span <= 1800 s": rows[-1][2] - rows[0][2] <= 1800,
        "amount rule 90-105%": all(90 * a[3] <= 100 * b[3] <= 105 * a[3] for a, b in zip(rows, rows[1:])),
        "length 3..8": 3 <= len(rows) <= 8,
    }
    for k, v in checks.items():
        print(f"    {k:<40}{'OK' if v else 'FAIL'}")
    return all(checks.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--q7", choices=("plain", "bidirectional"), default="plain")
    parser.add_argument("--skip-csv", action="store_true", help="skip the independent CSV checks")
    args = parser.parse_args()

    print(f"Section 6.1: 61-case comparison (Q7 SQL version: {args.q7})")
    print(f"{'case':<12}{'PG':>6}{'Neo':>6}  {'status':<16}{'Q7 path':<14}{'PG s':>8}{'Neo s':>8}")
    print("-" * 70)
    results = compare_all(args.q7)

    print("\n" + "=" * 70)
    print(f"{'question':<10}{'cases':>7}{'matching':>10}{'expected':>10}  status")
    print("-" * 70)
    expected = {"Q1": 6, "Q2": 1, "Q3": 6, "Q4": 24, "Q5": 6, "Q6": 6, "Q7": 12}
    per_q = Counter(r["question"] for r in results)
    ok_q = Counter(r["question"] for r in results if r["status"] in ("MATCH", "LENGTH MATCH"))
    all_ok = True
    for question, n in expected.items():
        good = per_q[question] == n == ok_q[question]
        all_ok &= good
        print(f"{question:<10}{per_q[question]:>7}{ok_q[question]:>10}{n:>10}  {'OK' if good else 'CHECK'}")
    paths = [r for r in results if r["question"] == "Q7" and r["path_status"].startswith("PATH")]
    valid = sum(r["path_status"] == "PATH VALID" for r in paths)
    all_ok &= valid == len(paths)
    print("-" * 70)
    print(f"{'TOTAL':<10}{len(results):>7}{sum(ok_q.values()):>10}{61:>10}  "
          f"{'ALL MATCH' if sum(ok_q.values()) == 61 == len(results) else 'MISMATCHES'}")
    print(f"Q7 supporting paths valid: {valid} of {len(paths)} successful cases")

    csv_ok = True
    if not args.skip_csv:
        print("\n" + "=" * 70)
        print("Independent check 1: one Q3 device overlap re-derived from the CSV files")
        q3a = next(r for r in results if r["case"] == "Q3-A")
        row = next((r for r in q3a["postgres"] if r[1] != r[0]), q3a["postgres"][0])
        csv_ok &= check_device_overlap(row, db.SETS["A"]["account"])
        print("\nIndependent check 2: one Q6 cycle re-derived from transfers.csv (streamed)")
        q6a = next(r for r in results if r["case"] == "Q6-A")
        p = db.set_params("A")
        csv_ok &= check_cycle(list(q6a["postgres"][0][0]), p["account"], p["start"], p["end"])

    out = config.RESULTS_DIR / f"compare_61_{args.q7}"
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case", "question", "set", "postgres_rows", "neo4j_rows", "status", "q7_path", "pg_s", "neo_s"])
        for r in results:
            w.writerow([r["case"], r["question"], r["set"], r["postgres_rows"], r["neo4j_rows"], r["status"],
                        r.get("path_status", ""), r["pg_seconds"], r["neo_seconds"]])
    out.with_suffix(".json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    db.close()

    ok = all_ok and csv_ok
    print("\n" + "=" * 70)
    print(f"61-CASE COMPARISON ({args.q7} Q7 SQL): {'PASSED' if ok else 'FAILED'}   "
          f"(saved {out.name}.csv/.json)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
