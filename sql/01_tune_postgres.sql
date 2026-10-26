-- Section 1.1 fixed resource settings for PostgreSQL (34 GB RAM laptop).
-- Run as postgres, then restart the postgresql-x64-18 service:
--   psql -U postgres -d mobile_money -f sql/01_tune_postgres.sql
-- Neo4j gets 8 GB heap + 10 GB page cache; only one service runs during timing.
ALTER SYSTEM SET shared_buffers = '8GB';
ALTER SYSTEM SET effective_cache_size = '18GB';
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET maintenance_work_mem = '2GB';
ALTER SYSTEM SET max_wal_size = '8GB';
ALTER SYSTEM SET timezone = 'Africa/Kigali';
