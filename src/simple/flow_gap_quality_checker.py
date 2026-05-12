"""S12 Flow Gap Quality Checker — NOVA SIMPLE ROBUST ENGINE v1.

Evaluates data quality of a 1-second flow bucket based on:
- trade count (empty bucket detection)
- websocket connection state
- stale timestamps
- malformed message count

Quality levels: OK, DEGRADED, INVALID
No private API. No orders. safe_to_open_real_trade always false.
"""

from __future__ import annotations

from typing import Any

_STALE_THRESHOLD_S = 5.0


def check_bucket_quality(
    trade_count: int,
    ws_agg_trade_connected: bool,
    ws_book_ticker_connected: bool,
    malformed_count: int = 0,
    age_seconds: float = 0.0,
    consecutive_empty_seconds: int = 0,
) -> dict[str, Any]:
    """Evaluate quality of one 1-second bucket and return a quality dict.

    Args:
        trade_count: number of aggTrade events in this bucket.
        ws_agg_trade_connected: whether aggTrade WS was connected during bucket.
        ws_book_ticker_connected: whether bookTicker WS was connected during bucket.
        malformed_count: number of messages that failed parsing.
        age_seconds: seconds since last aggTrade event (staleness).
        consecutive_empty_seconds: how many consecutive 1s buckets had zero trades.

    Returns a dict with keys: level, score, issues, reason_codes.
    """
    issues: list[str] = []
    score = 1.0

    if not ws_agg_trade_connected:
        issues.append("WS_AGG_TRADE_DISCONNECTED")
        score = min(score, 0.0)

    if not ws_book_ticker_connected:
        issues.append("WS_BOOK_TICKER_DISCONNECTED")
        score = min(score, 0.5)

    if malformed_count > 0:
        issues.append("MALFORMED_MESSAGES")
        score = min(score, 0.7)

    if age_seconds >= _STALE_THRESHOLD_S:
        issues.append("STALE_TIMESTAMP")
        score = min(score, 0.0)

    if trade_count == 0 and ws_agg_trade_connected:
        issues.append("ZERO_TRADES_BUCKET")
        score = min(score, 0.6)

    if consecutive_empty_seconds >= 5:
        issues.append("SUSTAINED_GAP")
        score = min(score, 0.0)

    if score == 0.0:
        level = "INVALID"
    elif score < 1.0:
        level = "DEGRADED"
    else:
        level = "OK"

    reason_codes = [f"DQ_{issue}" for issue in issues] if issues else ["DQ_OK"]

    return {
        "level": level,
        "score": round(score, 4),
        "issues": issues,
        "reason_codes": reason_codes,
    }
