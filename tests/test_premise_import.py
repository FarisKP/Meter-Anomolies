import tempfile
import unittest
from pathlib import Path

from import_premise_addresses import load_source_rows, resolve_rows


class PremiseImportTests(unittest.TestCase):
    def test_load_rejects_missing_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text("customer_id,premise_id\nCUST0001,PREM1\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "missing required columns"):
                load_source_rows(path)

    def test_unknown_customer_does_not_reach_geocoding(self):
        outcomes = resolve_rows([{
            "customer_id": "UNKNOWN", "premise_id": "PREM1", "address_line1": "Example",
            "city": "Cleveland", "state": "OH", "postal_code": "44114", "country_code": "US",
            "source_updated_at": "2026-10-22T00:00:00Z",
        }], {"CUST0001"})
        self.assertEqual(outcomes[0].status, "failed")
        self.assertIn("not present", outcomes[0].message)


if __name__ == "__main__":
    unittest.main()
