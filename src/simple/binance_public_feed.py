"""S11.5-A Binance Public Feed — NOVA SIMPLE ROBUST ENGINE v1.

Fetches live 1M candle and book ticker via Binance public REST.
No API key. No authentication. No order capability.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

BINANCE_BASE = "https://api.binance.com"
_TIMEOUT_S = 10


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "nova-simple-robust-engine/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode())


def fetch_latest_closed_1m_candle(symbol: str) -> dict[str, Any] | None:
    """Return the last fully closed 1M candle for symbol, or None on failure.

    Binance klines index 0 with limit=2 is the last closed candle (index 1 is open).
    Response field order: [open_time, open, high, low, close, volume, close_time, ...]
    """
    url = f"{BINANCE_BASE}/api/v3/klines?symbol={symbol}&interval=1m&limit=2"
    try:
        data = _get(url)
        row = data[0]
        return {
            "open_time_ms": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_time_ms": int(row[6]),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError, ValueError, IndexError):
        return None


def fetch_book_ticker(symbol: str) -> dict[str, float] | None:
    """Return best bid/ask for symbol, or None on failure."""
    url = f"{BINANCE_BASE}/api/v3/ticker/bookTicker?symbol={symbol}"
    try:
        data = _get(url)
        return {
            "best_bid": float(data["bidPrice"]),
            "best_ask": float(data["askPrice"]),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError, ValueError):
        return None
