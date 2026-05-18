from __future__ import annotations

from datetime import datetime
from typing import Any

from .active_scenario_registry import ACTIVE_SCENARIOS, DATA_QUALITY, REQUIRED_FIELDS, SCENARIO_BIASES, SCENARIO_QUALITY


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def validate_active_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for key in REQUIRED_FIELDS:
        if key not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{key}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")
    if not payload.get("active_scenario_id"):
        errors.append("MISSING_ACTIVE_SCENARIO_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")

    if payload.get("active_scenario") not in ACTIVE_SCENARIOS:
        errors.append("INVALID_ACTIVE_SCENARIO")
    if payload.get("scenario_bias") not in SCENARIO_BIASES:
        errors.append("INVALID_SCENARIO_BIAS")
    if payload.get("scenario_quality") not in SCENARIO_QUALITY:
        errors.append("INVALID_SCENARIO_QUALITY")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY")

    conf = payload.get("scenario_confidence")
    if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
        errors.append("INVALID_SCENARIO_CONFIDENCE_RANGE")

    if not isinstance(payload.get("selection_reason_codes"), list):
        errors.append("SELECTION_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("rejection_reason_codes"), list):
        errors.append("REJECTION_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("conflict_reason_codes"), list):
        errors.append("CONFLICT_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("scenario_candidates"), list):
        errors.append("SCENARIO_CANDIDATES_NOT_LIST")
    if not isinstance(payload.get("selected_candidate"), dict):
        errors.append("SELECTED_CANDIDATE_NOT_DICT")
    if not isinstance(payload.get("evidence"), dict):
        errors.append("EVIDENCE_NOT_DICT")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("warnings"), list):
        errors.append("WARNINGS_NOT_LIST")
    if not isinstance(payload.get("parent_lineage_ids"), list):
        errors.append("PARENT_LINEAGE_IDS_NOT_LIST")

    if not payload.get("market_state_id"):
        reason_codes = payload.get("reason_codes") or []
        if not isinstance(reason_codes, list) or "MARKET_STATE_MISSING" not in reason_codes:
            errors.append("MARKET_STATE_ID_MISSING_WITHOUT_REASON_CODE")

    return {"is_valid": len(errors) == 0, "errors": errors}

