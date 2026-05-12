"""Tests for S15 Flow-to-Setup Context Engine."""

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.flow_to_setup_context_engine import (
    compute_setup_context,
    no_valid_context_output,
    run_flow_to_setup_context_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_s15():
    d = TMP_BASE / f"s15_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_evidence(score: float, label: str, confidence: float = 0.8, dq_score: float = 1.0, dq_level: str = "OK") -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "symbol": "BTCUSDT",
        "source": "S12_FLOW_STATE",
        "input_status": "OK",
        "evidence_score": score,
        "evidence_label": label,
        "confidence": confidence,
        "pressure_evidence": {"pressure_label": "BUY_DOMINANT" if score > 0 else "SELL_DOMINANT"},
        "data_quality": {"level": dq_level, "score": dq_score},
    }


def _make_persistence(
    score: float,
    label: str,
    direction: str = "LONG",
    continuation: str = "STRONG",
    decay_risk: bool = False,
    flip_risk: bool = False,
    dq_score: float = 1.0,
    dq_level: str = "OK",
) -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S14_FLOW_PERSISTENCE_ENGINE",
        "symbol": "BTCUSDT",
        "source": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "input_status": "OK",
        "persistence_score": score,
        "persistence_label": label,
        "direction_label": direction,
        "continuation_quality": continuation,
        "decay_risk": decay_risk,
        "flip_risk": flip_risk,
        "data_quality": {"level": dq_level, "score": dq_score},
    }


STRONG_LONG_EVIDENCE = _make_evidence(8.0, "STRONG_LONG_PRESSURE", confidence=0.85)
SUSTAINED_LONG_PERSISTENCE = _make_persistence(8.0, "SUSTAINED_LONG_PRESSURE", direction="LONG", continuation="STRONG")

STRONG_SHORT_EVIDENCE = _make_evidence(-8.0, "STRONG_SHORT_PRESSURE", confidence=0.85)
SUSTAINED_SHORT_PERSISTENCE = _make_persistence(-8.0, "SUSTAINED_SHORT_PRESSURE", direction="SHORT", continuation="STRONG")

EARLY_LONG_EVIDENCE = _make_evidence(3.0, "EARLY_LONG_PRESSURE", confidence=0.5)
FADING_LONG_PERSISTENCE = _make_persistence(5.0, "FADING_LONG_PRESSURE", direction="LONG", continuation="WEAK", decay_risk=True)

NEUTRAL_EVIDENCE = _make_evidence(0.5, "NEUTRAL_FLOW", confidence=0.2)
CHOPPY_PERSISTENCE = _make_persistence(0.0, "CHOPPY_FLOW", direction="NEUTRAL", continuation="NONE")

EARLY_SHORT_EVIDENCE = _make_evidence(-3.0, "EARLY_SHORT_PRESSURE", confidence=0.5)
FADING_SHORT_PERSISTENCE = _make_persistence(-5.0, "FADING_SHORT_PRESSURE", direction="SHORT", continuation="WEAK", decay_risk=True)


# --- Test 1: strong long context ---

def test_strong_long_context():
    result = compute_setup_context(None, STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE)
    assert result["setup_context_label"] == "STRONG_LONG_CONTEXT"
    assert result["direction_bias"] == "LONG"
    assert result["tradeable"] is True


# --- Test 2: weak long context ---

def test_weak_long_context():
    evidence = _make_evidence(3.0, "EARLY_LONG_PRESSURE", confidence=0.55)
    persistence = _make_persistence(3.0, "SUSTAINED_LONG_PRESSURE", direction="LONG", continuation="MODERATE")
    result = compute_setup_context(None, evidence, persistence)
    assert result["setup_context_label"] == "WEAK_LONG_CONTEXT"
    assert result["direction_bias"] == "LONG"
    assert result["tradeable"] is False


# --- Test 3: strong short context ---

