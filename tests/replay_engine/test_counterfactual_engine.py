from __future__ import annotations

from src.replay_engine.counterfactual_engine import build_counterfactual_summary
from src.replay_engine.replay_scenario_engine import generate_replay_scenarios


def _outcome(r: float = -1.0, fate: str = "SL_HIT") -> dict:
    return {
        "outcome_id": "OUT_1",
        "trade_fate": fate,
        "r_multiple": r,
        "is_closed_outcome": True,
        "edge_eligible": True,
    }


def test_alternative_outcome_is_calculated() -> None:
    scenarios = generate_replay_scenarios(_outcome())
    no_trade = next(item for item in scenarios if item["scenario_type"] == "NO_TRADE")
    assert no_trade["alternative_outcome"]["trade_fate"] == "NO_TRADE"


def test_better_than_original_is_calculated() -> None:
    scenarios = generate_replay_scenarios(_outcome(r=-1.0))
    no_trade = next(item for item in scenarios if item["scenario_type"] == "NO_TRADE")
    assert no_trade["better_than_original"] is True


def test_worse_than_original_is_calculated() -> None:
    scenarios = generate_replay_scenarios(_outcome(r=1.0, fate="TP1_HIT"))
    late = next(item for item in scenarios if item["scenario_type"] == "LATE_ENTRY")
    assert late["worse_than_original"] is True


def test_counterfactual_summary_is_built() -> None:
    scenarios = generate_replay_scenarios(_outcome(r=-1.0))
    summary = build_counterfactual_summary(_outcome(r=-1.0), scenarios)
    assert "counterfactual_summary" in summary
    assert "learning_signals" in summary
