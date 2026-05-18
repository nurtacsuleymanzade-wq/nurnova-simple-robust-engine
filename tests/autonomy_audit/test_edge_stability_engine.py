from __future__ import annotations

from src.autonomy_audit.edge_stability_engine import evaluate_edge_stability


def test_edge_stability_score_is_calculated() -> None:
    result = evaluate_edge_stability(
        {
            "edge_eligible_outcome_count": 20,
            "conditional_edge_rows": [{"expectancy_r": 0.4}, {"expectancy_r": 0.2}],
            "reason_codes": [],
        },
        {"edge_growth": {"dead_edges": [], "decaying_edges": []}, "edge_decay": {"fake_edge_density": 0.1}},
    )
    assert result["edge_stability"]["score"] is not None
    assert 0.0 <= result["edge_stability"]["score"] <= 1.0
