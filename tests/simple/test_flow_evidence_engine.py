"""Tests for S13 Flow Evidence Engine."""

import json
import shutil
import uuid
import pytest
from pathlib import Path
from src.simple.flow_evidence_engine import (
    compute_flow_evidence,
    no_valid_flow_output,
    run_flow_evidence_engine,
    _score_delta,
    _score_aggression,
    _score_pressure,
    _evidence_label,
    _pressure_label,
    _clamp,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_s13():
    d = TMP_BASE / f"s13_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


POSITIVE_FLOW_STATE = {
    "latest_bucket": {
        "symbol": "BTCUSDT",
        "source": "S12_FLOW_STATE",
        "buy_volume": 1.0,
        "sell_volume": 0.1,
        "delta": 0.9,
        "total_volume": 1.1,
        "buy_trade_count": 8,
        "sell_trade_count": 2,
        "aggression_label": "STRONG_BUY",
    },
    "quality_state": {"level": "OK", "score": 1.0},
}

NEGATIVE_FLOW_STATE = {
    "latest_bucket": {
        "symbol": "BTCUSDT",
        "source": "S12_FLOW_STATE",
        "buy_volume": 0.1,
        "sell_volume": 1.0,
        "delta": -0.9,
        "total_volume": 1.1,
        "buy_trade_count": 2,
        "sell_trade_count": 8,
        "aggression_label": "STRONG_SELL",
    },
    "quality_state": {"level": "OK", "score": 1.0},
}

BALANCED_FLOW_STATE = {
    "latest_bucket": {
        "symbol": "BTCUSDT",
        "source": "S12_FLOW_STATE",
        "buy_volume": 0.5,
        "sell_volume": 0.5,
        "delta": 0.0,
        "total_volume": 1.0,
        "buy_trade_count": 5,
        "sell_trade_count": 5,
        "aggression_label": "BALANCED",
    },
    "quality_state": {"level": "OK", "score": 1.0},
}


def test_positive_delta_creates_long_pressure():
    result = compute_flow_evidence(POSITIVE_FLOW_STATE)
    assert result["delta_evidence"]["delta_score"] > 0
    assert result["evidence_label"] in (
        "STRONG_LONG_PRESSURE", "EARLY_LONG_PRESSURE", "NEUTRAL_FLOW"
    )
    assert result["pressure_evidence"]["pressure_label"] in ("BUY_DOMINANT", "BALANCED")


def test_negative_delta_creates_short_pressure():
    result = compute_flow_evidence(NEGATIVE_FLOW_STATE)
    assert result["delta_evidence"]["delta_score"] < 0
    assert result["evidence_label"] in (
        "STRONG_SHORT_PRESSURE", "EARLY_SHORT_PRESSURE", "NEUTRAL_FLOW"
    )
    assert result["pressure_evidence"]["pressure_label"] in ("SELL_DOMINANT", "BALANCED")


def test_balanced_flow_creates_neutral_flow():
    result = compute_flow_evidence(BALANCED_FLOW_STATE)
    assert result["evidence_label"] == "NEUTRAL_FLOW"
    assert result["pressure_evidence"]["pressure_label"] == "BALANCED"


def test_missing_flow_state_creates_no_valid_flow(tmp_s13, monkeypatch):
    import src.simple.flow_evidence_engine as eng
    monkeypatch.setattr(eng, "FLOW_STATE_PATH", tmp_s13 / "nonexistent.json")
    monkeypatch.setattr(eng, "EVIDENCE_PATH", tmp_s13 / "ev.json")
    monkeypatch.setattr(eng, "S13_STATE_PATH", tmp_s13 / "s13.json")
    monkeypatch.setattr(eng, "EVIDENCE_LOG_PATH", tmp_s13 / "log.jsonl")
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s13 / "report.md")
    result = run_flow_evidence_engine()
    assert result["evidence_label"] == "NO_VALID_FLOW"
    assert result["input_status"] == "MISSING"


def test_confidence_between_0_and_1():
    for state in (POSITIVE_FLOW_STATE, NEGATIVE_FLOW_STATE, BALANCED_FLOW_STATE):
        result = compute_flow_evidence(state)
        assert 0.0 <= result["confidence"] <= 1.0

    missing = no_valid_flow_output("TEST")
    assert 0.0 <= missing["confidence"] <= 1.0


def test_scores_between_minus10_and_plus10():
    for state in (POSITIVE_FLOW_STATE, NEGATIVE_FLOW_STATE, BALANCED_FLOW_STATE):
        result = compute_flow_evidence(state)
        assert -10.0 <= result["delta_evidence"]["delta_score"] <= 10.0
        assert -10.0 <= result["aggression_evidence"]["aggression_score"] <= 10.0
        assert -10.0 <= result["pressure_evidence"]["pressure_score"] <= 10.0
        assert -10.0 <= result["evidence_score"] <= 10.0


def test_reason_codes_not_empty():
    result = compute_flow_evidence(POSITIVE_FLOW_STATE)
    assert len(result["reason_codes"]) > 0

    missing = no_valid_flow_output("TEST")
    assert len(missing["reason_codes"]) > 0


def test_feeds_next_includes_s14():
    result = compute_flow_evidence(POSITIVE_FLOW_STATE)
    assert "S14_FLOW_PERSISTENCE_ENGINE" in result["feeds_next"]["next_blocks"]

    missing = no_valid_flow_output("TEST")
    assert "S14_FLOW_PERSISTENCE_ENGINE" in missing["feeds_next"]["next_blocks"]


def test_safety_flags_false():
    result = compute_flow_evidence(POSITIVE_FLOW_STATE)
    safety = result["execution_safety"]
    assert safety["safe_to_open_real_trade"] is False
    assert safety["private_api_used"] is False
    assert safety["live_order_sent"] is False

    missing = no_valid_flow_output("TEST")
    safety = missing["execution_safety"]
    assert safety["safe_to_open_real_trade"] is False
    assert safety["private_api_used"] is False
    assert safety["live_order_sent"] is False


def test_run_creates_output_files(tmp_s13, monkeypatch):
    import src.simple.flow_evidence_engine as eng

    flow_state_path = tmp_s13 / "latest_flow_state.json"
    flow_state_path.write_text(json.dumps(POSITIVE_FLOW_STATE), encoding="utf-8")

    monkeypatch.setattr(eng, "FLOW_STATE_PATH", flow_state_path)
    monkeypatch.setattr(eng, "EVIDENCE_PATH", tmp_s13 / "ev.json")
    monkeypatch.setattr(eng, "S13_STATE_PATH", tmp_s13 / "s13.json")
    monkeypatch.setattr(eng, "EVIDENCE_LOG_PATH", tmp_s13 / "log.jsonl")
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s13 / "report.md")

    result = run_flow_evidence_engine()
    assert (tmp_s13 / "ev.json").exists()
    assert (tmp_s13 / "s13.json").exists()
    assert (tmp_s13 / "log.jsonl").exists()
    assert (tmp_s13 / "report.md").exists()
    assert result["evidence_label"] != "NO_VALID_FLOW"
