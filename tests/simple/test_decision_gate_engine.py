"""Tests for S18 Decision Gate Engine."""

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.decision_gate_engine import (
    compute_decision_gate,
    no_valid_output,
    run_decision_gate_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_s18():
    d = TMP_BASE / f"s18_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _plan(
    side: str = "LONG",
    plan_status: str = "VALID",
    entry: float = 80000.0,
    sl: float | None = None,
    tp1: float | None = None,
    tp2: float | None = None,
    rr1: float = 1.6,
    rr2: float = 2.0,
    dq_level: str = "OK",
    dq_score: float = 1.0,
    safe: bool = True,
    reasons: list[str] | None = None,
) -> dict:
    if sl is None or tp1 is None or tp2 is None:
        if side == "LONG":
            sl = entry * 0.995
            tp1 = entry * 1.006
            tp2 = entry * 1.010
        elif side == "SHORT":
            sl = entry * 1.005
            tp1 = entry * 0.994
            tp2 = entry * 0.990
        else:
            sl = entry
            tp1 = entry
            tp2 = entry
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S17_TRADE_PLAN_ENGINE",
        "symbol": "BTCUSDT",
        "plan_status": plan_status,
        "side": side,
        "entry_price": entry,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr_tp1": rr1,
        "rr_tp2": rr2,
        "data_quality": {"level": dq_level, "score": dq_score},
        "reason_codes": reasons if reasons is not None else ["SAMPLE_REASON"],
        "execution_safety": {
            "safe_to_open_real_trade": not safe,
            "private_api_used": not safe,
            "live_order_sent": not safe,
        },
    }


def _trig(ready: bool = True, state: str = "READY_FOR_ENTRY", strength: float = 0.85) -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S16_SCENARIO_ENTRY_TRIGGER",
        "symbol": "BTCUSDT",
        "ready_for_entry": ready,
        "trigger_state": state,
        "trigger_strength": strength,
    }


# --- Test 1: allow valid LONG paper decision ---

def test_allow_valid_long_paper():
    r = compute_decision_gate(_plan("LONG"), _trig(), None, None, None, None)
    assert r["decision"] == "ALLOW_PAPER"
    assert r["decision_status"] == "PASSED"
    assert r["allowed_for_paper_alert"] is True
    assert r["allowed_for_paper_lifecycle"] is True
    assert r["selected_side"] == "LONG"


# --- Test 2: allow valid SHORT paper decision ---

def test_allow_valid_short_paper():
    r = compute_decision_gate(_plan("SHORT"), _trig(), None, None, None, None)
    assert r["decision"] == "ALLOW_PAPER"
    assert r["selected_side"] == "SHORT"
    assert r["selected_stop_loss"] > r["selected_entry"]
    assert r["selected_tp1"] < r["selected_entry"]


# --- Test 3: watch low RR ---

def test_watch_low_rr():
    r = compute_decision_gate(
        _plan("LONG", rr1=0.5, rr2=1.0), _trig(), None, None, None, None
    )
    assert r["decision"] == "WATCH_ONLY"
    assert r["decision_status"] == "WATCH_ONLY"
    assert "RR_BELOW_THRESHOLD" in r["warning_reasons"]


# --- Test 4: block invalid price logic ---

def test_block_invalid_price_logic():
    # LONG but stop above entry → contradiction
    bad = _plan("LONG", entry=80000.0, sl=80500.0, tp1=80800.0, tp2=81000.0)
    r = compute_decision_gate(bad, _trig(), None, None, None, None)
    assert r["decision"] == "BLOCK"
    assert "PRICE_LOGIC_CONTRADICTION" in r["block_reasons"]


# --- Test 5: block missing trade plan ---

def test_block_missing_trade_plan():
    r = compute_decision_gate(None, _trig(), None, None, None, None)
    assert r["decision"] == "BLOCK"
    assert r["decision_status"] == "INVALID"
    assert "TRADE_PLAN_MISSING" in r["block_reasons"]


