#!/usr/bin/env python3
"""Serve the local meter usage dashboard and its data API."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app_config import AppConfig
from feed_ingestion import (
    FeedSubmission,
    FeedSubmissionError,
    FeedStorageError,
    SupabaseFeedStore,
    feed_reference,
    receipt,
    validate_submission,
)
from investigation_context import InvestigationContextError, SupabaseInvestigationContext
from investigation_engine import generate_investigations, investigation_payload
from investigation_store import InvestigationStoreError, SupabaseInvestigationStore
from ticket_workspace import SupabaseTicketWorkspace, TicketWorkspaceError
from meter_models import MeterRead
from meter_repository import MeterDataRepository
from repository_factory import create_repository
from spike_screening import screen_read


ROOT = Path(__file__).resolve().parent
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CONFIG = AppConfig.from_environment(ROOT)
REPOSITORY = create_repository(CONFIG)


def timestamp(read: MeterRead) -> datetime:
    return datetime.strptime(read.read_at, DATE_FORMAT)


def number(value_text: str) -> float:
    try:
        value = float(value_text)
        return value if math.isfinite(value) else 0.0
    except (ValueError, TypeError):
        return 0.0


def build_data(repository: MeterDataRepository = REPOSITORY) -> dict:
    history = repository.history_reads()
    current = repository.current_reads()
    results = repository.analysis_results()
    results_by_key = {result.key: result for result in results}
    input_feed_candidates = repository.input_feed_spike_candidates()
    evidence_reader = getattr(repository, "input_feed_spike_candidate_evidence", None)
    candidate_evidence = evidence_reader() if callable(evidence_reader) else {}
    investigation_reader = getattr(repository, "input_feed_investigations", None)
    candidate_investigations = investigation_reader() if callable(investigation_reader) else {}

    by_customer: dict[str, list[dict]] = defaultdict(list)
    daily_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    slot_values: dict[tuple[str, int], list[float]] = defaultdict(list)
    max_rows: dict[str, dict] = {}

    for read in history:
        try:
            when = timestamp(read)
            usage = number(read.usage_index)
        except (ValueError, TypeError):
            continue
        customer = read.customer_id or "Unknown"
        day = when.strftime("%Y-%m-%d")
        by_customer[customer].append({"date": day, "time": when.strftime("%H:%M"), "usage": usage})
        daily_values[(customer, day)].append(usage)
        slot_values[(customer, when.hour)].append(usage)
        if customer not in max_rows or usage > max_rows[customer]["usage"]:
            max_rows[customer] = {"usage": usage, "date": day, "time": when.strftime("%H:%M")}

    customers = sorted(set(by_customer) | {read.customer_id for read in current})
    daily_series = []
    customer_stats = {}
    slot_stats = {}
    for customer in customers:
        usage_list = [item["usage"] for item in by_customer.get(customer, [])]
        usage_sorted = sorted(usage_list)
        daily_list = []
        for (cust, day), readings in daily_values.items():
            if cust != customer:
                continue
            daily_list.append({
                "date": day,
                "average": sum(readings) / len(readings),
                "total": sum(readings),
                "count": len(readings),
            })
        daily_list.sort(key=lambda item: item["date"])
        daily_series.extend({"customer": customer, **item} for item in daily_list)
        average = sum(usage_list) / len(usage_list) if usage_list else 0
        daily_averages = [item["average"] for item in daily_list]
        customer_stats[customer] = {
            "readings": len(usage_list),
            "days": len(daily_list),
            "mean": average,
            "min": min(usage_list) if usage_list else 0,
            "max": max_rows.get(customer, {}).get("usage", 0),
            "maxAt": max_rows.get(customer),
            "p99": usage_sorted[min(len(usage_sorted) - 1, int(0.99 * len(usage_sorted)))] if usage_sorted else 0,
            "dailyAverage": sum(daily_averages) / len(daily_averages) if daily_averages else 0,
        }
        for hour in range(0, 24, 4):
            values = slot_values.get((customer, hour), [])
            mean = sum(values) / len(values) if values else 0
            sd = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values)) if values else 0
            slot_stats[f"{customer}|{hour:02d}"] = {
                "count": len(values), "mean": mean, "stddev": sd,
            }

    current_rows = []
    for read in current:
        key = read.key
        result = results_by_key.get(key, {})
        current_rows.append({
            **read.to_api_row(),
            "usageNumber": number(read.usage_index),
            "flag": result.flag if result else "NOT_ANALYZED",
            "threshold": result.threshold if result else "",
            "baselineMean": result.baseline_mean if result else "",
            "reason": result.reason if result else "No matching analysis result found.",
        })

    candidate_rows = []
    for read in input_feed_candidates:
        evidence = candidate_evidence.get(read.key, {})
        investigation = candidate_investigations.get(read.key, {})
        candidate_rows.append({
            **read.to_api_row(),
            "usageNumber": number(read.usage_index),
            "flag": "TRUE",
            "readType": evidence.get("readType", "actual"),
            "baselineCount": evidence.get("baselineCount", ""),
            "baselineMean": evidence.get("baselineMean", ""),
            "baselineStddev": evidence.get("baselineStddev", ""),
            "threshold": evidence.get("threshold", ""),
            "reason": evidence.get("reason") or "Input-feed screening identified this reading as a spike candidate. Associate review is required.",
            "screening": evidence,
            "investigation": investigation,
            "source": "input_feed_screening",
        })

    screened_rows = [*current_rows, *candidate_rows]
    latest = max((row.get("current-meter-read-timestamp", "") for row in current_rows), default="")
    screened_latest = max((row.get("current-meter-read-timestamp", "") for row in screened_rows), default="")
    flagged = sum(row["flag"] == "TRUE" for row in screened_rows)
    budget_flagged = sum(
        row["flag"] == "TRUE" and row.get("budget indicator") == "Y"
        for row in screened_rows
    )
    current_dates = []
    observed_months: dict[str, set[str]] = defaultdict(set)
    for read in current:
        try:
            when = timestamp(read)
        except (ValueError, TypeError):
            continue
        current_dates.append(when)
        observed_months[read.customer_id or "Unknown"].add(when.strftime("%Y-%m"))
    expected_months = []
    if current_dates:
        cursor = min(current_dates).replace(day=1, hour=0, minute=0, second=0)
        last_month = max(current_dates).replace(day=1, hour=0, minute=0, second=0)
        while cursor <= last_month:
            expected_months.append(cursor.strftime("%Y-%m"))
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    missing_read_months = [
        {"customer": customer, "month": month,
         "monthLabel": datetime.strptime(month, "%Y-%m").strftime("%B %Y")}
        for customer in customers
        for month in expected_months
        if month not in observed_months.get(customer, set())
    ]
    missing_read_gaps = []
    if current_dates:
        first_slot = min(current_dates).replace(minute=0, second=0, microsecond=0)
        first_slot = first_slot.replace(hour=(first_slot.hour // 4) * 4)
        last_slot = max(current_dates).replace(minute=0, second=0, microsecond=0)
        last_slot = last_slot.replace(hour=(last_slot.hour // 4) * 4)
        for customer in customers:
            observed_slots = {
                when for read in current
                if read.customer_id == customer
                for when in [timestamp(read)]
            }
            cursor = first_slot
            gap_start = None
            gap_count = 0
            while cursor <= last_slot:
                if cursor not in observed_slots:
                    if gap_start is None:
                        gap_start = cursor
                    gap_count += 1
                elif gap_start is not None:
                    missing_read_gaps.append({
                        "customer": customer,
                        "start": gap_start.strftime(DATE_FORMAT),
                        "end": (cursor - timedelta(hours=4)).strftime(DATE_FORMAT),
                        "missingReads": gap_count,
                    })
                    gap_start = None
                    gap_count = 0
                cursor += timedelta(hours=4)
            if gap_start is not None:
                missing_read_gaps.append({
                    "customer": customer,
                    "start": gap_start.strftime(DATE_FORMAT),
                    "end": last_slot.strftime(DATE_FORMAT),
                    "missingReads": gap_count,
                })
    return {
        "historyCount": len(history),
        "currentCount": len(current_rows),
        "latest": latest,
        "customers": customers,
        "customerStats": customer_stats,
        "daily": daily_series,
        "slots": slot_stats,
        "current": current_rows,
        "screenedReadCount": len(screened_rows),
        "screenedLatest": screened_latest,
        "inputFeedSpikeCandidates": candidate_rows,
        "inputFeedSpikeCandidateCount": len(candidate_rows),
        "flaggedCount": flagged,
        "budgetFlaggedCount": budget_flagged,
        "missingReadMonths": missing_read_months,
        "missingReadCount": len(missing_read_months),
        "missingReadGaps": missing_read_gaps,
        "missingReadGapCount": len(missing_read_gaps),
        "historyStart": min((row["date"] for row in daily_series), default=""),
        "historyEnd": max((row["date"] for row in daily_series), default=""),
    }


def build_hourly_data(
    customer: str = "all",
    days: int | None = 90,
    repository: MeterDataRepository = REPOSITORY,
) -> list[dict]:
    """Return individual historical readings for the selected dashboard view."""
    rows = []
    for read in repository.history_reads():
        try:
            when = timestamp(read)
        except (ValueError, TypeError):
            continue
        if customer != "all" and read.customer_id != customer:
            continue
        rows.append({
            "customer": read.customer_id or "Unknown",
            "timestamp": when.strftime(DATE_FORMAT),
            "usage": number(read.usage_index),
        })
    if rows and days is not None:
        latest = max(datetime.strptime(row["timestamp"], DATE_FORMAT) for row in rows)
        start = latest - timedelta(days=days)
        rows = [row for row in rows if datetime.strptime(row["timestamp"], DATE_FORMAT) >= start]
    return rows


def build_investigation_preview(repository: MeterDataRepository = REPOSITORY) -> dict:
    """Return a non-mutating deterministic investigation preview.

    Persisting cases is intentionally kept in the trusted command-line job,
    not in a browser-request path. This route lets a future React case
    workspace inspect evidence before an associate workflow is introduced.
    """
    data = build_data(repository)
    source_run_id = CONFIG.analysis_run_id or "csv-analysis-unversioned"
    cases = generate_investigations(data["current"], data["missingReadGaps"], source_run_id)
    return investigation_payload(cases)


def build_feed_reference(repository: MeterDataRepository = REPOSITORY) -> dict:
    """Return only known customer/meter mappings needed by the intake form."""
    return feed_reference(repository)


def submit_feed_read(payload: dict, repository: MeterDataRepository = REPOSITORY) -> tuple[dict, int]:
    """Validate a form reading and persist only when the guarded feature is enabled."""
    if not CONFIG.feed_submissions_enabled:
        return {
            "error": "Feed submissions are disabled. An administrator must enable this protected workflow.",
            "code": "feed_submissions_disabled",
        }, 403
    try:
        submission = FeedSubmission.from_payload(payload)
        validate_submission(submission, repository)
        read = submission.meter_read()
        screening = screen_read(
            read,
            repository.historical_reads_for_slot(read, lookback_days=90),
        )
        if CONFIG.data_backend != "supabase":
            return receipt(submission, "validation_preview", screening), 200
        submission_id = SupabaseFeedStore(
            CONFIG.supabase_url or "", CONFIG.supabase_secret_key or ""
        ).save(submission, CONFIG.input_feed_batch_id, screening)
        response = receipt(submission, "supabase", screening, submission_id)
        if screening.spike_indicator:
            try:
                historical_boundary = repository.latest_historical_read_at(
                    submission.meter_id, submission.read_at
                )
                context = SupabaseInvestigationContext(
                    CONFIG.supabase_url or "", CONFIG.supabase_secret_key or "",
                    weather_enabled=CONFIG.weather_investigation_enabled,
                    premise_source_enabled=CONFIG.premise_source_enabled,
                    premise_source_base_url=CONFIG.premise_source_base_url,
                    premise_source_api_key=CONFIG.premise_source_api_key,
                    premise_source_name=CONFIG.premise_source_name,
                ).for_read(
                    submission.customer_id, submission.meter_id, submission.read_at,
                    historical_boundary,
                )
                candidate = {
                    **read.to_api_row(),
                    "usageNumber": float(read.usage_index),
                    "flag": "TRUE",
                    "readType": submission.read_type,
                    "baselineCount": screening.baseline_count,
                    "baselineMean": screening.baseline_mean,
                    "baselineStddev": screening.baseline_stddev,
                    "threshold": screening.threshold,
                    "reason": screening.reason,
                    **context,
                }
                source_run_id = f"input-feed-{submission_id.lower()}"
                cases = generate_investigations([candidate], [], source_run_id)
                SupabaseInvestigationStore(
                    CONFIG.supabase_url or "", CONFIG.supabase_secret_key or ""
                ).save(cases, source_run_id, create_tickets=True)
                response["autoInvestigation"] = {
                    "status": "ticket_created",
                    "caseId": cases[0].case_id,
                    "ticketId": f"TKT-{cases[0].case_id}",
                    "assignedTeam": cases[0].assigned_team,
                    "summary": cases[0].report_summary,
                }
            except (InvestigationContextError, InvestigationStoreError, IndexError):
                # The intake is already safely persisted. Never claim it failed and
                # trigger a duplicate form submission because a downstream evidence
                # source or ticket write needs recovery.
                response["autoInvestigation"] = {
                    "status": "recovery_required",
                    "message": "The spike is queued; the automatic investigation needs a server-side retry.",
                }
        return response, 201
    except FeedSubmissionError as error:
        return {"error": str(error), "code": "validation_failed"}, 422
    except FeedStorageError:
        return {"error": "The reading could not be saved. No result details were exposed to the browser.", "code": "storage_failed"}, 503


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, payload: object, status: int = 200) -> None:
        """Send an API response without treating a canceled browser request as a server error."""
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Data-Backend", CONFIG.data_backend)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.log_message("Browser canceled an API response before it completed")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            self.send_json(build_data())
            return
        if parsed.path == "/api/hourly":
            query = parse_qs(parsed.query)
            customer = query.get("customer", ["all"])[0]
            days_text = query.get("days", ["90"])[0]
            days = None if days_text == "all" else max(1, min(int(days_text), 3650))
            self.send_json(build_hourly_data(customer, days))
            return
        if parsed.path == "/api/investigations":
            self.send_json(build_investigation_preview())
            return
        if parsed.path == "/api/feed-reference":
            self.send_json(build_feed_reference())
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path in ("/", "/index.html"):
            self.path = "/dashboard.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/tickets/"):
            self.update_ticket(parsed.path)
            return
        if parsed.path != "/api/feed-submissions":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 10_000:
                raise ValueError
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "Submit one valid JSON reading."}, 400)
            return
        response, status = submit_feed_read(payload)
        body = json.dumps(response, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def update_ticket(self, path: str) -> None:
        ticket_id = path.removeprefix("/api/tickets/")
        if not CONFIG.data_backend == "supabase":
            self.send_json({"error": "Ticket editing requires the Supabase backend."}, 403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 14_000:
                raise ValueError
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            updated = SupabaseTicketWorkspace(
                CONFIG.supabase_url or "", CONFIG.supabase_secret_key or ""
            ).update(ticket_id, payload)
            self.send_json({"ticket": updated}, 200)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "Submit one valid ticket update."}, 400)
        except TicketWorkspaceError as error:
            self.send_json({"error": str(error)}, 422)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Meter usage dashboard: http://{args.host}:{args.port}")
    print(f"Data backend: {CONFIG.data_backend}")
    print("Press Ctrl+C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
