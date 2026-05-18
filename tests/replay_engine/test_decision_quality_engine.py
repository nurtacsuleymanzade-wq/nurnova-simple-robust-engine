from __future__ import annotations

from src.replay_engine.decision_quality_engine import evaluate_decision_quality
from src.replay_engine.replay_scenario_engine import generate_replay_scenarios


def _source(r: float, fate: str = "TP2_HIT") -> dict:
    return {"outcome_id": "OUT_1", "trade_fate": fate, "r_multiple": r}


def test_decision_quality_score_is_calculated() -> None:
    result = evaluate_decision_quality(_source(1.5), generate_replay_scenarios(_source(1.5)))
    assert isinstance(result["decision_quality_score"], float)


def test_excellent_decision_quality_is_possible() -> None:
    result = evaluate_decision_quality(
        _source(2.0),
        generate_replay_scenarios(_source(2.0)),
        trade_decision={"risk_grade": "LOW"},
    )
    assert result["decision_quality"] in {"EXCELLENT", "GOOD"}


def test_poor_or_terrible_decision_quality_is_possible() -> None:
    result = evaluate_decision_quality(
        _source(-1.0, fate="SL_HIT"),
        generate_replay_scenarios(_source(-1.0, fate="SL_HIT")),
        trade_decision={"risk_grade": "HIGH"},
    )
    assert result["decision_quality"] in {"POOR", "TERRIBLE"}
