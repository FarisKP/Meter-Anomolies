#!/usr/bin/env python3
"""Compare the CSV source dataset with the configured Supabase dataset."""

from __future__ import annotations

import argparse
import os
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app_config import AppConfig
from meter_repository import CsvMeterRepository
from repository_factory import create_repository


def normal_decimal(value: str) -> Decimal | None:
    if not value.strip():
        return None
    try:
        return Decimal(value).normalize()
    except InvalidOperation as error:
        raise ValueError(f"Invalid numeric result value: {value!r}") from error


def compare(name: str, expected: Counter, actual: Counter) -> list[str]:
    if expected == actual:
        return []
    missing = sum((expected - actual).values())
    unexpected = sum((actual - expected).values())
    return [f"{name}: {missing} missing and {unexpected} unexpected record(s)"]


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=root / "meter_usage_5cust_3years (1).csv")
    parser.add_argument("--current", type=Path, default=root / "simulated_current_meter_usage.csv")
    parser.add_argument("--results", type=Path, default=root / "usage_spike_results.csv")
    parser.add_argument("--run-id", default=os.getenv("SUPABASE_ANALYSIS_RUN_ID", "csv-analysis-initial"))
    args = parser.parse_args()

    environment = dict(os.environ)
    environment["DATA_BACKEND"] = "supabase"
    environment["SUPABASE_ANALYSIS_RUN_ID"] = args.run_id
    try:
        config = AppConfig.from_environment(root, environment)
        csv_data = CsvMeterRepository(args.history, args.current, args.results)
        database = create_repository(config)
        expected_history = Counter(read.key for read in csv_data.history_reads())
        expected_current = Counter(read.key for read in csv_data.current_reads())
        expected_results = Counter(
            (result.key, result.flag, normal_decimal(result.threshold))
            for result in csv_data.analysis_results()
        )
        actual_history = Counter(read.key for read in database.history_reads())
        actual_current = Counter(read.key for read in database.current_reads())
        actual_results = Counter(
            (result.key, result.flag, normal_decimal(result.threshold))
            for result in database.analysis_results()
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))

    problems = []
    problems += compare("history reads", expected_history, actual_history)
    problems += compare("current reads", expected_current, actual_current)
    problems += compare("analysis results (key, flag, threshold)", expected_results, actual_results)
    if problems:
        parser.error("Supabase verification failed: " + "; ".join(problems))
    print(
        "Supabase verification passed: "
        f"{len(expected_history)} history reads, {len(expected_current)} current reads, "
        f"and {len(expected_results)} analysis results match the CSV source."
    )


if __name__ == "__main__":
    main()
