from __future__ import annotations

from typing import Any

from .brain_registry import EDGE_TREND


def _classify_row(row: dict[str, Any]) -> str:
    status = str(row.get("edge_status") or "UNKNOWN").upper()
    expectancy = row.get("expectancy_r")
    sample = int(row.get("sample_size") or 0)
    if status in {"STRONG_EDGE_CANDIDATE", "TRADEABLE_EDGE_CANDIDATE"}:
        return "GROWING"
    if status == "WATCHLIST_EDGE" and sample >= 10 and (expectancy or 0) > 0:
        return "STABLE"
    if status in {"NEGATIVE_EDGE", "DEGRADED_BY_DATA_QUALITY"} or ((expectancy or 0) < 0 and sample >= 10):
        return "DECAYING"
    if status in {"NO_DATA", "INSUFFICIENT_SAMPLE"} or (sample == 0):
        return "DEAD"
    return "UNKNOWN"


def analyze_edge_intelligence(edge_matrix: dict[str, Any] | None) -> dict[str, Any]:
    rows = list((edge_matrix or {}).get("conditional_edge_rows") or [])
    growing_edges: list[dict[str, Any]] = []
    stable_edges: list[dict[str, Any]] = []
    decaying_edges: list[dict[str, Any]] = []
    dead_edges: list[dict[str, Any]] = []

    for row in rows:
        kind = _classify_row(row)
        compact = {
            "edge_row_id": row.get("edge_row_id"),
            "group_key": row.get("group_key"),
            "expectancy_r": row.get("expectancy_r"),
            "sample_size": row.get("sample_size"),
            "edge_status": row.get("edge_status"),
        }
        assert kind in EDGE_TREND
        if kind == "GROWING":
            growing_edges.append(compact)
        elif kind == "STABLE":
            stable_edges.append(compact)
        elif kind == "DECAYING":
            decaying_edges.append(compact)
        elif kind == "DEAD":
            dead_edges.append(compact)

    strong_clusters = sorted(growing_edges, key=lambda item: ((item.get("expectancy_r") or 0.0), item.get("sample_size") or 0), reverse=True)[:5]
    fake_edge_density = round(len(decaying_edges) / len(rows), 4) if rows else 0.0

    return {
        "growing_edges": growing_edges,
        "stable_edges": stable_edges,
        "decaying_edges": decaying_edges,
        "dead_edges": dead_edges,
        "strong_clusters": strong_clusters,
        "fake_edge_density": fake_edge_density,
        "total_edge_rows": len(rows),
    }
