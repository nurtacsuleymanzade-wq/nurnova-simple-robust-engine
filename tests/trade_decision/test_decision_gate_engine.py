from __future__ import annotations

import pytest
from src.trade_decision.decision_gate_engine import run_decision_gate


def _plan(
    preliminary: str = "ALLOW",
    trigger: str = "TRIGGER_READY",
    quality: str = "A",
    entry: float | None = 100.0,
    sl: float | None = 96.0,
    tp1: float | None = 106.0,
    inv: float | None = 96.0,
    rr: float | None = 1.5,
    side: str = "LONG",
    template_risk: float = 0.0,
    blocking: list | None = None,
) -> dict:
    return {
        "_preliminary_decision": preliminary,
        "_trigger_status": trigger,
        "plan_quality": quality,
        "side": side,
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit_1": tp1,
        "invalidation_level": inv,
        "rr_to_tp1": rr,
        "template_risk_score": template_risk,
        "blocking_reason_codes": blocking or [],
        "entry_reason_codes": ["ENTRY_LONG_RETEST_SUPPORT"],
        "sl_reason_codes": ["SL_LONG_STRUCTURAL_LOW"],
        "tp_reason_codes": ["TP1_LONG_LIQUIDITY_ABOVE"],
        "risk_reason_codes": [],
        "scores": {},
        "evidence": {"current_price": 100.0},
    }


# ── Test 7: TRIGGER_WAIT → WAIT ──────────────────────────────────────────────

def test_trigger_wait_decision_wait():
    gate = run_decision_gate(_plan(preliminary="WAIT", trigger="TRIGGER_WAIT"), "OK")
    assert gate["decision_status"] == "WAIT"


# ── Test 8: TRIGGER_INVALID → BLOCK ──────────────────────────────────────────

def test_trigger_invalid_decision_block():
    gate = run_decision_gate(
        _plan(preliminary="BLOCK", trigger="TRIGGER_INVALID", blocking=["TRIGGER_STATUS_TRIGGER_INVALID"]),
        "OK",
    )
    assert gate["decision_status"] == "BLOCK"


# ── Test 9: NO_SETUP → NO_TRADE ──────────────────────────────────────────────

def test_no_setup_decision_no_trade():
    gate = run_decision_gate(_plan(preliminary="NO_TRADE", side="NO_TRADE"), "OK")
    assert gate["decision_status"] == "NO_TRADE"


# ── Test 12: ALLOW_PAPER requires all fields ──────────────────────────────────

def test_allow_paper_requires_entry_price():
    plan = _plan(entry=None, blocking=["ENTRY_PRICE_MISSING"])
    gate = run_decision_gate(plan, "OK")
    assert gate["decision_status"] == "BLOCK"
    assert "ENTRY_PRICE_REQUIRED_FOR_ALLOW" in gate["blocking_reason_codes"]


def test_allow_paper_requires_stop_loss():
    plan = _plan(sl=None, blocking=["STOP_LOSS_MISSING"])
    gate = run_decision_gate(plan, "OK")
    assert gate["decision_status"] == "BLOCK"
    assert "STOP_LOSS_REQUIRED_FOR_ALLOW" in gate["blocking_reason_codes"]


def test_allow_paper_requires_take_profit():
    plan = _plan(tp1=None, blocking=["TAKE_PROFIT_MISSING"])
    gate = run_decision_gate(plan, "OK")
    assert gate["decision_status"] == "BLOCK"
    assert "TAKE_PROFIT_REQUIRED_FOR_ALLOW" in gate["blocking_reason_codes"]


def test_allow_paper_requires_invalidation():
    plan = _plan(inv=None)
    gate = run_decision_gate(plan, "OK")
    assert gate["decision_status"] == "BLOCK"
    assert "INVALIDATION_REQUIRED_FOR_ALLOW" in gate["blocking_reason_codes"]


# ── Test 13: template risk BLOCK ──────────────────────────────────────────────

def test_template_risk_high_blocks_allow():
    plan = _plan(template_risk=0.6)
    gate = run_decision_gate(plan, "OK")
    assert gate["decision_status"] == "BLOCK"
    assert "TEMPLATE_RISK_BLOCKS_ALLOW" in gate["blocking_reason_codes"]


# ── Full ALLOW_PAPER path ─────────────────────────────────────────────────────

def test_full_allow_paper():
    plan = _plan(rr=1.9, quality="A", template_risk=0.0)
    gate = run_decision_gate(plan, "OK")
    assert gate["decision_status"] == "ALLOW_PAPER"
    assert gate["decision_confidence"] > 0.0


# ── INVALID data quality → BLOCK ─────────────────────────────────────────────

def test_invalid_data_quality_blocks():
    plan = _plan(preliminary="ALLOW", quality="A")
    gate = run_decision_gate(plan, "INVALID")
    assert gate["decision_status"] == "BLOCK"
    assert "DATA_QUALITY_INVALID" in gate["blocking_reason_codes"]


# ── Test 17: feeds_next correct ───────────────────────────────────────────────

def test_feeds_next_in_gate_output():
    gate = run_decision_gate(_plan(), "OK")
    # Gate returns decision_status, decision_confidence, blocking_reason_codes
    assert "decision_status" in gate
    assert "decision_confidence" in gate
    assert "blocking_reason_codes" in gate


# ── Test 18: real_trade_allowed never set by gate ────────────────────────────

def test_real_trade_allowed_not_in_gate():
    gate = run_decision_gate(_plan(), "OK")
    assert "real_trade_allowed" not in gate
