from __future__ import annotations

from datetime import datetime
from typing import Any

from .edge_matrix_registry import DATA_QUALITY, EDGE_STATUSES, EXCLUDED_TOKENS, REQUIRED_FIELDS


def _is_iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return False
    return True


def _is_number_or_none(value: Any) -> bool:
    return value is None or isinstance(value, (int, float))


def validate_conditional_edge_matrix(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"MISSING_REQUIRED_FIELD:{field}")

    if not _is_iso(payload.get("timestamp_utc")):
        errors.append("INVALID_TIMESTAMP_UTC")
    if not payload.get("edge_matrix_id"):
        errors.append("MISSING_EDGE_MATRIX_ID")
    if not payload.get("lineage_id"):
        errors.append("MISSING_LINEAGE_ID")
    if not isinstance(payload.get("source_outcome_count"), int):
        errors.append("SOURCE_OUTCOME_COUNT_NOT_INT")
    if not isinstance(payload.get("edge_eligible_outcome_count"), int):
        errors.append("EDGE_ELIGIBLE_OUTCOME_COUNT_NOT_INT")
    if not isinstance(payload.get("conditional_edge_rows"), list):
        errors.append("CONDITIONAL_EDGE_ROWS_NOT_LIST")
    if payload.get("data_quality") not in DATA_QUALITY:
        errors.append("INVALID_DATA_QUALITY_ENUM")
    if not isinstance(payload.get("feeds_next"), list):
        errors.append("FEEDS_NEXT_NOT_LIST")
    if not isinstance(payload.get("reason_codes"), list):
        errors.append("REASON_CODES_NOT_LIST")

    for row in payload.get("conditional_edge_rows") or []:
        if not row.get("edge_row_id"):
            errors.append("EDGE_ROW_MISSING_ID")
        if row.get("edge_status") not in EDGE_STATUSES:
            errors.append("INVALID_EDGE_STATUS_ENUM")
        if not isinstance(row.get("sample_size"), int):
            errors.append("EDGE_ROW_SAMPLE_SIZE_NOT_INT")
        winrate = row.get("winrate")
        if not (winrate is None or (isinstance(winrate, (int, float)) and 0.0 <= winrate <= 1.0)):
            errors.append("EDGE_ROW_WINRATE_INVALID")
        if not _is_number_or_none(row.get("expectancy_r")):
            errors.append("EDGE_ROW_EXPECTANCY_INVALID")
        if not isinstance(row.get("source_outcome_ids"), list):
            errors.append("EDGE_ROW_SOURCE_OUTCOME_IDS_NOT_LIST")
        if not isinstance(row.get("source_paper_trade_ids"), list):
            errors.append("EDGE_ROW_SOURCE_PAPER_TRADE_IDS_NOT_LIST")

        forbidden_hits = []
        for source_id in row.get("source_outcome_ids") or []:
            upper = str(source_id).upper()
            if any(token in upper for token in EXCLUDED_TOKENS):
                forbidden_hits.append(upper)
        for trade_fate in row.get("source_trade_fates") or []:
            upper = str(trade_fate).upper()
            if any(token in upper for token in EXCLUDED_TOKENS):
                forbidden_hits.append(upper)
        if forbidden_hits:
            errors.append("FORBIDDEN_TIMEOUT_OR_NO_ENTRY_SOURCE_PRESENT")

    return {"is_valid": len(errors) == 0, "errors": errors}
