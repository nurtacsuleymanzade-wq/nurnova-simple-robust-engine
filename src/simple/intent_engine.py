"""Intent Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "INTENT_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_intent_analysis.json"
HISTORY_PATH = DATA_DIR / "intent_analysis_history.jsonl"

OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
DEPTH_MEMORY_PATH = STATE_DIR / "latest_depth_liquidity_memory.json"
WALL_LIFECYCLE_PATH = STATE_DIR / "latest_wall_lifecycle.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"


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


def run_intent_engine() -> dict[str, Any]:
    observation = _load_json(OBSERVATION_PATH) or {}
    mtf_dna = _load_json(MTF_DNA_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}
    depth_memory = _load_json(DEPTH_MEMORY_PATH) or {}
    wall_lifecycle = _load_json(WALL_LIFECYCLE_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}

    missing_inputs: list[str] = []
    for name, payload in (
        ("latest_observation_factory", observation),
        ("latest_mtf_candle_dna", mtf_dna),
        ("latest_liquidity_map", liquidity_map),
        ("latest_depth_liquidity_memory", depth_memory),
        ("latest_wall_lifecycle", wall_lifecycle),
        ("latest_interpretation", interpretation),
    ):
        if not payload:
            missing_inputs.append(name)

    volume_flow = observation.get("volume_flow") or {}
    aggression = observation.get("aggression") or {}
    war_reading = observation.get("war_reading") or {}
    micro_candidates = observation.get("micro_candidates") or {}
    tf_1m = mtf_dna.get("1m") or {}
    candle_category = ((tf_1m.get("candle_category") or {}).get("primary")) or "UNKNOWN"
    bid_wall = depth_memory.get("bid_wall") or {}
    ask_wall = depth_memory.get("ask_wall") or {}
    bid_history = wall_lifecycle.get("bid_wall_history") or {}
    ask_history = wall_lifecycle.get("ask_wall_history") or {}

    aggressive_buy = _safe_float(volume_flow.get("buy_volume"))
    aggressive_sell = _safe_float(volume_flow.get("sell_volume"))
    passive_buy = _safe_float(bid_wall.get("wall_notional"))
    passive_sell = _safe_float(ask_wall.get("wall_notional"))
    pressure_score = _safe_float(aggression.get("pressure_score"))

    iceberg_reasons: list[str] = []
    spoof_reasons: list[str] = []

    bid_absorption = _safe_float(bid_history.get("absorption_score"))
    ask_absorption = _safe_float(ask_history.get("absorption_score"))
    bid_events = bid_history.get("event_history") or []
    ask_events = ask_history.get("event_history") or []

    iceberg_detected = False
    iceberg_side = "UNKNOWN"
    iceberg_level = None
    iceberg_retests = 0
    refill_detected = False
    price_rejects = False
    if bid_absorption is None and ask_absorption is None:
        iceberg_reasons.append("INSUFFICIENT_LEVEL_RETEST_DATA")
    else:
        bid_score = bid_absorption or 0.0
        ask_score = ask_absorption or 0.0
        bid_retests = len(bid_events)
        ask_retests = len(ask_events)
        if bid_retests >= 3 and bid_score >= 0.75:
            iceberg_detected = True
            iceberg_side = "BUY"
            iceberg_level = _safe_float(bid_history.get("wall_price"))
            iceberg_retests = bid_retests
            refill_detected = True
            price_rejects = war_reading.get("who_won") == "SELLERS"
        elif ask_retests >= 3 and ask_score >= 0.75:
            iceberg_detected = True
            iceberg_side = "SELL"
            iceberg_level = _safe_float(ask_history.get("wall_price"))
            iceberg_retests = ask_retests
            refill_detected = True
            price_rejects = war_reading.get("who_won") == "BUYERS"
        else:
            iceberg_reasons.append("INSUFFICIENT_LEVEL_RETEST_DATA")

    spoof_detected = False
    spoof_side = "UNKNOWN"
    spoof_level = None
    disappears_before_fill = False
    no_trade_executed = False
    bid_spoof = _safe_float(bid_history.get("spoof_score"))
    ask_spoof = _safe_float(ask_history.get("spoof_score"))
    if bid_spoof is None and ask_spoof is None:
        spoof_reasons.append("INSUFFICIENT_ORDERBOOK_LIFECYCLE_DATA")
    else:
        if str(bid_history.get("current_event", "")) == "LIKELY_SPOOF" or (bid_spoof or 0.0) >= 0.8:
            spoof_detected = True
            spoof_side = "BUY"
            spoof_level = _safe_float(bid_history.get("wall_price"))
            disappears_before_fill = True
            no_trade_executed = True
        elif str(ask_history.get("current_event", "")) == "LIKELY_SPOOF" or (ask_spoof or 0.0) >= 0.8:
            spoof_detected = True
            spoof_side = "SELL"
            spoof_level = _safe_float(ask_history.get("wall_price"))
            disappears_before_fill = True
            no_trade_executed = True
        else:
            spoof_reasons.append("INSUFFICIENT_ORDERBOOK_LIFECYCLE_DATA")

    trapped_side = "NONE"
    attacker = str(war_reading.get("who_attacked", "UNKNOWN"))
    winner = str(war_reading.get("who_won", "UNKNOWN"))
    if attacker == "BUYERS" and winner == "SELLERS":
        trapped_side = "BUYERS"
    elif attacker == "SELLERS" and winner == "BUYERS":
        trapped_side = "SELLERS"

    passive_strength = None
    if passive_buy is not None or passive_sell is not None:
        passive_strength = max(passive_buy or 0.0, passive_sell or 0.0)

    aggressive_pressure = pressure_score if pressure_score is not None else _safe_float(aggression.get("delta"))

    slippage_score = None
    high_price = _safe_float(tf_1m.get("high"))
    low_price = _safe_float(tf_1m.get("low"))
    total_aggressive = (aggressive_buy or 0.0) + (aggressive_sell or 0.0)
    if high_price is not None and low_price is not None and total_aggressive > 0.0:
        slippage_score = round((high_price - low_price) / total_aggressive, 8)

    dominant_force = "UNKNOWN"
    if passive_strength is not None and aggressive_pressure is not None:
        if passive_strength > abs(aggressive_pressure):
            dominant_force = "PASSIVE"
        elif passive_strength < abs(aggressive_pressure):
            dominant_force = "AGGRESSIVE"
        else:
            dominant_force = "BALANCED"

    intent = "UNKNOWN"
    intent_type = "UNKNOWN"
    side = "UNKNOWN"
    result = "UNKNOWN"
    strength = None

    if spoof_detected:
        intent = "MANIPULATION"
        intent_type = "SPOOF"
        side = spoof_side
        result = "FAKE_RESISTANCE" if spoof_side == "SELL" else "FAKE_SUPPORT"
    elif iceberg_detected or candle_category in ("BUY_ABSORPTION", "SELL_ABSORPTION"):
        intent = "ABSORPTION"
        intent_type = "ICEBERG" if iceberg_detected else "PASSIVE_WALL"
        side = iceberg_side if iceberg_detected else ("BUY" if candle_category == "BUY_ABSORPTION" else "SELL")
        result = "SUPPORT_HOLDING" if side == "BUY" else "RESISTANCE_HOLDING"
    elif trapped_side != "NONE":
        intent = "BREAKOUT"
        intent_type = "TRAP"
        side = "BUY" if trapped_side == "SELLERS" else "SELL"
        result = "FAST_MOVE_POTENTIAL"
    elif aggressive_pressure is not None and abs(aggressive_pressure) > 0.0:
        intent = "ACCUMULATION" if aggressive_pressure > 0.0 and passive_buy is not None and (passive_buy or 0.0) >= (passive_sell or 0.0) else "DISTRIBUTION" if aggressive_pressure < 0.0 else "NONE"
        intent_type = "AGGRESSIVE_PUSH"
        side = "BUY" if aggressive_pressure > 0.0 else "SELL" if aggressive_pressure < 0.0 else "NEUTRAL"
        result = "FAST_MOVE_POTENTIAL" if micro_candidates.get("imbalance_candidate") else "UNKNOWN"
    else:
        intent = "NONE"
        intent_type = "NONE"
        side = "NEUTRAL"

    if passive_strength is not None and aggressive_pressure is not None:
        strength = round(abs(aggressive_pressure) + passive_strength, 4)

    interpretation_text = "UNKNOWN"
    if dominant_force == "PASSIVE":
        interpretation_text = "ABSORPTION" if intent == "ABSORPTION" else "UNKNOWN"
    elif dominant_force == "AGGRESSIVE":
        interpretation_text = "BREAKOUT" if intent in ("BREAKOUT", "ACCUMULATION", "DISTRIBUTION") else "UNKNOWN"
    elif trapped_side != "NONE":
        interpretation_text = "TRAP"

    score = 0.0
    if observation:
        score += 0.3
    if depth_memory:
        score += 0.25
    if wall_lifecycle:
        score += 0.2
    if interpretation and mtf_dna:
        score += 0.15
    if not missing_inputs:
        score += 0.1

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(observation.get("symbol") or mtf_dna.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "ORDERFLOW_DEPTH_INTENT_CONTEXT",
        },
        "intent_analysis": {
            "iceberg_detected": iceberg_detected,
            "spoof_detected": spoof_detected,
            "passive_strength": passive_strength,
            "aggressive_pressure": aggressive_pressure,
            "slippage_score": slippage_score,
            "trapped_side": trapped_side,
            "intent": intent,
            "intent_type": intent_type,
            "side": side,
            "strength": strength,
            "result": result,
        },
        "iceberg": {
            "detected": iceberg_detected,
            "side": iceberg_side,
            "level": iceberg_level,
            "retests": iceberg_retests,
            "refill_detected": refill_detected,
            "price_rejects": price_rejects,
            "reason_codes": iceberg_reasons,
        },
        "spoof": {
            "detected": spoof_detected,
            "side": spoof_side,
            "level": spoof_level,
            "disappears_before_fill": disappears_before_fill,
            "no_trade_executed": no_trade_executed,
            "reason_codes": spoof_reasons,
        },
        "passive_aggressive_balance": {
            "aggressive_buy": aggressive_buy,
            "aggressive_sell": aggressive_sell,
            "passive_buy": passive_buy,
            "passive_sell": passive_sell,
            "dominant_force": dominant_force,
            "interpretation": interpretation_text,
        },
        "reason_codes": [
            f"SYMBOL_{str(observation.get('symbol') or mtf_dna.get('symbol') or 'BTCUSDT')}",
            f"INTENT_{intent}",
            f"INTENT_TYPE_{intent_type}",
            *iceberg_reasons,
            *spoof_reasons,
            f"DQ_{_quality_level(score)}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "data_quality": {
            "level": _quality_level(score),
            "missing_inputs": missing_inputs,
        },
        "feeds_next": [
            "POSITIONING_CONTEXT_ENGINE",
            "MOMENTUM_CONTINUATION_ENGINE",
            "DOUBLE_DISTRIBUTION_REVERSAL_ENGINE",
            "TRAP_TRADER_ENGINE",
            "UNIFIED_CONTEXT_ENGINE",
            "S15_FLOW_TO_SETUP_CONTEXT",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_intent_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
