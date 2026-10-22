import unittest

from investigation_engine import generate_investigations


class InvestigationEngineTests(unittest.TestCase):
    def test_flagged_complete_row_reaches_review_required(self):
        cases = generate_investigations([{
            "flag": "TRUE", "cust-id": "CUST0001", "meter-num": "MTR001",
            "current-meter-read-timestamp": "2026-01-01 08:00:00", "usageNumber": 20,
            "baselineMean": 4, "threshold": 10, "reason": "threshold exceeded",
            "budget indicator": "Y",
        }], [], "run-1")

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].state, "review_required")
        self.assertEqual(cases[0].severity, "critical")
        self.assertEqual(cases[0].state_path[-1], "review_required")

    def test_missing_required_input_reaches_data_unavailable(self):
        cases = generate_investigations([{
            "flag": "TRUE", "cust-id": "CUST0001", "meter-num": "MTR001",
            "current-meter-read-timestamp": "2026-01-01 08:00:00", "usageNumber": 20,
        }], [], "run-1")

        self.assertEqual(cases[0].state, "data_unavailable")
        self.assertIn("threshold", cases[0].evidence[0].values["missing_fields"])

    def test_unflagged_row_does_not_create_case(self):
        self.assertEqual(generate_investigations([{"flag": "FALSE"}], [], "run-1"), [])

    def test_auto_ticket_evidence_assigns_billing_for_estimated_read(self):
        cases = generate_investigations([{
            "flag": "TRUE", "cust-id": "CUST0002", "meter-num": "MTR0002",
            "current-meter-read-timestamp": "2026-10-21 16:00:00", "usageNumber": 50,
            "baselineMean": 4, "threshold": 10, "readType": "estimated",
            "meter-status": "active", "weather": {
                "available": True, "provider": "test", "observedAt": "2026-10-21 16:00:00",
                "temperatureC": 35, "apparentTemperatureC": 37,
                "rangeStart": "2026-09-30 20:00:00", "rangeEnd": "2026-10-21 16:00:00",
                "sampleCount": 500, "minApparentTemperatureC": 5, "maxApparentTemperatureC": 39,
            },
            "meterEvents": [], "billingContext": {"correctionRequired": False},
        }], [], "input-feed-sub-1")

        case = cases[0]
        outcomes = {item.check_code: item.outcome for item in case.evidence}
        self.assertEqual(case.assigned_team, "Billing Resolution")
        self.assertIn("estimated-reading", case.possible_cause)
        self.assertEqual(outcomes["weather"], "finding")
        self.assertEqual(outcomes["billing_issues"], "finding")
        self.assertEqual(outcomes["meter_anomalies"], "finding")
        self.assertNotIn("customer_changes", outcomes)
        self.assertIn("Evidence requiring investigation", case.detailed_report)
        self.assertIn("Weather", case.detailed_report)
        self.assertIn("Evidence reviewed and available", case.detailed_report)
        weather = next(item for item in case.evidence if item.check_code == "weather")
        self.assertIn("2026-09-30 20:00:00", weather.summary)
        self.assertEqual(weather.values["sample_count"], 500)


if __name__ == "__main__":
    unittest.main()
