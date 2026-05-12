"""Tests for S14 Flow Persistence Engine."""

import json
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.simple.flow_persistence_engine import (
    compute_flow_persistence,
    no_valid_flow_output,
    run_flow_persistence_engine,
    _compute_window,
    _persistence_label,
    _direction_label,
    _continuation_quality,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_s14():
    d = TMP_BASE / f"s14_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_entry(score: float, age_seconds: float, ref: datetime, symbol: str = "BTCUSDT") -> dict:
    ts = ref - timedelta(seconds=age_seconds)
    label = "STRONG_LONG_PRESSURE" if score > 4 else ("STRONG_SHORT_PRESSURE" if score < -4 else "NEUTRAL_FLOW")
    return {
        "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "block_id": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "symbol": symbol,
        "evidence_score": score,
        "evidence_label": label,
        "confidence": min(abs(score) / 10.0, 1.0),
    }


REF_TIME = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)

CURRENT_EVIDENCE = {
    "timestamp_utc": "2026-05-11T12:00:00Z",
    "block_id": "S13_1S_FLOW_EVIDENCE_ENGINE",
    "symbol": "BTCUSDT",
    "source": "S12_FLOW_STATE",
    "input_status": "OK",
}


def _make_sustained_long_history() -> list[dict]:
    return [_make_entry(8.0, age, REF_TIME) for age in range(30, 0, -1)]


def _make_sustained_short_history() -> list[dict]:
    return [_make_entry(-8.0, age, REF_TIME) for age in range(30, 0, -1)]


def _make_mixed_history() -> list[dict]:
    entries = []
    for i, age in enumerate(range(30, 0, -1)):
        score = 7.0 if i % 2 == 0 else -7.0
        entries.append(_make_entry(score, age, REF_TIME))
    return entries


def _make_fading_long_history() -> list[dict]:
    entries = []
    for age in range(30, 5, -1):
        entries.append(_make_entry(8.0, age, REF_TIME))
    for age in range(5, 0, -1):
        entries.append(_make_entry(3.0, age, REF_TIME))
    return entries


# --- Test 1: sustained positive evidence creates SUSTAINED_LONG_PRESSURE ---

def test_sustained_positive_creates_sustained_long():
    history = _make_sustained_long_history()
    result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
    assert result["persistence_label"] == "SUSTAINED_LONG_PRESSURE"
    assert result["direction_label"] == "LONG"


# --- Test 2: sustained negative evidence creates SUSTAINED_SHORT_PRESSURE ---

def test_sustained_negative_creates_sustained_short():
    history = _make_sustained_short_history()
    result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
    assert result["persistence_label"] == "SUSTAINED_SHORT_PRESSURE"
    assert result["direction_label"] == "SHORT"


# --- Test 3: mixed evidence creates CHOPPY_FLOW ---

def test_mixed_evidence_creates_choppy_flow():
    history = _make_mixed_history()
    result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
    assert result["persistence_label"] == "CHOPPY_FLOW"


# --- Test 4: fading positive flow creates FADING_LONG_PRESSURE ---

def test_fading_positive_creates_fading_long():
    history = _make_fading_long_history()
    result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
    assert result["persistence_label"] == "FADING_LONG_PRESSURE"


# --- Test 5: missing history creates INSUFFICIENT_HISTORY or NO_VALID_FLOW ---

def test_missing_history_creates_insufficient_or_no_valid(tmp_s14, monkeypatch):
    import src.simple.flow_persistence_engine as eng
    monkeypatch.setattr(eng, "LATEST_EVIDENCE_PATH", tmp_s14 / "nonexistent.json")
    monkeypatch.setattr(eng, "EVIDENCE_LOG_PATH", tmp_s14 / "no_log.jsonl")
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", tmp_s14 / "persist.json")
    monkeypatch.setattr(eng, "S14_STATE_PATH", tmp_s14 / "state.json")
    monkeypatch.setattr(eng, "PERSISTENCE_LOG_PATH", tmp_s14 / "log.jsonl")
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s14 / "report.md")
    result = run_flow_persistence_engine()
    assert result["persistence_label"] in ("INSUFFICIENT_HISTORY", "NO_VALID_FLOW")


def test_empty_history_creates_no_valid_flow():
    result = compute_flow_persistence([], CURRENT_EVIDENCE, ref_time=REF_TIME)
    assert result["persistence_label"] in ("INSUFFICIENT_HISTORY", "NO_VALID_FLOW")


def test_single_entry_creates_insufficient_history():
    history = [_make_entry(8.0, 1, REF_TIME)]
    result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
    assert result["persistence_label"] in ("INSUFFICIENT_HISTORY", "NO_VALID_FLOW")


