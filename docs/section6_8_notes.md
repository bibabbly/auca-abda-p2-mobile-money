# Sections 6–8 — draft analysis from measured results (edit into your own words)

Machine: Intel i7-1165G7 (4 cores / 8 threads), 34.1 GB RAM, Windows 11, PostgreSQL 18.4
(shared_buffers 8 GB, work_mem 64 MB), Neo4j 2026.10.1 Community (heap 8 GB, page cache 10 GB).
One service running at a time for 6.2 and 7.

## 6.1 Correctness

61/61 cases identical (Q1 6, Q2 1, Q3 6, Q4 24, Q5 6, Q6 6, Q7 12 lengths); 8/8 Q7 supporting paths
valid (start, end, existence, direction, person roles, length). Independent Python checks on the CSVs:
Q3 overlap 998/8917 on device 228001 = [0,29]; Q6 cycle 20000001→…→20000004 satisfies every rule.
No mismatches had to be resolved; the only change needed during development was Q2 Cypher speed
(Section 4 note), not its answer.

## 6.2 Timings (median ms of 5 measured runs; full table `results/benchmark/summary.csv`)

| Case | PostgreSQL | Neo4j | PG/Neo |
|---|---|---|---|
| Q1 B / E | 1.2 / 0.5 | 8.4 / 7.9 | 0.14 / 0.06 |
| Q3 B / E | 1.4 / 0.5 | 7.5 / 8.4 | 0.19 / 0.06 |
| Q5 B / E | 3.2 / 0.4 | 6.9 / 6.1 | 0.46 / 0.07 |
| Q6 B / E | 1.3 / 0.5 | 6.3 / 5.5 | 0.21 / 0.09 |
| Q2 month | 12,508 | 8,752 | 1.43 |
| Q4 B d4 / d6 / d8 / d10 | 3.0 / 6.1 / 11.7 / 23.0 | 6.3 / 7.2 / 7.3 / 6.2 | 0.48 / 0.84 / 1.60 / 3.69 |
| Q4 E d4 / d6 / d8 / d10 | 2.0 / 5.8 / 7.6 / 23.8 | 3.9 / 4.9 / 4.6 / 4.3 | 0.50 / 1.19 / 1.67 / 5.50 |
| Q7 B b4 / b6 (plain SQL) | 1,154 / **5 timeouts** | 10.5 / 10.4 | 110 / – |
| Q7 E b4 / b6 (plain SQL) | 1,173 / **5 timeouts** | 8.2 / 13.5 | 143 / – |

Reading: for indexed point lookups and short joins (Q1, Q3, Q5, Q6, shallow Q4) PostgreSQL is
2–16× faster, mostly fixed per-query overhead in Neo4j (Bolt + Cypher runtime ≈ 5–8 ms floor).
As Q4 depth rises PostgreSQL time grows (3 → 23 ms) while Neo4j stays flat (≈ 4–7 ms). The full-month
aggregation Q2 favoured Neo4j once it had the machine alone (8.8 s vs 12.5 s).

**One processing difference (plans in `results/plans/`).**
- Q7 B bound 6, plain SQL (`pg_Q7-B-b6_plain.txt`, run without a timeout: 107.5 s): the recursive
  CTE ran 7 iterations, produced 427,953 (account, depth) rows, did 187,957 index-only scans on
  `transfers_sender_time_idx` returning 14.6 million transfer rows, and 14.6 million `accounts_pk`
  lookups to check the person role — 60 million buffer hits. The planner estimated 3 rows per
  WorkTable scan; the actual was 26,851. UNION only removes duplicate (account, depth) pairs, so the
  same account is expanded again at every depth, and the search does not stop when the destination
  is reached at depth 5.
- Neo4j PROFILE (`neo_Q7-B-b6.txt`): a single `ShortestPath` operator with the person predicate
  applied inside the search, 18,794 db hits in total, ~26 ms. It is a breadth-first search that
  stops at the first (shortest) hit and visits each node once.
- Q2: Neo4j does a `DirectedRelationshipTypeScan` of 20,003,300 relationships plus 40 million
  property reads (60 million db hits); PostgreSQL does a Parallel Seq Scan (2 workers) of the
  1.2 GB table with partial + finalize HashAggregate, 12.1 s, and mis-estimates 393,887 day groups
  for an actual 30. Both are full scans; neither model has an advantage in principle.

## 6.3 SQL improvement (Q7)

Wasted work identified in the plan: re-expanding accounts at several depths, and searching all the
way to depth 6 although the answer appears earlier. Prediction: searching from both ends should cut
the work from roughly d^6 to 2·d^3 states (d ≈ 16 distinct person contacts per account), i.e. by
hundreds of times.

