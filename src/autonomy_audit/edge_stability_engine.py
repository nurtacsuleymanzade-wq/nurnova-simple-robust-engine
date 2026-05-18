from __future__ import annotations

from typing import Any

from .autonomy_registry import SAFETY_STATUS, clamp, safety_status_from_positive_score


def evaluate_edge_stability(
    edge_matrix: dict[str, Any] | None,
    nova_brain: dict[str, Any] | None,
) -> dict[str, Any]:
    edge_matrix = edge_matrix or {}
    nova_brain = nova_brain or {}

    if not edge_matrix:
        return {
            "edge_stability": {"status": "UNKNOWN", "score": None, "reason_codes": ["UNKNOWN_AUTONOMY_STATE"]},
            "edge_decay_pressure": {"status": "UNKNOWN", "score": None, "reason_codes": ["UNKNOWN_AUTONOMY_STATE"]},
        }

    eligible = int(edge_matrix.get("edge_eligible_outcome_count") or 0)
    rows = list(edge_matrix.get("conditional_edge_rows") or [])
    no_data = "NO_DATA" in {str(code).upper() for code in (edge_matrix.get("reason_codes") or [])}
    fake_density = float(((nova_brain.get("edge_decay") or {}).get("fake_edge_density") or 0.0))
    dead_edges = len(((nova_brain.get("edge_growth") or {}).get("dead_edges") or []))
    decaying_edges = len(((nova_brain.get("edge_growth") or {}).get("decaying_edges") or []))

    if eligible == 0 or no_data:
        stability_score = 0.05
    else:
        sample_component = min(1.0, eligible / 50.0)
        rows_component = min(1.0, len(rows) / 20.0)
        expectancy_component = 0.5
        if rows:
            expectancy_values = [float(item.get("expectancy_r") or 0.0) for item in rows if item.get("expectancy_r") is not None]
            if expectancy_values:
                expectancy_component = clamp(sum(1 for value in expectancy_values if value > 0) / len(expectancy_values))
        stability_score = clamp(sample_component * 0.45 + rows_component * 0.2 + expectancy_component * 0.35)

    decay_score = clamp(max(fake_density, min(1.0, (dead_edges + decaying_edges) / 10.0), 0.7 if no_data else 0.0))
    edge_stability_status = safety_status_from_positive_score(stability_score)
    if eligible == 0 or no_data:
        edge_stability_status = "FAIL"
    edge_decay_status = "PASS" if decay_score <= 0.25 else "PARTIAL" if decay_score <= 0.55 else "FAIL"

    assert edge_stability_status in SAFETY_STATUS
    assert edge_decay_status in SAFETY_STATUS
    return {
        "edge_stability": {
            "status": edge_stability_status,
            "score": stability_score,
            "sample_reliability": clamp(min(1.0, eligible / 30.0)),
            "edge_survival_consistency": clamp(1.0 - min(1.0, (dead_edges + decaying_edges) / 10.0)),
            "fake_edge_density": fake_density,
            "reason_codes": list(edge_matrix.get("reason_codes") or []),
        },
        "edge_decay_pressure": {
            "status": edge_decay_status,
            "score": decay_score,
            "dead_edges": dead_edges,
            "decaying_edges": decaying_edges,
            "fake_edge_density": fake_density,
            "reason_codes": [],
        },
    }
