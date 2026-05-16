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


def _extract_candles() -> tuple[list[dict[str, Any]], list[str]]:
    reason_codes: list[str] = []
    market_truth = _load_json(LATEST_MARKET_TRUTH_PATH)
    if market_truth is None and not LATEST_MARKET_TRUTH_PATH.exists():
        reason_codes.append("SOURCE_FILE_MISSING")
    if market_truth:
        raw = market_truth.get("candles") or market_truth.get("ohlc_candles") or []
        candles = [c for c in raw if isinstance(c, dict) and all(k in c for k in ("high", "low", "close"))]
        if candles:
            return candles, reason_codes

    hybrid = _load_json(LATEST_HYBRID_DNA_PATH)
    if hybrid:
        raw = hybrid.get("candles") or hybrid.get("dna_candles") or []
        candles = [c for c in raw if isinstance(c, dict) and all(k in c for k in ("high", "low", "close"))]
        if candles:
            return candles, reason_codes
    return [], reason_codes


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
    candles = candles_override if candles_override is not None else _extract_candles()[0]
    if candles_override is None:
        _, extract_reasons = _extract_candles()
        reason_codes.extend(extract_reasons)

    if not candles:
        reason_codes = sorted(set(reason_codes + ["SOURCE_FILE_MISSING", "INSUFFICIENT_CANDLES", "NO_SWINGS_FOUND"]))
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
        reason_codes.append("INSUFFICIENT_CANDLES")

    swing_highs, swing_lows = _detect_swings(candles)
    if not swing_highs and not swing_lows:
        reason_codes.append("NO_SWINGS_FOUND")

    eq_highs = _equal_levels(swing_highs)
    eq_lows = _equal_levels(swing_lows)
    points = _last_structure_points(swing_highs, swing_lows)
    structure_bias, trend_direction, regime_hint = _bias_and_direction(swing_highs, swing_lows)
    bos, choch = _bos_choch(candles, swing_highs, swing_lows)

    not_ready = "INSUFFICIENT_CANDLES" in reason_codes or "NO_SWINGS_FOUND" in reason_codes
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