Attempt: bidirectional search — forward ⌈bound/2⌉ steps from the review account, backward ⌊bound/2⌋
steps from the destination (incoming transfers, person senders), minimum depth per account on each
side, join on shared accounts, `MIN(f.d + b.d)`. Kept both versions (`Q7_SQL`, `Q7_SQL_BIDIRECTIONAL`).

| Case | Plain SQL | Bidirectional SQL | Neo4j | New PG/Neo |
|---|---|---|---|---|
| Q7 B b4 | 1,154 | 6.8 | 10.5 | 0.65 |
| Q7 B b6 | timeout (107.5 s untimed) | 82.6 | 10.4 | 7.91 |
| Q7 E b4 | 1,173 | 10.9 | 8.2 | 1.33 |
| Q7 E b6 | timeout | 78.0 | 13.5 | 5.79 |

All 12 Q7 cases recheck correctly with the bidirectional version (`compare_61.py --q7 bidirectional`).
Selected for Section 7 and the final comparison: **bidirectional**. Outcome: B/E bound-6 medians fell
from >60 s to ≈ 80 ms (> 700× faster); Neo4j is still ≈ 6–8× faster at bound 6, but the gap is now
milliseconds, not minutes. Most of the original gap came from the SQL algorithm, not the data model.

## 7 Concurrency (median of 3 repetitions; `results/loadtest/summary.csv`, `charts/loadtest.png`)

| Engine | Workload | 1 client | 4 | 8 | 16 | p95 ms at 1 → 16 |
|---|---|---|---|---|---|---|
| PostgreSQL | Q4 d10 req/s | 22.3 | 82.8 | 120.9 | 115.7 | 139.5 → 464.4 |
| Neo4j | Q4 d10 req/s | 396.5 | 1,398.5 | 1,497.3 | 1,331.2 | 4.4 → 35.1 |
| PostgreSQL | Q7 b6 (bidir.) req/s | 6.8 | 22.5 | 28.8 | 27.8 | 204.4 → 925.8 |
| Neo4j | Q7 b6 req/s | 221.7 | 652.5 | 849.8 | 876.4 | 7.2 → 71.7 |

No errors, timeouts or wrong answers in any repetition.

**Scaling.** Both engines scale almost linearly from 1 to 4 clients, then flatten at 8: average CPU
jumps from 9–30% at 4 clients to 96–99% at 8 and 16 clients — the 8 hardware threads are saturated
(client processes and the database share the same laptop). From 8 to 16 clients throughput stays
flat or drops slightly while p95 latency roughly doubles (PostgreSQL Q4 211 → 464 ms; Neo4j Q7
17 → 72 ms): extra clients only queue.

**Throughput vs response time.** Throughput is the system's total completed work per second;
response time is what one analyst waits. At 16 clients PostgreSQL still completes ≈ 116 Q4 requests
per second, but an individual analyst's 95th-percentile wait is ≈ 0.46 s instead of 0.14 s.

**Does the graph advantage survive the SQL improvement?** In this experiment, yes for throughput:
Neo4j handled 12× (Q4) and 30× (Q7) more requests per second at 8 clients. Part of this is likely
per-query work in the PostgreSQL recursive CTEs (Q4 builds its edges CTE from all 1.07 million
ownership/device rows on every call); a precomputed edges table might narrow the gap — not tested. Limits: one laptop, both
client and server on the same CPU, three A–C accounts, 15 s windows, warm caches.

## 8.1 Investigation priority (Q3–Q7 evidence)

| Pair | Q3 shared devices | Q4 network (d10) | Q5 chains | Q6 cycles | Q7 shortest | Review first |
|---|---|---|---|---|---|---|
| A 998 / D 237998 | A 4 (incl. 3 on device 228001), D 4 | 187 / 192 | A 1, D 0 | A 1 (4 hops), D 0 | 3 / 3 | **A** |
| B 147228 / E 144228 | 9 / 9 | 228 / 230 | B 1, E 0 | 0 / 0 | none@4, 5@6 / same | **B** |
| C 206978 / F 203978 | 9 / 9 | 1,433 / 1,426 | C 1, F 0 | C 1 (6 hops), F 0 | none@4, 5@6 / same | **C** |

Q3, Q4 and Q7 look almost identical within each pair; the difference is the money pattern in Q5/Q6.
D/E/F also have 3- and 5-transfer routes to their destinations (Q7), but their transfers are spread
over days (e.g. D: 6, 8, 10 Sept, 45,000 RWF each) — normal repeated payments.

Detailed pair (A vs D): at 10:00:00 on 6 Sept 998 sent 200,000 RWF to 8917; 8917 sent 196,000 to
16836 forty seconds later; 16836 sent 192,080 to 24755; and 24755 returned 188,238 to 998 at 10:02:00
— four person accounts, 98% each hop, 2 minutes in total. Accounts 998, 8917, 16836 and 24755 were
all observed on handset 228001 for the whole month. D (237998) has the same shape of network but its
payments of 45,000 RWF to 5917 → 13836 → 21755 happen two days apart and never return.

