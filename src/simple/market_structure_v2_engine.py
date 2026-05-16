from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, write_json

BLOCK_ID = "MARKET_STRUCTURE_V2"
STATE_DIR = Path("state/simple")
OUTPUT_PATH = STATE_DIR / "latest_market_structure_v2.json"

LATEST_MARKET_TRUTH_PATH = STATE_DIR / "latest_market_truth.json"
LATEST_HYBRID_DNA_PATH = STATE_DIR / "latest_hybrid_candle_dna.json"
LATEST_1S_EVIDENCE_PATH = STATE_DIR / "latest_1s_evidence.json"
ONE_SECOND_EVIDENCE_JSONL_PATH = Path("data/simple/one_second_evidence.jsonl")

FEEDS_NEXT = [
    "REGIME_CLASSIFIER",
    "SETUP_CONTRACT_ENGINE",
    "TRADE_PLAN_ENGINE",
    "DECISION_GATE",
]

MIN_CANDLES = 20
SWING_LOOKBACK = 2
EQ_TOLERANCE = 0.001


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out <= 0:
        return None
    return out


def _extract_ts_seconds(row: dict[str, Any]) -> float | None:
    for key in ("second_epoch", "ts", "timestamp", "event_time"):
        raw = row.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            ts = float(raw)
            if ts > 1e12:
                ts /= 1000.0
            return ts
    iso = row.get("timestamp_utc")
    if isinstance(iso, str):
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
    return None


def _extract_ohlc_from_row(row: dict[str, Any], prev_close: float | None = None) -> tuple[float, float, float, float] | None:
    open_v = _safe_float(row.get("open")) or _safe_float(row.get("o")) or _safe_float(row.get("price_open"))
    high_v = _safe_float(row.get("high")) or _safe_float(row.get("h")) or _safe_float(row.get("price_high"))
    low_v = _safe_float(row.get("low")) or _safe_float(row.get("l")) or _safe_float(row.get("price_low"))
    close_v = (
        _safe_float(row.get("close"))
        or _safe_float(row.get("c"))
        or _safe_float(row.get("price_close"))
        or _safe_float(row.get("latest_price"))
        or _safe_float(row.get("price"))
    )
    fallback_price = close_v or _safe_float(row.get("price")) or prev_close
    if open_v is None:
        open_v = fallback_price
    if high_v is None:
        high_v = fallback_price
    if low_v is None:
        low_v = fallback_price
    if close_v is None:
        close_v = fallback_price
    if open_v is None or high_v is None or low_v is None or close_v is None:
        return None
    high_v = max(high_v, open_v, close_v)
    low_v = min(low_v, open_v, close_v)
    return open_v, high_v, low_v, close_v


def _normalize_candle_like(row: dict[str, Any], prev_close: float | None = None) -> dict[str, Any] | None:
    ohlc = _extract_ohlc_from_row(row, prev_close=prev_close)
    if ohlc is None:
        return None
    open_v, high_v, low_v, close_v = ohlc
    ts = _extract_ts_seconds(row)
    return {"open": open_v, "high": high_v, "low": low_v, "close": close_v, "ts": ts}


