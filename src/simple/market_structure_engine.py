"""Market Structure Engine.

Builds conservative per-timeframe structure state from observed MTF candle DNA
history. This is descriptive only and does not emit trade logic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MARKET_STRUCTURE_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

LATEST_MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MTF_HISTORY_PATH = DATA_DIR / "mtf_candle_dna_history.jsonl"
OUTPUT_PATH = STATE_DIR / "latest_market_structure.json"
HISTORY_PATH = DATA_DIR / "market_structure_history.jsonl"

TIMEFRAMES = ["1s", "3s", "5s", "15s", "1m", "3m", "5m", "15m", "1h", "4h", "12h", "1d"]
EQUAL_LEVEL_TOLERANCE_PCT = 0.0002


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


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load_mtf_history() -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    if MTF_HISTORY_PATH.exists():
        try:
            for line in MTF_HISTORY_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                history.append(record)
        except Exception:
            history = []

    latest = _load_json(LATEST_MTF_DNA_PATH)
    if latest:
        latest_ts = latest.get("timestamp_utc")
        if not history or history[-1].get("timestamp_utc") != latest_ts:
            history.append(latest)

    history.sort(key=lambda item: item.get("timestamp_utc", ""))
    return history


def _direction_from_truth(candle_truth: str | None) -> str:
    if candle_truth in ("REAL_BULLISH", "WEAK_BULLISH", "FAKE_BULLISH"):
        return "UP"
    if candle_truth in ("REAL_BEARISH", "WEAK_BEARISH", "FAKE_BEARISH"):
        return "DOWN"
    if candle_truth == "BALANCED":
        return "RANGE"
    return "UNKNOWN"


def _history_for_tf(history: list[dict[str, Any]], tf: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in history:
        tf_payload = record.get(tf)
        if not isinstance(tf_payload, dict):
            continue
        candle = dict(tf_payload)
        candle["timestamp_utc"] = record.get("timestamp_utc")
        entries.append(candle)
    return entries


def _valid_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for candle in candles:
        if all(candle.get(field_name) is not None for field_name in ("open", "high", "low", "close")):
            valid.append(candle)
    return valid


def _equal_zone(price_a: float | None, price_b: float | None) -> dict[str, Any] | None:
    if price_a is None or price_b is None:
        return None
    ref = max(abs(price_a), abs(price_b), 1.0)
    distance_pct = abs(price_a - price_b) / ref
    if distance_pct <= EQUAL_LEVEL_TOLERANCE_PCT:
        return {
            "price": round((price_a + price_b) / 2.0, 8),
            "tolerance_pct": EQUAL_LEVEL_TOLERANCE_PCT,
        }
    return None


def _last_swing_levels(candles: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    swing_high = None
    swing_low = None
    for idx in range(1, len(candles) - 1):
        prev_candle = candles[idx - 1]
        current = candles[idx]
        next_candle = candles[idx + 1]
        current_high = _safe_float(current.get("high"))
        current_low = _safe_float(current.get("low"))
        if current_high is not None:
            prev_high = _safe_float(prev_candle.get("high"))
            next_high = _safe_float(next_candle.get("high"))
            if prev_high is not None and next_high is not None and current_high >= prev_high and current_high >= next_high:
                swing_high = current_high
        if current_low is not None:
            prev_low = _safe_float(prev_candle.get("low"))
            next_low = _safe_float(next_candle.get("low"))
            if prev_low is not None and next_low is not None and current_low <= prev_low and current_low <= next_low:
                swing_low = current_low
    return swing_high, swing_low


def _base_structure_label(prev_candle: dict[str, Any], current_candle: dict[str, Any]) -> str:
    prev_high = _safe_float(prev_candle.get("high"))
    prev_low = _safe_float(prev_candle.get("low"))
    current_high = _safe_float(current_candle.get("high"))
    current_low = _safe_float(current_candle.get("low"))
    if None in (prev_high, prev_low, current_high, current_low):
        return "UNKNOWN"

    if _equal_zone(current_high, prev_high):
        return "EQH"
    if _equal_zone(current_low, prev_low):
        return "EQL"
    if current_high > prev_high and current_low >= prev_low:
        return "HH"
    if current_low > prev_low:
        return "HL"
    if current_low < prev_low and current_high <= prev_high:
        return "LL"
    if current_high < prev_high:
        return "LH"
    return "RANGE"


def _trend_state(candles: list[dict[str, Any]], choch_detected: bool, mss_detected: bool) -> str:
    if choch_detected or mss_detected:
        return "TRANSITION"
    if len(candles) < 4:
        return "UNKNOWN"

    labels: list[str] = []
    for idx in range(max(1, len(candles) - 3), len(candles)):
        labels.append(_base_structure_label(candles[idx - 1], candles[idx]))

    if labels.count("HH") + labels.count("HL") >= 2:
        return "UPTREND"
    if labels.count("LH") + labels.count("LL") >= 2:
        return "DOWNTREND"

    balanced_categories = 0
    for candle in candles[-3:]:
        primary = ((candle.get("candle_category") or {}).get("primary")) or "UNKNOWN"
        if primary in ("NORMAL_BALANCED", "FAILED_AUCTION", "UNKNOWN"):
            balanced_categories += 1
    if balanced_categories >= 2 or any(label in ("EQH", "EQL", "RANGE") for label in labels):
        return "RANGE"
    return "UNKNOWN"


def _data_quality(sample_count: int, missing_fields: list[str]) -> dict[str, Any]:
    if sample_count == 0:
        level = "MISSING"
    elif sample_count >= 8 and not missing_fields:
        level = "HIGH"
    elif sample_count >= 5:
        level = "OK"
    elif sample_count >= 3:
        level = "REDUCED"
    else:
        level = "LOW"
    return {
        "level": level,
        "sample_count": sample_count,
        "missing_fields": missing_fields,
    }


def _empty_structure(tf: str, sample_count: int = 0, missing_fields: list[str] | None = None) -> dict[str, Any]:
    return {
        "tf": tf,
        "structure_label": "UNKNOWN",
        "trend_state": "UNKNOWN",
        "last_swing_high": None,
        "last_swing_low": None,
        "equal_high_zone": None,
        "equal_low_zone": None,
        "bos_detected": False,
        "choch_detected": False,
        "mss_detected": False,
        "reason_codes": ["INSUFFICIENT_STRUCTURE_HISTORY"],
        "data_quality": _data_quality(sample_count, missing_fields or []),
    }


def _compute_structure_for_tf(tf: str, candles: list[dict[str, Any]]) -> dict[str, Any]:
    valid = _valid_candles(candles)
    sample_count = len(valid)
    missing_fields = [] if sample_count == len(candles) else ["open", "high", "low", "close"]
    if sample_count < 3:
        return _empty_structure(tf, sample_count, missing_fields)

    current = valid[-1]
    previous = valid[-2]
    prior_window = valid[:-1]
    previous_trend = _trend_state(prior_window, False, False)
    base_label = _base_structure_label(previous, current)
    swing_high, swing_low = _last_swing_levels(valid)
    equal_high_zone = _equal_zone(_safe_float(current.get("high")), _safe_float(previous.get("high")))
    equal_low_zone = _equal_zone(_safe_float(current.get("low")), _safe_float(previous.get("low")))

    current_close = _safe_float(current.get("close"))
    bos_up = swing_high is not None and current_close is not None and current_close > swing_high * (1.0 + EQUAL_LEVEL_TOLERANCE_PCT)
    bos_down = swing_low is not None and current_close is not None and current_close < swing_low * (1.0 - EQUAL_LEVEL_TOLERANCE_PCT)
    bos_detected = bos_up or bos_down
    choch_detected = (
        (previous_trend == "UPTREND" and bos_down)
        or (previous_trend == "DOWNTREND" and bos_up)
    )
    current_category = ((current.get("candle_category") or {}).get("primary")) or "UNKNOWN"
    mss_detected = choch_detected and current_category in (
        "REVERSAL_CANDLE",
        "TRAP_CANDLE",
        "BUY_ABSORPTION",
        "SELL_ABSORPTION",
        "LIQUIDITY_SWEEP_UP",
        "LIQUIDITY_SWEEP_DOWN",
        "STOP_RUN_UP",
        "STOP_RUN_DOWN",
    )
    trend_state = _trend_state(valid, choch_detected, mss_detected)

    if mss_detected:
        structure_label = "MSS"
    elif choch_detected:
        structure_label = "CHOCH"
    elif bos_detected:
        structure_label = "BOS"
    else:
        structure_label = base_label

    reason_codes = [
        f"TF_{tf}",
        f"EQUAL_LEVEL_TOLERANCE_PCT_{EQUAL_LEVEL_TOLERANCE_PCT}",
        f"BASE_{base_label}",
        f"PREVIOUS_TREND_{previous_trend}",
        f"CANDLE_CATEGORY_{current_category}",
    ]
    if swing_high is not None:
        reason_codes.append("SWING_HIGH_OBSERVED")
    if swing_low is not None:
        reason_codes.append("SWING_LOW_OBSERVED")
    if equal_high_zone is not None:
        reason_codes.append("EQH_ZONE_DETECTED")
    if equal_low_zone is not None:
        reason_codes.append("EQL_ZONE_DETECTED")
    if bos_up:
        reason_codes.append("BOS_UP_DETECTED")
    if bos_down:
        reason_codes.append("BOS_DOWN_DETECTED")
    if choch_detected:
        reason_codes.append("CHOCH_DETECTED")
    if mss_detected:
        reason_codes.append("MSS_DETECTED")

    return {
        "tf": tf,
        "structure_label": structure_label,
        "trend_state": trend_state,
        "last_swing_high": swing_high,
        "last_swing_low": swing_low,
        "equal_high_zone": equal_high_zone,
        "equal_low_zone": equal_low_zone,
        "bos_detected": bos_detected,
        "choch_detected": choch_detected,
        "mss_detected": mss_detected,
        "reason_codes": reason_codes,
        "data_quality": _data_quality(sample_count, missing_fields),
    }


def run_market_structure_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    history = _load_mtf_history()
    latest = _load_json(LATEST_MTF_DNA_PATH) or {}
    symbol = latest.get("symbol", "BTCUSDT")

    per_tf: dict[str, dict[str, Any]] = {}
    available_tfs = 0
    low_quality_tfs: list[str] = []
    for tf in TIMEFRAMES:
        candles = _history_for_tf(history, tf)
        structure = _compute_structure_for_tf(tf, candles)
        per_tf[tf] = structure
        if structure["data_quality"]["sample_count"] > 0:
            available_tfs += 1
        if structure["data_quality"]["level"] in ("LOW", "MISSING"):
            low_quality_tfs.append(tf)

    missing_inputs = []
    if not latest:
        missing_inputs.append("latest_mtf_candle_dna")
    if not history:
        missing_inputs.append("mtf_candle_dna_history")

    if available_tfs == 0:
        dq_level = "MISSING"
        dq_score = 0.0
    elif len(low_quality_tfs) == 0:
        dq_level = "OK"
        dq_score = 0.8
    else:
        dq_level = "LOW"
        dq_score = 0.4

    result: dict[str, Any] = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": "MTF_CANDLE_DNA_HISTORY",
        },
        "summary": {
            "timeframes_total": len(TIMEFRAMES),
            "timeframes_with_samples": available_tfs,
            "low_quality_timeframes": low_quality_tfs,
        },
        "data_quality": {
            "level": dq_level,
            "score": dq_score,
            "missing_inputs": missing_inputs,
        },
        "reason_codes": [
            f"SYMBOL_{symbol}",
            f"TIMEFRAMES_WITH_SAMPLES_{available_tfs}",
            f"EQUAL_LEVEL_TOLERANCE_PCT_{EQUAL_LEVEL_TOLERANCE_PCT}",
            f"DQ_{dq_level}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "LIQUIDITY_MAP_ENGINE",
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
    print(json.dumps(run_market_structure_engine(), indent=2))


if __name__ == "__main__":
    main()