**Ordinary explanation.** Four relatives or friends sharing one phone could be passing a contribution
round a savings group (ikimina), each keeping a small share (2%), or testing a new wallet. **Missing
evidence:** KYC relationships, balances before/after, which device initiated each payment, history
in other months, any cash-out at agents. If the four accounts belong to one household with a
documented savings group, priority drops; if the money ends in a cash-out shortly after, priority
rises. Do not call this fraud — it is a reason for enquiries.

Diagrams: reuse the Q6 cycle (998 → 8917 → 16836 → 24755 → 998, with times and amounts) and the Q4
4-link path (Account 998 – Device 228001 – Account 16836 – Customer 16836 – Account 236836).

## 8.2 Model recommendation — draft (≤ 500 words, edit)

**Reporting → PostgreSQL.** Daily totals (Q2) and per-account hourly activity (Q1) are set-based
aggregations over indexed columns. PostgreSQL answered Q1 in 0.5–1.2 ms vs Neo4j 8 ms; Q2 took 12.5 s
vs 8.8 s in Neo4j, so Neo4j is not slower at full scans here — evidence against a clean split — but
SQL `GROUP BY` with time-zone functions was simpler to write and did not need the day-key rewrite
that Neo4j needed (190 s → 39 s → 8.8 s warm).

**Traversal investigations → Neo4j.** Variable-depth device networks (Q4), payment cycles (Q6) and
shortest routes (Q7) are paths. Cypher expresses them as patterns (`*1..10`, `SHORTEST 1`) with
predicates inside the search; SQL needs recursive CTEs that are long and easy to get wrong. Neo4j
stayed at 4–14 ms for Q4 depth 10 and Q7 bound 6, PostgreSQL rose to 23 ms and 80 ms (after
rewriting Q7) or timed out (plain Q7).

**Concurrency.** Under 8–16 analysts on this laptop Neo4j delivered 12–32× the throughput with
13–23× lower p95.

**Load time and storage.** PostgreSQL: load + index/constraint setup (fill in total_load_seconds and
total_setup_seconds from your 2.2 screenshots) and 3.73 GB on disk (1.25 GB data + 2.47 GB indexes).
Neo4j: offline import 58.1 s + constraint/index setup 31.7 s; store 2.05 GB, transaction logs ≈ 0 GB
(the offline import writes no transaction log). Neo4j is smaller here mainly because PostgreSQL's two
covering transfer indexes are ≈ 1 GB each.

**SQL/Cypher and plan comparison.** Q7: the recursive CTE plan re-expanded 14.6 million transfer
rows; the Neo4j `ShortestPath` operator stopped after 18,794 db hits. The bidirectional SQL showed
that an algorithm change, not the model, removed most of the gap.

**Graph model vs implementation effects.** The model benefit: relationships are stored as adjacency
so following a transfer is a pointer hop and patterns read naturally. The implementation/algorithm
effects: Neo4j's built-in BFS with early stop, and PostgreSQL's lack of a visited set in recursive
CTEs. Our bidirectional SQL recovered >700× without changing the schema.

**Freshness.** Keep PostgreSQL as the system of record; copy to Neo4j for investigation with a
target of ≤ 15 minutes behind (change-data-capture or micro-batches). Stale data means a cycle
completed in the last minutes is missed or a closed account still appears — acceptable for
retrospective investigation, not for real-time blocking.

**Limits.** (1) One laptop, both client and server on the same 8 threads, warm caches, one month of
synthetic data; (2) only six review accounts and no writes during the tests — real operational
load and data growth could change the ranking.

## 8.3 Individual judgement — guidance (each member writes their own 150–200 words)

Pick a different finding each, e.g.:
- Theo: the Q7 plain-SQL vs bidirectional result (plan evidence; check: rerun with 1 more bound or
  with a visited-set rewrite; overturned if the gain came only from warm cache).
- Member 2: Q4 depth growth and the public-terminal effect for C/F (check: remove public terminals
  and rerun; overturned if C/F still grow faster).
- Member 3: the load-test saturation at 8 clients (check: run clients on another machine; overturned
  if throughput keeps rising when the DB has the CPU alone).

**LLM assistance statement (required).** State that Claude (Anthropic, model Claude Opus 5.5) helped
write and debug the Python/SQL/Cypher code and draft explanations; how you checked it: every query
pair compared across engines (61 cases), two answers re-derived from CSVs in plain Python, path
checks against PostgreSQL, rerunning all scripts yourselves and reading the plans.
