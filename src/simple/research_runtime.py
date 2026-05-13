from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
RUNTIME_CONTEXT_PATH = STATE_DIR / "latest_runtime_context.json"

LINEAGE_FIELDS = (
    "context_id",
    "loop_id",
    "setup_family",
    "dominant_setup_family",
    "model_id",
    "model_family",
    "model_instance_id",
    "paper_trade_id",
    "activation_score",
    "activation_band",
    "direction_resolution",
    "market_regime",
    "candle_category",
    "structure_label",
    "liquidity_event",
    "source_state_refs",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def history_tail(path: Path, max_lines: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            end = handle.tell()
            chunk_size = 4096
            buffer = b""
            line_count = 0
            position = end
            while position > 0 and line_count <= max_lines:
                read_size = min(chunk_size, position)
                position -= read_size
                handle.seek(position)
                buffer = handle.read(read_size) + buffer
                line_count = buffer.count(b"\n")
            lines = buffer.decode("utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            result.append(payload)
    return result


def initialize_runtime_context(symbol: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    loop_started_at_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    previous = load_json(RUNTIME_CONTEXT_PATH) or {}
    previous_loop_id = int(previous.get("loop_id") or 0)
    loop_id = previous_loop_id + 1
    raw = f"{symbol}|{loop_id}|{loop_started_at_utc}"
    context_id = f"CTX_{symbol}_{loop_id}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10].upper()}"
    payload = {
        "timestamp_utc": loop_started_at_utc,
        "block_id": "RUNTIME_CONTEXT",
        "symbol": symbol,
        "context_id": context_id,
        "loop_id": loop_id,
        "loop_started_at_utc": loop_started_at_utc,
        "runtime_pid": os.getpid(),
        "canonical_runtime": "run_loop.py",
    }
    write_json(RUNTIME_CONTEXT_PATH, payload)
    return payload


def current_runtime_context(symbol: str = "BTCUSDT") -> dict[str, Any]:
    return load_json(RUNTIME_CONTEXT_PATH) or initialize_runtime_context(symbol)


def stamp_payload(payload: dict[str, Any], block_id: str, symbol: str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = context or current_runtime_context(symbol or str(payload.get("symbol") or "BTCUSDT"))
    stamped = dict(payload)
    stamped["timestamp_utc"] = stamped.get("timestamp_utc") or utc_now()
    stamped["block_id"] = block_id
    stamped["symbol"] = str(stamped.get("symbol") or symbol or ctx.get("symbol") or "BTCUSDT")
    stamped["context_id"] = stamped.get("context_id") or ctx.get("context_id")
    stamped["loop_id"] = stamped.get("loop_id") or ctx.get("loop_id")
    return stamped


def source_state_refs_from_paths(paths: dict[str, Path]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for name, path in paths.items():
        payload = load_json(path) or {}
        refs[name] = {
            "path": str(path),
            "timestamp_utc": payload.get("timestamp_utc"),
            "block_id": payload.get("block_id"),
            "context_id": payload.get("context_id"),
            "loop_id": payload.get("loop_id"),
        }
    return refs


def compact_lineage(*records: dict[str, Any] | None) -> dict[str, Any]:
    lineage: dict[str, Any] = {}
    for field in LINEAGE_FIELDS:
        for record in records:
            if not isinstance(record, dict):
                continue
            value = record.get(field)
            if value not in (None, "", [], {}):
                lineage[field] = value
                break
    return lineage
