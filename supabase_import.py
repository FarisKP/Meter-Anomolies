#!/usr/bin/env python3
"""Import the validated CSV dataset into Supabase.

The command is deliberately a dry run unless ``--apply`` is present.  It uses
the server-only ``SUPABASE_SECRET_KEY`` environment variable and sends data
through Supabase's REST API in idempotent upsert batches.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from import_meter_csv import TIMESTAMP_FORMAT, build_manifest, load_reads, read_id
from meter_models import MeterRead, SpikeResult


RESULT_COLUMNS = {
    "cust-id",
    "meter-num",
    "current-meter-read-timestamp",
    "baseline-count",
    "baseline-mean",
    "baseline-stddev",
    "spike-threshold",
    "spike-flag",
    "flag-reason",
}
DEFAULT_HISTORY_BATCH = "history-csv-initial"
DEFAULT_CURRENT_BATCH = "current-csv-initial"
DEFAULT_RUN_ID = "csv-analysis-initial"
WRITE_BATCH_SIZE = 500


class SupabaseImportError(RuntimeError):
    """Raised for an invalid import plan or an unsuccessful API write."""


@dataclass(frozen=True)
class ImportPlan:
    history: list[MeterRead]
    current: list[MeterRead]
    results: list[SpikeResult]
    history_batch_id: str
    current_batch_id: str
    run_id: str
    history_source_name: str
    current_source_name: str

    @property
    def reads(self) -> list[MeterRead]:
        return self.history + self.current


def load_results(path: Path) -> list[SpikeResult]:
    """Load analysis output and ensure every record has a stable identity."""
    with path.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = RESULT_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise SupabaseImportError(
                f"{path.name}: missing required result columns: {', '.join(sorted(missing))}"
            )
        results = [SpikeResult.from_csv_row(row) for row in reader]

    if not results:
        raise SupabaseImportError(f"{path.name}: contains no analysis results")
    duplicates = [key for key, count in Counter(result.key for result in results).items() if count > 1]
    if duplicates:
        raise SupabaseImportError(f"{path.name}: contains {len(duplicates)} duplicate result key(s)")
    if any(not all(result.key) for result in results):
        raise SupabaseImportError(f"{path.name}: contains a result with a blank customer, meter, or timestamp")
    return results


def build_plan(
    history: list[MeterRead],
    current: list[MeterRead],
    results: list[SpikeResult],
    history_batch_id: str,
    current_batch_id: str,
    run_id: str,
    history_source_name: str = "meter_usage_5cust_3years (1).csv",
    current_source_name: str = "simulated_current_meter_usage.csv",
) -> ImportPlan:
    """Validate cross-file relationships required by the relational schema."""
    build_manifest(history, current)  # Validates duplicate read keys and overlap.
    if not history_batch_id or not current_batch_id or not run_id:
        raise SupabaseImportError("Batch IDs and run ID must not be blank.")
    if history_batch_id == current_batch_id:
        raise SupabaseImportError("History and current batch IDs must be different.")

    meter_customers: dict[str, str] = {}
    for read in history + current:
        previous_customer = meter_customers.setdefault(read.meter_number, read.customer_id)
        if previous_customer != read.customer_id:
            raise SupabaseImportError(
                f"Meter {read.meter_number!r} belongs to both {previous_customer!r} and "
                f"{read.customer_id!r}; the current schema requires one customer per meter."
            )

    current_keys = {read.key for read in current}
    unmatched_results = [result.key for result in results if result.key not in current_keys]
    if unmatched_results:
        raise SupabaseImportError(
            f"{len(unmatched_results)} result row(s) do not match a current-read row. "
            "Regenerate the analysis results before importing."
        )
    return ImportPlan(
        history,
        current,
        results,
        history_batch_id,
        current_batch_id,
        run_id,
        history_source_name,
        current_source_name,
    )


def numeric(value: str, field: str, key: tuple[str, str, str], nullable: bool = False) -> float | None:
    if not value.strip() and nullable:
        return None
    try:
        number = float(value)
    except ValueError as error:
        raise SupabaseImportError(f"Invalid {field} for read {key}: {value!r}") from error
    if number != number or number in (float("inf"), float("-inf")):
        raise SupabaseImportError(f"Invalid {field} for read {key}: {value!r}")
    return number


def database_timestamp(value: str) -> str:
    return datetime.strptime(value, TIMESTAMP_FORMAT).strftime("%Y-%m-%dT%H:%M:%S")


def meter_read_rows(reads: Iterable[MeterRead], batch_id: str) -> list[dict[str, Any]]:
    rows = []
    for read in reads:
        rows.append(
            {
                "read_id": read_id(read),
                "meter_id": read.meter_number,
                "read_at": database_timestamp(read.read_at),
                "meter_status": read.meter_status,
                "current_read": numeric(read.current_read, "current_read", read.key),
                "previous_read": numeric(read.previous_read, "previous_read", read.key),
                "usage_index": numeric(read.usage_index, "usage_index", read.key),
                "budget_indicator": read.budget_indicator or None,
                "slot_hour": datetime.strptime(read.read_at, TIMESTAMP_FORMAT).hour,
                "batch_id": batch_id,
            }
        )
    return rows


def spike_result_rows(plan: ImportPlan) -> list[dict[str, Any]]:
    reads_by_key = {read.key: read for read in plan.current}
    rows = []
    for result in plan.results:
        read = reads_by_key[result.key]
        try:
            baseline_count = int(result.baseline_count)
        except ValueError as error:
            raise SupabaseImportError(
                f"Invalid baseline_count for result {result.key}: {result.baseline_count!r}"
            ) from error
        rows.append(
            {
                "run_id": plan.run_id,
                "read_id": read_id(read),
                "baseline_count": baseline_count,
                "baseline_mean": numeric(result.baseline_mean, "baseline_mean", result.key, True),
                "baseline_stddev": numeric(result.baseline_stddev, "baseline_stddev", result.key, True),
                "spike_threshold": numeric(result.threshold, "spike_threshold", result.key, True),
                "spike_flag": result.flag,
                "flag_reason": result.reason,
            }
        )
    return rows


def import_summary(plan: ImportPlan) -> dict[str, Any]:
    return {
        "historyReads": len(plan.history),
        "currentReads": len(plan.current),
        "analysisResults": len(plan.results),
        "customers": len({read.customer_id for read in plan.reads}),
        "meters": len({read.meter_number for read in plan.reads}),
        "historyBatchId": plan.history_batch_id,
        "currentBatchId": plan.current_batch_id,
        "analysisRunId": plan.run_id,
    }


class SupabaseWriter:
    """Small REST writer with table-specific, conflict-safe upserts."""

    def __init__(self, url: str, secret_key: str) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key

    def upsert(self, table: str, rows: list[dict[str, Any]], conflict_columns: str) -> None:
        for start in range(0, len(rows), WRITE_BATCH_SIZE):
            page = rows[start : start + WRITE_BATCH_SIZE]
            target = f"{self._url}/rest/v1/{table}?{urlencode({'on_conflict': conflict_columns})}"
            request = Request(
                target,
                data=json.dumps(page).encode("utf-8"),
                method="POST",
                headers={
                    "apikey": self._secret_key,
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
            )
            try:
                with urlopen(request, timeout=30):
                    pass
            except HTTPError as error:
                raise SupabaseImportError(
                    f"Supabase upsert into {table} failed with HTTP {error.code}."
                ) from error
            except (URLError, TimeoutError) as error:
                raise SupabaseImportError(f"Could not write {table} to Supabase.") from error


def apply_plan(writer: SupabaseWriter, plan: ImportPlan, executed_at: str) -> None:
    """Write parents before children so foreign-key checks always hold."""
    all_reads = plan.reads
    writer.upsert(
        "ingest_batches",
        [
            {
                "batch_id": plan.history_batch_id,
                "source_name": plan.history_source_name,
                "imported_at": executed_at,
                "record_count": len(plan.history),
            },
            {
                "batch_id": plan.current_batch_id,
                "source_name": plan.current_source_name,
                "imported_at": executed_at,
                "record_count": len(plan.current),
            },
        ],
        "batch_id",
    )
    writer.upsert(
        "customers",
        [{"customer_id": customer_id} for customer_id in sorted({read.customer_id for read in all_reads})],
        "customer_id",
    )
    meter_customers = {read.meter_number: read.customer_id for read in all_reads}
    writer.upsert(
        "meters",
        [
            {"meter_id": meter_id, "customer_id": customer_id}
            for meter_id, customer_id in sorted(meter_customers.items())
        ],
        "meter_id",
    )
    writer.upsert("meter_reads", meter_read_rows(plan.history, plan.history_batch_id), "read_id")
    writer.upsert("meter_reads", meter_read_rows(plan.current, plan.current_batch_id), "read_id")
    writer.upsert(
        "analysis_runs",
        [
            {
                "run_id": plan.run_id,
                "executed_at": executed_at,
                "lookback_days": 90,
                "sigma": 3.0,
                "min_history": 12,
                "algorithm_version": "csv-prototype-v1",
            }
        ],
        "run_id",
    )
    writer.upsert("spike_results", spike_result_rows(plan), "run_id,read_id")


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=root / "meter_usage_5cust_3years (1).csv")
    parser.add_argument("--current", type=Path, default=root / "simulated_current_meter_usage.csv")
    parser.add_argument("--results", type=Path, default=root / "usage_spike_results.csv")
    parser.add_argument("--history-batch-id", default=os.getenv("SUPABASE_HISTORY_BATCH_ID", DEFAULT_HISTORY_BATCH))
    parser.add_argument("--current-batch-id", default=os.getenv("SUPABASE_CURRENT_BATCH_ID", DEFAULT_CURRENT_BATCH))
    parser.add_argument("--run-id", default=os.getenv("SUPABASE_ANALYSIS_RUN_ID", DEFAULT_RUN_ID))
    parser.add_argument("--apply", action="store_true", help="Write the plan to Supabase; otherwise print a dry-run summary")
    parser.add_argument("--json", action="store_true", help="Print the plan summary as JSON")
    args = parser.parse_args()

    try:
        plan = build_plan(
            load_reads(args.history),
            load_reads(args.current),
            load_results(args.results),
            args.history_batch_id,
            args.current_batch_id,
            args.run_id,
            args.history.name,
            args.current.name,
        )
        summary = import_summary(plan)
        if not args.apply:
            summary["status"] = "dry-run-ready"
            print(json.dumps(summary, indent=2) if args.json else "Dry run passed; add --apply to write to Supabase.\n" + "\n".join(f"{key}: {value}" for key, value in summary.items()))
            return

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SECRET_KEY")
        if not url or not key:
            raise SupabaseImportError("--apply requires SUPABASE_URL and SUPABASE_SECRET_KEY.")
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        apply_plan(SupabaseWriter(url, key), plan, executed_at)
    except (OSError, ValueError, SupabaseImportError) as error:
        parser.error(str(error))

    summary["status"] = "imported"
    print(json.dumps(summary, indent=2) if args.json else "Supabase import completed. Run verify_supabase_import.py next.")


if __name__ == "__main__":
    main()
