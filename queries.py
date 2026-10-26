"""Parameterized SQL/Cypher pairs for Q1 to Q7 (stored data only).

SQL placeholders are psycopg %(name)s parameters; Cypher uses $name.
"""

# Q1 Account activity: outgoing count and total RWF in the review hour, all receiver roles.
Q1_SQL = """
SELECT COUNT(*) AS transfers, COALESCE(SUM(amount_rwf), 0) AS total_rwf
FROM transfers
WHERE sender_id = %(account)s
  AND occurred_at >= %(start)s AND occurred_at < %(end)s
"""
Q1_CYPHER = """
MATCH (a:Account {account_id: $account})-[t:TRANSFER]->()
WHERE t.occurred_at >= $start AND t.occurred_at < $end
RETURN count(t) AS transfers, coalesce(sum(t.amount_rwf), 0) AS total_rwf
"""

# Q2 Daily activity: CAT calendar day, count and total RWF for the full month.
Q2_SQL = """
SELECT (to_timestamp(occurred_at) AT TIME ZONE 'Africa/Kigali')::date AS day,
       COUNT(*) AS transfers, SUM(amount_rwf) AS total_rwf
FROM transfers
GROUP BY 1
ORDER BY 1
"""
# Used version: aggregate on the CAT day number first (CAT is a fixed UTC+02:00, no DST),
# then convert only the 30 day keys with datetime(). Same 30 rows as the per-row form,
# ~39 s instead of ~190 s, because datetime() runs 30 times instead of 20,003,300.
Q2_CYPHER = """
MATCH ()-[t:TRANSFER]->()
WITH (t.occurred_at + 7200) / 86400 AS cat_day, count(*) AS transfers, sum(t.amount_rwf) AS total_rwf
RETURN date(datetime({epochSeconds: cat_day * 86400, timezone: 'Africa/Kigali'})) AS day,
       transfers, total_rwf
ORDER BY day
"""
# Literal per-row form, kept for the report comparison (same answer, ~190 s on this machine).
Q2_CYPHER_PER_ROW = """
MATCH ()-[t:TRANSFER]->()
WITH date(datetime({epochSeconds: t.occurred_at, timezone: 'Africa/Kigali'})) AS day, t.amount_rwf AS amount
RETURN day, count(*) AS transfers, sum(amount) AS total_rwf
ORDER BY day
"""

# Q3 Shared devices: other accounts on the review account's devices with overlapping days.
Q3_SQL = """
SELECT o.account_id AS other_account, o.device_id, d.access_type,
       GREATEST(r.first_day, o.first_day) AS overlap_start,
       LEAST(r.last_day, o.last_day)      AS overlap_end
FROM account_devices r
JOIN account_devices o ON o.device_id = r.device_id AND o.account_id <> r.account_id
JOIN devices d         ON d.device_id = r.device_id
WHERE r.account_id = %(account)s
  AND GREATEST(r.first_day, o.first_day) <= LEAST(r.last_day, o.last_day)
ORDER BY other_account, o.device_id
"""
Q3_CYPHER = """
MATCH (a:Account {account_id: $account})-[r:USED_DEVICE]->(d:Device)<-[o:USED_DEVICE]-(b:Account)
WHERE b <> a
WITH b, d,
     CASE WHEN r.first_day > o.first_day THEN r.first_day ELSE o.first_day END AS overlap_start,
     CASE WHEN r.last_day  < o.last_day  THEN r.last_day  ELSE o.last_day  END AS overlap_end
WHERE overlap_start <= overlap_end
RETURN b.account_id AS other_account, d.device_id AS device_id, d.access_type AS access_type,
       overlap_start, overlap_end
ORDER BY other_account, device_id
"""

# Q4 Ownership and device network: distinct other accounts within <depth> OWNS/USED_DEVICE
# links in either direction (no transfers, no date filter), counted once, by owner region.
Q4_SQL = """
WITH RECURSIVE edges(sk, si, dk, di) AS (
    SELECT 'Customer', customer_id, 'Account', account_id FROM accounts
    UNION ALL
    SELECT 'Account', account_id, 'Customer', customer_id FROM accounts
    UNION ALL
    SELECT 'Account', account_id, 'Device', device_id FROM account_devices
    UNION ALL
    SELECT 'Device', device_id, 'Account', account_id FROM account_devices
), walk(kind, id, depth) AS (
    SELECT 'Account', %(account)s::integer, 0
    UNION
    SELECT e.dk, e.di, w.depth + 1
    FROM walk w JOIN edges e ON e.sk = w.kind AND e.si = w.id
    WHERE w.depth < %(depth)s
)
SELECT c.region, COUNT(DISTINCT w.id) AS accounts
FROM walk w
JOIN accounts a  ON a.account_id = w.id
JOIN customers c ON c.customer_id = a.customer_id
WHERE w.kind = 'Account' AND w.id <> %(account)s
GROUP BY c.region
ORDER BY c.region
"""


