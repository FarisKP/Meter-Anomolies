"""Supabase REST implementation of the meter-data repository.

The adapter uses the Python standard library so the CSV application can switch
backends without adding a runtime dependency. It is server-side only: never
send the configured secret key to dashboard.html or another browser client.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from meter_models import MeterRead, SpikeResult


class SupabaseRepositoryError(RuntimeError):
    """Raised when the configured Supabase REST API cannot provide data."""


class SupabaseMeterRepository:
    PAGE_SIZE = 1_000

    def __init__(
        self,
        url: str,
        secret_key: str,
        history_batch_id: str,
        current_batch_id: str,
        analysis_run_id: str | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key
        self._history_batch_id = history_batch_id
        self._current_batch_id = current_batch_id
        self._analysis_run_id = analysis_run_id
        self._meter_customers: dict[str, str] | None = None

    def _fetch_rows(self, table: str, query: dict[str, str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            url = f"{self._url}/rest/v1/{table}?{urlencode(query)}"
            request = Request(
                url,
                headers={
                    "apikey": self._secret_key,
                    "Accept": "application/json",
                    "Range": f"{start}-{start + self.PAGE_SIZE - 1}",
                },
            )
            try:
                with urlopen(request, timeout=30) as response:
                    page = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                raise SupabaseRepositoryError(
                    f"Supabase request for {table} failed with HTTP {error.code}."
                ) from error
            except (URLError, TimeoutError, json.JSONDecodeError) as error:
                raise SupabaseRepositoryError(f"Could not read {table} from Supabase.") from error

            if not isinstance(page, list):
                raise SupabaseRepositoryError(f"Supabase returned an invalid {table} response.")
            rows.extend(page)
            if len(page) < self.PAGE_SIZE:
                return rows
            start += self.PAGE_SIZE

    def _customer_by_meter(self) -> dict[str, str]:
        if self._meter_customers is None:
            rows = self._fetch_rows("meters", {"select": "meter_id,customer_id"})
            self._meter_customers = {
                str(row["meter_id"]): str(row["customer_id"])
                for row in rows
                if row.get("meter_id") is not None and row.get("customer_id") is not None
            }
        return self._meter_customers

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _timestamp_text(value: Any) -> str:
        text = SupabaseMeterRepository._text(value)
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return text

    def _to_meter_read(self, row: dict[str, Any]) -> MeterRead:
        meter_number = self._text(row.get("meter_id"))
        return MeterRead(
            customer_id=self._customer_by_meter().get(meter_number, ""),
            meter_number=meter_number,
            meter_status=self._text(row.get("meter_status")),
            current_read=self._text(row.get("current_read")),
            read_at=self._timestamp_text(row.get("read_at")),
            previous_read=self._text(row.get("previous_read")),
            usage_index=self._text(row.get("usage_index")),
            budget_indicator=self._text(row.get("budget_indicator")),
        )

    def _reads_for_batch(self, batch_id: str) -> list[MeterRead]:
        rows = self._fetch_rows(
            "meter_reads",
            {
                "select": (
                    "meter_id,read_at,meter_status,current_read,previous_read,"
                    "usage_index,budget_indicator"
                ),
                "batch_id": f"eq.{batch_id}",
                "order": "read_at.asc",
            },
        )
        return [self._to_meter_read(row) for row in rows]

    def history_reads(self) -> list[MeterRead]:
        return self._reads_for_batch(self._history_batch_id)

    def current_reads(self) -> list[MeterRead]:
        return self._reads_for_batch(self._current_batch_id)

    def analysis_results(self) -> list[SpikeResult]:
        run_query = {"select": "run_id", "limit": "1"}
        if self._analysis_run_id:
            run_query["run_id"] = f"eq.{self._analysis_run_id}"
        else:
            run_query["order"] = "executed_at.desc"
        runs = self._fetch_rows("analysis_runs", run_query)
        if not runs:
            return []
        run_id = self._text(runs[0].get("run_id"))
        rows = self._fetch_rows(
            "spike_results",
            {
                "select": (
                    "baseline_count,baseline_mean,baseline_stddev,spike_threshold,spike_flag,"
                    "flag_reason,meter_reads(meter_id,read_at)"
                ),
                "run_id": f"eq.{run_id}",
            },
        )
        results = []
        customer_by_meter = self._customer_by_meter()
        for row in rows:
            read = row.get("meter_reads") or {}
            if not isinstance(read, dict):
                raise SupabaseRepositoryError("Supabase did not return the linked meter read.")
            meter_number = self._text(read.get("meter_id"))
            results.append(
                SpikeResult(
                    customer_id=customer_by_meter.get(meter_number, ""),
                    meter_number=meter_number,
                    read_at=self._timestamp_text(read.get("read_at")),
                    baseline_count=self._text(row.get("baseline_count")),
                    baseline_mean=self._text(row.get("baseline_mean")),
                    baseline_stddev=self._text(row.get("baseline_stddev")),
                    threshold=self._text(row.get("spike_threshold")),
                    flag=self._text(row.get("spike_flag")),
                    reason=self._text(row.get("flag_reason")),
                )
            )
        return results
