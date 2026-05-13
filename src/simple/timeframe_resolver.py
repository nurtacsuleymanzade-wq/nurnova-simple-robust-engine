from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.simple.model_timeframe_profile import get_timeframe_profile
from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import (
    current_runtime_context,
    load_json,
    source_state_refs_from_paths,
    stamp_payload,
    write_json,
)

BLOCK_ID = "TIMEFRAME_RESOLVER"
STATE_DIR = Path("state/simple")

OUTPUT_PATH = epoch_state_path("latest_timeframe_resolution.json")
HISTORY_PATH = epoch_data_path("timeframe_resolution_history.jsonl")

MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
THREE_SCENARIOS_PATH = STATE_DIR / "latest_three_scenarios.json"
SETUP_ACTIVATION_PATH = STATE_DIR / "latest_setup_family_activation.json"
UNIFIED_CONTEXT_PATH = STATE_DIR / "latest_unified_context.json"

_CORE_TFS = ("1m", "5m", "15m", "1h")
_CTX_TFS = ("15m", "1h", "4h")


def _upper(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text.upper() if text else fallback


def _nonempty_timeframes(payload: dict[str, Any], candidates: tuple[str, ...]) -> set[str]:
    return {tf for tf in candidates if isinstance(payload.get(tf), dict) and payload.get(tf)}


def _confidence_bucket(level: str) -> float:
    return {"HIGH": 1.0, "OK": 0.85, "MEDIUM": 0.7, "REDUCED": 0.55, "LOW": 0.4, "MISSING": 0.0}.get(level, 0.5)


def _pick_first(choices: list[str], available: set[str], fallback: str) -> str:
    for choice in choices:
        if choice in available:
            return choice
    return fallback


def _reason_sort_key(tf: str) -> int:
    return {"1m": 0, "5m": 1, "15m": 2, "1h": 3, "4h": 4}.get(tf, 9)


def _build_tf_evidence(
    mtf_dna: dict[str, Any],
    market_structure: dict[str, Any],
    interpretation: dict[str, Any],
    liquidity_map: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    evidence_map: dict[str, dict[str, Any]] = {}
    reason_map: dict[str, list[str]] = {}
    for tf in _CORE_TFS:
        dna_tf = mtf_dna.get(tf) or {}
        structure_tf = market_structure.get(tf) or {}
        interp_tf = interpretation.get(tf) or {}
        reasons: list[str] = []
        if dna_tf:
            candle_label = _upper((dna_tf.get("candle_category") or {}).get("primary") or dna_tf.get("candle_category_label"))
            if candle_label and candle_label != "UNKNOWN":
                reasons.append(f"{tf} candle {candle_label.lower().replace('_', ' ')}")
            liquidity_event = _upper(dna_tf.get("liquidity_event"))
            if liquidity_event and liquidity_event not in {"UNKNOWN", "WALL_REACTION"}:
                reasons.append(f"{tf} {liquidity_event.lower().replace('_', ' ')}")
        if structure_tf:
            structure_label = _upper(structure_tf.get("structure_label"))
            trend_state = _upper(structure_tf.get("trend_state"))
            if structure_label and structure_label not in {"UNKNOWN", "RANGE"}:
                reasons.append(f"{tf} structure {structure_label.lower()}")
            if trend_state and trend_state not in {"UNKNOWN", "RANGE"}:
                reasons.append(f"{tf} trend {trend_state.lower()}")
            if bool(structure_tf.get("bos_detected")):
                reasons.append(f"{tf} break of structure")
            if bool(structure_tf.get("choch_detected")):
                reasons.append(f"{tf} change of character")
        if interp_tf:
            interp_liquidity = _upper(((interp_tf.get("raw_context") or {}).get("liquidity_event")) or interp_tf.get("liquidity_event"))
            if interp_liquidity and interp_liquidity not in {"UNKNOWN", "WALL_REACTION"}:
                reasons.append(f"{tf} {interp_liquidity.lower().replace('_', ' ')}")
        evidence_map[tf] = {
            "available": bool(dna_tf or structure_tf or interp_tf),
            "dna_quality": (dna_tf.get("data_quality") or {}).get("level"),
            "structure_quality": (structure_tf.get("data_quality") or {}).get("level"),
            "interpretation_quality": (interp_tf.get("data_quality") or {}).get("level"),
            "candle_category": (dna_tf.get("candle_category") or {}).get("primary") or dna_tf.get("candle_category_label"),
            "structure_label": structure_tf.get("structure_label"),
            "trend_state": structure_tf.get("trend_state"),
            "liquidity_event": dna_tf.get("liquidity_event") or ((interp_tf.get("raw_context") or {}).get("liquidity_event")),
            "reason_codes": sorted(set(reasons)),
        }
        reason_map[tf] = sorted(set(reasons))

    if liquidity_map:
        for level in liquidity_map.get("near_liquidity") or []:
            for code in level.get("reason_codes") or []:
                if not str(code).startswith("TF_"):
                    continue
                tf = str(code).split("_", 1)[1]
                if tf in reason_map:
                    reason_map[tf].append(f"{tf} liquidity level mapped")
        for tf in _CORE_TFS:
            evidence_map.setdefault(tf, {}).setdefault("reason_codes", [])
            evidence_map[tf]["reason_codes"] = sorted(set([*evidence_map[tf]["reason_codes"], *reason_map.get(tf, [])]))
    return evidence_map, {tf: sorted(set(items)) for tf, items in reason_map.items()}


def _select_primary_tf(profile: dict[str, Any], setup: dict[str, Any], evidence_map: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    preferred = list(profile.get("preferred_primary_tf") or [])
    active = {tf for tf, payload in evidence_map.items() if payload.get("available")}
    primary_tf = _pick_first(preferred, active, preferred[0] if preferred else "5m")
    for tf in preferred:
        if evidence_map.get(tf, {}).get("reason_codes"):
            reasons.append(f"primary aligned to {tf} profile")
            primary_tf = tf
            break
    dominant_setup = _upper(setup.get("dominant_setup_family"))
    if dominant_setup == "TRAP_REVERSAL" and evidence_map.get("5m", {}).get("available"):
        primary_tf = "5m"
        reasons.append("5m trap profile bias")
    elif dominant_setup == "DOUBLE_DISTRIBUTION_REVERSAL" and evidence_map.get("15m", {}).get("available"):
        primary_tf = "15m"
        reasons.append("15m value rotation bias")
    elif dominant_setup == "LIQUIDITY_SWEEP_REVERSAL" and evidence_map.get("15m", {}).get("reason_codes"):
        primary_tf = "15m"
        reasons.append("15m liquidity sweep bias")
    return primary_tf, reasons


def _select_trigger_tf(profile: dict[str, Any], primary_tf: str, evidence_map: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    allowed = list(profile.get("allowed_trigger_tf") or [])
    reasons: list[str] = []
    trigger_tf = _pick_first(allowed, {tf for tf, payload in evidence_map.items() if payload.get("reason_codes")}, allowed[0] if allowed else primary_tf)
    for tf in allowed:
        if evidence_map.get(tf, {}).get("reason_codes"):
            trigger_tf = tf
            reasons.append(f"{tf} trigger confirmation")
            break
    if trigger_tf not in allowed and allowed:
        trigger_tf = allowed[0]
    return trigger_tf, reasons


def _select_context_tf(profile: dict[str, Any], evidence_map: dict[str, dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    available = {tf for tf in _CTX_TFS if evidence_map.get(tf, {}).get("available")}
    reasons: list[str] = []
    missing_inputs: list[str] = []
    choices = list(profile.get("context_tf") or [])
    context_tf = _pick_first(choices, available, choices[0] if choices else "15m")
    if context_tf not in available:
        if "15m" in available:
            context_tf = "15m"
            reasons.append("15m context fallback due to missing higher timeframe")
        else:
            missing_inputs.extend(["latest_interpretation:15m", "latest_market_structure:15m"])
    if "1h" in choices and "1h" not in available:
        missing_inputs.append("1h_context_missing")
    if "4h" in choices and "4h" not in available:
        missing_inputs.append("4h_context_missing")
    if evidence_map.get(context_tf, {}).get("reason_codes"):
        reasons.append(f"{context_tf} context in use")
    return context_tf, reasons, missing_inputs


def _select_structure_tf(primary_tf: str, trigger_tf: str, context_tf: str, market_structure: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    for tf in (primary_tf, trigger_tf, context_tf, "15m", "5m", "1m", "1h"):
        structure_tf = market_structure.get(tf) or {}
        if not structure_tf:
            continue
        if structure_tf.get("bos_detected") or structure_tf.get("choch_detected") or _upper(structure_tf.get("structure_label")) not in {"", "UNKNOWN"}:
            reasons.append(f"{tf} structure reference")
            return tf, reasons
    return primary_tf, reasons


def _timeframe_confidence(
    profile: dict[str, Any],
    setup: dict[str, Any],
    primary_tf: str,
    trigger_tf: str,
    context_tf: str,
    evidence_map: dict[str, dict[str, Any]],
    missing_inputs: list[str],
) -> float:
    score = 0.45
    score += 0.15 if primary_tf in (profile.get("preferred_primary_tf") or []) else 0.0
    score += 0.10 if trigger_tf in (profile.get("allowed_trigger_tf") or []) else 0.0
    score += 0.10 if context_tf in (profile.get("context_tf") or []) else 0.0
    score += min(float(setup.get("activation_score") or 0.0), 1.0) * 0.15
    agreement = 0
    for tf in {primary_tf, trigger_tf, context_tf}:
        if evidence_map.get(tf, {}).get("reason_codes"):
            agreement += 1
    score += agreement * 0.05
    if primary_tf == "1m" and context_tf in {"1h", "4h"}:
        score -= 0.10
    if trigger_tf == context_tf and trigger_tf not in {"15m", "1h"}:
        score -= 0.05
    score -= min(len(missing_inputs), 3) * 0.07
    if int(setup.get("conflict_count") or 0) > 0:
        score -= 0.10
    return round(max(0.0, min(1.0, score)), 4)


def run_timeframe_resolver() -> dict[str, Any]:
    context = current_runtime_context()
    mtf_dna = load_json(MTF_DNA_PATH) or {}
    market_structure = load_json(MARKET_STRUCTURE_PATH) or {}
    liquidity_map = load_json(LIQUIDITY_MAP_PATH) or {}
    interpretation = load_json(INTERPRETATION_PATH) or {}
    scenarios = load_json(THREE_SCENARIOS_PATH) or {}
    setup = load_json(SETUP_ACTIVATION_PATH) or {}
    unified = load_json(UNIFIED_CONTEXT_PATH) or {}

    profile = get_timeframe_profile(
        setup.get("dominant_setup_family") or unified.get("dominant_setup_family"),
        ((setup.get("source_models") or [{}])[0]).get("model_id"),
    )
    evidence_map, reason_map = _build_tf_evidence(mtf_dna, market_structure, interpretation, liquidity_map)
    primary_tf, primary_reasons = _select_primary_tf(profile, setup, evidence_map)
    trigger_tf, trigger_reasons = _select_trigger_tf(profile, primary_tf, evidence_map)
    context_tf, context_reasons, missing_inputs = _select_context_tf(profile, evidence_map)
    structure_tf, structure_reasons = _select_structure_tf(primary_tf, trigger_tf, context_tf, market_structure)

    reason_items: list[str] = []
    reason_items.extend(primary_reasons)
    reason_items.extend(context_reasons)
    reason_items.extend(trigger_reasons)
    reason_items.extend(structure_reasons)
    for tf in sorted({primary_tf, trigger_tf, context_tf}, key=_reason_sort_key):
        reason_items.extend(reason_map.get(tf, [])[:2])
    timeframe_reason = list(dict.fromkeys(reason_items))[:6]
    if not timeframe_reason:
        timeframe_reason = [f"{primary_tf} default profile selection"]

    hold = dict(profile.get("expected_hold_minutes") or {})
    min_hold = int(hold.get("min") or 15)
    max_hold = int(hold.get("max") or 90)
    confidence = _timeframe_confidence(profile, setup, primary_tf, trigger_tf, context_tf, evidence_map, missing_inputs)

    missing_payload_inputs = [
        name
        for name, payload in {
            "latest_mtf_candle_dna": mtf_dna,
            "latest_market_structure": market_structure,
            "latest_liquidity_map": liquidity_map,
            "latest_interpretation": interpretation,
            "latest_three_scenarios": scenarios,
            "latest_setup_family_activation": setup,
            "latest_unified_context": unified,
        }.items()
        if not payload
    ]
    missing_inputs = sorted(set([*missing_inputs, *missing_payload_inputs]))
    data_level = "HIGH"
    if missing_inputs:
        data_level = "MEDIUM" if len(missing_inputs) <= 3 else "LOW"
    if confidence < 0.45:
        data_level = "LOW"

    output = stamp_payload(
        {
            "symbol": str(setup.get("symbol") or unified.get("symbol") or mtf_dna.get("symbol") or "BTCUSDT"),
            "block_id": BLOCK_ID,
            "epoch_id": ACTIVE_EPOCH_ID,
            "source": {"source_mode": "TIMEFRAME_PROFILE_AND_STATE_RESOLUTION"},
            "setup_family": profile.get("resolved_setup_family"),
            "model_id": ((setup.get("source_models") or [{}])[0]).get("model_id"),
            "direction": _upper(setup.get("direction") or unified.get("setup_direction"), "NEUTRAL"),
            "primary_tf": primary_tf,
            "trigger_tf": trigger_tf,
            "context_tf": context_tf,
            "structure_tf": structure_tf,
            "expected_hold_min_minutes": min_hold,
            "expected_hold_max_minutes": max_hold,
            "expected_hold_label": f"{min_hold}m–{max_hold}m" if max_hold < 60 else (
                f"{min_hold}m–{max_hold}m" if min_hold < 60 else f"{min_hold // 60}h–{max_hold // 60}h"
            ),
            "timeframe_confidence": confidence,
            "timeframe_reason": timeframe_reason,
            "tf_evidence": {
                tf: evidence_map.get(tf, {}) for tf in _CORE_TFS
            },
            "profile": {
                "preferred_primary_tf": list(profile.get("preferred_primary_tf") or []),
                "allowed_trigger_tf": list(profile.get("allowed_trigger_tf") or []),
                "context_tf_candidates": list(profile.get("context_tf") or []),
                "plan_style": profile.get("plan_style"),
            },
            "source_state_refs": source_state_refs_from_paths(
                {
                    "mtf_candle_dna": MTF_DNA_PATH,
                    "market_structure": MARKET_STRUCTURE_PATH,
                    "liquidity_map": LIQUIDITY_MAP_PATH,
                    "interpretation": INTERPRETATION_PATH,
                    "three_scenarios": THREE_SCENARIOS_PATH,
                    "setup_activation": SETUP_ACTIVATION_PATH,
                    "unified_context": UNIFIED_CONTEXT_PATH,
                }
            ),
            "data_quality": {
                "level": data_level,
                "missing_inputs": missing_inputs,
            },
            "reason_codes": [
                f"PRIMARY_TF_{primary_tf}",
                f"TRIGGER_TF_{trigger_tf}",
                f"CONTEXT_TF_{context_tf}",
                f"STRUCTURE_TF_{structure_tf}",
                f"CONFIDENCE_{int(confidence * 100)}",
                "PAPER_ONLY",
                "NO_LIVE_EXECUTION",
                "NO_PRIVATE_API",
            ],
            "feeds_next": ["PAPER_TRADE_FACTORY", "RESEARCH_PAPER_LIFECYCLE_ENGINE"],
            "execution_safety": {
                "live_order_sent": False,
                "private_api_used": False,
            },
        },
        BLOCK_ID,
        str(setup.get("symbol") or unified.get("symbol") or "BTCUSDT"),
        context,
    )

    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("timeframe_resolution_history.jsonl", output)
    return output


def main() -> None:
    print(json.dumps(run_timeframe_resolver(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
