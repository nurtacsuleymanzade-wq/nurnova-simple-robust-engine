"""Tests for S16 Scenario + Entry Trigger Engine."""

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.scenario_entry_trigger_engine import (
    compute_scenario_trigger,
    no_valid_output,
    run_scenario_entry_trigger_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_s16():
    d = TMP_BASE / f"s16_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _setup_ctx(
    label: str,
    score: float,
    direction: str,
    confidence: float,
    tradeable: bool,
    dq_level: str = "OK",
    dq_score: float = 1.0,
) -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S15_FLOW_TO_SETUP_CONTEXT",
        "symbol": "BTCUSDT",
        "source": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "setup_context_label": label,
        "setup_context_score": score,
        "direction_bias": direction,
        "confidence": confidence,
        "tradeable": tradeable,
        "data_quality": {"level": dq_level, "score": dq_score},
    }


def _evidence(score: float, label: str, confidence: float = 0.85) -> dict:
    return {
        "symbol": "BTCUSDT",
        "evidence_score": score,
        "evidence_label": label,
        "confidence": confidence,
        "data_quality": {"level": "OK", "score": 1.0},
    }


def _persistence(
    score: float,
    label: str,
    direction: str = "LONG",
    continuation: str = "STRONG",
    decay_risk: bool = False,
    flip_risk: bool = False,
) -> dict:
    return {
        "symbol": "BTCUSDT",
        "persistence_score": score,
        "persistence_label": label,
        "direction_label": direction,
        "continuation_quality": continuation,
        "decay_risk": decay_risk,
        "flip_risk": flip_risk,
        "data_quality": {"level": "OK", "score": 1.0},
    }


# --- Test 1: long continuation ---

def test_long_continuation():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 8.0, "LONG", 0.85, True)
    ev = _evidence(8.0, "STRONG_LONG_PRESSURE")
    pers = _persistence(8.0, "SUSTAINED_LONG_PRESSURE", "LONG", "STRONG")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["scenario_label"] == "LONG_CONTINUATION"
    assert r["direction_bias"] == "LONG"
    assert r["market_regime"] == "TRENDING"


# --- Test 2: short continuation ---

def test_short_continuation():
    ctx = _setup_ctx("STRONG_SHORT_CONTEXT", -8.0, "SHORT", 0.85, True)
    ev = _evidence(-8.0, "STRONG_SHORT_PRESSURE")
    pers = _persistence(-8.0, "SUSTAINED_SHORT_PRESSURE", "SHORT", "STRONG")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["scenario_label"] == "SHORT_CONTINUATION"
    assert r["direction_bias"] == "SHORT"


# --- Test 3: reversal detection ---

def test_long_reversal_detection():
    ctx = _setup_ctx("WEAK_LONG_CONTEXT", 3.0, "LONG", 0.6, False)
    ev = _evidence(5.0, "EARLY_LONG_PRESSURE")
    pers = _persistence(-3.0, "SUSTAINED_SHORT_PRESSURE", "SHORT", "MODERATE", flip_risk=True)
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["scenario_label"] == "LONG_REVERSAL"
    assert r["market_regime"] == "REVERSAL"


def test_short_reversal_detection():
    ctx = _setup_ctx("WEAK_SHORT_CONTEXT", -3.0, "SHORT", 0.6, False)
    ev = _evidence(-5.0, "EARLY_SHORT_PRESSURE")
    pers = _persistence(3.0, "SUSTAINED_LONG_PRESSURE", "LONG", "MODERATE", flip_risk=True)
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["scenario_label"] == "SHORT_REVERSAL"


# --- Test 4: breakout attempt ---

def test_breakout_attempt():
    ctx = _setup_ctx("WEAK_LONG_CONTEXT", 5.0, "LONG", 0.65, False)
    ev = _evidence(7.0, "STRONG_LONG_PRESSURE")
    pers = _persistence(2.0, "INSUFFICIENT_HISTORY", "LONG", "WEAK")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["scenario_label"] == "BREAKOUT_ATTEMPT"


# --- Test 5: failed breakout ---

def test_failed_breakout():
    ctx = _setup_ctx("WEAK_LONG_CONTEXT", 4.0, "LONG", 0.5, False)
    ev = _evidence(5.0, "EARLY_LONG_PRESSURE")
    pers = _persistence(5.0, "FADING_LONG_PRESSURE", "LONG", "WEAK", decay_risk=True)
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["scenario_label"] == "FAILED_BREAKOUT"


