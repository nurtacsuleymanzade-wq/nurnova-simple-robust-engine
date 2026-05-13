from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import (
    compact_lineage,
    current_runtime_context,
    load_json,
    parse_ts,
    safe_float,
    stamp_payload,
    utc_now,
    write_json,
)

BLOCK_ID = "RESEARCH_PAPER_LIFECYCLE_ENGINE"
OUTPUT_PATH = epoch_state_path("latest_research_paper_lifecycle.json")
HISTORY_PATH = epoch_data_path("research_paper_lifecycle_history.jsonl")
FACTORY_HISTORY_PATH = epoch_data_path("paper_trade_factory_history.jsonl")
STATE_DIR = Path("state/simple")
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MAX_HISTORY_ROWS = 5000
MAX_OPEN_TRADES = 50


def _current_price(observation: dict[str, Any], dna: dict[str, Any]) -> float | None:
    price = safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if price is not None:
        return price
    return safe_float(((dna.get("1m") or {}).get("close")))


def _age_seconds(opened_at: Any, now_ts: str) -> int:
    opened_dt = parse_ts(opened_at)
    now_dt = parse_ts(now_ts)
    if opened_dt is None or now_dt is None:
        return 0
    return max(0, int((now_dt - opened_dt).total_seconds()))


def _compact_trade(trade: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "epoch_id",
        "symbol",
        "paper_trade_id",
        "context_id",
        "loop_id",
        "model_id",
        "setup_family",
        "direction",
        "entry",
        "stop_loss",
        "tp1",
        "tp2",
        "primary_tf",
        "trigger_tf",
        "context_tf",
        "structure_tf",
        "rr1",
        "rr2",
        "risk_distance",
        "tp1_distance",
        "tp2_distance",
        "plan_style",
        "expected_hold_label",
        "opened_at_utc",
        "closed_at_utc",
        "close_reason",
        "outcome_status",
        "status",
        "hold_seconds",
        "mfe",
        "mae",
        "r_result",
        "current_price",
        "exit_price",
        "valid_for_lifecycle",
        "valid_for_edge",
        "invalid_reason",
        "invalid_reason_codes",
        "cause_chain",
        "source_state_refs",
    )
    compact = {field: trade.get(field) for field in keep if field in trade}
    compact["execution_safety"] = {"live_order_sent": False, "private_api_used": False}
    return compact


def _collect_factory_trades() -> dict[str, dict[str, Any]]:
    trades: dict[str, dict[str, Any]] = {}
    for payload in read_jsonl_tail_objects(FACTORY_HISTORY_PATH, max_lines=MAX_HISTORY_ROWS):
        for trade in payload.get("newest_opened_this_loop") or payload.get("top_candidate_diagnostics") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                trades[trade_id] = dict(trade)
    return trades


def _collect_lifecycle_history() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    open_map: dict[str, dict[str, Any]] = {}
    closed_map: dict[str, dict[str, Any]] = {}
    for payload in read_jsonl_tail_objects(HISTORY_PATH, max_lines=MAX_HISTORY_ROWS):
        for trade in payload.get("open_trades") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                open_map[trade_id] = dict(trade)
        for trade in payload.get("trades_closed_this_loop") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                closed_map[trade_id] = dict(trade)
                open_map.pop(trade_id, None)
    return open_map, closed_map


