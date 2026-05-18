from __future__ import annotations

from src.lineage.run_lineage_repair_audit import evaluate_edge_rows


def test_closed_outcome_edge_link_is_valid() -> None:
    outcomes = {
        "OUT_1": {
            "status": "CLOSED",
            "record": {"outcome_id": "OUT_1", "outcome_status": "CLOSED"},
        }
    }
    edges = [{"source_outcome_id": "OUT_1", "reason_codes": []}]
    evaluated = evaluate_edge_rows(edges, outcomes)
    assert evaluated[0]["edge_lineage_status"] == "VALID_EDGE_LINEAGE"
    assert evaluated[0]["linked_closed_outcome_id"] == "OUT_1"


def test_open_or_pending_outcome_not_linked() -> None:
    outcomes = {
        "OUT_OPEN": {
            "status": "OPEN",
            "record": {"outcome_id": "OUT_OPEN", "outcome_status": "OPEN"},
        }
    }
    edges = [{"source_outcome_id": "OUT_OPEN", "reason_codes": []}]
    evaluated = evaluate_edge_rows(edges, outcomes)
    assert evaluated[0]["edge_lineage_status"] == "INVALID_EDGE_LINEAGE"
    assert "EDGE_WITHOUT_CLOSED_OUTCOME" in evaluated[0]["reason_codes"]


def test_edge_without_closed_outcome_marked_invalid() -> None:
    evaluated = evaluate_edge_rows([{"edge_event_id": "EDGE_1", "reason_codes": []}], {})
    assert evaluated[0]["edge_lineage_status"] == "INVALID_EDGE_LINEAGE"
    assert "EDGE_WITHOUT_CLOSED_OUTCOME" in evaluated[0]["reason_codes"]

