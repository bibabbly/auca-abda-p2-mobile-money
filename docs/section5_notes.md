# Section 5 — draft explanations (edit into your own words)

All results identical in PostgreSQL and Neo4j: Q4 24/24, Q5 6/6, Q6 6/6, Q7 12/12.

## Q4 Ownership and device network (5.1)

Distinct other accounts reached (all regions):

| Set | Account | 4 links | 6 links | 8 links | 10 links |
|---|---|---|---|---|---|
| A | 998 | 10 | 43 | 175 | 187 |
| B | 147228 | 46 | 178 | 188 | 228 |
| C | 206978 | 146 | 483 | 832 | 1,433 |
| D | 237998 | 10 | 44 | 180 | 192 |
| E | 144228 | 47 | 183 | 193 | 230 |
| F | 203978 | 147 | 488 | 837 | 1,426 |

**Prediction (write yours from the 4 and 6 columns before you look at 8 and 10).** For example:
from 4→6 links the networks grew 3–4×, so a simple guess was another 3–4× per two links. In fact
A, B, D and E flatten out after 6–8 links (they run out of new shared phones), while C and F keep
growing (×1.7 per two links) because within 4 links they reach a public terminal (device 220020 for
C, 220170 for F) that links dozens of unrelated accounts. Say whether your prediction was right.

**Supporting path (set A, 4 links):**
Account 998 –USED_DEVICE– Device 228001 –USED_DEVICE– Account 16836 –OWNS– Customer 16836 –OWNS– Account 236836.

**How deeper links create weak associations.** Each extra hop adds accounts that are only linked
through someone else's phone, an old replacement handset or a public terminal. The 6-link example
goes Account 998 → Device 228001 → Account 24755 → Device 24751 (a household phone) → Account 24752
→ Device 227777 (a replacement handset) → Account 101752: account 101752 has no direct relationship
with 998 at all. At 10 links C and F "reach" about 1,430 accounts, mostly through one public terminal,
which is not evidence of any personal connection.

Chart: `results/charts/q4_depth.png` (log scale).

## Q5 Rapid onward payments (5.2)

Matches: A 1, B 1, C 1, D 0, E 0, F 0.

Example (set A): transfers 20000001 → 20000002 → 20000003, final receiver 24755

| transfer | sender → receiver | time (CAT) | gap | amount RWF | % of previous |
|---|---|---|---|---|---|
| 20000001 | 998 → 8917 | 2026-09-06 10:00:00 | – | 200,000 | – |
| 20000002 | 8917 → 16836 | 2026-09-06 10:00:40 | 40 s | 196,000 | 98.00 |
| 20000003 | 16836 → 24755 | 2026-09-06 10:01:20 | 40 s | 192,080 | 98.00 |

**Why this does not prove the same funds moved.** Wallet money is fungible: 8917 could have paid
16836 from its own existing balance, and the 200,000 from 998 could still be sitting in 8917's wallet.
Similar amounts 40 seconds apart are consistent with onward movement but also with coincidence,
pre-arranged payments (rent split, group contribution) or a chain of unrelated sales. We would need
balances before and after each transfer, and ideally the account holders' explanations.

## Q6 Circular payments (5.3)

Matches: A 1 (length 4), B 0, C 1 (length 6), D 0, E 0, F 0.

Example (set A): 20000001 → 20000002 → 20000003 → 20000004, back to 998 at 10:02:00,
span 120 s, each amount 98% of the previous (200,000 → 196,000 → 192,080 → 188,238 RWF).
Set C cycle: 20000229–20000234, 6 transfers back to 206978.

**Further evidence to request.** KYC details and relationships of 998, 8917, 16836, 24755 (all
person accounts, two of them share device 228001); balances before/after; the device and location
used to initiate each payment (not in the observations data); whether the accounts did similar
cycles on other days; and any fees charged, since a cycle that loses 6% overall could also be a
mistaken or reversed payment.

## Q7 Shortest transfer connection (5.4)

| Set | Review → destination | ≤ 4 | ≤ 6 |
|---|---|---|---|
| A | 998 → 24755 | 3 | 3 |
| B | 147228 → 186823 | none | 5 |
| C | 206978 → 6573 | none | 5 |
| D | 237998 → 21755 | 3 | 3 |
| E | 144228 → 183823 | none | 5 |
| F | 203978 → 3573 | none | 5 |

Every supporting path was verified in PostgreSQL: correct start and end, every transfer exists,
sender→receiver direction, all accounts `person`, length equals the shortest length.
Example (B, bound 6): 147228 → 147906 → 147310 → 148101 → 178904 → 186823 via transfers
11540891, 15207140, 18927851, 16500879, 20000096 — dated 18, 23, 29, 25 and 13 September, i.e.
the route runs backwards and forwards in time.

**Why "no route within 4" does not mean "no connection".** The bound stops the search; B, C, E and
F have no route of 4 transfers or fewer but all have one of 5. They could also be linked through
merchant or agent accounts (excluded here), through cash, other providers, banks or months outside
September.

**Why a structural route need not show onward movement.** Q7 ignores time order and amount. In the
B example the transfers happen on 18, 23, 29, 25 and 13 September — the last hop happens before the
first — and amounts range from 4,700 to 968,486 RWF, so money from 147228 cannot have travelled along
that route. It only shows that the accounts belong to the same payment network.

## Performance observations for Sections 6–8 (single runs, not the formal timings)

- Q4–Q6: both engines answer in well under 0.2 s.
- Q7: Neo4j SHORTEST ≈ 0.01–0.02 s for every case. Plain recursive SQL ≈ 0.5 s at bound 4 and
  40–52 s at bound 6 (72.6 s on the first cold run), because it keeps expanding every account at
  every depth up to 6 even after the destination is found at depth 3, and re-visits the same account
  at several depths. A bidirectional SQL version (3 steps forward + 3 back, join in the middle) gives
  identical answers in ≈ 0.1–0.16 s (Section 6.3).
