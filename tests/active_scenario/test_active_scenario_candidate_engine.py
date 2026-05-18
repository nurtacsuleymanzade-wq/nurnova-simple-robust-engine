from __future__ import annotations

from src.active_scenario.active_scenario_candidate_engine import build_scenario_candidates


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


def _score(candidates: list[dict], scenario: str) -> float:
    for c in candidates:
        if c["scenario"] == scenario:
            return float(c["normalized_score"])
    return 0.0


def test_bullish_continuation_candidate_generated() -> None:
    candidates, _ = build_scenario_candidates(_evidence(), "OK")
    assert _score(candidates, "BULLISH_CONTINUATION") > 0.5


def test_bearish_continuation_candidate_generated() -> None:
    candidates, _ = build_scenario_candidates(
        _evidence(
            market_regime="DOWNTREND",
            trend_state="BEARISH",
            structure_state="LH_LL",
            liquidity_pressure_state="BELOW",
            flow_state="SELL_PRESSURE",
        ),
        "OK",
    )
    assert _score(candidates, "BEARISH_CONTINUATION") > 0.5

