"""S25 - Telegram follow-up notifier for paper lifecycle/outcome events."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

BLOCK_ID = "S25_TELEGRAM_FOLLOWUP"
FEEDS_NEXT = {"next_blocks": ["S22_EDGE_MATRIX_V2"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

LIFECYCLE_PATH = STATE_DIR / "latest_paper_lifecycle.json"
OUTCOME_PATH = STATE_DIR / "latest_outcome_monitor.json"
TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"
DECISION_GATE_PATH = STATE_DIR / "latest_decision_gate.json"

LATEST_PATH = STATE_DIR / "latest_telegram_followup.json"
S25_STATE_PATH = STATE_DIR / "s25_telegram_followup_state.json"
HISTORY_PATH = DATA_DIR / "telegram_followup_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s25_telegram_followup_latest_report.md"

ALLOWED_STATUS = {
    "SENT",
    "NO_NEW_EVENT",
    "BLOCKED_MISSING_ENV",
    "NO_LIFECYCLE",
    "INVALID",
}
ALLOWED_EVENT_TYPES = {
    "ENTRY_TOUCHED",
    "TP1_HIT",
    "TP2_HIT",
    "SL_HIT",
    "INVALIDATED",
    "CLOSED",
}
SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _resolve_event(
    lifecycle: dict[str, Any],
    outcome: dict[str, Any] | None,
) -> tuple[str, str | None, int | None]:
    lifecycle_id = lifecycle.get("lifecycle_id")
    lifecycle_status = lifecycle.get("lifecycle_status")
    events = list(lifecycle.get("lifecycle_events") or [])
    latest_ts = lifecycle.get("timestamp_utc")
    outcome_status = (outcome or {}).get("outcome_status")

    if not lifecycle_id or lifecycle_status == "NO_LIFECYCLE":
        return "NO_LIFECYCLE", None, None

    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        event_type = event.get("event")
        if event_type in ALLOWED_EVENT_TYPES:
            return event_type, event.get("timestamp_utc") or latest_ts, index

    if lifecycle_status == "CLOSED" and outcome_status == "CLOSED":
        return "CLOSED", latest_ts, len(events)

    return "NO_NEW_EVENT", None, None


def _event_key(lifecycle_id: Any, event_type: str, lifecycle_status: Any, event_ts: Any, event_index: int | None) -> str:
    suffix = event_ts or f"event_index:{event_index}"
    return f"{lifecycle_id}|{event_type}|{lifecycle_status}|{suffix}"


def _format_num(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _format_message(
    lifecycle: dict[str, Any],
    outcome: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    event_type: str,
    event_ts: str | None,
) -> str:
    current_price = lifecycle.get("current_price")
    final_price = (outcome or {}).get("final_price")
    realized_r = (outcome or {}).get("realized_r")
    unrealized_r = lifecycle.get("unrealized_r")
    lines = [
        "PAPER ONLY / REAL TRADE DISABLED",
        f"Event: {event_type}",
        f"Timestamp: {event_ts or lifecycle.get('timestamp_utc')}",
        f"Symbol: {lifecycle.get('symbol', 'UNKNOWN')}",
        f"Side: {lifecycle.get('side', 'UNKNOWN')}",
        f"Entry: {_format_num(lifecycle.get('entry_price'))}",
        f"SL: {_format_num(lifecycle.get('stop_loss'))}",
        f"TP1: {_format_num(lifecycle.get('tp1'))}",
        f"TP2: {_format_num(lifecycle.get('tp2'))}",
        f"Current Price: {_format_num(current_price)}",
        f"Final Price: {_format_num(final_price)}",
        f"Realized R: {_format_num(realized_r)}",
        f"Unrealized R: {_format_num(unrealized_r)}",
        f"Plan Status: {(trade_plan or {}).get('plan_status', 'UNKNOWN')}",
        f"Lifecycle Status: {lifecycle.get('lifecycle_status', 'UNKNOWN')}",
        f"Outcome Status: {(outcome or {}).get('outcome_status', 'UNKNOWN')}",
        f"Outcome Result: {(outcome or {}).get('outcome_result', 'UNKNOWN')}",
        "safe_to_open_real_trade=false",
        "private_api_used=false",
        "live_order_sent=false",
    ]
    return "\n".join(lines)


def _send_telegram(token: str, chat_id: str, message_text: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = parse.urlencode({"chat_id": chat_id, "text": message_text}).encode("utf-8")
    req = request.Request(url, data=payload, method="POST")
    with request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def run_telegram_followup_notifier() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lifecycle = _load_json(LIFECYCLE_PATH)
    outcome = _load_json(OUTCOME_PATH)
    trade_plan = _load_json(TRADE_PLAN_PATH)
    decision_gate = _load_json(DECISION_GATE_PATH)
    prior_state = _load_json(S25_STATE_PATH) or {}

    ts = _utc_now()
    base = {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": (lifecycle or {}).get("symbol") or (trade_plan or {}).get("symbol") or "UNKNOWN",
        "lifecycle_id": (lifecycle or {}).get("lifecycle_id"),
        "event_type": None,
        "followup_status": "INVALID",
        "message_text": "PAPER ONLY / REAL TRADE DISABLED",
        "telegram_sent": False,
        "telegram_response_ok": False,
        "event_timestamp_utc": None,
        "event_index": None,
        "dedup_key": None,
        "lifecycle_status": (lifecycle or {}).get("lifecycle_status"),
        "outcome_status": (outcome or {}).get("outcome_status"),
        "decision_status": (decision_gate or {}).get("decision_status"),
        "side": (lifecycle or {}).get("side") or (trade_plan or {}).get("side"),
        "entry_price": (lifecycle or {}).get("entry_price"),
        "stop_loss": (lifecycle or {}).get("stop_loss"),
        "tp1": (lifecycle or {}).get("tp1"),
        "tp2": (lifecycle or {}).get("tp2"),
        "current_price": (lifecycle or {}).get("current_price"),
        "final_price": (outcome or {}).get("final_price"),
        "realized_r": (outcome or {}).get("realized_r"),
        "unrealized_r": (lifecycle or {}).get("unrealized_r"),
        "reason_codes": [],
        "execution_safety": dict(SAFETY),
        "private_api_used": False,
        "live_order_sent": False,
        "safe_to_open_real_trade": False,
        "feeds_next": FEEDS_NEXT,
    }

    if not lifecycle or not outcome:
        base["followup_status"] = "NO_LIFECYCLE"
        base["reason_codes"] = [
            "FOLLOWUP_STATUS_NO_LIFECYCLE",
            "MISSING_LIFECYCLE_OR_OUTCOME",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ]
        _persist(base, prior_state)
        return base

    event_type, event_ts, event_index = _resolve_event(lifecycle, outcome)
    base["event_type"] = None if event_type == "NO_NEW_EVENT" else event_type
    base["event_timestamp_utc"] = event_ts
    base["event_index"] = event_index
    base["message_text"] = _format_message(lifecycle, outcome, trade_plan, event_type, event_ts)

    if event_type == "NO_LIFECYCLE":
        base["followup_status"] = "NO_LIFECYCLE"
        base["reason_codes"] = [
            "FOLLOWUP_STATUS_NO_LIFECYCLE",
            "NO_ACTIVE_LIFECYCLE_ID",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ]
        _persist(base, prior_state)
        return base

    if event_type == "NO_NEW_EVENT":
        base["followup_status"] = "NO_NEW_EVENT"
        base["reason_codes"] = [
            "FOLLOWUP_STATUS_NO_NEW_EVENT",
            f"LIFECYCLE_STATUS_{lifecycle.get('lifecycle_status', 'UNKNOWN')}",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ]
        _persist(base, prior_state)
        return base

    lifecycle_status = lifecycle.get("lifecycle_status")
    dedup_key = _event_key(lifecycle.get("lifecycle_id"), event_type, lifecycle_status, event_ts, event_index)
    base["dedup_key"] = dedup_key

    if dedup_key == prior_state.get("last_dedup_key"):
        base["followup_status"] = "NO_NEW_EVENT"
        base["reason_codes"] = [
            "FOLLOWUP_STATUS_NO_NEW_EVENT",
            "DEDUPLICATED_REPEAT_EVENT",
            f"EVENT_TYPE_{event_type}",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ]
        _persist(base, prior_state)
        return base

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        base["followup_status"] = "BLOCKED_MISSING_ENV"
        base["reason_codes"] = [
            "FOLLOWUP_STATUS_BLOCKED_MISSING_ENV",
            f"EVENT_TYPE_{event_type}",
            "TELEGRAM_ENV_MISSING",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ]
        _persist(base, prior_state)
        return base

    try:
        response = _send_telegram(token, chat_id, base["message_text"])
        ok = bool(response.get("ok"))
        base["telegram_response_ok"] = ok
        base["telegram_sent"] = ok
        base["followup_status"] = "SENT" if ok else "INVALID"
        base["reason_codes"] = [
            f"FOLLOWUP_STATUS_{base['followup_status']}",
            f"EVENT_TYPE_{event_type}",
            f"LIFECYCLE_STATUS_{lifecycle_status}",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ]
    except Exception as exc:
        base["followup_status"] = "INVALID"
        base["reason_codes"] = [
            "FOLLOWUP_STATUS_INVALID",
            f"EVENT_TYPE_{event_type}",
            f"TELEGRAM_SEND_ERROR_{type(exc).__name__}",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ]

    assert base["followup_status"] in ALLOWED_STATUS
    _persist(base, prior_state)
    return base


def _persist(result: dict[str, Any], prior_state: dict[str, Any]) -> None:
    _atomic_write(LATEST_PATH, json.dumps(result, indent=2, ensure_ascii=False))
    state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S25_TELEGRAM_FOLLOWUP_STATE",
        "last_lifecycle_id": result["lifecycle_id"],
        "last_event_type": result["event_type"],
        "last_followup_status": result["followup_status"],
        "last_event_timestamp_utc": result["event_timestamp_utc"],
        "last_event_index": result["event_index"],
        "last_dedup_key": result["dedup_key"],
        "runs": int(prior_state.get("runs") or 0) + 1,
        "safe_to_open_real_trade": False,
        "private_api_used": False,
        "live_order_sent": False,
    }
    _atomic_write(S25_STATE_PATH, json.dumps(state, indent=2, ensure_ascii=False))
    _append_jsonl(HISTORY_PATH, result)
    _write_report(result)


def _write_report(result: dict[str, Any]) -> None:
    lines = [
        "# S25 Telegram Follow-up Latest Report",
        "",
        f"**Timestamp:** {result['timestamp_utc']}",
        f"**Symbol:** {result['symbol']}",
        f"**Lifecycle ID:** {result['lifecycle_id']}",
        f"**Event Type:** {result['event_type']}",
        f"**Follow-up Status:** {result['followup_status']}",
        f"**Lifecycle Status:** {result['lifecycle_status']}",
        f"**Outcome Status:** {result['outcome_status']}",
        f"**Dedup Key:** {result['dedup_key']}",
        f"**Telegram Sent:** {result['telegram_sent']}",
        f"**Telegram Response OK:** {result['telegram_response_ok']}",
        f"**Safe To Open Real Trade:** {result['safe_to_open_real_trade']}",
        "",
        "## Message",
        "",
        "```",
        result["message_text"],
        "```",
    ]
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")
