from __future__ import annotations

import pytest
from src.setup_entry.entry_trigger_engine import build_entry_trigger


def _setup(candidate="LONG_CONTINUATION_SETUP", direction="LONG", quality="A", conf=0.8):
    return {
        "setup_candidate": candidate,
        "setup_direction": direction,
        "setup_quality": quality,
        "setup_confidence": conf,
    }


def _scn(conf=0.75):
    return {"scenario_confidence": conf}


def _flow(fc="CONFIRMED_LONG", conf=0.8):
    return {"flow_confirmation": fc, "reaction_confidence": conf}


def _mkt(risk="MEDIUM"):
    return {"risk_state": risk}


def test_trigger_ready_high_quality():
    result = build_entry_trigger(
        setup_result=_setup("LONG_CONTINUATION_SETUP", "LONG", "A", 0.8),
        active_scenario=_scn(0.75),
        flow_reaction=_flow("CONFIRMED_LONG", 0.8),
        market_state=_mkt("MEDIUM"),
    )
    assert result["entry_trigger_status"] == "TRIGGER_READY"
    assert result["entry_trigger_quality"] == "HIGH"


def test_trigger_near():
    result = build_entry_trigger(
        setup_result=_setup("LONG_CONTINUATION_SETUP", "LONG", "B", 0.6),
        active_scenario=_scn(0.65),
        flow_reaction=_flow("CONFIRMED_LONG", 0.65),
        market_state=_mkt("MEDIUM"),
    )
    assert result["entry_trigger_status"] == "TRIGGER_NEAR"
    assert result["entry_trigger_quality"] == "MEDIUM"


def test_trigger_wait():
    result = build_entry_trigger(
        setup_result=_setup("RANGE_LONG_SETUP", "LONG", "C", 0.5),
        active_scenario=_scn(0.55),
        flow_reaction=_flow("NOT_CONFIRMED", 0.4),
        market_state=_mkt("MEDIUM"),
    )
    assert result["entry_trigger_status"] == "TRIGGER_WAIT"


def test_trigger_invalid_no_setup():
    result = build_entry_trigger(
        setup_result=_setup("NO_SETUP", "NO_TRADE", "INVALID", 0.0),
        active_scenario=None,
        flow_reaction=None,
        market_state=None,
    )
    assert result["entry_trigger_status"] == "TRIGGER_INVALID"


def test_trigger_conflicted():
    result = build_entry_trigger(
        setup_result=_setup("LONG_CONTINUATION_SETUP", "LONG", "A", 0.8),
        active_scenario=_scn(0.75),
        flow_reaction=_flow("CONFIRMED_SHORT", 0.8),
        market_state=_mkt("MEDIUM"),
    )
    assert result["entry_trigger_status"] == "TRIGGER_CONFLICTED"


def test_trigger_invalid_risk_no_trade():
    result = build_entry_trigger(
        setup_result=_setup("LONG_CONTINUATION_SETUP", "LONG", "A", 0.8),
        active_scenario=_scn(0.75),
        flow_reaction=_flow("CONFIRMED_LONG", 0.8),
        market_state=_mkt("NO_TRADE"),
    )
    assert result["entry_trigger_status"] == "TRIGGER_INVALID"
    assert "RISK_STATE_NO_TRADE" in result["blocking_reason_codes"]


def test_trigger_unknown_no_evidence():
    result = build_entry_trigger(
        setup_result=_setup("CONFLICTED_SETUP", "NEUTRAL", "INVALID", 0.0),
        active_scenario=None,
        flow_reaction=None,
        market_state=None,
    )
    assert result["entry_trigger_status"] == "TRIGGER_CONFLICTED"
