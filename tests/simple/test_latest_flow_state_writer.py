"""Tests for latest_flow_state_writer — atomic overwrite, safety flags."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.simple.latest_flow_state_writer import write_latest_flow_state


def _read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, bucket=None, level="OK", score=1.0, counters=None):
    return write_latest_flow_state(
        path=path,
        latest_bucket=bucket,
        quality_level=level,
        quality_score=score,
        event_counters=counters or {"buckets_built": 1},
    )


def test_creates_state_file(tmp_path):
    p = tmp_path / "state" / "latest.json"
    assert _write(p) is True
    assert p.exists()


def test_overwrite_is_atomic(tmp_path):
    p = tmp_path / "latest.json"
    _write(p, level="OK", score=1.0, counters={"buckets_built": 1})
    _write(p, level="DEGRADED", score=0.6, counters={"buckets_built": 2})
    state = _read_state(p)
    assert state["quality_state"]["level"] == "DEGRADED"
    assert state["event_counters"]["buckets_built"] == 2


def test_safe_to_open_real_trade_always_false(tmp_path):
    p = tmp_path / "latest.json"
    _write(p)
    state = _read_state(p)
    assert state["execution_safety"]["safe_to_open_real_trade"] is False


def test_private_api_used_false(tmp_path):
    p = tmp_path / "latest.json"
    _write(p)
    state = _read_state(p)
    assert state["execution_safety"]["private_api_used"] is False


def test_heartbeat_present(tmp_path):
    p = tmp_path / "latest.json"
    _write(p)
    state = _read_state(p)
    assert "heartbeat_timestamp" in state


def test_quality_state_written(tmp_path):
    p = tmp_path / "latest.json"
    _write(p, level="INVALID", score=0.0, counters={"buckets_built": 3})
    state = _read_state(p)
    assert state["quality_state"]["level"] == "INVALID"
    assert state["quality_state"]["score"] == 0.0


def test_latest_bucket_persisted(tmp_path):
    p = tmp_path / "latest.json"
    bucket = {"symbol": "BTCUSDT", "trade_count": 7}
    _write(p, bucket=bucket)
    state = _read_state(p)
    assert state["latest_bucket"]["trade_count"] == 7
