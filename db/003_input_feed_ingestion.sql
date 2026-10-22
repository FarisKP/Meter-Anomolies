-- Four-hour operator feed intake. Apply after 001 and 002.
-- This migration is for Supabase/PostgreSQL.

ALTER TABLE meter_reads
    ADD COLUMN IF NOT EXISTS read_type VARCHAR(16) NOT NULL DEFAULT 'actual';

CREATE TABLE IF NOT EXISTS input_feed_submissions (
    submission_id VARCHAR(64) NOT NULL,
    read_id VARCHAR(64) NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    meter_id VARCHAR(64) NOT NULL,
    read_at TIMESTAMP NOT NULL,
    read_type VARCHAR(16) NOT NULL,
    submitted_by VARCHAR(128) NOT NULL,
    source_reference VARCHAR(255),
    validation_status VARCHAR(32) NOT NULL,
    validation_json TEXT NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    PRIMARY KEY (submission_id),
    FOREIGN KEY (read_id) REFERENCES meter_reads (read_id),
    FOREIGN KEY (batch_id) REFERENCES ingest_batches (batch_id),
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    FOREIGN KEY (meter_id) REFERENCES meters (meter_id)
);

CREATE INDEX IF NOT EXISTS idx_input_feed_submissions_meter_time
    ON input_feed_submissions (meter_id, read_at DESC);
