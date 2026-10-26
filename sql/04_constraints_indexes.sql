-- Section 2.1/2.2: keys, foreign keys, checks, indexes and statistics,
-- timed separately from the load.
--   psql -U postgres -d mobile_money -f sql/04_constraints_indexes.sql
\set ON_ERROR_STOP on
\timing on

SELECT extract(epoch FROM clock_timestamp()) AS setup_t0 \gset

-- Primary keys: each entity/event ID; (account_id, device_id) for device use.
ALTER TABLE customers       ADD CONSTRAINT customers_pk       PRIMARY KEY (customer_id);
ALTER TABLE accounts        ADD CONSTRAINT accounts_pk        PRIMARY KEY (account_id);
ALTER TABLE devices         ADD CONSTRAINT devices_pk         PRIMARY KEY (device_id);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_pk PRIMARY KEY (account_id, device_id);
ALTER TABLE transfers       ADD CONSTRAINT transfers_pk       PRIMARY KEY (transfer_id);

-- Foreign keys: ownership, device use and both transfer endpoints.
ALTER TABLE accounts        ADD CONSTRAINT accounts_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_account_fk
    FOREIGN KEY (account_id)  REFERENCES accounts (account_id);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_device_fk
    FOREIGN KEY (device_id)   REFERENCES devices (device_id);
ALTER TABLE transfers       ADD CONSTRAINT transfers_sender_fk
    FOREIGN KEY (sender_id)   REFERENCES accounts (account_id);
ALTER TABLE transfers       ADD CONSTRAINT transfers_receiver_fk
    FOREIGN KEY (receiver_id) REFERENCES accounts (account_id);

-- Checks: positive amounts and observations; inclusive day range 0..29.
ALTER TABLE transfers       ADD CONSTRAINT transfers_amount_positive CHECK (amount_rwf > 0);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_observations_positive CHECK (observations > 0);
ALTER TABLE account_devices ADD CONSTRAINT account_devices_day_range
    CHECK (0 <= first_day AND first_day <= last_day AND last_day <= 29);

-- Access-path indexes.
CREATE INDEX accounts_customer_idx        ON accounts (customer_id, account_id);
CREATE INDEX account_devices_device_idx   ON account_devices (device_id, account_id);
CREATE INDEX transfers_sender_time_idx    ON transfers (sender_id, occurred_at)
    INCLUDE (receiver_id, amount_rwf, transfer_id);
CREATE INDEX transfers_receiver_time_idx  ON transfers (receiver_id, occurred_at)
    INCLUDE (sender_id, amount_rwf, transfer_id);
CREATE INDEX transfers_occurred_brin      ON transfers USING brin (occurred_at);

ANALYZE customers, accounts, devices, account_devices, transfers;

\timing off
SELECT round((extract(epoch FROM clock_timestamp()) - :setup_t0)::numeric, 1) AS total_setup_seconds;
