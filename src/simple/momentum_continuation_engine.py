"""Momentum Continuation Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MOMENTUM_CONTINUATION_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_momentum_continuation.json"
HISTORY_PATH = DATA_DIR / "momentum_continuation_history.jsonl"

MARKET_REGIME_PATH = STATE_DIR / "latest_market_regime.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
INTENT_PATH = STATE_DIR / "latest_intent_analysis.json"


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


def run_momentum_continuation_engine() -> dict[str, Any]:
    market_regime = _load_json(MARKET_REGIME_PATH) or {}
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    mtf_dna = _load_json(MTF_DNA_PATH) or {}
    market_structure = _load_json(MARKET_STRUCTURE_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}
    intent_analysis = _load_json(INTENT_PATH) or {}

    missing_inputs: list[str] = []
    for name, payload in (
        ("latest_market_regime", market_regime),
        ("latest_business_zone", business_zone),
        ("latest_mtf_candle_dna", mtf_dna),
        ("latest_market_structure", market_structure),
        ("latest_interpretation", interpretation),
        ("latest_liquidity_map", liquidity_map),
        ("latest_intent_analysis", intent_analysis),
    ):
        if not payload:
            missing_inputs.append(name)

    regime = str(market_regime.get("regime", "UNKNOWN"))
    direction = str(market_regime.get("directional_bias", "UNKNOWN"))
    acceptance_state = str(market_regime.get("acceptance_state", "UNKNOWN"))
    tf_1m = mtf_dna.get("1m") or {}
    ms_1m = market_structure.get("1m") or {}
    biz_auction = business_zone.get("auction_summary") or {}
    intent = intent_analysis.get("intent_analysis") or {}

    structure_label = str(ms_1m.get("structure_label", "UNKNOWN"))
    trend_state = str(ms_1m.get("trend_state", "UNKNOWN"))
    candle_category = str(((tf_1m.get("candle_category") or {}).get("primary")) or "UNKNOWN")
    liquidity_levels = liquidity_map.get("detected_levels") or []
    trapped_side = str(intent.get("trapped_side", "UNKNOWN"))
    value_position = str((business_zone.get("value_area") or {}).get("value_position", "UNKNOWN"))

    balance_broken = structure_label not in ("RANGE", "EQH", "EQL", "UNKNOWN") or regime == "MOMENTUM_MODE"
    new_value_accepted = acceptance_state in ("ACCEPTED_ABOVE_VALUE", "ACCEPTED_BELOW_VALUE")
    trend_expansion = trend_state in ("UPTREND", "DOWNTREND") or candle_category in ("CONTINUATION_CANDLE", "BUY_IMBALANCE", "SELL_IMBALANCE")
    opposite_side_trapped = (direction == "LONG" and trapped_side == "SELLERS") or (direction == "SHORT" and trapped_side == "BUYERS")
    retest_available = bool(liquidity_levels)
    liquidity_target_available = False
    current_price = _safe_float(liquidity_map.get("current_price"))
    for level in liquidity_levels:
        price = _safe_float(level.get("price"))
        if price is None or current_price is None:
            continue
        if direction == "LONG" and price > current_price:
            liquidity_target_available = True
            break
        if direction == "SHORT" and price < current_price:
            liquidity_target_available = True
            break

    active = (
        direction in ("LONG", "SHORT")
        and (regime == "MOMENTUM_MODE" or (regime == "TRANSITION_MODE" and new_value_accepted))
        and balance_broken
        and trend_expansion
        and liquidity_target_available
    )

    condition_score = sum(
        1
        for flag in (
            balance_broken,
            new_value_accepted,
            trend_expansion,
            opposite_side_trapped,
            retest_available,
            liquidity_target_available,
        )
        if flag
    ) / 6.0
    quality = _quality_grade(condition_score)

    interpretation_text = (
        f"Regime={regime}, direction={direction}, value={value_position}, "
        f"auction={biz_auction.get('auction_state', 'UNKNOWN')}, continuation={candle_category}."
    )

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(market_regime.get("symbol") or mtf_dna.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "REGIME_CONTINUATION_CLASSIFICATION",
        },
        "setup_family": "MOMENTUM_CONTINUATION",
        "active": active,
        "direction": direction if direction in ("LONG", "SHORT") else "UNKNOWN" if active else "NEUTRAL",
        "conditions": {
            "balance_broken": balance_broken,
            "new_value_accepted": new_value_accepted,
            "trend_expansion": trend_expansion,
            "opposite_side_trapped": opposite_side_trapped,
            "retest_available": retest_available,
            "liquidity_target_available": liquidity_target_available,
        },
        "quality": quality,
        "interpretation": interpretation_text,
        "reason_codes": [
            f"REGIME_{regime}",
            f"DIRECTION_{direction}",
            f"VALUE_POSITION_{value_position}",
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
    print(json.dumps(run_momentum_continuation_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
