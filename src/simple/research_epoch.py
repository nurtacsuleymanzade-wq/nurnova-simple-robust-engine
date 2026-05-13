from __future__ import annotations

from pathlib import Path
from typing import Any

from src.simple.jsonl_tail_reader import (
    append_jsonl_atomic,
    read_jsonl_tail_objects,
    safe_read_json,
    safe_write_json_atomic,
)

ACTIVE_EPOCH_ID = "EPOCH_V2_TIMEFRAME_NATIVE"

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "simple"
STATE_DIR = ROOT / "state" / "simple"
EPOCH_DATA_DIR = DATA_DIR / "epoch_v2"
EPOCH_STATE_DIR = STATE_DIR / "epoch_v2"

LEGACY_DATA_DIR = DATA_DIR
LEGACY_STATE_DIR = STATE_DIR


def get_epoch_id() -> str:
    return ACTIVE_EPOCH_ID


def epoch_data_path(filename: str) -> Path:
    path = EPOCH_DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def epoch_state_path(filename: str) -> Path:
    path = EPOCH_STATE_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_epoch_json(filename: str, payload: dict[str, Any]) -> Path:
    path = epoch_state_path(filename)
    safe_write_json_atomic(path, payload)
    return path


def append_epoch_jsonl(filename: str, payload: dict[str, Any]) -> Path:
    path = epoch_data_path(filename)
    append_jsonl_atomic(path, payload)
    return path


def read_epoch_json(filename: str, default: Any = None, max_bytes: int = 2_000_000) -> Any:
    payload, _reason = safe_read_json(epoch_state_path(filename), default=default, max_bytes=max_bytes)
    return payload


def tail_epoch_jsonl(filename: str, limit: int = 5000) -> list[dict[str, Any]]:
    return read_jsonl_tail_objects(epoch_data_path(filename), max_lines=limit)


def ensure_epoch_dirs() -> None:
    EPOCH_DATA_DIR.mkdir(parents=True, exist_ok=True)
    EPOCH_STATE_DIR.mkdir(parents=True, exist_ok=True)
