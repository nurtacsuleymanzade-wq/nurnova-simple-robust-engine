from __future__ import annotations

from src.probabilistic_engine.probability_cluster_engine import build_probability_clusters


def test_probability_cluster_is_created() -> None:
    clusters = build_probability_clusters(
        edge_matrix={"top_positive_edges": [{"edge_row_id": "E1"}]},
        replay_engine={"decision_quality": "GOOD"},
        market_state={"trend_state": "UP", "market_regime": "TREND", "liquidity_pressure_state": "UP"},
        active_scenario={"active_scenario": "BULLISH_CONTINUATION", "scenario_bias": "LONG"},
        flow_reaction={"flow_confirmation": "CONFIRMED", "post_liquidity_reaction": "CLEAN_BREAKOUT", "trap_state": "NONE", "absorption_state": "NONE"},
        nova_brain={"fake_scenario_pressure": {"pressure_level": "NORMAL"}},
    )
    assert len(clusters) == 4
    assert any(item["cluster_type"] == "CONTINUATION_CLUSTER" for item in clusters)

