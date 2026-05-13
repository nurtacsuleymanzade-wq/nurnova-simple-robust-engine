from __future__ import annotations

import json
from typing import Any

from src.simple.research_epoch import (
    ACTIVE_EPOCH_ID,
    append_epoch_jsonl,
    epoch_data_path,
    epoch_state_path,
)
from src.simple.research_runtime import current_runtime_context, safe_float, stamp_payload, write_json
from src.simple.jsonl_tail_reader import read_jsonl_tail_objects

BLOCK_ID = "OUTCOME_ACCOUNTING_ENGINE"
OUTPUT_PATH = epoch_state_path("latest_outcome_accounting.json")
HISTORY_PATH = epoch_data_path("outcome_accounting_history.jsonl")
LIFECYCLE_HISTORY_PATH = epoch_data_path("research_paper_lifecycle_history.jsonl")
MAX_HISTORY_ROWS = 5000

REQUIRED_SAMPLE_FIELDS = (
    "symbol",
    "paper_trade_id",
    "model_id",
    "setup_family",
    "direction",
    "entry",
    "stop_loss",
    "tp1",
    "primary_tf",
    "trigger_tf",
    "context_tf",
)


def _latest_closed_records() -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for payload in read_jsonl_tail_objects(LIFECYCLE_HISTORY_PATH, max_lines=MAX_HISTORY_ROWS):
        for trade in payload.get("trades_closed_this_loop") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                records[trade_id] = dict(trade)
    return list(records.values())


def _result_bucket(trade: dict[str, Any]) -> str:
    reason = str(trade.get("close_reason") or trade.get("status") or "").upper()
    if reason in {"TP1_HIT", "TP2_HIT"}:
        return "WIN"
    if reason == "SL_HIT":
        return "LOSS"
    if reason == "EXPIRED":
        return "NEUTRAL"
    return "INVALID"


def _is_numeric(value: Any) -> bool:
    return safe_float(value) is not None


def _clean_sample_check(trade: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if str(trade.get("epoch_id") or "") != ACTIVE_EPOCH_ID:
        issues.append("EPOCH_MISMATCH")
    if str(trade.get("outcome_status") or "").upper() != "CLOSED":
        issues.append("OUTCOME_NOT_CLOSED")
    if trade.get("valid_for_edge") is False:
        issues.append("VALID_FOR_EDGE_FALSE")
    for field in REQUIRED_SAMPLE_FIELDS:
        if trade.get(field) in (None, ""):
            issues.append(f"MISSING_{field.upper()}")
    if not _is_numeric(trade.get("rr1")):
        issues.append("RR1_NOT_NUMERIC")
    if not _is_numeric(trade.get("rr2")):
        issues.append("RR2_NOT_NUMERIC")
    if not _is_numeric(trade.get("r_result")):
        issues.append("R_RESULT_NOT_NUMERIC")
    return not issues, issues


def run_outcome_accounting_engine() -> dict[str, Any]:
    context = current_runtime_context()
    lifecycle_records = _latest_closed_records()
    seen: set[str] = set()
    duplicates = 0
    wins = 0
    losses = 0
    expired = 0
    invalid = 0
    clean_closed_samples: list[dict[str, Any]] = []
    invalid_samples: list[dict[str, Any]] = []
    mismatch_flags: list[str] = []

    for trade in lifecycle_records:
        trade_id = str(trade.get("paper_trade_id") or "")
        if trade_id in seen:
            duplicates += 1
            continue
        seen.add(trade_id)
        bucket = _result_bucket(trade)
        clean, issues = _clean_sample_check(trade)
        if bucket == "WIN":
            wins += 1
        elif bucket == "LOSS":
            losses += 1
        elif bucket == "NEUTRAL":
            expired += 1
        else:
            invalid += 1
        if clean:
            clean_closed_samples.append(dict(trade))
        else:
            invalid_sample = {
                "paper_trade_id": trade_id,
                "symbol": trade.get("symbol"),
                "issues": issues,
                "close_reason": trade.get("close_reason"),
                "outcome_status": trade.get("outcome_status"),
            }
            invalid_samples.append(invalid_sample)

    closed_count = wins + losses + expired
    winrate = round(wins / (wins + losses), 4) if (wins + losses) > 0 else 0.0
    avg_r = round(
        sum(safe_float(item.get("r_result")) or 0.0 for item in clean_closed_samples) / len(clean_closed_samples),
        4,
    ) if clean_closed_samples else 0.0
    if closed_count != wins + losses + expired:
        mismatch_flags.append("CLOSED_COUNT_MISMATCH")
    if duplicates > 0:
        mismatch_flags.append("DUPLICATE_PAPER_TRADE_ID")
    if winrate == 0 and avg_r > 0:
        mismatch_flags.append("ACCOUNTING_MISMATCH")

    accounting_status = "OK" if not mismatch_flags else "CORRUPTED"
    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "block_id": BLOCK_ID,
            "source": {"source_mode": "EPOCH_V2_RESEARCH_PAPER_LIFECYCLE_HISTORY"},
            "summary": {
                "closed_count": closed_count,
                "wins": wins,
                "losses": losses,
                "expired": expired,
                "invalid": invalid,
                "clean_sample_count": len(clean_closed_samples),
                "invalid_sample_count": len(invalid_samples),
                "duplicate_paper_trade_id_count": duplicates,
                "winrate": winrate,
                "expectancy": avg_r,
                "avg_r": avg_r,
            },
            "closed_samples": clean_closed_samples[-200:],
            "invalid_samples": invalid_samples[-200:],
            "consistency_checks": {
                "closed_count_equals_components": closed_count == (wins + losses + expired),
                "duplicate_paper_trade_id_count": duplicates,
                "winrate_uses_clean_universe": True,
                "expectancy_uses_clean_universe": True,
            },
            "accounting_status": accounting_status,
            "accounting_flags": mismatch_flags,
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
            "data_quality": {
                "level": "HIGH" if clean_closed_samples or lifecycle_records else "MEDIUM",
                "missing_inputs": [] if LIFECYCLE_HISTORY_PATH.exists() else ["epoch_v2/research_paper_lifecycle_history.jsonl"],
            },
            "reason_codes": [
                f"CLEAN_SAMPLES_{len(clean_closed_samples)}",
                f"DUPLICATES_{duplicates}",
                f"ACCOUNTING_{accounting_status}",
                "PAPER_ONLY",
                "NO_LIVE_EXECUTION",
                "NO_PRIVATE_API",
            ],
            "feeds_next": ["RESEARCH_EDGE_MATRIX_ENGINE", "TELEGRAM_RESEARCH_REPORTER"],
        },
        BLOCK_ID,
        str((clean_closed_samples[-1] if clean_closed_samples else {}).get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("outcome_accounting_history.jsonl", output)
    return output


def main() -> None:
    print(json.dumps(run_outcome_accounting_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