# --- Test 6: choppy rejection ---

def test_choppy_rejection():
    ctx = _setup_ctx("CHOPPY_CONTEXT", 0.0, "NEUTRAL", 0.2, False)
    ev = _evidence(0.5, "NEUTRAL_FLOW", confidence=0.2)
    pers = _persistence(0.0, "CHOPPY_FLOW", "NEUTRAL", "NONE")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["scenario_label"] == "CHOPPY_RANGE"
    assert r["market_regime"] == "CHOPPY"
    assert r["trigger_state"] == "NO_TRIGGER"
    assert r["ready_for_entry"] is False


# --- Test 7: conflicted trigger ---

def test_conflicted_trigger():
    ctx = _setup_ctx("WEAK_LONG_CONTEXT", 3.0, "LONG", 0.6, False)
    ev = _evidence(4.0, "EARLY_LONG_PRESSURE")
    pers = _persistence(3.0, "SUSTAINED_LONG_PRESSURE", "LONG", "MODERATE",
                        decay_risk=True, flip_risk=True)
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["trigger_state"] == "CONFLICTED_TRIGGER"
    assert r["ready_for_entry"] is False


# --- Test 8: insufficient data ---

def test_insufficient_data_does_not_crash():
    r = compute_scenario_trigger(None, None, None, None)
    assert r["scenario_label"] == "INSUFFICIENT_DATA"
    assert r["trigger_state"] == "NO_TRIGGER"
    assert r["direction_bias"] == "UNKNOWN"
    assert r["market_regime"] == "UNKNOWN"
    assert r["ready_for_entry"] is False


def test_partial_inputs_do_not_crash():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 8.0, "LONG", 0.85, True)
    r = compute_scenario_trigger(ctx, None, None, None)
    assert r["scenario_label"] in (
        "INSUFFICIENT_DATA", "NO_SCENARIO", "LONG_CONTINUATION",
        "BREAKOUT_ATTEMPT", "CHOPPY_RANGE",
    )
    assert r["ready_for_entry"] is False


# --- Test 9: normalized probabilities ---

def test_normalized_probabilities():
    cases = [
        (_setup_ctx("STRONG_LONG_CONTEXT", 8.0, "LONG", 0.85, True),
         _evidence(8.0, "STRONG_LONG_PRESSURE"),
         _persistence(8.0, "SUSTAINED_LONG_PRESSURE")),
        (_setup_ctx("STRONG_SHORT_CONTEXT", -8.0, "SHORT", 0.85, True),
         _evidence(-8.0, "STRONG_SHORT_PRESSURE"),
         _persistence(-8.0, "SUSTAINED_SHORT_PRESSURE", "SHORT")),
        (_setup_ctx("CHOPPY_CONTEXT", 0.0, "NEUTRAL", 0.2, False),
         _evidence(0.0, "NEUTRAL_FLOW", confidence=0.2),
         _persistence(0.0, "CHOPPY_FLOW", "NEUTRAL", "NONE")),
        (None, None, None),
    ]
    for ctx, ev, pers in cases:
        r = compute_scenario_trigger(ctx, None, ev, pers)
        m, f, k = r["estimated_move_probability"], r["estimated_failure_probability"], r["estimated_fakeout_probability"]
        for p in (m, f, k):
            assert 0.0 <= p <= 1.0
        total = round(m + f + k, 2)
        assert abs(total - 1.0) < 0.02, f"Probabilities do not sum to 1.0: {total} ({m}+{f}+{k})"


# --- Test 10: trigger threshold logic ---

def test_low_trigger_strength_no_ready():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 4.0, "LONG", 0.4, True)
    ev = _evidence(4.0, "STRONG_LONG_PRESSURE", confidence=0.4)
    pers = _persistence(4.0, "SUSTAINED_LONG_PRESSURE", "LONG", "WEAK")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["trigger_strength"] < 0.70
    assert r["ready_for_entry"] is False


def test_high_trigger_strength_can_be_ready():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE", confidence=0.95)
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE", "LONG", "STRONG")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["trigger_strength"] >= 0.70
    assert r["ready_for_entry"] is True
    assert r["trigger_state"] == "READY_FOR_ENTRY"


# --- Test 11: ready_for_entry gate logic ---

