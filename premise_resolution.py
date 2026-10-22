"""Server-side service-premise resolution for weather investigations.

The adapter intentionally retains only the verified geocode and provenance in
MeterIQ. Full customer addresses stay in the authorised internal source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class PremiseResolutionError(RuntimeError):
    """Raised when an enabled internal-premise source cannot be read."""


@dataclass(frozen=True)
class ServicePremise:
    """The minimal, transient location record required for geocoding."""

    source_system: str
    source_record_id: str
    postal_code: str
    city: str
    region: str
    country_code: str
    source_updated_at: str | None

    @property
    def premise_id(self) -> str:
        digest = hashlib.sha256(
            f"{self.source_system}:{self.source_record_id}".encode("utf-8")
        ).hexdigest()[:48].upper()
        return f"SRC-{digest}"

    @property
    def location_hash(self) -> str:
        canonical = "|".join(
            value.strip().upper()
            for value in (self.postal_code, self.city, self.region, self.country_code)
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class InternalPremiseSource:
    """Configurable REST adapter for the authoritative service-premise system.

    Contract: ``GET {base_url}/customers/{customer_id}/service-premise``
    returns either the premise object or ``{\"servicePremise\": {...}}``.
    Required keys are ``recordId``, ``postalCode``, and ``countryCode``;
    ``city``, ``region``, and ``updatedAt`` are optional. The source response is
    used in memory only and is never persisted as an address in MeterIQ.
    """

    def __init__(self, base_url: str | None, api_key: str | None, source_name: str) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key
        self._source_name = source_name

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()

    def _parse(self, payload: object) -> ServicePremise | None:
        if not isinstance(payload, dict):
            return None
        record = payload.get("servicePremise", payload)
        if not isinstance(record, dict):
            return None
        source_record_id = self._text(record.get("recordId") or record.get("premiseId"))
        postal_code = self._text(record.get("postalCode") or record.get("zipCode"))
        country_code = self._text(record.get("countryCode")).upper()
        if not source_record_id or not postal_code or len(country_code) != 2:
            return None
        return ServicePremise(
            source_system=self._source_name,
            source_record_id=source_record_id,
            postal_code=postal_code,
            city=self._text(record.get("city")),
            region=self._text(record.get("region") or record.get("state")),
            country_code=country_code,
            source_updated_at=self._text(record.get("updatedAt")) or None,
        )

    def lookup(self, customer_id: str) -> ServicePremise | None:
        if not self.configured:
            return None
        target = f"{self._base_url}/customers/{quote(customer_id, safe='')}/service-premise"
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            with urlopen(Request(target, headers=headers), timeout=15) as response:
                return self._parse(json.loads(response.read().decode("utf-8")))
        except HTTPError as error:
            if error.code == 404:
                return None
            raise PremiseResolutionError(
                f"Internal premise-source request failed with HTTP {error.code}."
            ) from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise PremiseResolutionError("Could not retrieve the internal service-premise record.") from error


class OpenMeteoGeocoder:
    """Resolve a validated postal place to a weather-query coordinate."""

    _ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"

    def resolve(self, premise: ServicePremise) -> dict[str, Any] | None:
        query = urlencode({
            # The provider accepts a postcode directly. A city is not a valid
            # qualifier for this endpoint and caused valid Ohio postcodes to be
            # rejected as ambiguous/no-match.
            "name": premise.postal_code,
            "countryCode": premise.country_code,
            "count": 10,
            "language": "en",
        })
        try:
            with urlopen(f"{self._ENDPOINT}?{query}", timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return None
        exact_matches = [
            item for item in results if isinstance(item, dict)
            and str(item.get("country_code", "")).upper() == premise.country_code
            and premise.postal_code in {str(code) for code in item.get("postcodes", [])}
        ]
        if len(exact_matches) != 1:
            return None
        match = exact_matches[0]
        latitude, longitude = match.get("latitude"), match.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return None
        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "timezone": str(match.get("timezone") or "UTC"),
            "provider": "open-meteo-geocoding",
            "geocoded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
