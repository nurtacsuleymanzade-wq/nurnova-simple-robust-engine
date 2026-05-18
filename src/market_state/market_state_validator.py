from __future__ import annotations

from datetime import datetime
from typing import Any

from .market_state_registry import (
    AUCTION_STATES,
    DATA_QUALITY_STATES,
    FLOW_STATES,
    LIQUIDITY_PRESSURE_STATES,
    MARKET_REGIMES,
    MATURITY_STATES,
    REQUIRED_FIELDS,
    RISK_STATES,
    STRUCTURE_STATES,
    TREND_STATES,
    VOLATILITY_STATES,
)


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def validate_market_state(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")
    if not payload.get("market_state_id"):
        errors.append("MISSING_MARKET_STATE_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")
    if not isinstance(payload.get("parent_lineage_ids"), list):
        errors.append("PARENT_LINEAGE_IDS_NOT_LIST")

    if payload.get("market_regime") not in MARKET_REGIMES:
        errors.append("INVALID_MARKET_REGIME")
    if payload.get("trend_state") not in TREND_STATES:
        errors.append("INVALID_TREND_STATE")
    if payload.get("volatility_state") not in VOLATILITY_STATES:
        errors.append("INVALID_VOLATILITY_STATE")
    if payload.get("structure_state") not in STRUCTURE_STATES:
        errors.append("INVALID_STRUCTURE_STATE")
    if payload.get("liquidity_pressure_state") not in LIQUIDITY_PRESSURE_STATES:
        errors.append("INVALID_LIQUIDITY_PRESSURE_STATE")
    if payload.get("auction_state") not in AUCTION_STATES:
        errors.append("INVALID_AUCTION_STATE")
    if payload.get("flow_state") not in FLOW_STATES:
        errors.append("INVALID_FLOW_STATE")
    if payload.get("maturity_state") not in MATURITY_STATES:
        errors.append("INVALID_MATURITY_STATE")
    if payload.get("risk_state") not in RISK_STATES:
        errors.append("INVALID_RISK_STATE")

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        errors.append("INVALID_CONFIDENCE_RANGE")

    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")
    if payload.get("data_quality") not in DATA_QUALITY_STATES:
        errors.append("INVALID_DATA_QUALITY")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")

    confidence_components = payload.get("confidence_components")
    if not isinstance(confidence_components, dict):
        errors.append("CONFIDENCE_COMPONENTS_NOT_OBJECT")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("EVIDENCE_NOT_OBJECT")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
    }

