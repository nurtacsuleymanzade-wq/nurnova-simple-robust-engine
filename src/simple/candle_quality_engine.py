from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

MARKET_TRUTH_PATH = STATE_DIR / "latest_market_truth.json"
FLOW_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
FLOW_PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
CQE_PATH = STATE_DIR / "latest_cqe.json"
CQE_LOG_PATH = DATA_DIR / "cqe_history.jsonl"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _extract_candle(market_truth: dict[str, Any]) -> dict[str, Any]:
    candle = market_truth.get("candle")
    if isinstance(candle, dict):
        return candle

    official = market_truth.get("official_candle")
    if isinstance(official, dict):
        return official

    truth = market_truth.get("market_truth", {})
    return {
        "open": truth.get("official_open"),
        "high": truth.get("official_high"),
        "low": truth.get("official_low"),
        "close": truth.get("official_close"),
        "volume": truth.get("official_volume"),
    }


def compute_candle_quality(
    market_truth: dict[str, Any],
    evidence: dict[str, Any],
    persistence: dict[str, Any],
) -> dict[str, Any]:
    candle = _extract_candle(market_truth)
    open_price = float(candle.get("open", 0.0) or 0.0)
    high = float(candle.get("high", 0.0) or 0.0)
    low = float(candle.get("low", 0.0) or 0.0)
    close = float(candle.get("close", 0.0) or 0.0)

    body_size = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    candle_range = high - low

    body_ratio = round(body_size / candle_range, 4) if candle_range > 0 else 0.0
    upper_wick_ratio = round(upper_wick / candle_range, 4) if candle_range > 0 else 0.0
    lower_wick_ratio = round(lower_wick / candle_range, 4) if candle_range > 0 else 0.0

    candle_direction = "BULLISH" if close > open_price else ("BEARISH" if close < open_price else "DOJI")
    delta_score = float((evidence.get("delta_evidence") or {}).get("delta_score", 0.0))
    delta_aligned = (
        (candle_direction == "BULLISH" and delta_score > 0.0)
        or (candle_direction == "BEARISH" and delta_score < 0.0)
    )

    fake_move_probability = 0.0
    if upper_wick_ratio > 0.6 and candle_direction == "BULLISH":
        fake_move_probability += 40.0
    if lower_wick_ratio > 0.6 and candle_direction == "BEARISH":
        fake_move_probability += 40.0
    if not delta_aligned:
        fake_move_probability += 30.0
    if body_ratio < 0.2:
        fake_move_probability += 20.0

    last_60s = ((persistence.get("windows") or {}).get("last_60s") or {})
    avg_60s = float(last_60s.get("avg_evidence_score", 0.0))
    if candle_direction == "BULLISH" and avg_60s < -0.5:
        fake_move_probability += 10.0
    elif candle_direction == "BEARISH" and avg_60s > 0.5:
        fake_move_probability += 10.0

    fake_move_probability = round(_clamp(fake_move_probability, 0.0, 100.0), 2)

    if fake_move_probability < 20.0 and delta_aligned and body_ratio > 0.5:
        candle_quality = "STRONG_BULLISH" if candle_direction == "BULLISH" else "STRONG_BEARISH"
    elif fake_move_probability > 60.0:
        candle_quality = "FAKE_MOVE"
    else:
        candle_quality = f"WEAK_{candle_direction}"

    symbol = evidence.get("symbol") or market_truth.get("symbol") or persistence.get("symbol") or "UNKNOWN"
    mt_dq = float((market_truth.get("data_quality") or {}).get("score", 0.0))
    ev_dq = float((evidence.get("data_quality") or {}).get("score", 0.0))
    pers_dq = float((persistence.get("data_quality") or {}).get("score", 0.0))
    dq_score = round((mt_dq + ev_dq + pers_dq) / 3.0, 4)
    dq_level = (
        "OK" if dq_score >= 0.85
        else "REDUCED" if dq_score >= 0.6
        else "LOW" if dq_score > 0.0
        else "MISSING"
    )

    reason_codes = [f"SYMBOL_{symbol}"]
    if delta_aligned:
        reason_codes.append("DELTA_ALIGNED")
    else:
        reason_codes.append("DELTA_MISALIGNED")
    if body_ratio > 0.5:
        reason_codes.append("STRONG_BODY")
    elif body_ratio < 0.2:
        reason_codes.append("WEAK_BODY")
    if fake_move_probability <= 20.0:
        reason_codes.append("LOW_FAKE_PROBABILITY")
    elif fake_move_probability >= 60.0:
        reason_codes.append("HIGH_FAKE_PROBABILITY")
    reason_codes += [
        f"DQ_{dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
    ]

    return {
        "timestamp_utc": _now_utc(),
        "block_id": "CQE_CANDLE_QUALITY",
        "symbol": symbol,
        "source": "S1_S13_MARKET_FLOW",
        "input_status": "OK",
        "candle_direction": candle_direction,
        "body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "delta_aligned": delta_aligned,
        "fake_move_probability": fake_move_probability,
        "candle_quality": candle_quality,
        "timeframe": "1m",
        "candle_close_time": (
            (market_truth.get("official_candle") or {}).get("close_time_utc")
            or evidence.get("timestamp_utc", "UNKNOWN")
        ),
        "reason_codes": reason_codes,
        "data_quality": {"level": dq_level, "score": dq_score},
        "feeds_next": {"next_blocks": ["S6_SCENARIO_SETUP_CANDIDATE", "S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_output(reason: str) -> dict[str, Any]:
    return {
        "timestamp_utc": _now_utc(),
        "block_id": "CQE_CANDLE_QUALITY",
        "symbol": "UNKNOWN",
        "source": "S1_S13_MARKET_FLOW",
        "input_status": "MISSING",
        "candle_direction": "DOJI",
        "body_ratio": 0.0,
        "upper_wick_ratio": 0.0,
        "lower_wick_ratio": 0.0,
        "delta_aligned": False,
        "fake_move_probability": 0.0,
        "candle_quality": "UNKNOWN",
        "timeframe": "1m",
        "candle_close_time": "UNKNOWN",
        "reason_codes": [
            "INPUT_MISSING",
            reason,
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
        ],
        "data_quality": {"level": "MISSING", "score": 0.0},
        "feeds_next": {"next_blocks": ["S6_SCENARIO_SETUP_CANDIDATE", "S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_candle_quality_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    market_truth = _load_json(MARKET_TRUTH_PATH)
    evidence = _load_json(FLOW_EVIDENCE_PATH)
    persistence = _load_json(FLOW_PERSISTENCE_PATH)
    if market_truth is None or evidence is None or persistence is None:
        result = no_valid_output("REQUIRED_INPUT_MISSING")
    else:
        try:
            result = compute_candle_quality(market_truth, evidence, persistence)
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    CQE_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with CQE_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result) + "\n")
    return result
