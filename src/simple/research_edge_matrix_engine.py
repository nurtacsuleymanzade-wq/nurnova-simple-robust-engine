from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_runtime import (
    append_jsonl,
    current_runtime_context,
    safe_float,
    stamp_payload,
    write_json,
)

BLOCK_ID = "RESEARCH_EDGE_MATRIX_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_research_edge_matrix.json"
HISTORY_PATH = DATA_DIR / "research_edge_matrix_history.jsonl"
LIFECYCLE_HISTORY_PATH = DATA_DIR / "research_paper_lifecycle_history.jsonl"
MAX_LIFECYCLE_TAIL_ROWS = 5000
MAX_GROUPS_IN_LATEST = 20

GROUP_FIELDS = (
    "model_id",
    "model_family",
    "setup_family",
    "dominant_setup_family",
    "activation_band",
    "market_regime",
    "candle_category",
    "structure_label",
    "liquidity_event",
    "direction",
)


def _edge_maturity(sample_size: int, expectancy: float | None) -> tuple[str, str]:
    if sample_size < 20:
        return "SAMPLE_BUILDING", "INSUFFICIENT"
    if sample_size < 50:
        return "EARLY_READ", "EARLY_READ"
    if sample_size < 100:
        return "WATCH", "WATCH"
    if sample_size < 300:
        return "VALIDATING", "VALIDATING"
    if (expectancy or 0.0) > 0:
        return "PROMISING", "PROMISING"
    return "DANGEROUS", "DANGEROUS"


def _load_closed_trades() -> list[dict[str, Any]]:
    payloads = read_jsonl_tail_objects(LIFECYCLE_HISTORY_PATH, max_lines=MAX_LIFECYCLE_TAIL_ROWS)
    closed_by_id: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for trade in payload.get("trades_closed_this_loop") or payload.get("recent_closed") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                closed_by_id[trade_id] = trade
    return list(closed_by_id.values())


def _clean_sample(trade: dict[str, Any]) -> tuple[bool, str | None]:
    outcome_status = str(trade.get("outcome_status") or "").upper()
    status = str(trade.get("status") or trade.get("close_reason") or "").upper()
    if outcome_status != "CLOSED" and status not in {"TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"}:
        return False, "outcome_not_closed"
    if trade.get("invalid_for_edge") is True:
        return False, "invalid_for_edge"
    if not trade.get("model_id"):
        return False, "missing_model_id"
    if not trade.get("setup_family"):
        return False, "missing_setup_family"
    if not trade.get("context_id"):
        return False, "missing_context_id"
    if safe_float(trade.get("r_result")) is None:
        return False, "non_numeric_r_result"
    return True, None


def _profit_factor(items: list[dict[str, Any]]) -> float | None:
    gross_profit = sum(max(safe_float(item.get("r_result")) or 0.0, 0.0) for item in items)
    gross_loss = sum(abs(min(safe_float(item.get("r_result")) or 0.0, 0.0)) for item in items)
    if gross_loss == 0:
        return round(gross_profit, 4) if gross_profit > 0 else None
    return round(gross_profit / gross_loss, 4)


def _loss_streak(items: list[dict[str, Any]]) -> int:
    streak = 0
    max_streak = 0
    ordered = sorted(items, key=lambda item: str(item.get("closed_at_utc") or item.get("closed_at") or item.get("timestamp_utc") or ""))
    for item in ordered:
        if (safe_float(item.get("r_result")) or 0.0) < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _max_drawdown_r(items: list[dict[str, Any]]) -> float:
    ordered = sorted(items, key=lambda item: str(item.get("closed_at_utc") or item.get("closed_at") or item.get("timestamp_utc") or ""))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for item in ordered:
        equity += safe_float(item.get("r_result")) or 0.0
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(abs(max_dd), 4)