# --- Test 6: block degraded data ---

def test_block_degraded_data():
    r = compute_decision_gate(
        _plan("LONG", dq_level="MISSING", dq_score=0.0), _trig(), None, None, None, None
    )
    assert r["decision"] == "BLOCK"
    assert any("DATA_QUALITY_INVALID" in br for br in r["block_reasons"])


def test_watch_low_dq():
    r = compute_decision_gate(
        _plan("LONG", dq_level="LOW", dq_score=0.4), _trig(), None, None, None, None
    )
    assert r["decision"] in ("WATCH_ONLY", "BLOCK")
    assert "DATA_QUALITY_LOW" in r["warning_reasons"]


# --- Test 7: block unsafe flags ---

def test_block_unsafe_flags():
    r = compute_decision_gate(
        _plan("LONG", safe=False), _trig(), None, None, None, None
    )
    assert r["decision"] == "BLOCK"
    assert "UNSAFE_FLAGS_DETECTED" in r["block_reasons"]


# --- Test 8: gate_checks all present ---

def test_gate_checks_all_present():
    required = {
        "input_available", "plan_ready", "side_valid", "price_logic_valid",
        "rr_valid", "rr_threshold_valid", "data_quality_valid",
        "trigger_ready", "safety_valid", "reasons_present",
    }
    r = compute_decision_gate(_plan("LONG"), _trig(), None, None, None, None)
    assert required <= set(r["gate_checks"].keys())
    missing = no_valid_output("TEST")
    assert required <= set(missing["gate_checks"].keys())


# --- Test 9: reason_codes not empty ---

def test_reason_codes_not_empty():
    r = compute_decision_gate(_plan("LONG"), _trig(), None, None, None, None)
    assert len(r["reason_codes"]) > 0
    missing = no_valid_output("TEST")
    assert len(missing["reason_codes"]) > 0


# --- Test 10: safety flags always false ---

def test_safety_flags_always_false():
    cases = [
        (_plan("LONG"), _trig()),
        (_plan("SHORT"), _trig()),
        (_plan("LONG", plan_status="INVALID"), _trig()),
        (None, None),
    ]
    for plan, trig in cases:
        r = compute_decision_gate(plan, trig, None, None, None, None)
        s = r["execution_safety"]
        assert s["safe_to_open_real_trade"] is False
        assert s["private_api_used"] is False
        assert s["live_order_sent"] is False
    m = no_valid_output("X")["execution_safety"]
    assert m["safe_to_open_real_trade"] is False
    assert m["private_api_used"] is False
    assert m["live_order_sent"] is False


# --- Test 11: feeds_next includes S19 ---

def test_feeds_next_includes_s19():
    r = compute_decision_gate(_plan("LONG"), _trig(), None, None, None, None)
    assert "S19_TELEGRAM_PAPER_ALERT" in r["feeds_next"]["next_blocks"]
    assert "S19_TELEGRAM_PAPER_ALERT" in no_valid_output("X")["feeds_next"]["next_blocks"]


# --- Test 12: required output fields ---

def test_required_output_fields():
    r = compute_decision_gate(_plan("LONG"), _trig(), None, None, None, None)
    required = {
        "timestamp_utc", "block_id", "symbol", "source", "input_status",
        "decision", "decision_status", "allowed_for_paper_alert",
        "allowed_for_paper_lifecycle", "block_reasons", "warning_reasons",
        "decision_score", "final_grade", "selected_side", "selected_entry",
        "selected_stop_loss", "selected_tp1", "selected_tp2",
        "selected_rr_tp1", "selected_rr_tp2", "gate_checks", "data_quality",
        "reason_codes", "feeds_next", "execution_safety",
    }
    assert required <= set(r.keys())


# --- Test 13: trigger not ready blocks ALLOW_PAPER ---

