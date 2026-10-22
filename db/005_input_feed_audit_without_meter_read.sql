-- Keep an audit record for every screened form submission, even when the
-- reading is not eligible for the operational meter_reads feed.
-- Apply after migrations 001 through 004.

ALTER TABLE input_feed_submissions
    ALTER COLUMN read_id DROP NOT NULL;

ALTER TABLE input_feed_submissions
    DROP CONSTRAINT IF EXISTS input_feed_submissions_read_id_fkey;
