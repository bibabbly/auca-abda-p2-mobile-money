"""Sections 6.2 / 6.3: collect execution plans outside the timed runs.

PostgreSQL: EXPLAIN (ANALYZE, BUFFERS) for Q2, Q4 B depth 10, Q7 B bound 6 (plain and
bidirectional SQL). Neo4j: PROFILE for Q2, Q4 B depth 10, Q7 B bound 6.

  .venv\\Scripts\\python.exe plans.py --engine pg
  .venv\\Scripts\\python.exe plans.py --engine neo

Saves results/plans/<engine>_<case>.txt
"""
import argparse

from neo4j import Query

import cases
import config
import db

OUT = config.RESULTS_DIR / "plans"


def pg_plans():
    targets = [("Q2-month", cases.by_id("Q2-month")),
               ("Q4-B-d10", cases.by_id("Q4-B-d10")),
               ("Q7-B-b6_plain", cases.by_id("Q7-B-b6", "plain")),
               ("Q7-B-b6_bidirectional", cases.by_id("Q7-B-b6", "bidirectional"))]
    db.run_pg("SET statement_timeout = 0")
    for name, c in targets:
        rows = db.run_pg("EXPLAIN (ANALYZE, BUFFERS) " + c.sql, c.params)
        text = "\n".join(r[0] for r in rows)
        save(f"pg_{name}", c, c.sql, text)


def fmt_profile(node, depth=0):
    args = node.get("args", {})
    details = args.get("Details", "")
    line = (f"{'  ' * depth}+{node.get('operatorType', '?'):<34} rows={node.get('rows', 0):<10,} "
            f"dbHits={node.get('dbHits', 0):<12,} "
            f"pageCacheHits={node.get('pageCacheHits', 0):,} misses={node.get('pageCacheMisses', 0):,}"
            f"{'  | ' + str(details)[:140] if details else ''}")
    lines = [line]
    for child in node.get("children", []):
        lines += fmt_profile(child, depth + 1)
    return lines


def neo_plans():
    targets = [("Q2-month", cases.by_id("Q2-month")),
               ("Q4-B-d10", cases.by_id("Q4-B-d10")),
               ("Q7-B-b6", cases.by_id("Q7-B-b6"))]
    session = db.neo()
    for name, c in targets:
        summary = session.run(Query("PROFILE " + c.cypher, timeout=600), c.params).consume()
        prof = summary.profile
        total_hits = sum_hits(prof)
        text = "\n".join(fmt_profile(prof)) + (
            f"\n\nTotal dbHits: {total_hits:,}   result available after "
            f"{summary.result_available_after} ms, consumed after {summary.result_consumed_after} ms")
        save(f"neo_{name}", c, c.cypher, text)


def sum_hits(node):
    return node.get("dbHits", 0) + sum(sum_hits(ch) for ch in node.get("children", []))


def save(name, case, query, plan):
    OUT.mkdir(parents=True, exist_ok=True)
    body = f"-- {name}  params={case.params}\n{query}\n{'=' * 100}\n{plan}\n"
    (OUT / f"{name}.txt").write_text(body, encoding="utf-8")
    print("=" * 100)
    print(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("pg", "neo"), required=True)
    args = parser.parse_args()
    pg_plans() if args.engine == "pg" else neo_plans()
    db.close()


if __name__ == "__main__":
    main()
