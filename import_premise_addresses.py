#!/usr/bin/env python3
"""Resolve a local premise-address CSV without storing street addresses.

The command reads the approved local file, validates it against Supabase
customers, geocodes the postal locality, and writes only coordinate/provenance
metadata to ``customer_premises`` when ``--apply`` is supplied.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app_config import AppConfig
from premise_resolution import OpenMeteoGeocoder, ServicePremise


REQUIRED_COLUMNS = (
    "customer_id", "premise_id", "address_line1", "city", "state",
    "postal_code", "country_code", "source_updated_at",
)
SOURCE_SYSTEM = "csv-premise-address-load"


class PremiseImportError(RuntimeError):
    """Raised when a protected premise import cannot complete safely."""


@dataclass(frozen=True)
class ImportOutcome:
    customer_id: str
    premise_id: str
    status: str
    provider: str
    latitude: float | None
    longitude: float | None
    timezone: str | None
    message: str
    database_row: dict[str, Any] | None

    def review_row(self) -> dict[str, str]:
        return {
            "customer_id": self.customer_id,
            "premise_id": self.premise_id,
            "status": self.status,
            "provider": self.provider,
            "latitude": "" if self.latitude is None else f"{self.latitude:.6f}",
            "longitude": "" if self.longitude is None else f"{self.longitude:.6f}",
            "timezone": self.timezone or "",
            "message": self.message,
        }


class SupabasePremiseStore:
    def __init__(self, url: str, secret_key: str) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key

    def _request(
        self, table: str, query: dict[str, str], *, method: str = "GET", rows: list[dict[str, Any]] | None = None
    ) -> Any:
        request = Request(
            f"{self._url}/rest/v1/{table}?{urlencode(query)}",
            data=json.dumps(rows).encode("utf-8") if rows is not None else None,
            method=method,
            headers={
                "apikey": self._secret_key,
                "Authorization": f"Bearer {self._secret_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as error:
            raise PremiseImportError(f"Supabase request for {table} failed with HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise PremiseImportError(f"Could not read or write {table} in Supabase.") from error

    def customer_ids(self) -> set[str]:
        rows = self._request("customers", {"select": "customer_id"})
        return {
            str(row.get("customer_id")) for row in rows
            if isinstance(row, dict) and row.get("customer_id")
        } if isinstance(rows, list) else set()

    def upsert(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            self._request("customer_premises", {"on_conflict": "premise_id"}, method="POST", rows=rows)


def _text(row: dict[str, str], field: str) -> str:
    return str(row.get(field, "")).strip()


def _timestamp(value: str) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def load_source_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            headers = tuple(reader.fieldnames or ())
            missing = [column for column in REQUIRED_COLUMNS if column not in headers]
            if missing:
                raise PremiseImportError(f"The address file is missing required columns: {', '.join(missing)}.")
            return list(reader)
    except OSError as error:
        raise PremiseImportError(f"Could not read address input file: {path}.") from error


def resolve_rows(rows: list[dict[str, str]], known_customers: set[str]) -> list[ImportOutcome]:
    geocoder = OpenMeteoGeocoder()
    outcomes: list[ImportOutcome] = []
    seen_premises: set[str] = set()
    for row in rows:
        customer_id = _text(row, "customer_id")
        premise_id = _text(row, "premise_id")
        city = _text(row, "city")
        region = _text(row, "state")
        postal_code = _text(row, "postal_code")
        country_code = _text(row, "country_code").upper()
        source_updated_at = _timestamp(_text(row, "source_updated_at"))
        invalid = (
            not customer_id or not premise_id or not city or not region or not postal_code
            or len(country_code) != 2 or source_updated_at is None
        )
        if invalid:
            outcomes.append(ImportOutcome(customer_id, premise_id, "failed", "", None, None, None,
                "Missing or invalid required location fields.", None))
            continue
        if customer_id not in known_customers:
            outcomes.append(ImportOutcome(customer_id, premise_id, "failed", "", None, None, None,
                "Customer ID is not present in Supabase.", None))
            continue
        if premise_id in seen_premises:
            outcomes.append(ImportOutcome(customer_id, premise_id, "failed", "", None, None, None,
                "Duplicate premise ID in input file.", None))
            continue
        seen_premises.add(premise_id)
        source_premise = ServicePremise(
            source_system=SOURCE_SYSTEM,
            source_record_id=premise_id,
            postal_code=postal_code,
            city=city,
            region=region,
            country_code=country_code,
            source_updated_at=source_updated_at,
        )
        geocode = geocoder.resolve(source_premise)
        if not geocode:
            outcomes.append(ImportOutcome(customer_id, premise_id, "needs_review", "open-meteo-geocoding", None, None, None,
                "No single exact postcode match was returned; no coordinates were selected.", {
                    "premise_id": premise_id, "customer_id": customer_id,
                    "source_system": SOURCE_SYSTEM, "source_record_id": premise_id,
                    "location_reference_hash": source_premise.location_hash,
                    "geocode_status": "needs_review", "geocode_provider": "open-meteo-geocoding",
                    "source_updated_at": source_updated_at,
                }))
            continue
        database_row = {
            "premise_id": premise_id,
            "customer_id": customer_id,
            "latitude": geocode["latitude"],
            "longitude": geocode["longitude"],
            "timezone": geocode["timezone"],
            "source_system": SOURCE_SYSTEM,
            "source_record_id": premise_id,
            "location_reference_hash": source_premise.location_hash,
            "geocode_status": "verified",
            "geocode_provider": geocode["provider"],
            "geocoded_at": geocode["geocoded_at"],
            "source_updated_at": source_updated_at,
        }
        outcomes.append(ImportOutcome(customer_id, premise_id, "verified", geocode["provider"],
            geocode["latitude"], geocode["longitude"], geocode["timezone"],
            "Exact postcode match verified.", database_row))
    return outcomes


def write_review(path: Path, outcomes: list[ImportOutcome]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ("customer_id", "premise_id", "status", "provider", "latitude", "longitude", "timezone", "message")
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        writer.writerows(outcome.review_row() for outcome in outcomes)


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Local address CSV; it is never uploaded to Supabase.")
    parser.add_argument("--report", type=Path, default=root / "premise_address_import_review.csv")
    parser.add_argument("--apply", action="store_true", help="Persist derived geocodes and status metadata to Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and geocode only; this is the default behavior.")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("Choose either --apply or --dry-run, not both.")
    try:
        config = AppConfig.from_environment(root)
        if config.data_backend != "supabase":
            raise PremiseImportError("Premise import requires DATA_BACKEND=supabase.")
        store = SupabasePremiseStore(config.supabase_url or "", config.supabase_secret_key or "")
        outcomes = resolve_rows(load_source_rows(args.input), store.customer_ids())
        write_review(args.report, outcomes)
        if args.apply:
            store.upsert([outcome.database_row for outcome in outcomes if outcome.database_row])
    except (PremiseImportError, ValueError) as error:
        parser.error(str(error))
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    mode = "applied" if args.apply else "dry-run"
    print(f"Premise import {mode}: " + ", ".join(f"{status}={count}" for status, count in sorted(counts.items())))
    print(f"Review report: {args.report}")


if __name__ == "__main__":
    main()
