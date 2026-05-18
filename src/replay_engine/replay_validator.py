from __future__ import annotations

from datetime import datetime
from typing import Any

from .replay_registry import DATA_QUALITY, DECISION_QUALITY, REPLAY_SCENARIOS, REPLAY_STATUS, REQUIRED_FIELDS


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def validate_replay_output(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")
    if not payload.get("replay_batch_id"):
        errors.append("MISSING_REPLAY_BATCH_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")
    if not payload.get("source_outcome_id"):
        errors.append("MISSING_SOURCE_OUTCOME_ID")
    if not isinstance(payload.get("replay_scenarios"), list):
        errors.append("REPLAY_SCENARIOS_NOT_LIST")
    if payload.get("decision_quality") not in DECISION_QUALITY:
        errors.append("INVALID_DECISION_QUALITY_ENUM")
    if payload.get("replay_status") not in REPLAY_STATUS:
        errors.append("INVALID_REPLAY_STATUS_ENUM")
    if not (payload.get("decision_quality_score") is None or isinstance(payload.get("decision_quality_score"), (int, float))):
        errors.append("INVALID_DECISION_QUALITY_SCORE")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")

    for scenario in payload.get("replay_scenarios") or []:
        if not scenario.get("scenario_id"):
            errors.append("SCENARIO_ID_MISSING")
        if scenario.get("scenario_type") not in REPLAY_SCENARIOS:
            errors.append("INVALID_SCENARIO_TYPE_ENUM")

    if payload.get("replay_status") != "NO_REPLAY_DATA":
        if payload.get("source_is_closed_outcome") is not True:
            errors.append("REPLAY_SOURCE_NOT_CLOSED")
        if payload.get("source_edge_eligible") is not True:
            errors.append("REPLAY_SOURCE_NOT_EDGE_ELIGIBLE")

    return {"is_valid": len(errors) == 0, "errors": errors}
