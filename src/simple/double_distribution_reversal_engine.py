"""Double Distribution Reversal Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "DOUBLE_DISTRIBUTION_REVERSAL_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_double_distribution_reversal.json"
HISTORY_PATH = DATA_DIR / "double_distribution_reversal_history.jsonl"

MARKET_REGIME_PATH = STATE_DIR / "latest_market_regime.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
INTENT_PATH = STATE_DIR / "latest_intent_analysis.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"


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


def run_double_distribution_reversal_engine() -> dict[str, Any]:
    market_regime = _load_json(MARKET_REGIME_PATH) or {}
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    mtf_dna = _load_json(MTF_DNA_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}
    intent_analysis = _load_json(INTENT_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}

    missing_inputs: list[str] = []
    for name, payload in (
        ("latest_market_regime", market_regime),
        ("latest_business_zone", business_zone),
        ("latest_mtf_candle_dna", mtf_dna),
        ("latest_interpretation", interpretation),
        ("latest_intent_analysis", intent_analysis),
        ("latest_liquidity_map", liquidity_map),
    ):
        if not payload:
            missing_inputs.append(name)

    regime = str(market_regime.get("regime", "UNKNOWN"))
    day_type = str(market_regime.get("day_type", "UNKNOWN"))
    value_position = str((business_zone.get("value_area") or {}).get("value_position", "UNKNOWN"))
    auction_state = str((business_zone.get("auction_summary") or {}).get("auction_state", "UNKNOWN"))
    category = str((((mtf_dna.get("1m") or {}).get("candle_category") or {}).get("primary")) or "UNKNOWN")
    cvd_state = str((((interpretation.get("1m") or {}).get("raw_context") or {}).get("cvd_state")) or "UNKNOWN")
    candle_truth = str((((mtf_dna.get("1m") or {}).get("war_summary") or {}).get("candle_truth")) or "UNKNOWN")
    trapped_side = str(((intent_analysis.get("intent_analysis") or {}).get("trapped_side")) or "UNKNOWN")
    intent_name = str(((intent_analysis.get("intent_analysis") or {}).get("intent")) or "UNKNOWN")

    prior_balance_detected = auction_state == "BALANCE" or day_type in ("BALANCED_DAY", "ROTATIONAL_DAY") or value_position == "INSIDE_VALUE"
    impulsive_break_detected = regime in ("MOMENTUM_MODE", "TRANSITION_MODE") and value_position in ("ABOVE_VALUE", "BELOW_VALUE")
    fomo_aggression_detected = trapped_side != "NONE" or intent_name in ("BREAKOUT", "DISTRIBUTION", "ACCUMULATION")
    cvd_price_divergence = (
        (cvd_state == "BUY_PRESSURE" and candle_truth in ("FAKE_BEARISH", "BALANCED"))
        or (cvd_state == "SELL_PRESSURE" and candle_truth in ("FAKE_BULLISH", "BALANCED"))
    )
    absorption_detected = category in ("BUY_ABSORPTION", "SELL_ABSORPTION") or intent_name == "ABSORPTION"
    exhaustion_detected = category in ("EXHAUSTION_BUY", "EXHAUSTION_SELL", "FAILED_AUCTION")
    return_to_old_value = value_position == "INSIDE_VALUE" or str(market_regime.get("acceptance_state", "UNKNOWN")) == "REJECTED_FROM_VALUE"

    direction = "UNKNOWN"
    if value_position == "ABOVE_VALUE" or trapped_side == "BUYERS":
        direction = "SHORT"
    elif value_position == "BELOW_VALUE" or trapped_side == "SELLERS":
        direction = "LONG"
    elif return_to_old_value and cvd_price_divergence:
        direction = "LONG" if cvd_state == "SELL_PRESSURE" else "SHORT" if cvd_state == "BUY_PRESSURE" else "UNKNOWN"

    active = prior_balance_detected and impulsive_break_detected and return_to_old_value and (absorption_detected or exhaustion_detected or cvd_price_divergence)
    if not prior_balance_detected:
        missing_inputs.append("INSUFFICIENT_BALANCE_HISTORY")

    condition_score = sum(
        1
        for flag in (
            prior_balance_detected,
            impulsive_break_detected,
            fomo_aggression_detected,
            cvd_price_divergence,
            absorption_detected,
            exhaustion_detected,
            return_to_old_value,
        )
        if flag
    ) / 7.0

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(market_regime.get("symbol") or business_zone.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "DOUBLE_DISTRIBUTION_CONTEXT_CLASSIFICATION",
        },
        "setup_family": "DOUBLE_DISTRIBUTION_REVERSAL",
        "active": active,
        "direction": direction if direction in ("LONG", "SHORT") else "UNKNOWN" if active else "NEUTRAL",
        "conditions": {
            "prior_balance_detected": prior_balance_detected,
            "impulsive_break_detected": impulsive_break_detected,
            "fomo_aggression_detected": fomo_aggression_detected,
            "cvd_price_divergence": cvd_price_divergence,
            "absorption_detected": absorption_detected,
            "exhaustion_detected": exhaustion_detected,
            "return_to_old_value": return_to_old_value,
        },
        "quality": _quality_grade(condition_score),
        "interpretation": f"regime={regime}, value_position={value_position}, category={category}, cvd={cvd_state}",
        "reason_codes": [
            f"REGIME_{regime}",
            f"DAY_{day_type}",
            f"VALUE_{value_position}",
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
    print(json.dumps(run_double_distribution_reversal_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
