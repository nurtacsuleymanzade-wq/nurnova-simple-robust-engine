"""S12 Flow Bucket Builder — NOVA SIMPLE ROBUST ENGINE v1.

Aggregates parsed aggTrade events and a bookTicker snapshot into
a 1-second flow bucket. Pure computation — no I/O, no websocket.

Output bucket fields match S12 JSONL contract.
No private API. No orders. safe_to_open_real_trade always false.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.simple.flow_gap_quality_checker import check_bucket_quality

BLOCK_ID = "S12_FLOW_BUCKET"
FEEDS_NEXT = {"next_blocks": ["S13_1S_FLOW_EVIDENCE"]}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _aggression_label(delta_ratio: float) -> str:
    if delta_ratio >= 0.5:
        return "STRONG_BUY"
    if delta_ratio >= 0.1:
        return "MILD_BUY"
    if delta_ratio <= -0.5:
        return "STRONG_SELL"
    if delta_ratio <= -0.1:
        return "MILD_SELL"
    return "NEUTRAL"


def build_bucket(
    symbol: str,
    bucket_second: str,
    trades: list[dict[str, Any]],
    last_book_ticker: dict[str, Any] | None,
    ws_agg_trade_connected: bool = True,
    ws_book_ticker_connected: bool = True,
    malformed_count: int = 0,
    age_seconds: float = 0.0,
    consecutive_empty_seconds: int = 0,
) -> dict[str, Any]:
    """Build a 1-second flow bucket from parsed aggTrade events + book ticker.

    Args:
        symbol: trading pair e.g. "BTCUSDT".
        bucket_second: ISO second string e.g. "2026-05-11T12:00:01".
        trades: list of parsed aggTrade dicts from ws_agg_trade_collector.
        last_book_ticker: most recent parsed bookTicker dict, or None.
        ws_agg_trade_connected: WS connection state during this bucket.
        ws_book_ticker_connected: WS connection state during this bucket.
        malformed_count: raw messages that failed parsing this second.
        age_seconds: seconds since last aggTrade (staleness indicator).
        consecutive_empty_seconds: count of prior empty 1s buckets.

    Returns a fully populated bucket dict matching the S12 JSONL contract.
    """
    buy_volume = 0.0
    sell_volume = 0.0
    buy_count = 0
    sell_count = 0
    last_price: float | None = None
    vwap_numerator = 0.0

    for t in trades:
        qty = float(t.get("qty", 0.0))
        price = float(t.get("price", 0.0))
        side = t.get("side", "")
        if side == "BUY":
            buy_volume += qty
            buy_count += 1
        elif side == "SELL":
            sell_volume += qty
            sell_count += 1
        vwap_numerator += price * qty
        last_price = price

    total_volume = buy_volume + sell_volume
    delta = buy_volume - sell_volume

    if total_volume > 0.0:
        delta_ratio = round(delta / total_volume, 6)
        vwap = round(vwap_numerator / total_volume, 8)
    else:
        delta_ratio = 0.0
        vwap = None

    trade_count = len(trades)
    aggression = _aggression_label(delta_ratio)

    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    mid_price: float | None = None

    if last_book_ticker is not None:
        best_bid = last_book_ticker.get("best_bid")
        best_ask = last_book_ticker.get("best_ask")
        spread = last_book_ticker.get("spread")
        mid_price = last_book_ticker.get("mid_price")

    quality = check_bucket_quality(
        trade_count=trade_count,
        ws_agg_trade_connected=ws_agg_trade_connected,
        ws_book_ticker_connected=ws_book_ticker_connected,
        malformed_count=malformed_count,
        age_seconds=age_seconds,
        consecutive_empty_seconds=consecutive_empty_seconds,
    )

    gap_detected = any(
        issue in quality["issues"]
        for issue in ("WS_AGG_TRADE_DISCONNECTED", "STALE_TIMESTAMP", "SUSTAINED_GAP")
    )

    reason_codes = [
        "SOURCE_LIVE_WS_REAL",
        f"SYMBOL_{symbol}",
        f"DQ_{quality['level']}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]
    if gap_detected:
        reason_codes.append("GAP_DETECTED")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "bucket_second": bucket_second,
        "trade_count": trade_count,
        "buy_volume": round(buy_volume, 8),
        "sell_volume": round(sell_volume, 8),
        "total_volume": round(total_volume, 8),
        "delta": round(delta, 8),
        "delta_ratio": delta_ratio,
        "buy_trade_count": buy_count,
        "sell_trade_count": sell_count,
        "vwap": vwap,
        "last_price": last_price,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "mid_price": mid_price,
        "aggression_label": aggression,
        "gap_detected": gap_detected,
        "malformed_count": malformed_count,
        "data_quality": {
            "level": quality["level"],
            "score": quality["score"],
            "issues": quality["issues"],
        },
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }
