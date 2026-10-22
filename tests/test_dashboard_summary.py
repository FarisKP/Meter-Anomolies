import unittest

from dashboard import build_data
from meter_models import MeterRead


class CandidateRepository:
    def __init__(self):
        self.history = [MeterRead(
            customer_id="CUST0002", meter_number="MTR0002", meter_status="active",
            current_read="100", read_at="2026-09-30 16:00:00", previous_read="98",
            usage_index="2", budget_indicator="N",
        )]
        self.candidate = MeterRead(
            customer_id="CUST0002", meter_number="MTR0002", meter_status="active",
            current_read="25764.6", read_at="2026-10-21 16:00:00", previous_read="20764.6",
            usage_index="5000", budget_indicator="N",
        )

    def history_reads(self):
        return self.history

    def current_reads(self):
        return []

    def analysis_results(self):
        return []

    def customer_meter_pairs(self):
        return [("CUST0002", "MTR0002")]

    def read_exists(self, key):
        return False

    def historical_reads_for_slot(self, read, lookback_days):
        return self.history

    def input_feed_spike_candidates(self):
        return [self.candidate]


class DashboardSummaryTests(unittest.TestCase):
    def test_screened_summary_includes_protected_input_candidate(self):
        data = build_data(CandidateRepository())

        self.assertEqual(data["currentCount"], 0)
        self.assertEqual(data["screenedReadCount"], 1)
        self.assertEqual(data["screenedLatest"], "2026-10-21 16:00:00")
        self.assertEqual(data["flaggedCount"], 1)
        self.assertEqual(data["budgetFlaggedCount"], 0)
        self.assertEqual(data["inputFeedSpikeCandidateCount"], 1)


if __name__ == "__main__":
    unittest.main()
