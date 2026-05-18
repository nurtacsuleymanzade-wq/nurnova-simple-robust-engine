from __future__ import annotations

from typing import Any

from .autonomy_registry import SAFETY_STATUS, clamp, safety_status_from_risk_score


def evaluate_template_risk(
    trade_decision: dict[str, Any] | None,
    setup_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    trade_decision = trade_decision or {}
    setup_entry = setup_entry or {}

    if not trade_decision and not setup_entry:
        return {
            "status": "UNKNOWN",
            "score": None,
            "reason_codes": ["UNKNOWN_AUTONOMY_STATE"],
        }

    missing_economic_levels = sum(
        1
        for field in ("stop_loss", "take_profit_1", "take_profit_2", "invalidation_level")
        if trade_decision.get(field) is None
    )
    setup_quality = str(setup_entry.get("setup_quality") or "UNKNOWN").upper()
    trigger_quality = str(setup_entry.get("entry_trigger_quality") or "UNKNOWN").upper()
    trigger_status = str(setup_entry.get("entry_trigger_status") or "UNKNOWN").upper()
    plan_quality = str(trade_decision.get("plan_quality") or "UNKNOWN").upper()
    repeated_tp_structure = trade_decision.get("take_profit_1") == trade_decision.get("take_profit_2") and trade_decision.get("take_profit_1") is not None
    confidence_cluster = abs(float(setup_entry.get("setup_confidence") or 0.0) - float(setup_entry.get("entry_trigger_confidence") or 0.0)) <= 0.05
    fake_deterministic_pattern_risk = (
        str(trade_decision.get("entry_model") or "UNKNOWN").upper() == "RETEST"
        and str(trade_decision.get("decision_status") or "UNKNOWN").upper() == "BLOCK"
        and missing_economic_levels >= 3
    )

    risk_score = 0.0
    risk_score += min(0.5, missing_economic_levels * 0.12)
    if plan_quality == "INVALID":
        risk_score += 0.2
    if trigger_quality == "LOW" or trigger_status == "TRIGGER_INVALID":
        risk_score += 0.1
    if setup_quality == "C":
        risk_score += 0.05
    if repeated_tp_structure:
        risk_score += 0.1
    if confidence_cluster:
        risk_score += 0.05
    if fake_deterministic_pattern_risk:
        risk_score += 0.15
    risk_score = clamp(risk_score)
    status = safety_status_from_risk_score(risk_score)

    assert status in SAFETY_STATUS
    return {
        "status": status,
        "score": risk_score,
        "missing_economic_levels": missing_economic_levels,
        "repeated_tp_structure": repeated_tp_structure,
        "confidence_cluster_detected": confidence_cluster,
        "fake_deterministic_pattern_risk": fake_deterministic_pattern_risk,
        "reason_codes": [
            f"PLAN_QUALITY_{plan_quality}",
            f"TRIGGER_STATUS_{trigger_status}",
        ],
    }
