from __future__ import annotations

from typing import Any

from .autonomy_registry import AUTONOMY_STATUS, DATA_QUALITY, HUMAN_OVERRIDE, REQUIRED_FIELDS, RISK_LEVEL, SAFETY_STATUS


def validate_autonomy_audit(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not payload.get("autonomy_audit_id"):
        errors.append("MISSING_AUTONOMY_AUDIT_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")
    if payload.get("autonomy_status") not in AUTONOMY_STATUS:
        errors.append("INVALID_AUTONOMY_STATUS_ENUM")
    score = payload.get("autonomy_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not (0.0 <= float(score) <= 1.0):
        errors.append("INVALID_AUTONOMY_SCORE")
    if not isinstance(payload.get("safe_for_autonomy"), bool):
        errors.append("SAFE_FOR_AUTONOMY_NOT_BOOL")
    if payload.get("human_override_required") not in HUMAN_OVERRIDE:
        errors.append("INVALID_HUMAN_OVERRIDE_ENUM")
    if payload.get("global_risk_level") not in RISK_LEVEL:
        errors.append("INVALID_GLOBAL_RISK_LEVEL_ENUM")

    for field in (
        "lineage_integrity",
        "edge_stability",
        "replay_validation",
        "template_risk",
        "hallucination_risk",
    ):
        if not isinstance(payload.get(field), dict):
            errors.append(f"{field.upper()}_NOT_DICT")
        elif payload[field].get("status") not in SAFETY_STATUS:
            errors.append(f"INVALID_{field.upper()}_STATUS_ENUM")

    for field in (
        "critical_failures",
        "autonomy_blockers",
        "safety_constraints",
        "recommended_human_controls",
        "reason_codes",
        "feeds_next",
    ):
        if not isinstance(payload.get(field), list):
            errors.append(f"{field.upper()}_NOT_LIST")

    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")

    return {"is_valid": len(errors) == 0, "errors": errors}
