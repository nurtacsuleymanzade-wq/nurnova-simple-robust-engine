"""Tests for S20 Paper Lifecycle Tracker."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple import paper_lifecycle_tracker as plt
from src.simple.paper_lifecycle_tracker import (
    ALLOWED_LIFECYCLE_STATUS,
    compute_paper_lifecycle,
    run_paper_lifecycle_tracker,
)


def _gate(decision="ALLOW_PAPER", side="LONG", entry=100.0, sl=95.0, tp1=110.0, tp2=120.0):
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "block_id": "S18_DECISION_GATE",
        "symbol": "BTCUSDT",
        "decision": decision,
        "selected_side": side,
        "selected_entry": entry,
        "selected_stop_loss": sl,
        "selected_tp1": tp1,
        "selected_tp2": tp2,
        "data_quality": {"level": "OK", "score": 1.0},
    }


def _plan(side="LONG", entry=100.0, sl=95.0, tp1=110.0, tp2=120.0):
    return {
        "side": side,
        "entry_price": entry,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "invalidation_price": sl,
    }


def _alert(status="DRY_RUN_READY"):
    return {
        "block_id": "S19_TELEGRAM_PAPER_ALERT",
        "symbol": "BTCUSDT",
        "alert_status": status,
    }


def _flow(price=None):
    if price is None:
        return {"latest_bucket": {}}
    return {"latest_bucket": {"last_price": price}}


# --- Lifecycle creation ---

def test_creates_long_lifecycle_from_allowed_alert():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(101.0))
    assert r["lifecycle_status"] in ("ACTIVE", "TP1_HIT")
    assert r["side"] == "LONG"
    assert r["lifecycle_id"] is not None


def test_creates_short_lifecycle_from_allowed_alert():
    gate = _gate(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0)
    r = compute_paper_lifecycle(gate, _plan(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0), _alert(), _flow(99.0))
    assert r["side"] == "SHORT"
    assert r["lifecycle_status"] in ("ACTIVE", "TP1_HIT")


def test_no_lifecycle_when_decision_block():
    r = compute_paper_lifecycle(_gate(decision="BLOCK"), _plan(), _alert("BLOCKED"), _flow(101.0))
    assert r["lifecycle_status"] == "NO_LIFECYCLE"
    assert r["lifecycle_id"] is None


def test_no_lifecycle_when_alert_skipped():
    r = compute_paper_lifecycle(_gate(decision="WATCH"), _plan(), _alert("SKIPPED"), _flow(101.0))
    assert r["lifecycle_status"] == "NO_LIFECYCLE"


# --- LONG TP/SL ---

def test_long_tp1_hit():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(111.0))
    assert r["tp1_hit"] is True
    assert r["tp2_hit"] is False
    assert r["lifecycle_status"] == "TP1_HIT"
    assert r["realized_r"] == 2.0  # (110-100)/5


def test_long_tp2_hit():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(121.0))
    assert r["tp1_hit"] is True
    assert r["tp2_hit"] is True
    assert r["lifecycle_status"] == "TP2_HIT"


def test_long_sl_hit():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(94.0))
    assert r["stop_hit"] is True
    assert r["lifecycle_status"] == "SL_HIT"
    assert r["realized_r"] == -1.0


# --- SHORT TP/SL ---

def test_short_tp1_hit():
    gate = _gate(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0)
    r = compute_paper_lifecycle(gate, _plan(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0), _alert(), _flow(89.0))
    assert r["tp1_hit"] is True
    assert r["tp2_hit"] is False
    assert r["lifecycle_status"] == "TP1_HIT"


def test_short_tp2_hit():
    gate = _gate(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0)
    r = compute_paper_lifecycle(gate, _plan(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0), _alert(), _flow(79.0))
    assert r["tp2_hit"] is True
    assert r["lifecycle_status"] == "TP2_HIT"


def test_short_sl_hit():
    gate = _gate(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0)
    r = compute_paper_lifecycle(gate, _plan(side="SHORT", entry=100.0, sl=105.0, tp1=90.0, tp2=80.0), _alert(), _flow(106.0))
    assert r["stop_hit"] is True
    assert r["lifecycle_status"] == "SL_HIT"


# --- MFE / MAE ---

def test_mfe_mae_r_calculation():
    # Long: entry=100, sl=95, risk=5
    # Run 1: price=103 -> unrealized_r = +0.6
    r1 = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(103.0))
    assert r1["unrealized_r"] == 0.6
    assert r1["max_favorable_excursion_r"] == 0.6
    assert r1["max_adverse_excursion_r"] == 0.0

    # Run 2: price=96 (drawdown) -> mae should go to -0.8
    r2 = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(96.0), prior=r1)
    assert r2["unrealized_r"] == -0.8
    assert r2["max_favorable_excursion_r"] == 0.6  # carried over
    assert r2["max_adverse_excursion_r"] == -0.8


# --- Missing price degrades safely ---

def test_missing_price_degrades_safely():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(None))
    assert r["lifecycle_status"] in ("NOT_STARTED", "NO_LIFECYCLE")
    assert r["data_quality"]["level"] in ("DEGRADED", "MISSING")
    assert r["current_price"] is None


def test_missing_flow_state_does_not_crash():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), None)
    assert r["lifecycle_status"] in ("NOT_STARTED", "NO_LIFECYCLE")


# --- Lifecycle events ---

def test_lifecycle_events_not_empty_when_created():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(101.0))
    assert len(r["lifecycle_events"]) >= 1
    assert any(e.get("event") == "LIFECYCLE_CREATED" for e in r["lifecycle_events"])


def test_lifecycle_events_record_status_change():
    r1 = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(101.0))
    r2 = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(111.0), prior=r1)
    assert any(e.get("event") == "TP1_HIT" for e in r2["lifecycle_events"])
    assert any(e.get("event") == "STATUS_CHANGED" for e in r2["lifecycle_events"])


# --- Safety always false ---

def test_safety_flags_always_false():
    samples = [
        compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(101.0)),
        compute_paper_lifecycle(_gate(decision="BLOCK"), _plan(), _alert(), _flow(101.0)),
        compute_paper_lifecycle(None, None, None, None),
        compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(None)),
    ]
    for r in samples:
        es = r["execution_safety"]
        assert es["safe_to_open_real_trade"] is False
        assert es["private_api_used"] is False
        assert es["live_order_sent"] is False


# --- Contract fields ---

_REQUIRED = [
    "timestamp_utc", "block_id", "symbol", "source", "input_status",
    "lifecycle_id", "lifecycle_status", "side", "entry_price", "stop_loss",
    "tp1", "tp2", "current_price", "entry_touched", "tp1_hit", "tp2_hit",
    "stop_hit", "invalidated", "unrealized_r", "realized_r",
    "max_favorable_excursion_r", "max_adverse_excursion_r",
    "lifecycle_events", "data_quality", "reason_codes", "feeds_next",
    "execution_safety",
]


def test_all_required_fields_present():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(101.0))
    for f in _REQUIRED:
        assert f in r, f"missing field: {f}"
    assert r["block_id"] == "S20_PAPER_LIFECYCLE_TRACKER"
    assert "S21_OUTCOME_MONITOR" in r["feeds_next"]["next_blocks"]


def test_lifecycle_status_always_allowed():
    samples = [
        compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(101.0)),
        compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(111.0)),
        compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(121.0)),
        compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(94.0)),
        compute_paper_lifecycle(_gate(decision="BLOCK"), _plan(), _alert("BLOCKED"), _flow(101.0)),
        compute_paper_lifecycle(_gate(), _plan(), _alert(), None),
    ]
    for r in samples:
        assert r["lifecycle_status"] in ALLOWED_LIFECYCLE_STATUS


def test_reason_codes_not_empty():
    r = compute_paper_lifecycle(_gate(), _plan(), _alert(), _flow(101.0))
    assert isinstance(r["reason_codes"], list) and len(r["reason_codes"]) > 0
    assert any("SAFE_TO_OPEN_REAL_TRADE_FALSE" in c for c in r["reason_codes"])


# --- Append-only persistence ---

def test_runner_creates_outputs_and_appends(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        monkeypatch.setattr(plt, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(plt, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(plt, "REPORTS_DIR", tmp / "reports")
        monkeypatch.setattr(plt, "DECISION_GATE_PATH", tmp / "state" / "latest_decision_gate.json")
        monkeypatch.setattr(plt, "TRADE_PLAN_PATH", tmp / "state" / "latest_trade_plan.json")
        monkeypatch.setattr(plt, "ALERT_PATH", tmp / "state" / "latest_telegram_paper_alert.json")
        monkeypatch.setattr(plt, "FLOW_STATE_PATH", tmp / "state" / "latest_flow_state.json")
        monkeypatch.setattr(plt, "LIFECYCLE_PATH", tmp / "state" / "latest_paper_lifecycle.json")
        monkeypatch.setattr(plt, "S20_STATE_PATH", tmp / "state" / "s20_paper_lifecycle_state.json")
        monkeypatch.setattr(plt, "HISTORY_PATH", tmp / "data" / "paper_lifecycle_history.jsonl")
        monkeypatch.setattr(plt, "REPORT_PATH", tmp / "reports" / "s20_paper_lifecycle_latest_report.md")

        (tmp / "state").mkdir(parents=True, exist_ok=True)
        (tmp / "state" / "latest_decision_gate.json").write_text(json.dumps(_gate()))
        (tmp / "state" / "latest_trade_plan.json").write_text(json.dumps(_plan()))
        (tmp / "state" / "latest_telegram_paper_alert.json").write_text(json.dumps(_alert()))
        (tmp / "state" / "latest_flow_state.json").write_text(json.dumps(_flow(101.0)))

        r1 = run_paper_lifecycle_tracker()
        r2 = run_paper_lifecycle_tracker()

        assert (tmp / "state" / "latest_paper_lifecycle.json").exists()
        assert (tmp / "state" / "s20_paper_lifecycle_state.json").exists()
        assert (tmp / "data" / "paper_lifecycle_history.jsonl").exists()
        assert (tmp / "reports" / "s20_paper_lifecycle_latest_report.md").exists()

        lines = (tmp / "data" / "paper_lifecycle_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # append-only

        # lifecycle_id stable across runs
        assert r1["lifecycle_id"] == r2["lifecycle_id"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