def _close_trade(trade: dict[str, Any], current_price: float | None, now_ts: str) -> dict[str, Any]:
    updated = dict(trade)
    updated["epoch_id"] = ACTIVE_EPOCH_ID
    updated["current_price"] = current_price
    updated["opened_at_utc"] = updated.get("opened_at_utc") or now_ts
    updated["hold_seconds"] = _age_seconds(updated.get("opened_at_utc"), now_ts)
    updated["mfe"] = round(max(safe_float(updated.get("mfe")) or 0.0, 0.0), 8)
    updated["mae"] = round(max(safe_float(updated.get("mae")) or 0.0, 0.0), 8)
    updated["status"] = "OPEN"
    updated["outcome_status"] = "OPEN"

    entry = safe_float(updated.get("entry"))
    stop_loss = safe_float(updated.get("stop_loss"))
    tp1 = safe_float(updated.get("tp1"))
    tp2 = safe_float(updated.get("tp2"))
    risk_distance = safe_float(updated.get("risk_distance"))
    direction = str(updated.get("direction") or "").upper()

    invalid_reasons = list(updated.get("invalid_reason_codes") or [])
    if not updated.get("primary_tf") or not _is_numeric(updated.get("rr1")) or not _is_numeric(updated.get("rr2")):
        invalid_reasons.append("MISSING_TIMEFRAME_OR_RR")
    if invalid_reasons:
        updated["valid_for_edge"] = False
        updated["invalid_reason_codes"] = sorted(set(invalid_reasons))
        existing_invalid_reasons = str(updated.get("invalid_reason") or "").split("|") if updated.get("invalid_reason") else []
        updated["invalid_reason"] = "|".join(sorted(set([*existing_invalid_reasons, *invalid_reasons])))

    if current_price is None or entry is None or risk_distance is None or risk_distance <= 0:
        updated["status"] = "INVALID"
        updated["close_reason"] = "INVALID"
        updated["outcome_status"] = "INVALID"
        updated["closed_at_utc"] = now_ts
        updated["valid_for_edge"] = False
        updated["invalid_reason"] = "|".join(item for item in [updated.get("invalid_reason"), "PRICE_OR_RISK_INVALID"] if item)
        return updated

    if direction == "LONG":
        favorable = (current_price - entry) / risk_distance
        adverse = (entry - current_price) / risk_distance
    else:
        favorable = (entry - current_price) / risk_distance
        adverse = (current_price - entry) / risk_distance
    updated["mfe"] = round(max(safe_float(updated.get("mfe")) or 0.0, favorable), 8)
    updated["mae"] = round(max(safe_float(updated.get("mae")) or 0.0, adverse), 8)

    close_reason = None
    exit_price = current_price
    if direction == "LONG":
        if tp2 is not None and current_price >= tp2:
            close_reason, exit_price = "TP2_HIT", tp2
        elif tp1 is not None and current_price >= tp1:
            close_reason, exit_price = "TP1_HIT", tp1
        elif stop_loss is not None and current_price <= stop_loss:
            close_reason, exit_price = "SL_HIT", stop_loss
    elif direction == "SHORT":
        if tp2 is not None and current_price <= tp2:
            close_reason, exit_price = "TP2_HIT", tp2
        elif tp1 is not None and current_price <= tp1:
            close_reason, exit_price = "TP1_HIT", tp1
        elif stop_loss is not None and current_price >= stop_loss:
            close_reason, exit_price = "SL_HIT", stop_loss

    if close_reason is None and updated["hold_seconds"] >= int(updated.get("max_holding_seconds") or 1800):
        close_reason, exit_price = "EXPIRED", current_price

    if close_reason is None:
        return updated

    updated["status"] = close_reason
    updated["close_reason"] = close_reason
    updated["closed_at_utc"] = now_ts
    updated["exit_price"] = exit_price
    updated["outcome_status"] = "CLOSED"
    updated["r_result"] = round(((exit_price - entry) / risk_distance) if direction == "LONG" else ((entry - exit_price) / risk_distance), 8)
    if "MISSING_TIMEFRAME_OR_RR" in invalid_reasons:
        updated["status"] = "INVALID"
        updated["close_reason"] = "INVALID"
        updated["outcome_status"] = "INVALID"
    return updated


def _is_numeric(value: Any) -> bool:
    return safe_float(value) is not None


