from __future__ import annotations

from datetime import datetime
from typing import Any

from .flow_reaction_registry import (
    ABSORPTION_STATES,
    DATA_QUALITY,
    FLOW_CONFIRMATIONS,
    POST_LIQUIDITY_REACTIONS,
    REACTION_BIASES,
    REACTION_QUALITY,
    REQUIRED_FIELDS,
    TRAP_STATES,
)


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def validate_flow_reaction(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for key in REQUIRED_FIELDS:
        if key not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{key}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")
    if not payload.get("flow_reaction_id"):
        errors.append("MISSING_FLOW_REACTION_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")

    if payload.get("flow_confirmation") not in FLOW_CONFIRMATIONS:
        errors.append("INVALID_FLOW_CONFIRMATION")
    if payload.get("post_liquidity_reaction") not in POST_LIQUIDITY_REACTIONS:
        errors.append("INVALID_POST_LIQUIDITY_REACTION")
    if payload.get("absorption_state") not in ABSORPTION_STATES:
        errors.append("INVALID_ABSORPTION_STATE")
    if payload.get("trap_state") not in TRAP_STATES:
        errors.append("INVALID_TRAP_STATE")
    if payload.get("reaction_bias") not in REACTION_BIASES:
        errors.append("INVALID_REACTION_BIAS")
    if payload.get("reaction_quality") not in REACTION_QUALITY:
        errors.append("INVALID_REACTION_QUALITY")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY")

    conf = payload.get("reaction_confidence")
    if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
        errors.append("INVALID_REACTION_CONFIDENCE_RANGE")

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
    if not isinstance(payload.get("confirmation_reason_codes"), list):
        errors.append("CONFIRMATION_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("rejection_reason_codes"), list):
        errors.append("REJECTION_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("trap_reason_codes"), list):
        errors.append("TRAP_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("absorption_reason_codes"), list):
        errors.append("ABSORPTION_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("conflict_reason_codes"), list):
        errors.append("CONFLICT_REASON_CODES_NOT_LIST")
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

    return {"is_valid": len(errors) == 0, "errors": errors}
