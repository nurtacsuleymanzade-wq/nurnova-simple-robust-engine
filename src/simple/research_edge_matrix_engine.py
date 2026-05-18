from __future__ import annotations

import json
from typing import Any

from src.core.model_survival_registry import load_model_survival_registry, split_active_quarantined, update_model_survival_report
from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "RESEARCH_EDGE_MATRIX_ENGINE"
OUTPUT_PATH = epoch_state_path("latest_research_edge_matrix.json")
HISTORY_PATH = epoch_data_path("research_edge_matrix_history.jsonl")
LIFECYCLE_HISTORY_PATH = epoch_data_path("research_paper_lifecycle_history.jsonl")
OUTCOME_EVENTS_PATH = epoch_data_path("outcome_events.jsonl")
ACCOUNTING_PATH = epoch_state_path("latest_outcome_accounting.json")
MAX_HISTORY_ROWS = 5000

GROUP_FIELDS = (
    "model_id",
    "setup_family",
    "signal_grade",
    "direction",
    "primary_tf",
    "context_tf",
    "plan_style",
    "event_confluence_count",
)


def _closed_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for payload in read_jsonl_tail_objects(OUTCOME_EVENTS_PATH, max_lines=MAX_HISTORY_ROWS):
        trade_id = str(payload.get("paper_trade_id") or "")
        if trade_id:
            records[trade_id] = dict(payload)
    return records


def _clean_sample(trade: dict[str, Any]) -> bool:
    required = tuple(field for field in GROUP_FIELDS if field not in {"signal_grade", "event_confluence_count"})
    return (
        str(trade.get("epoch_id") or "") == ACTIVE_EPOCH_ID
        and bool(trade.get("closed_only", True))
        and str(trade.get("outcome_status") or "").upper() in {"TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"}
        and all(trade.get(field) not in (None, "") for field in required)
        and safe_float(trade.get("rr1")) is not None
        and safe_float(trade.get("rr2")) is not None
        and safe_float(trade.get("mfe")) is not None
    )


def _group_value(trade: dict[str, Any], field: str) -> str:
    if field == "signal_grade":
        return str(trade.get(field) or "LEGACY_UNGRADED")
    if field == "event_confluence_count":
        return str(trade.get(field) or 1)
    return str(trade.get(field) or "UNKNOWN")


def _group_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    sample_size = len(items)
    wins = sum(1 for item in items if str(item.get("close_reason") or "").upper() in {"TP1_HIT", "TP2_HIT"})
    losses = sum(1 for item in items if str(item.get("close_reason") or "").upper() == "SL_HIT")
    expired = sum(1 for item in items if str(item.get("close_reason") or "").upper() == "EXPIRED")
    expectancy = round(sum(safe_float(item.get("r_result")) or 0.0 for item in items) / sample_size, 4) if sample_size else 0.0
    winrate = round(wins / (wins + losses), 4) if (wins + losses) > 0 else 0.0
    if sample_size < 20:
        edge_status = "SAMPLE_BUILDING"
        maturity = "INSUFFICIENT"
    else:
        edge_status = "EDGE_ACTIVE"
        maturity = "SUFFICIENT"
    return {
        "sample_size": sample_size,
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "winrate": winrate,
        "expectancy": expectancy,
        "avg_r": expectancy,
        "edge_status": edge_status,
        "maturity": maturity,
    }


