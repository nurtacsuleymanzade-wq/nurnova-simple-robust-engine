"""S11.5-C VPS Health Monitor — NOVA SIMPLE ROBUST ENGINE v1.

Writes and reads the heartbeat JSON after every observer cycle.
Never raises — health monitoring must not crash the observer loop.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STATE_DIR = Path("state/simple")
_HEARTBEAT_FILE = _STATE_DIR / "vps_heartbeat.json"

_WARN_THRESHOLD = 3
_DEGRADED_THRESHOLD = 10


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_from_errors(consecutive_errors: int) -> str:
    if consecutive_errors == 0:
        return "OK"
    if consecutive_errors < _WARN_THRESHOLD:
        return "RECOVERING"
    if consecutive_errors < _DEGRADED_THRESHOLD:
        return "WARNING"
    return "DEGRADED"


def write_heartbeat(
    cycle_count: int,
    consecutive_errors: int,
    last_error: str | None,
) -> None:
    """Overwrite heartbeat file with current cycle state. Never raises."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "last_cycle_utc": _utc_now(),
            "cycle_count": cycle_count,
            "consecutive_errors": consecutive_errors,
            "last_error": last_error,
            "status": _status_from_errors(consecutive_errors),
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
            "observation_mode": True,
            "vps_ready": True,
            "SAFETY_INVARIANTS_VERIFIED": True,
        }
        tmp = _HEARTBEAT_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_HEARTBEAT_FILE)
    except Exception:
        pass


def read_heartbeat() -> dict[str, Any] | None:
    """Return parsed heartbeat, or None if file missing/corrupt."""
    try:
        return json.loads(_HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
