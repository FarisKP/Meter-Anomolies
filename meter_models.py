"""Domain records shared by the dashboard, analyzer, and future data stores.

The records deliberately retain the CSV values as strings in this step. That
preserves the dashboard's existing tolerant parsing behavior; validation and
database-specific conversions will be added separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


CsvRow = Mapping[str, str]
ReadKey = tuple[str, str, str]


@dataclass(frozen=True)
class MeterRead:
    customer_id: str
    meter_number: str
    meter_status: str
    current_read: str
    read_at: str
    previous_read: str
    usage_index: str
    budget_indicator: str

    @classmethod
    def from_csv_row(cls, row: CsvRow) -> "MeterRead":
        return cls(
            customer_id=row.get("cust-id", ""),
            meter_number=row.get("meter-num", ""),
            meter_status=row.get("meter-status", ""),
            current_read=row.get("current-meter-read", ""),
            read_at=row.get("current-meter-read-timestamp", ""),
            previous_read=row.get("previous-meter-read", ""),
            usage_index=row.get("usage-index", ""),
            budget_indicator=row.get("budget indicator", ""),
        )

    @property
    def key(self) -> ReadKey:
        return self.customer_id, self.meter_number, self.read_at

    def to_api_row(self) -> dict[str, str]:
        """Keep the browser API field names stable during the migration."""
        return {
            "cust-id": self.customer_id,
            "meter-num": self.meter_number,
            "meter-status": self.meter_status,
            "current-meter-read": self.current_read,
            "current-meter-read-timestamp": self.read_at,
            "previous-meter-read": self.previous_read,
            "usage-index": self.usage_index,
            "budget indicator": self.budget_indicator,
        }


@dataclass(frozen=True)
class SpikeResult:
    customer_id: str
    meter_number: str
    read_at: str
    baseline_count: str
    baseline_mean: str
    baseline_stddev: str
    threshold: str
    flag: str
    reason: str

    @classmethod
    def from_csv_row(cls, row: CsvRow) -> "SpikeResult":
        return cls(
            customer_id=row.get("cust-id", ""),
            meter_number=row.get("meter-num", ""),
            read_at=row.get("current-meter-read-timestamp", ""),
            baseline_count=row.get("baseline-count", ""),
            baseline_mean=row.get("baseline-mean", ""),
            baseline_stddev=row.get("baseline-stddev", ""),
            threshold=row.get("spike-threshold", ""),
            flag=row.get("spike-flag", ""),
            reason=row.get("flag-reason", ""),
        )

    @property
    def key(self) -> ReadKey:
        return self.customer_id, self.meter_number, self.read_at
