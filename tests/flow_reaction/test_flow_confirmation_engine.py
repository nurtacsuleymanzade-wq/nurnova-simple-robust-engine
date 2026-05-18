from __future__ import annotations

import pytest
from src.flow_reaction.flow_confirmation_engine import build_flow_confirmation


def _make_candle(bullish: bool, body_ratio: float = 0.6, upper_wick: float = 0.1, lower_wick: float = 0.1) -> dict:
    # o/c/h/l that satisfy the ratios
    if bullish:
        o, c = 100.0, 100.0 + 60 * body_ratio
    else:
        o, c = 100.0, 100.0 - 60 * body_ratio
    h = max(o, c) + upper_wick * 100
    lo = min(o, c) - lower_wick * 100
    return {"official_candle": {"open": o, "close": c, "high": h, "low": lo}}


def _long_scenario() -> dict:
    return {
        "scenario_bias": "LONG",
        "scenario_confidence": 0.8,
        "active_scenario": "BULLISH_CONTINUATION",
    }


def _short_scenario() -> dict:
    return {
        "scenario_bias": "SHORT",
        "scenario_confidence": 0.8,
        "active_scenario": "BEARISH_CONTINUATION",
    }


def _bull_market() -> dict:
    return {"trend_state": "BULLISH", "flow_state": "BUY_PRESSURE"}


def _bear_market() -> dict:
    return {"trend_state": "BEARISH", "flow_state": "SELL_PRESSURE"}


def test_confirmed_long():
    result = build_flow_confirmation(
        active_scenario=_long_scenario(),
        market_state=_bull_market(),
        candle=_make_candle(True),
        footprint={"buy_dominant": True},
        order_flow={"delta": 500},
        liquidity=None,
    )
    assert result["flow_confirmation"] == "CONFIRMED_LONG"


def test_confirmed_short():
    result = build_flow_confirmation(
        active_scenario=_short_scenario(),
        market_state=_bear_market(),
        candle=_make_candle(False),
        footprint={"sell_dominant": True},
        order_flow={"delta": -500},
        liquidity=None,
    )
    assert result["flow_confirmation"] == "CONFIRMED_SHORT"


def test_not_confirmed():
    # Weak signals, no flow teyidi
    result = build_flow_confirmation(
        active_scenario={"scenario_bias": "LONG", "scenario_confidence": 0.3},
        market_state={"trend_state": "NEUTRAL", "flow_state": "NEUTRAL"},
        candle=_make_candle(True, body_ratio=0.1),
        footprint=None,
        order_flow={"delta": 10},
        liquidity=None,
    )
    assert result["flow_confirmation"] == "NOT_CONFIRMED"


def test_conflicted():
    # Long scenario but strong negative delta and bearish close
    result = build_flow_confirmation(
        active_scenario=_long_scenario(),
        market_state={"trend_state": "NEUTRAL", "flow_state": "SELL_PRESSURE"},
        candle=_make_candle(False),
        footprint={"sell_dominant": True},
        order_flow={"delta": -1000},
        liquidity=None,
    )
    assert result["flow_confirmation"] == "CONFLICTED"


def test_unknown_no_evidence():
    result = build_flow_confirmation(
        active_scenario=None,
        market_state=None,
        candle=None,
        footprint=None,
        order_flow=None,
        liquidity=None,
    )
    assert result["flow_confirmation"] == "UNKNOWN"


def test_unknown_invalid_data_quality():
    result = build_flow_confirmation(
        active_scenario=_long_scenario(),
        market_state=_bull_market(),
        candle=None,
        footprint=None,
        order_flow=None,
        liquidity=None,
        data_quality="INVALID",
    )
    assert result["flow_confirmation"] == "UNKNOWN"
