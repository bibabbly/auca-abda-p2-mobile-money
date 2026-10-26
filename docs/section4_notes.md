# Section 4 — draft explanations (edit into your own words)

## Q1 Account activity (4.1)

All six sets return exactly one outgoing transfer in 09:45–10:45 CAT, identical in both engines:
A 998: 1 / 200,000 RWF · B 147228: 1 / 1,050,000 · C 206978: 1 / 300,000 ·
D 237998: 1 / 45,000 · E 144228: 1 / 40,000 · F 203978: 1 / 30,000.

**Why outgoing value is not a balance.** Q1 adds up money *sent* in one hour. A balance would need
the opening balance, all incoming transfers, cash-in/cash-out at agents, fees and reversals over the
whole history. The dataset says transfers are "not a complete ledger of cash balances, fees or
reversals", so an account can send 1,050,000 RWF in an hour that it received minutes earlier and
still end the hour with a low balance, or a high one.

## Q2 Daily activity (4.2)

30 CAT days, 1–30 Sep 2026; both engines return identical rows; the sums reconcile with capture.py:
20,003,300 transfers and 231,482,327,870 RWF. All activity falls between 06:00 and 21:59:59 CAT.

**Pattern.** Daily counts are almost flat (~666,667 per day, about 20M / 30). Days 6–15 Sep carry
about 150–330 extra transfers each and visibly higher value (≈7.74–7.86 bn RWF vs ≈7.66–7.70 bn on
other days), so these ten days contain the extra transfers that the later investigations (Q5/Q6)
look at.

**Why transfer value is not provider revenue.** Value is the money customers move between wallets.
The provider earns fees and commissions, which are not in the data. P2P transfers may be free, fees
vary by tier and channel, and money passing through several wallets is counted again at each hop,
so total value overstates the economic activity and says nothing direct about revenue.

Chart: `results/charts/q2_daily.png` (transfers per day in thousands; value per day in billion RWF).

**Implementation note for Section 6/8.** The literal per-row Cypher form
(`date(datetime({epochSeconds: t.occurred_at, ...}))` for each of 20,003,300 relationships) took
~190 s; aggregating on the CAT day number first and converting only the 30 keys took ~39 s with the
same answer; a bare relationship scan takes ~21 s. PostgreSQL takes ~12–13 s. The difference comes
mostly from per-row work, not from the graph model.

## Q3 Shared devices (4.3)

Rows (identical in both engines): A 4, B 9, C 9, D 4, E 9, F 9.

**Legitimate sharing.** Set B: accounts 147226, 147227, 147229 and 147230 share handset 147226 with
the review account 147228 for the whole month (days 0–29) — consistent with one household phone
used by several family members. In set A, account 220998 shares handset 998: it is a second wallet
of the same customer (customer 998), so sharing the phone is expected.

**Why overlap does not prove simultaneous use.** An observation interval only records the first and
last day an account was seen on the device, plus a count. Intervals [2,7] and [5,11] overlap on
days 5–7, but one account could have used the phone at 08:00 and the other at 20:00, or on different
days within that range. The data also does not say which device initiated any payment.
