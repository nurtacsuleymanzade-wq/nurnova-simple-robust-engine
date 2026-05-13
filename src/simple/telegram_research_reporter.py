from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "TELEGRAM_RESEARCH_REPORTER"
OUTPUT_PATH = epoch_state_path("latest_telegram_report.json")
HISTORY_PATH = epoch_data_path("telegram_report_history.jsonl")
FACTORY_PATH = epoch_state_path("latest_paper_trade_factory.json")
LIFECYCLE_PATH = epoch_state_path("latest_research_paper_lifecycle.json")
ACCOUNTING_PATH = epoch_state_path("latest_outcome_accounting.json")
EDGE_PATH = epoch_state_path("latest_research_edge_matrix.json")
EVENT_PATH = epoch_state_path("latest_signal_event.json")
GRADE_PATH = epoch_state_path("latest_signal_grade.json")
CONTRACT_PATH = epoch_state_path("latest_signal_data_contract.json")
STATE_DIR = Path("state/simple")
REPORTED_TRADES_PATH = epoch_state_path("telegram_reported_trades.json")
SUMMARY_HASH_PATH = epoch_state_path("last_summary_hash.json")
LAST_SUMMARY_SENT_PATH = epoch_state_path("last_summary_sent_at.json")
SUMMARY_INTERVAL_SECONDS = 15 * 60


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_payload(payload: Any) -> str:
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _format_number(value: Any, digits: int = 4) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _format_percent(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    if number <= 1:
        number *= 100
    return f"{number:.1f}".rstrip("0").rstrip(".") + "%"


def _load_reported_state() -> dict[str, Any]:
    payload = load_json(REPORTED_TRADES_PATH) or {}
    return {
        "reported_open_trade_ids": set(str(item) for item in payload.get("reported_open_trade_ids") or [] if item),
        "reported_closed_trade_ids": set(str(item) for item in payload.get("reported_closed_trade_ids") or [] if item),
        "reported_open_hashes": set(str(item) for item in payload.get("reported_open_hashes") or [] if item),
        "reported_closed_hashes": set(str(item) for item in payload.get("reported_closed_hashes") or [] if item),
        "reported_event_ids": set(str(item) for item in payload.get("reported_event_ids") or [] if item),
    }


def _write_reported_state(state: dict[str, Any]) -> None:
    write_json(
        REPORTED_TRADES_PATH,
        {
            "reported_open_trade_ids": sorted(state["reported_open_trade_ids"]),
            "reported_closed_trade_ids": sorted(state["reported_closed_trade_ids"]),
            "reported_open_hashes": sorted(state["reported_open_hashes"]),
            "reported_closed_hashes": sorted(state["reported_closed_hashes"]),
            "reported_event_ids": sorted(state["reported_event_ids"]),
            "updated_at_utc": _utc_now(),
        },
    )


def _load_summary_hash() -> str:
    return str((load_json(SUMMARY_HASH_PATH) or {}).get("last_summary_hash") or "")


def _write_summary_hash(summary_hash: str, preview: str) -> None:
    write_json(SUMMARY_HASH_PATH, {"last_summary_hash": summary_hash, "last_summary_preview": preview[:500], "updated_at_utc": _utc_now()})


def _parse_utc(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _summary_rate_limit_status() -> tuple[bool, str, float | None]:
    payload = load_json(LAST_SUMMARY_SENT_PATH) or {}
    last = _parse_utc(payload.get("last_summary_sent_at_utc"))
    if last is None:
        return True, "READY", None
    elapsed = max(0.0, (datetime.now(timezone.utc) - last).total_seconds())
    if elapsed < SUMMARY_INTERVAL_SECONDS:
        return False, "SUPPRESSED_15M_RATE_LIMIT", elapsed
    return True, "READY", elapsed


def _write_summary_sent_status(status: str) -> None:
    payload = load_json(LAST_SUMMARY_SENT_PATH) or {}
    if status != "SUPPRESSED_15M_RATE_LIMIT":
        payload["last_summary_sent_at_utc"] = _utc_now()
    payload["status"] = status
    payload["updated_at_utc"] = _utc_now()
    write_json(LAST_SUMMARY_SENT_PATH, payload)


def _send_telegram(token: str, chat_id: str, text: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = request.Request(url, data=payload, method="POST")
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _first_trade(*collections: list[dict[str, Any]]) -> dict[str, Any]:
    for collection in collections:
        if collection:
            return dict(collection[0])
    return {}


def _active_setup(factory: dict[str, Any], lifecycle: dict[str, Any], edge: dict[str, Any]) -> dict[str, Any]:
    trade = _first_trade(
        list(lifecycle.get("open_trades") or []),
        list(factory.get("newest_opened_this_loop") or []),
        list(factory.get("top_candidate_diagnostics") or []),
        list(edge.get("groups") or []),
    )
    return {
        "setup_family": trade.get("setup_family") or "NO_ACTIVE_SETUP",
        "primary_tf": trade.get("primary_tf") or "n/a",
        "context_tf": trade.get("context_tf") or "n/a",
        "model_id": trade.get("model_id") or "UNKNOWN",
    }


def _instant_signal_message(event: dict[str, Any], edge: dict[str, Any]) -> str:
    edge_summary = edge.get("summary") or {}
    return "\n".join(
        [
            "NURNOVA A+ SIGNAL",
            "",
            f"Pair: {event.get('symbol') or 'BTCUSDT'}",
            f"Direction: {event.get('direction') or 'UNKNOWN'}",
            f"Grade: {event.get('signal_grade') or 'UNKNOWN'}",
            f"Event ID: {event.get('event_id') or 'UNKNOWN'}",
            "",
            f"Primary Setup: {event.get('primary_setup') or 'UNKNOWN'}",
            f"Primary Model: {event.get('primary_model') or 'UNKNOWN'}",
            f"Supporting Models: {', '.join(event.get('supporting_models') or []) or 'none'}",
            "",
            "Timeframe:",
            f"Primary TF: {event.get('primary_tf') or 'n/a'}",
            f"Context TF: {event.get('context_tf') or 'n/a'}",
            f"Expected Hold: {event.get('expected_hold_label') or 'n/a'}",
            "",
            "Trade Plan:",
            f"Entry: {_format_number(event.get('entry'))}",
            f"Stop: {_format_number(event.get('stop_loss'))}",
            f"TP1: {_format_number(event.get('tp1'))}",
            f"TP2: {_format_number(event.get('tp2'))}",
            f"RR1: {_format_number(event.get('rr1'))}",
            f"RR2: {_format_number(event.get('rr2'))}",
            "",
            "Why:",
            f"- Activation: {_format_number(event.get('activation_score'), 2)}",
            f"- Timeframe: {event.get('primary_tf') or 'n/a'} / {event.get('context_tf') or 'n/a'}",
            f"- RR: {_format_number(event.get('rr1'))} / {_format_number(event.get('rr2'))}",
            f"- Model Confluence: {event.get('event_confluence_count') or 1}",
            "",
            "Edge:",
            f"Current Status: {edge.get('edge_status') or 'NO_CLEAN_SAMPLES'}",
            f"Model Sample Count: {edge_summary.get('best_sample_size') or 0}",
            f"Best Model: {edge_summary.get('best_model_id') or 'SAMPLE_BUILDING'}",
            "",
            "Safety:",
            "Paper Trade Only",
            "Live Trade OFF",
        ]
    )


def _summary_message(factory: dict[str, Any], lifecycle: dict[str, Any], accounting: dict[str, Any], edge: dict[str, Any], event_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    active = _active_setup(factory, lifecycle, edge)
    latest_event = event_payload.get("latest_event") or {}
    lifecycle_summary = lifecycle.get("summary") or {}
    accounting_summary = accounting.get("summary") or {}
    edge_summary = edge.get("summary") or {}
    best_winrate_model = edge.get("best_winrate_model") or {}
    best_avg_r_model = edge.get("best_avg_r_model") or {}
    payload = {
        "epoch_id": ACTIVE_EPOCH_ID,
        "pair": factory.get("symbol") or lifecycle.get("symbol") or latest_event.get("symbol") or "BTCUSDT",
        "active_setup": active["setup_family"],
        "primary_tf": active["primary_tf"],
        "context_tf": active["context_tf"],
        "open_trades": int(lifecycle_summary.get("open") or len(lifecycle.get("open_trades") or [])),
        "closed_trades": int(accounting_summary.get("closed_count") or 0),
        "tp_hits": int(accounting_summary.get("tp_hits") or accounting_summary.get("wins") or 0),
        "sl_hits": int(accounting_summary.get("sl_hits") or accounting_summary.get("losses") or 0),
        "expired": int(accounting_summary.get("expired") or 0),
        "winrate": accounting_summary.get("winrate"),
        "average_r": accounting_summary.get("avg_r"),
        "edge_status": edge.get("edge_status") or "NO_CLEAN_SAMPLES",
        "best_model": edge_summary.get("best_model_id") or (best_avg_r_model.get("model_id") or active["model_id"]),
        "best_model_winrate": best_winrate_model.get("winrate") if best_winrate_model else edge_summary.get("best_winrate"),
        "best_model_avg_r": best_avg_r_model.get("avg_r") if best_avg_r_model else edge_summary.get("best_expectancy"),
        "sample_count": int(edge_summary.get("best_sample_size") or accounting_summary.get("clean_sample_count") or 0),
        "live_trade": "OFF",
    }
    lines = [
        "NURNOVA 15M REPORT",
        "",
        f"Epoch: {ACTIVE_EPOCH_ID}",
        f"Pair: {payload['pair']}",
        "",
        "Research Status:",
        f"Open Trades: {payload['open_trades']}",
        f"Closed Trades: {payload['closed_trades']}",
        f"TP Hits: {payload['tp_hits']}",
        f"SL Hits: {payload['sl_hits']}",
        f"Expired: {payload['expired']}",
        f"Winrate: {_format_percent(payload['winrate'])}",
        f"Average R: {_format_number(payload['average_r'])}",
        f"Edge Status: {payload['edge_status']}",
        "",
        f"Best Model: {payload['best_model']}",
        f"Best Model Winrate: {_format_percent(payload['best_model_winrate'])}",
        f"Best Model Avg R: {_format_number(payload['best_model_avg_r'])}",
        f"Best Model Sample Count: {payload['sample_count']}",
        "",
        f"Current Active Setup: {latest_event.get('primary_setup') or payload['active_setup']}",
        f"Primary TF: {payload['primary_tf']}",
        f"Context TF: {payload['context_tf']}",
        "",
        "System:",
        "Pipeline: EPOCH_V2",
        "Sync: EPOCH_V2_SSOT",
        "Live Trade OFF",
        "",
        "Source:",
        "All metrics from EPOCH_V2_SSOT.",
    ]
    return "\n".join(lines), payload


def run_reporter(mode: str) -> dict[str, Any]:
    context = current_runtime_context()
    factory = load_json(FACTORY_PATH) or {}
    lifecycle = load_json(LIFECYCLE_PATH) or {}
    accounting = load_json(ACCOUNTING_PATH) or {}
    edge = load_json(EDGE_PATH) or {}
    event_payload = load_json(EVENT_PATH) or {}
    grade = load_json(GRADE_PATH) or {}
    contract = load_json(CONTRACT_PATH) or {}

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    reported = _load_reported_state()
    messages: list[dict[str, Any]] = []
    dedup_suppressed = 0
    rate_limit_status = "NOT_APPLICABLE"

    if mode == "instant":
        for event in event_payload.get("events") or ([event_payload.get("latest_event")] if event_payload.get("latest_event") else []):
            event_id = str(event.get("event_id") or "")
            if (
                not event_id
                or event_id in reported["reported_event_ids"]
                or event.get("signal_grade") != "A_PLUS"
                or event.get("a_plus_ready") is not True
            ):
                if event_id in reported["reported_event_ids"]:
                    dedup_suppressed += 1
                continue
            text = _instant_signal_message(event, edge)
            digest = _hash_payload({"event": event_id, "text": text})
            messages.append({"message_type": "NURNOVA_A_PLUS_SIGNAL", "event_id": event_id, "status": "A_PLUS_READY", "message_text": text, "message_hash": digest})
            reported["reported_event_ids"].add(event_id)
    else:
        allowed, rate_limit_status, elapsed = _summary_rate_limit_status()
        if not allowed:
            messages = []
            dedup_suppressed = 1
        else:
            text, summary_payload = _summary_message(factory, lifecycle, accounting, edge, event_payload)
            digest = _hash_payload(summary_payload)
            if digest != _load_summary_hash():
                _write_summary_hash(digest, text)
                messages.append({"message_type": "NURNOVA_15M_REPORT", "paper_trade_id": None, "event_id": None, "status": "SUMMARY_READY", "message_text": text, "message_hash": digest})
            else:
                dedup_suppressed = 1
            if messages:
                _write_summary_sent_status("SUMMARY_READY")
        if not messages and rate_limit_status == "SUPPRESSED_15M_RATE_LIMIT":
            _write_summary_sent_status(rate_limit_status)

    status = "NO_MESSAGES"
    if not token or not chat_id:
        status = "TELEGRAM_NOT_CONFIGURED" if messages else "NO_MESSAGES"
        for item in messages:
            item["telegram_status"] = "TELEGRAM_NOT_CONFIGURED"
    else:
        for item in messages:
            try:
                response = _send_telegram(token, chat_id, item["message_text"])
                item["telegram_response"] = response
                item["telegram_status"] = "SENT" if response.get("ok") else "TELEGRAM_SEND_FAILED"
                status = "SENT" if response.get("ok") else "TELEGRAM_SEND_FAILED"
            except Exception as exc:
                item["telegram_status"] = "TELEGRAM_SEND_FAILED"
                item["error"] = str(exc)[:300]
                status = "TELEGRAM_SEND_FAILED"
    _write_reported_state(reported)

    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "block_id": BLOCK_ID,
            "report_mode": mode.upper(),
            "source": {"source_mode": "EPOCH_V2_SSOT"},
            "source_state_refs": {
                "signal_data_contract": str(CONTRACT_PATH),
                "signal_event": str(EVENT_PATH),
                "signal_grade": str(GRADE_PATH),
                "paper_trade_factory": str(FACTORY_PATH),
                "research_paper_lifecycle": str(LIFECYCLE_PATH),
                "outcome_accounting": str(ACCOUNTING_PATH),
                "research_edge_matrix": str(EDGE_PATH),
            },
            "status": rate_limit_status if mode == "summary" and rate_limit_status == "SUPPRESSED_15M_RATE_LIMIT" else status if messages else ("SUPPRESSED_DUPLICATE" if dedup_suppressed else "NO_MESSAGES"),
            "summary": (_summary_message(factory, lifecycle, accounting, edge, event_payload)[1] if mode == "summary" else None),
            "message_count": len(messages),
            "dedup_suppressed_count": dedup_suppressed,
            "rate_limit_status": rate_limit_status,
            "telegram_configured": bool(token and chat_id),
            "messages": [
                {
                    "message_type": item.get("message_type"),
                    "paper_trade_id": item.get("paper_trade_id"),
                    "event_id": item.get("event_id"),
                    "status": item.get("status"),
                    "telegram_status": item.get("telegram_status"),
                }
                for item in messages
            ],
            "data_quality": {
                "level": "HIGH" if lifecycle and accounting and edge else "MEDIUM",
                "missing_inputs": [
                    name for name, payload in {
                        "epoch_v2/latest_paper_trade_factory.json": factory,
                        "epoch_v2/latest_research_paper_lifecycle.json": lifecycle,
                        "epoch_v2/latest_outcome_accounting.json": accounting,
                        "epoch_v2/latest_research_edge_matrix.json": edge,
                        "epoch_v2/latest_signal_event.json": event_payload,
                        "epoch_v2/latest_signal_grade.json": grade,
                        "epoch_v2/latest_signal_data_contract.json": contract,
                    }.items() if not payload
                ],
            },
            "reason_codes": [
                f"MODE_{mode.upper()}",
                f"STATUS_{status if messages else 'NO_MESSAGES'}",
                f"MESSAGES_{len(messages)}",
                "PAPER_ONLY",
                "NO_LIVE_EXECUTION",
                "NO_PRIVATE_API",
            ],
            "feeds_next": {"next_blocks": []},
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        str((factory.get("symbol") or lifecycle.get("symbol") or "BTCUSDT")),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("telegram_report_history.jsonl", output)
    return output


def run_summary_report() -> dict[str, Any]:
    return run_reporter("summary")


def run_instant_report() -> dict[str, Any]:
    return run_reporter("instant")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Epoch V2 Telegram research reporter")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--instant", action="store_true")
    mode.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    selected = "instant" if args.instant else "summary"
    print(json.dumps(run_reporter(selected), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
