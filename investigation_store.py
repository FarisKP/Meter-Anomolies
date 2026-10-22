"""Server-only persistence adapter for deterministic investigation records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from investigation_engine import DATA_CONTRACT_VERSION, ENGINE_VERSION, InvestigationCase


class InvestigationStoreError(RuntimeError):
    """Raised when a Supabase write cannot be completed."""


class SupabaseInvestigationStore:
    """Idempotent Supabase REST writer; it is never imported by browser code."""

    def __init__(self, url: str, secret_key: str) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key

    def _upsert(self, table: str, rows: list[dict[str, Any]], conflict_columns: str) -> None:
        if not rows:
            return
        target = f"{self._url}/rest/v1/{table}?{urlencode({'on_conflict': conflict_columns})}"
        request = Request(
            target,
            data=json.dumps(rows).encode("utf-8"),
            method="POST",
            headers={
                "apikey": self._secret_key,
                "Authorization": f"Bearer {self._secret_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urlopen(request, timeout=30):
                return
        except HTTPError as error:
            raise InvestigationStoreError(
                f"Supabase upsert into {table} failed with HTTP {error.code}."
            ) from error
        except (URLError, TimeoutError) as error:
            raise InvestigationStoreError(f"Could not write {table} to Supabase.") from error

    def _ticket_report_state(self) -> dict[str, bool]:
        """Return whether existing tickets need the newly generated report.

        A rerun must never reset an associate's status, team, notes, or
        remediation text.  It may only backfill the system-owned report field.
        """
        request = Request(
            f"{self._url}/rest/v1/investigation_tickets?{urlencode({'select': 'case_id,detailed_report'})}",
            headers={"apikey": self._secret_key, "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise InvestigationStoreError(f"Could not read ticket state from Supabase (HTTP {error.code}).") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise InvestigationStoreError("Could not read ticket state from Supabase.") from error
        if not isinstance(rows, list):
            raise InvestigationStoreError("Supabase returned an invalid ticket state response.")
        return {str(row.get("case_id")): bool(row.get("detailed_report")) for row in rows if isinstance(row, dict)}

    def _backfill_ticket_report(self, case_id: str, detailed_report: str, now: str) -> None:
        request = Request(
            f"{self._url}/rest/v1/investigation_tickets?{urlencode({'case_id': f'eq.{case_id}', 'detailed_report': 'is.null'})}",
            data=json.dumps({"detailed_report": detailed_report, "updated_at": now}).encode("utf-8"),
            method="PATCH",
            headers={
                "apikey": self._secret_key,
                "Authorization": f"Bearer {self._secret_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        try:
            with urlopen(request, timeout=30):
                return
        except HTTPError as error:
            raise InvestigationStoreError(f"Could not backfill ticket report (HTTP {error.code}).") from error
        except (URLError, TimeoutError) as error:
            raise InvestigationStoreError("Could not backfill the ticket report.") from error

    def save(
        self,
        cases: Iterable[InvestigationCase],
        source_run_id: str,
        *,
        create_tickets: bool = False,
    ) -> None:
        values = list(cases)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._upsert("data_source_runs", [{
            "source_run_id": source_run_id,
            "source_name": "usage-spike-analysis",
            "processed_at": now,
            "record_count": len(values),
            "data_contract_version": DATA_CONTRACT_VERSION,
            "engine_version": ENGINE_VERSION,
        }], "source_run_id")
        self._upsert("investigation_cases", [{
            "case_id": case.case_id,
            "case_key": case.case_key,
            "customer_id": case.customer_id,
            "meter_id": case.meter_id,
            "trigger_read_at": case.trigger_read_at,
            "trigger_usage": case.trigger_usage,
            "baseline_mean": case.baseline_mean,
            "spike_threshold": case.threshold,
            "severity": case.severity,
            "state": case.state,
            "recommended_action": case.recommended_action,
            "assigned_team": case.assigned_team or None,
            "possible_cause": case.possible_cause or None,
            "report_summary": case.report_summary or None,
            "source_run_id": case.source_run_id,
            "data_contract_version": DATA_CONTRACT_VERSION,
            "engine_version": ENGINE_VERSION,
            "updated_at": now,
        } for case in values], "case_key")
        self._upsert("investigation_evidence", [{
            "case_id": case.case_id,
            "check_code": evidence.check_code,
            "outcome": evidence.outcome,
            "summary": evidence.summary,
            "evidence_json": json.dumps(evidence.values, separators=(",", ":")),
            "recorded_at": now,
        } for case in values for evidence in case.evidence], "case_id,check_code")
        if not create_tickets:
            return
        existing_tickets = self._ticket_report_state()
        new_tickets = [{
            "ticket_id": f"TKT-{case.case_id}",
            "case_id": case.case_id,
            "status": "open",
            "assigned_team": case.assigned_team or "Meter Operations",
            "title": f"{case.severity.title()} usage spike review - {case.customer_id} / {case.meter_id}",
            "summary": case.report_summary or "Deterministic investigation requires associate review.",
            "detailed_report": case.detailed_report or None,
            "possible_cause": case.possible_cause or "Evidence review required.",
            "recommended_solution": case.recommended_action,
            "generated_by": ENGINE_VERSION,
            "created_at": now,
            "updated_at": now,
        } for case in values if case.state == "review_required" and case.case_id not in existing_tickets]
        self._upsert("investigation_tickets", new_tickets, "case_id")
        for case in values:
            if case.state == "review_required" and case.case_id in existing_tickets and not existing_tickets[case.case_id]:
                self._backfill_ticket_report(case.case_id, case.detailed_report, now)
