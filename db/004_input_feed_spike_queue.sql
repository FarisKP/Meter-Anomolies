-- Input-feed spike-review queue. Apply after 001, 002, and 003.
-- This table holds only deterministic input-feed spike candidates for
-- associate review. The input-feed workflow does not write to meter_reads.

CREATE TABLE IF NOT EXISTS meter_reads_temp (
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
    read_type VARCHAR(16) NOT NULL DEFAULT 'actual',
    spike_indicator BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (read_id),
    UNIQUE (meter_id, read_at),
    FOREIGN KEY (meter_id) REFERENCES meters (meter_id),
    FOREIGN KEY (batch_id) REFERENCES ingest_batches (batch_id)
);

CREATE INDEX IF NOT EXISTS idx_meter_reads_temp_spike_time
    ON meter_reads_temp (spike_indicator, read_at DESC);