def run_research_edge_matrix_engine() -> dict[str, Any]:
    context = current_runtime_context()
    accounting = load_json(ACCOUNTING_PATH) or {}
    registry = load_model_survival_registry()
    all_closed = _closed_records()
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    invalid_sample_count = 0

    closed_values, blocked_closed = split_active_quarantined(list(all_closed.values()), BLOCK_ID)
    survival_report = update_model_survival_report(location=BLOCK_ID, allowed_count=len(closed_values), blocked_items=blocked_closed, registry=registry)
    for trade in closed_values:
        if not _clean_sample(trade):
            invalid_sample_count += 1
            continue
        key = tuple(_group_value(trade, field) for field in GROUP_FIELDS)
        grouped.setdefault(key, []).append(trade)

    groups: list[dict[str, Any]] = []
    for key, items in grouped.items():
        record = {field: value for field, value in zip(GROUP_FIELDS, key)}
        record.update(_group_metrics(items))
        groups.append(record)

    groups.sort(key=lambda item: (int(item.get("sample_size") or 0), safe_float(item.get("expectancy")) or -9999), reverse=True)
    best_group = groups[0] if groups else {}
    mature_groups = [group for group in groups if int(group.get("sample_size") or 0) >= 20]
    best_winrate_model = max(mature_groups, key=lambda item: safe_float(item.get("winrate")) or 0.0) if mature_groups else {}
    best_avg_r_model = max(mature_groups, key=lambda item: safe_float(item.get("avg_r")) or -9999.0) if mature_groups else {}
    a_plus_groups = [group for group in mature_groups if str(group.get("signal_grade") or "") == "A_PLUS"]
    best_a_plus_model = max(a_plus_groups, key=lambda item: safe_float(item.get("avg_r")) or -9999.0) if a_plus_groups else {}
    worst_model = min(mature_groups, key=lambda item: safe_float(item.get("avg_r")) or 9999.0) if mature_groups else {}
    sample_building_models = [group for group in groups if int(group.get("sample_size") or 0) < 20][:20]
    accounting_clean_count = int(((accounting.get("summary") or {}).get("clean_sample_count")) or 0)
    if not groups and accounting_clean_count <= 0:
        edge_status = "NO_CLEAN_SAMPLES"
    elif not groups:
        edge_status = "SAMPLE_BUILDING"
    elif int(best_group.get("sample_size") or 0) < 20:
        edge_status = "SAMPLE_BUILDING"
    else:
        edge_status = "EDGE_ACTIVE"

    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "block_id": BLOCK_ID,
            "source": {"source_mode": "EPOCH_V2_OUTCOME_ACCOUNTING_AND_LIFECYCLE"},
            "groups": groups[:100],
            "edge_status": edge_status,
            "summary": {
                "group_count": len(groups),
                "clean_sample_count": accounting_clean_count,
                "closed_trade_count": int(((accounting.get("summary") or {}).get("closed_count")) or 0),
                "best_model_id": best_group.get("model_id"),
                "best_sample_size": int(best_group.get("sample_size") or 0),
                "best_expectancy": best_group.get("expectancy"),
                "best_winrate": best_group.get("winrate"),
                "invalid_sample_count": invalid_sample_count,
                "model_survival_blocked_count": len(blocked_closed),
            },
            "model_survival_registry": {"registry_status": survival_report.get("registry_status"), "blocked_count": len(blocked_closed)},
            "best_winrate_model": best_winrate_model,
            "best_avg_r_model": best_avg_r_model,
            "best_a_plus_model": best_a_plus_model,
            "worst_model": worst_model,
            "sample_building_models": sample_building_models,
            "data_quality": {
                "level": "HIGH" if accounting else "MEDIUM",
                "missing_inputs": [
                    name for name, ok in {
                        "epoch_v2/latest_outcome_accounting.json": bool(accounting),
                        "epoch_v2/outcome_events.jsonl": OUTCOME_EVENTS_PATH.exists(),
                    }.items() if not ok
                ],
            },
            "reason_codes": [
                f"CLEAN_SAMPLES_{(accounting.get('summary') or {}).get('clean_sample_count', 0)}",
                f"GROUPS_{len(groups)}",
                f"EDGE_STATUS_{edge_status}",
                "PAPER_ONLY",
                "NO_LIVE_EXECUTION",
                "NO_PRIVATE_API",
                "SOURCE_CLOSED_OUTCOMES_ONLY",
            ],
            "source": "closed_outcomes_only",
            "feeds_next": ["TELEGRAM_RESEARCH_REPORTER"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        str(best_group.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("research_edge_matrix_history.jsonl", output)
    return output


def main() -> None:
    print(json.dumps(run_research_edge_matrix_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
