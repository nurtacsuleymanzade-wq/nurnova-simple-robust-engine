from __future__ import annotations

from src.autonomy_audit.lineage_integrity_engine import evaluate_lineage_integrity


def test_lineage_integrity_score_is_calculated() -> None:
    result = evaluate_lineage_integrity(
        {
            "lineage_health_status": "PARTIAL",
            "outcome_to_edge_link_status": "PARTIAL",
            "total_nodes": 100,
            "orphan_outcomes": [1, 2],
            "orphan_edge_rows": [1],
            "critical_missing_fields": [1, 2],
            "non_deterministic_id_risks": [1],
        },
        {"edge_rows_total": 10, "edge_rows_invalid_without_closed_outcome": 2, "edge_rows_linked_to_closed_outcome": 8},
        {},
    )
    assert result["score"] is not None
    assert 0.0 <= result["score"] <= 1.0