def test_strong_short_context():
    result = compute_setup_context(None, STRONG_SHORT_EVIDENCE, SUSTAINED_SHORT_PERSISTENCE)
    assert result["setup_context_label"] == "STRONG_SHORT_CONTEXT"
    assert result["direction_bias"] == "SHORT"
    assert result["tradeable"] is True


# --- Test 4: weak short context ---

def test_weak_short_context():
    evidence = _make_evidence(-3.0, "EARLY_SHORT_PRESSURE", confidence=0.55)
    persistence = _make_persistence(-3.0, "SUSTAINED_SHORT_PRESSURE", direction="SHORT", continuation="MODERATE")
    result = compute_setup_context(None, evidence, persistence)
    assert result["setup_context_label"] == "WEAK_SHORT_CONTEXT"
    assert result["direction_bias"] == "SHORT"
    assert result["tradeable"] is False


# --- Test 5: neutral context ---

def test_neutral_context():
    evidence = _make_evidence(0.5, "NEUTRAL_FLOW", confidence=0.4)
    persistence = _make_persistence(0.5, "SUSTAINED_LONG_PRESSURE", direction="NEUTRAL", continuation="NONE")
    result = compute_setup_context(None, evidence, persistence)
    assert result["setup_context_label"] in ("NEUTRAL_CONTEXT", "NO_TRADE_CONTEXT", "INSUFFICIENT_CONTEXT")
    assert result["tradeable"] is False


# --- Test 6: choppy flow ---

def test_choppy_flow():
    result = compute_setup_context(None, NEUTRAL_EVIDENCE, CHOPPY_PERSISTENCE)
    assert result["setup_context_label"] == "CHOPPY_CONTEXT"
    assert result["tradeable"] is False


# --- Test 7: degraded quality blocks tradeable ---

def test_degraded_quality_blocks_tradeable():
    evidence = _make_evidence(8.0, "STRONG_LONG_PRESSURE", confidence=0.85, dq_score=0.1, dq_level="LOW")
    persistence = _make_persistence(8.0, "SUSTAINED_LONG_PRESSURE", dq_score=0.1, dq_level="LOW")
    result = compute_setup_context(None, evidence, persistence)
    assert result["tradeable"] is False


# --- Test 8: insufficient history does not crash ---

def test_insufficient_history_does_not_crash():
    result = compute_setup_context(None, None, None)
    assert result["setup_context_label"] == "INSUFFICIENT_CONTEXT"
    assert result["tradeable"] is False
    assert result["direction_bias"] == "UNKNOWN"


def test_missing_evidence_does_not_crash():
    result = compute_setup_context(None, None, SUSTAINED_LONG_PERSISTENCE)
    assert result["setup_context_label"] in ("INSUFFICIENT_CONTEXT", "NO_TRADE_CONTEXT", "WEAK_LONG_CONTEXT", "STRONG_LONG_CONTEXT")
    assert result["tradeable"] is False


def test_missing_persistence_does_not_crash():
    result = compute_setup_context(None, STRONG_LONG_EVIDENCE, None)
    assert result["setup_context_label"] in ("INSUFFICIENT_CONTEXT", "NO_TRADE_CONTEXT", "WEAK_LONG_CONTEXT")
    assert result["tradeable"] is False


# --- Test 9: normalized probabilities ---

def test_normalized_probabilities():
    for evidence, persistence in [
        (STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE),
        (STRONG_SHORT_EVIDENCE, SUSTAINED_SHORT_PERSISTENCE),
        (NEUTRAL_EVIDENCE, CHOPPY_PERSISTENCE),
        (None, None),
    ]:
        result = compute_setup_context(None, evidence, persistence)
        assert 0.0 <= result["long_probability"] <= 1.0
        assert 0.0 <= result["short_probability"] <= 1.0
        total = round(result["long_probability"] + result["short_probability"], 2)
        assert abs(total - 1.0) < 0.02, f"Probabilities do not sum to 1.0: {total}"


# --- Test 10: confidence threshold logic ---

