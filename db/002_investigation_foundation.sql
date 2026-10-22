-- Deterministic usage-spike investigation foundation.
-- Apply after 001_initial_schema.sql in the Supabase SQL Editor.
-- All timestamps are UTC by application convention.

CREATE TABLE data_source_runs (
    source_run_id VARCHAR(64) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    record_count INTEGER NOT NULL,
    data_contract_version VARCHAR(32) NOT NULL,
    engine_version VARCHAR(64) NOT NULL,
    PRIMARY KEY (source_run_id)
);

CREATE TABLE investigation_cases (
    case_id VARCHAR(64) NOT NULL,
    case_key VARCHAR(255) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    meter_id VARCHAR(64) NOT NULL,
    trigger_read_at TIMESTAMP NOT NULL,
    trigger_usage DECIMAL(18, 4),
    baseline_mean DECIMAL(18, 4),
    spike_threshold DECIMAL(18, 4),
    severity VARCHAR(16) NOT NULL,
    state VARCHAR(32) NOT NULL,
    recommended_action VARCHAR(500) NOT NULL,
    source_run_id VARCHAR(64) NOT NULL,
    data_contract_version VARCHAR(32) NOT NULL,
    engine_version VARCHAR(64) NOT NULL,
    opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (case_id),
    UNIQUE (case_key),
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    FOREIGN KEY (meter_id) REFERENCES meters (meter_id),
    FOREIGN KEY (source_run_id) REFERENCES data_source_runs (source_run_id)
);

CREATE INDEX idx_investigation_cases_state_severity
    ON investigation_cases (state, severity);

CREATE INDEX idx_investigation_cases_customer_opened
    ON investigation_cases (customer_id, opened_at);

CREATE TABLE investigation_evidence (
    case_id VARCHAR(64) NOT NULL,
    check_code VARCHAR(64) NOT NULL,
    outcome VARCHAR(32) NOT NULL,
    summary VARCHAR(500) NOT NULL,
    evidence_json TEXT NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (case_id, check_code),
    FOREIGN KEY (case_id) REFERENCES investigation_cases (case_id)
);

CREATE TABLE case_actions (
    action_id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    actor_id VARCHAR(128),
    action_comment VARCHAR(1000),
    action_at TIMESTAMP NOT NULL,
    PRIMARY KEY (action_id),
    FOREIGN KEY (case_id) REFERENCES investigation_cases (case_id)
);

CREATE INDEX idx_case_actions_case_time
    ON case_actions (case_id, action_at);
