from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .lineage_registry import LINEAGE_REGISTRY, NODE_TYPES


VALID_DATA_QUALITY = {"OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN"}


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_payload_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_lineage_id(
    *,
    symbol: str,
    node_type: str,
    timestamp_utc: str,
    source_block: str,
    source_file: str,
    source_record_id: str,
    parent_lineage_ids: list[str],
    hash_payload: str,
) -> str:
    base = {
        "symbol": symbol or "UNKNOWN",
        "node_type": node_type,
        "timestamp_utc": timestamp_utc,
        "source_block": source_block,
        "source_file": source_file,
        "source_record_id": source_record_id or "",
        "parent_lineage_ids": sorted(parent_lineage_ids or []),
        "hash_payload": hash_payload,
    }
    digest = hashlib.sha256(_canonical_json(base).encode("utf-8")).hexdigest()[:24].upper()
    return f"LIN_{digest}"


def _is_iso_utc(value: str) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def _to_iso_utc(value: Any) -> str:
    if isinstance(value, str) and _is_iso_utc(value):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "1970-01-01T00:00:00Z"


def infer_namespace(source_file: str, source_record: dict[str, Any] | None = None) -> str:
    lower = str(source_file or "").lower()
    if "replay" in lower or "true_outcome" in lower:
        return "replay"
    if "data/live" in lower or "live_" in lower:
        return "live"
    if source_record and str(source_record.get("source_mode") or "").upper() == "REPLAY":
        return "replay"
    return "core"


def build_lineage_node(
    *,
    node_type: str,
    source_block: str,
    source_file: str,
    source_record: dict[str, Any],
    parent_lineage_ids: list[str] | None = None,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    if node_type not in NODE_TYPES:
        raise ValueError(f"unknown node_type={node_type}")

    parent_ids = [str(x) for x in (parent_lineage_ids or []) if str(x)]
    symbol = str(source_record.get("symbol") or "BTCUSDT")
    timestamp_utc = _to_iso_utc(source_record.get("timestamp_utc"))
    context_id = source_record.get("context_id")
    data_quality = str(source_record.get("data_quality") or "UNKNOWN")
    if data_quality not in VALID_DATA_QUALITY:
        data_quality = "UNKNOWN"

    payload_hash = build_payload_hash(source_record)
    record_id = str(source_record_id or source_record.get("event_id") or source_record.get("id") or source_record.get("paper_trade_id") or "")
    if not record_id:
        record_id = f"{timestamp_utc}|{source_file}|{node_type}|{symbol}|{payload_hash[:16]}"

    lineage_id = build_lineage_id(
        symbol=symbol,
        node_type=node_type,
        timestamp_utc=timestamp_utc,
        source_block=source_block,
        source_file=source_file,
        source_record_id=record_id,
        parent_lineage_ids=parent_ids,
        hash_payload=payload_hash,
    )

    reason_codes = list(source_record.get("reason_codes") or [])
    if node_type != "raw_event" and not parent_ids:
        reason_codes.append("INVALID_LINEAGE_PARENT_MISSING")
        data_quality = "INVALID"

    required = set(LINEAGE_REGISTRY[node_type]["required_fields"])
    missing_required = []
    for key in required:
        if key in {"child_lineage_ids", "parent_lineage_ids", "reason_codes", "feeds_next"}:
            continue
        if key == "context_id":
            continue
        # Presence check for source fields that are created below.
    if not source_block:
        missing_required.append("source_block")
    if not timestamp_utc:
        missing_required.append("timestamp_utc")
    if missing_required:
        reason_codes.extend([f"MISSING_{item.upper()}" for item in missing_required])
        data_quality = "INVALID"

    node = {
        "lineage_id": lineage_id,
        "node_type": node_type,
        "source_block": source_block or "UNKNOWN_BLOCK",
        "timestamp_utc": timestamp_utc,
        "symbol": symbol,
        "parent_lineage_ids": parent_ids,
        "child_lineage_ids": [],
        "context_id": context_id,
        "data_quality": data_quality,
        "reason_codes": sorted(set(reason_codes)),
        "feeds_next": list(source_record.get("feeds_next") or []),
        "source_file": source_file,
        "source_record_id": record_id,
        "hash_payload": payload_hash,
        "lineage_status": "INVALID_LINEAGE" if "INVALID_LINEAGE_PARENT_MISSING" in reason_codes else "VALID",
        "lineage_namespace": infer_namespace(source_file, source_record),
        "outcome_status": source_record.get("outcome_status"),
    }
    return node
