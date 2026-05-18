from __future__ import annotations

from typing import Any

from .active_scenario_registry import DEFAULT_FEEDS_NEXT


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _scenario_quality(confidence: float, risk_state: str, valid: bool) -> str:
    if not valid:
        return "INVALID"
    if risk_state in ("HIGH", "NO_TRADE"):
        if confidence >= 0.7:
            return "MEDIUM"
        if confidence >= 0.4:
            return "LOW"
        return "LOW"
    if confidence >= 0.8:
        return "HIGH"
    if confidence >= 0.55:
        return "MEDIUM"
    if confidence >= 0.3:
        return "LOW"
    return "UNKNOWN"


def _conflict_detected(frame: dict[str, Any], top_long: dict[str, Any] | None, top_short: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if top_long and top_short:
        diff = abs(float(top_long.get("normalized_score", 0.0)) - float(top_short.get("normalized_score", 0.0)))
        if diff <= 0.06 and max(float(top_long.get("normalized_score", 0.0)), float(top_short.get("normalized_score", 0.0))) >= 0.45:
            reasons.append("LONG_SHORT_SCORES_TOO_CLOSE")

    regime = str(frame.get("market_regime", "UNKNOWN"))
    flow = str(frame.get("flow_state", "UNKNOWN"))
    structure = str(frame.get("structure_state", "UNKNOWN"))
    liquidity = str(frame.get("liquidity_pressure_state", "UNKNOWN"))
    if (regime == "UPTREND" and flow == "SELL_PRESSURE") or (regime == "DOWNTREND" and flow == "BUY_PRESSURE"):
        reasons.append("MARKET_STATE_FLOW_CONFLICT")
    if (structure == "HH_HL" and liquidity == "BELOW") or (structure == "LH_LL" and liquidity == "ABOVE"):
        reasons.append("STRUCTURE_LIQUIDITY_CONFLICT")
    return (len(reasons) > 0), reasons


def select_active_scenario(
    *,
    candidates: list[dict[str, Any]],
    feature_frame: dict[str, Any],
    data_quality: str,
    market_state_present: bool,
) -> dict[str, Any]:
    selection_reason_codes: list[str] = []
    rejection_reason_codes: list[str] = []
    conflict_reason_codes: list[str] = []

    if not candidates:
        return {
            "active_scenario": "NO_ACTIVE_SCENARIO",
            "scenario_bias": "NO_TRADE",
            "scenario_confidence": 0.0,
            "scenario_quality": "UNKNOWN",
            "selection_reason_codes": ["NO_CANDIDATE_GENERATED"],
            "rejection_reason_codes": [],
            "conflict_reason_codes": [],
            "selected_candidate": {},
            "candidate_scores": {
                "market_state_alignment": 0.0,
                "liquidity_alignment": 0.0,
                "structure_alignment": 0.0,
                "flow_alignment": 0.0,
                "reaction_alignment": 0.0,
                "conflict_penalty": 0.0,
                "data_quality_penalty": 0.0,
                "late_maturity_penalty": 0.0,
            },
            "feeds_next": list(DEFAULT_FEEDS_NEXT),
        }

    sorted_candidates = sorted(candidates, key=lambda x: float(x.get("normalized_score", 0.0)), reverse=True)
    selected = sorted_candidates[0]
    bias = str(selected.get("bias", "UNKNOWN"))
    confidence = float(selected.get("normalized_score", 0.0))
    selection_reason_codes.append(f"TOP_SCENARIO_{selected.get('scenario')}")
    selection_reason_codes.append(f"TOP_SCORE_{round(confidence,4)}")

    if not market_state_present:
        confidence *= 0.6
        selection_reason_codes.append("MARKET_STATE_MISSING_CONFIDENCE_DOWN")
    if data_quality in ("DEGRADED", "INVALID", "UNKNOWN"):
        confidence *= 0.75
        selection_reason_codes.append("LOW_DATA_QUALITY_CONFIDENCE_DOWN")
    if not selected.get("required_evidence_present", False):
        confidence *= 0.65
        selection_reason_codes.append("REQUIRED_EVIDENCE_MISSING_CONFIDENCE_DOWN")

    top_long = next((x for x in sorted_candidates if x.get("bias") == "LONG"), None)
    top_short = next((x for x in sorted_candidates if x.get("bias") == "SHORT"), None)
    conflicted, conflict_reasons = _conflict_detected(feature_frame, top_long, top_short)
    conflict_reason_codes.extend(conflict_reasons)

    if conflicted:
        selected = {
            "scenario": "CONFLICTED_SCENARIO",
            "bias": "NO_TRADE",
            "normalized_score": max(
                float(top_long.get("normalized_score", 0.0)) if top_long else 0.0,
                float(top_short.get("normalized_score", 0.0)) if top_short else 0.0,
            ),
            "candidate_scores": selected.get("candidate_scores") or {},
        }
        bias = "NO_TRADE"
        confidence = _clamp(confidence * 0.8)
        selection_reason_codes.append("CONFLICTED_SCENARIO_SELECTED")

    if data_quality == "INVALID" or confidence < 0.35 or selected.get("scenario") == "UNKNOWN":
        selected = {
            "scenario": "NO_ACTIVE_SCENARIO",
            "bias": "NO_TRADE",
            "normalized_score": _clamp(confidence),
            "candidate_scores": selected.get("candidate_scores") or {},
        }
        bias = "NO_TRADE"
        confidence = _clamp(min(confidence, 0.34))
        selection_reason_codes.append("NO_ACTIVE_SCENARIO_SELECTED_LOW_CONFIDENCE")

    for c in sorted_candidates[1:5]:
        rejection_reason_codes.append(f"REJECTED_{c.get('scenario')}_SCORE_{round(float(c.get('normalized_score', 0.0)),4)}")
        if c.get("opposing_reason_codes"):
            rejection_reason_codes.extend([f"REJECT_REASON_{code}" for code in c["opposing_reason_codes"][:2]])

    confidence = round(_clamp(confidence), 4)
    quality = _scenario_quality(confidence, str(feature_frame.get("risk_state", "UNKNOWN")), valid=True)
    if selected.get("scenario") == "NO_ACTIVE_SCENARIO" and quality == "HIGH":
        quality = "LOW"
    if selected.get("scenario") == "CONFLICTED_SCENARIO" and quality == "HIGH":
        quality = "MEDIUM"

    return {
        "active_scenario": selected.get("scenario", "UNKNOWN"),
        "scenario_bias": bias if bias in ("LONG", "SHORT", "NEUTRAL", "NO_TRADE", "UNKNOWN") else "UNKNOWN",
        "scenario_confidence": confidence,
        "scenario_quality": quality,
        "selection_reason_codes": sorted(set(selection_reason_codes)),
        "rejection_reason_codes": sorted(set(rejection_reason_codes)),
        "conflict_reason_codes": sorted(set(conflict_reason_codes)),
        "selected_candidate": selected,
        "candidate_scores": selected.get("candidate_scores")
        or {
            "market_state_alignment": 0.0,
            "liquidity_alignment": 0.0,
            "structure_alignment": 0.0,
            "flow_alignment": 0.0,
            "reaction_alignment": 0.0,
            "conflict_penalty": 0.0,
            "data_quality_penalty": 0.0,
            "late_maturity_penalty": 0.0,
        },
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
    }

