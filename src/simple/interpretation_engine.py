"""Interpretation Engine.

Converts observation, candle DNA, structure, liquidity, and ATR context into
descriptive per-timeframe market interpretation without generating trade
signals or one-way predictions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "INTERPRETATION_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_interpretation.json"
HISTORY_PATH = DATA_DIR / "interpretation_history.jsonl"

OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
ATR_STATE_PATH = STATE_DIR / "latest_atr_state.json"

FLOW_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
FLOW_PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
DEPTH_MEMORY_PATH = STATE_DIR / "latest_depth_liquidity_memory.json"
WALL_LIFECYCLE_PATH = STATE_DIR / "latest_wall_lifecycle.json"

TIMEFRAMES = ["1s", "3s", "5s", "15s", "1m", "3m", "5m", "15m", "1h", "4h", "12h", "1d"]

REQUIRED_INPUT_PATHS = {
    "latest_observation_factory": OBSERVATION_PATH,
    "latest_mtf_candle_dna": MTF_DNA_PATH,
    "latest_market_structure": MARKET_STRUCTURE_PATH,
    "latest_liquidity_map": LIQUIDITY_MAP_PATH,
    "latest_atr_state": ATR_STATE_PATH,
}

OPTIONAL_INPUT_PATHS = {
    "latest_flow_evidence": FLOW_EVIDENCE_PATH,
    "latest_flow_persistence": FLOW_PERSISTENCE_PATH,
    "latest_depth_liquidity_memory": DEPTH_MEMORY_PATH,
    "latest_wall_lifecycle": WALL_LIFECYCLE_PATH,
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


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_price(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    return f"{value:.2f}"


def _normalize_atr_tf_key(tf: str) -> str:
    if tf in ("1s", "3s", "5s", "15s"):
        return "1m"
    return tf


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


def _current_price(
    observation: dict[str, Any] | None,
    liquidity_map: dict[str, Any] | None,
    mtf_dna: dict[str, Any] | None,
) -> float | None:
    price = _safe_float(((observation or {}).get("market_snapshot") or {}).get("price"))
    if price is not None:
        return price
    price = _safe_float((liquidity_map or {}).get("current_price"))
    if price is not None:
        return price
    return _safe_float((((mtf_dna or {}).get("1s") or {}).get("close")))


def _dedup_levels(levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()
    for level in levels:
        price = _safe_float(level.get("price"))
        liquidity_type = str(level.get("liquidity_type", "unknown"))
        if price is None:
            continue
        key = (round(price, 8), liquidity_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(level)
    return deduped


def _nearest_levels(
    liquidity_map: dict[str, Any] | None,
    current_price: float | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    levels = _dedup_levels(list((liquidity_map or {}).get("detected_levels") or []))
    if current_price is None:
        return levels[:2], []

    above: list[dict[str, Any]] = []
    below: list[dict[str, Any]] = []
    for level in levels:
        price = _safe_float(level.get("price"))
        if price is None:
            continue
        if price > current_price:
            above.append(level)
        elif price < current_price:
            below.append(level)
    above.sort(key=lambda item: _safe_float(item.get("price")) or 0.0)
    below.sort(key=lambda item: _safe_float(item.get("price")) or 0.0, reverse=True)
    return above, below


def _liquidity_level_text(level: dict[str, Any] | None) -> str | None:
    if not level:
        return None
    price = _safe_float(level.get("price"))
    liquidity_type = str(level.get("liquidity_type", "liquidity")).replace("_", " ")
    return f"{_format_price(price)} ({liquidity_type})"


def _structure_context(structure_payload: dict[str, Any], mtf_payload: dict[str, Any]) -> str:
    structure_label = str(structure_payload.get("structure_label") or mtf_payload.get("structure_label") or "UNKNOWN")
    trend_state = str(structure_payload.get("trend_state", "UNKNOWN"))

    if structure_label == "HH":
        return "HH_BREAK"
    if structure_label == "HL":
        return "HL_FORMING"
    if structure_label == "LH":
        return "LH_FORMING"
    if structure_label == "LL":
        return "LL_BREAK"
    if structure_label in ("RANGE", "EQH", "EQL"):
        return "RANGE"
    if structure_label == "BOS":
        if trend_state == "DOWNTREND":
            return "LL_BREAK"
        return "HH_BREAK"
    if structure_label in ("CHOCH", "MSS"):
        if trend_state == "UPTREND":
            return "HL_FORMING"
        if trend_state == "DOWNTREND":
            return "LH_FORMING"
        return "RANGE"
    return "UNKNOWN"


def _cvd_state(candle_label: str, candle_reason_codes: list[str], delta: float | None, candle_truth: str) -> str:
    if "SELL_PRESSURE_ABSORBED" in candle_reason_codes:
        return "SELL_PRESSURE_ABSORBED"
    if "BUY_PRESSURE_ABSORBED" in candle_reason_codes:
        return "BUY_PRESSURE_ABSORBED"
    if candle_label == "SELL_ABSORPTION" and (delta is None or delta < 0):
        return "SELL_PRESSURE_ABSORBED"
    if candle_label == "BUY_ABSORPTION" and (delta is None or delta > 0):
        return "BUY_PRESSURE_ABSORBED"
    if delta is None:
        return "UNKNOWN"
    if delta > 0 and candle_truth in ("FAKE_BEARISH",):
        return "BUY_PRESSURE_ABSORBED"
    if delta < 0 and candle_truth in ("FAKE_BULLISH",):
        return "SELL_PRESSURE_ABSORBED"
    if delta > 0:
        return "BUY_PRESSURE"
    if delta < 0:
        return "SELL_PRESSURE"
    return "BALANCED"


def _liquidity_event(candle_label: str, mtf_event: str, wall_lifecycle: dict[str, Any] | None) -> str:
    if candle_label in ("LIQUIDITY_SWEEP_DOWN", "STOP_RUN_DOWN"):
        return "LOW_SWEEP"
    if candle_label in ("LIQUIDITY_SWEEP_UP", "STOP_RUN_UP"):
        return "HIGH_SWEEP"
    if mtf_event == "WALL_REACTION":
        return "WALL_REACTION"
    if mtf_event in ("SWEEP", "SPOOF_RISK"):
        return "UNKNOWN"
    if ((wall_lifecycle or {}).get("liquidity_intelligence") or {}).get("sweep_occurred"):
        return "UNKNOWN"
    if mtf_event == "NONE":
        return "NONE"
    return "UNKNOWN"


def _higher_tf(tf: str) -> str | None:
    try:
        index = TIMEFRAMES.index(tf)
    except ValueError:
        return None
    if index + 1 >= len(TIMEFRAMES):
        return None
    return TIMEFRAMES[index + 1]


def _direction_bias_from_structure(structure: str) -> str:
    if structure in ("HH_BREAK", "HL_FORMING"):
        return "BULLISH"
    if structure in ("LH_FORMING", "LL_BREAK"):
        return "BEARISH"
    if structure == "RANGE":
        return "NEUTRAL"
    return "UNKNOWN"


def _absorption_text(candle_label: str, candle_reason_codes: list[str], delta: float | None) -> str | None:
    if candle_label not in ("SELL_ABSORPTION", "BUY_ABSORPTION"):
        return None
    if "SELL_PRESSURE_ABSORBED" in candle_reason_codes or delta is not None and delta < 0:
        return "Sellers were aggressive, but limit buyers absorbed the pressure."
    if "BUY_PRESSURE_ABSORBED" in candle_reason_codes or delta is not None and delta > 0:
        return "Buyers were aggressive, but limit sellers absorbed the pressure."
    return "Absorption is present, but the attacking side is not fully confirmed."


def _footprint_summary(
    candle_label: str,
    candle_reason_codes: list[str],
    candle_truth: str,
    delta: float | None,
    close_position: str,
) -> str:
    absorption_text = _absorption_text(candle_label, candle_reason_codes, delta)
    if absorption_text:
        return absorption_text
    if candle_label == "LIQUIDITY_SWEEP_UP":
        return "Price probed above prior highs and failed to hold that extension."
    if candle_label == "LIQUIDITY_SWEEP_DOWN":
        return "Price probed below prior lows and returned back inside the auction."
    if candle_label == "STOP_RUN_UP":
        return "A stop-run above highs occurred and was met with rejection."
    if candle_label == "STOP_RUN_DOWN":
        return "A stop-run below lows occurred and price recovered from the flush."
    if candle_truth == "REAL_BULLISH":
        if close_position == "NEAR_HIGH":
            return "Buyers lifted the candle and the close held near the high."
        return "Buyers won the candle, but the close did not fully hold the high."
    if candle_truth == "REAL_BEARISH":
        if close_position == "NEAR_LOW":
            return "Sellers pressed the candle and the close held near the low."
        return "Sellers won the candle, but the close did not fully hold the low."
    if candle_truth in ("FAKE_BULLISH", "WEAK_BULLISH"):
        return "Price closed up, but the underlying aggressive flow did not fully confirm that push."
    if candle_truth in ("FAKE_BEARISH", "WEAK_BEARISH"):
        return "Price closed down, but the underlying aggressive flow did not fully confirm that drop."
    if delta == 0:
        return "The candle printed with balanced aggressive flow."
    return "Footprint context is mixed and does not resolve cleanly."


def _structure_summary(structure_payload: dict[str, Any], structure: str) -> str:
    structure_label = str(structure_payload.get("structure_label", "UNKNOWN"))
    trend_state = str(structure_payload.get("trend_state", "UNKNOWN"))

    if structure_label == "BOS":
        return f"Structure shows a break of structure with trend state {trend_state}."
    if structure_label == "CHOCH":
        return f"Structure shows a change of character against the prior {trend_state.lower()} context."
    if structure_label == "MSS":
        return "Structure is in transition after a market structure shift."
    if structure == "HH_BREAK":
        return "Higher-high structure is forming and upside continuation remains structurally possible."
    if structure == "HL_FORMING":
        return "Price is holding a higher-low type structure inside the active swing."
    if structure == "LH_FORMING":
        return "Price is forming a lower-high type structure and rallies are meeting resistance."
    if structure == "LL_BREAK":
        return "Lower-low structure is active and downside continuation remains structurally possible."
    if structure == "RANGE":
        return "Structure remains range-bound with no accepted directional break."
    return "Structure context is not resolved from the available candles."


def _liquidity_summary(
    current_price: float | None,
    above_levels: list[dict[str, Any]],
    below_levels: list[dict[str, Any]],
    liquidity_event: str,
) -> str:
    nearest_above = _liquidity_level_text(above_levels[0]) if above_levels else None
    nearest_below = _liquidity_level_text(below_levels[0]) if below_levels else None

    if nearest_above and nearest_below:
        text = f"Nearest upside liquidity sits at {nearest_above}, while nearest downside liquidity sits at {nearest_below}."
    elif nearest_above:
        text = f"Nearest mapped liquidity above price sits at {nearest_above}."
    elif nearest_below:
        text = f"Nearest mapped liquidity below price sits at {nearest_below}."
    else:
        text = "No verified nearby liquidity targets are available from the current map."

    if liquidity_event == "LOW_SWEEP":
        return f"{text} The latest candle also shows a low sweep reaction."
    if liquidity_event == "HIGH_SWEEP":
        return f"{text} The latest candle also shows a high sweep reaction."
    if liquidity_event == "WALL_REACTION":
        return f"{text} Price is also reacting around visible resting wall liquidity."
    if current_price is None:
        return "Liquidity levels are present, but current price is not available for distance context."
    return text


def _trend_summary(
    tf: str,
    structure: str,
    structure_payload: dict[str, Any],
    market_structure: dict[str, Any] | None,
    flow_persistence: dict[str, Any] | None,
) -> str:
    higher_tf = _higher_tf(tf)
    higher_payload = (market_structure or {}).get(higher_tf or "") or {}
    higher_structure = _structure_context(higher_payload, {})
    current_bias = _direction_bias_from_structure(structure)
    higher_bias = _direction_bias_from_structure(higher_structure)
    persistence_label = str((flow_persistence or {}).get("persistence_label", "UNKNOWN"))

    if current_bias in ("BULLISH", "BEARISH") and higher_bias == current_bias:
        return f"Current and next-higher timeframe structure both lean {current_bias.lower()}."
    if current_bias in ("BULLISH", "BEARISH") and higher_bias == "NEUTRAL":
        return f"Lower timeframe structure leans {current_bias.lower()}, but the next-higher timeframe is still range-bound."
    if current_bias in ("BULLISH", "BEARISH") and higher_bias not in ("UNKNOWN", current_bias):
        return "Structure is mixed: lower timeframe direction conflicts with higher timeframe structure."
    if persistence_label in ("SUSTAINED_LONG_PRESSURE", "SUSTAINED_SHORT_PRESSURE"):
        return f"Flow persistence remains {persistence_label.lower()} even though structure is not fully directional yet."
    if str(structure_payload.get("trend_state", "UNKNOWN")) == "RANGE":
        return "Trend state remains range and no timeframe acceptance has broken that balance."
    return "Trend context is mixed or underdeveloped."


def _pressure_summary(
    candle_label: str,
    delta: float | None,
    candle_truth: str,
    cvd_state: str,
    flow_evidence: dict[str, Any] | None,
) -> str:
    pressure_label = str((((flow_evidence or {}).get("pressure_evidence") or {}).get("pressure_label")) or "UNKNOWN")
    if cvd_state == "SELL_PRESSURE_ABSORBED":
        return "Sell pressure was active, but price response suggests that selling was absorbed rather than accepted lower."
    if cvd_state == "BUY_PRESSURE_ABSORBED":
        return "Buy pressure was active, but price response suggests that buying was absorbed rather than accepted higher."
    if delta is None:
        return "Pressure context is unknown because delta is missing."
    if delta > 0 and candle_truth == "REAL_BULLISH":
        return "Positive delta confirms the candle direction, so continuation pressure is present."
    if delta < 0 and candle_truth == "REAL_BEARISH":
        return "Negative delta confirms the candle direction, so continuation pressure is present."
    if delta > 0 and candle_truth in ("FAKE_BEARISH", "WEAK_BEARISH"):
        return "Positive delta disagrees with the candle close, which creates buy-pressure absorption risk."
    if delta < 0 and candle_truth in ("FAKE_BULLISH", "WEAK_BULLISH"):
        return "Negative delta disagrees with the candle close, which creates sell-pressure absorption risk."
    if pressure_label != "UNKNOWN":
        return f"Flow evidence reads {pressure_label.lower()}, but candle confirmation is limited."
    if candle_label == "NORMAL_BALANCED":
        return "Aggressive pressure is balanced and no side is forcing acceptance."
    return "Pressure is present, but follow-through is not clear."


def _trap_summary(
    candle_label: str,
    candle_truth: str,
    delta: float | None,
    liquidity_event: str,
) -> str:
    if candle_label == "TRAP_CANDLE":
        return "The candle category itself flags trap risk: aggressive flow and close location disagree."
    if candle_label in ("LIQUIDITY_SWEEP_UP", "STOP_RUN_UP"):
        return "A high-side sweep is present; that is trap risk, not confirmed bearish reversal by itself."
    if candle_label in ("LIQUIDITY_SWEEP_DOWN", "STOP_RUN_DOWN"):
        return "A low-side sweep is present; that is trap risk, not confirmed bullish reversal by itself."
    if delta is not None and delta > 0 and candle_truth in ("FAKE_BEARISH",):
        return "Buyers were active into a down close, which raises failed-breakdown or absorption risk."
    if delta is not None and delta < 0 and candle_truth in ("FAKE_BULLISH",):
        return "Sellers were active into an up close, which raises failed-breakout or absorption risk."
    if liquidity_event == "WALL_REACTION":
        return "Wall interaction is present, so the current move can still stall without a clean break."
    return "No clear trap condition is dominant from the current inputs."


def _scenario_summary(
    structure: str,
    above_levels: list[dict[str, Any]],
    below_levels: list[dict[str, Any]],
) -> str:
    nearest_above = _format_price(_safe_float(above_levels[0].get("price"))) if above_levels else "UNKNOWN"
    nearest_below = _format_price(_safe_float(below_levels[0].get("price"))) if below_levels else "UNKNOWN"

    if structure in ("HH_BREAK", "HL_FORMING") and above_levels:
        return f"Bullish continuation needs acceptance through {nearest_above}; failure below {nearest_below} keeps balance unresolved."
    if structure in ("LH_FORMING", "LL_BREAK") and below_levels:
        return f"Bearish continuation needs acceptance through {nearest_below}; recovery above {nearest_above} would neutralize the move."
    if above_levels and below_levels:
        return f"Balanced auction remains possible while price stays between {nearest_below} and {nearest_above}."
    return "Scenario planning is reduced because nearby liquidity boundaries are not fully available."


def _combine_interpretation(parts: list[str]) -> str:
    clean_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = part.strip()
        if not part or part in seen:
            continue
        seen.add(part)
        clean_parts.append(part)
    return " ".join(clean_parts)


def _tf_data_quality(
    tf: str,
    mtf_payload: dict[str, Any],
    structure_payload: dict[str, Any],
    atr_state: dict[str, Any] | None,
    required_inputs: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    missing_inputs = [name for name, payload in required_inputs.items() if payload is None]
    if not mtf_payload:
        missing_inputs.append(f"latest_mtf_candle_dna:{tf}")
    if not structure_payload:
        missing_inputs.append(f"latest_market_structure:{tf}")

    atr_key = _normalize_atr_tf_key(tf)
    atr_payload = ((atr_state or {}).get(atr_key)) if atr_state else None
    if not atr_payload:
        missing_inputs.append(f"latest_atr_state:{atr_key}")

    score = (len(required_inputs) - len([name for name, payload in required_inputs.items() if payload is None])) / max(len(required_inputs), 1)
    if not mtf_payload:
        score -= 0.25
    if not structure_payload:
        score -= 0.2
    if not atr_payload:
        score -= 0.2

    mtf_level = str((mtf_payload.get("data_quality") or {}).get("level", "MISSING"))
    structure_level = str((structure_payload.get("data_quality") or {}).get("level", "MISSING"))
    atr_quality = str((atr_payload or {}).get("atr_quality", "MISSING"))

    if mtf_level in ("LOW", "MISSING"):
        score -= 0.15
    elif mtf_level == "REDUCED":
        score -= 0.08
    if structure_level in ("LOW", "MISSING"):
        score -= 0.12
    elif structure_level == "REDUCED":
        score -= 0.06
    if atr_quality in ("LOW", "MISSING"):
        score -= 0.08
    elif atr_quality == "REDUCED":
        score -= 0.04

    score = max(0.0, min(1.0, round(score, 4)))
    return {
        "level": _quality_level(score),
        "missing_inputs": missing_inputs,
    }


def _interpret_timeframe(
    tf: str,
    observation: dict[str, Any] | None,
    mtf_dna: dict[str, Any] | None,
    market_structure: dict[str, Any] | None,
    liquidity_map: dict[str, Any] | None,
    atr_state: dict[str, Any] | None,
    flow_evidence: dict[str, Any] | None,
    flow_persistence: dict[str, Any] | None,
    wall_lifecycle: dict[str, Any] | None,
    required_inputs: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    mtf_payload = ((mtf_dna or {}).get(tf)) or {}
    structure_payload = ((market_structure or {}).get(tf)) or {}
    current_price = _current_price(observation, liquidity_map, mtf_dna)
    above_levels, below_levels = _nearest_levels(liquidity_map, current_price)

    candle_category = (mtf_payload.get("candle_category") or {})
    candle_label = str(candle_category.get("primary", "UNKNOWN"))
    candle_reason_codes = list(candle_category.get("reason_codes") or [])
    war_summary = mtf_payload.get("war_summary") or {}
    candle_truth = str(war_summary.get("candle_truth", "UNKNOWN"))
    delta = _safe_float(mtf_payload.get("delta"))
    cumulative_delta = _safe_float(mtf_payload.get("cumulative_delta"))
    mtf_event = str(mtf_payload.get("liquidity_event", "UNKNOWN"))
    structure = _structure_context(structure_payload, mtf_payload)
    cvd_state = _cvd_state(candle_label, candle_reason_codes, delta, candle_truth)
    liquidity_event = _liquidity_event(candle_label, mtf_event, wall_lifecycle)
    close_position = str(mtf_payload.get("close_position", "UNKNOWN"))

    footprint_summary = _footprint_summary(candle_label, candle_reason_codes, candle_truth, delta, close_position)
    structure_summary = _structure_summary(structure_payload, structure)
    liquidity_summary = _liquidity_summary(current_price, above_levels, below_levels, liquidity_event)
    trend_summary = _trend_summary(tf, structure, structure_payload, market_structure, flow_persistence)
    pressure_summary = _pressure_summary(candle_label, delta, candle_truth, cvd_state, flow_evidence)
    trap_summary = _trap_summary(candle_label, candle_truth, delta, liquidity_event)
    scenario_summary = _scenario_summary(structure, above_levels, below_levels)
    interpretation = _combine_interpretation(
        [
            footprint_summary,
            structure_summary,
            pressure_summary,
            liquidity_summary,
        ]
    )

    tf_quality = _tf_data_quality(tf, mtf_payload, structure_payload, atr_state, required_inputs)
    reason_codes = [
        f"TF_{tf}",
        f"CANDLE_{candle_label}",
        f"STRUCTURE_{structure}",
        f"CVD_{cvd_state}",
        f"LIQUIDITY_{liquidity_event}",
        f"DQ_{tf_quality['level']}",
    ]

    if candle_label in ("SELL_ABSORPTION", "BUY_ABSORPTION"):
        reason_codes.append("ABSORPTION_CONTEXT")
    if candle_label in ("LIQUIDITY_SWEEP_UP", "LIQUIDITY_SWEEP_DOWN", "STOP_RUN_UP", "STOP_RUN_DOWN"):
        reason_codes.append("SWEEP_CONTEXT")

    return {
        "timeframe": tf,
        "candle_label": candle_label,
        "footprint_summary": footprint_summary,
        "structure_summary": structure_summary,
        "liquidity_summary": liquidity_summary,
        "trend_summary": trend_summary,
        "pressure_summary": pressure_summary,
        "trap_summary": trap_summary,
        "scenario_summary": scenario_summary,
        "raw_context": {
            "delta": delta,
            "cumulative_delta": cumulative_delta,
            "cvd_state": cvd_state,
            "liquidity_event": liquidity_event,
            "structure": structure,
            "candle_category": candle_label,
            "candle_truth": candle_truth,
        },
        "interpretation": interpretation,
        "reason_codes": reason_codes,
        "data_quality": tf_quality,
    }


def run_interpretation_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    required_inputs = {name: _load_json(path) for name, path in REQUIRED_INPUT_PATHS.items()}
    optional_inputs = {name: _load_json(path) for name, path in OPTIONAL_INPUT_PATHS.items()}

    observation = required_inputs["latest_observation_factory"]
    mtf_dna = required_inputs["latest_mtf_candle_dna"]
    market_structure = required_inputs["latest_market_structure"]
    liquidity_map = required_inputs["latest_liquidity_map"]
    atr_state = required_inputs["latest_atr_state"]
    flow_evidence = optional_inputs["latest_flow_evidence"]
    flow_persistence = optional_inputs["latest_flow_persistence"]
    wall_lifecycle = optional_inputs["latest_wall_lifecycle"]

    symbol = (
        ((observation or {}).get("symbol"))
        or ((mtf_dna or {}).get("symbol"))
        or ((market_structure or {}).get("symbol"))
        or ((liquidity_map or {}).get("symbol"))
        or ((atr_state or {}).get("symbol"))
        or "BTCUSDT"
    )
    current_price = _current_price(observation, liquidity_map, mtf_dna)

    per_tf: dict[str, dict[str, Any]] = {}
    low_quality_timeframes: list[str] = []
    for tf in TIMEFRAMES:
        payload = _interpret_timeframe(
            tf=tf,
            observation=observation,
            mtf_dna=mtf_dna,
            market_structure=market_structure,
            liquidity_map=liquidity_map,
            atr_state=atr_state,
            flow_evidence=flow_evidence,
            flow_persistence=flow_persistence,
            wall_lifecycle=wall_lifecycle,
            required_inputs=required_inputs,
        )
        per_tf[tf] = payload
        if payload["data_quality"]["level"] in ("LOW", "MISSING"):
            low_quality_timeframes.append(tf)

    missing_required_inputs = [name for name, payload in required_inputs.items() if payload is None]
    available_required_inputs = [name for name, payload in required_inputs.items() if payload is not None]
    base_score = len(available_required_inputs) / max(len(required_inputs), 1)
    if low_quality_timeframes:
        base_score -= min(0.35, len(low_quality_timeframes) * 0.02)
    base_score = max(0.0, min(1.0, round(base_score, 4)))
    overall_level = _quality_level(base_score)

    result: dict[str, Any] = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": "STATE_INTERPRETATION_AGGREGATION",
            "input_files": [str(path).replace("\\", "/") for path in REQUIRED_INPUT_PATHS.values()],
            "optional_input_files": [str(path).replace("\\", "/") for path in OPTIONAL_INPUT_PATHS.values()],
        },
        "current_price": current_price,
        "summary": {
            "timeframes_total": len(TIMEFRAMES),
            "low_quality_timeframes": low_quality_timeframes,
        },
        "data_quality": {
            "level": overall_level,
            "missing_inputs": missing_required_inputs,
        },
        "reason_codes": [
            f"SYMBOL_{symbol}",
            f"TF_TOTAL_{len(TIMEFRAMES)}",
            f"LOW_QUALITY_TFS_{len(low_quality_timeframes)}",
            f"DQ_{overall_level}",
            "NO_FAKE_DATA",
            "NO_TRADE_EXECUTION",
            "NO_DIRECTIONAL_PREDICTION",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "THREE_SCENARIO_ENGINE",
            "S15_FLOW_TO_SETUP_CONTEXT",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }
    result.update(per_tf)

    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, result)
    return result


def main() -> None:
    print(json.dumps(run_interpretation_engine(), indent=2))


if __name__ == "__main__":
    main()
