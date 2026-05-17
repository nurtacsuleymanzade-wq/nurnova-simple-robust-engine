from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import append_epoch_jsonl, epoch_data_path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20].upper()}"


def lineage_record(
    *,
    record_type: str,
    event_id: str,
    parent_id: str | None = None,
    setup_id: str | None = None,
    signal_id: str | None = None,
    plan_id: str | None = None,
    decision_id: str | None = None,
    paper_trade_id: str | None = None,
    lifecycle_id: str | None = None,
    outcome_id: str | None = None,
    context_id: str | None = None,
    loop_id: str | None = None,
    reason_codes: list[str] | None = None,
    blocked_by: list[str] | None = None,
    feeds_next: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "record_type": record_type,
        "event_id": event_id,
        "output_id": event_id,
        "parent_id": parent_id,
        "setup_id": setup_id,
        "signal_id": signal_id,
        "plan_id": plan_id,
        "decision_id": decision_id,
        "paper_trade_id": paper_trade_id,
        "lifecycle_id": lifecycle_id,
        "outcome_id": outcome_id,
        "context_id": context_id,
        "loop_id": loop_id,
        "timestamp_utc": utc_now_iso(),
        "reason_codes": sorted(set(reason_codes or [])),
        "blocked_by": sorted(set(blocked_by or [])),
        "feeds_next": feeds_next or [],
    }
    if extra:
        payload.update(extra)
    return payload


def append_event(filename: str, record: dict[str, Any]) -> None:
    append_epoch_jsonl(filename, record)


def seen_ids(filename: str, id_field: str, max_lines: int = 5000) -> set[str]:
    out: set[str] = set()
    path = epoch_data_path(filename)
    for row in read_jsonl_tail_objects(path, max_lines=max_lines):
        val = str(row.get(id_field) or "")
        if val:
            out.add(val)
    return out
