"""Data-source boundary for meter readings.

The dashboard currently reads local CSV files. Keeping that behavior behind this
small interface lets a future Supabase or Db2 implementation replace only the
repository, rather than the dashboard and analysis logic.
"""

from __future__ import annotations

import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import Protocol, TypeAlias

from meter_models import MeterRead, ReadKey, SpikeResult


CsvRow: TypeAlias = dict[str, str]


class MeterDataRepository(Protocol):
    """Meter-data operations needed by the current dashboard."""

    def history_reads(self) -> list[MeterRead]: ...

    def current_reads(self) -> list[MeterRead]: ...

    def analysis_results(self) -> list[SpikeResult]: ...

    def customer_meter_pairs(self) -> list[tuple[str, str]]: ...

    def read_exists(self, key: ReadKey) -> bool: ...

    def historical_reads_for_slot(self, read: MeterRead, lookback_days: int) -> list[MeterRead]: ...

    def latest_historical_read_at(self, meter_id: str, before_read_at: str) -> str | None: ...

    def input_feed_spike_candidates(self) -> list[MeterRead]: ...

    def input_feed_spike_candidate_evidence(self) -> dict[ReadKey, dict[str, object]]: ...

    def input_feed_investigations(self) -> dict[ReadKey, dict[str, object]]: ...


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

    def customer_meter_pairs(self) -> list[tuple[str, str]]:
        return sorted({
            (read.customer_id, read.meter_number)
            for read in self.history_reads() + self.current_reads()
            if read.customer_id and read.meter_number
        })

    def read_exists(self, key: ReadKey) -> bool:
        return any(read.key == key for read in self.history_reads() + self.current_reads())

    def historical_reads_for_slot(self, read: MeterRead, lookback_days: int) -> list[MeterRead]:
        target = datetime.strptime(read.read_at, "%Y-%m-%d %H:%M:%S")
        start = target - timedelta(days=lookback_days)
        return [
            historical for historical in self.history_reads()
            if historical.customer_id == read.customer_id
            and historical.meter_number == read.meter_number
            and start <= datetime.strptime(historical.read_at, "%Y-%m-%d %H:%M:%S") < target
            and datetime.strptime(historical.read_at, "%Y-%m-%d %H:%M:%S").hour == target.hour
        ]

    def latest_historical_read_at(self, meter_id: str, before_read_at: str) -> str | None:
        """Return the historical interval boundary for a weather investigation."""
        target = datetime.strptime(before_read_at, "%Y-%m-%d %H:%M:%S")
        reads = [
            read for read in self.history_reads()
            if read.meter_number == meter_id
            and datetime.strptime(read.read_at, "%Y-%m-%d %H:%M:%S") < target
        ]
        return max(reads, key=lambda read: read.read_at).read_at if reads else None

    def input_feed_spike_candidates(self) -> list[MeterRead]:
        # CSV mode is deliberately non-mutating, so it has no persisted queue.
        return []

    def input_feed_spike_candidate_evidence(self) -> dict[ReadKey, dict[str, object]]:
        return {}

    def input_feed_investigations(self) -> dict[ReadKey, dict[str, object]]:
        return {}
