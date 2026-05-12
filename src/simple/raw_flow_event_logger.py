"""S12-B Raw Flow Event Logger — NOVA SIMPLE ROBUST ENGINE v1.

Append-only JSONL logger for raw flow events.
Never overwrites. Creates dirs automatically. Tolerates malformed input.
No private API. No orders. safe_to_open_real_trade always false.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_flow_event(path: str | Path, event: Any) -> bool:
    """Append one flow event as a JSONL line. Returns True on success."""
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not isinstance(event, dict):
            event = {"raw": str(event), "malformed": True}

        event = dict(event)
        event["timestamp_utc"] = _utc_now()

        line = json.dumps(event, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        return True
    except Exception:
        return False


def append_flow_events(path: str | Path, events: list[Any]) -> int:
    """Append multiple events. Returns count of successfully written events."""
    count = 0
    for event in events:
        if append_flow_event(path, event):
            count += 1
    return count
