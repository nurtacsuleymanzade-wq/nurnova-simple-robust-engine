from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import ACTIVE_EPOCH_ID, epoch_data_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "EDGE_VALIDATION_GOVERNOR"
STATE_DIR = Path("state/simple")
REPORT_PATH = Path("reports/simple/edge_validation_governor_latest_report.md")
OUTPUT_PATH = STATE_DIR / "latest_edge_validation_governor.json"
HISTORY_PATH = epoch_data_path("edge_validation_governor_history.jsonl")

RESEARCH_LIFECYCLE_HISTORY_PATH = epoch_data_path("research_paper_lifecycle_history.jsonl")
OUTCOME_ACCOUNTING_HISTORY_PATH = epoch_data_path("outcome_accounting_history.jsonl")
CONTRACT_EDGE_MATRIX_HISTORY_PATH = epoch_data_path("contract_edge_matrix_history.jsonl")
PAPER_FACTORY_HISTORY_PATH = epoch_data_path("paper_trade_factory_history.jsonl")

LATEST_CONTRACT_TRADE_PLAN_PATH = STATE_DIR / "latest_contract_trade_plan.json"
LATEST_CONTRACT_DECISION_GATE_PATH = STATE_DIR / "latest_contract_decision_gate.json"
LATEST_PAPER_TRADE_FACTORY_PATH = STATE_DIR / "epoch_v2" / "latest_paper_trade_factory.json"