def q4_cypher(depth):
    # Variable-length bounds cannot be parameters in Cypher, so the depth is formatted in.
    return f"""
MATCH (a:Account {{account_id: $account}})
MATCH (a)-[:OWNS|USED_DEVICE*1..{int(depth)}]-(b:Account)
WHERE b <> a
WITH DISTINCT b
MATCH (c:Customer)-[:OWNS]->(b)
RETURN c.region AS region, count(b) AS accounts
ORDER BY region
"""


# Q5 Rapid onward payments: three directed transfers through four distinct accounts; the first
# from the review account inside its hour, each next one strictly later and at most 600 s later,
# each onward amount 90%..105% of the previous one.
Q5_SQL = """
SELECT t1.transfer_id AS t1_id, t2.transfer_id AS t2_id, t3.transfer_id AS t3_id,
       t3.receiver_id AS final_receiver
FROM transfers t1
JOIN transfers t2 ON t2.sender_id = t1.receiver_id
                 AND t2.occurred_at > t1.occurred_at AND t2.occurred_at <= t1.occurred_at + 600
JOIN transfers t3 ON t3.sender_id = t2.receiver_id
                 AND t3.occurred_at > t2.occurred_at AND t3.occurred_at <= t2.occurred_at + 600
WHERE t1.sender_id = %(account)s
  AND t1.occurred_at >= %(start)s AND t1.occurred_at < %(end)s
  AND 90::bigint * t1.amount_rwf <= 100::bigint * t2.amount_rwf
  AND 100::bigint * t2.amount_rwf <= 105::bigint * t1.amount_rwf
  AND 90::bigint * t2.amount_rwf <= 100::bigint * t3.amount_rwf
  AND 100::bigint * t3.amount_rwf <= 105::bigint * t2.amount_rwf
  AND t1.receiver_id <> t1.sender_id
  AND t2.receiver_id NOT IN (t1.sender_id, t1.receiver_id)
  AND t3.receiver_id NOT IN (t1.sender_id, t1.receiver_id, t2.receiver_id)
ORDER BY t1_id, t2_id, t3_id, final_receiver
"""
Q5_CYPHER = """
MATCH (a:Account {account_id: $account})-[t1:TRANSFER]->(b:Account)
WHERE t1.occurred_at >= $start AND t1.occurred_at < $end
MATCH (b)-[t2:TRANSFER]->(c:Account)
WHERE t2.occurred_at > t1.occurred_at AND t2.occurred_at <= t1.occurred_at + 600
  AND 90 * t1.amount_rwf <= 100 * t2.amount_rwf AND 100 * t2.amount_rwf <= 105 * t1.amount_rwf
MATCH (c)-[t3:TRANSFER]->(d:Account)
WHERE t3.occurred_at > t2.occurred_at AND t3.occurred_at <= t2.occurred_at + 600
  AND 90 * t2.amount_rwf <= 100 * t3.amount_rwf AND 100 * t3.amount_rwf <= 105 * t2.amount_rwf
  AND a <> b AND a <> c AND a <> d AND b <> c AND b <> d AND c <> d
RETURN t1.transfer_id AS t1_id, t2.transfer_id AS t2_id, t3.transfer_id AS t3_id,
       d.account_id AS final_receiver
ORDER BY t1_id, t2_id, t3_id, final_receiver
"""

# Q6 Circular payments: 3..8 transfers from and back to the review account, all inside its hour,
# strictly increasing times, span <= 1800 s, Q5 amount rule, stop at the first return.
Q6_SQL = """
WITH RECURSIVE walk(cur, ids, first_t, last_t, last_amt, len) AS (
    SELECT receiver_id, ARRAY[transfer_id], occurred_at, occurred_at, amount_rwf, 1
    FROM transfers
    WHERE sender_id = %(account)s
      AND occurred_at >= %(start)s AND occurred_at < %(end)s
    UNION ALL
    SELECT t.receiver_id, w.ids || t.transfer_id, w.first_t, t.occurred_at, t.amount_rwf, w.len + 1
    FROM walk w
    JOIN transfers t ON t.sender_id = w.cur
                    AND t.occurred_at > w.last_t
                    AND t.occurred_at < %(end)s
                    AND t.occurred_at <= w.first_t + 1800
    WHERE w.len < 8
      AND w.cur <> %(account)s
      AND 90::bigint * w.last_amt <= 100::bigint * t.amount_rwf
      AND 100::bigint * t.amount_rwf <= 105::bigint * w.last_amt
)
SELECT ids AS transfer_ids, len AS length
FROM walk
WHERE cur = %(account)s AND len >= 3
ORDER BY ids
"""
Q6_CYPHER = """
MATCH (a:Account {account_id: $account})
MATCH p = (a) (()-[t:TRANSFER]->() WHERE t.occurred_at >= $start AND t.occurred_at < $end){3,8} (a)
WITH p, a, relationships(p) AS ts
WHERE last(ts).occurred_at - ts[0].occurred_at <= 1800
  AND all(i IN range(1, size(ts) - 1)
          WHERE ts[i].occurred_at > ts[i - 1].occurred_at
            AND 90 * ts[i - 1].amount_rwf <= 100 * ts[i].amount_rwf
            AND 100 * ts[i].amount_rwf <= 105 * ts[i - 1].amount_rwf)
  AND none(n IN nodes(p)[1..-1] WHERE n = a)
RETURN [t IN ts | t.transfer_id] AS transfer_ids, size(ts) AS length
ORDER BY transfer_ids
"""

