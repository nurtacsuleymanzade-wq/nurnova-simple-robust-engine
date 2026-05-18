from __future__ import annotations

from datetime import datetime
from typing import Any

from .paper_outcome_registry import (
    DATA_QUALITY,
    FORBIDDEN_OUTPUT_FIELDS,
    LIFECYCLE_STATES,
    OUTCOME_QUALITY,
    REQUIRED_FIELDS,
    SIDES,
    TRADE_FATES,
)


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def validate_paper_outcome(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")

    if not payload.get("paper_trade_id"):
        errors.append("MISSING_PAPER_TRADE_ID")
    if not payload.get("outcome_id"):
        errors.append("MISSING_OUTCOME_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")

    if not payload.get("trade_plan_id") and "MISSING_TRADE_PLAN_ID" not in (payload.get("reason_codes") or []):
        errors.append("MISSING_TRADE_PLAN_ID_WITHOUT_REASON")
    if not payload.get("decision_id") and "MISSING_DECISION_ID" not in (payload.get("reason_codes") or []):
        errors.append("MISSING_DECISION_ID_WITHOUT_REASON")

    if payload.get("side") not in SIDES:
        errors.append("INVALID_SIDE_ENUM")
    if payload.get("lifecycle_state") not in LIFECYCLE_STATES:
        errors.append("INVALID_LIFECYCLE_STATE_ENUM")
    if payload.get("trade_fate") not in TRADE_FATES:
        errors.append("INVALID_TRADE_FATE_ENUM")
    if payload.get("outcome_quality") not in OUTCOME_QUALITY:
        errors.append("INVALID_OUTCOME_QUALITY_ENUM")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")

    if not isinstance(payload.get("is_closed_outcome"), bool):
        errors.append("IS_CLOSED_OUTCOME_NOT_BOOL")
    if not isinstance(payload.get("edge_eligible"), bool):
        errors.append("EDGE_ELIGIBLE_NOT_BOOL")
    if not isinstance(payload.get("evidence"), dict):
        errors.append("EVIDENCE_NOT_DICT")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("parent_lineage_ids"), list):
        errors.append("PARENT_LINEAGE_IDS_NOT_LIST")
    if not isinstance(payload.get("warnings"), list):
        errors.append("WARNINGS_NOT_LIST")

    if payload.get("edge_eligible") is True and payload.get("is_closed_outcome") is not True:
        errors.append("EDGE_ELIGIBLE_REQUIRES_CLOSED_OUTCOME")
    if payload.get("edge_eligible") is True and payload.get("trade_fate") in {
        "NO_ACTIONABLE_DECISION",
        "NO_OPEN_PAPER_TRADE",
        "NO_ENTRY_TOUCH",
        "EXPIRED_NO_ENTRY",
        "DIAGNOSTIC_TIMEOUT",
        "INVALIDATED_BEFORE_ENTRY",
        "UNKNOWN",
        "ENTRY_FILLED",
    }:
        errors.append("EDGE_ELIGIBLE_INVALID_FOR_TRADE_FATE")

    for forbidden in FORBIDDEN_OUTPUT_FIELDS:
        if forbidden in payload:
            errors.append(f"FORBIDDEN_FIELD_PRESENT:{forbidden}")

    return {"is_valid": len(errors) == 0, "errors": errors}
