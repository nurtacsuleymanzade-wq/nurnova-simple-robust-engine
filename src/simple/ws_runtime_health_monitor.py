"""S12-C WS Runtime Health Monitor — NOVA SIMPLE ROBUST ENGINE v1.

Tracks websocket connection health: connected state, reconnect count,
stale detection, event counters, and runtime status transitions.
Pure state — no I/O, no async. safe_to_open_real_trade always false.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_STALE_THRESHOLD_S = 10.0


class WsRuntimeHealthMonitor:
    """Tracks live websocket runtime health state."""

    def __init__(self, stale_threshold_seconds: float = _STALE_THRESHOLD_S) -> None:
        self._connected = False
        self._reconnect_count = 0
        self._events_received = 0
        self._malformed_events = 0
        self._last_event_time: float | None = None
        self._stale_threshold = stale_threshold_seconds
        self._status = "DISCONNECTED"

    def on_connected(self) -> None:
        self._connected = True
        self._last_event_time = time.monotonic()
        self._status = "OK"

    def on_disconnected(self) -> None:
        self._connected = False
        self._reconnect_count += 1
        self._status = "DISCONNECTED"

    def on_reconnecting(self) -> None:
        self._status = "RECOVERING"

    def on_message(self) -> None:
        self._events_received += 1
        self._last_event_time = time.monotonic()
        if self._connected and self._status not in ("DEGRADED",):
            self._status = "OK"

    def on_malformed(self) -> None:
        self._malformed_events += 1
        if self._status == "OK":
            self._status = "DEGRADED"

    def check_stale(self, now: float | None = None) -> bool:
        """Check staleness. Returns True if stale. Accepts override for testing."""
        if self._last_event_time is None:
            return False
        t = now if now is not None else time.monotonic()
        stale = (t - self._last_event_time) > self._stale_threshold
        if stale and self._connected:
            self._status = "DEGRADED"
        return stale

    def get_stale_seconds(self, now: float | None = None) -> float:
        if self._last_event_time is None:
            return 0.0
        t = now if now is not None else time.monotonic()
        return max(0.0, t - self._last_event_time)

    def get_health(self, now: float | None = None) -> dict[str, Any]:
        return {
            "timestamp_utc": _utc_now(),
            "block_id": "S12_WS_RUNTIME_HEALTH",
            "websocket_connected": self._connected,
            "reconnect_count": self._reconnect_count,
            "stale_seconds": round(self.get_stale_seconds(now), 2),
            "events_received": self._events_received,
            "malformed_events": self._malformed_events,
            "runtime_status": self._status,
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        }
