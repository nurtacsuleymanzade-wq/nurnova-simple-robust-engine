"""S1 Official Market Truth Engine — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S1_OFFICIAL_MARKET_TRUTH"
FEEDS_NEXT = {"next_blocks": ["S2_LIGHTWEIGHT_1S_EVIDENCE"]}

_FAKE_CANDLE: dict[str, Any] = {
    "open": 104700.0,
    "high": 105500.0,
    "low": 104200.0,
    "close": 105000.0,
    "volume": 12.543,
    "open_time_ms": 1746835200000,
    "close_time_ms": 1746835259999,
}

_FAKE_TICKER: dict[str, float] = {
    "best_bid": 104990.0,
    "best_ask": 105010.0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms_to_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_spread(bid: float | None, ask: float | None) -> dict[str, Any]:
    if bid is None or ask is None:
        return {
            "best_bid": None,
            "best_ask": None,
            "mid_price": None,
            "spread": None,
            "spread_pct": None,
        }
    mid = (bid + ask) / 2.0
    spread = ask - bid
    spread_pct = round((spread / mid * 100) if mid != 0 else 0.0, 6)
    return {
        "best_bid": round(bid, 8),
        "best_ask": round(ask, 8),
        "mid_price": round(mid, 8),
        "spread": round(spread, 8),
        "spread_pct": spread_pct,
    }


def _calc_consistency(close: float | None, mid: float | None) -> dict[str, Any]:
    if close is None or mid is None:
        return {
            "close_vs_mid_diff": None,
            "close_vs_mid_diff_pct": None,
            "consistency_label": "UNKNOWN",
        }
    diff = abs(close - mid)
    diff_pct = round((diff / mid * 100) if mid != 0 else 0.0, 6)
    if diff_pct <= 0.05:
        label = "CONSISTENT"
    elif diff_pct <= 0.5:
        label = "MINOR_MISMATCH"
    else:
        label = "MAJOR_MISMATCH"
    return {
        "close_vs_mid_diff": round(diff, 8),
        "close_vs_mid_diff_pct": diff_pct,
        "consistency_label": label,
    }


def _build_data_quality(source_mode: str, issues: list[str]) -> dict[str, Any]:
    if source_mode == "NO_DATA":
        return {"level": "INVALID", "score": 0.0, "issues": issues or ["NO_DATA"]}
    if not issues:
        return {"level": "OK", "score": 1.0, "issues": []}
    if len(issues) == 1:
        return {"level": "ACCEPTABLE", "score": 0.85, "issues": issues}
    return {"level": "USABLE_DEGRADED", "score": 0.65, "issues": issues}


def build_truth(
    symbol: str,
    candle: dict[str, Any] | None,
    ticker: dict[str, float] | None,
    source_mode: str,
) -> dict[str, Any]:
    issues: list[str] = []
    reason_codes: list[str] = [f"SOURCE_{source_mode}"]

    if candle is None:
        issues.append("MISSING_CANDLE")
        reason_codes.append("MISSING_CANDLE")
        official_candle: dict[str, Any] = {
            "open_time_utc": None,
            "close_time_utc": None,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": None,
            "is_official_binance_1m": False,
        }
        market_truth: dict[str, Any] = {
            "current_price": None,
            "official_close": None,
            "official_high": None,
            "official_low": None,
            "official_open": None,
            "official_volume": None,
            "official_candle_closed": False,
        }
    else:
        official_candle = {
            "open_time_utc": _ms_to_utc(candle["open_time_ms"]),
            "close_time_utc": _ms_to_utc(candle["close_time_ms"]),
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"],
            "is_official_binance_1m": True,
        }
        market_truth = {
            "current_price": candle["close"],
            "official_close": candle["close"],
            "official_high": candle["high"],
            "official_low": candle["low"],
            "official_open": candle["open"],
            "official_volume": candle["volume"],
            "official_candle_closed": True,
        }
        reason_codes.append("VALID_CANDLE")

    if ticker is None:
        issues.append("MISSING_TICKER")
        reason_codes.append("MISSING_TICKER")

    price_truth = _calc_spread(
        ticker.get("best_bid") if ticker else None,
        ticker.get("best_ask") if ticker else None,
    )

    consistency = _calc_consistency(
        market_truth.get("official_close"),
        price_truth.get("mid_price"),
    )
    if consistency["consistency_label"] == "MAJOR_MISMATCH":
        issues.append("MAJOR_PRICE_MISMATCH")
        reason_codes.append("MAJOR_PRICE_MISMATCH")

    data_quality = _build_data_quality(source_mode, issues)
    if data_quality["level"] == "INVALID":
        reason_codes.append("DATA_QUALITY_INVALID")
    elif data_quality["level"] == "ACCEPTABLE":
        reason_codes.append("DATA_QUALITY_ACCEPTABLE")
    elif data_quality["level"] in ("USABLE_DEGRADED", "WEAK_BUT_USABLE"):
        reason_codes.append("DATA_QUALITY_DEGRADED")
    else:
        reason_codes.append("DATA_QUALITY_OK")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "market_truth": market_truth,
        "official_candle": official_candle,
        "price_truth": price_truth,
        "consistency": consistency,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_truth(symbol, _FAKE_CANDLE, _FAKE_TICKER, "FAKE_SAMPLE")
