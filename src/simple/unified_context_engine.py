"""Unified Context State Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, source_state_refs_from_paths, stamp_payload

BLOCK_ID = "UNIFIED_CONTEXT_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_unified_context.json"
HISTORY_PATH = DATA_DIR / "unified_context_history.jsonl"

BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
MARKET_REGIME_PATH = STATE_DIR / "latest_market_regime.json"
INTENT_PATH = STATE_DIR / "latest_intent_analysis.json"
POSITIONING_PATH = STATE_DIR / "latest_positioning_context.json"
MOMENTUM_PATH = STATE_DIR / "latest_momentum_continuation.json"
DOUBLE_DIST_PATH = STATE_DIR / "latest_double_distribution_reversal.json"
TRAP_PATH = STATE_DIR / "latest_trap_trader.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
ATR_PATH = STATE_DIR / "latest_atr_state.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
THREE_SCENARIOS_PATH = STATE_DIR / "latest_three_scenarios.json"
SETUP_ACTIVATION_PATH = STATE_DIR / "latest_setup_family_activation.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _quality_level(score: float) -> str:
    if score <= 0.0:
        return "MISSING"
    if score >= 0.95:
        return "HIGH"
    if score >= 0.75:
        return "OK"
    if score >= 0.5:
        return "REDUCED"
    return "LOW"


def run_unified_context_engine() -> dict[str, Any]:
    runtime_context = current_runtime_context()
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    market_regime = _load_json(MARKET_REGIME_PATH) or {}
    intent_analysis = _load_json(INTENT_PATH) or {}
    positioning = _load_json(POSITIONING_PATH) or {}
    momentum = _load_json(MOMENTUM_PATH) or {}
    double_dist = _load_json(DOUBLE_DIST_PATH) or {}
    trap = _load_json(TRAP_PATH) or {}
    observation = _load_json(OBSERVATION_PATH) or {}
    mtf_dna = _load_json(MTF_DNA_PATH) or {}
    atr = _load_json(ATR_PATH) or {}
    market_structure = _load_json(MARKET_STRUCTURE_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}
    three_scenarios = _load_json(THREE_SCENARIOS_PATH) or {}
    setup_activation = _load_json(SETUP_ACTIVATION_PATH) or {}

    missing_inputs: list[str] = []
    for name, payload in (
        ("latest_business_zone", business_zone),
        ("latest_market_regime", market_regime),
        ("latest_intent_analysis", intent_analysis),
        ("latest_positioning_context", positioning),
        ("latest_momentum_continuation", momentum),
        ("latest_double_distribution_reversal", double_dist),
        ("latest_trap_trader", trap),
        ("latest_market_structure", market_structure),
        ("latest_liquidity_map", liquidity_map),
        ("latest_interpretation", interpretation),
        ("latest_three_scenarios", three_scenarios),
    ):
        if not payload:
            missing_inputs.append(name)

    value_area = business_zone.get("value_area") or {}
    auction_summary = business_zone.get("auction_summary") or {}
    intent = intent_analysis.get("intent_analysis") or {}
    pos = positioning.get("positioning") or {}
    ltf_confirmation = positioning.get("ltf_confirmation") or {}
    int_1m = interpretation.get("1m") or {}
    raw_context = int_1m.get("raw_context") or {}
    tf_1m = (market_structure.get("1m") or {})

    active_setup_families: list[str] = []
    secondary_active_families: list[str] = list(setup_activation.get("secondary_active_families") or [])
    if momentum.get("active"):
        active_setup_families.append("MOMENTUM_CONTINUATION")
    if trap.get("active"):
        active_setup_families.append("TRAP_REVERSAL")
    if double_dist.get("active"):
        active_setup_families.append("DOUBLE_DISTRIBUTION_REVERSAL")
    if setup_activation.get("active_families"):
        active_setup_families = list(dict.fromkeys(setup_activation.get("active_families") or active_setup_families))

    dominant_context = "UNKNOWN"
    activation_dominant_family = str(setup_activation.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY")
    if activation_dominant_family != "NO_ACTIVE_SETUP_FAMILY":
        dominant_context = activation_dominant_family
    elif momentum.get("active"):
        dominant_context = "MOMENTUM_CONTINUATION"
    elif trap.get("active"):
        dominant_context = "TRAP_REVERSAL"
    elif double_dist.get("active"):
        dominant_context = "DOUBLE_DISTRIBUTION_REVERSAL"
    elif str(market_regime.get("regime", "UNKNOWN")) == "BALANCE_MODE":
        dominant_context = "AUCTION_BALANCE"
    elif market_regime:
        dominant_context = "NO_CLEAR_CONTEXT"

    near = liquidity_map.get("near_liquidity") or []
    mid = liquidity_map.get("mid_liquidity") or []
    far = liquidity_map.get("far_liquidity") or []
    target = "UNKNOWN"
    if near or mid or far:
        current_price = liquidity_map.get("current_price")
        above = 0
        below = 0
        for level in liquidity_map.get("detected_levels") or []:
            price = level.get("price")
            if current_price is None or price is None:
                continue
            if price > current_price:
                above += 1
            elif price < current_price:
                below += 1
        if above and below:
            target = "BOTH"
        elif above:
            target = "UP"
        elif below:
            target = "DOWN"
        else:
            target = "NONE"

    business_zone_side = "UNKNOWN"
    value_position = str(value_area.get("value_position", "UNKNOWN"))
    if value_position == "ABOVE_VALUE":
        business_zone_side = "UPPER"
    elif value_position == "BELOW_VALUE":
        business_zone_side = "LOWER"
    elif value_position == "INSIDE_VALUE":
        business_zone_side = "INSIDE"

    liquidity_cluster = "NONE"
    if near:
        liquidity_cluster = "NEAR"
    elif mid:
        liquidity_cluster = "MID"
    elif far:
        liquidity_cluster = "FAR"

    missing_before_setup: list[str] = []
    if str(market_regime.get("regime", "UNKNOWN")) == "UNKNOWN":
        missing_before_setup.append("MARKET_REGIME_UNKNOWN")
    if value_position == "UNKNOWN":
        missing_before_setup.append("VALUE_POSITION_UNKNOWN")
    if str(raw_context.get("cvd_state", "UNKNOWN")) == "UNKNOWN":
        missing_before_setup.append("ORDERFLOW_STATE_UNKNOWN")
    if not active_setup_families:
        missing_before_setup.append("NO_ACTIVE_SETUP_FAMILY")
    if setup_activation.get("missing"):
        missing_before_setup = list(setup_activation.get("missing") or missing_before_setup)

    score = 0.0
    available_count = 0
    for payload in (
        business_zone,
        market_regime,
        intent_analysis,
        positioning,
        momentum,
        double_dist,
        trap,
        market_structure,
        liquidity_map,
        interpretation,
        three_scenarios,
    ):
        if payload:
            available_count += 1
    score = min(1.0, available_count / 11.0)
    dominant_setup_family = str(setup_activation.get("dominant_setup_family") or "")
    if not dominant_setup_family:
        dominant_setup_family = dominant_context if dominant_context in {
            "MOMENTUM_CONTINUATION",
            "TRAP_REVERSAL",
            "DOUBLE_DISTRIBUTION_REVERSAL",
        } else "NO_ACTIVE_SETUP_FAMILY"
    ready_for_paper_research = bool(setup_activation.get("ready_for_paper_research")) if setup_activation else (not missing_before_setup and dominant_context != "UNKNOWN")
    activation_score = float(setup_activation.get("activation_score") or 0.0)
    activation_band = str(setup_activation.get("activation_band") or "WATCH_ONLY")
    raw_activation_score = float(setup_activation.get("raw_activation_score") or 0.0)
    adjusted_activation_score = float(setup_activation.get("adjusted_activation_score") or activation_score or 0.0)
    setup_risk_tags = list(setup_activation.get("risk_tags") or [])
    setup_direction = str(setup_activation.get("direction") or "NEUTRAL")
    setup_blocking_reasons = list(setup_activation.get("blocking_reasons") or [])
    score_breakdown = dict(setup_activation.get("score_breakdown") or {})
    direction_resolution = dict(setup_activation.get("direction_resolution") or {})

    output = {
        "symbol": str(market_regime.get("symbol") or business_zone.get("symbol") or "BTCUSDT"),
        "source": {
            "source_mode": "UNIFIED_CONTEXT_SYNTHESIS",
        },
        "observation": observation,
        "mtf_dna": mtf_dna,
        "atr": atr,
        "structure": market_structure,
        "liquidity": liquidity_map,
        "interpretation": interpretation,
        "scenario": three_scenarios,
        "business_zone": business_zone,
        "regime": market_regime,
        "intent": intent_analysis,
        "positioning": positioning,
        "setup_family_activation": setup_activation,
        "auction_context": {
            "regime": market_regime.get("regime", "UNKNOWN"),
            "value_position": value_position,
            "acceptance": auction_summary.get("acceptance", False),
            "rejection": auction_summary.get("rejection", False),
            "value_migration": value_area.get("value_migration", "UNKNOWN"),
        },
        "orderflow_context": {
            "delta_state": raw_context.get("cvd_state", "UNKNOWN"),
            "cvd_divergence": bool((double_dist.get("conditions") or {}).get("cvd_price_divergence", False)),
            "absorption": str(intent.get("intent", "UNKNOWN")) == "ABSORPTION",
            "exhaustion": bool((double_dist.get("conditions") or {}).get("exhaustion_detected", False)),
            "imbalance": "BUY" if str(raw_context.get("cvd_state", "UNKNOWN")) == "BUY_PRESSURE" else "SELL" if str(raw_context.get("cvd_state", "UNKNOWN")) == "SELL_PRESSURE" else "NONE" if raw_context else "UNKNOWN",
        },
        "liquidity_context": {
            "target": target,
            "npoc_near": False,
            "business_zone": business_zone_side,
            "liquidity_cluster": liquidity_cluster,
        },
        "intent_context": {
            "iceberg": bool((intent_analysis.get("iceberg") or {}).get("detected", False)),
            "spoof": bool((intent_analysis.get("spoof") or {}).get("detected", False)),
            "trapped_side": intent.get("trapped_side", "UNKNOWN"),
        },
        "positioning_context": {
            "crowded_side": pos.get("crowded_side", "UNKNOWN"),
            "squeeze_risk": pos.get("squeeze_risk", "UNKNOWN"),
        },
        "active_setup_families": active_setup_families,
        "secondary_active_families": secondary_active_families,
        "dominant_context": dominant_context,
        "directional_bias": str(market_regime.get("directional_bias") or setup_direction or "UNKNOWN"),
        "dominant_setup_family": dominant_setup_family,
        "activation_score": activation_score,
        "activation_band": activation_band,
        "raw_activation_score": raw_activation_score,
        "adjusted_activation_score": adjusted_activation_score,
        "setup_risk_tags": setup_risk_tags,
        "ready_for_paper_research": ready_for_paper_research,
        "setup_direction": setup_direction,
        "blocking_reasons": setup_blocking_reasons,
        "setup_blocking_reasons": setup_blocking_reasons,
        "score_breakdown": score_breakdown,
        "direction_resolution": direction_resolution,
        "risk_tags": setup_risk_tags,
        "missing": missing_before_setup,
        "source_state_refs": source_state_refs_from_paths(
            {
                "observation": OBSERVATION_PATH,
                "mtf_dna": MTF_DNA_PATH,
                "atr": ATR_PATH,
                "structure": MARKET_STRUCTURE_PATH,
                "liquidity": LIQUIDITY_MAP_PATH,
                "interpretation": INTERPRETATION_PATH,
                "scenario": THREE_SCENARIOS_PATH,
                "business_zone": BUSINESS_ZONE_PATH,
                "regime": MARKET_REGIME_PATH,
                "intent": INTENT_PATH,
                "positioning": POSITIONING_PATH,
                "setup_family_activation": SETUP_ACTIVATION_PATH,
            }
        ),
        "readiness": {
            "context_ready_for_setup_selection": ready_for_paper_research,
            "missing_before_setup": missing_before_setup,
        },
        "is_trade_signal": False,
        "reason_codes": [
            f"DOMINANT_{dominant_context}",
            f"STRUCTURE_{str(tf_1m.get('structure_label', 'UNKNOWN'))}",
            f"LTF_TRAP_{str(ltf_confirmation.get('trap_context', 'UNKNOWN'))}",
            f"DQ_{_quality_level(score)}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            *missing_inputs,
        ],
        "data_quality": {
            "level": _quality_level(score),
            "missing_inputs": missing_inputs,
        },
        "feeds_next": [
            "S15_FLOW_TO_SETUP_CONTEXT",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }
    output = stamp_payload(output, BLOCK_ID, output["symbol"], runtime_context)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_unified_context_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
