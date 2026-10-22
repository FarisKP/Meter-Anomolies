"""Deterministic screening for one validated input-feed meter reading.

This keeps the intake path aligned with the existing CSV prototype: compare a
reading only with the same customer's meter at the same four-hour slot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from meter_models import MeterRead


DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOOKBACK_DAYS = 90
SIGMA = 3.0
MIN_HISTORY = 30


@dataclass(frozen=True)
class SpikeScreening:
    """The explainable outcome of screening one new feed reading."""

    spike_indicator: bool
    status: str
    baseline_count: int
    baseline_mean: float | None
    baseline_stddev: float | None
    threshold: float | None
    reason: str

    def to_api(self) -> dict[str, object]:
        return {
            "spikeIndicator": self.spike_indicator,
            "status": self.status,
            "baselineCount": self.baseline_count,
            "baselineMean": self.baseline_mean,
            "baselineStddev": self.baseline_stddev,
            "threshold": self.threshold,
            "reason": self.reason,
            "lookbackDays": LOOKBACK_DAYS,
            "minHistory": MIN_HISTORY,
            "sigma": SIGMA,
        }


def screen_read(read: MeterRead, historical_reads: Iterable[MeterRead]) -> SpikeScreening:
    """Apply the existing same-slot statistical rule without mutating data."""
    read_at = datetime.strptime(read.read_at, DATE_FORMAT)
    start = read_at - timedelta(days=LOOKBACK_DAYS)
    matching: list[float] = []

    for historical in historical_reads:
        if historical.customer_id != read.customer_id or historical.meter_number != read.meter_number:
            continue
        try:
            historical_at = datetime.strptime(historical.read_at, DATE_FORMAT)
            usage = float(historical.usage_index)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(usage):
            continue
        if historical_at.hour == read_at.hour and historical_at.minute == read_at.minute and start <= historical_at < read_at:
            matching.append(usage)

    if len(matching) < MIN_HISTORY:
        return SpikeScreening(
            spike_indicator=False,
            status="INSUFFICIENT_HISTORY",
            baseline_count=len(matching),
            baseline_mean=None,
            baseline_stddev=None,
            threshold=None,
            reason=f"Need {MIN_HISTORY} matching historical readings; found {len(matching)}.",
        )

    mean = sum(matching) / len(matching)
    stddev = math.sqrt(sum((value - mean) ** 2 for value in matching) / len(matching))
    threshold = mean + SIGMA * stddev
    usage = float(read.usage_index)
    is_spike = usage > threshold
    return SpikeScreening(
        spike_indicator=is_spike,
        status="TRUE" if is_spike else "FALSE",
        baseline_count=len(matching),
        baseline_mean=mean,
        baseline_stddev=stddev,
        threshold=threshold,
        reason=(
            f"Usage {usage:g} exceeds same-slot threshold {threshold:.4f}."
            if is_spike else
            f"Usage {usage:g} is within same-slot threshold {threshold:.4f}."
        ),
    )
