"""Section 2.2 step 3: verify the PostgreSQL load against capture.py.

Checks row counts, transfer audit totals, account roles, validated constraints,
indexes and data/index sizes (1 GB = 1,000,000,000 bytes).
Saves results/pg_checks.json.

Usage:  .venv\\Scripts\\python.exe pg_checks.py
"""
import json
import sys

import psycopg

import config

TABLES = ("customers", "accounts", "devices", "account_devices", "transfers")
ROLES = {"person": 240_000, "merchant": 6_000, "agent": 2_000}
GB = 1e9


def line(char="-"):
    print(char * 100)


def main():
    audit = json.loads((config.RESULTS_DIR / "capture_audit.json").read_text(encoding="utf-8"))
    cap = audit["streams"]
    cap_t = cap["transfers"]["audit"]
    report = {"counts": {}, "audit": {}, "roles": {}, "constraints": [], "indexes": [], "sizes": {}}
    ok = True

    with psycopg.connect(**config.pg_conninfo()) as conn:
        # 1. Row counts vs capture.py
        line("=")
        print(f"{'table':<18}{'PostgreSQL rows':>18}{'capture.py rows':>18}  status")
        line()
        for t in TABLES:
            n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            match = n == cap[t]["written"]
            ok &= match
            report["counts"][t] = {"postgres": n, "capture": cap[t]["written"], "match": match}
            print(f"{t:<18}{n:>18,}{cap[t]['written']:>18,}  {'OK' if match else 'MISMATCH'}")

        # 2. Transfer audit totals
        row = conn.execute("SELECT count(*), min(occurred_at), max(occurred_at), sum(amount_rwf), "
                           "to_timestamp(min(occurred_at)), to_timestamp(max(occurred_at)) "
                           "FROM transfers").fetchone()
        line("=")
        print(f"{'transfer audit':<22}{'PostgreSQL':>26}{'capture.py':>26}  status")
        line()
        for label, got, want in (("count", row[0], cap_t["count"]),
                                 ("earliest occurred_at", row[1], cap_t["earliest_occurred_at"]),
                                 ("latest occurred_at", row[2], cap_t["latest_occurred_at"]),
                                 ("sum amount_rwf", int(row[3]), cap_t["sum_amount_rwf"])):
            match = got == want
            ok &= match
            report["audit"][label] = {"postgres": got, "capture": want, "match": match}
            print(f"{label:<22}{got:>26,}{want:>26,}  {'OK' if match else 'MISMATCH'}")
        print(f"earliest CAT = {row[4]:%Y-%m-%d %H:%M:%S %z}   latest CAT = {row[5]:%Y-%m-%d %H:%M:%S %z}")

        # 3. Account roles
        line("=")
        print(f"{'role':<18}{'accounts':>18}{'expected':>18}  status")
        line()
        got_roles = dict(conn.execute("SELECT role, count(*) FROM accounts GROUP BY role").fetchall())
        for role, want in ROLES.items():
            got = got_roles.get(role, 0)
            match = got == want
            ok &= match
            report["roles"][role] = {"accounts": got, "expected": want, "match": match}
            print(f"{role:<18}{got:>18,}{want:>18,}  {'OK' if match else 'MISMATCH'}")
        extra = set(got_roles) - set(ROLES)
        if extra:
            ok = False
            print("unexpected roles:", extra)

        # 4. Constraints, all must be validated
        line("=")
        print(f"{'table':<18}{'constraint':<40}{'type':<13}validated")
        line()
        rows = conn.execute("""
            SELECT conrelid::regclass::text, conname,
                   CASE contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                                WHEN 'c' THEN 'CHECK' ELSE contype::text END,
                   convalidated, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid::regclass::text = ANY(%s) AND contype IN ('p', 'f', 'c')
            ORDER BY 1, 3, 2""", (list(TABLES),)).fetchall()
        for t, name, kind, valid, definition in rows:
            ok &= valid
            report["constraints"].append({"table": t, "name": name, "type": kind,
                                          "validated": valid, "definition": definition})
            print(f"{t:<18}{name:<40}{kind:<13}{valid}")
        not_null = conn.execute("""
            SELECT count(*) FILTER (WHERE a.attnotnull), count(*)
            FROM pg_attribute a WHERE a.attrelid::regclass::text = ANY(%s)
              AND a.attnum > 0 AND NOT a.attisdropped""", (list(TABLES),)).fetchone()
        ok &= not_null[0] == not_null[1]
        report["not_null_columns"] = {"not_null": not_null[0], "total": not_null[1]}
        print(f"NOT NULL columns: {not_null[0]} of {not_null[1]}")
        if len(rows) != 13:
            ok = False
            print(f"expected 13 constraints (5 PK, 5 FK, 3 CHECK), found {len(rows)}")

        # 5. Indexes
        line("=")
        print(f"{'table':<18}{'index':<32}{'GB':>9}  definition")
        line()
        for t, name, size, definition in conn.execute("""
                SELECT i.tablename, i.indexname, pg_relation_size(i.indexname::regclass), i.indexdef
                FROM pg_indexes i WHERE i.schemaname = 'public' AND i.tablename = ANY(%s)
                ORDER BY 1, 2""", (list(TABLES),)).fetchall():
            report["indexes"].append({"table": t, "name": name, "bytes": size, "definition": definition})
            print(f"{t:<18}{name:<32}{size / GB:>9.3f}  {definition.split(' USING ', 1)[-1]}")

        # 6. Data and index sizes
        line("=")
        print(f"{'table':<18}{'data GB':>12}{'index GB':>12}{'total GB':>12}")
        line()
        tot = [0, 0, 0]
        for t in TABLES:
            data, idx, total = conn.execute(
                "SELECT pg_table_size(%s), pg_indexes_size(%s), pg_total_relation_size(%s)",
                (t, t, t)).fetchone()
            tot = [tot[0] + data, tot[1] + idx, tot[2] + total]
            report["sizes"][t] = {"data_bytes": data, "index_bytes": idx, "total_bytes": total}
            print(f"{t:<18}{data / GB:>12.3f}{idx / GB:>12.3f}{total / GB:>12.3f}")
        db_name, db_size = conn.execute(
            "SELECT current_database(), pg_database_size(current_database())").fetchone()
        report["sizes"]["_tables_total"] = {"data_bytes": tot[0], "index_bytes": tot[1], "total_bytes": tot[2]}
        report["sizes"]["_database_bytes"] = db_size
        line()
        print(f"{'ALL TABLES':<18}{tot[0] / GB:>12.3f}{tot[1] / GB:>12.3f}{tot[2] / GB:>12.3f}")
        print(f"database {db_name} on disk: {db_size / GB:.3f} GB")

    report["all_ok"] = ok
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "pg_checks.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    line("=")
    print("ALL POSTGRESQL CHECKS:", "PASSED" if ok else "FAILED", "  (saved results/pg_checks.json)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
