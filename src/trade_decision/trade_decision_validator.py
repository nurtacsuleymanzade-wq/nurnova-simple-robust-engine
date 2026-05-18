from __future__ import annotations

from datetime import datetime
from typing import Any

from .trade_decision_registry import (
    DATA_QUALITY,
    DECISION_STATUSES,
    ENTRY_MODELS,
    PLAN_QUALITY,
    REQUIRED_FIELDS,
    RISK_GRADES,
    SIDES,
)


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def _is_number_or_none(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, (int, float))


def validate_trade_decision(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")

    if not payload.get("trade_plan_id"):
        errors.append("MISSING_TRADE_PLAN_ID")
    if not payload.get("decision_id"):
        errors.append("MISSING_DECISION_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")

    if payload.get("side") not in SIDES:
        errors.append("INVALID_SIDE_ENUM")
    if payload.get("entry_model") not in ENTRY_MODELS:
        errors.append("INVALID_ENTRY_MODEL_ENUM")
    if payload.get("risk_grade") not in RISK_GRADES:
        errors.append("INVALID_RISK_GRADE_ENUM")
    if payload.get("decision_status") not in DECISION_STATUSES:
        errors.append("INVALID_DECISION_STATUS_ENUM")
    if payload.get("plan_quality") not in PLAN_QUALITY:
        errors.append("INVALID_PLAN_QUALITY_ENUM")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")

    dc = payload.get("decision_confidence")
    if not isinstance(dc, (int, float)) or dc < 0.0 or dc > 1.0:
        errors.append("INVALID_DECISION_CONFIDENCE_RANGE")

    if not _is_number_or_none(payload.get("rr_to_tp1")):
        errors.append("INVALID_RR_TO_TP1_TYPE")
    if not _is_number_or_none(payload.get("rr_to_tp2")):
        errors.append("INVALID_RR_TO_TP2_TYPE")

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
    if not isinstance(payload.get("entry_reason_codes"), list):
        errors.append("ENTRY_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("sl_reason_codes"), list):
        errors.append("SL_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("tp_reason_codes"), list):
        errors.append("TP_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("invalidation_reason_codes"), list):
        errors.append("INVALIDATION_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("blocking_reason_codes"), list):
        errors.append("BLOCKING_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("risk_reason_codes"), list):
        errors.append("RISK_REASON_CODES_NOT_LIST")
    if not isinstance(payload.get("warnings"), list):
        errors.append("WARNINGS_NOT_LIST")
    if not isinstance(payload.get("position_policy"), dict):
        errors.append("POSITION_POLICY_NOT_DICT")

    if payload.get("decision_status") == "ALLOW_PAPER":
        if payload.get("entry_price") is None:
            errors.append("ALLOW_PAPER_REQUIRES_ENTRY_PRICE")
        if payload.get("stop_loss") is None:
            errors.append("ALLOW_PAPER_REQUIRES_STOP_LOSS")
        if payload.get("take_profit_1") is None:
            errors.append("ALLOW_PAPER_REQUIRES_TAKE_PROFIT_1")
        if payload.get("invalidation_level") is None:
            errors.append("ALLOW_PAPER_REQUIRES_INVALIDATION_LEVEL")
        rr = payload.get("rr_to_tp1")
        if not isinstance(rr, (int, float)) or rr <= 0:
            errors.append("ALLOW_PAPER_REQUIRES_POSITIVE_RR")

    policy = payload.get("position_policy")
    if isinstance(policy, dict):
        if policy.get("real_trade_allowed") is not False:
            errors.append("REAL_TRADE_ALLOWED_MUST_BE_FALSE")

    return {"is_valid": len(errors) == 0, "errors": errors}
