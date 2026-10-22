"""Supabase REST implementation of the meter-data repository.

The adapter uses the Python standard library so the CSV application can switch
backends without adding a runtime dependency. It is server-side only: never
send the configured secret key to dashboard.html or another browser client.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from meter_models import MeterRead, ReadKey, SpikeResult


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

    def customer_meter_pairs(self) -> list[tuple[str, str]]:
        """Use the small mapping table; do not download historical reads for a form."""
        return sorted((customer_id, meter_id) for meter_id, customer_id in self._customer_by_meter().items())

    def read_exists(self, key: ReadKey) -> bool:
        """Check operational reads and previously screened form submissions."""
        _, meter_id, read_at = key
        rows = self._fetch_rows(
            "meter_reads",
            {
                "select": "read_id",
                "meter_id": f"eq.{meter_id}",
                "read_at": f"eq.{read_at.replace(' ', 'T')}",
                "limit": "1",
            },
        )
        if rows:
            return True
        submissions = self._fetch_rows(
            "input_feed_submissions",
            {
                "select": "submission_id",
                "meter_id": f"eq.{meter_id}",
                "read_at": f"eq.{read_at.replace(' ', 'T')}",
                "limit": "1",
            },
        )
        return bool(submissions)

    def historical_reads_for_slot(self, read: MeterRead, lookback_days: int) -> list[MeterRead]:
        """Fetch only the matching historical baseline for an input reading."""
        target = datetime.strptime(read.read_at, "%Y-%m-%d %H:%M:%S")
        start = target - timedelta(days=lookback_days)
        rows = self._fetch_rows(
            "meter_reads",
            {
                "select": "meter_id,read_at,meter_status,current_read,previous_read,usage_index,budget_indicator",
                "batch_id": f"eq.{self._history_batch_id}",
                "meter_id": f"eq.{read.meter_number}",
                "slot_hour": f"eq.{target.hour}",
                "and": (
                    f"(read_at.gte.{start.strftime('%Y-%m-%dT%H:%M:%S')},"
                    f"read_at.lt.{target.strftime('%Y-%m-%dT%H:%M:%S')})"
                ),
                "order": "read_at.asc",
            },
        )
        return [self._to_meter_read(row) for row in rows]

    def latest_historical_read_at(self, meter_id: str, before_read_at: str) -> str | None:
        """Fetch one meter's latest history record before an input-feed read."""
        rows = self._fetch_rows(
            "meter_reads",
            {
                "select": "read_at",
                "batch_id": f"eq.{self._history_batch_id}",
                "meter_id": f"eq.{meter_id}",
                "read_at": f"lt.{before_read_at.replace(' ', 'T')}",
                "order": "read_at.desc",
                "limit": "1",
            },
        )
        return self._timestamp_text(rows[0].get("read_at")) if rows else None

    def input_feed_spike_candidates(self) -> list[MeterRead]:
        rows = self._fetch_rows(
            "meter_reads_temp",
            {
                "select": "meter_id,read_at,meter_status,current_read,previous_read,usage_index,budget_indicator",
                "spike_indicator": "is.true",
                "order": "read_at.desc",
            },
        )
        return [self._to_meter_read(row) for row in rows]

    def input_feed_spike_candidate_evidence(self) -> dict[ReadKey, dict[str, object]]:
        """Read deterministic screening evidence saved with queued form submissions."""
        rows = self._fetch_rows(
            "input_feed_submissions",
            {
                "select": "customer_id,meter_id,read_at,read_type,validation_json",
                "validation_status": "eq.accepted_spike_candidate",
                "order": "submitted_at.desc",
            },
        )
        evidence: dict[ReadKey, dict[str, object]] = {}
        for row in rows:
            try:
                payload = json.loads(self._text(row.get("validation_json")))
            except json.JSONDecodeError:
                continue
            screening = payload.get("spike_screening")
            if not isinstance(screening, dict):
                continue
            key = (
                self._text(row.get("customer_id")),
                self._text(row.get("meter_id")),
                self._timestamp_text(row.get("read_at")),
            )
            evidence[key] = {
                "readType": self._text(row.get("read_type")),
                "baselineCount": screening.get("baselineCount"),
                "baselineMean": screening.get("baselineMean"),
                "baselineStddev": screening.get("baselineStddev"),
                "threshold": screening.get("threshold"),
                "reason": screening.get("reason"),
                "lookbackDays": screening.get("lookbackDays"),
                "minHistory": screening.get("minHistory"),
                "sigma": screening.get("sigma"),
            }
        return evidence

    def input_feed_investigations(self) -> dict[ReadKey, dict[str, object]]:
        """Return automatic cases and tickets for rows held in the protected queue."""
        try:
            cases = self._fetch_rows("investigation_cases", {
                "select": "case_id,customer_id,meter_id,trigger_read_at,severity,state,assigned_team,possible_cause,report_summary,recommended_action",
                "source_run_id": "like.input-feed-%",
                "order": "updated_at.desc",
            })
            tickets = self._fetch_rows("investigation_tickets", {
                "select": "ticket_id,case_id,status,assigned_team,title,summary,detailed_report,possible_cause,recommended_solution,associate_notes,last_edited_by,updated_at",
                "order": "updated_at.desc",
            })
            comments = self._fetch_rows("investigation_ticket_comments", {
                "select": "ticket_id,comment_id,author,comment_text,created_at",
                "order": "created_at.asc",
            })
            evidence_rows = self._fetch_rows("investigation_evidence", {
                "select": "case_id,check_code,outcome,summary,evidence_json",
            })
        except SupabaseRepositoryError:
            # The dashboard remains usable until migration 009 is applied.
            return {}
        tickets_by_case = {self._text(row.get("case_id")): row for row in tickets}
        comments_by_ticket: dict[str, list[dict[str, str]]] = {}
        for comment in comments:
            comments_by_ticket.setdefault(self._text(comment.get("ticket_id")), []).append({
                "commentId": self._text(comment.get("comment_id")),
                "author": self._text(comment.get("author")),
                "text": self._text(comment.get("comment_text")),
                "createdAt": self._timestamp_text(comment.get("created_at")),
            })
        evidence_by_case: dict[str, list[dict[str, object]]] = {}
        for row in evidence_rows:
            try:
                values = json.loads(self._text(row.get("evidence_json")))
            except json.JSONDecodeError:
                values = {}
            evidence_by_case.setdefault(self._text(row.get("case_id")), []).append({
                "checkCode": self._text(row.get("check_code")),
                "outcome": self._text(row.get("outcome")),
                "summary": self._text(row.get("summary")),
                "values": values if isinstance(values, dict) else {},
            })
        values: dict[ReadKey, dict[str, object]] = {}
        for case in cases:
            case_id = self._text(case.get("case_id"))
            ticket = tickets_by_case.get(case_id, {})
            values[(
                self._text(case.get("customer_id")),
                self._text(case.get("meter_id")),
                self._timestamp_text(case.get("trigger_read_at")),
            )] = {
                "caseId": case_id,
                "severity": self._text(case.get("severity")),
                "state": self._text(case.get("state")),
                "assignedTeam": self._text(ticket.get("assigned_team") or case.get("assigned_team")),
                "possibleCause": self._text(ticket.get("possible_cause") or case.get("possible_cause")),
                "summary": self._text(ticket.get("summary") or case.get("report_summary")),
                "detailedReport": self._text(ticket.get("detailed_report")),
                "recommendedSolution": self._text(ticket.get("recommended_solution") or case.get("recommended_action")),
                "ticketId": self._text(ticket.get("ticket_id")),
                "ticketStatus": self._text(ticket.get("status")),
                "title": self._text(ticket.get("title")),
                "associateNotes": self._text(ticket.get("associate_notes")),
                "lastEditedBy": self._text(ticket.get("last_edited_by")),
                "comments": comments_by_ticket.get(self._text(ticket.get("ticket_id")), []),
                "evidence": evidence_by_case.get(case_id, []),
            }
        return values
