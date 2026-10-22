import unittest

from feed_ingestion import FeedSubmission, FeedSubmissionError, FeedStorageError, SupabaseFeedStore, validate_submission
from meter_models import MeterRead
from spike_screening import SpikeScreening, screen_read


class FakeRepository:
    def __init__(self, reads):
        self.reads = reads

    def history_reads(self):
        return self.reads

    def current_reads(self):
        return []

    def analysis_results(self):
        return []

    def customer_meter_pairs(self):
        return sorted({(read.customer_id, read.meter_number) for read in self.reads})

    def read_exists(self, key):
        return any(read.key == key for read in self.reads)

    def historical_reads_for_slot(self, read, lookback_days):
        return self.reads

    def input_feed_spike_candidates(self):
        return []


def payload(**overrides):
    value = {
        "customerId": "CUST0001",
        "meterId": "MTR0001",
        "readAt": "2026-04-01T08:00",
        "meterStatus": "active",
        "currentRead": "120.50",
        "previousRead": "118.25",
        "usageIndex": "2.25",
        "readType": "actual",
        "budgetIndicator": "N",
        "submittedBy": "TEST-ASSOCIATE",
        "sourceReference": "test",
    }
    value.update(overrides)
    return value


class RecordingStore(SupabaseFeedStore):
    def __init__(self):
        self.calls = []

    def _ensure_batch(self, batch_id, now):
        return None

    def _upsert(self, table, rows, conflict_columns):
        self.calls.append((table, rows, conflict_columns))


class FeedIngestionTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeRepository([MeterRead(
            customer_id="CUST0001", meter_number="MTR0001", meter_status="active",
            current_read="10", read_at="2026-03-31 20:00:00", previous_read="8",
            usage_index="2", budget_indicator="N",
        )])

    def test_valid_aligned_submission_is_accepted_by_validator(self):
        submission = FeedSubmission.from_payload(payload())
        validate_submission(submission, self.repository)
        self.assertEqual(submission.read_at, "2026-04-01 08:00:00")

    def test_non_four_hour_slot_is_rejected(self):
        with self.assertRaisesRegex(FeedSubmissionError, "four-hour UTC slot"):
            FeedSubmission.from_payload(payload(readAt="2026-04-01T09:00"))

    def test_usage_index_must_equal_current_minus_previous_read(self):
        with self.assertRaisesRegex(FeedSubmissionError, "usageIndex must equal"):
            FeedSubmission.from_payload(payload(usageIndex="3.00"))

    def test_current_read_cannot_be_lower_than_previous_read(self):
        with self.assertRaisesRegex(FeedSubmissionError, "currentRead cannot be lower"):
            FeedSubmission.from_payload(payload(currentRead="118.00", usageIndex="0"))

    def test_unknown_customer_meter_pair_is_rejected(self):
        submission = FeedSubmission.from_payload(payload(meterId="MTR9999"))
        with self.assertRaisesRegex(FeedSubmissionError, "known active source mapping"):
            validate_submission(submission, self.repository)

    def test_duplicate_read_is_rejected(self):
        submission = FeedSubmission.from_payload(payload(readAt="2026-03-31T20:00"))
        with self.assertRaisesRegex(FeedSubmissionError, "already exists"):
            validate_submission(submission, self.repository)

    def test_screening_queues_a_read_above_the_same_slot_threshold(self):
        target = MeterRead(
            customer_id="CUST0001", meter_number="MTR0001", meter_status="active",
            current_read="200", read_at="2026-04-01 08:00:00", previous_read="150",
            usage_index="50", budget_indicator="N",
        )
        baseline = [MeterRead(
            customer_id="CUST0001", meter_number="MTR0001", meter_status="active",
            current_read="10", read_at=f"2026-03-{day:02d} 08:00:00", previous_read="8",
            usage_index="2", budget_indicator="N",
        ) for day in range(1, 31)]

        screening = screen_read(target, baseline)

        self.assertTrue(screening.spike_indicator)
        self.assertEqual(screening.status, "TRUE")
        self.assertEqual(screening.baseline_count, 30)

    def test_screening_does_not_queue_a_within_range_read(self):
        target = MeterRead(
            customer_id="CUST0001", meter_number="MTR0001", meter_status="active",
            current_read="10", read_at="2026-04-01 08:00:00", previous_read="8",
            usage_index="2", budget_indicator="N",
        )
        baseline = [MeterRead(
            customer_id="CUST0001", meter_number="MTR0001", meter_status="active",
            current_read="10", read_at=f"2026-03-{day:02d} 08:00:00", previous_read="8",
            usage_index="2", budget_indicator="N",
        ) for day in range(1, 31)]

        screening = screen_read(target, baseline)

        self.assertFalse(screening.spike_indicator)
        self.assertEqual(screening.status, "FALSE")

    def test_non_candidate_is_audited_without_a_meter_read_insert(self):
        store = RecordingStore()
        submission = FeedSubmission.from_payload(payload())
        within_range = SpikeScreening(False, "FALSE", 30, 2.0, 0.1, 2.3, "Within threshold")

        store.save(submission, "current-csv-initial", within_range)

        self.assertEqual([table for table, _, _ in store.calls], ["input_feed_submissions"])
        self.assertIsNone(store.calls[0][1][0]["read_id"])

    def test_candidate_enters_only_the_temp_queue(self):
        store = RecordingStore()
        submission = FeedSubmission.from_payload(payload())
        candidate = SpikeScreening(True, "TRUE", 30, 2.0, 0.1, 2.3, "Above threshold")

        store.save(submission, "current-csv-initial", candidate)

        self.assertEqual(
            [table for table, _, _ in store.calls],
            ["meter_reads_temp", "input_feed_submissions"],
        )
        self.assertTrue(store.calls[0][1][0]["spike_indicator"])

    def test_operational_meter_read_writes_are_hard_blocked(self):
        store = SupabaseFeedStore("https://example.supabase.co", "not-a-real-key")

        with self.assertRaisesRegex(FeedStorageError, "never writes meter_reads"):
            store._upsert("meter_reads", [], "read_id")


if __name__ == "__main__":
    unittest.main()
