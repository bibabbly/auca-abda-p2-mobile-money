"""Section 5: run the Q4 to Q7 SQL/Cypher pairs, compare, and print the requested examples.

  .venv\\Scripts\\python.exe run_section5.py q4
  .venv\\Scripts\\python.exe run_section5.py q5
  .venv\\Scripts\\python.exe run_section5.py q6
  .venv\\Scripts\\python.exe run_section5.py q7

Full outputs go to results/section5/, the Q4 plot to results/charts/q4_depth.png.
"""
import json
import sys
import time

import db
import config
import queries as q

OUT = config.RESULTS_DIR / "section5"
DEPTHS = (4, 6, 8, 10)
BOUNDS = (4, 6)


def timed(fn, *args):
    t = time.perf_counter()
    rows = fn(*args)
    return rows, time.perf_counter() - t


def pair(sql, cypher, params):
    pg_rows, pg_s = timed(db.run_pg, sql, params)
    neo_rows, neo_s = timed(db.run_neo, cypher, params)
    pg_rows, neo_rows = db.normalize(pg_rows), db.normalize(neo_rows)
    return pg_rows, neo_rows, pg_rows == neo_rows, pg_s, neo_s


def transfer_details(ids):
    rows = db.run_pg("SELECT t.transfer_id, t.sender_id, s.role, t.receiver_id, r.role, t.occurred_at, t.amount_rwf "
                     "FROM transfers t JOIN accounts s ON s.account_id = t.sender_id "
                     "JOIN accounts r ON r.account_id = t.receiver_id "
                     "WHERE t.transfer_id = ANY(%(ids)s)", {"ids": list(ids)})
    by_id = {r[0]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def print_transfers(ids):
    print(f"   {'transfer_id':>11}{'sender':>8} {'role':<9}{'receiver':>9} {'role':<9}{'time (CAT)':>21}"
          f"{'gap s':>7}{'amount RWF':>12}{'% prev':>8}")
    prev = None
    for tid, s, sr, r, rr, t, amt in transfer_details(ids):
        gap = "" if prev is None else str(t - prev[0])
        pct = "" if prev is None else f"{100 * amt / prev[1]:.2f}"
        print(f"   {tid:>11}{s:>8} {sr:<9}{r:>9} {rr:<9}{db.cat_time(t):>21}{gap:>7}{amt:>12,}{pct:>8}")
        prev = (t, amt)


# ---------------------------------------------------------------- Q4
def q4():
    print("Q4 Ownership and device network: distinct other accounts within N links, by owner region")
    print(q.Q4_SQL, q.q4_cypher(4), sep="\n")
    rows_out, ok = [], True
    print(f"{'set':<4}{'account':>8}{'depth':>6}{'PG total':>10}{'Neo total':>10}{'PG s':>8}{'Neo s':>8}  match"
          "   regions (PostgreSQL)")
    print("-" * 120)
    for s in db.SETS:
        for depth in DEPTHS:
            p = {**db.set_params(s), "depth": depth}
            pg_rows, neo_rows, match, pg_s, neo_s = pair(q.Q4_SQL, q.q4_cypher(depth), p)
            ok &= match
            pt, nt = sum(r[1] for r in pg_rows), sum(r[1] for r in neo_rows)
            regions = ", ".join(f"{r}={n}" for r, n in pg_rows)
            print(f"{s:<4}{p['account']:>8}{depth:>6}{pt:>10,}{nt:>10,}{pg_s:>8.2f}{neo_s:>8.2f}  "
                  f"{'OK' if match else 'DIFF':<6}{regions}")
            rows_out.append({"set": s, "account": p["account"], "depth": depth, "postgres": pg_rows,
                             "neo4j": neo_rows, "postgres_total": pt, "neo4j_total": nt, "match": match})
    (OUT / "q4.json").write_text(json.dumps(rows_out, indent=2), encoding="utf-8")
    print(f"\nQ4: {sum(r['match'] for r in rows_out)} of {len(rows_out)} comparisons match")
    plot_q4(rows_out)
    q4_supporting_path()
    return ok


def plot_q4(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for s in db.SETS:
        pts = [(r["depth"], r["postgres_total"]) for r in rows if r["set"] == s]
        ax.plot([d for d, _ in pts], [n for _, n in pts], marker="o",
                label=f"{s} ({db.SETS[s]['account']})", linestyle="-" if s in "ABC" else "--")
    ax.set_xticks(DEPTHS)
    ax.set_xlabel("Maximum links (OWNS / USED_DEVICE, either direction)")
    ax.set_ylabel("Distinct other accounts reached")
    ax.set_yscale("log")
    ax.set_title("Q4 Accounts reached vs search depth (log scale)")
    ax.grid(alpha=0.3, which="both")
    ax.legend(title="Set (review account)")
    fig.tight_layout()
    path = config.RESULTS_DIR / "charts" / "q4_depth.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"Chart saved: {path}")


def q4_supporting_path():
    print("\nQ4 supporting paths (set A, Cypher shortestPath, labels and IDs)")
    a = db.SETS["A"]["account"]
    for length in (4, 6):
        rows = db.run_neo(f"""
            MATCH (a:Account {{account_id: $account}})
            MATCH (a)-[:OWNS|USED_DEVICE*1..{length}]-(b:Account)
            WHERE b <> a
            WITH a, collect(DISTINCT b) AS reached
            UNWIND reached AS b
            MATCH p = shortestPath((a)-[:OWNS|USED_DEVICE*..{length}]-(b))
            WITH p, length(p) AS len
            WHERE len = {length}
            RETURN [i IN range(0, length(p)) |
                      labels(nodes(p)[i])[0] + ' ' +
                      toString(coalesce(nodes(p)[i].account_id, nodes(p)[i].customer_id, nodes(p)[i].device_id))]
                   AS nodes,
                   [r IN relationships(p) | type(r)] AS rels
            ORDER BY nodes LIMIT 1""", {"account": a})
        if rows:
            nodes, rels = rows[0]
            text = nodes[0]
            for rel, node in zip(rels, nodes[1:]):
                text += f" -[{rel}]- {node}"
            print(f"  {length} links: {text}")


# ---------------------------------------------------------------- Q5
def q5():
    print("Q5 Rapid onward payments: 3 transfers, 4 distinct accounts, <= 600 s gaps, 90-105% amounts")
    print(q.Q5_SQL, q.Q5_CYPHER, sep="\n")
    return chain_question("Q5", q.Q5_SQL, q.Q5_CYPHER, lambda r: r[:3])


def q6():
    print("Q6 Circular payments: 3-8 transfers back to the review account within its hour, span <= 1800 s")
    print(q.Q6_SQL, q.Q6_CYPHER, sep="\n")
    return chain_question("Q6", q.Q6_SQL, q.Q6_CYPHER, lambda r: r[0])


def chain_question(name, sql, cypher, ids_of):
    out, ok, example = [], True, None
    for s in db.SETS:
        p = db.set_params(s)
        pg_rows, neo_rows, match, pg_s, neo_s = pair(sql, cypher, p)
        ok &= match
        out.append({"set": s, "account": p["account"], "postgres": pg_rows, "neo4j": neo_rows, "match": match})
        print(f"Set {s} account {p['account']:>6}: PostgreSQL {len(pg_rows)} rows, Neo4j {len(neo_rows)} rows  "
              f"{'OK' if match else 'DIFF'}   ({pg_s:.2f} s / {neo_s:.2f} s)")
        for r in pg_rows:
            print(f"     {r}")
        if example is None and pg_rows:
            example = (s, pg_rows[0])
    (OUT / f"{name.lower()}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n{name} summary")
    print(f"{'set':<5}{'account':>8}{'PG rows':>9}{'Neo rows':>10}  match")
    for r in out:
        print(f"{r['set']:<5}{r['account']:>8}{len(r['postgres']):>9}{len(r['neo4j']):>10}  "
              f"{'OK' if r['match'] else 'DIFF'}")
    if example:
        s, row = example
        print(f"\n{name} example from set {s}: {row}")
        print_transfers(ids_of(row))
    return ok


# ---------------------------------------------------------------- Q7
def verify_path(accounts, transfer_ids, start, destination, length):
    checks = {"starts at review account": accounts[0] == start,
              "ends at destination": accounts[-1] == destination,
              "length equals shortest": len(transfer_ids) == length == len(accounts) - 1}
    details = transfer_details(transfer_ids)
    checks["every transfer exists"] = len(details) == len(transfer_ids)
    checks["direction sender->receiver"] = all(d[1] == accounts[i] and d[3] == accounts[i + 1]
                                               for i, d in enumerate(details))
    checks["all accounts person"] = all(d[2] == "person" and d[4] == "person" for d in details)
    return checks, details


def q7():
    print("Q7 Shortest directed transfer connection, person accounts only, bounds 4 and 6")
    print(q.Q7_SQL, q.q7_cypher(6), sep="\n")
    out, ok = [], True
    print(f"{'set':<4}{'account':>8}{'destination':>12}{'bound':>6}{'PG length':>10}{'Neo length':>11}"
          f"{'PG s':>8}{'Neo s':>8}  match")
    print("-" * 80)
    for s in db.SETS:
        for bound in BOUNDS:
            p = {**db.set_params(s), "bound": bound}
            pg_rows, neo_rows, match, pg_s, neo_s = pair(q.Q7_SQL, q.q7_cypher(bound), p)
            ok &= match
            pl, nl = pg_rows[0][0], neo_rows[0][0]
            print(f"{s:<4}{p['account']:>8}{p['destination']:>12}{bound:>6}{str(pl if pl is not None else 'none'):>10}"
                  f"{str(nl if nl is not None else 'none'):>11}{pg_s:>8.2f}{neo_s:>8.2f}  {'OK' if match else 'DIFF'}")
            out.append({"set": s, **{k: p[k] for k in ("account", "destination")}, "bound": bound,
                        "postgres": pl, "neo4j": nl, "match": match})

    print("\nQ7 path checks (path from Neo4j SHORTEST, each step verified in PostgreSQL)")
    for r in out:
        if r["postgres"] is None:
            continue
        p = {"account": r["account"], "destination": r["destination"]}
        accounts, ids = db.run_neo(q.q7_path_cypher(r["bound"]), p)[0]
        checks, details = verify_path(accounts, ids, r["account"], r["destination"], r["postgres"])
        r["path"] = {"accounts": accounts, "transfer_ids": ids, "checks": checks}
        ok &= all(checks.values())
        print(f"Set {r['set']} bound {r['bound']}: accounts {' -> '.join(map(str, accounts))}   transfers {ids}   "
              f"{'ALL CHECKS OK' if all(checks.values()) else checks}")
        for d in details:
            print(f"      {d[0]:>9}: {d[1]} ({d[2]}) -> {d[3]} ({d[4]})  {db.cat_time(d[5])}  {d[6]:,} RWF")
    (OUT / "q7.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nQ7: {sum(r['match'] for r in out)} of {len(out)} length comparisons match")
    return ok


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = [a.lower() for a in sys.argv[1:]] or ["q4", "q5", "q6", "q7"]
    results = {}
    for name in wanted:
        print("=" * 120)
        results[name] = {"q4": q4, "q5": q5, "q6": q6, "q7": q7}[name]()
        print()
    db.close()
    print("Section 5:", ", ".join(f"{k.upper()} {'PASSED' if v else 'FAILED'}" for k, v in results.items()))
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
