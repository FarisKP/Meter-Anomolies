-- Portable logical schema for PostgreSQL/Supabase and Db2.
-- Apply this through the migration mechanism of the selected database.
-- All timestamps are UTC by application convention.

CREATE TABLE ingest_batches (
    batch_id VARCHAR(64) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    record_count INTEGER NOT NULL,
    PRIMARY KEY (batch_id)
);

CREATE TABLE customers (
    customer_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (customer_id)
);

CREATE TABLE meters (
    meter_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (meter_id),
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
);

CREATE TABLE meter_reads (
    read_id VARCHAR(64) NOT NULL,
    meter_id VARCHAR(64) NOT NULL,
    read_at TIMESTAMP NOT NULL,
    meter_status VARCHAR(32) NOT NULL,
    current_read DECIMAL(18, 4) NOT NULL,
    previous_read DECIMAL(18, 4) NOT NULL,
    usage_index DECIMAL(18, 4) NOT NULL,
    budget_indicator CHAR(1),
    slot_hour SMALLINT NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (read_id),
    UNIQUE (meter_id, read_at),
    FOREIGN KEY (meter_id) REFERENCES meters (meter_id),
    FOREIGN KEY (batch_id) REFERENCES ingest_batches (batch_id)
);

CREATE INDEX idx_meter_reads_meter_slot_time
    ON meter_reads (meter_id, slot_hour, read_at);

CREATE INDEX idx_meter_reads_batch
    ON meter_reads (batch_id);

CREATE TABLE analysis_runs (
    run_id VARCHAR(64) NOT NULL,
    executed_at TIMESTAMP NOT NULL,
    lookback_days INTEGER NOT NULL,
    sigma DECIMAL(9, 4) NOT NULL,
    min_history INTEGER NOT NULL,
    algorithm_version VARCHAR(64) NOT NULL,
    PRIMARY KEY (run_id)
);

CREATE TABLE spike_results (
    run_id VARCHAR(64) NOT NULL,
    read_id VARCHAR(64) NOT NULL,
    baseline_count INTEGER NOT NULL,
    baseline_mean DECIMAL(18, 4),
    baseline_stddev DECIMAL(18, 4),
    spike_threshold DECIMAL(18, 4),
    spike_flag VARCHAR(32) NOT NULL,
    flag_reason VARCHAR(500) NOT NULL,
    PRIMARY KEY (run_id, read_id),
    FOREIGN KEY (run_id) REFERENCES analysis_runs (run_id),
    FOREIGN KEY (read_id) REFERENCES meter_reads (read_id)
);

CREATE INDEX idx_spike_results_read
    ON spike_results (read_id);
