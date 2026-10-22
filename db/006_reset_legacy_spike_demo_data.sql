-- ONE-TIME DESTRUCTIVE RESET FOR THE LEGACY SIMULATED CURRENT FEED.
--
-- Prerequisites: apply migrations 001 through 005 first.
-- Preserved: customers, meters, and all history-csv-initial meter reads.
-- Removed: legacy current-feed reads, their analysis results, investigation
-- artifacts, input-feed audit entries, and the spike-review queue.

BEGIN;

-- Investigation artifacts are derived from spike screening and must not
-- survive a clean reset of the legacy demonstration data.
DELETE FROM case_actions;
DELETE FROM investigation_evidence;
DELETE FROM investigation_cases;
DELETE FROM data_source_runs
WHERE source_run_id = 'csv-analysis-initial';

-- Remove the legacy analysis output before its parent run and input reads.
DELETE FROM spike_results
WHERE run_id = 'csv-analysis-initial';

DELETE FROM analysis_runs
WHERE run_id = 'csv-analysis-initial';

-- Remove the queue and audit data so fresh input-feed records start cleanly.
DELETE FROM meter_reads_temp;
DELETE FROM input_feed_submissions;

-- Remove only the imported simulated current batch; preserve historical data.
DELETE FROM meter_reads
WHERE batch_id = 'current-csv-initial';

DELETE FROM ingest_batches
WHERE batch_id = 'current-csv-initial';

COMMIT;

-- Expected after this script:
-- * meter_reads where batch_id = 'history-csv-initial' remains unchanged.
-- * meter_reads where batch_id = 'current-csv-initial' has zero rows.
-- * spike_results, investigation_cases, and meter_reads_temp have zero rows.
