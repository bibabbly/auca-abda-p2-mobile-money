-- Section 1.1: run once as the postgres superuser from psql:
--   psql -U postgres -f sql/00_create_database.sql
CREATE DATABASE mobile_money;
ALTER DATABASE mobile_money SET timezone TO 'Africa/Kigali';

\connect mobile_money
SHOW timezone;
SELECT version();
