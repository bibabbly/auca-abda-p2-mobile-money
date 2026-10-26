-- Section 2.1: the five tables, columns only (NOT NULL everywhere).
-- Keys, foreign keys, checks and indexes are added after the bulk load
-- (sql/04_constraints_indexes.sql) so load and setup times are measured separately.
--   psql -U postgres -d mobile_money -f sql/02_create_tables.sql
\set ON_ERROR_STOP on

DROP TABLE IF EXISTS transfers, account_devices, accounts, devices, customers CASCADE;

CREATE TABLE customers (
    customer_id  INTEGER NOT NULL,
    region       TEXT    NOT NULL
);

CREATE TABLE accounts (
    account_id   INTEGER NOT NULL,
    customer_id  INTEGER NOT NULL,
    role         TEXT    NOT NULL
);

CREATE TABLE devices (
    device_id    INTEGER NOT NULL,
    access_type  TEXT    NOT NULL
);

CREATE TABLE account_devices (
    account_id   INTEGER  NOT NULL,
    device_id    INTEGER  NOT NULL,
    first_day    SMALLINT NOT NULL,
    last_day     SMALLINT NOT NULL,
    observations INTEGER  NOT NULL
);

CREATE TABLE transfers (
    transfer_id  BIGINT  NOT NULL,
    sender_id    INTEGER NOT NULL,
    receiver_id  INTEGER NOT NULL,
    occurred_at  BIGINT  NOT NULL,
    amount_rwf   INTEGER NOT NULL
);

\dt
