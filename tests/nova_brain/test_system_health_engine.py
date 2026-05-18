from __future__ import annotations

from src.nova_brain.system_health_engine import evaluate_system_health


def test_system_health_is_computed() -> None:
    result = evaluate_system_health(
        {
            "market_state": {"data_quality": "OK"},
            "edge_matrix": {"data_quality": "OK"},
        },
        report_files_count=2,
        live_files_count=2,
    )
    assert result["status"] in {"HEALTHY", "STRESSED", "DEGRADED", "CRITICAL"}


def test_degraded_component_is_detected() -> None:
    result = evaluate_system_health(
        {
            "market_state": {"data_quality": "DEGRADED"},
            "edge_matrix": None,
        },
        report_files_count=0,
        live_files_count=1,
    )
    assert "market_state" in result["degraded_components"]
    assert "edge_matrix" in result["degraded_components"]