def _aggregate_seconds_to_1m(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    minute_buckets: dict[int, dict[str, Any]] = {}
    prev_close: float | None = None
    for row in rows:
        ts = _extract_ts_seconds(row)
        if ts is None:
            continue
        normalized = _normalize_candle_like(row, prev_close=prev_close)
        if normalized is None:
            continue
        prev_close = float(normalized["close"])
        minute_key = int(ts // 60)
        if minute_key not in minute_buckets:
            minute_buckets[minute_key] = {
                "open": float(normalized["open"]),
                "high": float(normalized["high"]),
                "low": float(normalized["low"]),
                "close": float(normalized["close"]),
                "ts": minute_key * 60,
            }
            continue
        bucket = minute_buckets[minute_key]
        bucket["high"] = max(float(bucket["high"]), float(normalized["high"]))
        bucket["low"] = min(float(bucket["low"]), float(normalized["low"]))
        bucket["close"] = float(normalized["close"])
    return [minute_buckets[k] for k in sorted(minute_buckets.keys())]


def _load_1s_evidence_jsonl_tail(path: Path, max_lines: int = 600) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("json"):
            line = line[4:].strip()
        try:
            raw = json.loads(line)
        except Exception:
            continue
        if isinstance(raw, dict):
            out.append(raw)
    return out


def _extract_candles() -> tuple[list[dict[str, Any]], list[str]]:
    reason_codes: list[str] = []
    tried_sources: list[str] = []

    # Priority A: data/simple/one_second_evidence.jsonl
    tried_sources.append("ONE_SECOND_EVIDENCE_JSONL")
    evidence_rows = _load_1s_evidence_jsonl_tail(ONE_SECOND_EVIDENCE_JSONL_PATH, max_lines=600)
    if evidence_rows:
        candles = _aggregate_seconds_to_1m(evidence_rows)
        if len(candles) >= 5:
            reason_codes.append("CANDLES_FROM_1S_EVIDENCE")
            return candles, reason_codes

    # Priority B: state/simple/latest_1s_evidence.json
    tried_sources.append("LATEST_1S_EVIDENCE")
    evidence_state = _load_json(LATEST_1S_EVIDENCE_PATH)
    if evidence_state:
        raw_points = (
            evidence_state.get("recent_buckets")
            or evidence_state.get("candles")
            or evidence_state.get("evidence_points")
            or []
        )
        if isinstance(raw_points, list):
            candles = _aggregate_seconds_to_1m([x for x in raw_points if isinstance(x, dict)])
            if len(candles) >= 5:
                reason_codes.append("CANDLES_FROM_LATEST_1S_EVIDENCE")
                return candles, reason_codes

    # Priority C: state/simple/latest_hybrid_candle_dna.json
    tried_sources.append("LATEST_HYBRID_CANDLE_DNA")
    hybrid = _load_json(LATEST_HYBRID_DNA_PATH)
    if hybrid:
        raw = hybrid.get("candles") or hybrid.get("official_candle")
        rows: list[dict[str, Any]] = []
        if isinstance(raw, list):
            rows = [x for x in raw if isinstance(x, dict)]
        elif isinstance(raw, dict):
            rows = [raw]
        candles = []
        prev_close: float | None = None
        for row in rows:
            normalized = _normalize_candle_like(row, prev_close=prev_close)
            if normalized:
                candles.append(normalized)
                prev_close = float(normalized["close"])
        if candles:
            reason_codes.append("CANDLES_FROM_HYBRID_DNA")
            return candles, reason_codes

    # Priority D: state/simple/latest_market_truth.json
    tried_sources.append("LATEST_MARKET_TRUTH")
    market_truth = _load_json(LATEST_MARKET_TRUTH_PATH)
    if market_truth:
        raw = market_truth.get("candles") or market_truth.get("ohlc_candles") or market_truth.get("official_candle")
        rows = []
        if isinstance(raw, list):
            rows = [x for x in raw if isinstance(x, dict)]
        elif isinstance(raw, dict):
            rows = [raw]
        candles = []
        prev_close = None
        for row in rows:
            normalized = _normalize_candle_like(row, prev_close=prev_close)
            if normalized:
                candles.append(normalized)
                prev_close = float(normalized["close"])
        if candles:
            reason_codes.append("CANDLES_FROM_MARKET_TRUTH")
            return candles, reason_codes

    reason_codes.append("INSUFFICIENT_CANDLES_FOR_STRUCTURE")
    reason_codes.extend([f"SOURCE_TRIED_{name}" for name in tried_sources])
    if not ONE_SECOND_EVIDENCE_JSONL_PATH.exists():
        reason_codes.append("SOURCE_FILE_MISSING")
    return [], sorted(set(reason_codes))


def _sample_candles(symbol: str) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    base = 100_000.0 if symbol.upper().startswith("BTC") else 100.0
    steps = [0, 24, 2, 22, 4, 25, 3, 23, 5, 26, 4, 24, 6, 27, 5, 25, 7, 28, 6, 26, 8, 29, 7, 27]
    for idx, offset in enumerate(steps):
        close = base + offset
        open_ = close - 3.0
        high = close + 4.0
        low = close - 6.0
        candles.append({"open": open_, "high": high, "low": low, "close": close, "ts": idx * 60})
    return candles


def _detect_swings(candles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    swing_highs: list[dict[str, Any]] = []
    swing_lows: list[dict[str, Any]] = []
    if len(candles) < (SWING_LOOKBACK * 2 + 1):
        return swing_highs, swing_lows

    for i in range(SWING_LOOKBACK, len(candles) - SWING_LOOKBACK):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        is_sh = all(high > float(candles[i - j]["high"]) for j in range(1, SWING_LOOKBACK + 1)) and all(
            high > float(candles[i + j]["high"]) for j in range(1, SWING_LOOKBACK + 1)
        )
        is_sl = all(low < float(candles[i - j]["low"]) for j in range(1, SWING_LOOKBACK + 1)) and all(
            low < float(candles[i + j]["low"]) for j in range(1, SWING_LOOKBACK + 1)
        )
        if is_sh:
            swing_highs.append({"index": i, "price": high, "ts": candles[i].get("ts")})
        if is_sl:
            swing_lows.append({"index": i, "price": low, "ts": candles[i].get("ts")})
    return swing_highs, swing_lows


def _equal_levels(swings: list[dict[str, Any]]) -> list[float]:
    prices = [float(s["price"]) for s in swings]
    levels: set[float] = set()
    for i in range(len(prices)):
        for j in range(i + 1, len(prices)):
            ref = max(abs(prices[i]), 1.0)
            if abs(prices[i] - prices[j]) / ref <= EQ_TOLERANCE:
                levels.add(round((prices[i] + prices[j]) / 2.0, 6))
    return sorted(levels)


def _last_structure_points(swing_highs: list[dict[str, Any]], swing_lows: list[dict[str, Any]]) -> dict[str, float | None]:
    return {
        "last_hh": swing_highs[-1]["price"] if len(swing_highs) >= 1 else None,
        "last_lh": swing_highs[-2]["price"] if len(swing_highs) >= 2 else None,
        "last_hl": swing_lows[-1]["price"] if len(swing_lows) >= 1 else None,
        "last_ll": swing_lows[-2]["price"] if len(swing_lows) >= 2 else None,
    }


def _bias_and_direction(swing_highs: list[dict[str, Any]], swing_lows: list[dict[str, Any]]) -> tuple[str, str, str]:
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        hh_up = swing_highs[-1]["price"] > swing_highs[-2]["price"]
        hl_up = swing_lows[-1]["price"] > swing_lows[-2]["price"]
        lh_down = swing_highs[-1]["price"] < swing_highs[-2]["price"]
        ll_down = swing_lows[-1]["price"] < swing_lows[-2]["price"]
        if hh_up and hl_up:
            return "LONG", "LONG", "TREND_UP"
        if lh_down and ll_down:
            return "SHORT", "SHORT", "TREND_DOWN"
        return "NEUTRAL", "NEUTRAL", "RANGE"
    return "NEUTRAL", "NEUTRAL", "UNKNOWN"


def _bos_choch(candles: list[dict[str, Any]], swing_highs: list[dict[str, Any]], swing_lows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not candles:
        return None, None
    close = float(candles[-1]["close"])
    bos = None
    if swing_highs and close > float(swing_highs[-1]["price"]):
        bos = "BULLISH_BOS"
    elif swing_lows and close < float(swing_lows[-1]["price"]):
        bos = "BEARISH_BOS"
    return bos, None


def build_market_structure_v2(symbol: str = "BTCUSDT", candles_override: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    reason_codes: list[str] = []
    if candles_override is not None:
        candles = candles_override
    else:
        candles, extract_reasons = _extract_candles()
        reason_codes.extend(extract_reasons)

    if not candles:
        reason_codes = sorted(
            set(reason_codes + ["SOURCE_FILE_MISSING", "INSUFFICIENT_CANDLES_FOR_STRUCTURE", "NO_SWINGS_FOUND"])
        )
        return {
            "timestamp_utc": _utc_now(),
            "block_id": BLOCK_ID,
            "symbol": symbol,
            "source": {"source_mode": "STATE_FILE"},
            "data_quality": "INVALID",
            "structure_status": "NOT_READY",
            "regime_hint": "UNKNOWN",
            "trend_direction": "NEUTRAL",
            "swing_highs": [],
            "swing_lows": [],
            "equal_highs": [],
            "equal_lows": [],
            "last_hh": None,
            "last_hl": None,
            "last_lh": None,
            "last_ll": None,
            "bos": None,
            "choch": None,
            "recent_sweep": None,
            "structure_bias": "NEUTRAL",
            "confidence": 0.0,
            "reason_codes": reason_codes,
            "feeds_next": FEEDS_NEXT,
        }

    if len(candles) < MIN_CANDLES:
        reason_codes.append("INSUFFICIENT_CANDLES_FOR_STRUCTURE")

    swing_highs, swing_lows = _detect_swings(candles)
    if not swing_highs and not swing_lows:
        reason_codes.append("NO_SWINGS_FOUND")

    eq_highs = _equal_levels(swing_highs)
    eq_lows = _equal_levels(swing_lows)
    points = _last_structure_points(swing_highs, swing_lows)
    structure_bias, trend_direction, regime_hint = _bias_and_direction(swing_highs, swing_lows)
    bos, choch = _bos_choch(candles, swing_highs, swing_lows)

    not_ready = "INSUFFICIENT_CANDLES_FOR_STRUCTURE" in reason_codes or "NO_SWINGS_FOUND" in reason_codes
    structure_status = "NOT_READY" if not_ready else "READY"
    if structure_status == "NOT_READY":
        structure_bias = "NEUTRAL"
        trend_direction = "NEUTRAL"
    data_quality = "OK" if structure_status == "READY" else "DEGRADED"
    if not candles:
        data_quality = "INVALID"
    confidence = 0.0 if structure_status != "READY" else round(min(1.0, (len(swing_highs) + len(swing_lows)) / 20.0), 3)
    if data_quality != "OK":
        reason_codes.append("DATA_QUALITY_INVALID")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {"source_mode": "STATE_FILE" if candles_override is None else "FAKE_SAMPLE"},
        "data_quality": data_quality,
        "structure_status": structure_status,
        "regime_hint": regime_hint,
        "trend_direction": trend_direction,
        "swing_highs": swing_highs[-20:],
        "swing_lows": swing_lows[-20:],
        "equal_highs": eq_highs,
        "equal_lows": eq_lows,
        "last_hh": points["last_hh"],
        "last_hl": points["last_hl"],
        "last_lh": points["last_lh"],
        "last_ll": points["last_ll"],
        "bos": bos,
        "choch": choch,
        "recent_sweep": None,
        "structure_bias": structure_bias,
        "confidence": confidence,
        "reason_codes": sorted(set(reason_codes)),
        "feeds_next": FEEDS_NEXT,
    }


def run_market_structure_v2_engine(symbol: str = "BTCUSDT", fake_sample: bool = False) -> dict[str, Any]:
    context = current_runtime_context(symbol)
    candles = _sample_candles(symbol) if fake_sample else None
    payload = build_market_structure_v2(symbol=symbol, candles_override=candles)
    payload["context_id"] = context.get("context_id")
    payload["loop_id"] = context.get("loop_id")
    write_json(OUTPUT_PATH, payload)
    return payload