def test_confidence_threshold_blocks_tradeable():
    evidence = _make_evidence(8.0, "STRONG_LONG_PRESSURE", confidence=0.3)
    persistence = _make_persistence(8.0, "SUSTAINED_LONG_PRESSURE", continuation="NONE")
    result = compute_setup_context(None, evidence, persistence)
    assert result["confidence"] < 0.60
    assert result["tradeable"] is False


def test_high_confidence_allows_tradeable():
    result = compute_setup_context(None, STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE)
    assert result["confidence"] >= 0.60
    assert result["tradeable"] is True


# --- Test 11: tradeable gate logic ---

def test_tradeable_gate_choppy():
    evidence = _make_evidence(8.0, "STRONG_LONG_PRESSURE", confidence=0.85)
    persistence = _make_persistence(8.0, "CHOPPY_FLOW", continuation="NONE")
    result = compute_setup_context(None, evidence, persistence)
    assert result["tradeable"] is False


def test_tradeable_gate_decay_risk():
    evidence = _make_evidence(8.0, "STRONG_LONG_PRESSURE", confidence=0.85)
    persistence = _make_persistence(8.0, "SUSTAINED_LONG_PRESSURE", decay_risk=True)
    result = compute_setup_context(None, evidence, persistence)
    assert result["tradeable"] is False


def test_tradeable_gate_flip_risk():
    evidence = _make_evidence(8.0, "STRONG_LONG_PRESSURE", confidence=0.85)
    persistence = _make_persistence(8.0, "SUSTAINED_LONG_PRESSURE", flip_risk=True)
    result = compute_setup_context(None, evidence, persistence)
    assert result["tradeable"] is False


def test_tradeable_only_on_strong_label():
    evidence = _make_evidence(3.0, "EARLY_LONG_PRESSURE", confidence=0.85)
    persistence = _make_persistence(3.0, "SUSTAINED_LONG_PRESSURE", continuation="STRONG")
    result = compute_setup_context(None, evidence, persistence)
    assert result["setup_context_label"] != "STRONG_LONG_CONTEXT"
    assert result["tradeable"] is False


# --- Test 12: append-only persistence ---

def test_append_only_persistence(tmp_s15, monkeypatch):
    import src.simple.flow_to_setup_context_engine as eng

    evidence_path = tmp_s15 / "latest_flow_evidence.json"
    persistence_file = tmp_s15 / "latest_flow_persistence.json"
    evidence_path.write_text(json.dumps(STRONG_LONG_EVIDENCE), encoding="utf-8")
    persistence_file.write_text(json.dumps(SUSTAINED_LONG_PERSISTENCE), encoding="utf-8")

    log_path = tmp_s15 / "setup_context_history.jsonl"

    monkeypatch.setattr(eng, "FLOW_STATE_PATH", tmp_s15 / "no_flow_state.json")
    monkeypatch.setattr(eng, "EVIDENCE_PATH", evidence_path)
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", persistence_file)
    monkeypatch.setattr(eng, "SETUP_CONTEXT_PATH", tmp_s15 / "latest_setup_context.json")
    monkeypatch.setattr(eng, "S15_STATE_PATH", tmp_s15 / "s15_state.json")
    monkeypatch.setattr(eng, "SETUP_CONTEXT_LOG_PATH", log_path)
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s15 / "report.md")

    run_flow_to_setup_context_engine()
    run_flow_to_setup_context_engine()
    run_flow_to_setup_context_engine()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3, f"Expected 3 log lines, got {len(lines)}"
    for line in lines:
        entry = json.loads(line)
        assert entry["block_id"] == "S15_FLOW_TO_SETUP_CONTEXT"


# --- Test 13: safety flags always false ---

