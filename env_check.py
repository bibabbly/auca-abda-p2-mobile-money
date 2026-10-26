"""Section 1.1: record machine, software, driver and database memory settings,
and prove both database connections work. Output is printed and saved to
results/environment.json for the report.

Usage:  .venv\\Scripts\\python.exe env_check.py
"""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib
import neo4j
import numpy
import pandas
import psutil
import psycopg

import config

PG_SETTINGS = ("TimeZone", "shared_buffers", "work_mem", "maintenance_work_mem",
               "effective_cache_size", "max_worker_processes",
               "max_parallel_workers_per_gather", "max_wal_size", "data_directory")


def cpu_name():
    if platform.system() == "Windows":
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Processor).Name"],
                             capture_output=True, text=True).stdout.strip()
        if out:
            return out
    return platform.processor()


def machine_info():
    return {
        "checked_at_cat": datetime.now(ZoneInfo(config.TZ)).isoformat(timespec="seconds"),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": cpu_name(),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "python": sys.version.split()[0],
        "drivers": {"psycopg": psycopg.__version__, "libpq": psycopg.pq.version(),
                    "neo4j": neo4j.__version__, "numpy": numpy.__version__,
                    "pandas": pandas.__version__, "matplotlib": matplotlib.__version__},
        "generator_sha256": hashlib.sha256(
            (config.ROOT / "mobile_money_generator.py").read_bytes()).hexdigest(),
    }


def postgres_info():
    with psycopg.connect(**config.pg_conninfo()) as conn:
        version = conn.execute("SELECT version()").fetchone()[0]
        settings = {name: conn.execute(f"SHOW {name}").fetchone()[0] for name in PG_SETTINGS}
        db = conn.execute("SELECT current_database(), current_user, now()").fetchone()
    return {"connected": True, "version": version, "database": db[0], "user": db[1],
            "server_now": db[2].isoformat(), "settings": settings}


def neo4j_info():
    s = config.neo4j_settings()
    with neo4j.GraphDatabase.driver(s["uri"], auth=s["auth"]) as driver:
        driver.verify_connectivity()
        with driver.session(database=s["database"]) as session:
            comp = session.run("CALL dbms.components() YIELD name, versions, edition "
                               "WHERE name = 'Neo4j Kernel' "
                               "RETURN name, versions[0] AS version, edition").single()
            memory = {r["name"]: r["value"] for r in session.run(
                "SHOW SETTINGS YIELD name, value "
                "WHERE name IN ['server.memory.heap.initial_size', 'server.memory.heap.max_size', "
                "'server.memory.pagecache.size', 'dbms.memory.transaction.total.max'] "
                "RETURN name, value ORDER BY name")}
            db = session.run("SHOW DATABASES YIELD name, currentStatus WHERE name = $db "
                             "RETURN name, currentStatus", db=s["database"]).single()
    return {"connected": True, "product": comp["name"], "version": comp["version"],
            "edition": comp["edition"], "database": db["name"], "status": db["currentStatus"],
            "memory_settings": memory}


def main():
    report = {"machine": machine_info()}
    for name, probe in (("postgresql", postgres_info), ("neo4j", neo4j_info)):
        try:
            report[name] = probe()
        except Exception as exc:  # show the failure instead of hiding it
            report[name] = {"connected": False, "error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(report, indent=2))
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "environment.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    ok = report["postgresql"]["connected"] and report["neo4j"]["connected"]
    print("\nPostgreSQL:", "CONNECTED" if report["postgresql"]["connected"] else "FAILED",
          "| Neo4j:", "CONNECTED" if report["neo4j"]["connected"] else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