# Q7 Shortest transfer connection: fewest directed transfers from review account to destination
# over the month, every account on the route a person, within <bound> transfers.
# NULL / no row means no route within the bound.
Q7_SQL = """
WITH RECURSIVE bfs(node, depth) AS (
    SELECT a.account_id, 0 FROM accounts a
    WHERE a.account_id = %(account)s AND a.role = 'person'
    UNION
    SELECT t.receiver_id, b.depth + 1
    FROM bfs b
    JOIN transfers t ON t.sender_id = b.node
    JOIN accounts r  ON r.account_id = t.receiver_id AND r.role = 'person'
    WHERE b.depth < %(bound)s
)
SELECT MIN(depth) AS shortest_length FROM bfs WHERE node = %(destination)s
"""


# Section 6.3 improvement: search from both ends. Forward ceil(bound/2) steps from the review
# account, backward floor(bound/2) steps from the destination, keep each account's minimum
# depth on each side, and join on shared accounts. Any route of length L <= bound has a node at
# forward distance <= ceil(bound/2) whose remaining distance is <= floor(bound/2), so the minimum
# of forward + backward depth is the shortest length (NULL when there is none within the bound).
Q7_SQL_BIDIRECTIONAL = """
WITH RECURSIVE fwd(node, depth) AS (
    SELECT a.account_id, 0 FROM accounts a
    WHERE a.account_id = %(account)s AND a.role = 'person'
    UNION
    SELECT t.receiver_id, f.depth + 1
    FROM fwd f
    JOIN transfers t ON t.sender_id = f.node
    JOIN accounts r  ON r.account_id = t.receiver_id AND r.role = 'person'
    WHERE f.depth < (%(bound)s + 1) / 2
), bwd(node, depth) AS (
    SELECT a.account_id, 0 FROM accounts a
    WHERE a.account_id = %(destination)s AND a.role = 'person'
    UNION
    SELECT t.sender_id, b.depth + 1
    FROM bwd b
    JOIN transfers t ON t.receiver_id = b.node
    JOIN accounts s  ON s.account_id = t.sender_id AND s.role = 'person'
    WHERE b.depth < %(bound)s / 2
), f AS (SELECT node, MIN(depth) AS d FROM fwd GROUP BY node),
   b AS (SELECT node, MIN(depth) AS d FROM bwd GROUP BY node)
SELECT MIN(f.d + b.d) AS shortest_length
FROM f JOIN b ON b.node = f.node
"""


def q7_cypher(bound):
    return f"""
MATCH (a:Account {{account_id: $account}}), (d:Account {{account_id: $destination}})
WHERE a.role = 'person' AND d.role = 'person'
OPTIONAL MATCH p = SHORTEST 1 (a) (()-[:TRANSFER]->(:Account {{role: 'person'}})){{1,{int(bound)}}} (d)
RETURN min(length(p)) AS shortest_length
"""


def q7_path_cypher(bound):
    return f"""
MATCH (a:Account {{account_id: $account}}), (d:Account {{account_id: $destination}})
MATCH p = SHORTEST 1 (a) (()-[:TRANSFER]->(:Account {{role: 'person'}})){{1,{int(bound)}}} (d)
RETURN [n IN nodes(p) | n.account_id] AS accounts, [r IN relationships(p) | r.transfer_id] AS transfer_ids
"""


QUERIES = {
    "Q1": (Q1_SQL, Q1_CYPHER),
    "Q2": (Q2_SQL, Q2_CYPHER),
    "Q3": (Q3_SQL, Q3_CYPHER),
    "Q5": (Q5_SQL, Q5_CYPHER),
    "Q6": (Q6_SQL, Q6_CYPHER),
}
