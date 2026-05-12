"""S12-B Latest Flow State Writer — NOVA SIMPLE ROBUST ENGINE v1.

DUZELTME: current_kline ve latest_closed_kline alanlari eklendi.
Atomically overwrites latest flow state JSON using a temp-file swap.
Never partially corrupts the file. safe_to_open_real_trade always false.
No private API. No orders.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_latest_flow_state(
    path: str | Path,
    latest_bucket: dict[str, Any] | None,
    quality_level: str,
    quality_score: float,
    event_counters: dict[str, int],
    current_kline: dict[str, Any] | None = None,
    latest_closed_kline: dict[str, Any] | None = None,
) -> bool:
    """Atomically write latest flow state JSON. Returns True on success."""
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "timestamp_utc": _utc_now(),
            "block_id": "S12_LATEST_FLOW_STATE",
            "heartbeat_timestamp": _utc_now(),
            "latest_bucket": latest_bucket,
            # Kline verileri — S3 Hybrid Candle DNA icin
            "current_kline_1m": current_kline,       # suanda birikmekte olan mum (kapanmadi)
            "latest_closed_kline_1m": latest_closed_kline,  # son kapanan mum (kesin OHLC)
            "quality_state": {
                "level": quality_level,
                "score": round(quality_score, 4),
            },
            "event_counters": dict(event_counters),
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        }

        dir_ = path.parent
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return True
    except Exception:
        return False
