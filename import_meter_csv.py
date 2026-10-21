#!/usr/bin/env python3
"""Validate and plan the initial CSV-to-database import.

This command intentionally does not connect to a database. It produces a
deterministic manifest that the Supabase and Db2 import adapters will consume
in later steps.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from meter_models import MeterRead


TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
REQUIRED_COLUMNS = {
    "cust-id",
    "meter-num",
    "meter-status",
    "current-meter-read",
    "current-meter-read-timestamp",
    "previous-meter-read",
    "usage-index",
}


def read_id(read: MeterRead) -> str:
    """Create the stable identifier used by both database implementations."""
    value = "\x1f".join(read.key).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def load_reads(path: Path) -> list[MeterRead]:
    with path.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(f"{path.name}: missing required columns: {', '.join(sorted(missing))}")
        reads = [MeterRead.from_csv_row(row) for row in reader]

    if not reads:
        raise ValueError(f"{path.name}: contains no reads")

    for row_number, read in enumerate(reads, start=2):
        if not all(read.key):
            raise ValueError(f"{path.name}: row {row_number} has a blank customer, meter, or timestamp")
        try:
            datetime.strptime(read.read_at, TIMESTAMP_FORMAT)
        except ValueError as error:
            raise ValueError(
                f"{path.name}: row {row_number} has invalid timestamp {read.read_at!r}"
            ) from error
    return reads


def duplicate_keys(reads: list[MeterRead]) -> list[tuple[str, str, str]]:
    counts = Counter(read.key for read in reads)
    return sorted(key for key, count in counts.items() if count > 1)


def build_manifest(history: list[MeterRead], current: list[MeterRead]) -> dict:
    history_duplicates = duplicate_keys(history)
    current_duplicates = duplicate_keys(current)
    overlap = sorted({read.key for read in history} & {read.key for read in current})
    if history_duplicates or current_duplicates or overlap:
        problems = []
        if history_duplicates:
            problems.append(f"{len(history_duplicates)} duplicate history key(s)")
        if current_duplicates:
            problems.append(f"{len(current_duplicates)} duplicate current key(s)")
        if overlap:
            problems.append(f"{len(overlap)} key(s) appear in both files")
        raise ValueError("Import cannot continue: " + "; ".join(problems))

    all_reads = history + current
    return {
        "historyReads": len(history),
        "currentReads": len(current),
        "totalReads": len(all_reads),
        "customers": len({read.customer_id for read in all_reads}),
        "meters": len({read.meter_number for read in all_reads}),
        "historyBatchId": "history-csv-initial",
        "currentBatchId": "current-csv-initial",
        "readIdExample": read_id(all_reads[0]),
        "status": "ready-for-database-import",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True, help="Historical meter-read CSV")
    parser.add_argument("--current", type=Path, required=True, help="Current meter-read CSV")
    parser.add_argument("--json", action="store_true", help="Print the import manifest as JSON")
    args = parser.parse_args()

    try:
        manifest = build_manifest(load_reads(args.history), load_reads(args.current))
    except (OSError, ValueError) as error:
        parser.error(str(error))

    if args.json:
        print(json.dumps(manifest, indent=2))
        return

    print("CSV import preflight passed")
    for label, value in manifest.items():
        print(f"{label}: {value}")


if __name__ == "__main__":
    main()
