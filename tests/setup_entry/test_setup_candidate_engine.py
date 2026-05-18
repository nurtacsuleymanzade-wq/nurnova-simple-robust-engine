from __future__ import annotations

import pytest
from src.setup_entry.setup_candidate_engine import build_setup_candidate


def _mkt(regime="UPTREND", trend="BULLISH", risk="MEDIUM"):
    return {"market_regime": regime, "trend_state": trend, "risk_state": risk}


def _scn(scenario="BULLISH_CONTINUATION", bias="LONG", conf=0.7):
    return {"active_scenario": scenario, "scenario_bias": bias, "scenario_confidence": conf}


def _flow(fc="CONFIRMED_LONG", plr="CONTINUATION_AFTER_SWEEP", conf=0.75):
    return {"flow_confirmation": fc, "post_liquidity_reaction": plr, "reaction_confidence": conf}


def test_long_continuation_setup():
    result = build_setup_candidate(
        market_state=_mkt("UPTREND", "BULLISH", "MEDIUM"),
        active_scenario=_scn("BULLISH_CONTINUATION", "LONG", 0.75),
        flow_reaction=_flow("CONFIRMED_LONG", "CONTINUATION_AFTER_SWEEP", 0.8),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "LONG_CONTINUATION_SETUP"
    assert result["setup_direction"] == "LONG"


def test_short_continuation_setup():
    result = build_setup_candidate(
        market_state=_mkt("DOWNTREND", "BEARISH", "MEDIUM"),
        active_scenario=_scn("BEARISH_CONTINUATION", "SHORT", 0.75),
        flow_reaction=_flow("CONFIRMED_SHORT", "CONTINUATION_AFTER_SWEEP", 0.8),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "SHORT_CONTINUATION_SETUP"
    assert result["setup_direction"] == "SHORT"


def test_long_reversal_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("BULLISH_REVERSAL", "LONG", 0.65),
        flow_reaction=_flow("CONFIRMED_LONG", "REVERSAL_AFTER_SWEEP", 0.7),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "LONG_REVERSAL_SETUP"
    assert result["setup_direction"] == "LONG"


def test_short_reversal_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("BEARISH_REVERSAL", "SHORT", 0.65),
        flow_reaction=_flow("CONFIRMED_SHORT", "REVERSAL_AFTER_SWEEP", 0.7),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "SHORT_REVERSAL_SETUP"
    assert result["setup_direction"] == "SHORT"


def test_range_long_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("RANGE_ROTATION_UP", "LONG", 0.6),
        flow_reaction=_flow("CONFIRMED_LONG", "CONTINUATION_AFTER_SWEEP", 0.65),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "RANGE_LONG_SETUP"
    assert result["setup_direction"] == "LONG"


def test_range_short_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("RANGE_ROTATION_DOWN", "SHORT", 0.6),
        flow_reaction=_flow("CONFIRMED_SHORT", "CONTINUATION_AFTER_SWEEP", 0.65),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "RANGE_SHORT_SETUP"
    assert result["setup_direction"] == "SHORT"


def test_compression_breakout_long_setup():
    result = build_setup_candidate(
        market_state=_mkt("COMPRESSION", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("COMPRESSION_BREAKOUT_UP", "LONG", 0.65),
        flow_reaction=_flow("CONFIRMED_LONG", "REAL_BREAKOUT", 0.75),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "COMPRESSION_BREAKOUT_LONG_SETUP"
    assert result["setup_direction"] == "LONG"


def test_compression_breakout_short_setup():
    result = build_setup_candidate(
        market_state=_mkt("COMPRESSION", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("COMPRESSION_BREAKOUT_DOWN", "SHORT", 0.65),
        flow_reaction=_flow("CONFIRMED_SHORT", "REAL_BREAKOUT", 0.75),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "COMPRESSION_BREAKOUT_SHORT_SETUP"
    assert result["setup_direction"] == "SHORT"


def test_buyers_trapped_short_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("BUYERS_TRAPPED_CONTINUATION_SHORT", "SHORT", 0.7),
        flow_reaction=_flow("CONFIRMED_SHORT", "BUYERS_TRAPPED", 0.8),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "BUYERS_TRAPPED_SHORT_SETUP"
    assert result["setup_direction"] == "SHORT"


def test_sellers_trapped_long_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("SELLERS_TRAPPED_CONTINUATION_LONG", "LONG", 0.7),
        flow_reaction=_flow("CONFIRMED_LONG", "SELLERS_TRAPPED", 0.8),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "SELLERS_TRAPPED_LONG_SETUP"
    assert result["setup_direction"] == "LONG"


def test_post_sweep_reclaim_long_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("POST_SWEEP_RECLAIM_LONG", "LONG", 0.65),
        flow_reaction=_flow("CONFIRMED_LONG", "RECLAIM_AFTER_SWEEP", 0.7),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "POST_SWEEP_RECLAIM_LONG_SETUP"
    assert result["setup_direction"] == "LONG"


def test_post_sweep_rejection_short_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("POST_SWEEP_REJECTION_SHORT", "SHORT", 0.65),
        flow_reaction=_flow("CONFIRMED_SHORT", "REJECTION_AFTER_SWEEP", 0.7),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "POST_SWEEP_REJECTION_SHORT_SETUP"
    assert result["setup_direction"] == "SHORT"


def test_no_setup():
    result = build_setup_candidate(
        market_state=_mkt("UNKNOWN", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("NO_ACTIVE_SCENARIO", "NEUTRAL", 0.0),
        flow_reaction=None,
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "NO_SETUP"
    assert result["setup_direction"] == "NO_TRADE"


def test_conflicted_setup():
    result = build_setup_candidate(
        market_state=_mkt("RANGE", "NEUTRAL", "MEDIUM"),
        active_scenario=_scn("BULLISH_CONTINUATION", "LONG", 0.5),
        flow_reaction=_flow("CONFIRMED_SHORT", "CONTINUATION_AFTER_SWEEP", 0.5),
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "CONFLICTED_SETUP"


def test_no_evidence_produces_unknown():
    result = build_setup_candidate(
        market_state=None,
        active_scenario=None,
        flow_reaction=None,
        liquidity=None,
        structure=None,
        candle=None,
    )
    assert result["setup_candidate"] == "UNKNOWN"


def test_invalid_data_quality():
    result = build_setup_candidate(
        market_state=_mkt(),
        active_scenario=_scn(),
        flow_reaction=None,
        liquidity=None,
        structure=None,
        candle=None,
        data_quality="INVALID",
    )
    assert result["setup_candidate"] == "UNKNOWN"
    assert result["setup_quality"] == "INVALID"
