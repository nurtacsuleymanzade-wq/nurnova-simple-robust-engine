"""Tests for S21 Outcome Monitor."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

from src.simple import outcome_monitor as om
from src.simple.outcome_monitor import (
    ALLOWED_OUTCOME_RESULT,
    ALLOWED_OUTCOME_STATUS,
    compute_outcome,
    run_outcome_monitor,
)


def _lifecycle(
    status="ACTIVE",
    side="LONG",
    entry=100.0,
    sl=95.0,
    tp1=110.0,
    tp2=120.0,
    current=101.0,
    tp1_hit=False,
    tp2_hit=False,
    stop_hit=False,
    invalidated=False,
    realized_r=None,
    mfe=0.2,
    mae=-0.4,
    lifecycle_id="lc-001",
):
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "block_id": "S20_PAPER_LIFECYCLE_TRACKER",
        "symbol": "BTCUSDT",
        "source": "S18_DECISION_GATE",
        "input_status": "OK",
        "lifecycle_id": lifecycle_id,
        "lifecycle_status": status,
        "side": side,
        "entry_price": entry,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "current_price": current,
        "entry_touched": True,
        "tp1_hit": tp1_hit,
        "tp2_hit": tp2_hit,
        "stop_hit": stop_hit,
        "invalidated": invalidated,
        "unrealized_r": 0.0,
        "realized_r": realized_r,
        "max_favorable_excursion_r": mfe,
        "max_adverse_excursion_r": mae,
        "lifecycle_events": [],
        "data_quality": {"score": 0.9, "level": "HIGH", "issues": []},
        "reason_codes": ["SYMBOL_BTCUSDT"],
        "feeds_next": {"next_blocks": ["S21_OUTCOME_MONITOR"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def _no_lc():
    lc = _lifecycle(status="NO_LIFECYCLE", lifecycle_id=None)
    lc["lifecycle_id"] = None
    return lc


def _setup():
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "setup_context_label": "LONG_PRESSURE",
        "setup_context_score": 7.5,
        "direction_bias": "LONG",
        "long_probability": 0.7,
        "short_probability": 0.3,
        "confidence": 0.65,
        "tradeable": True,
        "context_reason": "test",
    }


def _scenario():
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "scenario_label": "BREAKOUT_ATTEMPT",
        "scenario_score": 8.0,
        "direction_bias": "LONG",
        "trigger_state": "STRONG_TRIGGER",
        "trigger_strength": 0.75,
        "trigger_confidence": 0.6,
        "estimated_move_probability": 0.6,
        "estimated_failure_probability": 0.25,
        "estimated_fakeout_probability": 0.15,
        "market_regime": "TRENDING",
        "tradeable": True,
        "ready_for_entry": True,
    }


def _gate():
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "decision": "ALLOW_PAPER",
        "decision_status": "OK",
        "allowed_for_paper_alert": True,
        "allowed_for_paper_lifecycle": True,
        "decision_score": 0.85,
        "final_grade": "A",
        "selected_side": "LONG",
        "selected_entry": 100.0,
        "selected_stop_loss": 95.0,
        "selected_tp1": 110.0,
        "selected_tp2": 120.0,
        "selected_rr_tp1": 2.0,
        "selected_rr_tp2": 4.0,
    }


def _plan():
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "plan_status": "READY",
        "side": "LONG",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "tp1": 110.0,
        "tp2": 120.0,
        "rr_tp1": 2.0,
        "rr_tp2": 4.0,
        "invalidation_price": 95.0,
        "plan_quality_score": 0.8,
        "plan_grade": "A",
    }


# --- Outcome mapping ---

def test_tp1_outcome():
    lc = _lifecycle(status="TP1_HIT", tp1_hit=True, current=111.0, realized_r=2.0)
    r = compute_outcome(lc, _plan(), _gate(), _setup(), _scenario())
    assert r["outcome_result"] == "TP1"
    assert r["outcome_status"] == "OPEN"
    assert r["realized_r"] == 2.0


def test_tp2_outcome():
    lc = _lifecycle(status="TP2_HIT", tp1_hit=True, tp2_hit=True, current=121.0, realized_r=4.0)
    r = compute_outcome(lc, _plan(), _gate(), _setup(), _scenario())
    assert r["outcome_result"] == "TP2"
    assert r["outcome_status"] == "CLOSED"
    assert r["realized_r"] == 4.0


def test_sl_outcome():
    lc = _lifecycle(status="SL_HIT", stop_hit=True, current=94.0, realized_r=-1.0)
    r = compute_outcome(lc, _plan(), _gate(), _setup(), _scenario())
    assert r["outcome_result"] == "SL"
    assert r["outcome_status"] == "CLOSED"
    assert r["realized_r"] == -1.0


def test_invalidated_outcome():
    lc = _lifecycle(status="INVALIDATED", invalidated=True, current=94.5)
    r = compute_outcome(lc, _plan(), _gate(), _setup(), _scenario())
    assert r["outcome_result"] == "INVALIDATED"
    assert r["outcome_status"] == "CLOSED"


def test_still_open_outcome():
    lc = _lifecycle(status="ACTIVE", current=101.0)
    r = compute_outcome(lc, _plan(), _gate(), _setup(), _scenario())
    assert r["outcome_result"] == "STILL_OPEN"
    assert r["outcome_status"] == "OPEN"


def test_no_lifecycle_outcome():
    r = compute_outcome(_no_lc(), _plan(), _gate(), _setup(), _scenario())
    assert r["outcome_result"] == "NO_LIFECYCLE"
    assert r["outcome_status"] == "NO_OUTCOME"


def test_missing_lifecycle_input_yields_no_outcome():
    r = compute_outcome(None, _plan(), _gate(), _setup(), _scenario())
    assert r["outcome_result"] == "NO_LIFECYCLE"
    assert r["outcome_status"] == "NO_OUTCOME"


# --- No TIMEOUT class ---

def test_no_timeout_result_class():
    assert "TIMEOUT" not in ALLOWED_OUTCOME_RESULT
    assert "TIMEOUT" not in ALLOWED_OUTCOME_STATUS
    samples = [
        compute_outcome(_lifecycle(status="ACTIVE"), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="TP1_HIT", tp1_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="TP2_HIT", tp1_hit=True, tp2_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="SL_HIT", stop_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="INVALIDATED", invalidated=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_no_lc(), _plan(), _gate(), _setup(), _scenario()),
    ]
    for r in samples:
        assert r["outcome_result"] != "TIMEOUT"
        assert r["close_reason"] != "TIMEOUT"


# --- Snapshots preserved ---

def test_snapshots_preserved():
    lc = _lifecycle(status="TP2_HIT", tp1_hit=True, tp2_hit=True, current=121.0)
    r = compute_outcome(lc, _plan(), _gate(), _setup(), _scenario())
    assert r["setup_context_snapshot"]["setup_context_label"] == "LONG_PRESSURE"
    assert r["scenario_trigger_snapshot"]["scenario_label"] == "BREAKOUT_ATTEMPT"
    assert r["decision_snapshot"]["decision"] == "ALLOW_PAPER"
    assert r["trade_plan_snapshot"]["plan_status"] == "READY"


# --- realized_r / mfe_r / mae_r ---

def test_r_metrics_copied_or_calculated_safely():
    # lifecycle provides realized_r
    lc1 = _lifecycle(status="SL_HIT", stop_hit=True, realized_r=-1.0, mfe=0.3, mae=-1.0)
    r1 = compute_outcome(lc1, _plan(), _gate(), _setup(), _scenario())
    assert r1["realized_r"] == -1.0
    assert r1["mfe_r"] == 0.3
    assert r1["mae_r"] == -1.0

    # lifecycle missing realized_r for TP2 — compute safely
    lc2 = _lifecycle(status="TP2_HIT", tp1_hit=True, tp2_hit=True, realized_r=None, mfe=4.0, mae=0.0)
    r2 = compute_outcome(lc2, _plan(), _gate(), _setup(), _scenario())
    assert r2["realized_r"] == 4.0  # (120-100)/5

    # still open -> realized_r None
    lc3 = _lifecycle(status="ACTIVE")
    r3 = compute_outcome(lc3, _plan(), _gate(), _setup(), _scenario())
    assert r3["realized_r"] is None


# --- reason_codes ---

def test_reason_codes_not_empty():
    samples = [
        compute_outcome(_lifecycle(status="ACTIVE"), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_no_lc(), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(None, None, None, None, None),
    ]
    for r in samples:
        assert isinstance(r["reason_codes"], list)
        assert len(r["reason_codes"]) > 0
        assert any("SAFE_TO_OPEN_REAL_TRADE_FALSE" in c for c in r["reason_codes"])


# --- Safety always false ---

def test_safety_flags_always_false():
    samples = [
        compute_outcome(_lifecycle(status="TP2_HIT", tp1_hit=True, tp2_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="SL_HIT", stop_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_no_lc(), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(None, None, None, None, None),
    ]
    for r in samples:
        es = r["execution_safety"]
        assert es["safe_to_open_real_trade"] is False
        assert es["private_api_used"] is False
        assert es["live_order_sent"] is False


# --- Contract fields ---

_REQUIRED = [
    "timestamp_utc", "block_id", "symbol", "source", "input_status",
    "outcome_status", "outcome_result", "lifecycle_id", "side",
    "entry_price", "stop_loss", "tp1", "tp2", "final_price",
    "realized_r", "mfe_r", "mae_r", "close_reason",
    "setup_context_snapshot", "scenario_trigger_snapshot",
    "decision_snapshot", "trade_plan_snapshot", "outcome_reason",
    "data_quality", "reason_codes", "feeds_next", "execution_safety",
]


def test_all_required_fields_present():
    r = compute_outcome(_lifecycle(status="ACTIVE"), _plan(), _gate(), _setup(), _scenario())
    for f in _REQUIRED:
        assert f in r, f"missing field: {f}"
    assert r["block_id"] == "S21_OUTCOME_MONITOR"
    assert "S22_EDGE_MATRIX_V2" in r["feeds_next"]["next_blocks"]


def test_outcome_status_and_result_always_allowed():
    samples = [
        compute_outcome(_lifecycle(status="ACTIVE"), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="TP1_HIT", tp1_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="TP2_HIT", tp1_hit=True, tp2_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="SL_HIT", stop_hit=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_lifecycle(status="INVALIDATED", invalidated=True), _plan(), _gate(), _setup(), _scenario()),
        compute_outcome(_no_lc(), _plan(), _gate(), _setup(), _scenario()),
    ]
    for r in samples:
        assert r["outcome_status"] in ALLOWED_OUTCOME_STATUS
        assert r["outcome_result"] in ALLOWED_OUTCOME_RESULT


# --- Append-only persistence ---

def test_runner_creates_outputs_and_appends(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        monkeypatch.setattr(om, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(om, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(om, "REPORTS_DIR", tmp / "reports")
        monkeypatch.setattr(om, "LIFECYCLE_PATH", tmp / "state" / "latest_paper_lifecycle.json")
        monkeypatch.setattr(om, "TRADE_PLAN_PATH", tmp / "state" / "latest_trade_plan.json")
        monkeypatch.setattr(om, "DECISION_GATE_PATH", tmp / "state" / "latest_decision_gate.json")
        monkeypatch.setattr(om, "SETUP_CONTEXT_PATH", tmp / "state" / "latest_setup_context.json")
        monkeypatch.setattr(om, "SCENARIO_TRIGGER_PATH", tmp / "state" / "latest_scenario_trigger.json")
        monkeypatch.setattr(om, "OUTCOME_PATH", tmp / "state" / "latest_outcome_monitor.json")
        monkeypatch.setattr(om, "S21_STATE_PATH", tmp / "state" / "s21_outcome_monitor_state.json")
        monkeypatch.setattr(om, "HISTORY_PATH", tmp / "data" / "outcome_monitor_history.jsonl")
        monkeypatch.setattr(om, "REPORT_PATH", tmp / "reports" / "s21_outcome_monitor_latest_report.md")

        (tmp / "state").mkdir(parents=True, exist_ok=True)
        (tmp / "state" / "latest_paper_lifecycle.json").write_text(
            json.dumps(_lifecycle(status="TP2_HIT", tp1_hit=True, tp2_hit=True, current=121.0))
        )
        (tmp / "state" / "latest_trade_plan.json").write_text(json.dumps(_plan()))
        (tmp / "state" / "latest_decision_gate.json").write_text(json.dumps(_gate()))
        (tmp / "state" / "latest_setup_context.json").write_text(json.dumps(_setup()))
        (tmp / "state" / "latest_scenario_trigger.json").write_text(json.dumps(_scenario()))

        r1 = run_outcome_monitor()
        r2 = run_outcome_monitor()

        assert (tmp / "state" / "latest_outcome_monitor.json").exists()
        assert (tmp / "state" / "s21_outcome_monitor_state.json").exists()
        assert (tmp / "data" / "outcome_monitor_history.jsonl").exists()
        assert (tmp / "reports" / "s21_outcome_monitor_latest_report.md").exists()

        lines = (tmp / "data" / "outcome_monitor_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # append-only

        assert r1["outcome_result"] == "TP2"
        assert r2["outcome_status"] == "CLOSED"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
