"""Deterministic, explainable usage-spike investigation planning.

This module deliberately has no database or web dependencies.  Given the
existing dashboard rows it creates reproducible investigation cases and a
record of every check performed.  It is the first stage of the investigation
state machine, not a root-cause classifier and not a customer-contact tool.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable


DATA_CONTRACT_VERSION = "1.0"
ENGINE_VERSION = "deterministic-spike-v1"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class InvestigationEvidence:
    check_code: str
    outcome: str
    summary: str
    values: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvestigationCase:
    case_id: str
    case_key: str
    customer_id: str
    meter_id: str
    trigger_read_at: str
    trigger_usage: float | None
    baseline_mean: float | None
    threshold: float | None
    severity: str
    state: str
    recommended_action: str
    source_run_id: str
    state_path: tuple[str, ...]
    evidence: tuple[InvestigationEvidence, ...]
    assigned_team: str = ""
    possible_cause: str = ""
    report_summary: str = ""
    detailed_report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "state_path": list(self.state_path),
            "evidence": [item.to_dict() for item in self.evidence],
            "data_contract_version": DATA_CONTRACT_VERSION,
            "engine_version": ENGINE_VERSION,
        }


def _finite_number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _case_identity(customer_id: str, meter_id: str, read_at: str) -> tuple[str, str]:
    case_key = f"usage-spike:{customer_id}:{meter_id}:{read_at}"
    digest = hashlib.sha256(case_key.encode("utf-8")).hexdigest()[:16].upper()
    return f"USG-{digest}", case_key


def _severity(usage: float, threshold: float) -> str:
    ratio = usage / threshold if threshold > 0 else 1.0
    if ratio >= 2:
        return "critical"
    if ratio >= 1.5:
        return "high"
    return "medium"


def _read_type(row: dict[str, Any]) -> str:
    return str(row.get("readType", row.get("read_type", "actual"))).strip().lower() or "actual"


def _event_rows(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _weather_evidence(weather: object) -> InvestigationEvidence:
    if not isinstance(weather, dict) or not weather.get("available"):
        return InvestigationEvidence(
            "weather", "data_unavailable",
            "No approved weather observations are available from the latest historical meter read through the incoming meter-read time.",
            {"provider": None, "reason": "premise location or weather snapshots unavailable"},
        )
    apparent = _finite_number(weather.get("apparentTemperatureC"))
    temperature = _finite_number(weather.get("temperatureC"))
    measured = apparent if apparent is not None else temperature
    if measured is None:
        return InvestigationEvidence(
            "weather", "data_unavailable",
            "The weather source returned no usable temperature observation at the incoming meter-read time.",
            {"provider": weather.get("provider")},
        )
    condition = "extreme_heat" if measured >= 32 else "extreme_cold" if measured <= 0 else "normal_range"
    outcome = "finding" if condition != "normal_range" else "pass"
    range_start = weather.get("rangeStart")
    range_end = weather.get("rangeEnd")
    sample_count = _finite_number(weather.get("sampleCount"))
    interval = (
        f" Weather was evaluated from {range_start} through {range_end} across {int(sample_count)} hourly observation(s)."
        if range_start and range_end and sample_count is not None else ""
    )
    summary = (
        f"{condition.replace('_', ' ').title()} was observed at the premise ({measured:.1f}°C apparent/air temperature); weather may contribute to demand."
        if outcome == "finding" else
        f"Observed premise temperature was {measured:.1f}°C; this screen found no configured extreme-temperature condition."
    )
    summary += interval
    return InvestigationEvidence("weather", outcome, summary, {
        "provider": weather.get("provider"),
        "observed_at": weather.get("observedAt"),
        "temperature_c": temperature,
        "apparent_temperature_c": apparent,
        "condition": condition,
        "range_start": range_start,
        "range_end": range_end,
        "sample_count": int(sample_count) if sample_count is not None else None,
        "min_apparent_temperature_c": _finite_number(weather.get("minApparentTemperatureC")),
        "max_apparent_temperature_c": _finite_number(weather.get("maxApparentTemperatureC")),
        "extreme_heat_hours": _finite_number(weather.get("extremeHeatHours")),
        "extreme_cold_hours": _finite_number(weather.get("extremeColdHours")),
    })


def _assign_team(read_type: str, meter_status: str, weather: InvestigationEvidence) -> str:
    if read_type == "estimated":
        return "Billing Resolution"
    if meter_status in {"inactive", "maintenance"}:
        return "Meter Operations"
    # Weather can be contributory but does not override a confirmed interval anomaly.
    return "Meter Operations"


def _gap_affects_read(gap: dict[str, Any], read_at: str) -> bool:
    """Return true only when a known gap touches the trigger's four-hour slot."""
    try:
        trigger = datetime.strptime(read_at, DATE_FORMAT)
        start = datetime.strptime(str(gap["start"]), DATE_FORMAT)
        end = datetime.strptime(str(gap["end"]), DATE_FORMAT)
    except (KeyError, TypeError, ValueError):
        return False
    return start - timedelta_hours(4) <= trigger <= end + timedelta_hours(4)


