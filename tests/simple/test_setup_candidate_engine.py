"""Tests for S6 Scenario + Setup Candidate Engine."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.setup_candidate_engine import (
    build_setup_candidate,
    run_fake_sample,
    _FAKE_S1,
    _FAKE_S2,
    _FAKE_S3,
    _FAKE_S4,
    _FAKE_S5,
    FEEDS_NEXT,
)
import src.simple.run_s6_setup_candidate as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "input_status", "scenario", "setup_candidate",
    "evidence_alignment", "quality_context", "risk",
    "data_quality", "reason_codes", "feeds_next",
]

_REQUIRED_INPUT_STATUS = [
    "market_truth_available", "evidence_available",
    "hybrid_candle_available", "quality_weight_available",
    "liquidity_structure_available", "missing_inputs",
]

_REQUIRED_SCENARIO = [
    "scenario_type", "scenario_direction", "scenario_score",
    "scenario_label", "scenario_reason",
]

_REQUIRED_SETUP = [
    "setup_type", "setup_direction", "raw_setup_score",
    "quality_adjusted_setup_score", "setup_grade",
    "setup_status", "setup_reason",
]

_REQUIRED_ALIGNMENT = [
    "flow_direction", "candle_intent", "structure_bias",
    "liquidity_bias", "alignment_label", "alignment_score",
]

_REQUIRED_QC = [
    "inherited_quality_weight", "inherited_quality_label",
    "quality_allows_setup_candidate",
]

_REQUIRED_RISK = ["setup_risk_label", "trap_risk", "conflict_risk", "reason"]

_FORBIDDEN_KEYS = [
    "entry_price", "stop_loss", "take_profit", "tp1", "tp2",
    "risk_reward", "risk_reward_ratio", "rr",
    "paper_decision", "decision", "paper_trade",
    "edge_score", "edge_eligible", "edge_count",
    "safe_to_open_real_trade",
]


def test_fake_sample_all_required_top_fields():
    sc = run_fake_sample("BTCUSDT")
    for field in _REQUIRED_TOP:
        assert field in sc, f"Missing top-level field: {field}"
    assert sc["block_id"] == "S6_SCENARIO_SETUP_CANDIDATE"
    assert sc["symbol"] == "BTCUSDT"


def test_fake_sample_input_status_fields():
    sc = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_INPUT_STATUS:
        assert f in sc["input_status"], f"input_status missing: {f}"


def test_fake_sample_scenario_fields():
    sc = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_SCENARIO:
        assert f in sc["scenario"], f"scenario missing: {f}"


def test_fake_sample_setup_fields():
    sc = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_SETUP:
        assert f in sc["setup_candidate"], f"setup_candidate missing: {f}"


def test_fake_sample_alignment_fields():
    sc = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_ALIGNMENT:
        assert f in sc["evidence_alignment"], f"evidence_alignment missing: {f}"


def test_fake_sample_quality_context_fields():
    sc = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_QC:
        assert f in sc["quality_context"], f"quality_context missing: {f}"


def test_fake_sample_risk_fields():
    sc = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_RISK:
        assert f in sc["risk"], f"risk missing: {f}"


def test_reason_codes_not_empty():
    sc = run_fake_sample("BTCUSDT")
    assert isinstance(sc["reason_codes"], list)
    assert len(sc["reason_codes"]) >= 1
    assert all(isinstance(c, str) for c in sc["reason_codes"])


def test_feeds_next_includes_s7():
    sc = run_fake_sample("BTCUSDT")
    assert "S7_TRADE_PLAN_DECISION_GATE" in sc["feeds_next"]["next_blocks"]


def test_no_forbidden_decision_or_edge_fields_top_level():
    sc = run_fake_sample("BTCUSDT")
    for k in _FORBIDDEN_KEYS:
        assert k not in sc, f"S6 top-level must not contain forbidden field: {k}"


def test_no_forbidden_decision_fields_in_setup_candidate():
    sc = run_fake_sample("BTCUSDT")
    for k in _FORBIDDEN_KEYS:
        assert k not in sc["setup_candidate"], (
            f"S6 setup_candidate must not contain forbidden field: {k}"
        )


def test_aligned_bullish_produces_long_setup():
    sc = run_fake_sample("BTCUSDT")
    assert sc["evidence_alignment"]["alignment_label"] == "ALIGNED_LONG"
    assert sc["scenario"]["scenario_direction"] == "LONG"
    assert sc["setup_candidate"]["setup_type"].startswith("LONG_")


def test_missing_s5_yields_no_setup_or_watch_no_crash():
    sc = build_setup_candidate(
        "BTCUSDT", _FAKE_S1, _FAKE_S2, _FAKE_S3, _FAKE_S4, None, "TEST"
    )
    assert sc["input_status"]["liquidity_structure_available"] is False
    assert sc["setup_candidate"]["setup_status"] in ("NO_SETUP", "WATCH_SETUP")
    assert sc["scenario"]["scenario_type"] in ("NO_CLEAR_SCENARIO", "UNKNOWN")
    assert sc["reason_codes"]
    assert "S7_TRADE_PLAN_DECISION_GATE" in sc["feeds_next"]["next_blocks"]


def test_missing_s1_yields_invalid():
    sc = build_setup_candidate(
        "BTCUSDT", None, _FAKE_S2, _FAKE_S3, _FAKE_S4, _FAKE_S5, "TEST"
    )
    assert sc["input_status"]["market_truth_available"] is False
    assert sc["setup_candidate"]["setup_status"] == "INVALID"
    assert sc["reason_codes"]


def test_invalid_official_candle_yields_invalid():
    bad_s1 = dict(_FAKE_S1)
    bad_s1["is_official_binance_1m"] = False
    sc = build_setup_candidate(
        "BTCUSDT", bad_s1, _FAKE_S2, _FAKE_S3, _FAKE_S4, _FAKE_S5, "TEST"
    )
    assert sc["setup_candidate"]["setup_status"] == "INVALID"


def test_quality_weight_adjusts_setup_score():
    s4_high = dict(_FAKE_S4)
    s4_high["quality_weight"] = 0.95
    s4_high["quality_label"] = "HIGH_QUALITY"
    sc_high = build_setup_candidate(
        "BTCUSDT", _FAKE_S1, _FAKE_S2, _FAKE_S3, s4_high, _FAKE_S5, "TEST"
    )
    s4_low = dict(_FAKE_S4)
    s4_low["quality_weight"] = 0.30
    s4_low["quality_label"] = "LOW_QUALITY"
    sc_low = build_setup_candidate(
        "BTCUSDT", _FAKE_S1, _FAKE_S2, _FAKE_S3, s4_low, _FAKE_S5, "TEST"
    )
    high = sc_high["setup_candidate"]["quality_adjusted_setup_score"]
    low = sc_low["setup_candidate"]["quality_adjusted_setup_score"]
    assert high > low, (
        f"quality_adjusted_setup_score should fall as quality drops "
        f"(high={high}, low={low})"
    )


def test_conflicting_signals_label_mixed_or_conflicted():
    s3_bear = dict(_FAKE_S3)
    s3_bear["candle_direction"] = "BEARISH"
    s3_bear["intent_label"] = "SELL_PRESSURE_CONFIRMED"
    s5_bear = dict(_FAKE_S5)
    s5_bear["structure_bias"] = "BEARISH"
    s5_bear["draw_on_liquidity"] = "BELOW"
    s5_bear["context_label"] = "BEARISH_CONTEXT"
    sc = build_setup_candidate(
        "BTCUSDT", _FAKE_S1, _FAKE_S2, s3_bear, _FAKE_S4, s5_bear, "TEST"
    )
    assert sc["evidence_alignment"]["alignment_label"] in ("MIXED", "CONFLICTED")
    assert sc["setup_candidate"]["setup_grade"] != "A_PLUS"


def test_data_quality_object_shape():
    sc = run_fake_sample("BTCUSDT")
    dq = sc["data_quality"]
    assert "score" in dq and "level" in dq and "issues" in dq
    assert dq["level"] in ("HIGH", "MEDIUM", "LOW", "CRITICAL")
    assert 0.0 <= dq["score"] <= 1.0


def test_alignment_score_in_range():
    sc = run_fake_sample("BTCUSDT")
    assert 0.0 <= sc["evidence_alignment"]["alignment_score"] <= 1.0


def test_scenario_score_in_range():
    sc = run_fake_sample("BTCUSDT")
    assert 0.0 <= sc["scenario"]["scenario_score"] <= 100.0


def test_setup_score_in_range():
    sc = run_fake_sample("BTCUSDT")
    assert 0.0 <= sc["setup_candidate"]["raw_setup_score"] <= 100.0
    assert 0.0 <= sc["setup_candidate"]["quality_adjusted_setup_score"] <= 100.0


def test_runner_creates_all_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        sc = run_fake_sample("BTCUSDT")
        runner._write_outputs(sc)

        assert (tmp / "state" / "latest_setup_candidate.json").exists()
        assert (tmp / "state" / "s6_setup_candidate_state.json").exists()
        assert (tmp / "data" / "setup_candidate.jsonl").exists()
        assert (tmp / "reports" / "s6_setup_candidate_latest_report.md").exists()

        data = json.loads(
            (tmp / "state" / "latest_setup_candidate.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == "S6_SCENARIO_SETUP_CANDIDATE"
        assert data["reason_codes"]
        assert "S7_TRADE_PLAN_DECISION_GATE" in data["feeds_next"]["next_blocks"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
