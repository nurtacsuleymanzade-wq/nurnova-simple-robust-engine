from __future__ import annotations

from typing import Any

from .perspective_merger_registry import (
    ALIGNMENT_STATUSES,
    BIAS_VALUES,
    DATA_QUALITY,
    REQUIRED_FIELDS,
)


def validate_perspective_merger(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not payload.get("perspective_merger_id"):
        errors.append("MISSING_PERSPECTIVE_MERGER_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")
    for field in ("core_bias", "smc_bias", "mm_bias"):
        if payload.get(field) not in BIAS_VALUES:
            errors.append(f"INVALID_{field.upper()}_ENUM")
    if payload.get("alignment_status") not in ALIGNMENT_STATUSES:
        errors.append("INVALID_ALIGNMENT_STATUS_ENUM")
    score = payload.get("alignment_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not (0.0 <= float(score) <= 1.0):
        errors.append("INVALID_ALIGNMENT_SCORE")
    if not isinstance(payload.get("perspective_agreement"), dict):
        errors.append("PERSPECTIVE_AGREEMENT_NOT_DICT")
    if not isinstance(payload.get("bias_conflicts"), list):
        errors.append("BIAS_CONFLICTS_NOT_LIST")
    if not isinstance(payload.get("conflict_sources"), list):
        errors.append("CONFLICT_SOURCES_NOT_LIST")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")
    reason_codes = set(str(item) for item in payload.get("reason_codes") or [])
    if payload.get("smc_bias") == "UNKNOWN" and "MISSING_SMC_PERSPECTIVE" not in reason_codes:
        errors.append("MISSING_SMC_REASON_CODE")
    if payload.get("mm_bias") == "UNKNOWN" and "MISSING_MM_PERSPECTIVE" not in reason_codes:
        errors.append("MISSING_MM_REASON_CODE")
    return {"is_valid": len(errors) == 0, "errors": errors}
