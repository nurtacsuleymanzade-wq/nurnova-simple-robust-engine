from __future__ import annotations

from datetime import datetime
from typing import Any

from .setup_entry_registry import (
    DATA_QUALITY,
    ENTRY_TRIGGER_QUALITY,
    ENTRY_TRIGGER_STATUSES,
    REQUIRED_FIELDS,
    SETUP_CANDIDATES,
    SETUP_DIRECTIONS,
    SETUP_QUALITY,
)


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def validate_setup_entry(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for key in REQUIRED_FIELDS:
        if key not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{key}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")
    if not payload.get("setup_candidate_id"):
        errors.append("MISSING_SETUP_CANDIDATE_ID")
    if not payload.get("entry_trigger_id"):
        errors.append("MISSING_ENTRY_TRIGGER_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")

    if payload.get("setup_candidate") not in SETUP_CANDIDATES:
        errors.append("INVALID_SETUP_CANDIDATE")
    if payload.get("setup_direction") not in SETUP_DIRECTIONS:
        errors.append("INVALID_SETUP_DIRECTION")
    if payload.get("setup_quality") not in SETUP_QUALITY:
        errors.append("INVALID_SETUP_QUALITY")
    if payload.get("entry_trigger_status") not in ENTRY_TRIGGER_STATUSES:
        errors.append("INVALID_ENTRY_TRIGGER_STATUS")
    if payload.get("entry_trigger_quality") not in ENTRY_TRIGGER_QUALITY:
        errors.append("INVALID_ENTRY_TRIGGER_QUALITY")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY")

    sc = payload.get("setup_confidence")
    if not isinstance(sc, (int, float)) or sc < 0.0 or sc > 1.0:
        errors.append("INVALID_SETUP_CONFIDENCE_RANGE")

    etc = payload.get("entry_trigger_confidence")
    if not isinstance(etc, (int, float)) or etc < 0.0 or etc > 1.0:
        errors.append("INVALID_ENTRY_TRIGGER_CONFIDENCE_RANGE")

    if not isinstance(payload.get("timeframe_context"), dict):
        errors.append("TIMEFRAME_CONTEXT_NOT_DICT")
    if not isinstance(payload.get("evidence"), dict):
        errors.append("EVIDENCE_NOT_DICT")
    if not isinstance(payload.get("scores"), dict):
        errors.append("SCORES_NOT_DICT")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("parent_lineage_ids"), list):
        errors.append("PARENT_LINEAGE_IDS_NOT_LIST")
    if not isinstance(payload.get("setup_reason_codes"), list):
        errors.append("SETUP_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("entry_trigger_reason_codes"), list):
        errors.append("ENTRY_TRIGGER_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("blocking_reason_codes"), list):
        errors.append("BLOCKING_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("conflict_reason_codes"), list):
        errors.append("CONFLICT_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("missing_evidence"), list):
        errors.append("MISSING_EVIDENCE_NOT_LIST")
    if not isinstance(payload.get("warnings"), list):
        errors.append("WARNINGS_NOT_LIST")

    if not payload.get("market_state_id"):
        reason_codes = payload.get("reason_codes") or []
        if not isinstance(reason_codes, list) or "MARKET_STATE_MISSING" not in reason_codes:
            errors.append("MARKET_STATE_ID_MISSING_WITHOUT_REASON_CODE")

    if not payload.get("active_scenario_id"):
        reason_codes = payload.get("reason_codes") or []
        if not isinstance(reason_codes, list) or "ACTIVE_SCENARIO_MISSING" not in reason_codes:
            errors.append("ACTIVE_SCENARIO_ID_MISSING_WITHOUT_REASON_CODE")

    if not payload.get("flow_reaction_id"):
        reason_codes = payload.get("reason_codes") or []
        if not isinstance(reason_codes, list) or "FLOW_REACTION_MISSING" not in reason_codes:
            errors.append("FLOW_REACTION_ID_MISSING_WITHOUT_REASON_CODE")

    return {"is_valid": len(errors) == 0, "errors": errors}
