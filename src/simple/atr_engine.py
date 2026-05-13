"""ATR Engine.

Computes ATR from locally produced MTF candle DNA history.
ATR is volatility normalization only. It does not create trade signals.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "ATR_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

LATEST_MTF_CANDLE_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MTF_CANDLE_DNA_HISTORY_PATH = DATA_DIR / "mtf_candle_dna_history.jsonl"
OUTPUT_PATH = STATE_DIR / "latest_atr_state.json"
HISTORY_PATH = DATA_DIR / "atr_state_history.jsonl"

TARGET_TIMEFRAMES = ["1m", "3m", "5m", "15m", "1h", "4h", "12h", "1d"]


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


def _history_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if MTF_CANDLE_DNA_HISTORY_PATH.exists():
        try:
            for line in MTF_CANDLE_DNA_HISTORY_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        except Exception:
            records = []

    latest = _load_json(LATEST_MTF_CANDLE_DNA_PATH)
    if latest:
        records.append(latest)

    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        latest_reference_ts = ((record.get("source") or {}).get("latest_reference_ts")) or record.get("timestamp_utc")
        if latest_reference_ts:
            deduped[str(latest_reference_ts)] = record

    sorted_records = sorted(
        deduped.values(),
        key=lambda record: _parse_ts(((record.get("source") or {}).get("latest_reference_ts")) or record.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    return sorted_records


def _empty_tf(tf: str, extra_reason_codes: list[str] | None = None) -> dict[str, Any]:
    reason_codes = list(extra_reason_codes or [])
    if "INSUFFICIENT_ATR_HISTORY" not in reason_codes:
        reason_codes.append("INSUFFICIENT_ATR_HISTORY")
    return {
        "tf": tf,
        "atr_14": None,
        "atr_21": None,
        "true_range_latest": None,
        "atr_quality": "MISSING",
        "sample_count": 0,
        "reason_codes": reason_codes,
    }


def _extract_tf_candles(records: list[dict[str, Any]], tf: str) -> tuple[list[dict[str, float]], int]:
    candles: list[dict[str, float]] = []
    missing_ohlc_count = 0
    for record in records:
        tf_payload = record.get(tf)
        if not isinstance(tf_payload, dict):
            continue
        open_ = _safe_float(tf_payload.get("open"))
        high = _safe_float(tf_payload.get("high"))
        low = _safe_float(tf_payload.get("low"))
        close = _safe_float(tf_payload.get("close"))
        if high is None or low is None or close is None:
            missing_ohlc_count += 1
            continue
        candles.append(
            {
                "open": open_ if open_ is not None else close,
                "high": high,
                "low": low,
                "close": close,
            }
        )
    return candles, missing_ohlc_count


def _true_ranges(candles: list[dict[str, float]]) -> list[float]:
    ranges: list[float] = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous_close = candles[index - 1]["close"]
        true_range = max(
            current["high"] - current["low"],
            abs(current["high"] - previous_close),
            abs(current["low"] - previous_close),
        )
        ranges.append(round(true_range, 8))
    return ranges


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 8)


def _atr_quality(sample_count: int) -> str:
    if sample_count <= 0:
        return "MISSING"
    if sample_count < 14:
        return "LOW"
    if sample_count < 21:
        return "REDUCED"
    if sample_count < 42:
        return "OK"
    return "HIGH"


def _build_tf_state(tf: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    candles, missing_ohlc_count = _extract_tf_candles(records, tf)
    if len(candles) < 2:
        reason_codes = ["INSUFFICIENT_ATR_HISTORY"]
        if missing_ohlc_count > 0:
            reason_codes.append("MISSING_OHLC_FIELDS")
        return _empty_tf(tf, reason_codes)

    ranges = _true_ranges(candles)
    sample_count = len(ranges)
    atr_14 = _sma(ranges, 14)
    atr_21 = _sma(ranges, 21)
    true_range_latest = ranges[-1] if ranges else None

    reason_codes: list[str] = []
    if missing_ohlc_count > 0:
        reason_codes.append("MISSING_OHLC_FIELDS")
    if atr_14 is None or atr_21 is None:
        reason_codes.append("INSUFFICIENT_ATR_HISTORY")
    if not reason_codes:
        reason_codes.append("ATR_FROM_MTF_CANDLE_DNA_HISTORY")

    return {
        "tf": tf,
        "atr_14": atr_14,
        "atr_21": atr_21,
        "true_range_latest": true_range_latest,
        "atr_quality": _atr_quality(sample_count),
        "sample_count": sample_count,
        "reason_codes": reason_codes,
    }


def run_atr_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    latest_mtf_candle_dna = _load_json(LATEST_MTF_CANDLE_DNA_PATH)
    history_records = _history_records()

    available_inputs = []
    missing_inputs = []
    if latest_mtf_candle_dna is not None:
        available_inputs.append("latest_mtf_candle_dna")
    else:
        missing_inputs.append("latest_mtf_candle_dna")
    if history_records:
        available_inputs.append("mtf_candle_dna_history")
    else:
        missing_inputs.append("mtf_candle_dna_history")

    result: dict[str, Any] = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": (latest_mtf_candle_dna or {}).get("symbol", "BTCUSDT"),
        "source": {
            "source_mode": "MTF_CANDLE_DNA_HISTORY_ATR",
            "input_files": [
                str(LATEST_MTF_CANDLE_DNA_PATH).replace("\\", "/"),
                str(MTF_CANDLE_DNA_HISTORY_PATH).replace("\\", "/"),
            ],
        },
        "data_quality": {
            "level": "MISSING",
            "score": 0.0,
            "available_inputs": available_inputs,
            "missing_inputs": missing_inputs,
        },
        "reason_codes": [
            "ATR_NOT_A_SIGNAL",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "MARKET_STRUCTURE_ENGINE",
            "LIQUIDITY_MAP_ENGINE",
            "S15_FLOW_TO_SETUP_CONTEXT",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    non_missing_timeframes = 0
    high_or_ok_timeframes = 0
    for tf in TARGET_TIMEFRAMES:
        tf_state = _build_tf_state(tf, history_records)
        result[tf] = tf_state
        if tf_state["sample_count"] > 0:
            non_missing_timeframes += 1
        if tf_state["atr_quality"] in ("HIGH", "OK"):
            high_or_ok_timeframes += 1

    if non_missing_timeframes == 0:
        dq_level = "MISSING"
        dq_score = 0.0
    elif high_or_ok_timeframes == len(TARGET_TIMEFRAMES):
        dq_level = "HIGH"
        dq_score = 1.0
    elif high_or_ok_timeframes > 0:
        dq_level = "OK"
        dq_score = round(0.5 + (high_or_ok_timeframes / len(TARGET_TIMEFRAMES)) * 0.25, 4)
    else:
        dq_level = "LOW"
        dq_score = round(0.25 + (non_missing_timeframes / len(TARGET_TIMEFRAMES)) * 0.15, 4)

    result["data_quality"]["level"] = dq_level
    result["data_quality"]["score"] = dq_score
    result["reason_codes"].extend(
        [
            f"DQ_{dq_level}",
            f"ATR_TIMEFRAMES_{non_missing_timeframes}_{len(TARGET_TIMEFRAMES)}",
        ]
    )

    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, result)
    return result


def main() -> None:
    print(json.dumps(run_atr_engine(), indent=2))


if __name__ == "__main__":
    main()