def run_research_paper_lifecycle_engine() -> dict[str, Any]:
    context = current_runtime_context()
    observation = load_json(OBSERVATION_PATH) or {}
    dna = load_json(DNA_PATH) or {}
    current_price = _current_price(observation, dna)
    now_ts = utc_now()

    factory_trades = _collect_factory_trades()
    open_map, closed_map = _collect_lifecycle_history()

    for trade_id, trade in factory_trades.items():
        if trade_id in closed_map or trade_id in open_map:
            continue
        open_map[trade_id] = dict(trade)

    next_open: dict[str, dict[str, Any]] = {}
    closed_this_loop: dict[str, dict[str, Any]] = {}
    invalid_this_loop: dict[str, dict[str, Any]] = {}
    missing_timeframe_count = 0
    missing_rr_count = 0

    for trade_id, trade in open_map.items():
        updated = _close_trade(trade, current_price, now_ts)
        updated.update(compact_lineage(trade))
        if "MISSING_TIMEFRAME_OR_RR" in (updated.get("invalid_reason_codes") or []):
            missing_timeframe_count += 0 if updated.get("primary_tf") else 1
            missing_rr_count += 1 if (not _is_numeric(updated.get("rr1")) or not _is_numeric(updated.get("rr2"))) else 0
        if str(updated.get("outcome_status") or "").upper() == "OPEN":
            next_open[trade_id] = updated
            continue
        if trade_id in closed_map:
            continue
        if str(updated.get("outcome_status") or "").upper() == "INVALID":
            invalid_this_loop[trade_id] = updated
        else:
            closed_this_loop[trade_id] = updated
        closed_map[trade_id] = updated

    recent_closed = sorted(
        [_compact_trade(item) for item in closed_map.values() if str(item.get("outcome_status") or "").upper() == "CLOSED"],
        key=lambda item: str(item.get("closed_at_utc") or ""),
    )[-200:]
    recent_invalid = sorted(
        [_compact_trade(item) for item in closed_map.values() if str(item.get("outcome_status") or "").upper() == "INVALID"],
        key=lambda item: str(item.get("closed_at_utc") or ""),
    )[-200:]
    open_trades = sorted(
        [_compact_trade(item) for item in next_open.values()],
        key=lambda item: str(item.get("opened_at_utc") or ""),
    )[-MAX_OPEN_TRADES:]

    duplicate_closed_ids = len(closed_map) - len({trade.get("paper_trade_id") for trade in closed_map.values()})
    tp = sum(1 for trade in closed_map.values() if str(trade.get("close_reason") or "").upper() in {"TP1_HIT", "TP2_HIT"})
    sl = sum(1 for trade in closed_map.values() if str(trade.get("close_reason") or "").upper() == "SL_HIT")
    expired = sum(1 for trade in closed_map.values() if str(trade.get("close_reason") or "").upper() == "EXPIRED")

    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "block_id": BLOCK_ID,
            "source": {"source_mode": "EPOCH_V2_FACTORY_AND_LIFECYCLE_HISTORY"},
            "current_price": current_price,
            "open_trades": open_trades,
            "recent_closed": recent_closed,
            "recent_invalid": recent_invalid,
            "trades_closed_this_loop": [_compact_trade(item) for item in list(closed_this_loop.values()) + list(invalid_this_loop.values())],
            "summary": {
                "opened": len(factory_trades),
                "open": len(open_trades),
                "closed": len(recent_closed),
                "invalid": len(recent_invalid),
                "tp": tp,
                "sl": sl,
                "expired": expired,
            },
            "quality_counters": {
                "duplicate_paper_trade_id_count": duplicate_closed_ids,
                "missing_timeframe_count": missing_timeframe_count,
                "missing_rr_count": missing_rr_count,
            },
            "reason_codes": [
                f"OPEN_{len(open_trades)}",
                f"CLOSED_{len(recent_closed)}",
                f"INVALID_{len(recent_invalid)}",
                f"DUPLICATES_{duplicate_closed_ids}",
                "PAPER_ONLY",
                "NO_LIVE_EXECUTION",
                "NO_PRIVATE_API",
            ],
            "data_quality": {
                "level": "HIGH" if FACTORY_HISTORY_PATH.exists() else "MEDIUM",
                "missing_inputs": [name for name, ok in {
                    "epoch_v2/paper_trade_factory_history.jsonl": FACTORY_HISTORY_PATH.exists(),
                    "epoch_v2/research_paper_lifecycle_history.jsonl": HISTORY_PATH.exists(),
                }.items() if not ok],
            },
            "feeds_next": ["OUTCOME_ACCOUNTING_ENGINE", "RESEARCH_EDGE_MATRIX_ENGINE"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        str(observation.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("research_paper_lifecycle_history.jsonl", output)
    return output


def main() -> None:
    print(json.dumps(run_research_paper_lifecycle_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
