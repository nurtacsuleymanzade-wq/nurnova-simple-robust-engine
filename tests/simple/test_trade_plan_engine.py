"""Tests for S17 Trade Plan Engine."""

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.trade_plan_engine import (
    compute_trade_plan,
    no_valid_output,
    run_trade_plan_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_s17():
    d = TMP_BASE / f"s17_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _trigger(
    direction: str = "LONG",
    trigger_state: str = "READY_FOR_ENTRY",
    ready: bool = True,
    trigger_strength: float = 0.85,
    scenario_label: str = "LONG_CONTINUATION",
    dq_level: str = "OK",
    dq_score: float = 1.0,
) -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S16_SCENARIO_ENTRY_TRIGGER",
        "symbol": "BTCUSDT",
        "source": "S15_FLOW_TO_SETUP_CONTEXT",
        "scenario_label": scenario_label,
        "scenario_score": 8.0,
        "direction_bias": direction,
        "trigger_state": trigger_state,
        "trigger_strength": trigger_strength,
        "trigger_confidence": 0.7,
        "ready_for_entry": ready,
        "tradeable": ready,
        "data_quality": {"level": dq_level, "score": dq_score},
    }


def _setup(direction: str = "LONG", confidence: float = 0.85, tradeable: bool = True) -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S15_FLOW_TO_SETUP_CONTEXT",
        "symbol": "BTCUSDT",
        "direction_bias": direction,
        "confidence": confidence,
        "tradeable": tradeable,
        "data_quality": {"level": "OK", "score": 1.0},
    }


def _flow_state(price: float = 80000.0) -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S12_LATEST_FLOW_STATE",
        "latest_bucket": {
            "symbol": "BTCUSDT",
            "last_price": price,
            "mid_price": price,
            "vwap": price,
        },
    }


def _market_truth() -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "candle_close_time": "2026-05-11T12:00:00Z",
        "official_candle": {"close_time_utc": "2026-05-11T12:00:00Z"},
    }


# --- Test 1: valid long plan ---

def test_valid_long_plan():
    r = compute_trade_plan(_trigger("LONG"), _setup("LONG"), _flow_state(80000.0), None, None)
    assert r["plan_status"] in ("PLAN_READY", "WATCH_ONLY")
    assert r["side"] == "LONG"
    assert r["stop_loss"] < r["entry_price"]
    assert r["tp1"] > r["entry_price"]
    assert r["tp2"] > r["entry_price"]
    assert r["tp2"] >= r["tp1"]
    assert r["invalidation_price"] == r["stop_loss"]


def test_valid_long_plan_ready():
    r = compute_trade_plan(_trigger("LONG", trigger_strength=0.9), _setup("LONG", 0.9), _flow_state(80000.0), None, None)
    assert r["plan_status"] == "PLAN_READY"
    assert r["plan_grade"] in ("A_PLUS", "A", "B", "C")
    assert r["rr_tp1"] >= 1.0
    assert r["rr_tp2"] >= 1.5


# --- Test 2: valid short plan ---

def test_valid_short_plan():
    r = compute_trade_plan(
        _trigger("SHORT", scenario_label="SHORT_CONTINUATION", trigger_strength=0.9),
        _setup("SHORT", 0.9),
        _flow_state(80000.0),
        None, None,
    )
    assert r["plan_status"] == "PLAN_READY"
    assert r["side"] == "SHORT"
    assert r["stop_loss"] > r["entry_price"]
    assert r["tp1"] < r["entry_price"]
    assert r["tp2"] < r["entry_price"]
    assert r["tp2"] <= r["tp1"]
    assert r["invalidation_price"] == r["stop_loss"]


# --- Test 3: no plan when S16 not ready ---

def test_no_plan_when_not_ready():
    r = compute_trade_plan(
        _trigger("LONG", trigger_state="WAIT_FOR_CONFIRMATION", ready=False, trigger_strength=0.5),
        _setup("LONG"),
        _flow_state(80000.0),
        None, None,
    )
    assert r["plan_status"] == "WATCH_ONLY"
    assert r["plan_grade"] == "WATCH"


def test_no_plan_when_missing_inputs():
    r = compute_trade_plan(None, None, None, None, None)
    assert r["plan_status"] == "NO_PLAN"
    assert r["plan_grade"] == "NO_PLAN"
    assert r["side"] == "UNKNOWN"


