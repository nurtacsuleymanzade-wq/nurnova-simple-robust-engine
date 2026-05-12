"""Tests for S3 Hybrid Candle DNA Engine."""

from __future__ import annotations

import json
import pathlib

import pytest

from src.simple.hybrid_candle_dna_engine import (
    build_dna,
    run_fake_sample,
    _FAKE_CANDLE,
    FEEDS_NEXT,
)
import src.simple.run_s3_hybrid_candle_dna as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "official_candle", "micro_evidence", "shape", "candle_intent",
    "flow_vs_price", "coverage", "quality", "data_quality",
    "reason_codes", "feeds_next",
]

_REQUIRED_SHAPE = [
    "candle_direction", "body_size", "upper_wick_size", "lower_wick_size",
    "range_size", "body_pct", "upper_wick_pct", "lower_wick_pct",
    "shape_label", "dna_open", "dna_high", "dna_low", "dna_close",
    "body_ratio", "wick_upper_ratio", "wick_lower_ratio", "candle_type",
]

_REQUIRED_INTENT = ["intent_label", "intent_score", "intent_strength"]
_REQUIRED_FLOW = ["alignment", "explanation"]
_REQUIRED_COVERAGE = ["official_candle_available", "one_second_evidence_available", "coverage_pct"]
_REQUIRED_QUALITY = ["hybrid_quality_weight", "hybrid_quality_label", "usable_for_next_block"]


def test_fake_sample_contract_fields():
    dna = run_fake_sample("BTCUSDT")
    for field in _REQUIRED_TOP:
        assert field in dna, f"Missing top-level field: {field}"
    assert dna["block_id"] == "S3_HYBRID_CANDLE_DNA"
    assert dna["symbol"] == "BTCUSDT"
    for field in _REQUIRED_SHAPE:
        assert field in dna["shape"], f"shape missing: {field}"
    for field in _REQUIRED_INTENT:
        assert field in dna["candle_intent"], f"candle_intent missing: {field}"
    for field in _REQUIRED_FLOW:
        assert field in dna["flow_vs_price"], f"flow_vs_price missing: {field}"
    for field in _REQUIRED_COVERAGE:
        assert field in dna["coverage"], f"coverage missing: {field}"
    for field in _REQUIRED_QUALITY:
        assert field in dna["quality"], f"quality missing: {field}"


def test_reason_codes_not_empty():
    dna = run_fake_sample("BTCUSDT")
    assert dna["reason_codes"], "reason_codes must not be empty"
    assert isinstance(dna["reason_codes"], list)
    assert len(dna["reason_codes"]) >= 1


def test_feeds_next_includes_s4():
    dna = run_fake_sample("BTCUSDT")
    assert "S4_QUALITY_WEIGHT_ENGINE" in dna["feeds_next"]["next_blocks"]


def test_official_ohlc_preserved():
    dna = run_fake_sample("BTCUSDT")
    sh = dna["shape"]
    assert sh["dna_open"] == _FAKE_CANDLE["open"]
    assert sh["dna_high"] == _FAKE_CANDLE["high"]
    assert sh["dna_low"] == _FAKE_CANDLE["low"]
    assert sh["dna_close"] == _FAKE_CANDLE["close"]


def test_body_wick_ratios_sum_to_one():
    dna = run_fake_sample("BTCUSDT")
    sh = dna["shape"]
    total = sh["body_ratio"] + sh["wick_upper_ratio"] + sh["wick_lower_ratio"]
    assert abs(total - 1.0) <= 0.01, f"Ratio sum {total} not close to 1.0"


def test_candle_direction_bullish():
    dna = run_fake_sample("BTCUSDT")
    assert dna["shape"]["candle_direction"] == "BULLISH"


def test_missing_evidence_no_crash():
    dna = build_dna("BTCUSDT", _FAKE_CANDLE, None, "FAKE_SAMPLE", s1_dq_score=1.0)
    assert dna["flow_vs_price"]["alignment"] == "UNKNOWN"
    assert dna["candle_intent"]["intent_label"] == "UNKNOWN"
    assert dna["reason_codes"]


def test_runner_creates_all_output_files(monkeypatch):
    import shutil
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        dna = run_fake_sample("BTCUSDT")
        runner._write_outputs(dna)

        assert (tmp / "state" / "latest_hybrid_candle_dna.json").exists()
        assert (tmp / "state" / "s3_hybrid_candle_dna_state.json").exists()
        assert (tmp / "data" / "hybrid_candle_dna.jsonl").exists()
        assert (tmp / "reports" / "s3_hybrid_candle_dna_latest_report.md").exists()

        data = json.loads((tmp / "state" / "latest_hybrid_candle_dna.json").read_text())
        assert data["block_id"] == "S3_HYBRID_CANDLE_DNA"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
