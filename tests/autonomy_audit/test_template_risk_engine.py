from __future__ import annotations

from src.autonomy_audit.template_risk_engine import evaluate_template_risk


def test_template_risk_score_is_calculated() -> None:
    result = evaluate_template_risk(
        {
            "entry_model": "RETEST",
            "decision_status": "BLOCK",
            "plan_quality": "INVALID",
            "stop_loss": None,
            "take_profit_1": None,
            "take_profit_2": None,
            "invalidation_level": None,
        },
        {
            "setup_quality": "C",
            "entry_trigger_quality": "LOW",
            "entry_trigger_status": "TRIGGER_INVALID",
            "setup_confidence": 0.35,
            "entry_trigger_confidence": 0.34,
        },
    )
    assert result["score"] is not None
    assert 0.0 <= result["score"] <= 1.0
