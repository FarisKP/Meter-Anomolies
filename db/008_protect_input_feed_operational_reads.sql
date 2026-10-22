-- Guardrail for the four-hour form intake workflow.
--
-- Apply after migrations 001 through 005. This does not delete or alter
-- existing readings. It blocks the retired current-csv-initial demo batch and
-- any attempted write to meter_reads when its batch was created by the
-- input-feed form. Candidate readings belong only in meter_reads_temp;
-- non-candidates belong only in input_feed_submissions.

CREATE OR REPLACE FUNCTION reject_input_feed_operational_read()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.batch_id = 'current-csv-initial'
       OR NEW.batch_id LIKE 'input-feed-%'
       OR EXISTS (
            SELECT 1
            FROM ingest_batches
            WHERE batch_id = NEW.batch_id
              AND source_name = 'operator-four-hour-form'
       ) THEN
        RAISE EXCEPTION
            'Input-feed readings cannot be written to meter_reads; use meter_reads_temp for spike candidates.'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_reject_input_feed_operational_read ON meter_reads;

CREATE TRIGGER trg_reject_input_feed_operational_read
BEFORE INSERT OR UPDATE OF batch_id ON meter_reads
FOR EACH ROW
EXECUTE FUNCTION reject_input_feed_operational_read();
