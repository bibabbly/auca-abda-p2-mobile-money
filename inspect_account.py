"""Section 3.3: trace one account to its owner, a device and an outgoing transfer
in both models, and check the two answers match.

Usage:  .venv\\Scripts\\python.exe inspect_account.py [account_id]   (default 998, set A)
PostgreSQL and Neo4j must both be running.
"""
import sys

import psycopg
from neo4j import GraphDatabase

import config

SQL = """
SELECT a.account_id, a.role, c.customer_id, c.region,
       ad.device_id, d.access_type, ad.first_day, ad.last_day, ad.observations,
       t.transfer_id, t.receiver_id, t.occurred_at, t.amount_rwf
FROM accounts a
JOIN customers c ON c.customer_id = a.customer_id
JOIN LATERAL (SELECT * FROM account_devices x
              WHERE x.account_id = a.account_id
              ORDER BY x.device_id LIMIT 1) ad ON true
JOIN devices d ON d.device_id = ad.device_id
JOIN LATERAL (SELECT * FROM transfers y
              WHERE y.sender_id = a.account_id
              ORDER BY y.occurred_at, y.transfer_id LIMIT 1) t ON true
WHERE a.account_id = %(account)s
"""

CYPHER = """
MATCH (c:Customer)-[:OWNS]->(a:Account {account_id: $account})
MATCH (a)-[u:USED_DEVICE]->(d:Device)
WITH c, a, u, d ORDER BY d.device_id LIMIT 1
MATCH (a)-[t:TRANSFER]->(r:Account)
WITH c, a, u, d, t, r ORDER BY t.occurred_at, t.transfer_id LIMIT 1
RETURN a.account_id AS account_id, a.role AS role, c.customer_id AS customer_id, c.region AS region,
       d.device_id AS device_id, d.access_type AS access_type, u.first_day AS first_day,
       u.last_day AS last_day, u.observations AS observations,
       t.transfer_id AS transfer_id, r.account_id AS receiver_id, t.occurred_at AS occurred_at,
       t.amount_rwf AS amount_rwf
"""


def main():
    account = int(sys.argv[1]) if len(sys.argv) > 1 else 998
    params = {"account": account}

    with psycopg.connect(**config.pg_conninfo()) as conn:
        cur = conn.execute(SQL, params)
        cols = [c.name for c in cur.description]
        pg = dict(zip(cols, cur.fetchone()))

    s = config.neo4j_settings()
    with GraphDatabase.driver(s["uri"], auth=s["auth"]) as driver, driver.session(database=s["database"]) as ses:
        neo = ses.run(CYPHER, params).single().data()

    print("SQL:" + SQL)
    print("Cypher:" + CYPHER)
    print(f"{'field':<16}{'PostgreSQL':>20}{'Neo4j':>20}  match")
    print("-" * 64)
    same = True
    for col in cols:
        match = pg[col] == neo[col]
        same &= match
        print(f"{col:<16}{str(pg[col]):>20}{str(neo[col]):>20}  {'OK' if match else 'DIFF'}")
    from datetime import datetime
    from zoneinfo import ZoneInfo
    print(f"\noccurred_at {pg['occurred_at']} = "
          f"{datetime.fromtimestamp(pg['occurred_at'], ZoneInfo(config.TZ)):%Y-%m-%d %H:%M:%S} CAT")
    print("BOTH MODELS RETURN THE SAME RECORD" if same else "MODELS DIFFER")


if __name__ == "__main__":
    main()
