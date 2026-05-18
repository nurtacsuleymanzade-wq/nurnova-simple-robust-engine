from __future__ import annotations

from typing import Any

from .replay_registry import DECISION_QUALITY


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_decision_quality(
    source_outcome: dict[str, Any],
    replay_scenarios: list[dict[str, Any]],
    *,
    edge_context: dict[str, Any] | None = None,
    trade_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_r = _to_float(source_outcome.get("r_multiple")) or 0.0
    alt_values = [_to_float(item.get("alternative_r_multiple")) for item in replay_scenarios]
    alt_values = [value for value in alt_values if value is not None]
    best_alt = max(alt_values) if alt_values else base_r
    better_count = sum(1 for item in replay_scenarios if item.get("better_than_original"))
    worse_count = sum(1 for item in replay_scenarios if item.get("worse_than_original"))
    no_trade_alt = next(
        (_to_float(item.get("alternative_r_multiple")) for item in replay_scenarios if item.get("scenario_type") == "NO_TRADE"),
        None,
    )
    wait_alt = next(
        (
            _to_float(item.get("alternative_r_multiple"))
            for item in replay_scenarios
            if item.get("scenario_type") in {"WAIT_INSTEAD_OF_ENTRY", "BLOCK_INSTEAD_OF_ENTRY"}
        ),
        None,
    )

    risk_grade = str((trade_decision or {}).get("risk_grade") or "UNKNOWN").upper()
    edge_rows = (edge_context or {}).get("conditional_edge_rows") or []

    score = 0.5
    if base_r > 0:
        score += 0.15
    elif base_r < 0:
        score -= 0.1

    if best_alt <= base_r:
        score += 0.25
    elif best_alt - base_r <= 0.1:
        score += 0.1
    else:
        score -= 0.2

    if worse_count > better_count:
        score += 0.2
    elif better_count > worse_count:
        score -= 0.2

    if no_trade_alt is not None and no_trade_alt > base_r:
        gap = no_trade_alt - base_r
        score -= 0.35 if gap >= 0.5 else 0.2
    if wait_alt is not None and wait_alt > base_r:
        score -= 0.15

    if risk_grade == "LOW" and base_r > 0:
        score += 0.05
    elif risk_grade == "HIGH" and base_r < 0:
        score -= 0.1

    if edge_rows:
        statuses = {str(row.get("edge_status") or "") for row in edge_rows}
        if statuses.intersection({"STRONG_EDGE_CANDIDATE", "TRADEABLE_EDGE_CANDIDATE"}) and base_r > 0:
            score += 0.05
        if statuses.intersection({"NEGATIVE_EDGE"}) and base_r < 0:
            score -= 0.1

    score = round(max(0.0, min(1.0, score)), 4)

    quality = "UNKNOWN"
    if score >= 0.85:
        quality = "EXCELLENT"
    elif score >= 0.65:
        quality = "GOOD"
    elif score >= 0.45:
        quality = "NEUTRAL"
    elif score >= 0.2:
        quality = "POOR"
    else:
        quality = "TERRIBLE"
    assert quality in DECISION_QUALITY
    return {"decision_quality": quality, "decision_quality_score": score}
