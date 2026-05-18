from __future__ import annotations

from typing import Any

from .scenario_registry import DATA_QUALITY, PROBABILITY_BANDS, REQUIRED_FIELDS, RISK_PATH_LEVELS, SCENARIO_PATHS


def _is_probability(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return 0.0 <= float(value) <= 1.0


def validate_probabilistic_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not payload.get("scenario_engine_id"):
        errors.append("MISSING_SCENARIO_ENGINE_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")
    if not isinstance(payload.get("future_paths"), list):
        errors.append("FUTURE_PATHS_NOT_LIST")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")

    for item in payload.get("future_paths") or []:
        if item.get("scenario_path") not in SCENARIO_PATHS:
            errors.append("INVALID_SCENARIO_PATH_ENUM")
        if item.get("probability_band") not in PROBABILITY_BANDS:
            errors.append("INVALID_PROBABILITY_BAND_ENUM")
        if item.get("risk_level") not in RISK_PATH_LEVELS:
            errors.append("INVALID_RISK_LEVEL_ENUM")
        if not _is_probability(item.get("estimated_probability")):
            errors.append("INVALID_ESTIMATED_PROBABILITY")
        if not _is_probability(item.get("continuation_survival_probability")):
            errors.append("INVALID_CONTINUATION_SURVIVAL_PROBABILITY")
        if not _is_probability(item.get("fake_breakout_probability")):
            errors.append("INVALID_FAKE_BREAKOUT_PROBABILITY")

    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")

    return {"is_valid": len(errors) == 0, "errors": errors}
