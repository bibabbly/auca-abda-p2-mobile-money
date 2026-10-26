"""Shared settings: reads .env from the project folder (no extra package needed)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_DIR = ROOT / "data" / "csv"
LOG_DIR = ROOT / "logs"
RESULTS_DIR = ROOT / "results"
TZ = "Africa/Kigali"

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def pg_conninfo():
    return dict(host=os.environ.get("PGHOST", "localhost"),
                port=int(os.environ.get("PGPORT", 5432)),
                dbname=os.environ.get("PGDATABASE", "mobile_money"),
                user=os.environ.get("PGUSER", "postgres"),
                password=os.environ.get("PGPASSWORD", ""))


def neo4j_settings():
    return dict(uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "")),
                database=os.environ.get("NEO4J_DATABASE", "neo4j"))
