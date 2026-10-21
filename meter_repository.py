"""Data-source boundary for meter readings.

The dashboard currently reads local CSV files. Keeping that behavior behind this
small interface lets a future Supabase or Db2 implementation replace only the
repository, rather than the dashboard and analysis logic.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol, TypeAlias

from meter_models import MeterRead, SpikeResult


CsvRow: TypeAlias = dict[str, str]


class MeterDataRepository(Protocol):
    """Meter-data operations needed by the current dashboard."""

    def history_reads(self) -> list[MeterRead]: ...

    def current_reads(self) -> list[MeterRead]: ...

    def analysis_results(self) -> list[SpikeResult]: ...


class CsvMeterRepository:
    """Read the existing dashboard data files without changing their behavior."""

    def __init__(self, history_path: Path, current_path: Path, results_path: Path) -> None:
        self._history_path = history_path
        self._current_path = current_path
        self._results_path = results_path

    @staticmethod
    def _read_csv(path: Path) -> list[CsvRow]:
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as source:
            return list(csv.DictReader(source))

    def history_reads(self) -> list[MeterRead]:
        return [MeterRead.from_csv_row(row) for row in self._read_csv(self._history_path)]

    def current_reads(self) -> list[MeterRead]:
        return [MeterRead.from_csv_row(row) for row in self._read_csv(self._current_path)]

    def analysis_results(self) -> list[SpikeResult]:
        return [SpikeResult.from_csv_row(row) for row in self._read_csv(self._results_path)]
