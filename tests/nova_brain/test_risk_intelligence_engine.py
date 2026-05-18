from __future__ import annotations

from src.nova_brain.risk_intelligence_engine import analyze_risk_intelligence


def _risk_result() -> dict:
    return analyze_risk_intelligence(
        market_state={"market_regime": "CHOPPY", "volatility_state": "HIGH", "trend_state": "UP"},
        active_scenario={"active_scenario": "BREAKOUT_ATTEMPT"},
        flow_reaction={"flow_confirmation": "NOT_CONFIRMED", "post_liquidity_reaction": "FAILED_BREAKOUT", "trap_state": "BUYERS_TRAPPED"},
        trade_decision={"risk_grade": "HIGH", "decision_id": "DEC_1"},
        paper_outcome={"trade_fate": "SL_HIT", "data_quality": "OK"},
        edge_matrix={"data_quality": "DEGRADED"},
        replay_engine={"decision_quality": "POOR", "decision_quality_score": 0.2, "learning_signals": ["NO_TRADE_WOULD_HAVE_BEEN_BETTER"]},
        edge_intelligence={"growing_edges": [], "stable_edges": [], "decaying_edges": [{"edge_row_id": "EDR_1"}], "dead_edges": [], "fake_edge_density": 0.5},
    )


def test_fake_breakout_pressure_is_measured() -> None:
    result = _risk_result()
    assert result["fake_scenario_pressure"]["pressure_level"] in {"ELEVATED", "DANGEROUS", "EXTREME"}


def test_regime_risk_is_computed() -> None:
    result = _risk_result()
    assert result["risk_map"]["global_risk_level"] in {"MEDIUM", "HIGH", "EXTREME"}


def test_decision_quality_overview_is_computed() -> None:
    result = _risk_result()
    assert result["decision_quality_overview"]["status"] in {"WEAKENING", "POOR"}
