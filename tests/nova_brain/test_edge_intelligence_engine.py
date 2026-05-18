from __future__ import annotations

from src.nova_brain.edge_intelligence_engine import analyze_edge_intelligence


def _edge_row(status: str, expectancy: float | None, sample: int) -> dict:
    return {
        "edge_row_id": f"EDR_{status}_{sample}",
        "group_key": {"pattern": "TEST"},
        "edge_status": status,
        "expectancy_r": expectancy,
        "sample_size": sample,
    }


def test_growing_edge_is_detected() -> None:
    result = analyze_edge_intelligence({"conditional_edge_rows": [_edge_row("STRONG_EDGE_CANDIDATE", 0.8, 50)]})
    assert len(result["growing_edges"]) == 1


def test_dead_edge_is_detected() -> None:
    result = analyze_edge_intelligence({"conditional_edge_rows": [_edge_row("NO_DATA", None, 0)]})
    assert len(result["dead_edges"]) == 1
