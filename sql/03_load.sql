-- Section 2.2 step 1: bulk-load the captured CSVs.
-- Order: customers, devices, then accounts, account_devices, transfers.
--   psql -U postgres -d mobile_money -f sql/03_load.sql
\set ON_ERROR_STOP on
\timing on

SELECT extract(epoch FROM clock_timestamp()) AS load_t0 \gset

\copy customers       FROM 'D:/AUCA/ABDA_Project2/data/csv/customers.csv'       CSV HEADER
\copy devices         FROM 'D:/AUCA/ABDA_Project2/data/csv/devices.csv'         CSV HEADER
\copy accounts        FROM 'D:/AUCA/ABDA_Project2/data/csv/accounts.csv'        CSV HEADER
\copy account_devices FROM 'D:/AUCA/ABDA_Project2/data/csv/account_devices.csv' CSV HEADER
\copy transfers       FROM 'D:/AUCA/ABDA_Project2/data/csv/transfers.csv'       CSV HEADER

\timing off
SELECT round((extract(epoch FROM clock_timestamp()) - :load_t0)::numeric, 1) AS total_load_seconds;