def test_no_plan_when_no_flow_state():
    r = compute_trade_plan(_trigger("LONG"), _setup("LONG"), None, None, None)
    assert r["plan_status"] == "INVALID"


# --- Test 4: invalid if LONG stop above entry (direction contradiction enforced by builder) ---

def test_long_stop_below_entry_invariant():
    r = compute_trade_plan(_trigger("LONG", trigger_strength=0.95), _setup("LONG", 0.95), _flow_state(80000.0), None, None)
    assert r["stop_loss"] < r["entry_price"], "LONG stop must be below entry"


# --- Test 5: invalid if SHORT stop below entry (invariant test) ---

def test_short_stop_above_entry_invariant():
    r = compute_trade_plan(
        _trigger("SHORT", scenario_label="SHORT_CONTINUATION", trigger_strength=0.95),
        _setup("SHORT", 0.95),
        _flow_state(80000.0),
        None, None,
    )
    assert r["stop_loss"] > r["entry_price"], "SHORT stop must be above entry"


# --- Test 6: invalid TP direction caught ---

def test_direction_contradiction_detected_via_invalid_inputs():
    # NEUTRAL direction → not directional → NO_PLAN
    r = compute_trade_plan(_trigger("NEUTRAL"), _setup("NEUTRAL", 0.5, False), _flow_state(80000.0), None, None)
    assert r["plan_status"] == "NO_PLAN"
    assert r["side"] == "NEUTRAL"


def test_long_tp_above_entry():
    r = compute_trade_plan(_trigger("LONG", trigger_strength=0.95), _setup("LONG", 0.95), _flow_state(80000.0), None, None)
    assert r["tp1"] > r["entry_price"]
    assert r["tp2"] > r["entry_price"]


def test_short_tp_below_entry():
    r = compute_trade_plan(
        _trigger("SHORT", scenario_label="SHORT_CONTINUATION", trigger_strength=0.95),
        _setup("SHORT", 0.95), _flow_state(80000.0), None, None,
    )
    assert r["tp1"] < r["entry_price"]
    assert r["tp2"] < r["entry_price"]


# --- Test 7: RR calculated from prices ---

def test_rr_calculated_from_prices():
    r = compute_trade_plan(_trigger("LONG", trigger_strength=0.95), _setup("LONG", 0.95), _flow_state(80000.0), None, None)
    expected_rr1 = abs(r["tp1"] - r["entry_price"]) / abs(r["entry_price"] - r["stop_loss"])
    expected_rr2 = abs(r["tp2"] - r["entry_price"]) / abs(r["entry_price"] - r["stop_loss"])
    assert abs(r["rr_tp1"] - round(expected_rr1, 4)) < 1e-3
    assert abs(r["rr_tp2"] - round(expected_rr2, 4)) < 1e-3
    assert r["rr_tp1"] > 0
    assert r["rr_tp2"] > 0


# --- Test 8: low RR downgrades plan ---

def test_low_rr_downgrades_plan(monkeypatch):
    import src.simple.trade_plan_engine as eng
    monkeypatch.setattr(eng, "MIN_RR_TP1", 5.0)
    monkeypatch.setattr(eng, "MIN_RR_TP2", 10.0)
    r = eng.compute_trade_plan(_trigger("LONG", trigger_strength=0.95), _setup("LONG", 0.95), _flow_state(80000.0), None, None)
    assert r["plan_status"] == "WATCH_ONLY"
    assert "LOW_RR_DOWNGRADE" in r["reason_codes"]


# --- Test 9: reason_codes not empty ---

def test_reason_codes_not_empty():
    r = compute_trade_plan(_trigger("LONG"), _setup("LONG"), _flow_state(80000.0), None, None)
    assert len(r["reason_codes"]) > 0
    missing = no_valid_output("TEST")
    assert len(missing["reason_codes"]) > 0


# --- Test 10: safety flags always false ---

def test_safety_flags_always_false():
    cases = [
        (_trigger("LONG", trigger_strength=0.95), _setup("LONG", 0.95), _flow_state(80000.0)),
        (_trigger("SHORT", scenario_label="SHORT_CONTINUATION"), _setup("SHORT"), _flow_state(80000.0)),
        (None, None, None),
    ]
    for trig, ctx, fs in cases:
        r = compute_trade_plan(trig, ctx, fs, None, None)
        s = r["execution_safety"]
        assert s["safe_to_open_real_trade"] is False
        assert s["private_api_used"] is False
        assert s["live_order_sent"] is False
    m = no_valid_output("X")["execution_safety"]
    assert m["safe_to_open_real_trade"] is False
    assert m["private_api_used"] is False
    assert m["live_order_sent"] is False


