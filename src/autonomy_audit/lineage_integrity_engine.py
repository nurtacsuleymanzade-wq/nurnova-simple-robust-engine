from __future__ import annotations

from typing import Any

from .autonomy_registry import SAFETY_STATUS, clamp, safety_status_from_positive_score


def evaluate_lineage_integrity(
    lineage_audit: dict[str, Any] | None,
    lineage_repair: dict[str, Any] | None,
    edge_mapping: dict[str, Any] | None,
) -> dict[str, Any]:
    lineage_audit = lineage_audit or {}
    lineage_repair = lineage_repair or {}
    edge_mapping = edge_mapping or {}

    if not lineage_audit and not lineage_repair and not edge_mapping:
        return {
            "status": "UNKNOWN",
            "score": None,
            "orphan_pressure": None,
            "invalid_edge_lineage_ratio": None,
            "deterministic_id_consistency": None,
            "historical_backlog_risk": None,
            "reason_codes": ["UNKNOWN_AUTONOMY_STATE"],
        }

    total_nodes = max(int(lineage_audit.get("total_nodes") or 0), 1)
    orphan_outcomes = len(lineage_audit.get("orphan_outcomes") or [])
    orphan_edges = len(lineage_audit.get("orphan_edge_rows") or [])
    critical_missing = len(lineage_audit.get("critical_missing_fields") or [])
    non_det_risks = len(lineage_audit.get("non_deterministic_id_risks") or [])
    repair_non_det = int(lineage_repair.get("non_deterministic_id_risks_total") or 0)
    edge_rows_total = max(int(lineage_repair.get("edge_rows_total") or edge_mapping.get("edge_rows_before") or 0), 1)
    invalid_edges = int(
        lineage_repair.get("edge_rows_invalid_without_closed_outcome")
        or edge_mapping.get("edge_rows_invalid_without_closed_outcome")
        or 0
    )
    linked_edges = int(
        lineage_repair.get("edge_rows_linked_to_closed_outcome")
        or edge_mapping.get("edge_rows_linked_to_closed_outcome")
        or 0
    )
    orphan_pressure = clamp((orphan_outcomes + orphan_edges) / total_nodes)
    invalid_edge_ratio = clamp(invalid_edges / edge_rows_total)
    deterministic_id_consistency = clamp(1.0 - min(1.0, max(non_det_risks, repair_non_det) / 50.0))
    backlog_risk = clamp(max(invalid_edge_ratio, min(1.0, orphan_outcomes / 50.0)))

    score = 1.0
    if str(lineage_audit.get("lineage_health_status") or "UNKNOWN").upper() == "FAIL":
        score -= 0.45
    elif str(lineage_audit.get("lineage_health_status") or "UNKNOWN").upper() == "PARTIAL":
        score -= 0.2
    if str(lineage_audit.get("outcome_to_edge_link_status") or "UNKNOWN").upper() == "FAIL":
        score -= 0.25
    elif str(lineage_audit.get("outcome_to_edge_link_status") or "UNKNOWN").upper() == "PARTIAL":
        score -= 0.12
    score -= min(0.15, orphan_pressure * 0.2)
    score -= min(0.1, invalid_edge_ratio * 0.2)
    score -= min(0.1, critical_missing / total_nodes)
    score -= min(0.1, max(non_det_risks, repair_non_det) / 100.0)
    score = clamp(score)
    status = safety_status_from_positive_score(score)
    if str(lineage_audit.get("lineage_health_status") or "").upper() == "FAIL":
        status = "FAIL"

    reason_codes = [
        f"LINEAGE_HEALTH_{str(lineage_audit.get('lineage_health_status') or 'UNKNOWN').upper()}",
        f"OUTCOME_EDGE_LINK_{str(lineage_audit.get('outcome_to_edge_link_status') or edge_mapping.get('outcome_to_edge_link_status') or 'UNKNOWN').upper()}",
    ]
    if non_det_risks or repair_non_det:
        reason_codes.append("NON_DETERMINISTIC_ID_RISK_PRESENT")
    if invalid_edges > 0:
        reason_codes.append("INVALID_EDGE_LINEAGE_PRESENT")

    assert status in SAFETY_STATUS
    return {
        "status": status,
        "score": score,
        "orphan_pressure": orphan_pressure,
        "invalid_edge_lineage_ratio": invalid_edge_ratio,
        "deterministic_id_consistency": deterministic_id_consistency,
        "historical_backlog_risk": backlog_risk,
        "linked_closed_edges": linked_edges,
        "invalid_edge_rows": invalid_edges,
        "reason_codes": reason_codes,
    }
