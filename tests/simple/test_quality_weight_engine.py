"""Tests for S4 Quality Weight Engine."""

from __future__ import annotations

import json
import pathlib

import pytest

from src.simple.quality_weight_engine import (
    build_quality_weight,
    run_fake_sample,
    _FAKE_S1,
    _FAKE_S2,
    _FAKE_S3,
    FEEDS_NEXT,
)
import src.simple.run_s4_quality_weight as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "input_status", "quality_components", "quality_weight",
    "decision_policy", "repair_policy", "edge_policy",
    "data_quality", "reason_codes", "feeds_next",
]

_REQUIRED_INPUT_STATUS = [
    "market_truth_available", "one_second_evidence_available",
    "hybrid_candle_available", "missing_inputs",
]

_REQUIRED_COMPONENTS = [
    "market_truth_score", "evidence_score", "hybrid_candle_score",
    "coverage_score", "consistency_score", "final_quality_score",
]

_REQUIRED_QW = ["quality_weight", "quality_label", "confidence_policy"]
_REQUIRED_DP = ["decision_quality_mode", "max_allowed_decision"]
_REQUIRED_RP = ["repair_required", "repair_action"]
_REQUIRED_EP = ["edge_eligible_if_trade_opens", "edge_reason"]


def test_fake_sample_contract_fields():
    qw = run_fake_sample("BTCUSDT")
    for field in _REQUIRED_TOP:
        assert field in qw, f"Missing top-level field: {field}"
    assert qw["block_id"] == "S4_QUALITY_WEIGHT_ENGINE"
    assert qw["symbol"] == "BTCUSDT"
    for field in _REQUIRED_INPUT_STATUS:
        assert field in qw["input_status"], f"input_status missing: {field}"
    for field in _REQUIRED_COMPONENTS:
        assert field in qw["quality_components"], f"quality_components missing: {field}"
    for field in _REQUIRED_QW:
        assert field in qw["quality_weight"], f"quality_weight missing: {field}"
    for field in _REQUIRED_DP:
        assert field in qw["decision_policy"], f"decision_policy missing: {field}"
    for field in _REQUIRED_RP:
        assert field in qw["repair_policy"], f"repair_policy missing: {field}"
    for field in _REQUIRED_EP:
        assert field in qw["edge_policy"], f"edge_policy missing: {field}"


def test_reason_codes_not_empty():
    qw = run_fake_sample("BTCUSDT")
    assert qw["reason_codes"], "reason_codes must not be empty"
    assert isinstance(qw["reason_codes"], list)
    assert len(qw["reason_codes"]) >= 1


def test_feeds_next_includes_s5():
    qw = run_fake_sample("BTCUSDT")
    assert "S5_LIQUIDITY_STRUCTURE_CONTEXT" in qw["feeds_next"]["next_blocks"]


def test_quality_weight_in_range():
    qw = run_fake_sample("BTCUSDT")
    w = qw["quality_weight"]["quality_weight"]
    assert 0.0 <= w <= 1.0, f"quality_weight {w} out of range"


def test_pipeline_never_blocks():
    qw = build_quality_weight("BTCUSDT", None, None, None, "NO_DATA")
    assert qw["feeds_next"]["next_blocks"], "feeds_next must always be set"
    assert len(qw["feeds_next"]["next_blocks"]) >= 1


def test_missing_s2_reduces_not_blocks():
    qw = build_quality_weight("BTCUSDT", _FAKE_S1, None, _FAKE_S3, "TEST")
    assert qw["feeds_next"]["next_blocks"]
    assert qw["repair_policy"]["repair_required"] is False
    assert qw["quality_weight"]["quality_weight"] < run_fake_sample("BTCUSDT")["quality_weight"]["quality_weight"]


def test_missing_s1_triggers_repair():
    qw = build_quality_weight("BTCUSDT", None, _FAKE_S2, _FAKE_S3, "TEST")
    assert qw["repair_policy"]["repair_required"] is True
    assert qw["repair_policy"]["repair_action"] == "REBUILD_S1"


def test_runner_creates_all_output_files(monkeypatch):
    import shutil
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        qw = run_fake_sample("BTCUSDT")
        runner._write_outputs(qw)

        assert (tmp / "state" / "latest_quality_weight.json").exists()
        assert (tmp / "state" / "s4_quality_weight_state.json").exists()
        assert (tmp / "data" / "quality_weight.jsonl").exists()
        assert (tmp / "reports" / "s4_quality_weight_latest_report.md").exists()

        data = json.loads((tmp / "state" / "latest_quality_weight.json").read_text())
        assert data["block_id"] == "S4_QUALITY_WEIGHT_ENGINE"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
