"""S12 aggTrade websocket message parser — NOVA SIMPLE ROBUST ENGINE v1.

Parses raw Binance aggTrade websocket messages into normalized dicts.
No live websocket connection in this module — pure parsing only.
No private API. No authentication. No orders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_agg_trade(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single Binance aggTrade websocket message.

    Binance aggTrade fields:
        e: event type ("aggTrade")
        E: event time ms
        s: symbol
        a: aggregate trade id
        p: price
        q: quantity
        T: trade time ms
        m: is_buyer_maker (True = taker is seller → SELL side aggression)

    Returns None if message is malformed or not an aggTrade event.
    """
    try:
        if raw.get("e") != "aggTrade":
            return None
        price = float(raw["p"])
        qty = float(raw["q"])
        is_buyer_maker: bool = bool(raw["m"])
        side = "SELL" if is_buyer_maker else "BUY"
        return {
            "timestamp_utc": _utc_now(),
            "stream": "aggTrade",
            "symbol": str(raw.get("s", "")),
            "agg_trade_id": int(raw["a"]),
            "price": price,
            "qty": qty,
            "side": side,
            "is_buyer_maker": is_buyer_maker,
            "trade_time_ms": int(raw["T"]),
            "event_time_ms": int(raw["E"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def parse_agg_trade_batch(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse a list of raw aggTrade messages, silently skipping malformed ones."""
    result = []
    for msg in messages:
        parsed = parse_agg_trade(msg)
        if parsed is not None:
            result.append(parsed)
    return result
