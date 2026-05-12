"""Tests for raw_flow_event_logger — append-only invariant, malformed tolerance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.simple.raw_flow_event_logger import append_flow_event, append_flow_events


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_append_creates_file(tmp_path):
    p = tmp_path / "sub" / "events.jsonl"
    result = append_flow_event(p, {"symbol": "BTCUSDT", "qty": 0.1})
    assert result is True
    assert p.exists()


def test_append_only_never_overwrites(tmp_path):
    p = tmp_path / "events.jsonl"
    append_flow_event(p, {"n": 1})
    append_flow_event(p, {"n": 2})
    lines = _read_lines(p)
    assert len(lines) == 2
    assert lines[0]["n"] == 1
    assert lines[1]["n"] == 2


def test_timestamp_utc_injected(tmp_path):
    p = tmp_path / "events.jsonl"
    append_flow_event(p, {"x": 42})
    lines = _read_lines(p)
    assert "timestamp_utc" in lines[0]


def test_malformed_dict_input_tolerated(tmp_path):
    p = tmp_path / "events.jsonl"
    result = append_flow_event(p, "not-a-dict")
    assert result is True
    lines = _read_lines(p)
    assert lines[0]["malformed"] is True


def test_malformed_none_tolerated(tmp_path):
    p = tmp_path / "events.jsonl"
    result = append_flow_event(p, None)
    assert result is True


def test_batch_append(tmp_path):
    p = tmp_path / "events.jsonl"
    events = [{"n": i} for i in range(5)]
    count = append_flow_events(p, events)
    assert count == 5
    lines = _read_lines(p)
    assert len(lines) == 5


def test_dirs_created_automatically(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "events.jsonl"
    assert append_flow_event(deep, {"ok": True}) is True
    assert deep.exists()
