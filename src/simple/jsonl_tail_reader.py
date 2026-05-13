from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def read_jsonl_tail(path: str | Path, max_lines: int = 2000) -> list[str]:
    file_path = Path(path)
    if max_lines <= 0 or not file_path.exists():
        return []
    try:
        with file_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            chunk_size = 8192
            buffer = b""
            newline_count = 0
            while position > 0 and newline_count <= max_lines:
                read_size = min(chunk_size, position)
                position -= read_size
                handle.seek(position)
                buffer = handle.read(read_size) + buffer
                newline_count = buffer.count(b"\n")
        return [line for line in buffer.decode("utf-8", errors="ignore").splitlines() if line.strip()][-max_lines:]
    except Exception:
        return []


def read_jsonl_tail_objects(path: str | Path, max_lines: int = 2000) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for line in read_jsonl_tail(path, max_lines=max_lines):
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def safe_read_json(path: str | Path, default: Any = None, max_bytes: int = 2_000_000) -> tuple[Any, str | None]:
    file_path = Path(path)
    if not file_path.exists():
        return default, "FILE_MISSING"
    try:
        size = file_path.stat().st_size
    except Exception:
        return default, "FILE_STAT_FAILED"
    if size > max_bytes:
        return default, "FILE_TOO_LARGE"
    try:
        return json.loads(file_path.read_text(encoding="utf-8")), None
    except Exception:
        return default, "JSON_CORRUPT"


def safe_write_json_atomic(path: str | Path, obj: Any) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(file_path)


def append_jsonl_atomic(path: str | Path, obj: Any) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    existing = b""
    if file_path.exists():
        try:
            existing = file_path.read_bytes()
        except Exception:
            existing = b""
    temp_path.write_bytes(existing + line.encode("utf-8"))
    temp_path.replace(file_path)
