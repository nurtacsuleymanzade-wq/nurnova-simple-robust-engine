from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from src.simple.research_runtime import append_jsonl, current_runtime_context, load_json, parse_ts, safe_float, stamp_payload, write_json

BLOCK_ID = "TELEGRAM_RESEARCH_REPORTER"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

SYSTEM_AUDIT_PATH = STATE_DIR / "latest_system_audit.json"
CONTEXT_SYNC_PATH = STATE_DIR / "latest_context_sync.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
SETUP_ACTIVATION_PATH = STATE_DIR / "latest_setup_family_activation.json"
PAPER_TRADE_FACTORY_PATH = STATE_DIR / "latest_paper_trade_factory.json"
LIFECYCLE_PATH = STATE_DIR / "latest_research_paper_lifecycle.json"
EDGE_PATH = STATE_DIR / "latest_research_edge_matrix.json"
FEEDBACK_PATH = STATE_DIR / "latest_model_feedback.json"
PROMOTION_PATH = STATE_DIR / "latest_model_promotion.json"
LIVE_GATE_PATH = STATE_DIR / "latest_live_eligibility_gate.json"

OUTPUT_PATH = STATE_DIR / "latest_telegram_report.json"
REPORTED_TRADES_PATH = STATE_DIR / "telegram_reported_trades.json"
HISTORY_PATH = DATA_DIR / "telegram_report_history.jsonl"

CLOSED_STATUSES = {"TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"}
UTC_PLUS_4 = timezone(timedelta(hours=4))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_number(value: Any, digits: int = 4) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _status_time_utc_plus_4(value: Any) -> str:
    dt = parse_ts(value) or datetime.now(timezone.utc)
    return dt.astimezone(UTC_PLUS_4).strftime("%Y-%m-%d %H:%M:%S UTC+4")


def _load_reported_state() -> dict[str, Any]:
    payload = load_json(REPORTED_TRADES_PATH) or {}
    return {
        "reported_open_trade_ids": list(payload.get("reported_open_trade_ids") or []),
        "reported_closed_trade_ids": list(payload.get("reported_closed_trade_ids") or []),
        "last_summary_sent_at_utc": payload.get("last_summary_sent_at_utc"),
        "updated_at_utc": payload.get("updated_at_utc"),
    }


def _write_reported_state(state: dict[str, Any]) -> None:
    write_json(
        REPORTED_TRADES_PATH,
        {
            "reported_open_trade_ids": sorted({str(item) for item in state.get("reported_open_trade_ids") or [] if item}),
            "reported_closed_trade_ids": sorted({str(item) for item in state.get("reported_closed_trade_ids") or [] if item}),
            "last_summary_sent_at_utc": state.get("last_summary_sent_at_utc"),
            "updated_at_utc": _utc_now(),
        },
    )


