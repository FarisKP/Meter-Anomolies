"""Server-side validation and controlled intake for four-hour meter readings."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from meter_models import MeterRead
from meter_repository import MeterDataRepository
from spike_screening import SpikeScreening


DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CADENCE_HOURS = 4


class FeedSubmissionError(ValueError):
    """An input-feed request is invalid or cannot be accepted."""


class FeedStorageError(RuntimeError):
    """A server-side Supabase write did not complete."""


@dataclass(frozen=True)
class FeedSubmission:
    customer_id: str
    meter_id: str
    read_at: str
    meter_status: str
    current_read: float
    previous_read: float
    usage_index: float
    read_type: str
    budget_indicator: str
    submitted_by: str
    source_reference: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FeedSubmission":
        def text(key: str) -> str:
            return str(payload.get(key, "")).strip()

        read_at_text = text("readAt").replace("T", " ")
        if len(read_at_text) == 16:
            read_at_text += ":00"
        try:
            read_at = datetime.strptime(read_at_text, DATE_FORMAT)
        except ValueError as error:
            raise FeedSubmissionError("Read timestamp must use a valid UTC date and time.") from error

        def decimal(key: str) -> float:
            try:
                value = float(payload.get(key))
            except (TypeError, ValueError) as error:
                raise FeedSubmissionError(f"{key} must be a valid number.") from error
            if not math.isfinite(value) or value < 0:
                raise FeedSubmissionError(f"{key} must be a non-negative number.")
            return value

        submission = cls(
            customer_id=text("customerId"),
            meter_id=text("meterId"),
            read_at=read_at.strftime(DATE_FORMAT),
            meter_status=text("meterStatus").lower(),
            current_read=decimal("currentRead"),
            previous_read=decimal("previousRead"),
            usage_index=decimal("usageIndex"),
            read_type=text("readType").lower(),
            budget_indicator=text("budgetIndicator").upper() or "N",
            submitted_by=text("submittedBy"),
            source_reference=text("sourceReference"),
        )
        required = {
            "customer": submission.customer_id,
            "meter": submission.meter_id,
            "meter status": submission.meter_status,
            "read type": submission.read_type,
            "submitted by": submission.submitted_by,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise FeedSubmissionError(f"Required field(s) missing: {', '.join(missing)}.")
        if submission.meter_status not in {"active", "inactive", "maintenance"}:
            raise FeedSubmissionError("meterStatus must be active, inactive, or maintenance.")
        if submission.read_type not in {"actual", "estimated"}:
            raise FeedSubmissionError("readType must be actual or estimated.")
        if submission.budget_indicator not in {"Y", "N"}:
            raise FeedSubmissionError("budgetIndicator must be Y or N.")
        if submission.current_read < submission.previous_read:
            raise FeedSubmissionError("currentRead cannot be lower than previousRead.")
        expected_usage_index = submission.current_read - submission.previous_read
        if not math.isclose(submission.usage_index, expected_usage_index, rel_tol=0, abs_tol=1e-6):
            raise FeedSubmissionError("usageIndex must equal currentRead minus previousRead.")
        if read_at.minute or read_at.second or read_at.hour % CADENCE_HOURS:
            raise FeedSubmissionError("Read timestamp must align to a four-hour UTC slot (00:00, 04:00, 08:00, etc.).")
        return submission

    def meter_read(self) -> MeterRead:
        return MeterRead(
            customer_id=self.customer_id,
            meter_number=self.meter_id,
            meter_status=self.meter_status,
            current_read=str(self.current_read),
            read_at=self.read_at,
            previous_read=str(self.previous_read),
            usage_index=str(self.usage_index),
            budget_indicator=self.budget_indicator,
        )


def feed_reference(repository: MeterDataRepository) -> dict[str, Any]:
    """Return canonical customer/meter pairs known to the active data source."""
    values = [
        {"customerId": customer, "meterId": meter}
        for customer, meter in repository.customer_meter_pairs()
    ]
    return {
        "cadenceHours": CADENCE_HOURS,
        "timestampConvention": "UTC",
        "pairs": values,
    }


def validate_submission(submission: FeedSubmission, repository: MeterDataRepository) -> None:
    if (submission.customer_id, submission.meter_id) not in set(repository.customer_meter_pairs()):
        raise FeedSubmissionError("The selected customer and meter are not a known active source mapping.")
    if repository.read_exists(submission.meter_read().key):
        raise FeedSubmissionError("A reading already exists for this meter and four-hour timestamp. Use the revision workflow, not a duplicate submission.")


def receipt(
    submission: FeedSubmission,
    persistence: str,
    screening: SpikeScreening,
    submission_id: str | None = None,
) -> dict[str, Any]:
    is_queued = persistence == "supabase" and screening.spike_indicator
    storage_target = (
        "meter_reads_temp" if is_queued else
        "input_feed_submissions" if persistence == "supabase" else
        "none"
    )
    candidate_message = (
        " It exceeded the deterministic threshold."
        if screening.spike_indicator else " It did not qualify for the spike-review queue."
    )
    return {
        "status": "accepted" if is_queued else "screened",
        "persistence": persistence,
        "storageTarget": storage_target,
        "submissionId": submission_id,
        "message": (
            "Reading accepted into the meter_reads_temp spike-review queue." + candidate_message
            if is_queued else
            "Reading was screened and retained in input_feed_submissions only; it was not added to meter_reads." + candidate_message
            if persistence == "supabase" else
            "Reading passed validation. CSV mode is preview-only and did not alter source files." + candidate_message
        ),
        "spikeScreening": screening.to_api(),
        "read": {
            "customerId": submission.customer_id,
            "meterId": submission.meter_id,
            "readAt": submission.read_at,
            "readType": submission.read_type,
            "cadenceHours": CADENCE_HOURS,
        },
    }


class SupabaseFeedStore:
    """Server-only writer for an explicit form submission."""

    _WRITE_TABLE_ALLOWLIST = frozenset({
        "ingest_batches",
        "meter_reads_temp",
        "input_feed_submissions",
    })

    def __init__(self, url: str, secret_key: str) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key

    def _request(self, target: str, *, data: list[dict[str, Any]] | None = None, method: str = "GET") -> Any:
        request = Request(
            target,
            data=json.dumps(data).encode("utf-8") if data is not None else None,
            method=method,
            headers={
                "apikey": self._secret_key,
                "Authorization": f"Bearer {self._secret_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as error:
            raise FeedStorageError(f"Supabase request failed with HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise FeedStorageError("Could not complete the Supabase feed submission.") from error

    def _upsert(self, table: str, rows: list[dict[str, Any]], conflict_columns: str) -> None:
        if table not in self._WRITE_TABLE_ALLOWLIST:
            raise FeedStorageError(
                f"Input-feed writes to {table!r} are blocked; the workflow never writes meter_reads."
            )
        target = f"{self._url}/rest/v1/{table}?{urlencode({'on_conflict': conflict_columns})}"
        self._request(target, data=rows, method="POST")

    def _ensure_batch(self, batch_id: str, now: str) -> None:
        query = urlencode({"select": "batch_id", "batch_id": f"eq.{batch_id}", "limit": "1"})
        existing = self._request(f"{self._url}/rest/v1/ingest_batches?{query}")
        if existing:
            return
        self._upsert("ingest_batches", [{
            "batch_id": batch_id,
            "source_name": "operator-four-hour-form",
            "imported_at": now,
            "record_count": 0,
        }], "batch_id")

    def save(self, submission: FeedSubmission, intake_batch_id: str, screening: SpikeScreening) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        submission_id = f"SUB-{uuid.uuid4().hex[:20].upper()}"
        read = submission.meter_read()
        read_id = hashlib.sha256("\x1f".join(read.key).encode("utf-8")).hexdigest()
        self._ensure_batch(intake_batch_id, now)
        meter_read_row = {
            "read_id": read_id,
            "meter_id": read.meter_number,
            "read_at": datetime.strptime(read.read_at, DATE_FORMAT).strftime("%Y-%m-%dT%H:%M:%S"),
            "meter_status": read.meter_status,
            "current_read": submission.current_read,
            "previous_read": submission.previous_read,
            "usage_index": submission.usage_index,
            "budget_indicator": submission.budget_indicator,
            "read_type": submission.read_type,
            "slot_hour": datetime.strptime(read.read_at, DATE_FORMAT).hour,
            "batch_id": intake_batch_id,
        }
        if screening.spike_indicator:
            self._upsert("meter_reads_temp", [{
                **meter_read_row,
                "spike_indicator": True,
            }], "read_id")
        self._upsert("input_feed_submissions", [{
            "submission_id": submission_id,
            "read_id": read_id if screening.spike_indicator else None,
            "batch_id": intake_batch_id,
            "customer_id": submission.customer_id,
            "meter_id": submission.meter_id,
            "read_at": datetime.strptime(read.read_at, DATE_FORMAT).strftime("%Y-%m-%dT%H:%M:%S"),
            "read_type": submission.read_type,
            "submitted_by": submission.submitted_by,
            "source_reference": submission.source_reference or None,
            "validation_status": "accepted_spike_candidate" if screening.spike_indicator else f"screened_{screening.status.lower()}",
            "validation_json": json.dumps({
                "cadence_hours": CADENCE_HOURS,
                "timestamp_convention": "UTC",
                "spike_screening": screening.to_api(),
            }),
            "submitted_at": now,
        }], "submission_id")
        return submission_id
