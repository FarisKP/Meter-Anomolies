-- Automated, deterministic investigation and ticketing foundation.
-- Apply after migrations 001 through 008.
-- This migration creates only operational evidence stores; it does not seed
-- customer locations, weather, meter events, billing context, or customer
-- changes. Those sources must be supplied by approved systems.

ALTER TABLE investigation_cases
    ADD COLUMN IF NOT EXISTS assigned_team VARCHAR(64),
    ADD COLUMN IF NOT EXISTS possible_cause VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS report_summary VARCHAR(2000);

CREATE TABLE IF NOT EXISTS customer_premises (
    premise_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    latitude DECIMAL(9, 6),
    longitude DECIMAL(9, 6),
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    active_from TIMESTAMP,
    active_to TIMESTAMP,
    source_reference VARCHAR(255),
    PRIMARY KEY (premise_id),
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
);

CREATE INDEX IF NOT EXISTS idx_customer_premises_customer_active
    ON customer_premises (customer_id, active_from, active_to);

CREATE TABLE IF NOT EXISTS meter_events (
    event_id VARCHAR(64) NOT NULL,
    meter_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    event_at TIMESTAMP NOT NULL,
    meter_status VARCHAR(32),
    work_order_reference VARCHAR(255),
    PRIMARY KEY (event_id),
    FOREIGN KEY (meter_id) REFERENCES meters (meter_id)
);

CREATE INDEX IF NOT EXISTS idx_meter_events_meter_time
    ON meter_events (meter_id, event_at DESC);

CREATE TABLE IF NOT EXISTS billing_read_context (
    meter_id VARCHAR(64) NOT NULL,
    read_at TIMESTAMP NOT NULL,
    read_disposition VARCHAR(16) NOT NULL,
    billing_state VARCHAR(32),
    estimated_reason VARCHAR(255),
    correction_required BOOLEAN NOT NULL DEFAULT FALSE,
    source_reference VARCHAR(255),
    PRIMARY KEY (meter_id, read_at),
    FOREIGN KEY (meter_id) REFERENCES meters (meter_id)
);

CREATE TABLE IF NOT EXISTS customer_change_events (
    event_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    premise_id VARCHAR(64),
    change_type VARCHAR(64) NOT NULL,
    effective_at TIMESTAMP NOT NULL,
    source_reference VARCHAR(255),
    PRIMARY KEY (event_id),
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    FOREIGN KEY (premise_id) REFERENCES customer_premises (premise_id)
);

CREATE INDEX IF NOT EXISTS idx_customer_change_events_customer_time
    ON customer_change_events (customer_id, effective_at DESC);

CREATE TABLE IF NOT EXISTS weather_snapshots (
    premise_id VARCHAR(64) NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    provider VARCHAR(64) NOT NULL,
    temperature_c DECIMAL(6, 2),
    apparent_temperature_c DECIMAL(6, 2),
    relative_humidity_percent DECIMAL(5, 2),
    precipitation_mm DECIMAL(8, 2),
    weather_code INTEGER,
    retrieved_at TIMESTAMP NOT NULL,
    PRIMARY KEY (premise_id, observed_at),
    FOREIGN KEY (premise_id) REFERENCES customer_premises (premise_id)
);

CREATE TABLE IF NOT EXISTS investigation_tickets (
    ticket_id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    assigned_team VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary VARCHAR(2000) NOT NULL,
    possible_cause VARCHAR(1000) NOT NULL,
    recommended_solution VARCHAR(2000) NOT NULL,
    generated_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (ticket_id),
    UNIQUE (case_id),
    FOREIGN KEY (case_id) REFERENCES investigation_cases (case_id)
);

CREATE INDEX IF NOT EXISTS idx_investigation_tickets_status_team
    ON investigation_tickets (status, assigned_team, updated_at DESC);