def _send_telegram(token: str, chat_id: str, message_text: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = parse.urlencode({"chat_id": chat_id, "text": message_text}).encode("utf-8")
    req = request.Request(url, data=payload, method="POST")
    with request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _trade_reason(trade: dict[str, Any]) -> str:
    reason = trade.get("reason")
    if reason:
        return str(reason)
    reasons = trade.get("activation_reasons") or trade.get("reason_codes") or []
    if isinstance(reasons, list) and reasons:
        return ", ".join(str(item) for item in reasons[:3])
    return "RESEARCH_SIGNAL"


def _best_model_name(feedback: dict[str, Any], promotion: dict[str, Any], edge: dict[str, Any]) -> str:
    for value in (
        (feedback.get("summary") or {}).get("best"),
        (promotion.get("feedback_summary") or {}).get("best"),
        (edge.get("summary") or {}).get("best_model_id"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "UNKNOWN"


def _worst_model_name(feedback: dict[str, Any], promotion: dict[str, Any]) -> str:
    for value in (
        (feedback.get("summary") or {}).get("worst"),
        (promotion.get("feedback_summary") or {}).get("worst"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "UNKNOWN"


def _summary_bottleneck(audit: dict[str, Any], sync: dict[str, Any], promotion: dict[str, Any], live_gate: dict[str, Any]) -> str:
    critical = audit.get("critical_issues") or []
    if critical:
        return str(critical[0])
    warnings = audit.get("warnings") or []
    if warnings:
        return str(warnings[0])
    mismatches = sync.get("context_mismatches") or []
    if mismatches:
        return "CONTEXT_MISMATCH"
    stale = sync.get("critical_stale") or []
    if stale:
        return "CRITICAL_STALE_STATE"
    sample_building = int((promotion.get("feedback_summary") or {}).get("sample_building") or 0)
    if sample_building > 0:
        return f"SAMPLE_BUILDING_{sample_building}"
    blockers = live_gate.get("blocking_reasons") or []
    if blockers:
        return str(blockers[0])
    return "NONE"


def _closed_stats(lifecycle: dict[str, Any]) -> dict[str, Any]:
    closed = list(lifecycle.get("closed_trades") or [])
    tp_count = sum(1 for trade in closed if str(trade.get("status") or trade.get("close_reason") or "").upper() in {"TP1_HIT", "TP2_HIT"})
    sl_count = sum(1 for trade in closed if str(trade.get("status") or trade.get("close_reason") or "").upper() == "SL_HIT")
    expired_count = sum(1 for trade in closed if str(trade.get("status") or trade.get("close_reason") or "").upper() == "EXPIRED")
    winrate = round(tp_count / len(closed), 4) if closed else None
    return {
        "closed_count": len(closed),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "expired_count": expired_count,
        "winrate": winrate,
    }


def _instant_signal_message(trade: dict[str, Any]) -> str:
    lines = [
        "PAPER TRADE SIGNAL",
        f"Pair: {trade.get('symbol') or 'UNKNOWN'}",
        f"Direction: {trade.get('direction') or 'UNKNOWN'}",
        f"Model: {trade.get('model_id') or trade.get('dominant_model_id') or 'UNKNOWN'}",
        f"Setup: {trade.get('setup_family') or trade.get('dominant_setup_family') or 'UNKNOWN'}",
        f"Reason: {_trade_reason(trade)}",
        f"Entry: {_format_number(trade.get('entry'))}",
        f"Stop Loss: {_format_number(trade.get('stop_loss'))}",
        f"TP1: {_format_number(trade.get('tp1'))}",
        f"TP2: {_format_number(trade.get('tp2'))}",
        f"RR: {_format_number(trade.get('rr_tp2') if safe_float(trade.get('rr_tp2')) is not None else trade.get('rr_tp1'))}",
        "Status: PAPER OPENED",
        f"Time UTC+4: {_status_time_utc_plus_4(trade.get('opened_at_utc') or trade.get('timestamp_utc'))}",
        "Live Trade OFF",
    ]
    return "\n".join(lines)


def _result_message(trade: dict[str, Any], lifecycle: dict[str, Any], feedback: dict[str, Any], promotion: dict[str, Any], edge: dict[str, Any]) -> str:
    stats = _closed_stats(lifecycle)
    lines = [
        "PAPER TRADE RESULT",
        f"Pair: {trade.get('symbol') or 'UNKNOWN'}",
        f"Direction: {trade.get('direction') or 'UNKNOWN'}",
        f"Model: {trade.get('model_id') or trade.get('dominant_model_id') or 'UNKNOWN'}",
        f"Setup: {trade.get('setup_family') or trade.get('dominant_setup_family') or 'UNKNOWN'}",
        f"Entry: {_format_number(trade.get('entry'))}",
        f"Exit: {_format_number(trade.get('exit_price'))}",
        f"Result: {trade.get('status') or trade.get('close_reason') or 'UNKNOWN'}",
        f"R Result: {_format_number(trade.get('r_result'))}",
        f"Closed count: {stats['closed_count']}",
        f"TP count: {stats['tp_count']}",
        f"SL count: {stats['sl_count']}",
        f"Expired count: {stats['expired_count']}",
        f"Winrate: {_format_number(stats['winrate'])}",
        f"Best model: {_best_model_name(feedback, promotion, edge)}",
        "Live Trade OFF",
    ]
    return "\n".join(lines)


def _summary_message(
    audit: dict[str, Any],
    sync: dict[str, Any],
    setup: dict[str, Any],
    lifecycle: dict[str, Any],
    edge: dict[str, Any],
    feedback: dict[str, Any],
    promotion: dict[str, Any],
    live_gate: dict[str, Any],
) -> str:
    summary = lifecycle.get("summary") or {}
    closed = _closed_stats(lifecycle)
    expectancy = (edge.get("summary") or {}).get("best_expectancy")
    if expectancy is None and edge.get("groups"):
        expectancy_values = [safe_float(group.get("expectancy")) for group in edge.get("groups") or []]
        expectancy_values = [value for value in expectancy_values if value is not None]
        if expectancy_values:
            expectancy = round(sum(expectancy_values) / len(expectancy_values), 4)
    sample_building = int((promotion.get("feedback_summary") or {}).get("sample_building") or 0)
    lines = [
        "RESEARCH SUMMARY 15M",
        f"System health: {audit.get('system_status') or 'UNKNOWN'}",
        f"Sync status: {sync.get('sync_status') or 'UNKNOWN'}",
        f"Active setup: {setup.get('dominant_setup_family') or 'NO_ACTIVE_SETUP_FAMILY'}",
        f"Opened / open / closed / invalid: {summary.get('opened', 0)} / {summary.get('open', 0)} / {summary.get('closed', 0)} / {summary.get('invalid', 0)}",
        f"TP count / SL count / expired: {closed['tp_count']} / {closed['sl_count']} / {closed['expired_count']}",
        f"Winrate: {_format_number(closed['winrate'])}",
        f"Expectancy: {_format_number(expectancy)}",
        f"Best model: {_best_model_name(feedback, promotion, edge)}",
        f"Worst model: {_worst_model_name(feedback, promotion)}",
        f"Sample building count: {sample_building}",
        f"Current bottleneck: {_summary_bottleneck(audit, sync, promotion, live_gate)}",
        "Live Trade OFF",
    ]
    return "\n".join(lines)


def _maybe_send_messages(token: str | None, chat_id: str | None, messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    if not token or not chat_id:
        for item in messages:
            item["telegram_status"] = "TELEGRAM_NOT_CONFIGURED"
            item["telegram_ok"] = False
        return "TELEGRAM_NOT_CONFIGURED", messages

    overall_status = "NO_MESSAGES"
    for item in messages:
        try:
            response = _send_telegram(token, chat_id, item["message_text"])
            ok = bool(response.get("ok"))
            item["telegram_response"] = response
            item["telegram_ok"] = ok
            item["telegram_status"] = "SENT" if ok else "TELEGRAM_SEND_FAILED"
            if ok:
                overall_status = "SENT"
            elif overall_status != "SENT":
                overall_status = "TELEGRAM_SEND_FAILED"
        except Exception as exc:
            item["telegram_ok"] = False
            item["telegram_status"] = "TELEGRAM_SEND_FAILED"
            item["error"] = str(exc)[:300]
            if overall_status != "SENT":
                overall_status = "TELEGRAM_SEND_FAILED"
    return overall_status, messages


def run_reporter(mode: str) -> dict[str, Any]:
    context = current_runtime_context()
    audit = load_json(SYSTEM_AUDIT_PATH) or {}
    sync = load_json(CONTEXT_SYNC_PATH) or {}
    observation = load_json(OBSERVATION_PATH) or {}
    setup = load_json(SETUP_ACTIVATION_PATH) or {}
    factory = load_json(PAPER_TRADE_FACTORY_PATH) or {}
    lifecycle = load_json(LIFECYCLE_PATH) or {}
    edge = load_json(EDGE_PATH) or {}
    feedback = load_json(FEEDBACK_PATH) or {}
    promotion = load_json(PROMOTION_PATH) or {}
    live_gate = load_json(LIVE_GATE_PATH) or {}
    reported = _load_reported_state()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or None
    input_symbol = str(
        observation.get("symbol")
        or factory.get("symbol")
        or lifecycle.get("symbol")
        or edge.get("symbol")
        or "BTCUSDT"
    )

    messages: list[dict[str, Any]] = []
    reason_codes = ["PAPER_ONLY", "NO_LIVE_EXECUTION", "NO_PRIVATE_API"]
    pending_open_ids: set[str] = set()
    pending_closed_ids: set[str] = set()

    if mode == "instant":
        open_ids = {str(item) for item in reported.get("reported_open_trade_ids") or [] if item}
        closed_ids = {str(item) for item in reported.get("reported_closed_trade_ids") or [] if item}
        open_candidates = list(lifecycle.get("new_trades_opened") or [])
        closed_candidates = list(lifecycle.get("trades_closed_this_loop") or [])

        if not open_candidates:
            open_candidates = list(lifecycle.get("open_trades") or [])
        if not closed_candidates:
            closed_candidates = list(lifecycle.get("closed_trades") or [])

        for trade in open_candidates:
            trade_id = str(trade.get("paper_trade_id") or "")
            if not trade_id or trade_id in open_ids:
                continue
            if str(trade.get("status") or "").upper() != "OPEN":
                continue
            messages.append(
                {
                    "message_type": "INSTANT_SIGNAL",
                    "paper_trade_id": trade_id,
                    "status": "PAPER OPENED",
                    "message_text": _instant_signal_message(trade),
                }
            )
            pending_open_ids.add(trade_id)

        for trade in closed_candidates:
            trade_id = str(trade.get("paper_trade_id") or "")
            status = str(trade.get("status") or trade.get("close_reason") or "").upper()
            if not trade_id or trade_id in closed_ids or status not in CLOSED_STATUSES:
                continue
            messages.append(
                {
                    "message_type": "TRADE_RESULT",
                    "paper_trade_id": trade_id,
                    "status": status,
                    "message_text": _result_message(trade, lifecycle, feedback, promotion, edge),
                }
            )
            pending_closed_ids.add(trade_id)
        reason_codes.append(f"PENDING_MESSAGES_{len(messages)}")
    else:
        messages.append(
            {
                "message_type": "SUMMARY",
                "paper_trade_id": None,
                "status": "SUMMARY_READY",
                "message_text": _summary_message(audit, sync, setup, lifecycle, edge, feedback, promotion, live_gate),
            }
        )
        reported["last_summary_sent_at_utc"] = _utc_now()
        reason_codes.append("SUMMARY_MODE")

    transport_status, sent_messages = _maybe_send_messages(token, chat_id, messages)
    if transport_status == "TELEGRAM_NOT_CONFIGURED":
        reason_codes.append("TELEGRAM_ENV_MISSING")
    elif transport_status == "SENT":
        reason_codes.append("TELEGRAM_SENT")
    elif transport_status == "TELEGRAM_SEND_FAILED":
        reason_codes.append("TELEGRAM_SEND_FAILED")
    else:
        reason_codes.append("NO_MESSAGE_EMITTED")

    if mode == "instant":
        open_ids = {str(item) for item in reported.get("reported_open_trade_ids") or [] if item}
        closed_ids = {str(item) for item in reported.get("reported_closed_trade_ids") or [] if item}
        for item in sent_messages:
            if item.get("telegram_status") != "SENT":
                continue
            trade_id = str(item.get("paper_trade_id") or "")
            if not trade_id:
                continue
            if item.get("message_type") == "INSTANT_SIGNAL" and trade_id in pending_open_ids:
                open_ids.add(trade_id)
            if item.get("message_type") == "TRADE_RESULT" and trade_id in pending_closed_ids:
                closed_ids.add(trade_id)
        reported["reported_open_trade_ids"] = sorted(open_ids)
        reported["reported_closed_trade_ids"] = sorted(closed_ids)

    sent_count = sum(1 for item in sent_messages if item.get("telegram_status") == "SENT")
    failed_count = sum(1 for item in sent_messages if item.get("telegram_status") == "TELEGRAM_SEND_FAILED")
    not_configured_count = sum(1 for item in sent_messages if item.get("telegram_status") == "TELEGRAM_NOT_CONFIGURED")

    output = stamp_payload(
        {
            "report_mode": mode.upper(),
            "status": transport_status,
            "symbol": input_symbol,
            "message_count": len(sent_messages),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "not_configured_count": not_configured_count,
            "messages": sent_messages,
            "reported_open_trade_ids_count": len(reported.get("reported_open_trade_ids") or []),
            "reported_closed_trade_ids_count": len(reported.get("reported_closed_trade_ids") or []),
            "telegram_configured": bool(token and chat_id),
            "env": {
                "has_telegram_bot_token": bool(token),
                "has_telegram_chat_id": bool(chat_id),
            },
            "source_state": {
                "latest_system_audit": SYSTEM_AUDIT_PATH.as_posix(),
                "latest_context_sync": CONTEXT_SYNC_PATH.as_posix(),
                "latest_observation_factory": OBSERVATION_PATH.as_posix(),
                "latest_setup_family_activation": SETUP_ACTIVATION_PATH.as_posix(),
                "latest_paper_trade_factory": PAPER_TRADE_FACTORY_PATH.as_posix(),
                "latest_research_paper_lifecycle": LIFECYCLE_PATH.as_posix(),
                "latest_research_edge_matrix": EDGE_PATH.as_posix(),
                "latest_model_feedback": FEEDBACK_PATH.as_posix(),
                "latest_model_promotion": PROMOTION_PATH.as_posix(),
                "latest_live_eligibility_gate": LIVE_GATE_PATH.as_posix(),
            },
            "reason_codes": reason_codes,
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        input_symbol,
        context,
    )

    _write_reported_state(reported)
    write_json(OUTPUT_PATH, output)
    append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram research reporter for NurNova paper engine.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--instant", action="store_true", help="Send instant paper trade open and result alerts.")
    mode.add_argument("--summary", action="store_true", help="Send 15-minute research summary.")
    args = parser.parse_args()

    selected_mode = "instant" if args.instant else "summary"
    print(json.dumps(run_reporter(selected_mode), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
