-- Section 2.1 screenshot: table definitions, constraints and indexes.
--   psql -U postgres -d mobile_money -f sql/05_show_definitions.sql
\d customers
\d accounts
\d devices
\d account_devices
\d transfers

SELECT conrelid::regclass AS table_name, conname AS constraint_name,
       CASE contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY' WHEN 'c' THEN 'CHECK'
                    WHEN 'n' THEN 'NOT NULL' END AS type,
       convalidated AS validated, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid IN ('customers'::regclass, 'accounts'::regclass, 'devices'::regclass,
                   'account_devices'::regclass, 'transfers'::regclass)
ORDER BY 1::text, 3, 2;
