from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.simple.jsonl_tail_reader import read_jsonl_tail_objects, safe_read_json
from src.simple.research_runtime import (
    append_jsonl,
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
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_research_paper_lifecycle.json"
HISTORY_PATH = DATA_DIR / "research_paper_lifecycle_history.jsonl"

PAPER_FACTORY_PATH = STATE_DIR / "latest_paper_trade_factory.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"

MAX_OPEN_TRADES = 20
MAX_RECENT_CLOSED = 20
MAX_RECENT_INVALID = 20
MAX_HISTORY_TAIL_ROWS = 5000
LATEST_FILE_MAX_BYTES = 500_000


def _empty_summary() -> dict[str, int]:
    return {
        "opened": 0,
        "open": 0,
        "closed": 0,
        "invalid": 0,
        "tp": 0,
        "sl": 0,
        "expired": 0,
    }


def _current_price(observation: dict[str, Any], dna: dict[str, Any]) -> float | None:
    price = safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if price is not None:
        return price
    return safe_float((((dna.get("1m") or {}).get("close"))))


def _load_previous_snapshot() -> dict[str, Any]:
    latest, latest_reason = safe_read_json(OUTPUT_PATH, default={}, max_bytes=LATEST_FILE_MAX_BYTES)
    if isinstance(latest, dict) and latest:
        return latest
    tail = read_jsonl_tail_objects(HISTORY_PATH, max_lines=5)
    previous = tail[-1] if tail else {}
    if latest_reason == "FILE_TOO_LARGE":
        previous.setdefault("reason_codes", []).append("FILE_TOO_LARGE_SKIPPED")
    return previous


def _count_close_reasons(trades: list[dict[str, Any]]) -> dict[str, int]:
    tp = 0
    sl = 0
    expired = 0
    invalid = 0
    for trade in trades:
        status = str(trade.get("status") or trade.get("close_reason") or "").upper()
        outcome_status = str(trade.get("outcome_status") or "").upper()
        if status in {"TP1_HIT", "TP2_HIT"}:
            tp += 1
        elif status == "SL_HIT":
            sl += 1
        elif status == "EXPIRED":
            expired += 1
        if outcome_status == "INVALID":
            invalid += 1
    return {"tp": tp, "sl": sl, "expired": expired, "invalid": invalid}


def _closed_tail_from_history() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    closed_by_id: dict[str, dict[str, Any]] = {}
    invalid_by_id: dict[str, dict[str, Any]] = {}
    for payload in read_jsonl_tail_objects(HISTORY_PATH, max_lines=MAX_HISTORY_TAIL_ROWS):
        for key, target in (("trades_closed_this_loop", closed_by_id), ("recent_closed", closed_by_id), ("recent_invalid", invalid_by_id)):
            for trade in payload.get(key) or []:
                trade_id = str(trade.get("paper_trade_id") or "")
                if trade_id:
                    target[trade_id] = dict(trade)
    closed = sorted(
        [
            trade for trade in closed_by_id.values()
            if str(trade.get("outcome_status") or trade.get("status") or "").upper() == "CLOSED"
        ],
        key=lambda item: str(item.get("closed_at_utc") or item.get("timestamp_utc") or ""),
    )
    invalid = sorted(
        [
            trade for trade in {**closed_by_id, **invalid_by_id}.values()
            if str(trade.get("outcome_status") or "").upper() == "INVALID"
        ],
        key=lambda item: str(item.get("closed_at_utc") or item.get("timestamp_utc") or ""),
    )
    return closed[-MAX_RECENT_CLOSED:], invalid[-MAX_RECENT_INVALID:]


def _compact_trade(trade: dict[str, Any]) -> dict[str, Any]:
    keep_fields = (
        "paper_trade_id",
        "context_id",
        "loop_id",
        "symbol",
        "model_id",
        "model_family",
        "setup_family",
        "dominant_setup_family",
        "direction",
        "entry",
        "stop_loss",
        "tp1",
        "tp2",
        "risk_distance",
        "opened_at_utc",
        "closed_at_utc",
        "current_price",
        "exit_price",
        "status",
        "close_reason",
        "outcome_status",
        "invalid_for_edge",
        "r_result",
        "r_unrealized",
        "mfe",
        "mae",
        "reason_codes",
    )
    compact = {field: trade.get(field) for field in keep_fields if field in trade}
    compact["execution_safety"] = {
        "live_order_sent": False,
        "private_api_used": False,
    }
    return compact


def _age_seconds(opened_at: Any, now_ts: str) -> int:
    opened_dt = parse_ts(opened_at)
    now_dt = parse_ts(now_ts)
    if opened_dt is None or now_dt is None:
        return 0
    return max(0, int((now_dt - opened_dt).total_seconds()))


def _trade_update(trade: dict[str, Any], current_price: float | None, now_ts: str) -> dict[str, Any]:
    updated = dict(trade)
    entry = safe_float(updated.get("entry"))
    risk_distance = safe_float(updated.get("risk_distance"))
    direction = str(updated.get("direction") or "UNKNOWN").upper()
    tp1 = safe_float(updated.get("tp1"))
    tp2 = safe_float(updated.get("tp2"))
    stop_loss = safe_float(updated.get("stop_loss"))

    opened_at_utc = updated.get("opened_at_utc") or updated.get("opened_at")
    updated["opened_at_utc"] = opened_at_utc
    updated["hold_seconds"] = _age_seconds(opened_at_utc, now_ts)
    updated.setdefault("mfe", 0.0)
    updated.setdefault("mae", 0.0)
    updated.setdefault("path_snapshots_count", 0)
    updated["current_price"] = current_price
    updated["close_reason"] = None
    updated["outcome_status"] = "OPEN"
    updated["r_unrealized"] = None

    if current_price is None:
        updated["close_reason"] = "PRICE_MISSING"
        updated["reason"] = "PRICE_MISSING"
        updated["status"] = "OPEN"
        updated["outcome_status"] = "OPEN"
        return updated

    if entry is not None and risk_distance and risk_distance > 0:
        if direction == "LONG":
            favorable = (current_price - entry) / risk_distance
            adverse = (entry - current_price) / risk_distance
        else:
            favorable = (entry - current_price) / risk_distance
            adverse = (current_price - entry) / risk_distance
        updated["mfe"] = round(max(safe_float(updated.get("mfe")) or 0.0, favorable), 8)
        updated["mae"] = round(max(safe_float(updated.get("mae")) or 0.0, adverse), 8)
        updated["r_unrealized"] = round(favorable if direction in {"LONG", "SHORT"} else 0.0, 8)
    updated["path_snapshots_count"] = int(updated.get("path_snapshots_count") or 0) + 1
    updated["max_favorable_price"] = max(
        [price for price in [safe_float(updated.get("max_favorable_price")), current_price] if price is not None]
    ) if direction == "LONG" else min(
        [price for price in [safe_float(updated.get("max_favorable_price")), current_price] if price is not None]
    ) if direction == "SHORT" and any(price is not None for price in [safe_float(updated.get("max_favorable_price")), current_price]) else current_price
    updated["max_adverse_price"] = min(
        [price for price in [safe_float(updated.get("max_adverse_price")), current_price] if price is not None]
    ) if direction == "LONG" and any(price is not None for price in [safe_float(updated.get("max_adverse_price")), current_price]) else max(
        [price for price in [safe_float(updated.get("max_adverse_price")), current_price] if price is not None]
    ) if direction == "SHORT" else current_price

    close_reason = None
    exit_price = current_price
    if direction == "LONG":
        if tp2 is not None and current_price >= tp2:
            close_reason = "TP2_HIT"
            exit_price = tp2
        elif tp1 is not None and current_price >= tp1:
            close_reason = "TP1_HIT"
            exit_price = tp1
        elif stop_loss is not None and current_price <= stop_loss:
            close_reason = "SL_HIT"
            exit_price = stop_loss
    elif direction == "SHORT":
        if tp2 is not None and current_price <= tp2:
            close_reason = "TP2_HIT"
            exit_price = tp2
        elif tp1 is not None and current_price <= tp1:
            close_reason = "TP1_HIT"
            exit_price = tp1
        elif stop_loss is not None and current_price >= stop_loss:
            close_reason = "SL_HIT"
            exit_price = stop_loss

    if close_reason is None and updated["hold_seconds"] >= int(updated.get("max_holding_seconds") or 1800):
        close_reason = "EXPIRED"

    if close_reason:
        updated["closed_at_utc"] = now_ts
        updated["exit_price"] = exit_price
        updated["close_reason"] = close_reason
        updated["status"] = close_reason
        updated["outcome_status"] = "CLOSED"
        if entry is not None and risk_distance and risk_distance > 0 and exit_price is not None:
            if direction == "LONG":
                r_result = (exit_price - entry) / risk_distance
            else:
                r_result = (entry - exit_price) / risk_distance
            updated["r_result"] = round(r_result, 8)
        else:
            updated["r_result"] = None
    else:
        updated["status"] = "OPEN"
        updated["close_reason"] = updated.get("close_reason") or None
        updated["r_result"] = updated.get("r_result")

    if not updated.get("context_id") or not updated.get("model_id"):
        updated["invalid_for_edge"] = True
        if close_reason and updated["outcome_status"] == "CLOSED":
            updated["outcome_status"] = "INVALID"
    return updated


def run_research_paper_lifecycle_engine() -> dict[str, Any]:
    context = current_runtime_context()
    factory = load_json(PAPER_FACTORY_PATH) or {}
    observation = load_json(OBSERVATION_PATH) or {}
    dna = load_json(DNA_PATH) or {}
    previous = _load_previous_snapshot()
    now_ts = utc_now()
    current_price = _current_price(observation, dna)

    previous_open = {str(trade.get("paper_trade_id")): dict(trade) for trade in (previous.get("open_trades") or []) if trade.get("paper_trade_id")}
    previous_closed_ids = {
        str(trade.get("paper_trade_id") or "")
        for trade in [*(previous.get("recent_closed") or []), *(previous.get("recent_invalid") or [])]
        if str(trade.get("paper_trade_id") or "")
    }
    previous_reason_codes = list(previous.get("reason_codes") or [])

    new_trades_opened: list[dict[str, Any]] = []
    factory_candidates = factory.get("newest_opened_this_loop") or factory.get("top_candidate_diagnostics") or factory.get("paper_trades") or []
    for trade in factory_candidates:
        if str(trade.get("status") or "").upper() not in {"OPEN", "OPEN_CANDIDATE"}:
            continue
        if len(previous_open) >= MAX_OPEN_TRADES:
            break
        trade_id = str(trade.get("paper_trade_id") or "")
        if not trade_id or trade_id in previous_open or trade_id in previous_closed_ids:
            continue
        opened = dict(trade)
        opened["status"] = "OPEN"
        opened["opened_at_utc"] = opened.get("opened_at_utc") or opened.get("opened_at") or now_ts
        opened["current_price"] = current_price
        previous_open[trade_id] = opened
        new_trades_opened.append(opened)

    updated_open: dict[str, dict[str, Any]] = {}
    trades_closed_this_loop: list[dict[str, Any]] = []

    for trade_id, trade in previous_open.items():
        updated_trade = _trade_update(trade, current_price, now_ts)
        updated_trade.update(compact_lineage(trade, factory))
        if updated_trade.get("outcome_status") in {"CLOSED", "INVALID"}:
            trades_closed_this_loop.append(updated_trade)
        else:
            updated_open[trade_id] = updated_trade

    recent_closed_history, recent_invalid_history = _closed_tail_from_history()
    recent_closed_map = {
        str(trade.get("paper_trade_id") or ""): dict(trade)
        for trade in [*recent_closed_history, *trades_closed_this_loop]
        if str(trade.get("paper_trade_id") or "")
    }
    recent_invalid_map = {
        str(trade.get("paper_trade_id") or ""): dict(trade)
        for trade in [*recent_invalid_history, *trades_closed_this_loop]
        if str(trade.get("outcome_status") or "").upper() == "INVALID" and str(trade.get("paper_trade_id") or "")
    }
    recent_closed = sorted(
        [trade for trade in recent_closed_map.values() if str(trade.get("outcome_status") or "").upper() == "CLOSED"],
        key=lambda item: str(item.get("closed_at_utc") or item.get("timestamp_utc") or ""),
    )[-MAX_RECENT_CLOSED:]
    recent_invalid = sorted(
        list(recent_invalid_map.values()),
        key=lambda item: str(item.get("closed_at_utc") or item.get("timestamp_utc") or ""),
    )[-MAX_RECENT_INVALID:]
    open_trades = sorted(
        [_compact_trade(trade) for trade in updated_open.values()],
        key=lambda item: str(item.get("opened_at_utc") or item.get("timestamp_utc") or ""),
    )[-MAX_OPEN_TRADES:]
    recent_closed_compact = [_compact_trade(trade) for trade in recent_closed]
    recent_invalid_compact = [_compact_trade(trade) for trade in recent_invalid]
    closed_counts = _count_close_reasons([*recent_closed, *recent_invalid])
    latest_reason_codes = [
        f"OPEN_{len(open_trades)}",
        f"CLOSED_{len(recent_closed_compact)}",
        f"PRICE_AVAILABLE_{str(current_price is not None).upper()}",
        "NO_LIVE_EXECUTION",
        "NO_PRIVATE_API",
        "PAPER_ONLY",
    ]
    if current_price is None:
        latest_reason_codes.append("PRICE_MISSING")
    if "FILE_TOO_LARGE_SKIPPED" in previous_reason_codes:
        latest_reason_codes.append("FILE_TOO_LARGE_SKIPPED")

    output = stamp_payload(
        {
            "symbol": str(observation.get("symbol") or factory.get("symbol") or "BTCUSDT"),
            "block_id": BLOCK_ID,
            "source": {"source_mode": "PAPER_FACTORY_LIFECYCLE"},
            "current_price": current_price,
            "open_trades": open_trades,
            "recent_closed": recent_closed_compact,
            "recent_invalid": recent_invalid_compact,
            "new_trades_opened": [_compact_trade(trade) for trade in new_trades_opened[:MAX_OPEN_TRADES]],
            "trades_closed_this_loop": [_compact_trade(trade) for trade in trades_closed_this_loop[-MAX_RECENT_CLOSED:]],
            "summary": {
                "opened": len(new_trades_opened),
                "open": len(open_trades),
                "closed": len(recent_closed_compact),
                "invalid": len(recent_invalid_compact),
                "tp": closed_counts["tp"],
                "sl": closed_counts["sl"],
                "expired": closed_counts["expired"],
            },
            "reason_codes": sorted(set(latest_reason_codes)),
            "data_quality": {
                "level": "HIGH" if factory else "LOW",
                "missing_inputs": [name for name, payload in {
                    "latest_paper_trade_factory": factory,
                    "latest_observation_factory": observation,
                }.items() if not payload],
            },
            "feeds_next": ["RESEARCH_EDGE_MATRIX_ENGINE", "MODEL_FEEDBACK_DIAGNOSTIC"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        str(observation.get("symbol") or factory.get("symbol") or "BTCUSDT"),
        context,
    )
    for optional_field in ("sanitized_at_utc", "pre_sanitize_archive_path"):
        if previous.get(optional_field):
            output[optional_field] = previous.get(optional_field)

    write_json(OUTPUT_PATH, output)
    append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_research_paper_lifecycle_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