# --- Test 11: feeds_next includes S18 ---

def test_feeds_next_includes_s18():
    r = compute_trade_plan(_trigger("LONG"), _setup("LONG"), _flow_state(80000.0), None, None)
    assert "S18_DECISION_GATE" in r["feeds_next"]["next_blocks"]
    missing = no_valid_output("TEST")
    assert "S18_DECISION_GATE" in missing["feeds_next"]["next_blocks"]


# --- Test 12: required output fields ---

def test_required_output_fields():
    r = compute_trade_plan(_trigger("LONG", trigger_strength=0.95), _setup("LONG", 0.95), _flow_state(80000.0), None, None)
    required = {
        "timestamp_utc", "block_id", "symbol", "source", "input_status",
        "plan_status", "side", "entry_price", "stop_loss", "tp1", "tp2",
        "rr_tp1", "rr_tp2", "invalidation_price", "plan_quality_score",
        "plan_grade", "entry_reason", "stop_reason", "tp_reason",
        "invalidation_reason", "model_veto", "model_veto_reason", "timeframe",
        "candle_close_time", "risk_context", "data_quality",
        "reason_codes", "feeds_next", "execution_safety",
    }
    assert required <= set(r.keys())


def test_model_veto_invalidates_plan():
    r = compute_trade_plan(
        _trigger("LONG", trigger_strength=0.95),
        _setup("LONG", 0.95),
        _flow_state(80000.0),
        None,
        None,
        market_truth=_market_truth(),
        model_registry={
            "active_model_count": 1,
            "consensus_direction": "SHORT",
            "long_probability_pct": 0.0,
            "short_probability_pct": 100.0,
        },
    )
    assert r["plan_status"] == "INVALID"
    assert r["model_veto"] is True
    assert r["model_veto_reason"] == "MODEL_VETO_LONG_CONSENSUS_SHORT_STRENGTH_100.0"
    assert r["timeframe"] == "1m"
    assert r["candle_close_time"] == "2026-05-11T12:00:00Z"


# --- Test 13: degraded DQ → WATCH_ONLY not PLAN_READY ---

def test_degraded_dq_blocks_plan_ready():
    r = compute_trade_plan(
        _trigger("LONG", dq_level="LOW", dq_score=0.3, trigger_strength=0.95),
        _setup("LONG", 0.95),
        _flow_state(80000.0),
        None, None,
    )
    assert r["plan_status"] == "WATCH_ONLY"


# --- Test 14: append-only persistence + files created ---

def test_append_only_persistence_and_outputs(tmp_s17, monkeypatch):
    import src.simple.trade_plan_engine as eng

    trig = _trigger("LONG", trigger_strength=0.95)
    ctx = _setup("LONG", 0.95)
    fs = _flow_state(80000.0)

    trig_p = tmp_s17 / "trigger.json"
    ctx_p = tmp_s17 / "ctx.json"
    fs_p = tmp_s17 / "fs.json"
    trig_p.write_text(json.dumps(trig), encoding="utf-8")
    ctx_p.write_text(json.dumps(ctx), encoding="utf-8")
    fs_p.write_text(json.dumps(fs), encoding="utf-8")

    log_path = tmp_s17 / "trade_plan_history.jsonl"

    monkeypatch.setattr(eng, "SCENARIO_TRIGGER_PATH", trig_p)
    monkeypatch.setattr(eng, "SETUP_CONTEXT_PATH", ctx_p)
    monkeypatch.setattr(eng, "FLOW_STATE_PATH", fs_p)
    monkeypatch.setattr(eng, "EVIDENCE_PATH", tmp_s17 / "no_ev.json")
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", tmp_s17 / "no_pers.json")
    monkeypatch.setattr(eng, "TRADE_PLAN_PATH", tmp_s17 / "latest_trade_plan.json")
    monkeypatch.setattr(eng, "S17_STATE_PATH", tmp_s17 / "s17_state.json")
    monkeypatch.setattr(eng, "TRADE_PLAN_LOG_PATH", log_path)
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s17 / "report.md")

    run_trade_plan_engine()
    run_trade_plan_engine()
    run_trade_plan_engine()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert (tmp_s17 / "latest_trade_plan.json").exists()
    assert (tmp_s17 / "s17_state.json").exists()
    assert (tmp_s17 / "report.md").exists()
