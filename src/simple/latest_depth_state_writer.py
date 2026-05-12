"""Depth state writer — atomic JSON overwrite for latest_depth_state.json"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_latest_depth_state(
    path: str | Path,
    latest_depth: dict[str, Any],
    event_count: int,
) -> bool:
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "timestamp_utc":  _utc_now(),
            "block_id":       "S12_DEPTH_STATE",
            "event_count":    event_count,
            "latest_depth":   latest_depth,
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used":        False,
                "live_order_sent":         False,
            },
        }

        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return True
    except Exception:
        return False
