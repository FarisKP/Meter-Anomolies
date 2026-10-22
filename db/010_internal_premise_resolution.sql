-- Internal-source-first premise resolution for weather investigations.
-- Apply after 009. MeterIQ retains a verified weather coordinate and audit
-- metadata only; full service addresses remain in the authorised source.

ALTER TABLE customer_premises
    ADD COLUMN IF NOT EXISTS source_system VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_record_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS location_reference_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS geocode_status VARCHAR(32) NOT NULL DEFAULT 'unconfigured',
    ADD COLUMN IF NOT EXISTS geocode_provider VARCHAR(64),
    ADD COLUMN IF NOT EXISTS geocoded_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_customer_premises_source_record
    ON customer_premises (source_system, source_record_id);
