"""Three Scenario Engine.

Builds always-on bullish, bearish, and neutral/range scenarios from the latest
interpretation and supporting market state. This is scenario planning only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "THREE_SCENARIO_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_three_scenarios.json"
HISTORY_PATH = DATA_DIR / "three_scenarios_history.jsonl"

INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
ATR_STATE_PATH = STATE_DIR / "latest_atr_state.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"

TIMEFRAME_PRIORITY = ["1m", "5m", "15m", "1h"]

REQUIRED_INPUT_PATHS = {
    "latest_interpretation": INTERPRETATION_PATH,
    "latest_mtf_candle_dna": MTF_DNA_PATH,
    "latest_market_structure": MARKET_STRUCTURE_PATH,
    "latest_liquidity_map": LIQUIDITY_MAP_PATH,
    "latest_atr_state": ATR_STATE_PATH,
    "latest_observation_factory": OBSERVATION_PATH,
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


def _scenario_quality(score: float) -> str:
    if score <= 0.0:
        return "UNKNOWN"
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"


def _current_price(observation: dict[str, Any] | None, liquidity_map: dict[str, Any] | None) -> float | None:
    price = _safe_float(((observation or {}).get("market_snapshot") or {}).get("price"))
    if price is not None:
        return price
    return _safe_float((liquidity_map or {}).get("current_price"))


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


def _split_liquidity_levels(
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


def _anchor_interpretations(interpretation: dict[str, Any] | None) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for tf in TIMEFRAME_PRIORITY:
        payload = ((interpretation or {}).get(tf)) or {}
        if payload:
            anchors.append(payload)
    return anchors


def _bullish_signal(payload: dict[str, Any]) -> bool:
    raw = payload.get("raw_context") or {}
    structure = str(raw.get("structure", "UNKNOWN"))
    cvd_state = str(raw.get("cvd_state", "UNKNOWN"))
    candle_label = str(payload.get("candle_label", "UNKNOWN"))
    return (
        structure in ("HH_BREAK", "HL_FORMING")
        or cvd_state in ("BUY_PRESSURE", "SELL_PRESSURE_ABSORBED")
        or candle_label in ("BUY_IMBALANCE", "BUY_ABSORPTION", "CONTINUATION_CANDLE")
    )


def _bearish_signal(payload: dict[str, Any]) -> bool:
    raw = payload.get("raw_context") or {}
    structure = str(raw.get("structure", "UNKNOWN"))
    cvd_state = str(raw.get("cvd_state", "UNKNOWN"))
    candle_label = str(payload.get("candle_label", "UNKNOWN"))
    return (
        structure in ("LH_FORMING", "LL_BREAK")
        or cvd_state in ("SELL_PRESSURE", "BUY_PRESSURE_ABSORBED")
        or candle_label in ("SELL_IMBALANCE", "SELL_ABSORPTION", "CONTINUATION_CANDLE")
    )


def _neutral_signal(payload: dict[str, Any]) -> bool:
    raw = payload.get("raw_context") or {}
    structure = str(raw.get("structure", "UNKNOWN"))
    cvd_state = str(raw.get("cvd_state", "UNKNOWN"))
    candle_label = str(payload.get("candle_label", "UNKNOWN"))
    return (
        structure == "RANGE"
        or cvd_state == "BALANCED"
        or candle_label in ("NORMAL_BALANCED", "FAILED_AUCTION", "UNKNOWN")
    )


def _collect_supporting_evidence(anchors: list[dict[str, Any]], direction: str) -> list[str]:
    evidence: list[str] = []
    for payload in anchors:
        tf = str(payload.get("timeframe", "unknown"))
        raw = payload.get("raw_context") or {}
        candle_label = str(payload.get("candle_label", "UNKNOWN"))
        structure = str(raw.get("structure", "UNKNOWN"))
        cvd_state = str(raw.get("cvd_state", "UNKNOWN"))
        if direction == "BULLISH" and _bullish_signal(payload):
            evidence.append(f"{tf}: {candle_label} with {structure} and {cvd_state}.")
        elif direction == "BEARISH" and _bearish_signal(payload):
            evidence.append(f"{tf}: {candle_label} with {structure} and {cvd_state}.")
        elif direction == "NEUTRAL_RANGE" and _neutral_signal(payload):
            evidence.append(f"{tf}: {candle_label} with {structure} and {cvd_state}.")
    return evidence


def _collect_contradicting_evidence(anchors: list[dict[str, Any]], direction: str) -> list[str]:
    evidence: list[str] = []
    for payload in anchors:
        tf = str(payload.get("timeframe", "unknown"))
        raw = payload.get("raw_context") or {}
        candle_label = str(payload.get("candle_label", "UNKNOWN"))
        structure = str(raw.get("structure", "UNKNOWN"))
        cvd_state = str(raw.get("cvd_state", "UNKNOWN"))
        if direction == "BULLISH" and _bearish_signal(payload):
            evidence.append(f"{tf}: opposing read from {candle_label}, {structure}, {cvd_state}.")
        elif direction == "BEARISH" and _bullish_signal(payload):
            evidence.append(f"{tf}: opposing read from {candle_label}, {structure}, {cvd_state}.")
        elif direction == "NEUTRAL_RANGE" and (_bullish_signal(payload) or _bearish_signal(payload)) and not _neutral_signal(payload):
            evidence.append(f"{tf}: directional pressure is still present via {candle_label}, {structure}, {cvd_state}.")
    return evidence


def _range_bounds(
    current_price: float | None,
    above_levels: list[dict[str, Any]],
    below_levels: list[dict[str, Any]],
    mtf_dna: dict[str, Any] | None,
) -> tuple[float | None, float | None]:
    upper = _safe_float(above_levels[0].get("price")) if above_levels else None
    lower = _safe_float(below_levels[0].get("price")) if below_levels else None
    if upper is not None and lower is not None:
        return lower, upper

    for tf in ("1m", "5m", "15m"):
        payload = ((mtf_dna or {}).get(tf)) or {}
        tf_high = _safe_float(payload.get("high"))
        tf_low = _safe_float(payload.get("low"))
        if tf_high is not None and tf_low is not None and tf_high > tf_low:
            return tf_low, tf_high
    return None, None


def _atr_context(atr_state: dict[str, Any] | None) -> str:
    atr_payload = ((atr_state or {}).get("1m")) or {}
    atr_quality = str(atr_payload.get("atr_quality", "UNKNOWN"))
    atr_14 = _safe_float(atr_payload.get("atr_14"))
    if atr_quality == "MISSING":
        return "ATR context is missing, so only directional conditions are described."
    return f"ATR context is {atr_quality.lower()} on 1m with atr_14={_format_price(atr_14)}."


def _make_scenario(
    scenario_id: str,
    condition: str,
    required_confirmation: list[str],
    invalidated_if: list[str],
    liquidity_targets: list[float],
    expected_path: str,
    supporting_evidence: list[str],
    contradicting_evidence: list[str],
) -> dict[str, Any]:
    score = 0.0
    score += min(0.45, len(supporting_evidence) * 0.15)
    score -= min(0.30, len(contradicting_evidence) * 0.10)
    if liquidity_targets:
        score += 0.2
    if required_confirmation:
        score += 0.15
    score = max(0.0, min(1.0, round(score, 4)))

    if not liquidity_targets and "LIQUIDITY_TARGETS_NOT_AVAILABLE" not in contradicting_evidence:
        contradicting_evidence = list(contradicting_evidence) + ["LIQUIDITY_TARGETS_NOT_AVAILABLE"]

    return {
        "scenario_id": scenario_id,
        "condition": condition,
        "trigger": required_confirmation[0] if required_confirmation else "UNKNOWN",
        "invalidation": invalidated_if[0] if invalidated_if else "UNKNOWN",
        "target": liquidity_targets[0] if liquidity_targets else None,
        "required_evidence": required_confirmation,
        "missing_evidence": contradicting_evidence,
        "confidence_band": _scenario_quality(score),
        "required_confirmation": required_confirmation,
        "invalidated_if": invalidated_if,
        "liquidity_targets": liquidity_targets,
        "expected_path": expected_path,
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": contradicting_evidence,
        "quality": _scenario_quality(score),
        "is_trade_signal": False,
    }


def _dominant_current_read(anchors: list[dict[str, Any]]) -> str:
    bullish = sum(1 for payload in anchors if _bullish_signal(payload))
    bearish = sum(1 for payload in anchors if _bearish_signal(payload))
    neutral = sum(1 for payload in anchors if _neutral_signal(payload))

    if bullish == 0 and bearish == 0 and neutral == 0:
        return "UNKNOWN"
    if bullish > bearish + 1:
        return "BULLISH"
    if bearish > bullish + 1:
        return "BEARISH"
    if neutral >= max(bullish, bearish):
        return "NEUTRAL"
    if bullish == bearish:
        return "MIXED"
    return "MIXED"


def run_three_scenario_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    inputs = {name: _load_json(path) for name, path in REQUIRED_INPUT_PATHS.items()}
    interpretation = inputs["latest_interpretation"]
    mtf_dna = inputs["latest_mtf_candle_dna"]
    market_structure = inputs["latest_market_structure"]
    liquidity_map = inputs["latest_liquidity_map"]
    atr_state = inputs["latest_atr_state"]
    observation = inputs["latest_observation_factory"]

    symbol = (
        ((interpretation or {}).get("symbol"))
        or ((mtf_dna or {}).get("symbol"))
        or ((market_structure or {}).get("symbol"))
        or ((liquidity_map or {}).get("symbol"))
        or ((atr_state or {}).get("symbol"))
        or ((observation or {}).get("symbol"))
        or "BTCUSDT"
    )
    current_price = _current_price(observation, liquidity_map)
    above_levels, below_levels = _split_liquidity_levels(liquidity_map, current_price)
    anchors = _anchor_interpretations(interpretation)
    lower_bound, upper_bound = _range_bounds(current_price, above_levels, below_levels, mtf_dna)
    atr_note = _atr_context(atr_state)

    bull_break = _safe_float(above_levels[0].get("price")) if above_levels else None
    bull_targets = [_safe_float(level.get("price")) for level in above_levels[1:3] if _safe_float(level.get("price")) is not None]
    bear_break = _safe_float(below_levels[0].get("price")) if below_levels else None
    bear_targets = [_safe_float(level.get("price")) for level in below_levels[1:3] if _safe_float(level.get("price")) is not None]

    bullish_support = _collect_supporting_evidence(anchors, "BULLISH")
    bullish_contra = _collect_contradicting_evidence(anchors, "BULLISH")
    bearish_support = _collect_supporting_evidence(anchors, "BEARISH")
    bearish_contra = _collect_contradicting_evidence(anchors, "BEARISH")
    neutral_support = _collect_supporting_evidence(anchors, "NEUTRAL_RANGE")
    neutral_contra = _collect_contradicting_evidence(anchors, "NEUTRAL_RANGE")

    bullish_condition = (
        f"{_format_price(bull_break)} reclaim with positive delta and accepted structure above resistance."
        if bull_break is not None
        else "Upside continuation requires positive delta and accepted structure, but a reclaim level is not available."
    )
    bullish_confirmations = [
        "1m keeps BUY_PRESSURE or SELL_PRESSURE_ABSORBED context.",
        "1m structure holds HH_BREAK or HL_FORMING.",
    ]
    if bull_break is not None:
        bullish_confirmations.insert(0, f"Price accepts above {_format_price(bull_break)}.")
    bullish_invalidations = [
        "1m flips into BUY_PRESSURE_ABSORBED or LH_FORMING.",
    ]
    if bear_break is not None:
        bullish_invalidations.insert(0, f"Price loses {_format_price(bear_break)} and accepts below it.")
    bullish_expected_path = (
        f"Reclaim above {_format_price(bull_break)} could rotate price toward {_format_price(bull_targets[0])}"
        + (f" and then {_format_price(bull_targets[1])}." if len(bull_targets) > 1 else ".")
        if bull_break is not None and bull_targets
        else f"Bullish path is descriptive only because liquidity targets are not available. {atr_note}"
    )
    bullish_scenario = _make_scenario(
        scenario_id="BULLISH",
        condition=bullish_condition,
        required_confirmation=bullish_confirmations,
        invalidated_if=bullish_invalidations,
        liquidity_targets=bull_targets,
        expected_path=bullish_expected_path,
        supporting_evidence=bullish_support,
        contradicting_evidence=bullish_contra,
    )

    bearish_condition = (
        f"{_format_price(bear_break)} breakdown with negative delta and accepted structure below support."
        if bear_break is not None
        else "Downside continuation requires negative delta and accepted structure, but a breakdown level is not available."
    )
    bearish_confirmations = [
        "1m keeps SELL_PRESSURE or BUY_PRESSURE_ABSORBED context.",
        "1m structure holds LL_BREAK or LH_FORMING.",
    ]
    if bear_break is not None:
        bearish_confirmations.insert(0, f"Price accepts below {_format_price(bear_break)}.")
    bearish_invalidations = [
        "1m flips into SELL_PRESSURE_ABSORBED or HL_FORMING.",
    ]
    if bull_break is not None:
        bearish_invalidations.insert(0, f"Price reclaims {_format_price(bull_break)} and accepts above it.")
    bearish_expected_path = (
        f"Breakdown below {_format_price(bear_break)} could rotate price toward {_format_price(bear_targets[0])}"
        + (f" and then {_format_price(bear_targets[1])}." if len(bear_targets) > 1 else ".")
        if bear_break is not None and bear_targets
        else f"Bearish path is descriptive only because liquidity targets are not available. {atr_note}"
    )
    bearish_scenario = _make_scenario(
        scenario_id="BEARISH",
        condition=bearish_condition,
        required_confirmation=bearish_confirmations,
        invalidated_if=bearish_invalidations,
        liquidity_targets=bear_targets,
        expected_path=bearish_expected_path,
        supporting_evidence=bearish_support,
        contradicting_evidence=bearish_contra,
    )

    neutral_condition = (
        f"Price remains between {_format_price(lower_bound)} and {_format_price(upper_bound)} with a balanced auction."
        if lower_bound is not None and upper_bound is not None
        else "Balanced range continuation requires visible two-sided boundaries, but they are not fully available."
    )
    neutral_confirmations = [
        "1m keeps RANGE or BALANCED context.",
        "Neither side achieves accepted structure outside the current auction.",
    ]
    neutral_invalidations = []
    if upper_bound is not None:
        neutral_invalidations.append(f"Price accepts above {_format_price(upper_bound)}.")
    if lower_bound is not None:
        neutral_invalidations.append(f"Price accepts below {_format_price(lower_bound)}.")
    neutral_targets = []
    if lower_bound is not None and upper_bound is not None:
        neutral_targets = [round(lower_bound, 8), round(upper_bound, 8)]
    neutral_expected_path = (
        f"Balanced auction may continue between {_format_price(lower_bound)} and {_format_price(upper_bound)} until either side accepts outside the range."
        if neutral_targets
        else f"Neutral path is descriptive only because range bounds are not fully available. {atr_note}"
    )
    neutral_scenario = _make_scenario(
        scenario_id="NEUTRAL_RANGE",
        condition=neutral_condition,
        required_confirmation=neutral_confirmations,
        invalidated_if=neutral_invalidations,
        liquidity_targets=neutral_targets,
        expected_path=neutral_expected_path,
        supporting_evidence=neutral_support,
        contradicting_evidence=neutral_contra,
    )

    missing_inputs = [name for name, payload in inputs.items() if payload is None]
    score = (len(inputs) - len(missing_inputs)) / max(len(inputs), 1)
    scenario_levels = [
        bullish_scenario["quality"],
        bearish_scenario["quality"],
        neutral_scenario["quality"],
    ]
    if "LOW" in scenario_levels:
        score -= 0.1
    if "UNKNOWN" in scenario_levels:
        score -= 0.2
    score = max(0.0, min(1.0, round(score, 4)))
    dq_level = _quality_level(score)

    result = {
        "timestamp_utc": _utc_now(),
        "symbol": symbol,
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "INTERPRETATION_SCENARIO_PLANNING",
            "input_files": [str(path).replace("\\", "/") for path in REQUIRED_INPUT_PATHS.values()],
        },
        "current_price": current_price,
        "bullish_scenario": bullish_scenario,
        "bearish_scenario": bearish_scenario,
        "neutral_scenario": neutral_scenario,
        "neutral_range_scenario": neutral_scenario,
        "dominant_current_read": _dominant_current_read(anchors),
        "scenario_note": "This is scenario planning, not prediction or execution.",
        "data_quality": {
            "level": dq_level,
            "missing_inputs": missing_inputs,
        },
        "reason_codes": [
            f"SYMBOL_{symbol}",
            f"DQ_{dq_level}",
            f"ANCHOR_TFS_{len(anchors)}",
            "ALWAYS_THREE_SCENARIOS",
            "NO_FAKE_DATA",
            "NO_TRADE_EXECUTION",
            "NO_DIRECTIONAL_PREDICTION",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "S15_FLOW_TO_SETUP_CONTEXT",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, result)
    return result


def main() -> None:
    print(json.dumps(run_three_scenario_engine(), indent=2))


if __name__ == "__main__":
    main()
