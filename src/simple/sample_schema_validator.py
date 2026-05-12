"""S11.2 Sample Schema Validator — NOVA SIMPLE ROBUST ENGINE v1.

Validates replay_samples.jsonl structure integrity. Guards future VPS/live
research data from silently corrupting the edge research dataset.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S11_2_SAMPLE_SCHEMA_VALIDATOR"
FEEDS_NEXT = {"next_blocks": ["S11_REPLAY_SAMPLE_RUNNER"]}

_TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%SZ"

_VALID_CANDLE_DIRECTIONS = {"BULLISH", "BEARISH", "DOJI"}
_VALID_EVIDENCE_LABELS = {"LONG_PRESSURE", "SHORT_PRESSURE", "NEUTRAL"}
_VALID_STRUCTURE_BIASES = {"bullish", "bearish", "neutral"}
_VALID_SETUP_TYPES = {
    "NO_SETUP",
    "LONG_CONTINUATION", "LONG_REVERSAL", "LONG_BREAKOUT",
    "SHORT_CONTINUATION", "SHORT_REVERSAL", "SHORT_BREAKDOWN",
}
_VALID_SETUP_DIRECTIONS = {"NONE", "LONG", "SHORT"}
_VALID_SETUP_GRADES = {"NONE", "A", "B", "C"}
_VALID_PAPER_DECISIONS = {"NO_TRADE", "LONG", "SHORT"}
_VALID_OUTCOMES = {"NO_TRADE", "WIN_TP1", "WIN_TP2", "LOSS", "AMBIGUOUS"}

_REQUIRED_TOP = ["sample_id", "seed", "symbol", "scenario", "decision", "outcome"]
_REQUIRED_SCENARIO = [
    "candle_direction", "evidence_label", "quality_weight",
    "structure_bias", "setup_type", "setup_direction", "setup_grade",
]
_REQUIRED_DECISION = [
    "paper_decision", "entry_price", "stop_loss", "tp1", "tp2", "rr_tp1", "rr_tp2",
]
_REQUIRED_OUTCOME_FIELDS = ["outcome", "realized_rr", "edge_eligible"]

_CRITICAL_NON_NULL_TOP = ["sample_id", "seed", "symbol"]
_CRITICAL_NON_NULL_SCENARIO = [
    "candle_direction", "evidence_label", "quality_weight",
    "structure_bias", "setup_type", "setup_direction", "setup_grade",
]
_CRITICAL_NON_NULL_DECISION = ["paper_decision"]
_CRITICAL_NON_NULL_OUTCOME = ["outcome", "edge_eligible"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)


def _validate_timestamp(value: Any) -> bool:
    try:
        datetime.strptime(value, _TIMESTAMP_FMT)
        return True
    except (ValueError, TypeError):
        return False


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_row(row: dict[str, Any], row_idx: int) -> list[str]:
    errors: list[str] = []
    prefix = f"row[{row_idx}]"

    for f in _REQUIRED_TOP:
        if f not in row:
            errors.append(f"{prefix}: missing required field '{f}'")

    for f in _CRITICAL_NON_NULL_TOP:
        if f in row and row[f] is None:
            errors.append(f"{prefix}: critical field '{f}' is null")

    if "timestamp_utc" in row and not _validate_timestamp(row["timestamp_utc"]):
        errors.append(f"{prefix}: invalid timestamp_utc format '{row['timestamp_utc']}'")

    scenario = row.get("scenario")
    if isinstance(scenario, dict):
        for f in _REQUIRED_SCENARIO:
            if f not in scenario:
                errors.append(f"{prefix}.scenario: missing field '{f}'")
        for f in _CRITICAL_NON_NULL_SCENARIO:
            if f in scenario and scenario[f] is None:
                errors.append(f"{prefix}.scenario: critical field '{f}' is null")
        if "candle_direction" in scenario and scenario["candle_direction"] not in _VALID_CANDLE_DIRECTIONS:
            errors.append(f"{prefix}.scenario: invalid candle_direction '{scenario['candle_direction']}'")
        if "evidence_label" in scenario and scenario["evidence_label"] not in _VALID_EVIDENCE_LABELS:
            errors.append(f"{prefix}.scenario: invalid evidence_label '{scenario['evidence_label']}'")
        if "structure_bias" in scenario and scenario["structure_bias"] not in _VALID_STRUCTURE_BIASES:
            errors.append(f"{prefix}.scenario: invalid structure_bias '{scenario['structure_bias']}'")
        if "setup_type" in scenario and scenario["setup_type"] not in _VALID_SETUP_TYPES:
            errors.append(f"{prefix}.scenario: invalid setup_type '{scenario['setup_type']}'")
        if "setup_direction" in scenario and scenario["setup_direction"] not in _VALID_SETUP_DIRECTIONS:
            errors.append(f"{prefix}.scenario: invalid setup_direction '{scenario['setup_direction']}'")
        if "setup_grade" in scenario and scenario["setup_grade"] not in _VALID_SETUP_GRADES:
            errors.append(f"{prefix}.scenario: invalid setup_grade '{scenario['setup_grade']}'")
        if "quality_weight" in scenario and scenario["quality_weight"] is not None:
            if not _is_numeric(scenario["quality_weight"]):
                errors.append(f"{prefix}.scenario: quality_weight must be numeric")

    decision = row.get("decision")
    if isinstance(decision, dict):
        for f in _REQUIRED_DECISION:
            if f not in decision:
                errors.append(f"{prefix}.decision: missing field '{f}'")
        for f in _CRITICAL_NON_NULL_DECISION:
            if f in decision and decision[f] is None:
                errors.append(f"{prefix}.decision: critical field '{f}' is null")
        if "paper_decision" in decision and decision["paper_decision"] not in _VALID_PAPER_DECISIONS:
            errors.append(f"{prefix}.decision: invalid paper_decision '{decision['paper_decision']}'")
        for rr_field in ("rr_tp1", "rr_tp2"):
            if rr_field in decision and decision[rr_field] is not None:
                if not _is_numeric(decision[rr_field]):
                    errors.append(f"{prefix}.decision: {rr_field} must be numeric or null")

    outcome = row.get("outcome")
    if isinstance(outcome, dict):
        for f in _REQUIRED_OUTCOME_FIELDS:
            if f not in outcome:
                errors.append(f"{prefix}.outcome: missing field '{f}'")
        for f in _CRITICAL_NON_NULL_OUTCOME:
            if f in outcome and outcome[f] is None:
                errors.append(f"{prefix}.outcome: critical field '{f}' is null")
        if "outcome" in outcome and outcome["outcome"] not in _VALID_OUTCOMES:
            errors.append(f"{prefix}.outcome: invalid outcome '{outcome['outcome']}'")
        if "edge_eligible" in outcome and not isinstance(outcome["edge_eligible"], bool):
            errors.append(
                f"{prefix}.outcome: edge_eligible must be bool, got {type(outcome['edge_eligible']).__name__}"
            )
        if "realized_rr" in outcome and outcome["realized_rr"] is not None:
            if not _is_numeric(outcome["realized_rr"]):
                errors.append(f"{prefix}.outcome: realized_rr must be numeric or null")

    return errors


def _build_data_quality(total: int, error_rows: int, malformed: int) -> dict[str, Any]:
    bad = error_rows + malformed
    if total == 0:
        return {"score": 0.0, "level": "CRITICAL", "issues": ["NO_ROWS_FOUND"]}
    ratio = bad / total
    if malformed > 0:
        return {"score": 0.0, "level": "CRITICAL", "issues": [f"MALFORMED_ROWS_{malformed}"]}
    if ratio > 0.1:
        return {"score": 0.2, "level": "CRITICAL", "issues": [f"HIGH_ERROR_RATE_{round(ratio, 3)}"]}
    if ratio > 0:
        return {"score": 0.6, "level": "MEDIUM", "issues": [f"SOME_ERRORS_{error_rows}"]}
    return {"score": 1.0, "level": "HIGH", "issues": []}


def _build_reason_codes(
    total: int, valid: int, error_rows: int, malformed: int, dq: dict[str, Any]
) -> list[str]:
    return [
        f"TOTAL_ROWS_{total}",
        f"VALID_ROWS_{valid}",
        f"ERROR_ROWS_{error_rows}",
        f"MALFORMED_ROWS_{malformed}",
        f"DATA_QUALITY_{dq['level']}",
        "RESEARCH_ONLY",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
    ]


def validate_file(path: Path) -> dict[str, Any]:
    """Validate replay_samples.jsonl and return a full JSON-contract result."""
    all_errors: list[str] = []
    total_rows = 0
    malformed_rows = 0
    error_rows = 0
    valid_rows = 0

    with path.open(encoding="utf-8") as fh:
        for line_idx, raw_line in enumerate(fh):
            line = raw_line.strip()
            if not line:
                continue
            total_rows += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                malformed_rows += 1
                all_errors.append(f"row[{line_idx}]: malformed JSON — {exc}")
                continue

            row_errors = _validate_row(row, line_idx)
            if row_errors:
                error_rows += 1
                all_errors.extend(row_errors)
            else:
                valid_rows += 1

    dq = _build_data_quality(total_rows, error_rows, malformed_rows)
    reason_codes = _build_reason_codes(total_rows, valid_rows, error_rows, malformed_rows, dq)

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": "MULTI",
        "source": {
            "source_mode": "FILE_VALIDATION",
            "path": str(path),
        },
        "validation_summary": {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "error_rows": error_rows,
            "malformed_rows": malformed_rows,
        },
        "errors": all_errors,
        "data_quality": dq,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
            "research_only": True,
        },
    }
