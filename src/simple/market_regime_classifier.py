"""Market Regime Classifier."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MARKET_REGIME_CLASSIFIER"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_market_regime.json"
HISTORY_PATH = DATA_DIR / "market_regime_history.jsonl"

MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
ATR_STATE_PATH = STATE_DIR / "latest_atr_state.json"
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


def _direction_from_structure(label: str, trend_state: str) -> str:
    if label in ("HH", "HL", "BOS") or trend_state == "UPTREND":
        return "LONG"
    if label in ("LH", "LL", "BOS") and trend_state == "DOWNTREND":
        return "SHORT"
    if trend_state == "DOWNTREND":
        return "SHORT"
    if trend_state == "RANGE":
        return "NEUTRAL"
    return "UNKNOWN"


def run_market_regime_classifier() -> dict[str, Any]:
    mtf_dna = _load_json(MTF_DNA_PATH) or {}
    market_structure = _load_json(MARKET_STRUCTURE_PATH) or {}
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    atr_state = _load_json(ATR_STATE_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}

    missing_inputs: list[str] = []
    for name, payload in (
        ("latest_mtf_candle_dna", mtf_dna),
        ("latest_market_structure", market_structure),
        ("latest_business_zone", business_zone),
        ("latest_atr_state", atr_state),
        ("latest_interpretation", interpretation),
    ):
        if not payload:
            missing_inputs.append(name)

    tf_1m = mtf_dna.get("1m") or {}
    tf_5m = mtf_dna.get("5m") or {}
    ms_1m = market_structure.get("1m") or {}
    ms_5m = market_structure.get("5m") or {}
    int_1m = interpretation.get("1m") or {}
    value_area = business_zone.get("value_area") or {}
    auction_summary = business_zone.get("auction_summary") or {}

    category_1m = ((tf_1m.get("candle_category") or {}).get("primary")) or "UNKNOWN"
    category_5m = ((tf_5m.get("candle_category") or {}).get("primary")) or "UNKNOWN"
    categories = [category_1m, category_5m]
    structure_1m = str(ms_1m.get("structure_label", "UNKNOWN"))
    structure_5m = str(ms_5m.get("structure_label", "UNKNOWN"))
    trend_1m = str(ms_1m.get("trend_state", "UNKNOWN"))
    trend_5m = str(ms_5m.get("trend_state", "UNKNOWN"))
    value_position = str(value_area.get("value_position", "UNKNOWN"))
    value_migration = str(value_area.get("value_migration", "UNKNOWN"))
    cvd_state = str((int_1m.get("raw_context") or {}).get("cvd_state", "UNKNOWN"))
    liquidity_context = str((int_1m.get("raw_context") or {}).get("liquidity_event", "UNKNOWN"))

    balance_like = {"RANGE", "EQH", "EQL"}
    continuation_like = {"CONTINUATION_CANDLE", "BUY_IMBALANCE", "SELL_IMBALANCE"}
    transition_like = {
        "REVERSAL_CANDLE",
        "TRAP_CANDLE",
        "BUY_ABSORPTION",
        "SELL_ABSORPTION",
        "FAILED_AUCTION",
        "LIQUIDITY_SWEEP_UP",
        "LIQUIDITY_SWEEP_DOWN",
        "STOP_RUN_UP",
        "STOP_RUN_DOWN",
    }

    regime = "UNKNOWN"
    directional_bias = "UNKNOWN"
    reason_codes: list[str] = []

    accepted_value = str(auction_summary.get("auction_state", "UNKNOWN")) == "ACCEPTANCE"
    has_momentum_structure = (
        trend_1m in ("UPTREND", "DOWNTREND")
        or trend_5m in ("UPTREND", "DOWNTREND")
        or structure_1m in ("HH", "HL", "LH", "LL", "BOS")
        or structure_5m in ("HH", "HL", "LH", "LL", "BOS")
    )
    has_transition = (
        structure_1m in ("CHOCH", "MSS")
        or structure_5m in ("CHOCH", "MSS")
        or category_1m in transition_like
        or category_5m in transition_like
        or liquidity_context in ("SWEEP", "SPOOF_RISK")
    )
    has_balance = (
        structure_1m in balance_like
        and structure_5m in balance_like
        and category_1m in ("UNKNOWN", "NORMAL_BALANCED", "FAILED_AUCTION")
    )

    if has_transition:
        regime = "TRANSITION_MODE"
        reason_codes.append("TRANSITION_EVIDENCE_PRESENT")
    elif has_momentum_structure and (accepted_value or value_migration in ("UP", "DOWN") or any(cat in continuation_like for cat in categories)):
        regime = "MOMENTUM_MODE"
        reason_codes.append("MOMENTUM_STRUCTURE_AND_ACCEPTANCE")
    elif has_balance or value_position == "INSIDE_VALUE":
        regime = "BALANCE_MODE"
        reason_codes.append("BALANCE_STRUCTURE_AND_VALUE")

    structure_direction = _direction_from_structure(structure_1m, trend_1m)
    if regime == "MOMENTUM_MODE":
        directional_bias = structure_direction
        if directional_bias == "UNKNOWN":
            directional_bias = "LONG" if cvd_state == "BUY_PRESSURE" else "SHORT" if cvd_state == "SELL_PRESSURE" else "UNKNOWN"
    elif regime == "BALANCE_MODE":
        directional_bias = "NEUTRAL"
    elif regime == "TRANSITION_MODE":
        if value_position == "ABOVE_VALUE":
            directional_bias = "SHORT"
        elif value_position == "BELOW_VALUE":
            directional_bias = "LONG"
        else:
            directional_bias = structure_direction

    acceptance_state = "UNKNOWN"
    if value_position == "INSIDE_VALUE":
        acceptance_state = "INSIDE_VALUE"
    elif value_position == "ABOVE_VALUE":
        acceptance_state = "ACCEPTED_ABOVE_VALUE" if accepted_value else "REJECTED_FROM_VALUE"
    elif value_position == "BELOW_VALUE":
        acceptance_state = "ACCEPTED_BELOW_VALUE" if accepted_value else "REJECTED_FROM_VALUE"

    day_type = "UNKNOWN"
    if regime == "BALANCE_MODE":
        day_type = "BALANCED_DAY" if not auction_summary.get("rejection") else "ROTATIONAL_DAY"
    elif regime == "MOMENTUM_MODE":
        day_type = "TREND_DAY"
    elif regime == "TRANSITION_MODE":
        day_type = "DOUBLE_DISTRIBUTION_DAY" if accepted_value and value_migration in ("UP", "DOWN") else "ROTATIONAL_DAY"

    atr_1m = atr_state.get("1m") or {}
    atr_quality = str(atr_1m.get("atr_quality", "MISSING"))
    atr_expansion = "UNKNOWN"
    if atr_quality != "MISSING":
        tr_latest = _safe_float(atr_1m.get("true_range_latest"))
        atr_14 = _safe_float(atr_1m.get("atr_14"))
        if tr_latest is not None and atr_14 is not None:
            atr_expansion = "EXPANDING" if tr_latest > atr_14 else "CONTRACTING"

    score = 0.0
    if mtf_dna and market_structure:
        score += 0.4
    if business_zone:
        score += 0.2
    if interpretation:
        score += 0.2
    if atr_state:
        score += 0.1
    if regime != "UNKNOWN":
        score += 0.1
    score = min(1.0, score)

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(mtf_dna.get("symbol") or business_zone.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "MTF_STRUCTURE_VALUE_REGIME",
        },
        "regime": regime,
        "day_type": day_type,
        "acceptance_state": acceptance_state,
        "directional_bias": directional_bias,
        "evidence": {
            "structure": {"1m": structure_1m, "5m": structure_5m, "trend_1m": trend_1m, "trend_5m": trend_5m},
            "value_position": value_position,
            "delta_alignment": cvd_state,
            "atr_expansion": atr_expansion,
            "candle_categories": categories,
            "liquidity_context": liquidity_context,
        },
        "reason_codes": [
            f"SYMBOL_{str(mtf_dna.get('symbol') or business_zone.get('symbol') or 'BTCUSDT')}",
            *reason_codes,
            f"REGIME_{regime}",
            f"DAY_{day_type}",
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
    print(json.dumps(run_market_regime_classifier(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