def _group_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    sample_size = len(items)
    r_values = [safe_float(item.get("r_result")) for item in items if safe_float(item.get("r_result")) is not None]
    wins = sum(1 for value in r_values if (value or 0.0) > 0)
    expectancy = round(sum(r_values) / sample_size, 4) if sample_size else None
    avg_r = round(sum(r_values) / sample_size, 4) if sample_size else None
    winrate = round(wins / sample_size, 4) if sample_size else None
    avg_mfe = round(sum(safe_float(item.get("mfe")) or 0.0 for item in items) / sample_size, 4) if sample_size else None
    avg_mae = round(sum(safe_float(item.get("mae")) or 0.0 for item in items) / sample_size, 4) if sample_size else None
    edge_status, maturity = _edge_maturity(sample_size, expectancy)
    best_context = max(items, key=lambda item: safe_float(item.get("r_result")) or -9999).get("context_id") if items else None
    worst_context = min(items, key=lambda item: safe_float(item.get("r_result")) or 9999).get("context_id") if items else None
    return {
        "sample_size": sample_size,
        "winrate": winrate,
        "avg_r": avg_r,
        "expectancy": expectancy if sample_size >= 20 else None,
        "avg_mfe": avg_mfe,
        "avg_mae": avg_mae,
        "best_context": best_context,
        "worst_context": worst_context,
        "loss_streak": _loss_streak(items),
        "max_drawdown_r": _max_drawdown_r(items),
        "profit_factor": _profit_factor(items),
        "edge_status": edge_status,
        "maturity": maturity,
    }


def run_research_edge_matrix_engine() -> dict[str, Any]:
    context = current_runtime_context()
    closed_trades = _load_closed_trades()
    clean_samples: list[dict[str, Any]] = []
    invalid_sample_reasons: dict[str, int] = {}
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}

    for trade in closed_trades:
        clean, reason = _clean_sample(trade)
        if not clean:
            invalid_sample_reasons[reason or "unknown"] = invalid_sample_reasons.get(reason or "unknown", 0) + 1
            continue
        clean_samples.append(trade)
        key = tuple(str(trade.get(field) or "UNKNOWN") for field in GROUP_FIELDS)
        grouped.setdefault(key, []).append(trade)

    groups_output: list[dict[str, Any]] = []
    for key, items in grouped.items():
        metrics = _group_metrics(items)
        record = {field: value for field, value in zip(GROUP_FIELDS, key)}
        record.update(metrics)
        groups_output.append(record)

    groups_output.sort(
        key=lambda item: (
            safe_float(item.get("expectancy")) if item.get("expectancy") is not None else -9999,
            item.get("sample_size", 0),
        ),
        reverse=True,
    )
    best_group = groups_output[0] if groups_output else None
    if not clean_samples:
        edge_status = "NO_CLOSED_SAMPLES" if not closed_trades else "SAMPLE_BUILDING"
    else:
        edge_status = best_group.get("edge_status") if best_group else "SAMPLE_BUILDING"
    best_expectancy = best_group.get("expectancy") if best_group else None

    output = stamp_payload(
        {
            "symbol": "BTCUSDT",
            "block_id": BLOCK_ID,
            "source": {"source_mode": "RESEARCH_PAPER_LIFECYCLE_HISTORY"},
            "groups": groups_output[:MAX_GROUPS_IN_LATEST],
            "summary": {
                "group_count": len(groups_output),
                "closed_trade_count": len(closed_trades),
                "clean_sample_count": len(clean_samples),
                "best_model_id": best_group.get("model_id") if best_group else None,
                "best_sample_size": best_group.get("sample_size") if best_group else 0,
                "best_expectancy": best_expectancy,
                "best_winrate": best_group.get("winrate") if best_group else None,
                "best_maturity": best_group.get("maturity") if best_group else "INSUFFICIENT",
                "best_context": best_group.get("best_context") if best_group else None,
            },
            "edge_status": edge_status,
            "invalid_sample_reasons": invalid_sample_reasons,
            "reason_codes": [
                f"CLOSED_TRADES_{len(closed_trades)}",
                f"CLEAN_SAMPLES_{len(clean_samples)}",
                f"GROUPS_{len(groups_output)}",
                "NO_LIVE_EXECUTION",
                "NO_PRIVATE_API",
                "PAPER_ONLY",
            ],
            "data_quality": {
                "level": "HIGH" if clean_samples else "LOW",
                "missing_inputs": [] if LIFECYCLE_HISTORY_PATH.exists() else ["research_paper_lifecycle_history"],
            },
            "feeds_next": ["MODEL_FEEDBACK_DIAGNOSTIC", "MODEL_PROMOTION_ENGINE"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        "BTCUSDT",
        context,
    )

    write_json(OUTPUT_PATH, output)
    append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_research_edge_matrix_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
