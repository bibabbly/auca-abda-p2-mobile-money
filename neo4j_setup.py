"""Section 3.2 step 3: after the import, start Neo4j and run this.

Creates unique constraints on the three business IDs and a range index on
TRANSFER.occurred_at, waits until every index is ONLINE, then records setup
seconds and store / transaction-log size (1 GB = 1,000,000,000 bytes).
Saves results/neo4j_setup.json.

Usage:  .venv\\Scripts\\python.exe neo4j_setup.py
"""
import json
import time
from pathlib import Path

from neo4j import GraphDatabase

import config

NEO4J_HOME = Path(r"D:\AUCA\neo4j-community")
STATEMENTS = [
    "CREATE CONSTRAINT customer_id_unique IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
    "CREATE CONSTRAINT account_id_unique  IF NOT EXISTS FOR (a:Account)  REQUIRE a.account_id IS UNIQUE",
    "CREATE CONSTRAINT device_id_unique   IF NOT EXISTS FOR (d:Device)   REQUIRE d.device_id IS UNIQUE",
    "CREATE RANGE INDEX transfer_occurred_at IF NOT EXISTS FOR ()-[t:TRANSFER]-() ON (t.occurred_at)",
]


def dir_bytes(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main():
    s = config.neo4j_settings()
    with GraphDatabase.driver(s["uri"], auth=s["auth"]) as driver, driver.session(database=s["database"]) as session:
        started = time.perf_counter()
        for stmt in STATEMENTS:
            t0 = time.perf_counter()
            session.run(stmt).consume()
            print(f"{time.perf_counter() - t0:7.2f} s  {' '.join(stmt.split())}")
        t0 = time.perf_counter()
        session.run("CALL db.awaitIndexes(3600)").consume()
        print(f"{time.perf_counter() - t0:7.2f} s  CALL db.awaitIndexes(3600)")
        setup_seconds = time.perf_counter() - started

        print("\nConstraints:")
        constraints = session.run("SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties "
                                  "RETURN name, type, entityType, labelsOrTypes, properties ORDER BY name").data()
        for c in constraints:
            print(f"  {c['name']:<22}{c['type']:<12}{c['entityType']:<8}{c['labelsOrTypes']} {c['properties']}")
        print("\nIndexes:")
        indexes = session.run("SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state, "
                              "populationPercent RETURN name, type, entityType, labelsOrTypes, properties, "
                              "state, populationPercent ORDER BY name").data()
        for i in indexes:
            print(f"  {i['name']:<22}{i['type']:<8}{i['entityType']:<14}{str(i['labelsOrTypes']):<16}"
                  f"{str(i['properties']):<18}{i['state']:<8}{i['populationPercent']}%")

    store = dir_bytes(NEO4J_HOME / "data" / "databases" / s["database"])
    txlog = dir_bytes(NEO4J_HOME / "data" / "transactions" / s["database"])
    imported = json.loads((config.RESULTS_DIR / "neo4j_import.json").read_text(encoding="utf-8-sig"))
    result = {"import_seconds": imported["import_seconds"], "setup_seconds": round(setup_seconds, 2),
              "store_bytes": store, "store_gb": round(store / 1e9, 3),
              "transaction_log_bytes": txlog, "transaction_log_gb": round(txlog / 1e9, 3),
              "constraints": constraints, "indexes": indexes,
              "all_online": all(i["state"] == "ONLINE" for i in indexes)}
    (config.RESULTS_DIR / "neo4j_setup.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"import seconds      : {imported['import_seconds']}")
    print(f"index/constraint s  : {setup_seconds:.1f}")
    print(f"store size          : {store / 1e9:.3f} GB")
    print(f"transaction logs    : {txlog / 1e9:.3f} GB")
    print(f"all indexes ONLINE  : {result['all_online']}   (saved results/neo4j_setup.json)")


if __name__ == "__main__":
    main()