def test_ready_for_entry_blocked_by_non_tradeable():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, False)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE", confidence=0.95)
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE", "LONG", "STRONG")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["ready_for_entry"] is False


def test_ready_for_entry_blocked_by_degraded_quality():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True, dq_level="LOW", dq_score=0.2)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE", confidence=0.95)
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE", "LONG", "STRONG")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["ready_for_entry"] is False


def test_ready_for_entry_blocked_by_neutral_direction():
    ctx = _setup_ctx("NEUTRAL_CONTEXT", 0.0, "NEUTRAL", 0.95, False)
    ev = _evidence(0.0, "NEUTRAL_FLOW", confidence=0.95)
    pers = _persistence(0.0, "SUSTAINED_LONG_PRESSURE", "NEUTRAL", "STRONG")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["ready_for_entry"] is False
    assert r["trigger_state"] == "NO_TRIGGER"


def test_model_consensus_conflict_reduces_scenario_score():
    ctx = _setup_ctx("WEAK_LONG_CONTEXT", 5.0, "LONG", 0.7, False)
    ev = _evidence(4.0, "STRONG_LONG_PRESSURE", confidence=0.7)
    pers = _persistence(3.0, "SUSTAINED_LONG_PRESSURE", "LONG", "STRONG")
    base = compute_scenario_trigger(ctx, None, ev, pers)
    conflict = compute_scenario_trigger(
        ctx, None, ev, pers, {
            "consensus_direction": "SHORT",
            "active_model_count": 2,
            "long_probability_pct": 0.0,
            "short_probability_pct": 100.0,
        }
    )
    assert conflict["direction_bias"] == "SHORT"
    assert conflict["scenario_label"] == "MODEL_SHORT_OVERRIDE"
    assert "MODEL_OVERRIDE_LONG_TO_SHORT" in conflict["reason_codes"]
    assert conflict["model_integration"]["model_consensus"] == "SHORT"
    assert conflict["timeframe"] == "1m"
    assert base["scenario_score"] != conflict["scenario_score"]


def test_ready_for_entry_blocked_by_flip_risk():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE", confidence=0.95)
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE", "LONG", "STRONG", flip_risk=True)
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert r["ready_for_entry"] is False


# --- Test 12: append-only persistence ---

def test_append_only_persistence(tmp_s16, monkeypatch):
    import src.simple.scenario_entry_trigger_engine as eng

    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE", confidence=0.95)
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE", "LONG", "STRONG")

    ctx_path = tmp_s16 / "setup_context.json"
    ev_path = tmp_s16 / "evidence.json"
    pers_path = tmp_s16 / "persistence.json"
    ctx_path.write_text(json.dumps(ctx), encoding="utf-8")
    ev_path.write_text(json.dumps(ev), encoding="utf-8")
    pers_path.write_text(json.dumps(pers), encoding="utf-8")

    log_path = tmp_s16 / "scenario_trigger_history.jsonl"

    monkeypatch.setattr(eng, "SETUP_CONTEXT_PATH", ctx_path)
    monkeypatch.setattr(eng, "FLOW_STATE_PATH", tmp_s16 / "no_flow_state.json")
    monkeypatch.setattr(eng, "EVIDENCE_PATH", ev_path)
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", pers_path)
    monkeypatch.setattr(eng, "SCENARIO_TRIGGER_PATH", tmp_s16 / "latest_scenario_trigger.json")
    monkeypatch.setattr(eng, "S16_STATE_PATH", tmp_s16 / "s16_state.json")
    monkeypatch.setattr(eng, "SCENARIO_TRIGGER_LOG_PATH", log_path)
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s16 / "report.md")

    run_scenario_entry_trigger_engine()
    run_scenario_entry_trigger_engine()
    run_scenario_entry_trigger_engine()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


# --- Test 13: safety flags always false ---

def test_safety_flags_always_false():
    cases = [
        (_setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True),
         _evidence(9.0, "STRONG_LONG_PRESSURE"),
         _persistence(9.0, "SUSTAINED_LONG_PRESSURE")),
        (None, None, None),
    ]
    for ctx, ev, pers in cases:
        r = compute_scenario_trigger(ctx, None, ev, pers)
        s = r["execution_safety"]
        assert s["safe_to_open_real_trade"] is False
        assert s["private_api_used"] is False
        assert s["live_order_sent"] is False

    missing = no_valid_output("TEST")
    s = missing["execution_safety"]
    assert s["safe_to_open_real_trade"] is False
    assert s["private_api_used"] is False
    assert s["live_order_sent"] is False


