from __future__ import annotations

from src.autonomy_audit.hallucination_risk_engine import evaluate_hallucination_risk


def test_hallucination_risk_score_is_calculated() -> None:
    result = evaluate_hallucination_risk(
        trade_decision={"decision_confidence": 0.0},
        paper_outcome={},
        edge_matrix={"source_outcome_count": 10, "edge_eligible_outcome_count": 0},
        replay_engine={"replay_status": "NO_REPLAY_DATA"},
        nova_brain={"dominant_market_story": {"market_bias": "LONG"}, "decision_quality_overview": {"status": "UNKNOWN"}},
        probabilistic_engine={"dominant_path": {"estimated_probability": 0.7}, "fake_breakout_probabilities": {"probability": 0.6}},
        perspective_merger={"reason_codes": ["MISSING_PERSPECTIVE"]},
    )
    assert result["score"] is not None
    assert 0.0 <= result["score"] <= 1.0
