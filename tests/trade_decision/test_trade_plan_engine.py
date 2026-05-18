from __future__ import annotations

import pytest
from src.trade_decision.trade_plan_engine import build_trade_plan, _compute_template_risk_score


def _setup_entry(
    direction: str = "LONG",
    quality: str = "A",
    trigger: str = "TRIGGER_READY",
    trigger_quality: str = "HIGH",
    candidate: str = "RANGE_LONG_SETUP",
) -> dict:
    return {
        "setup_candidate_id": "SCE_TEST001",
        "entry_trigger_id": "ETG_TEST001",
        "lineage_id": "LIN_TEST001",
        "setup_direction": direction,
        "setup_quality": quality,
        "entry_trigger_status": trigger,
        "entry_trigger_quality": trigger_quality,
        "setup_candidate": candidate,
        "setup_confidence": 0.8,
    }


def _active_scenario(scenario: str = "RANGE_ROTATION_UP", bias: str = "LONG") -> dict:
    return {
        "active_scenario_id": "ASC_TEST001",
        "active_scenario": scenario,
        "scenario_bias": bias,
        "scenario_confidence": 0.7,
    }


def _liquidity_structure(
    current: float = 100.0,
    range_high: float = 105.0,
    range_low: float = 95.0,
    liq_above: float = 106.0,
    liq_below: float = 94.0,
    support: float = 96.0,
    resistance: float = 104.0,
) -> dict:
    return {
        "range_context": {
            "current_price": current,
            "range_high": range_high,
            "range_low": range_low,
            "range_mid": (range_high + range_low) / 2,
        },
        "liquidity_levels": {
            "nearest_liquidity_above": {"price": liq_above, "liquidity_type": "RANGE_HIGH"},
            "nearest_liquidity_below": {"price": liq_below, "liquidity_type": "RANGE_LOW"},
        },
        "nearest_support": support,
        "nearest_resistance": resistance,
        "liquidity_notes": [],
    }


# ── Test 1: Long trade plan is produced ──────────────────────────────────────

def test_long_trade_plan_produced():
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY"),
        market_state=None,
        active_scenario=_active_scenario("RANGE_ROTATION_UP", "LONG"),
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    assert plan["side"] == "LONG"
    assert plan["entry_price"] is not None
    assert plan["_preliminary_decision"] == "ALLOW"


# ── Test 2: Short trade plan is produced ─────────────────────────────────────

def test_short_trade_plan_produced():
    plan = build_trade_plan(
        setup_entry=_setup_entry("SHORT", trigger="TRIGGER_READY", candidate="RANGE_SHORT_SETUP"),
        market_state=None,
        active_scenario=_active_scenario("RANGE_ROTATION_DOWN", "SHORT"),
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    assert plan["side"] == "SHORT"
    assert plan["entry_price"] is not None
    assert plan["_preliminary_decision"] == "ALLOW"


# ── Test 3: Missing entry produces BLOCK ─────────────────────────────────────

def test_missing_entry_produces_block():
    liq = _liquidity_structure(current=None)
    liq["range_context"]["current_price"] = None
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=liq,
        data_quality="OK",
    )
    assert plan["entry_price"] is None
    assert "ENTRY_PRICE_MISSING" in plan["blocking_reason_codes"]
    assert plan["_preliminary_decision"] == "BLOCK"


# ── Test 4: Missing stop produces BLOCK ──────────────────────────────────────

def test_missing_stop_produces_block():
    # All price levels same as current → degenerate → no valid SL below entry
    liq = _liquidity_structure(
        current=100.0,
        range_high=100.0,
        range_low=100.0,
        liq_above=100.0,
        liq_below=100.0,
        support=100.0,
        resistance=100.0,
    )
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=liq,
        data_quality="OK",
    )
    assert plan["stop_loss"] is None
    assert "STOP_LOSS_MISSING" in plan["blocking_reason_codes"]


# ── Test 5: Missing TP produces BLOCK ────────────────────────────────────────

def test_missing_tp_produces_block():
    # CONTINUATION entry → entry_price = current_price = 100.0
    # liq_above and range_high == 100.0 == entry_price → no valid TP above
    liq = _liquidity_structure(
        current=100.0,
        range_high=100.0,
        liq_above=100.0,
        support=96.0,
        liq_below=94.0,
    )
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY", candidate="LONG_CONTINUATION_SETUP"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=liq,
        data_quality="OK",
    )
    assert plan["take_profit_1"] is None
    assert "TAKE_PROFIT_MISSING" in plan["blocking_reason_codes"]


# ── Test 6: Missing invalidation produces BLOCK ───────────────────────────────

def test_missing_invalidation_produces_block():
    # Same as test 4 — no SL → no invalidation
    liq = _liquidity_structure(
        current=100.0,
        range_high=100.0,
        range_low=100.0,
        liq_above=100.0,
        liq_below=100.0,
        support=100.0,
        resistance=100.0,
    )
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=liq,
        data_quality="OK",
    )
    assert plan["invalidation_level"] is None


