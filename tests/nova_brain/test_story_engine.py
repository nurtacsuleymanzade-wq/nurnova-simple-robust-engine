from __future__ import annotations

from src.nova_brain.story_engine import build_brain_story


def _story() -> dict:
    return build_brain_story(
        market_state={"market_regime": "RANGING"},
        active_scenario={"active_scenario": "RANGE_ROTATION_FAKE_BREAKOUT"},
        flow_reaction={"flow_confirmation": "NOT_CONFIRMED", "post_liquidity_reaction": "FAILED_BREAKOUT"},
        trade_decision={"side": "SHORT"},
        system_health={"status": "DEGRADED"},
        edge_intelligence={"growing_edges": [], "decaying_edges": [{"edge_row_id": "E1"}], "dead_edges": [{"edge_row_id": "E2"}], "fake_edge_density": 0.5},
        risk_intelligence={
            "risk_map": {"global_risk_level": "HIGH"},
            "fake_scenario_pressure": {"pressure_level": "DANGEROUS"},
            "decision_quality_overview": {"status": "POOR"},
        },
    )


def test_dominant_market_story_is_generated() -> None:
    result = _story()
    assert result["dominant_market_story"]["primary_story"] is not None


def test_operational_alert_is_generated() -> None:
    result = _story()
    assert len(result["operational_alerts"]) >= 1
