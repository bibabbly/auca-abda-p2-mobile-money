# Advanced Big Data Analytics — Project 2: Mobile Money Investigations

PostgreSQL vs Neo4j on the September 2026 mobile-money dataset.
Commands are in execution order. Run them from `D:\AUCA\ABDA_Project2` in PowerShell.

`mobile_money_generator.py` is used unchanged.
SHA-256: `2ea0e59d2b7b987d84a3d151bd9d1ad7b3052bfbc25abf1466c8e94467e9455a`

## 0. Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy "psycopg[binary]" neo4j pandas matplotlib psutil
Copy-Item .env.example .env   # then put your own passwords in .env
```

## 1.1 Workspace

### PostgreSQL 18 (database `mobile_money`, time zone Africa/Kigali)

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f sql\00_create_database.sql
```

### Neo4j Community (dedicated instance, default `neo4j` database)

1. Download the Neo4j **Community** Windows ZIP (used: 2026.10.1) from the Neo4j Deployment Center
   and extract it to `D:\AUCA\neo4j-community`.
2. Append to `D:\AUCA\neo4j-community\conf\neo4j.conf` (original kept as `neo4j.conf.original`):
   ```
   server.memory.heap.initial_size=8g
   server.memory.heap.max_size=8g
   server.memory.pagecache.size=10g
   dbms.memory.transaction.total.max=6g
   dbms.usage_report.enabled=false
   ```
3. In every new PowerShell window, load Java 21 (bundled with Neo4j Desktop) and Neo4j paths:
   ```powershell
   . .\neo4j_env.ps1
   ```
4. Set the initial password, then start it in the console:
   ```powershell
   neo4j-admin dbms set-initial-password <your-neo4j-password>
   neo4j console
   ```

### Record versions, hardware and memory settings

```powershell
.\.venv\Scripts\python.exe env_check.py     # -> results/environment.json
```

## 1.2 Capture

```powershell
.\.venv\Scripts\python.exe capture.py --preview   # -> logs/capture_preview.log
.\.venv\Scripts\python.exe capture.py             # -> data/csv/*.csv, results/capture_audit.json, logs/capture.log
```

## 2 PostgreSQL

Schema diagram and field units: `docs/postgres_schema.md`.

```powershell
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
& $psql -U postgres -d mobile_money -f sql\02_create_tables.sql        # 2.1 tables (NOT NULL columns)
& $psql -U postgres -d mobile_money -f sql\03_load.sql                 # 2.2 \copy, load seconds
& $psql -U postgres -d mobile_money -f sql\04_constraints_indexes.sql  # 2.1/2.2 PK, FK, CHECK, indexes, ANALYZE, setup seconds
& $psql -U postgres -d mobile_money -f sql\05_show_definitions.sql     # 2.1 definitions and constraints
.\.venv\Scripts\python.exe pg_checks.py                                # 2.2 counts, audit, roles, constraints, indexes, sizes
```

## 3 Neo4j

Graph schema and field mapping: `docs/neo4j_graph_schema.md`.

```powershell
.\.venv\Scripts\python.exe prepare_import.py   # 3.2 typed-header copies in import/ + owns.csv
.\import_neo4j.ps1                             # 3.2 full import (Neo4j stopped) -> results/neo4j_import.json
. .\neo4j_env.ps1; neo4j console               # start Neo4j (separate window)
.\.venv\Scripts\python.exe neo4j_setup.py      # 3.2 constraints, range index, sizes -> results/neo4j_setup.json
.\.venv\Scripts\python.exe neo4j_checks.py     # 3.2 counts, roles, owners, unique IDs, audit
.\.venv\Scripts\python.exe prepare_import.py --clean   # 3.2 remove temporary import copies
.\.venv\Scripts\python.exe inspect_account.py 998      # 3.3 same account in SQL and Cypher
```

## 4–5 Questions Q1–Q7

Queries: `queries.py` (SQL `%(name)s`, Cypher `$name`). Shared wrappers `run_pg` / `run_neo`: `db.py`.

```powershell
.\.venv\Scripts\python.exe run_section4.py q1   # also q2, q3  -> results/section4/, charts/q2_daily.png
.\.venv\Scripts\python.exe run_section5.py q4   # also q5, q6, q7 -> results/section5/, charts/q4_depth.png
```

## 6 Correctness and performance

```powershell
# both services running
.\.venv\Scripts\python.exe compare_61.py                       # 6.1 61 cases + CSV cross-checks
# PostgreSQL only (stop Neo4j)
.\.venv\Scripts\python.exe benchmark.py --engine pg            # 6.2 21 cases, plain Q7 SQL
.\.venv\Scripts\python.exe benchmark.py --engine pg --cases q7revised   # 6.3 4 revised Q7 cases
.\.venv\Scripts\python.exe plans.py --engine pg                # EXPLAIN (ANALYZE, BUFFERS)
# Neo4j only (stop PostgreSQL)
.\.venv\Scripts\python.exe benchmark.py --engine neo           # 6.2 21 cases
.\.venv\Scripts\python.exe plans.py --engine neo               # PROFILE
# any time
.\.venv\Scripts\python.exe benchmark.py --summary              # medians, min/max, PG/Neo ratio
# both services running
.\.venv\Scripts\python.exe compare_61.py --q7 bidirectional    # 6.3 recheck all 12 Q7 cases
```

## 7 Concurrent requests

```powershell
.\.venv\Scripts\python.exe loadtest.py --engine pg    # PostgreSQL only
.\.venv\Scripts\python.exe loadtest.py --engine neo   # Neo4j only
.\.venv\Scripts\python.exe loadtest.py --summary      # -> results/loadtest/summary.csv, charts/loadtest.png
```
