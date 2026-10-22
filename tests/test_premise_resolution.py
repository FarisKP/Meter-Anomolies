import unittest
from unittest.mock import patch

from premise_resolution import InternalPremiseSource, OpenMeteoGeocoder, ServicePremise


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class PremiseResolutionTests(unittest.TestCase):
    def test_source_contract_parses_without_retaining_address_fields(self):
        source = InternalPremiseSource("https://internal.example/api", "secret", "test-source")
        premise = source._parse({
            "recordId": "PREM-42",
            "postalCode": "44114",
            "city": "Cleveland",
            "state": "OH",
            "countryCode": "us",
            "updatedAt": "2026-10-22T10:00:00Z",
            "addressLine1": "Not persisted by MeterIQ",
        })

        self.assertIsNotNone(premise)
        assert premise is not None
        self.assertEqual(premise.country_code, "US")
        self.assertTrue(premise.premise_id.startswith("SRC-"))
        self.assertEqual(len(premise.location_hash), 64)

    def test_geocoder_rejects_ambiguous_or_non_postcode_matches(self):
        premise = ServicePremise("test", "PREM-42", "44114", "Cleveland", "OH", "US", None)
        self.assertEqual(premise.postal_code, "44114")
        self.assertEqual(OpenMeteoGeocoder._ENDPOINT, "https://geocoding-api.open-meteo.com/v1/search")

    def test_geocoder_searches_by_postcode_and_accepts_one_exact_match(self):
        premise = ServicePremise("test", "PREM-42", "44114", "Cleveland", "OH", "US", None)
        payload = b'{"results":[{"country_code":"US","postcodes":["44114"],"latitude":41.5,"longitude":-81.7,"timezone":"America/New_York"}]}'
        with patch("premise_resolution.urlopen", return_value=FakeResponse(payload)) as opener:
            result = OpenMeteoGeocoder().resolve(premise)

        self.assertIsNotNone(result)
        self.assertIn("name=44114", opener.call_args.args[0])
        assert result is not None
        self.assertEqual(result["timezone"], "America/New_York")


if __name__ == "__main__":
    unittest.main()
