from __future__ import annotations

from typing import Any


def _safe_str(val: Any) -> str:
    return str(val).upper() if val else ""


def build_entry_trigger(
    setup_result: dict[str, Any],
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    market_state: dict[str, Any] | None,
    data_quality: str = "UNKNOWN",
) -> dict[str, Any]:
    """
    Produces entry_trigger_status + quality + confidence based on setup.
    Context-only; no entry prices or trade permissions emitted.
    """
    setup_candidate = setup_result.get("setup_candidate", "UNKNOWN")
    setup_direction = setup_result.get("setup_direction", "UNKNOWN")
    setup_quality = setup_result.get("setup_quality", "INVALID")
    setup_confidence = setup_result.get("setup_confidence", 0.0)

    entry_trigger_reason_codes: list[str] = []
    blocking_reason_codes: list[str] = []
    conflict_reason_codes: list[str] = []

    if data_quality == "INVALID":
        return {
            "entry_trigger_status": "TRIGGER_INVALID",
            "entry_trigger_quality": "INVALID",
            "entry_trigger_confidence": 0.0,
            "entry_trigger_reason_codes": ["DATA_QUALITY_INVALID"],
            "blocking_reason_codes": ["DATA_QUALITY_INVALID"],
            "conflict_reason_codes": [],
        }

    scenario_conf = 0.0
    if active_scenario:
        scenario_conf = float(active_scenario.get("scenario_confidence") or 0.0)

    flow_confirmation = "UNKNOWN"
    flow_conf = 0.0
    if flow_reaction:
        flow_confirmation = _safe_str(flow_reaction.get("flow_confirmation") or "UNKNOWN")
        flow_conf = float(flow_reaction.get("reaction_confidence") or 0.0)

    risk_state = "UNKNOWN"
    if market_state:
        risk_state = _safe_str(market_state.get("risk_state") or "UNKNOWN")

    # NO_SETUP or UNKNOWN: not triggerable
    if setup_candidate in ("NO_SETUP", "UNKNOWN", "CONFLICTED_SETUP"):
        entry_trigger_reason_codes.append(f"NO_TRIGGERABLE_SETUP:{setup_candidate}")
        blocking_reason_codes.append("NO_VALID_SETUP")
        return {
            "entry_trigger_status": "TRIGGER_INVALID" if setup_candidate == "NO_SETUP" else "TRIGGER_CONFLICTED",
            "entry_trigger_quality": "INVALID",
            "entry_trigger_confidence": 0.0,
            "entry_trigger_reason_codes": entry_trigger_reason_codes,
            "blocking_reason_codes": blocking_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
        }

    # Risk prohibits entry
    if risk_state == "NO_TRADE":
        blocking_reason_codes.append("RISK_STATE_NO_TRADE")
        return {
            "entry_trigger_status": "TRIGGER_INVALID",
            "entry_trigger_quality": "INVALID",
            "entry_trigger_confidence": 0.0,
            "entry_trigger_reason_codes": ["BLOCKED_BY_RISK_STATE"],
            "blocking_reason_codes": blocking_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
        }

    # Check flow confirmation alignment with setup direction
    if setup_direction == "LONG" and flow_confirmation == "CONFIRMED_SHORT":
        conflict_reason_codes.append("SETUP_LONG_BUT_FLOW_SHORT")
    elif setup_direction == "SHORT" and flow_confirmation == "CONFIRMED_LONG":
        conflict_reason_codes.append("SETUP_SHORT_BUT_FLOW_LONG")

    # Base trigger readiness score
    trigger_score = setup_confidence * 0.5 + scenario_conf * 0.3 + flow_conf * 0.2
    trigger_score = round(trigger_score, 4)

    # Quality tiers
    if setup_quality == "A" and trigger_score >= 0.65:
        entry_trigger_quality = "HIGH"
    elif setup_quality in ("A", "B") and trigger_score >= 0.55:
        entry_trigger_quality = "MEDIUM"
    elif setup_quality == "B" and trigger_score >= 0.45:
        entry_trigger_quality = "MEDIUM"
    elif setup_quality == "C" and trigger_score >= 0.4:
        entry_trigger_quality = "LOW"
    else:
        entry_trigger_quality = "LOW"

    # Trigger status logic
    if conflict_reason_codes and len(conflict_reason_codes) >= 1:
        entry_trigger_status = "TRIGGER_CONFLICTED"
        entry_trigger_reason_codes.append("SETUP_DIRECTION_FLOW_MISMATCH")
    elif setup_quality == "A" and trigger_score >= 0.72:
        entry_trigger_status = "TRIGGER_READY"
        entry_trigger_reason_codes.append("HIGH_QUALITY_SETUP_READY_FOR_ENTRY")
    elif setup_quality == "B" and trigger_score >= 0.65:
        entry_trigger_status = "TRIGGER_READY"
        entry_trigger_reason_codes.append("MEDIUM_QUALITY_SETUP_READY_FOR_ENTRY")
    elif setup_quality == "A" and trigger_score >= 0.60:
        entry_trigger_status = "TRIGGER_NEAR"
        entry_trigger_reason_codes.append("SETUP_NEAR_READY_AWAITING_CONFIRMATION")
    elif setup_quality == "B" and trigger_score >= 0.50:
        entry_trigger_status = "TRIGGER_NEAR"
        entry_trigger_reason_codes.append("SETUP_NEAR_READY_AWAITING_CONFIRMATION")
    elif setup_quality in ("A", "B", "C") and trigger_score >= 0.40:
        entry_trigger_status = "TRIGGER_WAIT"
        entry_trigger_reason_codes.append("SETUP_VALID_BUT_WAIT_FOR_BETTER_EVIDENCE")
    else:
        entry_trigger_status = "TRIGGER_INVALID"
        blocking_reason_codes.append("TRIGGER_SCORE_BELOW_MINIMUM")

    return {
        "entry_trigger_status": entry_trigger_status,
        "entry_trigger_quality": entry_trigger_quality,
        "entry_trigger_confidence": trigger_score,
        "entry_trigger_reason_codes": entry_trigger_reason_codes,
        "blocking_reason_codes": blocking_reason_codes,
        "conflict_reason_codes": conflict_reason_codes,
    }
