"""Shared database access and review-set parameters for Sections 4 to 7.

run_pg(query, params) and run_neo(query, params) return every result row as a
list of tuples over one persistent connection per engine (opened on first use).
normalize() turns rows into plain comparable Python values.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg
from neo4j import GraphDatabase
from neo4j.time import Date as NeoDate, DateTime as NeoDateTime

import config

CAT = ZoneInfo(config.TZ)

# Section 4 review sets: review account, Q7 destination, September day.
SETS = {
    "A": {"account": 998,    "destination": 24755,  "day": 6},
    "B": {"account": 147228, "destination": 186823, "day": 13},
    "C": {"account": 206978, "destination": 6573,   "day": 8},
    "D": {"account": 237998, "destination": 21755,  "day": 6},
    "E": {"account": 144228, "destination": 183823, "day": 13},
    "F": {"account": 203978, "destination": 3573,   "day": 8},
}


def hour_window(day):
    """09:45:00 inclusive to 10:45:00 exclusive CAT on 2026-09-<day>, as epoch seconds."""
    start = datetime(2026, 9, day, 9, 45, 0, tzinfo=CAT)
    end = datetime(2026, 9, day, 10, 45, 0, tzinfo=CAT)
    return int(start.timestamp()), int(end.timestamp())


def set_params(name):
    s = SETS[name]
    start, end = hour_window(s["day"])
    return {"account": s["account"], "destination": s["destination"], "start": start, "end": end}


def cat_time(epoch):
    return datetime.fromtimestamp(epoch, CAT).strftime("%Y-%m-%d %H:%M:%S")


_pg = None
_neo_driver = None
_neo_session = None


def pg():
    global _pg
    if _pg is None or _pg.closed:
        _pg = psycopg.connect(**config.pg_conninfo(), autocommit=True)
    return _pg


def neo():
    global _neo_driver, _neo_session
    if _neo_session is None:
        s = config.neo4j_settings()
        _neo_driver = GraphDatabase.driver(s["uri"], auth=s["auth"])
        _neo_session = _neo_driver.session(database=s["database"])
    return _neo_session


def run_pg(query, params=None):
    with pg().cursor() as cur:
        cur.execute(query, params or {})
        return cur.fetchall() if cur.description is not None else []


def run_neo(query, params=None):
    return [tuple(r.values()) for r in neo().run(query, params or {})]


def close():
    global _pg, _neo_driver, _neo_session
    if _pg is not None:
        _pg.close()
        _pg = None
    if _neo_session is not None:
        _neo_session.close()
        _neo_driver.close()
        _neo_session = _neo_driver = None


def _value(v):
    if isinstance(v, (NeoDate, NeoDateTime)):
        v = v.to_native()
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return tuple(_value(x) for x in v)
    if hasattr(v, "__int__") and not isinstance(v, (str, bool, float)):
        return int(v)  # Decimal sums from PostgreSQL, numpy ints
    return v


def normalize(rows, sort=True):
    out = [tuple(_value(v) for v in row) for row in rows]
    return sorted(out) if sort else out
