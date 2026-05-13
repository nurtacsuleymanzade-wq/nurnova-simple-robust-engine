"""Trap Trader Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "TRAP_TRADER_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_trap_trader.json"
HISTORY_PATH = DATA_DIR / "trap_trader_history.jsonl"

INTENT_PATH = STATE_DIR / "latest_intent_analysis.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"


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


def _quality_grade(score: float) -> str:
    if score >= 0.95:
        return "A_PLUS"
    if score >= 0.8:
        return "A"
    if score >= 0.65:
        return "B"
    if score >= 0.5:
        return "C"
    if score > 0.0:
        return "LOW"
    return "UNKNOWN"


def run_trap_trader_engine() -> dict[str, Any]:
    intent_analysis = _load_json(INTENT_PATH) or {}
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}
    market_structure = _load_json(MARKET_STRUCTURE_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}
    mtf_dna = _load_json(MTF_DNA_PATH) or {}

    missing_inputs: list[str] = []
    for name, payload in (
        ("latest_intent_analysis", intent_analysis),
        ("latest_business_zone", business_zone),
        ("latest_liquidity_map", liquidity_map),
        ("latest_market_structure", market_structure),
        ("latest_interpretation", interpretation),
        ("latest_mtf_candle_dna", mtf_dna),
    ):
        if not payload:
            missing_inputs.append(name)

    intent = intent_analysis.get("intent_analysis") or {}
    ms_1m = market_structure.get("1m") or {}
    int_1m = interpretation.get("1m") or {}
    tf_1m = mtf_dna.get("1m") or {}
    value_area = business_zone.get("value_area") or {}

    structure_label = str(ms_1m.get("structure_label", "UNKNOWN"))
    candle_category = str(((tf_1m.get("candle_category") or {}).get("primary")) or "UNKNOWN")
    cvd_state = str(((int_1m.get("raw_context") or {}).get("cvd_state")) or "UNKNOWN")
    trapped_side = str(intent.get("trapped_side", "UNKNOWN"))
    liquidity_event = str(((tf_1m.get("liquidity_event")) or "UNKNOWN"))
    current_price = _safe_float(liquidity_map.get("current_price"))
    poc = _safe_float(value_area.get("poc"))

    important_level_break = structure_label in ("BOS", "CHOCH", "MSS", "EQH", "EQL") or liquidity_event in ("SWEEP", "WALL_REACTION")
    footprint_aggression = cvd_state in ("BUY_PRESSURE", "SELL_PRESSURE") or candle_category in ("BUY_IMBALANCE", "SELL_IMBALANCE", "LIQUIDITY_SWEEP_UP", "LIQUIDITY_SWEEP_DOWN")
    failure_to_continue = candle_category in ("FAILED_AUCTION", "TRAP_CANDLE", "REVERSAL_CANDLE", "UNKNOWN") or structure_label == "RANGE"
    poc_shift = False
    poc_reason = []
    if poc is not None and current_price is not None:
        poc_shift = abs(current_price - poc) <= max(abs(current_price) * 0.0002, 0.01)
    else:
        poc_reason.append("POC_NOT_AVAILABLE")
    retest = bool(liquidity_map.get("near_liquidity") or [])
    trapped_buyers = trapped_side == "BUYERS"
    trapped_sellers = trapped_side == "SELLERS"

    trap_type = "UNKNOWN"
    direction = "NEUTRAL"
    if trapped_buyers:
        trap_type = "BUYERS_TRAPPED"
        direction = "SHORT"
    elif trapped_sellers:
        trap_type = "SELLERS_TRAPPED"
        direction = "LONG"
    elif liquidity_event == "SWEEP":
        trap_type = "FAKE_BREAKOUT" if cvd_state == "BUY_PRESSURE" else "FAKE_BREAKDOWN" if cvd_state == "SELL_PRESSURE" else "UNKNOWN"
        direction = "SHORT" if trap_type == "FAKE_BREAKOUT" else "LONG" if trap_type == "FAKE_BREAKDOWN" else "NEUTRAL"

    active = important_level_break and footprint_aggression and failure_to_continue and retest and (poc_shift or trapped_buyers or trapped_sellers)
    condition_score = sum(
        1
        for flag in (
            important_level_break,
            footprint_aggression,
            failure_to_continue,
            poc_shift,
            retest,
            trapped_buyers,
            trapped_sellers,
        )
        if flag
    ) / 7.0

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(intent_analysis.get("symbol") or business_zone.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "TRAP_CONTEXT_CLASSIFICATION",
        },
        "setup_family": "TRAP_TRADER_REVERSAL",
        "active": active,
        "direction": direction if active else "NEUTRAL",
        "conditions": {
            "important_level_break": important_level_break,
            "footprint_aggression": footprint_aggression,
            "failure_to_continue": failure_to_continue,
            "poc_shift": poc_shift,
            "retest": retest,
            "trapped_buyers": trapped_buyers,
            "trapped_sellers": trapped_sellers,
        },
        "trap_type": trap_type,
        "quality": _quality_grade(condition_score),
        "interpretation": f"structure={structure_label}, candle={candle_category}, cvd={cvd_state}, trap={trapped_side}",
        "reason_codes": [
            f"TRAP_{trap_type}",
            *poc_reason,
            f"DQ_{_quality_level(condition_score)}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            *missing_inputs,
        ],
        "is_trade_signal": False,
        "data_quality": {
            "level": _quality_level(condition_score if not missing_inputs else min(condition_score, 0.7)),
            "missing_inputs": missing_inputs,
        },
        "feeds_next": [
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
    print(json.dumps(run_trap_trader_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