def _detailed_report(
    usage: float,
    baseline: float | None,
    threshold: float,
    evidence: list[InvestigationEvidence],
    assigned_team: str,
) -> str:
    """Produce a traceable narrative only from retained deterministic evidence."""
    baseline_text = f" The comparable same-slot mean was {baseline:.2f}." if baseline is not None else ""
    finding_lines = [
        f"- {item.check_code.replace('_', ' ').title()}: {item.summary}"
        for item in evidence if item.outcome == "finding"
    ]
    available_lines = [
        f"- {item.check_code.replace('_', ' ').title()}: {item.summary}"
        for item in evidence if item.outcome == "pass"
    ]
    report = (
        f"Trigger assessment\nUsage of {usage:.2f} exceeded the deterministic same-slot threshold of {threshold:.2f}."
        f"{baseline_text}\n\nEvidence requiring investigation\n"
        f"{'\n'.join(finding_lines) if finding_lines else '- No additional findings were produced.'}"
        f"\n\nEvidence reviewed and available\n"
        f"{'\n'.join(available_lines) if available_lines else '- No supporting sources were available.'}"
        f"\n\nRouting\nThis case is assigned to {assigned_team}. Associate validation is required before any customer contact."
    )
    return report


def timedelta_hours(hours: int):
    """Kept small and explicit to make time-window logic easy to audit."""
    from datetime import timedelta

    return timedelta(hours=hours)