# --- Test 14: feeds_next includes S17 ---

def test_feeds_next_includes_s17():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE")
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert "S17_TRADE_PLAN_ENGINE" in r["feeds_next"]["next_blocks"]

    missing = no_valid_output("TEST")
    assert "S17_TRADE_PLAN_ENGINE" in missing["feeds_next"]["next_blocks"]


# --- Test 15: required output fields ---

def test_required_output_fields():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE")
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    required = {
        "timestamp_utc", "block_id", "symbol", "source",
        "scenario_label", "scenario_score", "direction_bias",
        "trigger_state", "trigger_strength", "trigger_confidence", "trigger_reason",
        "estimated_move_probability", "estimated_failure_probability",
        "estimated_fakeout_probability", "market_regime", "tradeable",
        "ready_for_entry", "model_integration", "timeframe", "candle_close_time",
        "data_quality", "reason_codes", "feeds_next", "execution_safety",
    }
    assert required <= set(r.keys())


# --- Test 16: scenario_score and trigger_strength bounds ---

def test_score_and_strength_bounds():
    cases = [
        (_setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True),
         _evidence(9.0, "STRONG_LONG_PRESSURE"),
         _persistence(9.0, "SUSTAINED_LONG_PRESSURE")),
        (_setup_ctx("STRONG_SHORT_CONTEXT", -9.0, "SHORT", 0.95, True),
         _evidence(-9.0, "STRONG_SHORT_PRESSURE"),
         _persistence(-9.0, "SUSTAINED_SHORT_PRESSURE", "SHORT")),
        (None, None, None),
    ]
    for ctx, ev, pers in cases:
        r = compute_scenario_trigger(ctx, None, ev, pers)
        assert -10.0 <= r["scenario_score"] <= 10.0
        assert 0.0 <= r["trigger_strength"] <= 1.0
        assert 0.0 <= r["trigger_confidence"] <= 1.0


# --- Test 17: reason_codes not empty ---

def test_reason_codes_not_empty():
    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE")
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE")
    r = compute_scenario_trigger(ctx, None, ev, pers)
    assert len(r["reason_codes"]) > 0

    missing = no_valid_output("TEST")
    assert len(missing["reason_codes"]) > 0


# --- Test 18: output files created ---

def test_run_creates_output_files(tmp_s16, monkeypatch):
    import src.simple.scenario_entry_trigger_engine as eng

    ctx = _setup_ctx("STRONG_LONG_CONTEXT", 9.0, "LONG", 0.95, True)
    ev = _evidence(9.0, "STRONG_LONG_PRESSURE")
    pers = _persistence(9.0, "SUSTAINED_LONG_PRESSURE")

    ctx_path = tmp_s16 / "setup_context.json"
    ev_path = tmp_s16 / "evidence.json"
    pers_path = tmp_s16 / "persistence.json"
    ctx_path.write_text(json.dumps(ctx), encoding="utf-8")
    ev_path.write_text(json.dumps(ev), encoding="utf-8")
    pers_path.write_text(json.dumps(pers), encoding="utf-8")

    monkeypatch.setattr(eng, "SETUP_CONTEXT_PATH", ctx_path)
    monkeypatch.setattr(eng, "FLOW_STATE_PATH", tmp_s16 / "no_flow_state.json")
    monkeypatch.setattr(eng, "EVIDENCE_PATH", ev_path)
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", pers_path)
    monkeypatch.setattr(eng, "SCENARIO_TRIGGER_PATH", tmp_s16 / "latest_scenario_trigger.json")
    monkeypatch.setattr(eng, "S16_STATE_PATH", tmp_s16 / "s16_state.json")
    monkeypatch.setattr(eng, "SCENARIO_TRIGGER_LOG_PATH", tmp_s16 / "history.jsonl")
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s16 / "report.md")

    r = run_scenario_entry_trigger_engine()
    assert (tmp_s16 / "latest_scenario_trigger.json").exists()
    assert (tmp_s16 / "s16_state.json").exists()
    assert (tmp_s16 / "history.jsonl").exists()
    assert (tmp_s16 / "report.md").exists()
    assert r["block_id"] == "S16_SCENARIO_ENTRY_TRIGGER"
