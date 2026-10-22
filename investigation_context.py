"""Server-side evidence retrieval for the deterministic investigation engine.

No browser receives Supabase or weather-provider credentials.  A missing or
failed source is represented as unavailable evidence rather than a guessed
finding, which keeps the investigation report auditable.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from premise_resolution import InternalPremiseSource, OpenMeteoGeocoder, PremiseResolutionError

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class InvestigationContextError(RuntimeError):
    """Raised only for a persistence failure that should stop auto-ticketing."""


class OpenMeteoWeather:
    """Retrieve hourly weather for an auditable meter-reading interval."""

    _ENDPOINT = "https://historical-forecast-api.open-meteo.com/v1/forecast"

    def observations(
        self, latitude: float, longitude: float, start_at: str, end_at: str
    ) -> list[dict[str, Any]] | None:
        """Return all hourly observations between two UTC meter timestamps.

        The historical-forecast endpoint covers the recent interval immediately
        preceding an incoming read as well as older readings. The caller keeps
        only the requested hours and persists each returned snapshot.
        """
        start = datetime.strptime(start_at, DATE_FORMAT)
        end = datetime.strptime(end_at, DATE_FORMAT)
        if end < start:
            return None
        query = urlencode({
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code",
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "timezone": "UTC",
        })
        try:
            with urlopen(f"{self._ENDPOINT}?{query}", timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None
        hourly = payload.get("hourly") if isinstance(payload, dict) else None
        times = hourly.get("time") if isinstance(hourly, dict) else None
        if not isinstance(times, list):
            return None

        def value(name: str, index: int) -> Any:
            values = hourly.get(name) if isinstance(hourly, dict) else None
            return values[index] if isinstance(values, list) and len(values) > index else None

        rows = []
        for index, value_at in enumerate(times):
            try:
                observed = datetime.strptime(str(value_at), "%Y-%m-%dT%H:%M")
            except ValueError:
                continue
            if not start <= observed <= end:
                continue
            rows.append({
                "available": True,
                "provider": "open-meteo-historical-forecast",
                "observedAt": observed.strftime(DATE_FORMAT),
                "temperatureC": value("temperature_2m", index),
                "apparentTemperatureC": value("apparent_temperature", index),
                "relativeHumidityPercent": value("relative_humidity_2m", index),
                "precipitationMm": value("precipitation", index),
                "weatherCode": value("weather_code", index),
            })
        return rows or None


class SupabaseInvestigationContext:
    """Load approved evidence sources and optionally cache weather snapshots."""

    def __init__(
        self,
        url: str,
        secret_key: str,
        weather_enabled: bool = False,
        premise_source_enabled: bool = False,
        premise_source_base_url: str | None = None,
        premise_source_api_key: str | None = None,
        premise_source_name: str = "internal-service-premise",
    ) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key
        self._weather_enabled = weather_enabled
        self._weather = OpenMeteoWeather()
        self._premise_source = (
            InternalPremiseSource(premise_source_base_url, premise_source_api_key, premise_source_name)
            if premise_source_enabled else None
        )
        self._geocoder = OpenMeteoGeocoder()

    def _request(self, table: str, query: dict[str, str], *, method: str = "GET", rows: list[dict[str, Any]] | None = None) -> Any:
        target = f"{self._url}/rest/v1/{table}?{urlencode(query)}"
        request = Request(
            target,
            data=json.dumps(rows).encode("utf-8") if rows is not None else None,
            method=method,
            headers={
                "apikey": self._secret_key,
                "Authorization": f"Bearer {self._secret_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as error:
            raise InvestigationContextError(f"Supabase evidence request failed with HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise InvestigationContextError("Could not retrieve deterministic investigation evidence.") from error

    def _rows(self, table: str, query: dict[str, str]) -> list[dict[str, Any]]:
        response = self._request(table, query)
        return response if isinstance(response, list) else []

    @staticmethod
    def _as_utc_text(value: str) -> str:
        return datetime.strptime(value, DATE_FORMAT).strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _nearby(rows: list[dict[str, Any]], field: str, read_at: str, days: int = 90) -> list[dict[str, Any]]:
        target = datetime.strptime(read_at, DATE_FORMAT)
        start = target - timedelta(days=days)
        values = []
        for row in rows:
            try:
                observed = datetime.fromisoformat(str(row.get(field, "")).replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
            if start <= observed <= target:
                values.append(row)
        return values

    @staticmethod
    def _weather_summary(rows: list[dict[str, Any]], start_at: str, end_at: str) -> dict[str, Any] | None:
        if not rows:
            return None
        by_time = {str(row.get("observedAt")): row for row in rows}
        trigger = by_time.get(end_at)
        if not trigger:
            return None
        apparent = [
            float(row["apparentTemperatureC"])
            for row in rows if row.get("apparentTemperatureC") is not None
        ]
        temperatures = [
            float(row["temperatureC"])
            for row in rows if row.get("temperatureC") is not None
        ]
        return {
            **trigger,
            "rangeStart": start_at,
            "rangeEnd": end_at,
            "sampleCount": len(rows),
            "minApparentTemperatureC": min(apparent) if apparent else None,
            "maxApparentTemperatureC": max(apparent) if apparent else None,
            "minTemperatureC": min(temperatures) if temperatures else None,
            "maxTemperatureC": max(temperatures) if temperatures else None,
            "extremeHeatHours": sum(value >= 32 for value in apparent),
            "extremeColdHours": sum(value <= 0 for value in apparent),
        }

    def _weather_for(
        self, premise: dict[str, Any] | None, historical_read_at: str | None, read_at: str
    ) -> dict[str, Any] | None:
        if not premise:
            return None
        premise_id = str(premise.get("premise_id", ""))
        if not premise_id or not historical_read_at:
            return None
        start_at = historical_read_at
        start_iso = self._as_utc_text(start_at)
        end_iso = self._as_utc_text(read_at)
        snapshots = self._rows("weather_snapshots", {
            "select": "premise_id,observed_at,provider,temperature_c,apparent_temperature_c,relative_humidity_percent,precipitation_mm,weather_code",
            "premise_id": f"eq.{premise_id}", "observed_at": f"gte.{start_iso}",
            "order": "observed_at.asc",
        })
        cached = []
        for snapshot in snapshots:
            observed = self._timestamp_text(snapshot.get("observed_at"))
            if start_at <= observed <= read_at:
                cached.append({
                    "available": True, "provider": snapshot.get("provider"), "observedAt": observed,
                    "temperatureC": snapshot.get("temperature_c"), "apparentTemperatureC": snapshot.get("apparent_temperature_c"),
                    "relativeHumidityPercent": snapshot.get("relative_humidity_percent"), "precipitationMm": snapshot.get("precipitation_mm"),
                    "weatherCode": snapshot.get("weather_code"),
                })
        expected_hours = int((datetime.strptime(read_at, DATE_FORMAT) - datetime.strptime(start_at, DATE_FORMAT)).total_seconds() / 3600) + 1
        cached_times = {str(row.get("observedAt")) for row in cached}
        expected_times = {
            (datetime.strptime(start_at, DATE_FORMAT) + timedelta(hours=index)).strftime(DATE_FORMAT)
            for index in range(expected_hours)
        }
        cached_summary = self._weather_summary(cached, start_at, read_at)
        if cached_summary and expected_times.issubset(cached_times):
            return cached_summary
        if not self._weather_enabled or premise.get("latitude") is None or premise.get("longitude") is None:
            return None
        weather = self._weather.observations(float(premise["latitude"]), float(premise["longitude"]), start_at, read_at)
        if weather is None:
            return None
        try:
            self._request("weather_snapshots", {"on_conflict": "premise_id,observed_at"}, method="POST", rows=[{
                "premise_id": premise_id, "observed_at": self._as_utc_text(row["observedAt"]), "provider": row["provider"],
                "temperature_c": row["temperatureC"], "apparent_temperature_c": row["apparentTemperatureC"],
                "relative_humidity_percent": row["relativeHumidityPercent"], "precipitation_mm": row["precipitationMm"],
                "weather_code": row["weatherCode"], "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            } for row in weather])
        except InvestigationContextError:
            # The report keeps the fetched evidence even if its cache cannot be written.
            pass
        return self._weather_summary(weather, start_at, read_at)

    def _resolve_premise(
        self, customer_id: str, existing: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Resolve one authoritative premise only when no usable geocode exists."""
        if existing and existing.get("latitude") is not None and existing.get("longitude") is not None:
            return existing
        if not self._premise_source or not self._premise_source.configured:
            return existing
        try:
            source_premise = self._premise_source.lookup(customer_id)
        except PremiseResolutionError:
            # Missing third-party/internal source evidence must not block ticket creation.
            return existing
        if not source_premise:
            return existing
        geocode = self._geocoder.resolve(source_premise)
        status = "verified" if geocode else "needs_review"
        row = {
            "premise_id": source_premise.premise_id,
            "customer_id": customer_id,
            "latitude": geocode["latitude"] if geocode else None,
            "longitude": geocode["longitude"] if geocode else None,
            "timezone": geocode["timezone"] if geocode else "UTC",
            "source_system": source_premise.source_system,
            "source_record_id": source_premise.source_record_id,
            "location_reference_hash": source_premise.location_hash,
            "geocode_status": status,
            "geocode_provider": geocode["provider"] if geocode else "open-meteo-geocoding",
            "geocoded_at": geocode["geocoded_at"] if geocode else None,
            "source_updated_at": source_premise.source_updated_at,
        }
        try:
            self._request("customer_premises", {"on_conflict": "premise_id"}, method="POST", rows=[row])
        except InvestigationContextError:
            return existing
        return row

    @staticmethod
    def _timestamp_text(value: Any) -> str:
        text = str(value or "")
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime(DATE_FORMAT)
        except ValueError:
            return text

    def for_read(
        self, customer_id: str, meter_id: str, read_at: str, historical_read_at: str | None = None
    ) -> dict[str, Any]:
        premises = self._rows("customer_premises", {
            "select": "premise_id,latitude,longitude,timezone,active_from,active_to,geocode_status",
            "customer_id": f"eq.{customer_id}", "limit": "1",
        })
        premise = self._resolve_premise(customer_id, premises[0] if premises else None)
        meter_events = self._nearby(self._rows("meter_events", {
            "select": "event_id,event_type,event_at,meter_status,work_order_reference",
            "meter_id": f"eq.{meter_id}", "order": "event_at.desc", "limit": "25",
        }), "event_at", read_at)
        billing_rows = self._rows("billing_read_context", {
            "select": "read_disposition,billing_state,estimated_reason,correction_required,source_reference",
            "meter_id": f"eq.{meter_id}", "read_at": f"eq.{self._as_utc_text(read_at)}", "limit": "1",
        })
        return {
            "weather": self._weather_for(premise, historical_read_at, read_at),
            "meterEvents": meter_events,
            "billingContext": {
                "correctionRequired": bool(billing_rows and billing_rows[0].get("correction_required")),
                "source": billing_rows[0] if billing_rows else None,
            },
        }
