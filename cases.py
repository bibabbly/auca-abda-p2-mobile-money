"""Case lists shared by compare_61.py (Section 6.1), benchmark.py (6.2/6.3) and loadtest.py (7).

A case is one question with fixed parameters and its SQL and Cypher text.
Q7 has two SQL versions: "plain" (Section 5) and "bidirectional" (Section 6.3).
"""
from dataclasses import dataclass, field

import db
import queries as q

DEPTHS = (4, 6, 8, 10)
BOUNDS = (4, 6)
Q7_SQL = {"plain": q.Q7_SQL, "bidirectional": q.Q7_SQL_BIDIRECTIONAL}


@dataclass
class Case:
    case_id: str
    question: str
    set_name: str
    params: dict
    sql: str
    cypher: str
    extra: dict = field(default_factory=dict)


def _q1_to_q7(question, s, q7_sql="plain", depth=None, bound=None):
    p = db.set_params(s) if s != "month" else {}
    if question == "Q4":
        p = {**p, "depth": depth}
        return Case(f"Q4-{s}-d{depth}", "Q4", s, p, q.Q4_SQL, q.q4_cypher(depth), {"depth": depth})
    if question == "Q7":
        p = {**p, "bound": bound}
        return Case(f"Q7-{s}-b{bound}", "Q7", s, p, Q7_SQL[q7_sql], q.q7_cypher(bound),
                    {"bound": bound, "q7_sql": q7_sql})
    sql, cypher = q.QUERIES[question]
    return Case(f"{question}-{s}", question, s, p, sql, cypher)


def all_61(q7_sql="plain"):
    """Q1 6, Q2 1, Q3 6, Q4 24, Q5 6, Q6 6, Q7 12 = 61 cases."""
    sets = list(db.SETS)
    cases = [_q1_to_q7("Q1", s) for s in sets]
    cases.append(_q1_to_q7("Q2", "month"))
    cases += [_q1_to_q7("Q3", s) for s in sets]
    cases += [_q1_to_q7("Q4", s, depth=d) for s in sets for d in DEPTHS]
    cases += [_q1_to_q7("Q5", s) for s in sets]
    cases += [_q1_to_q7("Q6", s) for s in sets]
    cases += [_q1_to_q7("Q7", s, q7_sql, bound=b) for s in sets for b in BOUNDS]
    return cases


def timing_21(q7_sql="plain"):
    """Section 6.2: Q1/Q3/Q5/Q6 for B and E, Q2 full month, Q4 B/E x 4 depths, Q7 B/E x 2 bounds."""
    cases = []
    for question in ("Q1", "Q3", "Q5", "Q6"):
        cases += [_q1_to_q7(question, s) for s in ("B", "E")]
    cases.append(_q1_to_q7("Q2", "month"))
    cases += [_q1_to_q7("Q4", s, depth=d) for s in ("B", "E") for d in DEPTHS]
    cases += [_q1_to_q7("Q7", s, q7_sql, bound=b) for s in ("B", "E") for b in BOUNDS]
    return cases


def q7_revised():
    """Section 6.3: the four revised SQL cases, B/E at both bounds, bidirectional version."""
    return [_q1_to_q7("Q7", s, "bidirectional", bound=b) for s in ("B", "E") for b in BOUNDS]


def by_id(case_id, q7_sql="plain"):
    for c in all_61(q7_sql):
        if c.case_id == case_id:
            return c
    raise KeyError(case_id)
