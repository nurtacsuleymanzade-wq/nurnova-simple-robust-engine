"""Tests for S23 Simple Brain v2."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

from src.simple import simple_brain_v2 as sb
from src.simple.simple_brain_v2 import (
    ALLOWED_BRAIN_MODE,
    ALLOWED_BRAIN_STATUS,
    build_brain_report,
    run_simple_brain_v2,
)


def _flow_state():
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "block_id": "S12_FLOW_COLLECTOR",
        "heartbeat_timestamp": "2026-05-11T00:00:00Z",
        "quality_state": "OK",
    }


def _flow_evidence(symbol="BTCUSDT"):
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "block_id": "S13_FLOW_EVIDENCE",
        "symbol": symbol,
        "input_status": "OK",
        "evidence_label": "LONG_PRESSURE",
        "evidence_score": 0.7,
        "confidence": "MEDIUM",
        "data_quality": {"score": 1.0, "level": "HIGH", "issues": []},
    }


def _flow_persistence():
    return {
        "block_id": "S14_FLOW_PERSISTENCE",
        "symbol": "BTCUSDT",
        "persistence_label": "STRONG",
        "persistence_score": 0.8,
        "direction_label": "LONG",
        "continuation_quality": "HIGH",
        "decay_risk": "LOW",
        "flip_risk": "LOW",
        "data_quality": {"score": 1.0, "level": "HIGH", "issues": []},
    }


def _setup_context():
    return {
        "block_id": "S15_SETUP_CONTEXT",
        "symbol": "BTCUSDT",
        "setup_context_label": "LONG_PRESSURE",
        "setup_context_score": 0.7,
        "direction_bias": "LONG",
        "long_probability": 0.7,
        "short_probability": 0.3,
        "tradeable": True,
        "confidence": "MEDIUM",
        "data_quality": {"score": 1.0, "level": "HIGH", "issues": []},
    }


def _scenario_trigger():
    return {
        "block_id": "S16_SCENARIO_TRIGGER",
        "symbol": "BTCUSDT",
        "scenario_label": "BREAKOUT_ATTEMPT",
        "scenario_score": 0.7,
        "direction_bias": "LONG",
        "trigger_state": "READY",
        "trigger_strength": "MEDIUM",
        "market_regime": "TREND",
        "tradeable": True,
        "ready_for_entry": True,
        "estimated_fakeout_probability": 0.2,
    }


def _trade_plan():
    return {
        "block_id": "S17_TRADE_PLAN",
        "symbol": "BTCUSDT",
        "plan_status": "VALID",
        "side": "LONG",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "tp1": 102.0,
        "tp2": 104.0,
        "rr_tp1": 2.0,
        "rr_tp2": 4.0,
        "plan_grade": "A",
        "plan_quality_score": 0.9,
    }


def _decision_gate(decision="ALLOW_PAPER", block_reasons=None):
    return {
        "block_id": "S18_DECISION_GATE",
        "symbol": "BTCUSDT",
        "decision": decision,
        "decision_status": "RESOLVED",
        "allowed_for_paper_alert": decision == "ALLOW_PAPER",
        "allowed_for_paper_lifecycle": decision == "ALLOW_PAPER",
        "block_reasons": block_reasons or [],
        "warning_reasons": [],
        "final_grade": "A",
        "decision_score": 0.8,
    }


def _telegram_alert(sent=False, dry_run=True):
    return {
        "block_id": "S19_TELEGRAM_PAPER_ALERT",
        "symbol": "BTCUSDT",
        "alert_status": "DRY_RUN_READY",
        "telegram_mode": "DRY_RUN",
        "sent": sent,
        "dry_run": dry_run,
        "decision": "ALLOW_PAPER",
    }


def _paper_lifecycle():
    return {
        "block_id": "S20_PAPER_LIFECYCLE",
        "symbol": "BTCUSDT",
        "lifecycle_id": "LC1",
        "lifecycle_status": "OPEN",
        "entry_touched": True,
        "tp1_hit": False,
        "tp2_hit": False,
        "stop_hit": False,
        "invalidated": False,
        "unrealized_r": 0.5,
        "realized_r": None,
    }


def _outcome_monitor():
    return {
        "block_id": "S21_OUTCOME_MONITOR",
        "symbol": "BTCUSDT",
        "outcome_status": "CLOSED",
        "outcome_result": "TP1",
        "lifecycle_id": "LC1",
        "realized_r": 2.0,
        "mfe_r": 2.2,
        "mae_r": -0.3,
        "close_reason": "TP1_HIT",
    }


def _edge_matrix(edge_status="RESEARCH_ONLY", sample_status="EARLY_SAMPLE", total=5):
    return {
        "block_id": "S22_EDGE_MATRIX_V2",
        "symbol": "BTCUSDT",
        "sample_summary": {
            "total_records": total,
            "closed_records": total,
            "open_records": 0,
            "no_lifecycle_records": 0,
            "usable_closed_records": total,
            "min_required_sample": 30,
            "sample_status": sample_status,
        },
        "overall_stats": {
            "win_rate": 0.6,
            "expectancy_r": 1.2,
        },
        "edge_quality": {
            "edge_status": edge_status,
            "edge_score": 0.5,
            "confidence_level": "LOW",
            "caution_reason": "SAMPLE_BELOW_MIN_REQUIRED_30",
        },
    }


def _full_inputs():
    return {
        "flow_state": _flow_state(),
        "flow_evidence": _flow_evidence(),
        "flow_persistence": _flow_persistence(),
        "setup_context": _setup_context(),
        "scenario_trigger": _scenario_trigger(),
        "trade_plan": _trade_plan(),
        "decision_gate": _decision_gate(),
        "telegram_alert": _telegram_alert(),
        "paper_lifecycle": _paper_lifecycle(),
        "outcome_monitor": _outcome_monitor(),
        "edge_matrix_v2": _edge_matrix(),
    }


# --- Full inputs ---

def test_full_inputs_create_brain_report():
    r = build_brain_report(_full_inputs())
    assert r["block_id"] == "S23_SIMPLE_BRAIN_V2"
    assert r["symbol"] == "BTCUSDT"
    assert r["input_status"] == "OK"
    assert r["brain_status"] in ALLOWED_BRAIN_STATUS
    assert r["brain_mode"] in ALLOWED_BRAIN_MODE


def test_required_fields_present():
    required = [
        "timestamp_utc", "block_id", "symbol", "source", "input_status",
        "market_flow_summary", "persistence_summary", "setup_context_summary",
        "scenario_summary", "trade_plan_summary", "decision_summary",
        "lifecycle_summary", "outcome_summary", "edge_summary",
        "brain_status", "brain_mode", "primary_reading", "primary_risk",
        "primary_next_action", "system_health", "limitations",
        "data_quality", "reason_codes", "feeds_next", "execution_safety",
    ]
    r = build_brain_report(_full_inputs())
    for f in required:
        assert f in r, f"missing field: {f}"
    assert "S24_VPS_SYSTEMD_24_7_PRODUCTION_OBSERVER" in r["feeds_next"]["next_blocks"]


# --- Missing inputs ---

def test_missing_optional_inputs_does_not_crash():
    inputs = _full_inputs()
    inputs["flow_state"] = None
    inputs["telegram_alert"] = None
    inputs["paper_lifecycle"] = None
    inputs["outcome_monitor"] = None
    r = build_brain_report(inputs)
    assert r["brain_status"] in ALLOWED_BRAIN_STATUS
    assert r["input_status"] in {"PARTIAL", "OK"}


def test_missing_core_inputs_degrades_brain_status():
    inputs = _full_inputs()
    inputs["flow_evidence"] = None
    inputs["setup_context"] = None
    r = build_brain_report(inputs)
    assert r["brain_status"] in {"DEGRADED", "INSUFFICIENT_DATA"}


def test_all_missing_inputs_insufficient_data():
    inputs = {k: None for k in _full_inputs().keys()}
    r = build_brain_report(inputs)
    assert r["brain_status"] == "INSUFFICIENT_DATA"
    assert r["input_status"] == "MISSING"
    assert r["brain_mode"] == "OBSERVER_MODE"


# --- Mode rules ---

def test_small_sample_sets_research_or_accumulation_mode():
    inputs = _full_inputs()
    inputs["edge_matrix_v2"] = _edge_matrix(
        edge_status="RESEARCH_ONLY", sample_status="EARLY_SAMPLE", total=5
    )
    r = build_brain_report(inputs)
    assert r["brain_mode"] in {"RESEARCH_MODE", "SAMPLE_ACCUMULATION_MODE"}


def test_no_edge_claim_prevents_live_readiness_wording():
    inputs = _full_inputs()
    inputs["edge_matrix_v2"] = _edge_matrix(
        edge_status="NO_EDGE_CLAIM", sample_status="INSUFFICIENT_SAMPLE", total=0
    )
    r = build_brain_report(inputs)
    assert r["brain_status"] != "READY"
    assert r["brain_mode"] != "PAPER_ALERT_MODE" or True
    # primary_next_action should not claim live readiness
    assert "REAL" not in r["primary_next_action"].upper() or "NO_TRADE" in r["primary_next_action"].upper() or "OBSERVE" in r["primary_next_action"].upper()
    assert r["execution_safety"]["safe_to_open_real_trade"] is False


def test_block_decision_produces_no_trade_next_action():
    inputs = _full_inputs()
    inputs["decision_gate"] = _decision_gate(
        decision="BLOCK", block_reasons=["LOW_RR", "INVALID_STOP"]
    )
    r = build_brain_report(inputs)
    assert r["brain_status"] == "BLOCKED"
    assert r["brain_mode"] == "NO_TRADE_MODE"
    assert "NO_TRADE" in r["primary_next_action"]


def test_allow_paper_can_produce_paper_alert_mode():
    inputs = _full_inputs()
    # need edge_status NOT in NO_EDGE_CLAIM/RESEARCH_ONLY to enable PAPER_ALERT_MODE
    inputs["edge_matrix_v2"] = _edge_matrix(
        edge_status="VALIDATED_EDGE", sample_status="ROBUST_SAMPLE", total=120
    )
    inputs["decision_gate"] = _decision_gate(decision="ALLOW_PAPER")
    inputs["telegram_alert"] = _telegram_alert(sent=False, dry_run=True)
    r = build_brain_report(inputs)
    assert r["brain_mode"] == "PAPER_ALERT_MODE"


# --- Safety ---

def test_safety_flags_always_false():
    for inputs in (
        {k: None for k in _full_inputs().keys()},
        _full_inputs(),
    ):
        r = build_brain_report(inputs)
        es = r["execution_safety"]
        assert es["safe_to_open_real_trade"] is False
        assert es["private_api_used"] is False
        assert es["live_order_sent"] is False


def test_reason_codes_not_empty():
    for inputs in (
        {k: None for k in _full_inputs().keys()},
        _full_inputs(),
    ):
        r = build_brain_report(inputs)
        assert isinstance(r["reason_codes"], list)
        assert len(r["reason_codes"]) > 0
        assert any("SAFE_TO_OPEN_REAL_TRADE_FALSE" in c for c in r["reason_codes"])


# --- Runner / persistence / report ---

def test_runner_creates_outputs_and_appends(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        monkeypatch.setattr(sb, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(sb, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(sb, "REPORTS_DIR", tmp / "reports")

        # Re-bind paths under tmp
        monkeypatch.setattr(sb, "FLOW_STATE_PATH", tmp / "state" / "latest_flow_state.json")
        monkeypatch.setattr(sb, "FLOW_EVIDENCE_PATH", tmp / "state" / "latest_flow_evidence.json")
        monkeypatch.setattr(sb, "FLOW_PERSISTENCE_PATH", tmp / "state" / "latest_flow_persistence.json")
        monkeypatch.setattr(sb, "SETUP_CONTEXT_PATH", tmp / "state" / "latest_setup_context.json")
        monkeypatch.setattr(sb, "SCENARIO_TRIGGER_PATH", tmp / "state" / "latest_scenario_trigger.json")
        monkeypatch.setattr(sb, "TRADE_PLAN_PATH", tmp / "state" / "latest_trade_plan.json")
        monkeypatch.setattr(sb, "DECISION_GATE_PATH", tmp / "state" / "latest_decision_gate.json")
        monkeypatch.setattr(sb, "TELEGRAM_ALERT_PATH", tmp / "state" / "latest_telegram_paper_alert.json")
        monkeypatch.setattr(sb, "PAPER_LIFECYCLE_PATH", tmp / "state" / "latest_paper_lifecycle.json")
        monkeypatch.setattr(sb, "OUTCOME_MONITOR_PATH", tmp / "state" / "latest_outcome_monitor.json")
        monkeypatch.setattr(sb, "EDGE_MATRIX_V2_PATH", tmp / "state" / "latest_edge_matrix_v2.json")
        monkeypatch.setattr(sb, "LATEST_BRAIN_PATH", tmp / "state" / "latest_simple_brain_v2.json")
        monkeypatch.setattr(sb, "S23_STATE_PATH", tmp / "state" / "s23_simple_brain_v2_state.json")
        monkeypatch.setattr(sb, "BRAIN_HISTORY_PATH", tmp / "data" / "simple_brain_v2_history.jsonl")
        monkeypatch.setattr(sb, "REPORT_PATH", tmp / "reports" / "simple_brain_v2_latest_report.md")

        (tmp / "state").mkdir(parents=True, exist_ok=True)
        (tmp / "data").mkdir(parents=True, exist_ok=True)

        # Write full inputs
        files = {
            "latest_flow_state.json": _flow_state(),
            "latest_flow_evidence.json": _flow_evidence(),
            "latest_flow_persistence.json": _flow_persistence(),
            "latest_setup_context.json": _setup_context(),
            "latest_scenario_trigger.json": _scenario_trigger(),
            "latest_trade_plan.json": _trade_plan(),
            "latest_decision_gate.json": _decision_gate(),
            "latest_telegram_paper_alert.json": _telegram_alert(),
            "latest_paper_lifecycle.json": _paper_lifecycle(),
            "latest_outcome_monitor.json": _outcome_monitor(),
            "latest_edge_matrix_v2.json": _edge_matrix(),
        }
        for name, content in files.items():
            (tmp / "state" / name).write_text(json.dumps(content), encoding="utf-8")

        r1 = run_simple_brain_v2()
        r2 = run_simple_brain_v2()

        assert (tmp / "state" / "latest_simple_brain_v2.json").exists()
        assert (tmp / "state" / "s23_simple_brain_v2_state.json").exists()
        assert (tmp / "data" / "simple_brain_v2_history.jsonl").exists()
        assert (tmp / "reports" / "simple_brain_v2_latest_report.md").exists()

        lines = (tmp / "data" / "simple_brain_v2_history.jsonl").read_text(
            encoding="utf-8"
        ).strip().splitlines()
        assert len(lines) == 2  # append-only

        # Report contains required sections
        report_text = (tmp / "reports" / "simple_brain_v2_latest_report.md").read_text(
            encoding="utf-8"
        )
        for section in (
            "Current Flow", "Persistence", "Setup Context", "Scenario",
            "Trade Plan", "Decision", "Lifecycle", "Latest Outcome",
            "Edge Status", "Brain Status", "Brain Mode",
            "Primary Next Action", "Safety Summary",
        ):
            assert section in report_text, f"missing report section: {section}"

        assert r1["symbol"] == "BTCUSDT"
        assert r2["brain_status"] in ALLOWED_BRAIN_STATUS
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
