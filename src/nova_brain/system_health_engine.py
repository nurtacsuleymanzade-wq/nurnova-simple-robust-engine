from __future__ import annotations

from typing import Any

from .brain_registry import SYSTEM_HEALTH


def _extract_dq(value: Any) -> str:
    if isinstance(value, dict):
        dq = value.get("data_quality")
        if isinstance(dq, dict):
            level = dq.get("level")
            if isinstance(level, str):
                upper = level.upper()
                if upper in {"HIGH", "MEDIUM", "LOW", "MISSING", "CRITICAL"}:
                    return {
                        "HIGH": "OK",
                        "MEDIUM": "ACCEPTABLE",
                        "LOW": "DEGRADED",
                        "MISSING": "INVALID",
                        "CRITICAL": "INVALID",
                    }[upper]
        if isinstance(dq, str):
            return dq.upper()
        if isinstance(value.get("data_quality"), str):
            return str(value.get("data_quality")).upper()
    return "UNKNOWN"


def evaluate_system_health(
    inputs: dict[str, dict[str, Any] | None],
    *,
    report_files_count: int = 0,
    live_files_count: int = 0,
) -> dict[str, Any]:
    expected = len(inputs)
    present = sum(1 for value in inputs.values() if value)
    missing_ratio = 1.0 - (present / expected) if expected else 1.0

    degraded_components: list[str] = []
    critical_failures: list[str] = []
    dq_bad = 0
    partial_or_fail = 0

    for name, payload in inputs.items():
        if not payload:
            degraded_components.append(name)
            continue
        dq = _extract_dq(payload)
        if dq in {"DEGRADED", "INVALID"}:
            dq_bad += 1
            degraded_components.append(name)

        joined = " ".join(
            str(payload.get(key) or "")
            for key in ("status", "lineage_health_status", "outcome_to_edge_link_status", "edge_status", "replay_status")
        ).upper()
        if any(token in joined for token in ("FAIL", "INVALID", "CRITICAL")):
            critical_failures.append(name)
        if any(token in joined for token in ("PARTIAL", "DEGRADED", "NO_DATA", "UNKNOWN")):
            partial_or_fail += 1

    data_quality_pressure = round(
        min(
            1.0,
            missing_ratio * 0.45
            + (dq_bad / expected if expected else 0.0) * 0.35
            + (partial_or_fail / expected if expected else 0.0) * 0.20,
        ),
        4,
    )

    health_score = round(max(0.0, 1.0 - data_quality_pressure), 4)
    if critical_failures or missing_ratio >= 0.5:
        status = "CRITICAL"
    elif data_quality_pressure >= 0.55:
        status = "DEGRADED"
    elif data_quality_pressure >= 0.25:
        status = "STRESSED"
    elif present == 0:
        status = "UNKNOWN"
    else:
        status = "HEALTHY"
    assert status in SYSTEM_HEALTH

    if report_files_count == 0:
        degraded_components.append("reports")
    if live_files_count == 0:
        degraded_components.append("live_data")

    return {
        "status": status,
        "health_score": health_score,
        "critical_failures": sorted(set(critical_failures)),
        "degraded_components": sorted(set(degraded_components)),
        "data_quality_pressure": data_quality_pressure,
        "present_inputs_count": present,
        "expected_inputs_count": expected,
        "report_files_count": report_files_count,
        "live_files_count": live_files_count,
    }
