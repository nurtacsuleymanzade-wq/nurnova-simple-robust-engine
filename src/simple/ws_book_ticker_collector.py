"""S12 bookTicker websocket message parser — NOVA SIMPLE ROBUST ENGINE v1.

Parses raw Binance bookTicker websocket messages into normalized dicts.
No live websocket connection in this module — pure parsing only.
No private API. No authentication. No orders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_book_ticker(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single Binance bookTicker websocket message.

    Binance individual bookTicker stream fields:
        u: order book update id
        s: symbol
        b: best bid price
        B: best bid qty
        a: best ask price
        A: best ask qty

    Returns None if message is malformed or missing required fields.
    """
    try:
        best_bid = float(raw["b"])
        best_ask = float(raw["a"])
        spread = round(best_ask - best_bid, 8)
        mid_price = round((best_bid + best_ask) / 2.0, 8)
        return {
            "timestamp_utc": _utc_now(),
            "stream": "bookTicker",
            "symbol": str(raw.get("s", "")),
            "update_id": int(raw.get("u", 0)),
            "best_bid": best_bid,
            "best_bid_qty": float(raw.get("B", 0.0)),
            "best_ask": best_ask,
            "best_ask_qty": float(raw.get("A", 0.0)),
            "spread": spread,
            "mid_price": mid_price,
        }
    except (KeyError, TypeError, ValueError):
        return None


def parse_book_ticker_batch(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse a list of raw bookTicker messages, silently skipping malformed ones."""
    result = []
    for msg in messages:
        parsed = parse_book_ticker(msg)
        if parsed is not None:
            result.append(parsed)
    return result
