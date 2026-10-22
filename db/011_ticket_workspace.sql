-- Editable associate workspace for deterministic investigation tickets.
-- Apply after migrations 001 through 010.
-- The generated report remains system evidence; associate notes and comments
-- are retained separately so the original automated conclusion is auditable.

ALTER TABLE investigation_tickets
    ADD COLUMN IF NOT EXISTS detailed_report TEXT,
    ADD COLUMN IF NOT EXISTS associate_notes VARCHAR(4000),
    ADD COLUMN IF NOT EXISTS last_edited_by VARCHAR(128);

CREATE TABLE IF NOT EXISTS investigation_ticket_comments (
    comment_id VARCHAR(64) NOT NULL,
    ticket_id VARCHAR(64) NOT NULL,
    author VARCHAR(128) NOT NULL,
    comment_text VARCHAR(2000) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (comment_id),
    FOREIGN KEY (ticket_id) REFERENCES investigation_tickets (ticket_id)
);

CREATE INDEX IF NOT EXISTS idx_investigation_ticket_comments_ticket_time
    ON investigation_ticket_comments (ticket_id, created_at ASC);
