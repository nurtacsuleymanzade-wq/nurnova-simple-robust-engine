from __future__ import annotations

import pytest
from src.flow_reaction.post_liquidity_reaction_engine import build_post_liquidity_reaction


def _candle(o, c, h, lo) -> dict:
    return {"official_candle": {"open": o, "close": c, "high": h, "low": lo}}


def _liq_above_taken() -> dict:
    return {"reaction_flags": {"liquidity_above_taken": True, "upside_sweep": True, "downside_sweep": False,
                                "liquidity_below_taken": False, "reclaim": False, "rejection": False}}


def _liq_below_taken() -> dict:
    return {"reaction_flags": {"liquidity_below_taken": True, "downside_sweep": True, "upside_sweep": False,
                                "liquidity_above_taken": False, "reclaim": False, "rejection": False}}


def _liq_below_taken_reclaim() -> dict:
    return {"reaction_flags": {"liquidity_below_taken": True, "downside_sweep": True, "upside_sweep": False,
                                "liquidity_above_taken": False, "reclaim": True, "rejection": False}}


def test_continuation_after_sweep():
    # Upside sweep + bullish close + positive delta
    result = build_post_liquidity_reaction(
        liquidity=_liq_above_taken(),
        candle=_candle(100, 108, 115, 99),  # strong bullish
        order_flow={"delta": 500},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state={"flow_state": "BUY_PRESSURE"},
    )
    assert result["post_liquidity_reaction"] == "CONTINUATION_AFTER_SWEEP"


def test_reversal_after_sweep():
    # Upside sweep + bearish close
    result = build_post_liquidity_reaction(
        liquidity=_liq_above_taken(),
        candle=_candle(110, 102, 115, 100),  # bearish body
        order_flow={"delta": -200},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "REVERSAL_AFTER_SWEEP"


def test_rejection_after_sweep():
    # Upside sweep + large upper wick
    result = build_post_liquidity_reaction(
        liquidity=_liq_above_taken(),
        candle=_candle(100, 102, 120, 99),  # tiny body, huge upper wick
        order_flow={"delta": -100},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "REJECTION_AFTER_SWEEP"


def test_reclaim_after_sweep():
    # Downside sweep + reclaim + bullish close
    result = build_post_liquidity_reaction(
        liquidity=_liq_below_taken_reclaim(),
        candle=_candle(100, 108, 110, 95),  # bullish with lower wick (reclaim)
        order_flow={"delta": 300},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "RECLAIM_AFTER_SWEEP"


def test_absorption_detected():
    # Positive delta + upper wick (buy absorption)
    result = build_post_liquidity_reaction(
        liquidity={"reaction_flags": {"upside_sweep": False, "downside_sweep": False,
                                       "liquidity_above_taken": False, "liquidity_below_taken": False,
                                       "reclaim": False, "rejection": False}},
        candle=_candle(100, 101, 115, 99),  # tiny body, large upper wick
        order_flow={"delta": 500},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "ABSORPTION_DETECTED"
    assert result["absorption_state"] in ("BUY_ABSORPTION", "BOTH")


def test_buyers_trapped():
    # Upside liquidity taken + bearish reversal + negative delta
    result = build_post_liquidity_reaction(
        liquidity=_liq_above_taken(),
        candle=_candle(108, 99, 115, 98),  # bearish with large body after sweep
        order_flow={"delta": -500},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "BUYERS_TRAPPED"
    assert result["trap_state"] == "BUYERS_TRAPPED"


def test_sellers_trapped():
    # Downside liquidity taken + bullish reversal + positive delta
    result = build_post_liquidity_reaction(
        liquidity=_liq_below_taken(),
        candle=_candle(95, 108, 109, 90),  # bullish with lower wick
        order_flow={"delta": 500},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "SELLERS_TRAPPED"
    assert result["trap_state"] == "SELLERS_TRAPPED"


def test_failed_breakout():
    # No sweep but strong wick rejection on attempted breakout
    result = build_post_liquidity_reaction(
        liquidity={"reaction_flags": {"upside_sweep": True, "downside_sweep": False,
                                       "liquidity_above_taken": False, "liquidity_below_taken": False,
                                       "reclaim": False, "rejection": True}},
        candle=_candle(100, 101, 120, 99),  # large upper wick
        order_flow={"delta": -50},
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "REJECTION_AFTER_SWEEP"


def test_real_breakout():
    # Strong directional breakout candle + flow alignment
    result = build_post_liquidity_reaction(
        liquidity={"reaction_flags": {"upside_sweep": False, "downside_sweep": False,
                                       "liquidity_above_taken": False, "liquidity_below_taken": False,
                                       "reclaim": False, "rejection": False}},
        candle=_candle(100, 115, 116, 99),  # huge bullish body
        order_flow={"delta": 800},
        footprint={"buy_dominant": True},
        structure=None,
        active_scenario=None,
        market_state={"flow_state": "BUY_PRESSURE"},
    )
    assert result["post_liquidity_reaction"] == "REAL_BREAKOUT"


def test_no_liquidity_event_no_crash():
    result = build_post_liquidity_reaction(
        liquidity=None,
        candle=None,
        order_flow=None,
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "NO_LIQUIDITY_EVENT"


def test_insufficient_evidence_no_crash():
    # Liquidity event but no candle or flow evidence
    result = build_post_liquidity_reaction(
        liquidity=_liq_above_taken(),
        candle=None,
        order_flow=None,
        footprint=None,
        structure=None,
        active_scenario=None,
        market_state=None,
    )
    assert result["post_liquidity_reaction"] == "INSUFFICIENT_EVIDENCE"
