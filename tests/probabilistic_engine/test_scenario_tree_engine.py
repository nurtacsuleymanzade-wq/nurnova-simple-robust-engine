from __future__ import annotations

from src.probabilistic_engine.scenario_tree_engine import build_scenario_tree


def test_scenario_tree_is_created() -> None:
    future_paths = [
        {
            "path_id": "PTH_A",
            "scenario_path": "BULLISH_CONTINUATION_PATH",
            "probability_band": "HIGH",
            "estimated_probability": 0.7,
            "risk_level": "CAUTION",
            "expected_behavior": "continuation",
        },
        {
            "path_id": "PTH_B",
            "scenario_path": "FAKE_BREAKOUT_PATH",
            "probability_band": "MEDIUM",
            "estimated_probability": 0.35,
            "risk_level": "DANGEROUS",
            "expected_behavior": "fake breakout",
        },
    ]
    result = build_scenario_tree(future_paths, future_paths[0])
    assert result["branch_count"] == 2
    assert result["dominant_branch"]["scenario_path"] == "BULLISH_CONTINUATION_PATH"

