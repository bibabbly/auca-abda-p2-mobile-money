# 8.3 Fact sheets: one finding per member

Each member writes their own 150–200 words from their own sheet. Structure:
**finding (with numbers) → why it happens → one check that could overturn it.**

---

## Theo: Q7 shortest path, plain SQL vs bidirectional SQL

**Measured**
- Plain recursive SQL, bound 4: ≈1.15 s (B 1,154 ms, E 1,173 ms).
- Plain recursive SQL, bound 6: 5/5 timeouts at 60 s for both B and E; 107.5 s when run without a limit (EXPLAIN ANALYZE).
- Bidirectional SQL, bound 6: B 82.6 ms, E 78.0 ms. Same answers in all 12 cases.
- Neo4j SHORTEST, bound 6: B 10.4 ms, E 13.5 ms.

**Why (from the plan, `results/plans/pg_Q7-B-b6_plain.txt`)**
- 427,953 (account, depth) states; 14.6 million transfer rows read; 14.6 million account role checks; 60 million buffer hits.
- UNION only removes identical (account, depth) pairs, so an account is expanded again at each depth.
- The search keeps going after it reaches the destination.
- Planner estimate 3 rows per step vs 26,851 actual.
- Bidirectional: 3 steps from each end, so roughly 2·d³ states instead of d⁶.

**Checks that could overturn it**
- Run the bidirectional query with a cold cache (restart PostgreSQL first): does it stay in milliseconds?
- Try another fix (e.g. keeping a visited set or stopping at the first hit) to see whether bidirectional is the reason or any pruning would do.
- Test accounts with much higher degree (agents): bidirectional could blow up there.

---

## Eric: Q4 network growth with depth and the public-terminal effect

**Measured (distinct other accounts reached)**
| Set | 4 | 6 | 8 | 10 links |
|---|---|---|---|---|
| A 998 | 10 | 43 | 175 | 187 |
| B 147228 | 46 | 178 | 188 | 228 |
| C 206978 | 146 | 483 | 832 | 1,433 |
| D 237998 | 10 | 44 | 180 | 192 |
| E 144228 | 47 | 183 | 193 | 230 |
| F 203978 | 147 | 488 | 837 | 1,426 |

- A, B, D, E flatten after 6–8 links; C and F keep growing.
- C and F reach a **public terminal** within 4 links (devices 220020 and 220170). Each terminal is used by many unrelated accounts.
- Timing: PostgreSQL Q4 rises 3 → 23 ms from depth 4 to 10; Neo4j stays ≈ 4–7 ms.
- 6-link example from 998: Device 228001 → 24755 → household handset 24751 → 24752 → replacement handset 227777 → 101752 (no direct link to 998).

**Why**
- Households share one phone (5 customers per shared handset for some customers), replacement phones link a second set, and public terminals link dozens of strangers, so every extra 2 links can jump into a new cluster.

**Checks that could overturn it**
- Rerun Q4 for C and F excluding `access_type = 'public_terminal'` devices: if they still grow much faster than A/B/D/E, the terminal is not the reason.
- Count how many accounts use 220020 and 220170.

---

## Janvier: load test saturation at 8 clients

**Measured (median of 3 repetitions, requests per second)**
| Engine / workload | 1 | 4 | 8 | 16 clients | p95 ms 8 → 16 |
|---|---|---|---|---|---|
| PostgreSQL Q4 d10 | 22.3 | 82.8 | 120.9 | 115.7 | 211 → 464 |
| Neo4j Q4 d10 | 396.5 | 1,398.5 | 1,497.3 | 1,331.2 | 10.7 → 35.1 |
| PostgreSQL Q7 b6 | 6.8 | 22.5 | 28.8 | 27.8 | 391 → 926 |
| Neo4j Q7 b6 | 221.7 | 652.5 | 849.8 | 876.4 | 16.9 → 71.7 |

- Average CPU: 9–30 % at 4 clients, 96–99 % at 8 and 16 clients (8 hardware threads).
- No errors, timeouts or wrong answers.

**Why**
- The laptop has 4 cores / 8 threads, and the client processes and the database share them. At 8 clients the CPU is full, so more clients only wait in a queue: throughput stays flat and each request's wait (p95) roughly doubles.
- Throughput (total work) ≠ response time (one analyst's wait).

**Checks that could overturn it**
- Run the clients on a different machine so the database has the CPU to itself: if throughput keeps rising past 8 clients, the limit was the shared laptop, not the database.
- Rerun with 6 and 12 clients to find the exact knee.
