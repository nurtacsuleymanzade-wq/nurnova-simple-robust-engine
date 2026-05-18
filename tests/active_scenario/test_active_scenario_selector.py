from __future__ import annotations

from src.active_scenario.active_scenario_candidate_engine import build_scenario_candidates
from src.active_scenario.active_scenario_selector import select_active_scenario


def _evidence(
    *,
    market_regime: str = "UPTREND",
    trend_state: str = "BULLISH",
    volatility_state: str = "NORMAL",
    structure_state: str = "HH_HL",
    liquidity_pressure_state: str = "ABOVE",
    flow_state: str = "BUY_PRESSURE",
    maturity_state: str = "MID",
    risk_state: str = "LOW",
    reaction: dict | None = None,
) -> dict:
    reaction = reaction or {}
    return {
        "market_state_evidence": {
            "market_regime": market_regime,
            "trend_state": trend_state,
            "volatility_state": volatility_state,
            "structure_state": structure_state,
            "liquidity_pressure_state": liquidity_pressure_state,
            "flow_state": flow_state,
            "maturity_state": maturity_state,
            "risk_state": risk_state,
        },
        "liquidity_evidence": {"liquidity_pressure_state": liquidity_pressure_state},
        "structure_evidence": {"structure_state": structure_state, "trend_state": trend_state},
        "flow_evidence": {"flow_state": flow_state},
        "reaction_evidence": reaction,
        "risk_evidence": {"risk_state": risk_state},
    }


def _select(evidence: dict, *, data_quality: str = "OK", market_state_present: bool = True) -> dict:
    candidates, frame = build_scenario_candidates(evidence, data_quality)
    return select_active_scenario(
        candidates=candidates,
        feature_frame=frame,
        data_quality=data_quality,
        market_state_present=market_state_present,
    )


def test_buyers_trapped_continuation_short_selected() -> None:
    out = _select(
        _evidence(
            market_regime="RANGE",
            trend_state="BEARISH",
            structure_state="BROKEN_STRUCTURE",
            liquidity_pressure_state="ABOVE",
            flow_state="SELL_PRESSURE",
            reaction={"liquidity_above_taken": True, "buy_pressure_failed": True, "rejection": True},
        )
    )
    assert out["active_scenario"] == "BUYERS_TRAPPED_CONTINUATION_SHORT"


def test_sellers_trapped_continuation_long_selected() -> None:
    out = _select(
        _evidence(
            market_regime="RANGE",
            trend_state="BULLISH",
            structure_state="BROKEN_STRUCTURE",
            liquidity_pressure_state="BELOW",
            flow_state="BUY_PRESSURE",
            reaction={"liquidity_below_taken": True, "sell_pressure_failed": True, "reclaim": True},
        )
    )
    assert out["active_scenario"] == "SELLERS_TRAPPED_CONTINUATION_LONG"


def test_range_rotation_up_selected() -> None:
    out = _select(
        _evidence(
            market_regime="RANGE",
            trend_state="NEUTRAL",
            structure_state="RANGE_BOUND",
            liquidity_pressure_state="BELOW",
            flow_state="BUY_PRESSURE",
        )
    )
    assert out["active_scenario"] == "RANGE_ROTATION_UP"


def test_range_rotation_down_selected() -> None:
    out = _select(
        _evidence(
            market_regime="RANGE",
            trend_state="NEUTRAL",
            structure_state="RANGE_BOUND",
            liquidity_pressure_state="ABOVE",
            flow_state="SELL_PRESSURE",
        )
    )
    assert out["active_scenario"] == "RANGE_ROTATION_DOWN"


def test_compression_breakout_up_selected() -> None:
    out = _select(
        _evidence(
            market_regime="COMPRESSION",
            trend_state="BULLISH",
            volatility_state="EXPANDING",
            structure_state="RANGE_BOUND",
            liquidity_pressure_state="ABOVE",
            flow_state="BUY_PRESSURE",
        )
    )
    assert out["active_scenario"] == "COMPRESSION_BREAKOUT_UP"


def test_compression_breakout_down_selected() -> None:
    out = _select(
        _evidence(
            market_regime="COMPRESSION",
            trend_state="BEARISH",
            volatility_state="EXPANDING",
            structure_state="RANGE_BOUND",
            liquidity_pressure_state="BELOW",
            flow_state="SELL_PRESSURE",
        )
    )
    assert out["active_scenario"] == "COMPRESSION_BREAKOUT_DOWN"


def test_post_sweep_reclaim_long_selected() -> None:
    out = _select(
        _evidence(
            market_regime="REVERSAL_RISK",
            trend_state="BULLISH",
            structure_state="BROKEN_STRUCTURE",
            liquidity_pressure_state="BELOW",
            flow_state="BUY_PRESSURE",
            reaction={"downside_sweep": True, "reclaim": True, "sell_absorption": True, "buy_reaction": True},
        )
    )
    assert out["active_scenario"] == "POST_SWEEP_RECLAIM_LONG"


def test_post_sweep_rejection_short_selected() -> None:
    out = _select(
        _evidence(
            market_regime="REVERSAL_RISK",
            trend_state="BEARISH",
            structure_state="BROKEN_STRUCTURE",
            liquidity_pressure_state="ABOVE",
            flow_state="SELL_PRESSURE",
            reaction={"upside_sweep": True, "rejection": True, "buy_absorption": True, "sell_reaction": True},
        )
    )
    assert out["active_scenario"] == "POST_SWEEP_REJECTION_SHORT"


def test_conflicted_scenario_selected() -> None:
    out = _select(
        _evidence(
            market_regime="RANGE",
            trend_state="MIXED",
            structure_state="BROKEN_STRUCTURE",
            liquidity_pressure_state="BOTH",
            flow_state="DIVERGENT",
            reaction={"liquidity_above_taken": True, "liquidity_below_taken": True, "buy_pressure_failed": True, "sell_pressure_failed": True},
        )
    )
    assert out["active_scenario"] == "CONFLICTED_SCENARIO"


def test_no_active_scenario_selected() -> None:
    out = _select(
        _evidence(
            market_regime="UNKNOWN",
            trend_state="UNKNOWN",
            volatility_state="UNKNOWN",
            structure_state="UNKNOWN",
            liquidity_pressure_state="UNKNOWN",
            flow_state="UNKNOWN",
            maturity_state="UNKNOWN",
            risk_state="NO_TRADE",
        ),
        data_quality="INVALID",
    )
    assert out["active_scenario"] == "NO_ACTIVE_SCENARIO"


def test_missing_market_state_no_crash() -> None:
    out = _select(_evidence(), market_state_present=False)
    assert "scenario_confidence" in out


def test_selected_scenario_feeds_next() -> None:
    out = _select(_evidence())
    assert out["feeds_next"] == [
        "PHASE_4_FLOW_CONFIRMATION_POST_LIQUIDITY_REACTION",
        "PHASE_5_SETUP_CANDIDATE_ENTRY_TRIGGER",
        "PHASE_8_CONDITIONAL_EDGE_MATRIX",
        "PHASE_10_NOVA_BRAIN_SNAPSHOT",
    ]