def test_safety_flags_always_false():
    for evidence, persistence in [
        (STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE),
        (STRONG_SHORT_EVIDENCE, SUSTAINED_SHORT_PERSISTENCE),
        (None, None),
    ]:
        result = compute_setup_context(None, evidence, persistence)
        safety = result["execution_safety"]
        assert safety["safe_to_open_real_trade"] is False
        assert safety["private_api_used"] is False
        assert safety["live_order_sent"] is False

    missing = no_valid_context_output("TEST")
    safety = missing["execution_safety"]
    assert safety["safe_to_open_real_trade"] is False
    assert safety["private_api_used"] is False
    assert safety["live_order_sent"] is False


# --- Test 14: feeds_next includes S16_SCENARIO_ENTRY_TRIGGER ---

def test_feeds_next_includes_s16():
    for evidence, persistence in [
        (STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE),
        (None, None),
    ]:
        result = compute_setup_context(None, evidence, persistence)
        assert "S16_SCENARIO_ENTRY_TRIGGER" in result["feeds_next"]["next_blocks"]

    missing = no_valid_context_output("TEST")
    assert "S16_SCENARIO_ENTRY_TRIGGER" in missing["feeds_next"]["next_blocks"]


# --- Test 15: setup_context_score bounds ---

def test_setup_context_score_bounds():
    for evidence, persistence in [
        (STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE),
        (STRONG_SHORT_EVIDENCE, SUSTAINED_SHORT_PERSISTENCE),
        (NEUTRAL_EVIDENCE, CHOPPY_PERSISTENCE),
        (None, None),
    ]:
        result = compute_setup_context(None, evidence, persistence)
        assert -10.0 <= result["setup_context_score"] <= 10.0


# --- Test 16: reason_codes not empty ---

def test_reason_codes_not_empty():
    for evidence, persistence in [
        (STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE),
        (None, None),
    ]:
        result = compute_setup_context(None, evidence, persistence)
        assert len(result["reason_codes"]) > 0

    missing = no_valid_context_output("TEST")
    assert len(missing["reason_codes"]) > 0


# --- Test 17: output files created ---

def test_run_creates_output_files(tmp_s15, monkeypatch):
    import src.simple.flow_to_setup_context_engine as eng

    evidence_path = tmp_s15 / "latest_flow_evidence.json"
    persistence_file = tmp_s15 / "latest_flow_persistence.json"
    evidence_path.write_text(json.dumps(STRONG_LONG_EVIDENCE), encoding="utf-8")
    persistence_file.write_text(json.dumps(SUSTAINED_LONG_PERSISTENCE), encoding="utf-8")

    monkeypatch.setattr(eng, "FLOW_STATE_PATH", tmp_s15 / "no_flow_state.json")
    monkeypatch.setattr(eng, "EVIDENCE_PATH", evidence_path)
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", persistence_file)
    monkeypatch.setattr(eng, "SETUP_CONTEXT_PATH", tmp_s15 / "latest_setup_context.json")
    monkeypatch.setattr(eng, "S15_STATE_PATH", tmp_s15 / "s15_state.json")
    monkeypatch.setattr(eng, "SETUP_CONTEXT_LOG_PATH", tmp_s15 / "setup_context_history.jsonl")
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s15 / "report.md")

    result = run_flow_to_setup_context_engine()

    assert (tmp_s15 / "latest_setup_context.json").exists()
    assert (tmp_s15 / "s15_state.json").exists()
    assert (tmp_s15 / "setup_context_history.jsonl").exists()
    assert (tmp_s15 / "report.md").exists()
    assert result["block_id"] == "S15_FLOW_TO_SETUP_CONTEXT"


# --- Test 18: required output fields ---

def test_required_output_fields():
    result = compute_setup_context(None, STRONG_LONG_EVIDENCE, SUSTAINED_LONG_PERSISTENCE)
    required = {
        "timestamp_utc", "block_id", "symbol", "source", "input_status",
        "setup_context_label", "setup_context_score", "direction_bias",
        "long_probability", "short_probability", "confidence", "tradeable",
        "context_reason", "data_quality", "reason_codes", "feeds_next",
        "execution_safety",
    }
    assert required <= set(result.keys())