MAX_TAIL_ROWS = 4
EDGE_STATUSES = {
    "EDGE_REJECTED",
    "EDGE_WATCHLIST",
    "EDGE_CANDIDATE",
    "EDGE_VALIDATED_PAPER",
    "EDGE_PROBATION",
    "EDGE_DISABLED",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _status_timestamp(trade: dict[str, Any]) -> str:
    return str(
        trade.get("closed_at_utc")
        or trade.get("opened_at_utc")
        or trade.get("timestamp_utc")
        or ""
    )


def _extract_r_value(trade: dict[str, Any]) -> float | None:
    value = safe_float(trade.get("r_result"))
    if value is not None:
        return value
    reason = str(trade.get("close_reason") or trade.get("status") or "").upper()
    if reason in {"TP1_HIT", "TP2_HIT"}:
        return 1.0
    if reason == "SL_HIT":
        return -1.0
    if reason == "EXPIRED":
        return 0.0
    return None


def _trade_regime_tags(trade: dict[str, Any]) -> list[str]:
    tags = []
    for key in ("primary_regime", "regime", "structure_bias", "liquidity_bias", "paper_source"):
        value = trade.get(key)
        if value not in (None, "", [], {}):
            tags.append(f"{key}:{value}")
    return tags


def _entity_refs(trade: dict[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    model_id = str(trade.get("model_id") or "").strip()
    setup_family = str(trade.get("setup_family") or "").strip()
    contract_id = str(trade.get("contract_id") or "").strip()
    if model_id:
        refs.append(("MODEL", model_id))
    if setup_family:
        refs.append(("SETUP_FAMILY", setup_family))
    if contract_id:
        refs.append(("CONTRACT", contract_id))
    return refs


def _iter_lifecycle_events() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    closed: dict[str, dict[str, Any]] = {}
    invalid: dict[str, dict[str, Any]] = {}
    latest_open: dict[str, dict[str, Any]] = {}
    for payload in read_jsonl_tail_objects(RESEARCH_LIFECYCLE_HISTORY_PATH, max_lines=MAX_TAIL_ROWS):
        for trade in payload.get("open_trades") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                latest_open[trade_id] = dict(trade)
        for trade in payload.get("recent_closed") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                closed[trade_id] = dict(trade)
        for trade in payload.get("recent_invalid") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                invalid[trade_id] = dict(trade)
        for trade in payload.get("trades_closed_this_loop") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if not trade_id:
                continue
            outcome_status = str(trade.get("outcome_status") or "").upper()
            if outcome_status == "INVALID" or str(trade.get("status") or "").upper() == "INVALID":
                invalid[trade_id] = dict(trade)
            else:
                closed[trade_id] = dict(trade)
                invalid.pop(trade_id, None)
                latest_open.pop(trade_id, None)
    return list(closed.values()), list(invalid.values()), list(latest_open.values())


def _iter_factory_opens() -> list[dict[str, Any]]:
    opened: dict[str, dict[str, Any]] = {}
    for payload in read_jsonl_tail_objects(PAPER_FACTORY_HISTORY_PATH, max_lines=MAX_TAIL_ROWS):
        for trade in payload.get("newest_opened_this_loop") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                opened[trade_id] = dict(trade)
    return list(opened.values())


def _iter_outcome_accounting_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in read_jsonl_tail_objects(OUTCOME_ACCOUNTING_HISTORY_PATH, max_lines=MAX_TAIL_ROWS):
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _iter_contract_edge_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in read_jsonl_tail_objects(CONTRACT_EDGE_MATRIX_HISTORY_PATH, max_lines=MAX_TAIL_ROWS):
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _global_data_quality_score(
    outcome_accounting: dict[str, Any] | None,
    paper_factory: dict[str, Any] | None,
    outcome_rows: list[dict[str, Any]] | None = None,
    edge_matrix_rows: list[dict[str, Any]] | None = None,
) -> float:
    level = str(((paper_factory or {}).get("data_quality") or {}).get("level") or "LOW").upper()
    base = {"HIGH": 0.95, "MEDIUM": 0.8, "LOW": 0.6}.get(level, 0.4)
    invalid = int(((outcome_accounting or {}).get("summary") or {}).get("invalid", 0) or 0)
    clean = int(((outcome_accounting or {}).get("summary") or {}).get("clean_sample_count", 0) or 0)
    for row in outcome_rows or []:
        summary = row.get("summary") or {}
        invalid = max(invalid, int(summary.get("invalid", 0) or 0))
        clean = max(clean, int(summary.get("clean_sample_count", 0) or 0))
    total = clean + invalid
    penalty = (invalid / total) * 0.2 if total > 0 else 0.0
    edge_bonus = 0.0
    for row in edge_matrix_rows or []:
        sample_summary = row.get("sample_summary") or {}
        contract_sample_count = int(sample_summary.get("contract_sample_count", 0) or 0)
        if contract_sample_count >= 30:
            edge_bonus = 0.03
            break
        if contract_sample_count >= 10:
            edge_bonus = 0.01
    return round(max(0.0, min(1.0, base - penalty + edge_bonus)), 4)


def _calc_max_loss_streak(closed_rows: list[dict[str, Any]]) -> int:
    streak = 0
    max_streak = 0
    ordered = sorted(closed_rows, key=_status_timestamp)
    for trade in ordered:
        r_value = _extract_r_value(trade)
        if r_value is not None and r_value < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _last_20_performance(closed_rows: list[dict[str, Any]]) -> float:
    ordered = sorted(closed_rows, key=_status_timestamp)[-20:]
    values = [value for value in (_extract_r_value(trade) for trade in ordered) if value is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _stability_score(
    expectancy_r: float,
    profit_factor: float,
    max_loss_streak: int,
    timeout_rate: float,
    duplicate_rate: float,
    data_quality_score: float,
    last_20_performance: float,
) -> float:
    score = 0.0
    score += min(max(expectancy_r, -1.0), 1.0) * 0.25 + 0.25
    score += min(profit_factor / 2.0, 1.0) * 0.2
    score += max(0.0, 1.0 - (max_loss_streak / 10.0)) * 0.15
    score += max(0.0, 1.0 - timeout_rate) * 0.1
    score += max(0.0, 1.0 - duplicate_rate) * 0.1
    score += data_quality_score * 0.15
    score += max(0.0, min((last_20_performance + 1.0) / 2.0, 1.0)) * 0.05
    return round(max(0.0, min(1.0, score)), 4)


def _classify_edge(metrics: dict[str, Any]) -> str:
    closed_count = int(metrics["closed_count"])
    expectancy_r = float(metrics["expectancy_r"])
    profit_factor = float(metrics["profit_factor"])
    max_loss_streak = int(metrics["max_loss_streak"])
    timeout_rate = float(metrics["timeout_rate"])
    duplicate_rate = float(metrics["duplicate_rate"])
    data_quality_score = float(metrics["data_quality_score"])
    last_20_performance = float(metrics["last_20_performance"])

    if closed_count >= 10 and expectancy_r < 0:
        return "EDGE_REJECTED"
    if duplicate_rate > 0.25 or max_loss_streak >= 8:
        return "EDGE_DISABLED"
    if max_loss_streak > 5 or last_20_performance < 0:
        return "EDGE_PROBATION"
    if (
        closed_count >= 30
        and expectancy_r > 0
        and profit_factor >= 1.2
        and max_loss_streak <= 5
        and timeout_rate <= 0.35
        and duplicate_rate <= 0.10
        and last_20_performance >= 0
        and data_quality_score >= 0.7
    ):
        return "EDGE_VALIDATED_PAPER"
    if closed_count >= 10 and expectancy_r > 0 and profit_factor >= 1.0 and data_quality_score >= 0.6:
        return "EDGE_CANDIDATE"
    if closed_count < 10:
        return "EDGE_WATCHLIST"
    return "EDGE_REJECTED"


def _build_entity_row(
    entity_type: str,
    entity_id: str,
    closed_rows: list[dict[str, Any]],
    open_rows: list[dict[str, Any]],
    invalid_rows: list[dict[str, Any]],
    opened_rows: list[dict[str, Any]],
    data_quality_score: float,
) -> dict[str, Any]:
    closed_values = [value for value in (_extract_r_value(trade) for trade in closed_rows) if value is not None]
    closed_count = len(closed_values)
    win_count = sum(1 for value in closed_values if value > 0)
    timeout_count = sum(
        1 for trade in closed_rows if str(trade.get("close_reason") or trade.get("status") or "").upper() == "EXPIRED"
    )
    gross_profit = sum(value for value in closed_values if value > 0)
    gross_loss = abs(sum(value for value in closed_values if value < 0))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    expectancy_r = round(sum(closed_values) / closed_count, 4) if closed_count else 0.0
    winrate = round(win_count / closed_count, 4) if closed_count else 0.0
    timeout_rate = round(timeout_count / closed_count, 4) if closed_count else 0.0
    open_count = len(open_rows)
    invalid_count = len(invalid_rows)
    duplicate_rate = 0.0
    if opened_rows:
        event_ids = [str(row.get("event_id") or "") for row in opened_rows if row.get("event_id")]
        duplicates = max(0, len(event_ids) - len(set(event_ids)))
        duplicate_rate = round(duplicates / len(opened_rows), 4) if opened_rows else 0.0
    max_loss_streak = _calc_max_loss_streak(closed_rows)
    last_20_performance = _last_20_performance(closed_rows)
    stability_score = _stability_score(
        expectancy_r=expectancy_r,
        profit_factor=profit_factor,
        max_loss_streak=max_loss_streak,
        timeout_rate=timeout_rate,
        duplicate_rate=duplicate_rate,
        data_quality_score=data_quality_score,
        last_20_performance=last_20_performance,
    )
    tags = sorted({tag for trade in [*closed_rows, *open_rows, *invalid_rows] for tag in _trade_regime_tags(trade)})[:20]
    status = _classify_edge(
        {
            "closed_count": closed_count,
            "expectancy_r": expectancy_r,
            "profit_factor": profit_factor,
            "max_loss_streak": max_loss_streak,
            "timeout_rate": timeout_rate,
            "duplicate_rate": duplicate_rate,
            "data_quality_score": data_quality_score,
            "last_20_performance": last_20_performance,
        }
    )
    autonomy = status in {"EDGE_CANDIDATE", "EDGE_VALIDATED_PAPER"}
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "sample_size": closed_count,
        "closed_count": closed_count,
        "open_count": open_count,
        "invalid_count": invalid_count,
        "winrate": winrate,
        "avg_R": expectancy_r,
        "expectancy_R": expectancy_r,
        "profit_factor": profit_factor,
        "max_loss_streak": max_loss_streak,
        "timeout_rate": timeout_rate,
        "duplicate_rate": duplicate_rate,
        "data_quality_score": data_quality_score,
        "regime_context_tags": tags,
        "last_20_performance": last_20_performance,
        "stability_score": stability_score,
        "edge_status": status,
        "paper_autonomy_permission": autonomy,
        "real_execution_permission": False,
        "safe_to_open_real_trade": False,
        "private_api_used": False,
        "live_order_sent": False,
    }


def _match_rows(rows: list[dict[str, Any]], entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for row in rows:
        refs = dict(_entity_refs(row))
        if refs.get(entity_type) == entity_id:
            matched.append(row)
    return matched


def _current_edge_decision(
    entity_rows: list[dict[str, Any]],
    latest_trade_plan: dict[str, Any] | None,
    latest_decision_gate: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = latest_trade_plan or {}
    decision = latest_decision_gate or {}
    candidates: list[tuple[int, dict[str, Any]]] = []
    contract_id = str(plan.get("contract_id") or decision.get("contract_id") or "").strip()
    setup_family = str(plan.get("setup_family") or decision.get("setup_family") or "").strip()
    direction = str(plan.get("direction") or decision.get("direction") or "").upper()
    for row in entity_rows:
        if row["entity_type"] == "CONTRACT" and contract_id and row["entity_id"] == contract_id:
            candidates.append((3, row))
        elif row["entity_type"] == "SETUP_FAMILY" and setup_family and row["entity_id"] == setup_family:
            candidates.append((2, row))
    chosen = max(candidates, key=lambda item: (item[0], item[1].get("stability_score", 0.0)), default=(0, None))[1]
    if chosen is None:
        return {
            "entity_type": "UNKNOWN",
            "entity_id": contract_id or setup_family or "UNKNOWN",
            "direction": direction,
            "edge_status": "EDGE_WATCHLIST",
            "paper_autonomy_permission": False,
            "edge_block": False,
            "reason_codes": ["EDGE_VALIDATION_UNAVAILABLE_FOR_CURRENT_PLAN"],
            "real_execution_permission": False,
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        }
    edge_status = str(chosen["edge_status"])
    autonomy = bool(chosen["paper_autonomy_permission"])
    block = edge_status in {"EDGE_REJECTED", "EDGE_DISABLED"}  # WATCHLIST/PROBATION trade açabilir
    return {
        "entity_type": chosen["entity_type"],
        "entity_id": chosen["entity_id"],
        "direction": direction,
        "edge_status": edge_status,
        "paper_autonomy_permission": autonomy,
        "edge_block": block,
        "reason_codes": [f"EDGE_STATUS_{edge_status}", f"EDGE_ENTITY_{chosen['entity_type']}_{chosen['entity_id']}"],
        "real_execution_permission": False,
        "safe_to_open_real_trade": False,
        "private_api_used": False,
        "live_order_sent": False,
    }


def _report_markdown(payload: dict[str, Any]) -> str:
    rows = payload.get("edge_rows") or []
    top_rows = rows[:10]
    lines = [
        "# Edge Validation Governor",
        "",
        f"- Timestamp: {payload.get('timestamp_utc')}",
        f"- Current edge status: {(payload.get('current_edge_decision') or {}).get('edge_status')}",
        f"- Autonomous paper permission: {payload.get('paper_autonomy_permission')}",
        f"- Real trade allowed: {payload.get('real_trade_allowed')}",
        f"- Status counts: {json.dumps(payload.get('edge_status_counts') or {}, ensure_ascii=False)}",
        f"- Input rows: {json.dumps(payload.get('input_row_counts') or {}, ensure_ascii=False)}",
        "",
        "## Top Rows",
    ]
    for row in top_rows:
        lines.append(
            f"- {row['entity_type']}:{row['entity_id']} | {row['edge_status']} | sample={row['closed_count']} "
            f"exp={row['expectancy_R']} pf={row['profit_factor']} last20={row['last_20_performance']}"
        )
    lines.append("")
    return "\n".join(lines)


def run_edge_validation_governor(symbol: str = "BTCUSDT") -> dict[str, Any]:
    context = current_runtime_context(symbol)
    latest_trade_plan = load_json(LATEST_CONTRACT_TRADE_PLAN_PATH) or {}
    latest_decision_gate = load_json(LATEST_CONTRACT_DECISION_GATE_PATH) or {}
    latest_paper_factory = load_json(LATEST_PAPER_TRADE_FACTORY_PATH) or {}
    latest_outcome_accounting = load_json(STATE_DIR / "epoch_v2" / "latest_outcome_accounting.json") or {}

    closed_rows, invalid_rows, open_rows = _iter_lifecycle_events()
    opened_rows = _iter_factory_opens()
    outcome_rows = _iter_outcome_accounting_rows()
    edge_matrix_rows = _iter_contract_edge_rows()
    data_quality_score = _global_data_quality_score(
        latest_outcome_accounting,
        latest_paper_factory,
        outcome_rows=outcome_rows,
        edge_matrix_rows=edge_matrix_rows,
    )

    entity_keys: set[tuple[str, str]] = set()
    for row in [*closed_rows, *invalid_rows, *open_rows, *opened_rows]:
        entity_keys.update(_entity_refs(row))

    entity_rows: list[dict[str, Any]] = []
    for entity_type, entity_id in sorted(entity_keys):
        entity_rows.append(
            _build_entity_row(
                entity_type=entity_type,
                entity_id=entity_id,
                closed_rows=_match_rows(closed_rows, entity_type, entity_id),
                open_rows=_match_rows(open_rows, entity_type, entity_id),
                invalid_rows=_match_rows(invalid_rows, entity_type, entity_id),
                opened_rows=_match_rows(opened_rows, entity_type, entity_id),
                data_quality_score=data_quality_score,
            )
        )
    entity_rows.sort(
        key=lambda row: (
            str(row["edge_status"]) != "EDGE_VALIDATED_PAPER",
            str(row["edge_status"]) != "EDGE_CANDIDATE",
            -float(row["stability_score"]),
            -int(row["closed_count"]),
        )
    )
    current_edge = _current_edge_decision(entity_rows, latest_trade_plan, latest_decision_gate)
    status_counts = Counter(str(row["edge_status"]) for row in entity_rows)
    payload = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "source": {"source_mode": "EDGE_HISTORY_TAIL_ANALYSIS"},
            "max_tail_rows": MAX_TAIL_ROWS,
            "latest_trade_plan_ref": {
                "path": str(LATEST_CONTRACT_TRADE_PLAN_PATH),
                "exists": LATEST_CONTRACT_TRADE_PLAN_PATH.exists(),
            },
            "latest_decision_gate_ref": {
                "path": str(LATEST_CONTRACT_DECISION_GATE_PATH),
                "exists": LATEST_CONTRACT_DECISION_GATE_PATH.exists(),
            },
            "edge_rows": entity_rows[:200],
            "edge_status_counts": dict(status_counts),
            "input_row_counts": {
                "research_paper_lifecycle_history": len(closed_rows) + len(invalid_rows) + len(open_rows),
                "outcome_accounting_history": len(outcome_rows),
                "contract_edge_matrix_history": len(edge_matrix_rows),
                "paper_trade_factory_history": len(opened_rows),
            },
            "current_edge_decision": current_edge,
            "paper_autonomy_permission": bool(current_edge.get("paper_autonomy_permission")),
            "real_execution_permission": False,
            "real_trade_allowed": False,
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
            "data_quality": {
                "level": "HIGH" if entity_rows else "MEDIUM",
                "score": data_quality_score,
                "missing_inputs": [
                    name
                    for name, ok in {
                        "research_paper_lifecycle_history": RESEARCH_LIFECYCLE_HISTORY_PATH.exists(),
                        "outcome_accounting_history": OUTCOME_ACCOUNTING_HISTORY_PATH.exists(),
                        "contract_edge_matrix_history": CONTRACT_EDGE_MATRIX_HISTORY_PATH.exists(),
                        "paper_trade_factory_history": PAPER_FACTORY_HISTORY_PATH.exists(),
                    }.items()
                    if not ok
                ],
            },
            "reason_codes": [
                f"EDGE_ROWS_{len(entity_rows)}",
                f"CURRENT_EDGE_{current_edge.get('edge_status')}",
                f"AUTONOMY_{bool(current_edge.get('paper_autonomy_permission'))}",
                "PAPER_ONLY",
                "NO_REAL_TRADE",
                "NO_PRIVATE_API",
            ],
            "feeds_next": ["CONTRACT_DECISION_GATE", "MODEL_FEEDBACK_DIAGNOSTIC"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        symbol,
        context,
    )
    write_json(OUTPUT_PATH, payload)
    _append_jsonl(HISTORY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_report_markdown(payload), encoding="utf-8")
    return payload


def main() -> None:
    print(json.dumps(run_edge_validation_governor(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
