"""Section 3.2 step 4: verify the Neo4j graph against the source streams and capture.py.

Checks node counts, relationship counts and totals, account roles, exactly one
owner per account, unique transfer_id and the transfer audit totals.
Saves results/neo4j_checks.json.

Usage:  .venv\\Scripts\\python.exe neo4j_checks.py
"""
import json
import sys

from neo4j import GraphDatabase

import config

ROLES = {"person": 240_000, "merchant": 6_000, "agent": 2_000}


def line(char="-"):
    print(char * 92)


def status(ok):
    return "OK" if ok else "MISMATCH"


def main():
    audit = json.loads((config.RESULTS_DIR / "capture_audit.json").read_text(encoding="utf-8"))
    cap = audit["streams"]
    cap_t = cap["transfers"]["audit"]
    expected_nodes = {"Customer": cap["customers"]["written"], "Account": cap["accounts"]["written"],
                      "Device": cap["devices"]["written"]}
    expected_rels = {"OWNS": 248_000, "USED_DEVICE": cap["account_devices"]["written"],
                     "TRANSFER": cap["transfers"]["written"]}
    report, ok = {}, True

    s = config.neo4j_settings()
    with GraphDatabase.driver(s["uri"], auth=s["auth"]) as driver, driver.session(database=s["database"]) as ses:
        def one(query):
            return ses.run(query).single()[0]

        line("=")
        print(f"{'nodes / relationships':<24}{'Neo4j':>16}{'expected':>16}  status")
        line()
        counts = {}
        for label, want in expected_nodes.items():
            got = one(f"MATCH (n:{label}) RETURN count(n)")
            counts[label] = (got, want)
            print(f"{':' + label:<24}{got:>16,}{want:>16,}  {status(got == want)}")
        for rel, want in expected_rels.items():
            got = one(f"MATCH ()-[r:{rel}]->() RETURN count(r)")
            counts[rel] = (got, want)
            print(f"{':' + rel:<24}{got:>16,}{want:>16,}  {status(got == want)}")
        all_nodes, all_rels = one("MATCH (n) RETURN count(n)"), one("MATCH ()-[r]->() RETURN count(r)")
        counts["ALL NODES"], counts["ALL RELATIONSHIPS"] = (all_nodes, 704_600), (all_rels, 20_536_900)
        line()
        print(f"{'ALL NODES':<24}{all_nodes:>16,}{704_600:>16,}  {status(all_nodes == 704_600)}")
        print(f"{'ALL RELATIONSHIPS':<24}{all_rels:>16,}{20_536_900:>16,}  {status(all_rels == 20_536_900)}")
        report["counts"] = {k: {"neo4j": g, "expected": w, "match": g == w} for k, (g, w) in counts.items()}
        ok &= all(v["match"] for v in report["counts"].values())

        line("=")
        print(f"{'account role':<24}{'Neo4j':>16}{'expected':>16}  status")
        line()
        roles = {r["role"]: r["n"] for r in ses.run("MATCH (a:Account) RETURN a.role AS role, count(*) AS n")}
        report["roles"] = {}
        for role, want in ROLES.items():
            got = roles.get(role, 0)
            report["roles"][role] = {"neo4j": got, "expected": want, "match": got == want}
            ok &= got == want
            print(f"{role:<24}{got:>16,}{want:>16,}  {status(got == want)}")
        if set(roles) - set(ROLES):
            ok = False
            print("unexpected roles:", set(roles) - set(ROLES))

        line("=")
        bad_owner = one("MATCH (a:Account) WHERE COUNT { (:Customer)-[:OWNS]->(a) } <> 1 RETURN count(a)")
        dup = ses.run("MATCH ()-[t:TRANSFER]->() "
                      "RETURN count(t) AS n, count(DISTINCT t.transfer_id) AS d, "
                      "count(t.transfer_id) AS nonnull").single()
        unique_ok = dup["n"] == dup["d"] == dup["nonnull"]
        print(f"accounts without exactly one owner : {bad_owner:,}  {status(bad_owner == 0)}")
        print(f"TRANSFER count / distinct transfer_id / non-null : "
              f"{dup['n']:,} / {dup['d']:,} / {dup['nonnull']:,}  {status(unique_ok)}")
        report["one_owner_per_account"] = {"violations": bad_owner, "match": bad_owner == 0}
        report["unique_transfer_id"] = {"transfers": dup["n"], "distinct": dup["d"], "match": unique_ok}
        ok &= bad_owner == 0 and unique_ok

        line("=")
        print(f"{'transfer audit':<24}{'Neo4j':>22}{'capture.py':>22}  status")
        line()
        a = ses.run("MATCH ()-[t:TRANSFER]->() RETURN count(t) AS c, min(t.occurred_at) AS lo, "
                    "max(t.occurred_at) AS hi, sum(t.amount_rwf) AS total, "
                    "toString(datetime({epochSeconds: min(t.occurred_at), timezone: 'Africa/Kigali'})) AS lo_cat, "
                    "toString(datetime({epochSeconds: max(t.occurred_at), timezone: 'Africa/Kigali'})) AS hi_cat"
                    ).single()
        report["audit"] = {}
        for label, got, want in (("count", a["c"], cap_t["count"]),
                                 ("earliest occurred_at", a["lo"], cap_t["earliest_occurred_at"]),
                                 ("latest occurred_at", a["hi"], cap_t["latest_occurred_at"]),
                                 ("sum amount_rwf", a["total"], cap_t["sum_amount_rwf"])):
            report["audit"][label] = {"neo4j": got, "capture": want, "match": got == want}
            ok &= got == want
            print(f"{label:<24}{got:>22,}{want:>22,}  {status(got == want)}")
        print(f"earliest CAT = {a['lo_cat']}   latest CAT = {a['hi_cat']}")

    report["all_ok"] = ok
    (config.RESULTS_DIR / "neo4j_checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    line("=")
    print("ALL NEO4J CHECKS:", "PASSED" if ok else "FAILED", "  (saved results/neo4j_checks.json)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
