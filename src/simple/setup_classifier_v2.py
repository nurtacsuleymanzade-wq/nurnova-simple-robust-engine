"""S29 - Setup Classifier V2.

Read-only classifier that converts flow, persistence, quality, structure,
liquidity, scenario, and edge context into setup readiness and class labels.
No orders. No Telegram. No real trades.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S29_SETUP_CLASSIFIER_V2"
SYMBOL = "BTCUSDT"

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

INPUT_PATHS = {
    "flow_state": STATE_DIR / "latest_flow_state.json",
    "flow_evidence": STATE_DIR / "latest_flow_evidence.json",
    "flow_persistence": STATE_DIR / "latest_flow_persistence.json",
    "setup_context": STATE_DIR / "latest_setup_context.json",
    "scenario_trigger": STATE_DIR / "latest_scenario_trigger.json",
    "trade_plan": STATE_DIR / "latest_trade_plan.json",
    "decision_gate": STATE_DIR / "latest_decision_gate.json",
    "quality_audit": STATE_DIR / "latest_live_flow_quality_audit.json",
    "liquidity_memory": STATE_DIR / "latest_depth_liquidity_memory.json",
    "market_structure": STATE_DIR / "latest_market_structure_v2.json",
    "edge_matrix": STATE_DIR / "latest_edge_matrix_v2.json",
    "full_chain_truth_audit": STATE_DIR / "latest_full_chain_truth_audit.json",
}

LATEST_STATE_PATH = STATE_DIR / "latest_setup_classifier_v2.json"
S29_STATE_PATH = STATE_DIR / "s29_setup_classifier_v2_state.json"
HISTORY_PATH = DATA_DIR / "setup_classifier_v2_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s29_setup_classifier_v2_latest_report.md"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

COMPONENT_WEIGHTS = {
    "quality_component": 0.15,
    "flow_component": 0.25,
    "persistence_component": 0.20,
    "structure_component": 0.20,
    "liquidity_component": 0.10,
    "scenario_component": 0.10,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _direction_from_evidence(label: str, score: float) -> str:
    label_u = str(label).upper()
    if "LONG" in label_u or score >= 1.5:
        return "LONG"
    if "SHORT" in label_u or score <= -1.5:
        return "SHORT"
    return "NEUTRAL"


def _score_to_unit(score: float, scale: float = 6.0) -> float:
    return _clamp(abs(score) / scale)


def _component_result(score: float, status: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {"score": round(_clamp(score), 4), "status": status}
    if details:
        out.update(details)
    return out


def _assess_quality(
    quality_audit: dict[str, Any] | None,
    flow_evidence: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    no_trade_reasons: list[str],
    supporting: list[str],
    blocking: list[str],
    required_improvements: list[str],
    reason_codes: list[str],
) -> tuple[dict[str, Any], str, str]:
    qa = quality_audit or {}
    flow_dq = (flow_evidence or {}).get("data_quality") or {}
    chain_dq = (audit or {}).get("data_quality") or {}

    label = str(qa.get("quality_label") or qa.get("data_quality", {}).get("level") or flow_dq.get("level") or "NO_DATA").upper()
    if isinstance(chain_dq.get("level"), dict):
        chain_level = str(chain_dq.get("level", {}).get("level", "UNKNOWN")).upper()
    else:
        chain_level = str(chain_dq.get("level", "UNKNOWN")).upper()

    score = _safe_float(qa.get("quality_score"), _safe_float(qa.get("data_quality", {}).get("score"), _safe_float(flow_dq.get("score"), 0.0)))
    if label in ("HIGH", "OK"):
        supporting.append(f"Quality supports evaluation ({label}, score={round(score,3)}).")
        status = "ALIGNED"
    elif label == "DEGRADED":
        no_trade_reasons.append("DEGRADED_DATA_QUALITY")
        required_improvements.append("Improve live flow data quality before trusting setup grade.")
        blocking.append("Quality is degraded.")
        reason_codes.append("DEGRADED_DATA_QUALITY")
        status = "DEGRADED"
    elif label in ("STALE", "NO_DATA", "MISSING"):
        no_trade_reasons.append("STALE_DATA" if label == "STALE" else "MISSING_INPUTS")
        required_improvements.append("Refresh live inputs before evaluating setup readiness.")
        blocking.append(f"Quality blocks setup evaluation ({label}).")
        reason_codes.append("STALE_DATA" if label == "STALE" else "MISSING_INPUTS")
        status = "BLOCKED"
        score = min(score, 0.1)
    else:
        status = "UNKNOWN"
        score = min(score, 0.25)

    data_quality = {
        "quality_label": label,
        "quality_score": round(score, 4),
        "chain_quality_level": chain_level,
        "stale_data": bool(qa.get("stale_data", False)),
        "full_chain_status": audit.get("system_running_status") if audit else "UNKNOWN",
    }
    return _component_result(score, status, data_quality), label, chain_level


def _assess_flow(
    flow_evidence: dict[str, Any] | None,
    no_trade_reasons: list[str],
    supporting: list[str],
    blocking: list[str],
    reason_codes: list[str],
) -> tuple[dict[str, Any], str, float]:
    evidence = flow_evidence or {}
    label = str(evidence.get("evidence_label", "NEUTRAL_FLOW")).upper()
    raw_score = _safe_float(evidence.get("evidence_score"), 0.0)
    confidence = _safe_float(evidence.get("confidence"), 0.0)
    side = _direction_from_evidence(label, raw_score)

    score = min(_score_to_unit(raw_score, 6.0), confidence + 0.2 if side != "NEUTRAL" else 0.25)
    if side == "NEUTRAL":
        no_trade_reasons.append("NO_DIRECTIONAL_BIAS")
        blocking.append("Flow evidence is neutral or too weak.")
        reason_codes.append("NO_DIRECTIONAL_BIAS")
        score = min(score, 0.25)
        status = "NEUTRAL"
    else:
        supporting.append(f"Flow supports {side} ({label}, confidence={round(confidence,3)}).")
        status = "ALIGNED"

    if confidence < 0.60:
        no_trade_reasons.append("LOW_FLOW_CONFIDENCE")
        blocking.append(f"Flow confidence is below readiness threshold ({round(confidence,3)}).")
        reason_codes.append("LOW_FLOW_CONFIDENCE")
        status = "WEAK" if side != "NEUTRAL" else status
        score = min(score, 0.59)

    return _component_result(score, status, {
        "label": label,
        "evidence_score": round(raw_score, 4),
        "confidence": round(confidence, 4),
        "side": side,
    }), side, confidence


def _assess_persistence(
    persistence: dict[str, Any] | None,
    setup_side: str,
    no_trade_reasons: list[str],
    supporting: list[str],
    blocking: list[str],
    reason_codes: list[str],
) -> tuple[dict[str, Any], str]:
    data = persistence or {}
    label = str(data.get("persistence_label", "NO_VALID_FLOW")).upper()
    direction = str(data.get("direction_label", "UNKNOWN")).upper()
    cont = str(data.get("continuation_quality", "NONE")).upper()
    decay = bool(data.get("decay_risk", False))
    flip = bool(data.get("flip_risk", False))
    score = _score_to_unit(_safe_float(data.get("persistence_score"), 0.0), 6.0)
    family_hint = "UNKNOWN"

    if label == "CHOPPY_FLOW":
        no_trade_reasons.append("CHOPPY_PERSISTENCE")
        blocking.append("Persistence is choppy.")
        reason_codes.append("CHOPPY_PERSISTENCE")
        return _component_result(0.1, "CHOPPY", {
            "label": label,
            "direction": direction,
            "continuation_quality": cont,
            "decay_risk": decay,
            "flip_risk": flip,
        }), family_hint

    if label in ("FADING_LONG_PRESSURE", "FADING_SHORT_PRESSURE"):
        no_trade_reasons.append("FADING_PERSISTENCE")
        blocking.append(f"Persistence is fading ({label}).")
        reason_codes.append("FADING_PERSISTENCE")
        family_hint = "REVERSAL"
        score = min(score, 0.55)
        status = "FADING"
    elif label in ("SUSTAINED_LONG_PRESSURE", "SUSTAINED_SHORT_PRESSURE"):
        supporting.append(f"Persistence is sustained ({label}).")
        family_hint = "CONTINUATION"
        status = "ALIGNED" if setup_side in ("UNKNOWN", "NEUTRAL", direction) else "CONFLICT"
    else:
        status = "WEAK"
        score = min(score, 0.35)

    if flip:
        family_hint = "REVERSAL"
    return _component_result(score, status, {
        "label": label,
        "direction": direction,
        "continuation_quality": cont,
        "decay_risk": decay,
        "flip_risk": flip,
    }), family_hint


def _assess_structure(
    structure: dict[str, Any] | None,
    flow_side: str,
    no_trade_reasons: list[str],
    supporting: list[str],
    blocking: list[str],
    required_improvements: list[str],
    reason_codes: list[str],
) -> tuple[dict[str, Any], str, str]:
    data = structure or {}
    bias = str(data.get("structure_bias", "INSUFFICIENT_DATA")).upper()
    strength = _safe_float(data.get("structure_strength"), 0.0)
    sweep = str(data.get("liquidity_sweep_status", "INSUFFICIENT_DATA")).upper()
    choch = str(data.get("choch_status", "INSUFFICIENT_DATA")).upper()
    bos = str(data.get("bos_status", "INSUFFICIENT_DATA")).upper()
    readiness = str(data.get("setup_readiness_hint", "STRUCTURE_NOT_READY")).upper()
    family = "UNKNOWN"

    side = "NEUTRAL"
    if bias == "BULLISH_STRUCTURE":
        side = "LONG"
    elif bias == "BEARISH_STRUCTURE":
        side = "SHORT"

    if bias == "INSUFFICIENT_DATA":
        no_trade_reasons.append("STRUCTURE_INSUFFICIENT")
        required_improvements.append("Accumulate enough candles for market structure.")
        blocking.append("Structure is insufficient.")
        reason_codes.append("STRUCTURE_INSUFFICIENT")
        return _component_result(0.1, "INSUFFICIENT", {
            "bias": bias,
            "strength": round(strength, 4),
            "sweep": sweep,
            "choch": choch,
            "bos": bos,
            "readiness": readiness,
        }), side, family

    if side != "NEUTRAL" and flow_side not in ("NEUTRAL", "UNKNOWN") and side != flow_side:
        no_trade_reasons.append("STRUCTURE_CONFLICT")
        blocking.append(f"Structure conflicts with flow ({bias} vs {flow_side}).")
        reason_codes.append("STRUCTURE_CONFLICT")
        status = "CONFLICT"
        score = min(strength, 0.35)
    else:
        supporting.append(f"Structure bias is {bias} (strength={round(strength,3)}).")
        status = "ALIGNED" if side != "NEUTRAL" else "RANGE"
        score = max(strength, 0.2 if bias == "RANGE_STRUCTURE" else 0.0)

    if "SWEEP" in sweep and "SELL_SIDE" in sweep:
        family = "SWEEP_RECLAIM"
    elif "SWEEP" in sweep and "BUY_SIDE" in sweep:
        family = "SWEEP_RECLAIM"
    elif choch in ("BULLISH_CHOCH", "BEARISH_CHOCH"):
        family = "REVERSAL"
    elif bos in ("BULLISH_BOS", "BEARISH_BOS"):
        family = "BREAKOUT"
    elif bias == "RANGE_STRUCTURE":
        family = "RANGE_FADE"
    elif bias in ("BULLISH_STRUCTURE", "BEARISH_STRUCTURE"):
        family = "CONTINUATION"

    return _component_result(score, status, {
        "bias": bias,
        "strength": round(strength, 4),
        "sweep": sweep,
        "choch": choch,
        "bos": bos,
        "readiness": readiness,
    }), side, family


def _assess_liquidity(
    liquidity: dict[str, Any] | None,
    setup_side: str,
    structure_family: str,
    no_trade_reasons: list[str],
    supporting: list[str],
    blocking: list[str],
    required_improvements: list[str],
    reason_codes: list[str],
) -> tuple[dict[str, Any], str]:
    data = liquidity or {}
    bias = str(data.get("liquidity_bias", "UNKNOWN")).upper()
    status = str(data.get("liquidity_memory_status", "UNKNOWN")).upper()
    depth_available = bool(data.get("depth_available", False))
    fallback_used = bool(data.get("fallback_used", False))
    family = structure_family

    if not liquidity:
        no_trade_reasons.append("LIQUIDITY_DEPTH_MISSING")
        required_improvements.append("Provide S27 liquidity memory for setup confirmation.")
        blocking.append("Liquidity input missing.")
        reason_codes.append("LIQUIDITY_DEPTH_MISSING")
        return _component_result(0.1, "MISSING", {
            "bias": bias,
            "liquidity_memory_status": status,
            "depth_available": depth_available,
            "fallback_used": fallback_used,
        }), family

    score = 0.35 if bias in ("UNKNOWN", "NO_CLEAR_LIQUIDITY", "BOTH_SIDES") else 0.75
    state = "NEUTRAL"
    if not depth_available:
        no_trade_reasons.append("LIQUIDITY_DEPTH_MISSING")
        required_improvements.append("Feed live depth snapshots to validate liquidity.")
        reason_codes.append("LIQUIDITY_DEPTH_MISSING")
        score = min(score, 0.35)
        state = "WEAK"

    if setup_side == "LONG" and bias == "ASK_RESISTANCE":
        no_trade_reasons.append("LIQUIDITY_CONFLICT")
        blocking.append("Liquidity leans against LONG idea.")
        reason_codes.append("LIQUIDITY_CONFLICT")
        score = min(score, 0.25)
        state = "CONFLICT"
    elif setup_side == "SHORT" and bias == "BID_SUPPORT":
        no_trade_reasons.append("LIQUIDITY_CONFLICT")
        blocking.append("Liquidity leans against SHORT idea.")
        reason_codes.append("LIQUIDITY_CONFLICT")
        score = min(score, 0.25)
        state = "CONFLICT"
    elif bias in ("BID_SUPPORT", "ASK_RESISTANCE"):
        supporting.append(f"Liquidity bias supports setup ({bias}).")
        state = "ALIGNED"

    wall_events = data.get("wall_events") or []
    absorption = data.get("absorption_candidates") or []
    broken = data.get("broken_wall_candidates") or []
    if absorption:
        family = "ABSORPTION"
    if broken:
        family = "TRAP"
    for ev in wall_events:
        side = str(ev.get("side", "")).upper()
        st = str(ev.get("status", "")).upper()
        if side == "BID" and st in ("ABSORBED", "BROKEN") and setup_side == "SHORT":
            family = "FAILED_BREAKOUT"
        if side == "ASK" and st in ("ABSORBED", "BROKEN") and setup_side == "LONG":
            family = "FAILED_BREAKOUT"

    return _component_result(score, state, {
        "bias": bias,
        "liquidity_memory_status": status,
        "depth_available": depth_available,
        "fallback_used": fallback_used,
        "wall_events": wall_events[:5],
    }), family


def _assess_scenario(
    scenario: dict[str, Any] | None,
    no_trade_reasons: list[str],
    supporting: list[str],
    blocking: list[str],
    reason_codes: list[str],
) -> tuple[dict[str, Any], str, str]:
    data = scenario or {}
    label = str(data.get("scenario_label", "INSUFFICIENT_DATA")).upper()
    trigger_state = str(data.get("trigger_state", "NO_TRIGGER")).upper()
    direction = str(data.get("direction_bias", "UNKNOWN")).upper()
    trigger_strength = _safe_float(data.get("trigger_strength"), 0.0)
    trigger_confidence = _safe_float(data.get("trigger_confidence"), 0.0)
    family = "UNKNOWN"

    score = max(trigger_strength, trigger_confidence)
    if label in ("NO_SCENARIO", "INSUFFICIENT_DATA", "CHOPPY_RANGE"):
        no_trade_reasons.append("SCENARIO_NOT_READY")
        blocking.append(f"Scenario does not support a trade setup ({label}).")
        reason_codes.append("SCENARIO_NOT_READY")
        score = min(score, 0.2)
        status = "NOT_READY"
    elif trigger_state != "READY_FOR_ENTRY":
        no_trade_reasons.append("SCENARIO_NOT_READY")
        blocking.append(f"Scenario is not entry-ready ({trigger_state}).")
        reason_codes.append("SCENARIO_NOT_READY")
        score = min(score, 0.65)
        status = "WATCH"
    else:
        supporting.append(f"Scenario supports setup ({label}, {trigger_state}).")
        status = "ALIGNED"

    if "CONTINUATION" in label:
        family = "CONTINUATION"
    elif "REVERSAL" in label:
        family = "REVERSAL"
    elif "FAILED_BREAKOUT" in label:
        family = "FAILED_BREAKOUT"
    elif "BREAKOUT" in label:
        family = "BREAKOUT"

    return _component_result(score, status, {
        "label": label,
        "trigger_state": trigger_state,
        "trigger_strength": round(trigger_strength, 4),
        "trigger_confidence": round(trigger_confidence, 4),
        "direction_bias": direction,
    }), direction, family


def _assess_edge(
    edge: dict[str, Any] | None,
    no_trade_reasons: list[str],
    blocking: list[str],
    reason_codes: list[str],
) -> dict[str, Any]:
    data = edge or {}
    quality = data.get("edge_quality") or {}
    sample = data.get("sample_summary") or {}
    edge_status = str(quality.get("edge_status", "NO_EDGE_CLAIM")).upper()
    sample_status = str(sample.get("sample_status", "INSUFFICIENT_SAMPLE")).upper()
    usable = int(sample.get("usable_closed_records", 0) or 0)
    caution = str(quality.get("caution_reason", "")).upper()

    score = 0.8 if edge_status == "VALIDATED_EDGE" else 0.6 if edge_status == "PROMISING_EDGE" else 0.35 if edge_status == "WEAK_EDGE" else 0.15
    if edge_status in ("NO_EDGE_CLAIM", "RESEARCH_ONLY") or usable < 30:
        if "EDGE_NOT_VALIDATED" not in no_trade_reasons:
            no_trade_reasons.append("EDGE_NOT_VALIDATED")
        blocking.append("Edge history is not validated yet.")
        reason_codes.append("EDGE_NOT_VALIDATED")

    return {
        "edge_status": edge_status,
        "sample_status": sample_status,
        "usable_closed_records": usable,
        "caution_reason": caution,
        "score": round(score, 4),
    }


def _family_from_components(struct_family: str, liq_family: str, scen_family: str) -> str:
    priority = ("TRAP", "FAILED_BREAKOUT", "ABSORPTION", "SWEEP_RECLAIM", "REVERSAL")
    for family in priority:
        if family in (liq_family, struct_family, scen_family):
            return family
    for family in (scen_family, struct_family, liq_family):
        if family in {"CONTINUATION", "BREAKOUT", "RANGE_FADE"}:
            return family
    return "NO_FAMILY"


def _class_from_family(side: str, family: str, score: float, confidence: float) -> str:
    if side == "LONG":
        if family == "SWEEP_RECLAIM":
            return "L4_LONG_SWEEP_RECLAIM"
        if family == "REVERSAL":
            return "L3_LONG_REVERSAL"
        if family == "CONTINUATION":
            return "L2_LONG_CONTINUATION"
        if score >= 0.9 and confidence >= 0.8:
            return "L5_RARE_A_PLUS_LONG"
        return "L1_WEAK_LONG_WATCH"
    if side == "SHORT":
        if family == "SWEEP_RECLAIM":
            return "S4_SHORT_SWEEP_RECLAIM"
        if family == "REVERSAL":
            return "S3_SHORT_REVERSAL"
        if family == "CONTINUATION":
            return "S2_SHORT_CONTINUATION"
        if score >= 0.9 and confidence >= 0.8:
            return "S5_RARE_A_PLUS_SHORT"
        return "S1_WEAK_SHORT_WATCH"
    return "NO_SETUP_CLASS"


def _upgrade_rare_class(setup_class: str, side: str, family: str, score: float, confidence: float) -> str:
    if score >= 0.9 and confidence >= 0.8 and family in ("CONTINUATION", "REVERSAL", "SWEEP_RECLAIM"):
        return "L5_RARE_A_PLUS_LONG" if side == "LONG" else "S5_RARE_A_PLUS_SHORT"
    return setup_class


def _grade_from_outcome(
    score: float,
    confidence: float,
    quality_label: str,
    critical_conflict: bool,
    edge_validated: bool,
) -> str:
    if critical_conflict:
        return "NO_SETUP"
    if quality_label in ("STALE", "NO_DATA", "MISSING"):
        return "NO_SETUP"
    if score >= 0.9 and confidence >= 0.8 and quality_label in ("OK", "HIGH") and edge_validated:
        return "A_PLUS"
    if score >= 0.8 and confidence >= 0.7:
        return "A"
    if score >= 0.7 and confidence >= 0.6:
        return "B"
    if score >= 0.55 and confidence >= 0.45:
        return "C"
    return "WATCH"


def compute_setup_classifier_v2(inputs: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    ts = _utc_now()
    symbol = next((str((data or {}).get("symbol")) for data in inputs.values() if isinstance(data, dict) and data.get("symbol")), SYMBOL)
    source = "S28_MARKET_STRUCTURE_V2"
    reason_codes: list[str] = ["S29_SETUP_CLASSIFIER_V2_RUN", "SAFE_TO_OPEN_REAL_TRADE_FALSE", "RR_NOT_EVALUATED_YET"]
    no_trade_reasons: list[str] = ["RR_NOT_EVALUATED_YET"]
    supporting: list[str] = []
    blocking: list[str] = []
    required_improvements: list[str] = []
    missing_inputs = [name for name, data in inputs.items() if data is None]

    input_status = "OK" if not missing_inputs else "PARTIAL" if len(missing_inputs) < len(inputs) else "MISSING"
    if missing_inputs:
        no_trade_reasons.append("MISSING_INPUTS")
        blocking.append(f"Missing inputs: {', '.join(missing_inputs)}.")
        required_improvements.append("Restore missing upstream state files.")
        reason_codes.append("MISSING_INPUTS")

    quality_component, quality_label, chain_level = _assess_quality(
        inputs.get("quality_audit"), inputs.get("flow_evidence"), inputs.get("full_chain_truth_audit"),
        no_trade_reasons, supporting, blocking, required_improvements, reason_codes,
    )
    flow_component, flow_side, flow_confidence = _assess_flow(
        inputs.get("flow_evidence"), no_trade_reasons, supporting, blocking, reason_codes,
    )
    scenario_component, scenario_side, scenario_family = _assess_scenario(
        inputs.get("scenario_trigger"), no_trade_reasons, supporting, blocking, reason_codes,
    )

    setup_side = "UNKNOWN"
    for side in (scenario_side, flow_side, str((inputs.get("setup_context") or {}).get("direction_bias", "UNKNOWN")).upper()):
        if side in ("LONG", "SHORT"):
            setup_side = side
            break
    if setup_side == "UNKNOWN" and flow_side == "NEUTRAL":
        setup_side = "NEUTRAL"

    persistence_component, persistence_family = _assess_persistence(
        inputs.get("flow_persistence"), setup_side, no_trade_reasons, supporting, blocking, reason_codes,
    )
    structure_component, structure_side, structure_family = _assess_structure(
        inputs.get("market_structure"), setup_side if setup_side in ("LONG", "SHORT") else flow_side,
        no_trade_reasons, supporting, blocking, required_improvements, reason_codes,
    )
    if setup_side not in ("LONG", "SHORT") and structure_side in ("LONG", "SHORT"):
        setup_side = structure_side
    liquidity_component, liquidity_family = _assess_liquidity(
        inputs.get("liquidity_memory"), setup_side, structure_family,
        no_trade_reasons, supporting, blocking, required_improvements, reason_codes,
    )
    edge_component = _assess_edge(inputs.get("edge_matrix"), no_trade_reasons, blocking, reason_codes)

    weighted_score = sum(COMPONENT_WEIGHTS[name] * component["score"] for name, component in (
        ("quality_component", quality_component),
        ("flow_component", flow_component),
        ("persistence_component", persistence_component),
        ("structure_component", structure_component),
        ("liquidity_component", liquidity_component),
        ("scenario_component", scenario_component),
    ))
    confidence = (
        flow_confidence * 0.35
        + _safe_float(scenario_component.get("trigger_confidence"), 0.0) * 0.25
        + structure_component["score"] * 0.15
        + quality_component["score"] * 0.15
        + persistence_component["score"] * 0.10
    )

    critical_conflict = any(code in reason_codes for code in ("STRUCTURE_CONFLICT", "LIQUIDITY_CONFLICT")) or quality_label in ("STALE", "NO_DATA", "MISSING")
    if flow_confidence < 0.60:
        confidence = min(confidence, 0.59)
    if quality_label == "DEGRADED":
        weighted_score = min(weighted_score, 0.79)
        confidence = min(confidence, 0.69)
    if "EDGE_NOT_VALIDATED" in reason_codes:
        confidence = min(confidence, 0.89)
    else:
        all_strong = all(component["score"] >= 0.70 for component in (
            quality_component,
            flow_component,
            persistence_component,
            structure_component,
            liquidity_component,
            scenario_component,
        ))
        if all_strong and quality_label in ("OK", "HIGH"):
            weighted_score = min(weighted_score + 0.1, 1.0)
            confidence = min(confidence + 0.03, 1.0)

    setup_score = round(_clamp(weighted_score), 4)
    setup_confidence = round(_clamp(confidence), 4)
    setup_family = _family_from_components(structure_family, liquidity_family, scenario_family)

    if setup_side not in ("LONG", "SHORT"):
        setup_side = "NEUTRAL" if flow_side == "NEUTRAL" else "UNKNOWN"
    setup_class = _class_from_family(setup_side, setup_family, setup_score, setup_confidence)
    setup_class = _upgrade_rare_class(setup_class, setup_side, setup_family, setup_score, setup_confidence)

    edge_validated = edge_component["edge_status"] == "VALIDATED_EDGE"
    setup_grade = _grade_from_outcome(setup_score, setup_confidence, quality_label, critical_conflict, edge_validated)
    if quality_label == "DEGRADED" and setup_grade in ("A_PLUS", "A"):
        setup_grade = "B"

    decision = inputs.get("decision_gate") or {}
    if str(decision.get("decision", "BLOCK")).upper() != "ALLOW_PAPER":
        if "DECISION_GATE_NOT_PASSED" not in no_trade_reasons:
            no_trade_reasons.append("DECISION_GATE_NOT_PASSED")
        reason_codes.append("DECISION_GATE_NOT_PASSED")

    if input_status == "MISSING" or quality_label in ("STALE", "NO_DATA", "MISSING"):
        setup_status = "INSUFFICIENT_DATA"
        setup_class = "INSUFFICIENT_DATA_CLASS"
        setup_grade = "NO_SETUP"
        tradeability = "INSUFFICIENT_DATA"
    elif setup_side not in ("LONG", "SHORT") or flow_component["status"] == "NEUTRAL":
        setup_status = "NO_SETUP"
        setup_class = "NO_SETUP_CLASS"
        setup_grade = "NO_SETUP"
        tradeability = "NO_TRADE"
    elif critical_conflict:
        setup_status = "BLOCKED"
        tradeability = "BLOCKED_BY_STRUCTURE" if "STRUCTURE_CONFLICT" in reason_codes else "BLOCKED_BY_LIQUIDITY" if "LIQUIDITY_CONFLICT" in reason_codes else "BLOCKED_BY_QUALITY"
    elif setup_grade in ("A_PLUS", "A", "B") and flow_confidence >= 0.60 and scenario_component["status"] == "ALIGNED":
        setup_status = "SETUP_READY"
        tradeability = "TRADEABLE_CANDIDATE"
    elif setup_grade in ("C", "WATCH"):
        setup_status = "WATCHLIST"
        tradeability = "WATCH_ONLY"
        if setup_grade == "WATCH":
            setup_grade = "WATCH"
    else:
        setup_status = "NO_SETUP"
        tradeability = "NO_TRADE"

    if setup_status != "SETUP_READY" and setup_grade not in ("NO_SETUP", "WATCH"):
        setup_grade = setup_grade if setup_grade == "B" else "WATCH"

    if setup_class == "L5_RARE_A_PLUS_LONG" and setup_grade != "A_PLUS":
        setup_class = "L2_LONG_CONTINUATION" if setup_family == "CONTINUATION" else "L3_LONG_REVERSAL" if setup_family == "REVERSAL" else "L4_LONG_SWEEP_RECLAIM"
    if setup_class == "S5_RARE_A_PLUS_SHORT" and setup_grade != "A_PLUS":
        setup_class = "S2_SHORT_CONTINUATION" if setup_family == "CONTINUATION" else "S3_SHORT_REVERSAL" if setup_family == "REVERSAL" else "S4_SHORT_SWEEP_RECLAIM"

    if setup_status == "SETUP_READY" and setup_grade == "WATCH":
        setup_status = "WATCHLIST"
        tradeability = "WATCH_ONLY"

    closest_to_setup = (
        "FLOW_CONFIDENCE" if "LOW_FLOW_CONFIDENCE" in no_trade_reasons else
        "STRUCTURE_ALIGNMENT" if "STRUCTURE_INSUFFICIENT" in no_trade_reasons or "STRUCTURE_CONFLICT" in no_trade_reasons else
        "LIQUIDITY_VALIDATION" if "LIQUIDITY_DEPTH_MISSING" in no_trade_reasons or "LIQUIDITY_CONFLICT" in no_trade_reasons else
        "SCENARIO_READINESS" if "SCENARIO_NOT_READY" in no_trade_reasons else
        "QUALITY_RECOVERY" if quality_label in ("DEGRADED", "STALE", "NO_DATA", "MISSING") else
        "SETUP_READY"
    )

    feeds_next = {
        "next_blocks": ["S17_TRADE_PLAN_ENGINE", "S18_DECISION_GATE"],
        "candidate_allowed": setup_status == "SETUP_READY" and tradeability == "TRADEABLE_CANDIDATE",
        "weights": COMPONENT_WEIGHTS,
    }

    record = {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": source,
        "input_status": input_status,
        "setup_status": setup_status,
        "setup_family": setup_family if setup_status != "INSUFFICIENT_DATA" else "UNKNOWN",
        "setup_class": setup_class,
        "setup_side": setup_side,
        "setup_grade": setup_grade,
        "setup_score": setup_score,
        "setup_confidence": setup_confidence,
        "tradeability": tradeability,
        "no_trade_reasons": sorted(set(no_trade_reasons)),
        "supporting_evidence": supporting or ["No meaningful supporting evidence."],
        "blocking_evidence": blocking or ["No critical blockers detected."],
        "flow_component": flow_component,
        "persistence_component": persistence_component,
        "quality_component": quality_component,
        "structure_component": structure_component,
        "liquidity_component": liquidity_component,
        "scenario_component": scenario_component,
        "edge_component": edge_component,
        "rr_readiness_hint": "RR_NOT_EVALUATED_YET",
        "entry_readiness_hint": scenario_component.get("trigger_state", "NO_TRIGGER"),
        "lifecycle_expectation": "NO_LIFECYCLE_CREATED_BY_S29",
        "closest_to_setup": closest_to_setup,
        "required_improvements": sorted(set(required_improvements)) or ["NONE"],
        "data_quality": {
            "quality_label": quality_label,
            "chain_quality_level": chain_level,
            "component_score": quality_component["score"],
        },
        "reason_codes": sorted(set(reason_codes)),
        "feeds_next": feeds_next,
        "execution_safety": dict(SAFETY),
    }
    return record


def _write_report(record: dict[str, Any]) -> None:
    lines = [
        "# S29 Setup Classifier V2 - Latest Report",
        "",
        f"- **Current setup class**: {record['setup_class']}",
        f"- **Current setup grade**: {record['setup_grade']}",
        f"- **Setup side**: {record['setup_side']}",
        f"- **Setup status**: {record['setup_status']}",
        f"- **Setup family**: {record['setup_family']}",
        f"- **Setup score / confidence**: {record['setup_score']} / {record['setup_confidence']}",
        f"- **Tradeability**: {record['tradeability']}",
        f"- **Telegram eligible**: {record['tradeability'] == 'TRADEABLE_CANDIDATE' and record['setup_grade'] in ('A_PLUS', 'A')}",
        "",
        "## Component Scores",
        "",
        f"- quality_component: {record['quality_component']['score']}",
        f"- flow_component: {record['flow_component']['score']}",
        f"- persistence_component: {record['persistence_component']['score']}",
        f"- structure_component: {record['structure_component']['score']}",
        f"- liquidity_component: {record['liquidity_component']['score']}",
        f"- scenario_component: {record['scenario_component']['score']}",
        "",
        "## Supporting Evidence",
        "",
    ]
    lines.extend(f"- {item}" for item in record["supporting_evidence"])
    lines += ["", "## Blocking Evidence", ""]
    lines.extend(f"- {item}" for item in record["blocking_evidence"])
    lines += ["", "## No-Trade Reasons", ""]
    lines.extend(f"- {item}" for item in record["no_trade_reasons"])
    lines += ["", "## Missing Requirements", ""]
    lines.extend(f"- {item}" for item in record["required_improvements"])
    lines += [
        "",
        "## Progression",
        "",
        f"- Why it should/should not proceed to trade plan: {record['tradeability']}",
        f"- closest_to_setup: {record['closest_to_setup']}",
        f"- rr_readiness_hint: {record['rr_readiness_hint']}",
        f"- entry_readiness_hint: {record['entry_readiness_hint']}",
        "",
        "## Safety Confirmation",
        "",
        f"- safe_to_open_real_trade: {record['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {record['execution_safety']['private_api_used']}",
        f"- live_order_sent: {record['execution_safety']['live_order_sent']}",
    ]
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")


def run_setup_classifier_v2() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    inputs = {name: _load_json(path) for name, path in INPUT_PATHS.items()}
    result = compute_setup_classifier_v2(inputs)
    _atomic_write(LATEST_STATE_PATH, json.dumps(result, indent=2, ensure_ascii=False))

    state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S29_SETUP_CLASSIFIER_V2_STATE",
        "last_setup_status": result["setup_status"],
        "last_setup_class": result["setup_class"],
        "last_setup_grade": result["setup_grade"],
        "last_setup_score": result["setup_score"],
        "last_setup_confidence": result["setup_confidence"],
        "last_tradeability": result["tradeability"],
    }
    _atomic_write(S29_STATE_PATH, json.dumps(state, indent=2, ensure_ascii=False))
    _append_jsonl(HISTORY_PATH, result)
    _write_report(result)
    return result