def generate_investigations(
    current_rows: Iterable[dict[str, Any]],
    missing_read_gaps: Iterable[dict[str, Any]],
    source_run_id: str = "unversioned-source",
) -> list[InvestigationCase]:
    """Generate only reviewable spike cases from already-analysed current reads.

    The decision graph is deterministic but branches based on evidence:
    invalid inputs reach ``data_unavailable``; otherwise a threshold breach is
    checked for continuity concerns before reaching ``review_required``.
    """
    gaps_by_customer: dict[str, list[dict[str, Any]]] = {}
    for gap in missing_read_gaps:
        customer = str(gap.get("customer", ""))
        gaps_by_customer.setdefault(customer, []).append(gap)

    cases: list[InvestigationCase] = []
    for row in current_rows:
        if str(row.get("flag", "")).upper() != "TRUE":
            continue

        customer_id = str(row.get("cust-id", "")).strip()
        meter_id = str(row.get("meter-num", "")).strip()
        read_at = str(row.get("current-meter-read-timestamp", "")).strip()
        usage = _finite_number(row.get("usageNumber", row.get("usage-index")))
        baseline = _finite_number(row.get("baselineMean"))
        threshold = _finite_number(row.get("threshold"))
        case_id, case_key = _case_identity(customer_id or "unknown", meter_id or "unknown", read_at or "unknown")

        required_missing = [
            name for name, value in {
                "customer_id": customer_id,
                "meter_id": meter_id,
                "read_at": read_at,
                "usage": usage,
                "threshold": threshold,
            }.items() if value in ("", None)
        ]
        evidence = [
            InvestigationEvidence(
                "input_integrity",
                "pass" if not required_missing else "data_unavailable",
                "Required spike-investigation fields are available."
                if not required_missing
                else f"Missing required fields: {', '.join(required_missing)}.",
                {"missing_fields": required_missing},
            )
        ]
        if required_missing:
            cases.append(InvestigationCase(
                case_id, case_key, customer_id, meter_id, read_at, usage, baseline, threshold,
                "medium", "data_unavailable",
                "Restore the required meter-reading and baseline fields, then rerun the investigation.",
                source_run_id, ("spike_detected", "validate_input", "data_unavailable"), tuple(evidence),
            ))
            continue

        assert usage is not None and threshold is not None
        evidence.append(InvestigationEvidence(
            "historical_baseline",
            "finding",
            "Current usage exceeds the same-slot historical threshold.",
            {
                "usage": usage,
                "baseline_mean": baseline,
                "threshold": threshold,
                "percent_above_threshold": round(((usage - threshold) / threshold) * 100, 2) if threshold else None,
                "analysis_reason": str(row.get("reason", "")),
            },
        ))
        related_gaps = [
            gap for gap in gaps_by_customer.get(customer_id, []) if _gap_affects_read(gap, read_at)
        ]
        evidence.append(InvestigationEvidence(
            "read_continuity",
            "finding" if related_gaps else "pass",
            "A nearby current-feed gap needs review before interpreting the spike."
            if related_gaps else "No current-feed gap touches the triggering read.",
            {"related_gaps": related_gaps},
        ))
        budget_indicator = str(row.get("budget indicator", "")).strip().upper()
        evidence.append(InvestigationEvidence(
            "budget_indicator",
            "finding" if budget_indicator == "Y" else "pass",
            "The source marks this reading as budget-related."
            if budget_indicator == "Y" else "No budget indicator is present on this reading.",
            {"budget_indicator": budget_indicator or None},
        ))
        read_type = _read_type(row)
        meter_status = str(row.get("meter-status", row.get("meterStatus", ""))).strip().lower()
        weather = _weather_evidence(row.get("weather"))
        evidence.append(weather)
        meter_events = _event_rows(row.get("meterEvents"))
        evidence.append(InvestigationEvidence(
            "meter_changes",
            "finding" if meter_events else "pass" if meter_status == "active" else "data_unavailable",
            "Recent meter events require operational review."
            if meter_events else
            "The submitted meter status is active and no replacement or status-change event was supplied."
            if meter_status == "active" else
            "No verified active meter status or meter-event history is available for this reading.",
            {"meter_status": meter_status or None, "events": meter_events},
        ))
        billing_context = row.get("billingContext") if isinstance(row.get("billingContext"), dict) else {}
        billing_outcome = "finding" if read_type == "estimated" or billing_context.get("correctionRequired") else "pass"
        evidence.append(InvestigationEvidence(
            "billing_issues", billing_outcome,
            "Estimated or correction-required billing context needs validation before customer outreach."
            if billing_outcome == "finding" else
            "The intake identifies an actual reading and no billing correction is currently evidenced.",
            {"read_type": read_type, "billing_context": billing_context},
        ))
        ratio = usage / threshold if threshold else None
        evidence.append(InvestigationEvidence(
            "meter_anomalies", "finding",
            f"Usage is {ratio:.2f} times the deterministic same-slot threshold; this is a suspected interval or device anomaly, not a confirmed meter fault.",
            {"usage_to_threshold_ratio": round(ratio, 4) if ratio is not None else None},
        ))
        assigned_team = _assign_team(read_type, meter_status, weather)
        causes = []
        if billing_outcome == "finding":
            causes.append("estimated-reading or billing reconciliation issue")
        if meter_events or meter_status != "active":
            causes.append("meter status or replacement event")
        if weather.outcome == "finding":
            causes.append("temperature-related demand")
        causes.append("unusual interval or source-reading pattern")
        possible_cause = "Possible " + "; possible ".join(causes) + "."
        action = (
            "Validate the missing interval readings and the meter data continuity before contacting the customer."
            if related_gaps else
            "Validate the interval readings, meter status, and historical comparison before contacting the customer."
        )
        report_summary = (
            f"Usage {usage:.2f} exceeded the same-slot threshold of {threshold:.2f}. "
            f"The deterministic engine assigned {assigned_team}; evidence is retained for associate review."
        )
        detailed_report = _detailed_report(usage, baseline, threshold, evidence, assigned_team)
        cases.append(InvestigationCase(
            case_id, case_key, customer_id, meter_id, read_at, usage, baseline, threshold,
            _severity(usage, threshold), "review_required", action, source_run_id,
            ("spike_detected", "validate_input", "compare_historical_baseline", "evaluate_read_continuity", "review_required"),
            tuple(evidence), assigned_team, possible_cause, report_summary, detailed_report,
        ))
    return cases


def investigation_payload(cases: Iterable[InvestigationCase]) -> dict[str, Any]:
    """Stable API/CLI response shape with no hidden data mutation."""
    values = [case.to_dict() for case in cases]
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engineVersion": ENGINE_VERSION,
        "dataContractVersion": DATA_CONTRACT_VERSION,
        "caseCount": len(values),
        "cases": values,
    }
