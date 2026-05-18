from __future__ import annotations

from src.probabilistic_engine.future_path_engine import build_future_paths


def _paths() -> tuple[list[dict], dict]:
    return build_future_paths(
        market_state={"volatility_state": "HIGH"},
        active_scenario={"active_scenario": "BULLISH_CONTINUATION", "scenario_bias": "LONG", "scenario_confidence": 0.72},
        flow_reaction={"flow_confirmation": "CONFIRMED", "post_liquidity_reaction": "BREAKOUT_HOLD"},
        edge_matrix={"top_positive_edges": [{"edge_row_id": "E1"}]},
        replay_engine={},
        nova_brain={"risk_map": {"global_risk_level": "MEDIUM"}},
        probability_clusters=[
            {"cluster_type": "CONTINUATION_CLUSTER", "estimated_probability": 0.66},
            {"cluster_type": "REVERSAL_CLUSTER", "estimated_probability": 0.24},
            {"cluster_type": "FAKE_BREAKOUT_CLUSTER", "estimated_probability": 0.31},
            {"cluster_type": "LIQUIDITY_SWEEP_CLUSTER", "estimated_probability": 0.28},
        ],
    )


def test_continuation_path_is_created() -> None:
    paths, _ = _paths()
    assert any(item["scenario_path"] == "BULLISH_CONTINUATION_PATH" for item in paths)


def test_reversal_path_is_created() -> None:
    paths, _ = _paths()
    assert any(item["scenario_path"] == "REVERSAL_PATH" for item in paths)


def test_fake_breakout_path_is_created() -> None:
    paths, _ = _paths()
    assert any(item["scenario_path"] == "FAKE_BREAKOUT_PATH" for item in paths)


def test_liquidity_sweep_path_is_created() -> None:
    paths, _ = _paths()
    assert any(item["scenario_path"] == "LIQUIDITY_SWEEP_PATH" for item in paths)


def test_continuation_survival_probability_is_calculated() -> None:
    paths, _ = _paths()
    continuation = next(item for item in paths if item["scenario_path"] == "BULLISH_CONTINUATION_PATH")
    assert continuation["continuation_survival_probability"] > 0


def test_fake_breakout_probability_is_calculated() -> None:
    paths, _ = _paths()
    fake = next(item for item in paths if item["scenario_path"] == "FAKE_BREAKOUT_PATH")
    assert fake["fake_breakout_probability"] > 0


def test_dominant_future_path_is_selected() -> None:
    _, dominant = _paths()
    assert dominant["scenario_path"] == "BULLISH_CONTINUATION_PATH"


def test_deterministic_path_id_is_stable() -> None:
    paths_one, _ = _paths()
    paths_two, _ = _paths()
    assert paths_one[0]["path_id"] == paths_two[0]["path_id"]