def test_trigger_not_ready_watch():
    r = compute_decision_gate(
        _plan("LONG"), _trig(ready=False, state="WAIT_FOR_CONFIRMATION"),
        None, None, None, None,
    )
    assert r["decision"] in ("WATCH_ONLY", "BLOCK")
    assert any("TRIGGER_NOT_READY" in w for w in r["warning_reasons"])


# --- Test 14: plan not ready (WATCH_ONLY) → WATCH ---

def test_plan_not_ready_watch():
    r = compute_decision_gate(
        _plan("LONG", plan_status="WATCH_ONLY"), _trig(), None, None, None, None
    )
    assert r["decision"] == "WATCH_ONLY"
    assert any("PLAN_NOT_READY" in w for w in r["warning_reasons"])


def test_no_model_signal_warning_added():
    r = compute_decision_gate(
        _plan("LONG"),
        _trig(),
        None,
        None,
        None,
        None,
        {"active_model_count": 0},
    )
    assert "NO_MODEL_SIGNAL" in r["warning_reasons"]


def test_model_veto_blocks_decision():
    veto_plan = _plan("LONG", plan_status="INVALID", reasons=["MODEL_VETO_LONG_CONSENSUS_SHORT_STRENGTH_100.0"])
    veto_plan["model_veto"] = True
    veto_plan["model_veto_reason"] = "MODEL_VETO_LONG_CONSENSUS_SHORT_STRENGTH_100.0"
    r = compute_decision_gate(
        veto_plan,
        _trig(),
        None,
        None,
        None,
        None,
        {"active_model_count": 1, "consensus_direction": "SHORT"},
    )
    assert r["decision"] == "BLOCK"
    assert "MODEL_VETO_DETECTED" in r["block_reasons"]


# --- Test 15: empty plan reasons blocks ---

def test_empty_plan_reasons_blocks():
    r = compute_decision_gate(
        _plan("LONG", reasons=[]), _trig(), None, None, None, None
    )
    assert r["decision"] == "BLOCK"
    assert "EMPTY_PLAN_REASONS" in r["block_reasons"]


# --- Test 16: append-only persistence and output files ---

def test_append_only_persistence_and_outputs(tmp_s18, monkeypatch):
    import src.simple.decision_gate_engine as eng

    plan = _plan("LONG")
    trig = _trig()

    plan_p = tmp_s18 / "plan.json"
    trig_p = tmp_s18 / "trig.json"
    plan_p.write_text(json.dumps(plan), encoding="utf-8")
    trig_p.write_text(json.dumps(trig), encoding="utf-8")

    log_path = tmp_s18 / "decision_gate_history.jsonl"

    monkeypatch.setattr(eng, "TRADE_PLAN_PATH", plan_p)
    monkeypatch.setattr(eng, "SCENARIO_TRIGGER_PATH", trig_p)
    monkeypatch.setattr(eng, "SETUP_CONTEXT_PATH", tmp_s18 / "no_ctx.json")
    monkeypatch.setattr(eng, "FLOW_STATE_PATH", tmp_s18 / "no_fs.json")
    monkeypatch.setattr(eng, "EVIDENCE_PATH", tmp_s18 / "no_ev.json")
    monkeypatch.setattr(eng, "PERSISTENCE_PATH", tmp_s18 / "no_pers.json")
    monkeypatch.setattr(eng, "DECISION_GATE_PATH", tmp_s18 / "latest_decision_gate.json")
    monkeypatch.setattr(eng, "S18_STATE_PATH", tmp_s18 / "s18_state.json")
    monkeypatch.setattr(eng, "DECISION_GATE_LOG_PATH", log_path)
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s18 / "report.md")

    run_decision_gate_engine()
    run_decision_gate_engine()
    run_decision_gate_engine()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert (tmp_s18 / "latest_decision_gate.json").exists()
    assert (tmp_s18 / "s18_state.json").exists()
    assert (tmp_s18 / "report.md").exists()