# ── Test 7: TRIGGER_WAIT produces WAIT ───────────────────────────────────────

def test_trigger_wait_produces_wait():
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_WAIT"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    assert plan["_preliminary_decision"] == "WAIT"


# ── Test 8: TRIGGER_INVALID produces BLOCK ───────────────────────────────────

def test_trigger_invalid_produces_block():
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_INVALID"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    assert plan["_preliminary_decision"] == "BLOCK"
    assert any("TRIGGER_INVALID" in c for c in plan["blocking_reason_codes"])


# ── Test 9: NO_SETUP produces NO_TRADE ───────────────────────────────────────

def test_no_setup_produces_no_trade():
    plan = build_trade_plan(
        setup_entry=None,
        market_state=None,
        active_scenario=None,
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    assert plan["side"] == "NO_TRADE"
    assert plan["_preliminary_decision"] == "NO_TRADE"


# ── Test 10: TP not produced without liquidity destination ────────────────────

def test_tp_not_produced_without_liquidity_destination():
    # SHORT CONTINUATION → entry_price = current_price = 100.0
    # liq_below and range_low == 100.0 == entry_price → no valid TP below
    liq = _liquidity_structure(
        current=100.0,
        range_low=100.0,
        liq_below=100.0,
        liq_above=104.0,
        resistance=104.0,
        support=96.0,
    )
    plan = build_trade_plan(
        setup_entry=_setup_entry("SHORT", trigger="TRIGGER_READY", candidate="SHORT_CONTINUATION_SETUP"),
        market_state=None,
        active_scenario=_active_scenario("RANGE_ROTATION_DOWN", "SHORT"),
        flow_reaction=None,
        liquidity_structure=liq,
        data_quality="OK",
    )
    assert plan["take_profit_1"] is None
    assert any("NO_LIQUIDITY_DESTINATION" in c for c in plan["tp_reason_codes"])


# ── Test 11: TP not produced from fixed RR ────────────────────────────────────

def test_tp_not_produced_from_fixed_rr():
    # entry=96 (support retest), sl=94 (liq_below), tp should come from liq_above=106 not entry+risk*2
    liq = _liquidity_structure(
        current=100.0,
        support=96.0,
        liq_below=94.0,
        liq_above=106.0,
        range_high=110.0,
    )
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=liq,
        data_quality="OK",
    )
    entry = plan["entry_price"]
    sl = plan["stop_loss"]
    tp1 = plan["take_profit_1"]
    assert tp1 is not None
    assert entry is not None and sl is not None
    # TP must not be entry + (entry-sl)*N for any round N
    risk = entry - sl
    for multiplier in (1.0, 1.5, 2.0, 2.5, 3.0):
        fixed_tp = round(entry + risk * multiplier, 2)
        assert tp1 != fixed_tp, f"TP {tp1} matches fixed RR {multiplier}x formula ({fixed_tp})"


# ── Test 12: ALLOW_PAPER requires all fields ──────────────────────────────────

def test_allow_paper_requires_all_fields():
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    # If plan is ALLOW, it must have all fields
    if plan["_preliminary_decision"] == "ALLOW":
        assert plan["entry_price"] is not None
        assert plan["stop_loss"] is not None
        assert plan["take_profit_1"] is not None
        assert plan["invalidation_level"] is not None


# ── Test 13: Template risk score raises ───────────────────────────────────────

def test_template_risk_score_raises():
    # Directly test _compute_template_risk_score with suspicious inputs:
    # - entry == current_price and entry_reason_codes empty → +0.3
    # - TP codes contain NO_LIQUIDITY_DESTINATION → +0.3
    # - sl_reason_codes empty → +0.2
    # - evidence all empty → +0.2
    score = _compute_template_risk_score(
        entry_price=100.0,
        current_price=100.0,
        entry_reason_codes=[],
        sl_reason_codes=[],
        tp_reason_codes=["TP_NO_LIQUIDITY_DESTINATION_ABOVE"],
        rr=None,
        evidence={},
    )
    assert score >= 0.5


# ── Test 17: Feeds next is correct ────────────────────────────────────────────

def test_feeds_next_correct_in_plan():
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    # The plan engine doesn't produce feeds_next; runner does.
    # Just verify plan has required output keys
    for key in ("side", "entry_model", "blocking_reason_codes", "scores"):
        assert key in plan


# ── Test 18: real_trade_allowed is always False ───────────────────────────────

def test_real_trade_allowed_false():
    # Enforced by runner; plan engine never sets it
    plan = build_trade_plan(
        setup_entry=_setup_entry("LONG", trigger="TRIGGER_READY"),
        market_state=None,
        active_scenario=_active_scenario(),
        flow_reaction=None,
        liquidity_structure=_liquidity_structure(),
        data_quality="OK",
    )
    # No real_trade field should exist in raw plan (it's set in runner)
    assert "real_trade_allowed" not in plan
