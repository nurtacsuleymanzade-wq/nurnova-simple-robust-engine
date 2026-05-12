"""Tests for S2 Lightweight 1S Evidence Engine."""

from __future__ import annotations

import json
import pathlib

import pytest

from src.simple.lightweight_1s_evidence_engine import (
    build_evidence,
    run_fake_sample,
    FEEDS_NEXT,
)
import src.simple.run_s2_1s_evidence as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "market_context", "trade_flow", "evidence", "quality",
    "data_quality", "reason_codes", "feeds_next",
]

_REQUIRED_TRADE_FLOW = [
    "buy_volume", "sell_volume", "total_volume", "delta", "delta_ratio", "trade_count",
]

_REQUIRED_EVIDENCE = [
    "evidence_score", "evidence_label", "evidence_strength", "micro_winner",
    "tick_count", "buy_pressure", "sell_pressure", "missing_seconds", "confidence_adjusted",
]

_REQUIRED_QUALITY = [
    "sample_coverage_pct", "sample_quality_label", "usable_for_next_block",
]


def test_fake_sample_contract_fields():
    ev = run_fake_sample("BTCUSDT")
    for field in _REQUIRED_TOP:
        assert field in ev, f"Missing top-level field: {field}"
    assert ev["block_id"] == "S2_LIGHTWEIGHT_1S_EVIDENCE"
    assert ev["symbol"] == "BTCUSDT"
    for field in _REQUIRED_TRADE_FLOW:
        assert field in ev["trade_flow"], f"trade_flow missing: {field}"
    for field in _REQUIRED_EVIDENCE:
        assert field in ev["evidence"], f"evidence missing: {field}"
    for field in _REQUIRED_QUALITY:
        assert field in ev["quality"], f"quality missing: {field}"


def test_reason_codes_not_empty():
    ev = run_fake_sample("BTCUSDT")
    assert ev["reason_codes"], "reason_codes must not be empty"
    assert isinstance(ev["reason_codes"], list)
    assert len(ev["reason_codes"]) >= 1


def test_feeds_next_includes_s3():
    ev = run_fake_sample("BTCUSDT")
    assert "S3_HYBRID_CANDLE_DNA" in ev["feeds_next"]["next_blocks"]


def test_buy_sell_pressure_sum_constraint():
    ev = run_fake_sample("BTCUSDT")
    total = ev["evidence"]["buy_pressure"] + ev["evidence"]["sell_pressure"]
    assert total <= 1.0 + 1e-6, f"buy+sell pressure {total} exceeds 1.0"


def test_tick_count_non_negative():
    ev = run_fake_sample("BTCUSDT")
    assert ev["evidence"]["tick_count"] >= 0


def test_missing_seconds_sets_confidence_adjusted():
    ticks = [{"price": 104700.0, "side": "BUY", "qty": 0.1}]
    ev = build_evidence("BTCUSDT", ticks, missing_seconds=5, source_mode="FAKE_SAMPLE")
    assert ev["evidence"]["confidence_adjusted"] is True


def test_zero_ticks_no_crash():
    ev = build_evidence("BTCUSDT", [], missing_seconds=60, source_mode="NO_DATA")
    assert ev["quality"]["sample_quality_label"] == "EMPTY"
    assert ev["evidence"]["evidence_label"] == "UNKNOWN"
    assert ev["reason_codes"]


def test_runner_creates_all_output_files(monkeypatch):
    import shutil
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        evidence = run_fake_sample("BTCUSDT")
        runner._write_outputs(evidence)

        assert (tmp / "state" / "latest_1s_evidence.json").exists()
        assert (tmp / "state" / "s2_1s_evidence_state.json").exists()
        assert (tmp / "data" / "1s_evidence.jsonl").exists()
        assert (tmp / "reports" / "s2_1s_evidence_latest_report.md").exists()

        data = json.loads((tmp / "state" / "latest_1s_evidence.json").read_text())
        assert data["block_id"] == "S2_LIGHTWEIGHT_1S_EVIDENCE"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