# --- Test 6: score bounds valid ---

def test_persistence_score_bounds():
    for history in [
        _make_sustained_long_history(),
        _make_sustained_short_history(),
        _make_mixed_history(),
        _make_fading_long_history(),
        [],
    ]:
        result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
        assert -10.0 <= result["persistence_score"] <= 10.0

    missing = no_valid_flow_output("TEST")
    assert -10.0 <= missing["persistence_score"] <= 10.0


def test_window_score_bounds():
    history = _make_sustained_long_history()
    result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
    for wname in ("last_5s", "last_15s", "last_30s"):
        w = result["windows"][wname]
        assert -10.0 <= w["avg_evidence_score"] <= 10.0
        assert 0.0 <= w["direction_consistency"] <= 1.0
        assert 0.0 <= w["confidence_avg"] <= 1.0


# --- Test 7: reason_codes not empty ---

def test_reason_codes_not_empty():
    for history in [_make_sustained_long_history(), []]:
        result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
        assert len(result["reason_codes"]) > 0

    missing = no_valid_flow_output("TEST")
    assert len(missing["reason_codes"]) > 0


# --- Test 8: feeds_next includes S15_FLOW_TO_SETUP_CONTEXT ---

def test_feeds_next_includes_s15():
    result = compute_flow_persistence(_make_sustained_long_history(), CURRENT_EVIDENCE, ref_time=REF_TIME)
    assert "S15_FLOW_TO_SETUP_CONTEXT" in result["feeds_next"]["next_blocks"]

    missing = no_valid_flow_output("TEST")
    assert "S15_FLOW_TO_SETUP_CONTEXT" in missing["feeds_next"]["next_blocks"]


# --- Test 9: safety flags false ---

def test_safety_flags_false():
    for history in [_make_sustained_long_history(), []]:
        result = compute_flow_persistence(history, CURRENT_EVIDENCE, ref_time=REF_TIME)
        safety = result["execution_safety"]
        assert safety["safe_to_open_real_trade"] is False
        assert safety["private_api_used"] is False
        assert safety["live_order_sent"] is False

    missing = no_valid_flow_output("TEST")
    safety = missing["execution_safety"]
    assert safety["safe_to_open_real_trade"] is False
    assert safety["private_api_used"] is False
    assert safety["live_order_sent"] is False


# --- Output file creation ---

def test_run_creates_output_files(tmp_s14, monkeypatch):
    import src.simple.flow_persistence_engine as eng

    evidence_path = tmp_s14 / "latest_flow_evidence.json"
    evidence_path.write_text(json.dumps(CURRENT_EVIDENCE), encoding="utf-8")

    log_path = tmp_s14 / "flow_evidence.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        for entry in _make_sustained_long_history():
            f.write(json.dumps(entry) + "\n")

    monkeypatch.setattr(eng, "LATEST_EVIDENCE_PATH", evidence_path)
    monkeypatch.setattr(eng, "EVIDENCE_LOG_PATH", log_path)
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", tmp_s14 / "persist.json")
    monkeypatch.setattr(eng, "S14_STATE_PATH", tmp_s14 / "state.json")
    monkeypatch.setattr(eng, "PERSISTENCE_LOG_PATH", tmp_s14 / "log.jsonl")
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s14 / "report.md")

    result = run_flow_persistence_engine()
    assert (tmp_s14 / "persist.json").exists()
    assert (tmp_s14 / "state.json").exists()
    assert (tmp_s14 / "log.jsonl").exists()
    assert (tmp_s14 / "report.md").exists()
    assert result["persistence_label"] != "NO_VALID_FLOW"


# --- Required window fields ---

def test_all_windows_have_required_fields():
    result = compute_flow_persistence(_make_sustained_long_history(), CURRENT_EVIDENCE, ref_time=REF_TIME)
    required = {"sample_count", "avg_evidence_score", "positive_count", "negative_count",
                "neutral_count", "dominant_label", "direction_consistency", "confidence_avg"}
    for wname in ("last_5s", "last_15s", "last_30s"):
        assert required <= set(result["windows"][wname].keys()), f"Missing fields in {wname}"


# --- Required top-level fields ---

def test_required_top_level_fields():
    result = compute_flow_persistence(_make_sustained_long_history(), CURRENT_EVIDENCE, ref_time=REF_TIME)
    required = {
        "timestamp_utc", "block_id", "symbol", "source", "input_status",
        "windows", "persistence_score", "persistence_label", "direction_label",
        "continuation_quality", "decay_risk", "flip_risk", "data_quality",
        "reason_codes", "feeds_next", "execution_safety",
    }
    assert required <= set(result.keys())
