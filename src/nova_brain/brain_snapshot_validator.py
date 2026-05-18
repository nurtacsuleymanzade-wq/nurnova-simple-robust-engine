from __future__ import annotations

from typing import Any

from .brain_registry import (
    DATA_QUALITY,
    DECISION_QUALITY_OVERVIEW,
    REQUIRED_FIELDS,
    RISK_LEVEL,
    SCENARIO_PRESSURE,
    SYSTEM_HEALTH,
)


def validate_brain_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not payload.get("brain_snapshot_id"):
        errors.append("MISSING_BRAIN_SNAPSHOT_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")
    if not isinstance(payload.get("system_health"), dict):
        errors.append("SYSTEM_HEALTH_NOT_DICT")
    if not isinstance(payload.get("edge_growth"), dict):
        errors.append("EDGE_GROWTH_NOT_DICT")
    if not isinstance(payload.get("risk_map"), dict):
        errors.append("RISK_MAP_NOT_DICT")
    if not isinstance(payload.get("decision_quality_overview"), dict):
        errors.append("DECISION_QUALITY_OVERVIEW_NOT_DICT")
    if not isinstance(payload.get("operational_alerts"), list):
        errors.append("OPERATIONAL_ALERTS_NOT_LIST")
    if not isinstance(payload.get("brain_summary"), list):
        errors.append("BRAIN_SUMMARY_NOT_LIST")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")

    if isinstance(payload.get("system_health"), dict):
        if payload["system_health"].get("status") not in SYSTEM_HEALTH:
            errors.append("INVALID_SYSTEM_HEALTH_ENUM")
    if isinstance(payload.get("risk_map"), dict):
        if payload["risk_map"].get("global_risk_level") not in RISK_LEVEL:
            errors.append("INVALID_RISK_LEVEL_ENUM")
    if isinstance(payload.get("fake_scenario_pressure"), dict):
        if payload["fake_scenario_pressure"].get("pressure_level") not in SCENARIO_PRESSURE:
            errors.append("INVALID_SCENARIO_PRESSURE_ENUM")
    if isinstance(payload.get("decision_quality_overview"), dict):
        if payload["decision_quality_overview"].get("status") not in DECISION_QUALITY_OVERVIEW:
            errors.append("INVALID_DECISION_QUALITY_OVERVIEW_ENUM")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")

    return {"is_valid": len(errors) == 0, "errors": errors}
