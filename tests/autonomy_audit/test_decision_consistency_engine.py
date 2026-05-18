from __future__ import annotations

from src.autonomy_audit.decision_consistency_engine import evaluate_decision_consistency


def test_replay_validation_and_decision_quality_are_calculated() -> None:
    result = evaluate_decision_consistency(
        lineage_audit={"missing_source": []},
        trade_decision={"decision_status": "ALLOW_PAPER"},
        replay_engine={"replay_status": "REPLAY_SUCCESS", "counterfactual_summary": {"scenario_count": 5}},
        nova_brain={"system_health": {"status": "HEALTHY"}, "decision_quality_overview": {"status": "STABLE"}},
        probabilistic_engine={"dominant_path": {"estimated_probability": 0.4}, "scenario_pressure_map": {"pressure_level": "NORMAL"}},
        perspective_merger={"alignment_status": "FULL_ALIGNMENT", "data_quality": "OK"},
        edge_matrix={"edge_eligible_outcome_count": 12},
    )
    assert result["replay_validation"]["score"] is not None
    assert result["decision_quality"]["score"] is not None
