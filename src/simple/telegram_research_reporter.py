from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from src.core.model_survival_registry import get_active_models, get_quarantined_models, is_model_quarantined, load_model_survival_registry, split_active_quarantined, update_model_survival_report
from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "TELEGRAM_RESEARCH_REPORTER"
OUTPUT_PATH = epoch_state_path("latest_telegram_report.json")
HISTORY_PATH = epoch_data_path("telegram_report_history.jsonl")
FACTORY_PATH = epoch_state_path("latest_paper_trade_factory.json")
LIFECYCLE_PATH = epoch_state_path("latest_research_paper_lifecycle.json")
ACCOUNTING_PATH = epoch_state_path("latest_outcome_accounting.json")
EDGE_PATH = epoch_state_path("latest_research_edge_matrix.json")
MODEL_SURVIVAL_PATH = epoch_state_path("latest_model_survival_filter.json")
EVENT_PATH = epoch_state_path("latest_signal_event.json")
GRADE_PATH = epoch_state_path("latest_signal_grade.json")
CONTRACT_PATH = epoch_state_path("latest_signal_data_contract.json")
DASHBOARD_PATH = epoch_state_path("latest_edge_learning_dashboard.json")
MODEL_SURVIVAL_REPORT_PATH = epoch_state_path("latest_model_survival_report.json")
TRUE_OUTCOME_PATH = epoch_state_path("latest_true_outcome.json")
STATE_DIR = Path("state/simple")
ELITE_CONTEXT_PATH = epoch_state_path("latest_elite_context.json")
TP_DNA_PATH = epoch_state_path("latest_tp_condition_dna.json")
ZONE_CONTEXT_PATH = STATE_DIR / "latest_zone_context.json"
EPOCH_ZONE_CONTEXT_PATH = epoch_state_path("latest_zone_context.json")
REPORTED_TRADES_PATH = epoch_state_path("telegram_reported_trades.json")
SUMMARY_HASH_PATH = epoch_state_path("last_summary_hash.json")
LAST_SUMMARY_SENT_PATH = epoch_state_path("last_summary_sent_at.json")
SUMMARY_INTERVAL_SECONDS = 15 * 60
ELITE_LIFECYCLE_STATUSES = {"TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"}


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


def _format_utc(value: Any) -> str:
    parsed = _parse_utc(value)
    if parsed is None:
        return "n/a"
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_utc_plus4(value: Any) -> str:
    parsed = _parse_utc(value)
    if parsed is None:
        return "n/a"
    local = parsed.astimezone(timezone.utc) + timedelta(hours=4)
    return local.strftime("%Y-%m-%d %H:%M:%S UTC+4")


def _signal_birth_time(event: dict[str, Any], factory: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    timestamp = event.get("timestamp_utc")
    if not timestamp and factory:
        timestamp = factory.get("timestamp_utc")
    if not timestamp and context:
        timestamp = context.get("timestamp_utc")
    if not timestamp:
        timestamp = _utc_now()
        reasons.append("TIMESTAMP_FALLBACK_USED")
    return _format_utc(timestamp), reasons


def _top_zone_lines(zone: dict[str, Any], limit: int = 3) -> list[str]:
    zones = zone.get("zones") if isinstance(zone, dict) else []
    lines: list[str] = []
    for item in (zones or [])[:limit]:
        if not isinstance(item, dict):
            continue
        lines.append(f"- {item.get('zone_type') or 'UNKNOWN'} | {item.get('approximation_level') or 'UNKNOWN'} | {item.get('zone_meaning') or 'n/a'}")
    return lines or ["- n/a"]


def _condition_dna_lines(dna: dict[str, Any], fallback_conditions: list[Any] | None = None) -> list[str]:
    conditions = []
    for item in dna.get("tp_edge_conditions") or dna.get("top_tp_conditions") or []:
        if isinstance(item, dict):
            conditions.append(str(item.get("condition") or item.get("key") or "UNKNOWN"))
        else:
            conditions.append(str(item))
    if not conditions and fallback_conditions:
        conditions = [str(item) for item in fallback_conditions]
    return [f"- {item}" for item in conditions[:8]] or ["- sample building"]


def _title_for_result(result: Any) -> str:
    normalized = str(result or "").upper()
    if normalized == "TP1_HIT":
        return "NURNOVA TP1 HIT"
    if normalized == "TP2_HIT":
        return "NURNOVA TP2 HIT"
    if normalized == "SL_HIT":
        return "NURNOVA SL HIT"
    if normalized == "EXPIRED":
        return "NURNOVA EXPIRED"
    return f"NURNOVA {normalized or 'LIFECYCLE'}"


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


def render_elite_signal_message(
    event: dict[str, Any],
    elite_context: dict[str, Any],
    dna: dict[str, Any],
    zone: dict[str, Any],
    factory: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    birth_utc, reason_codes = _signal_birth_time(event, factory, context)
    context_type = elite_context.get("context_type") or event.get("context_type") or "ELITE_CONTINUATION_CONTEXT"
    lifecycle_id = event.get("lifecycle_id") or event.get("paper_trade_id") or event.get("event_id") or "pending"
    tracking_status = "TRACKING_STARTED" if event.get("paper_trade_id") or lifecycle_id != "pending" else "PAPER_TRACKING_PENDING"
    conditions = list(elite_context.get("conditions") or event.get("grade_reasons") or [])
    lines = [
        "NURNOVA ELITE SIGNAL",
        "",
        f"Signal Birth Time UTC: {birth_utc}",
        f"Signal Birth Time Local UTC+4: {_format_utc_plus4(birth_utc)}",
        f"Event ID: {event.get('event_id') or 'UNKNOWN'}",
        f"Paper Trade ID: {event.get('paper_trade_id') or 'pending'}",
        f"Lifecycle ID: {lifecycle_id}",
        f"Context ID: {event.get('context_id') or (context or {}).get('context_id') or 'UNKNOWN'}",
        f"Loop ID: {event.get('loop_id') or (context or {}).get('loop_id') or 'UNKNOWN'}",
        f"Grade: {event.get('signal_grade') or event.get('grade') or 'UNKNOWN'}",
        f"Context Type: {context_type}",
        "",
        f"Primary Setup: {event.get('primary_setup') or event.get('setup_family') or 'UNKNOWN'}",
        f"Primary Model: {event.get('primary_model') or event.get('model_id') or 'UNKNOWN'}",
        f"Supporting Models: {', '.join(event.get('supporting_models') or []) or 'none'}",
        "",
        "Timeframe:",
        f"primary_tf: {event.get('primary_tf') or 'n/a'}",
        f"trigger_tf: {event.get('trigger_tf') or 'n/a'}",
        f"context_tf: {event.get('context_tf') or 'n/a'}",
        f"structure_tf: {event.get('structure_tf') or 'n/a'}",
        f"expected_hold_label: {event.get('expected_hold_label') or 'n/a'}",
        "",
        "Trade Plan:",
        f"entry: {_format_number(event.get('entry'))}",
        f"stop_loss: {_format_number(event.get('stop_loss'))}",
        f"tp1: {_format_number(event.get('tp1'))}",
        f"tp2: {_format_number(event.get('tp2'))}",
        f"rr1: {_format_number(event.get('rr1'))}",
        f"rr2: {_format_number(event.get('rr2'))}",
        "",
        "Zone Context:",
        *_top_zone_lines(zone),
        "",
        "Condition DNA:",
        *_condition_dna_lines(dna, conditions),
        "",
        "Tracking:",
        f"status: {tracking_status}",
        "expected follow-ups: TP1_HIT / TP2_HIT / SL_HIT / EXPIRED",
        "",
        "Paper Only",
        "Live Trade OFF",
    ]
    if reason_codes:
        lines.extend(["", f"Reason Codes: {', '.join(reason_codes)}"])
    return "\n".join(lines), {"signal_birth_time_utc": birth_utc, "tracking_status": tracking_status, "reason_codes": reason_codes}


def render_lifecycle_followup_message(trade: dict[str, Any], dna: dict[str, Any], zone: dict[str, Any]) -> str:
    result = str(trade.get("outcome_status") or trade.get("close_reason") or trade.get("result") or trade.get("status") or "UNKNOWN").upper()
    birth = trade.get("signal_birth_time_utc") or trade.get("born_at_utc") or trade.get("opened_at_utc") or trade.get("timestamp_utc")
    closed = trade.get("closed_at_utc") or trade.get("close_time_utc") or trade.get("updated_at_utc") or trade.get("timestamp_utc")
    birth_utc = _format_utc(birth) if birth else "n/a"
    closed_utc = _format_utc(closed) if closed else "n/a"
    lines = [
        _title_for_result(result),
        "",
        f"Original Signal Birth Time UTC: {birth_utc}",
        f"Original Signal Birth Time UTC+4: {_format_utc_plus4(birth_utc)}",
        f"Closed Time UTC: {closed_utc}",
        f"Closed Time UTC+4: {_format_utc_plus4(closed_utc)}",
        f"Event ID: {trade.get('event_id') or 'UNKNOWN'}",
        f"Paper Trade ID: {trade.get('paper_trade_id') or 'UNKNOWN'}",
        f"Lifecycle ID: {trade.get('lifecycle_id') or trade.get('paper_trade_id') or 'UNKNOWN'}",
        f"Model ID: {trade.get('model_id') or trade.get('primary_model') or 'UNKNOWN'}",
        f"Setup Family: {trade.get('setup_family') or trade.get('primary_setup') or 'UNKNOWN'}",
        f"Direction: {trade.get('direction') or 'UNKNOWN'}",
        f"Entry: {_format_number(trade.get('entry') or trade.get('entry_price'))}",
        f"Stop Loss: {_format_number(trade.get('stop_loss'))}",
        f"TP1: {_format_number(trade.get('tp1'))}",
        f"TP2: {_format_number(trade.get('tp2'))}",
        f"Exit Price: {_format_number(trade.get('exit_price') or trade.get('close_price'))}",
        f"Result: {result}",
        f"R Result: {_format_number(trade.get('realized_r') if trade.get('realized_r') is not None else trade.get('r_result'))}",
        f"MFE: {_format_number(trade.get('mfe'))}",
        f"MAE: {_format_number(trade.get('mae'))}",
        f"Hold Time: {trade.get('hold_seconds') or trade.get('holding_seconds') or 'n/a'}s",
        "",
        "Zone Context at Birth:",
        *_top_zone_lines({"zones": trade.get("zone_context") or zone.get("zones") or []}),
        "",
        "Condition DNA at Birth:",
        *_condition_dna_lines(dna, trade.get("condition_dna") or trade.get("grade_reasons") or trade.get("reason_codes") or []),
        "",
        "Why result happened:",
        f"{trade.get('outcome_reason') or trade.get('close_reason') or ', '.join(trade.get('reason_codes') or []) or 'n/a'}",
        "",
        "Paper Only",
        "Live Trade OFF",
    ]
    return "\n".join(lines)


def telegram_elite_filter(payload: dict[str, Any]) -> tuple[bool, str]:
    model_id = payload.get("model_id") or payload.get("primary_model") or payload.get("dominant_model_id")
    if model_id and is_model_quarantined(model_id):
        return False, "MODEL_SURVIVAL_REGISTRY_BLOCK"
    context_type = str(payload.get("context_type") or "").upper()
    status = str(payload.get("outcome_status") or payload.get("status") or payload.get("close_reason") or payload.get("result") or "").upper()
    if context_type == "ELITE_CONTINUATION_CONTEXT":
        return True, "ELITE_CONTINUATION_CONTEXT"
    if status in ELITE_LIFECYCLE_STATUSES:
        return True, status
    if str(payload.get("message_type") or "").upper() in {"HOURLY_SUMMARY", "NURNOVA_HOURLY_REPORT", "CRITICAL_SYSTEM_WARNING"}:
        return True, str(payload.get("message_type")).upper()
    return False, "TELEGRAM_ELITE_FILTER_BLOCK"


def _elite_context_message(context_payload: dict[str, Any], event: dict[str, Any], dna: dict[str, Any], zone: dict[str, Any]) -> str:
    text, _meta = render_elite_signal_message(event, context_payload, dna, zone)
    return text


def _lifecycle_message(trade: dict[str, Any], dna: dict[str, Any], zone: dict[str, Any]) -> str:
    return render_lifecycle_followup_message(trade, dna, zone)


def _summary_message(factory: dict[str, Any], lifecycle: dict[str, Any], accounting: dict[str, Any], edge: dict[str, Any], event_payload: dict[str, Any], survival: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    dashboard = load_json(DASHBOARD_PATH) or {}
    tp_dna = load_json(TP_DNA_PATH) or {}
    edge_query = load_json(epoch_state_path("latest_edge_query_report.json")) or {}
    survival_report = load_json(MODEL_SURVIVAL_REPORT_PATH) or {}
    zone_context = load_json(EPOCH_ZONE_CONTEXT_PATH) or load_json(ZONE_CONTEXT_PATH) or {}
    fallback_used = False
    active_models = list(dashboard.get("active_models") or survival_report.get("active_models") or get_active_models())
    quarantined_models = set(str(item) for item in (dashboard.get("quarantined_models") or survival_report.get("quarantined_models") or get_quarantined_models()))
    lifecycle_summary = lifecycle.get("summary") or {}
    accounting_summary = accounting.get("summary") or {}

    def _clean_model(value: Any) -> str:
        if isinstance(value, dict):
            candidate = str(value.get("key") or value.get("model_id") or value.get("best_model_id") or "")
        else:
            candidate = str(value or "")
        if not candidate or candidate in quarantined_models or (active_models and candidate not in set(active_models)):
            return "SAMPLE_BUILDING"
        return candidate

    best_model = _clean_model(dashboard.get("best_model"))
    worst_model = _clean_model(dashboard.get("worst_model"))
    if dashboard.get("best_active_models"):
        best_model = _clean_model((dashboard.get("best_active_models") or [{}])[0])
    if dashboard.get("worst_active_models"):
        worst_model = _clean_model((dashboard.get("worst_active_models") or [{}])[0])
    if not dashboard:
        fallback_used = True
        best_model = _clean_model((edge.get("summary") or {}).get("best_model_id"))
        worst_model = _clean_model((edge.get("worst_model") or {}).get("model_id"))
    if best_model == worst_model and best_model != "SAMPLE_BUILDING":
        worst_model = "SAMPLE_BUILDING"
    report_utc = _utc_now()
    payload = {
        "epoch_id": ACTIVE_EPOCH_ID,
        "report_time_utc": report_utc,
        "report_time_utc_plus4": _format_utc_plus4(report_utc),
        "active_models": active_models,
        "quarantined_models": sorted(quarantined_models),
        "elite_context_count": int(dashboard.get("elite_context_count") or 0),
        "open_trades": int(lifecycle_summary.get("open") or len(lifecycle.get("open_trades") or [])),
        "closed_trades": int(accounting_summary.get("closed_count") or 0),
        "tp1": int(dashboard.get("tp1_count") or accounting_summary.get("tp1_hits") or 0),
        "tp2": int(dashboard.get("tp2_count") or accounting_summary.get("tp2_hits") or 0),
        "sl": int(dashboard.get("sl_count") or accounting_summary.get("sl_hits") or accounting_summary.get("losses") or 0),
        "expired": int(dashboard.get("expired_count") or accounting_summary.get("expired") or 0),
        "winrate": dashboard.get("winrate", accounting_summary.get("winrate")),
        "average_r": dashboard.get("expectancy", accounting_summary.get("avg_r")),
        "best_active_model": best_model,
        "worst_active_model": worst_model,
        "best_zone": dashboard.get("best_zone") or (dashboard.get("best_zones") or [{}])[0] or {},
        "worst_zone": dashboard.get("worst_zone") or (dashboard.get("worst_zones") or [{}])[0] or {},
        "best_condition_dna": dashboard.get("best_condition_dna") or (tp_dna.get("tp_edge_conditions") or [{}])[0],
        "worst_condition_dna": dashboard.get("worst_condition_dna") or (tp_dna.get("sl_risk_conditions") or [{}])[0],
        "best_timeframe_combo": dashboard.get("best_timeframe_combo") or {},
        "current_gate": "HARD_QUARANTINE_ACTIVE" if quarantined_models else "SAMPLE_BUILDING",
        "fallback_used": fallback_used,
        "zone_summary": zone_context.get("summary") or {},
        "edge_query_summary": edge_query.get("summary") or {},
    }
    lines = [
        "NURNOVA EDGE LEARNING REPORT",
        "",
        f"Report Time UTC: {payload['report_time_utc']}",
        f"Report Time UTC+4: {payload['report_time_utc_plus4']}",
        f"Active Models: {', '.join(active_models) or 'none'}",
        f"Quarantined Models: {', '.join(sorted(quarantined_models)) or 'none'}",
        f"Elite Context Count: {payload['elite_context_count']}",
        f"Open Trades: {payload['open_trades']}",
        f"Closed Trades: {payload['closed_trades']}",
        f"TP1: {payload['tp1']}",
        f"TP2: {payload['tp2']}",
        f"SL: {payload['sl']}",
        f"Expired: {payload['expired']}",
        f"Winrate: {_format_percent(payload['winrate'])}",
        f"Average R: {_format_number(payload['average_r'])}",
        f"Best Active Model: {payload['best_active_model']}",
        f"Worst Active Model: {payload['worst_active_model']}",
        f"Best Zone: {json.dumps(payload['best_zone'], ensure_ascii=False)}",
        f"Worst Zone: {json.dumps(payload['worst_zone'], ensure_ascii=False)}",
        f"Best Condition DNA: {json.dumps(payload['best_condition_dna'], ensure_ascii=False)}",
        f"Worst Condition DNA: {json.dumps(payload['worst_condition_dna'], ensure_ascii=False)}",
        f"Best Timeframe Combo: {json.dumps(payload['best_timeframe_combo'], ensure_ascii=False)}",
        f"Current Gate: {payload['current_gate']}",
        "Live Trade OFF / Paper Only",
    ]
    if fallback_used:
        lines.append("Reason Code: EDGE_REPORT_FALLBACK_USED")
    return "\n".join(lines), payload


def run_reporter(mode: str) -> dict[str, Any]:
    context = current_runtime_context()
    factory = load_json(FACTORY_PATH) or {}
    lifecycle = load_json(LIFECYCLE_PATH) or {}
    accounting = load_json(ACCOUNTING_PATH) or {}
    edge = load_json(EDGE_PATH) or {}
    survival = load_json(MODEL_SURVIVAL_PATH) or {}
    event_payload = load_json(EVENT_PATH) or {}
    grade = load_json(GRADE_PATH) or {}
    contract = load_json(CONTRACT_PATH) or {}
    elite_context = load_json(ELITE_CONTEXT_PATH) or {}
    tp_dna = load_json(TP_DNA_PATH) or {}
    zone_context = load_json(EPOCH_ZONE_CONTEXT_PATH) or load_json(ZONE_CONTEXT_PATH) or {}
    true_outcome = load_json(TRUE_OUTCOME_PATH) or {}
    registry = load_model_survival_registry()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    reported = _load_reported_state()
    messages: list[dict[str, Any]] = []
    dedup_suppressed = 0
    rate_limit_status = "NOT_APPLICABLE"

    if mode == "instant":
        raw_events = list(event_payload.get("events") or ([event_payload.get("latest_event")] if event_payload.get("latest_event") else []))
        filtered_events, blocked_events = split_active_quarantined(raw_events, BLOCK_ID)
        survival_report = update_model_survival_report(location=BLOCK_ID, allowed_count=len(filtered_events), blocked_items=blocked_events, registry=registry)
        if elite_context and telegram_elite_filter(elite_context)[0]:
            event = event_payload.get("latest_event") or {}
            event_id = str(event.get("event_id") or elite_context.get("context_id") or "")
            if event_id and event_id not in reported["reported_event_ids"]:
                text, meta = render_elite_signal_message(event, elite_context, tp_dna, zone_context, factory, context)
                messages.append({"message_type": "ELITE_CONTINUATION_CONTEXT", "event_id": event_id, "status": "ELITE_CONTEXT_READY", "message_text": text, "message_hash": _hash_payload({"elite_context": elite_context, "event": event_id})})
                reported["reported_event_ids"].add(event_id)
        true_closed = [item for item in true_outcome.get("outcomes") or [] if isinstance(item, dict) and str(item.get("outcome_status") or "").upper() in ELITE_LIFECYCLE_STATUSES]
        weak_closed = list(lifecycle.get("trades_closed_this_loop") or accounting.get("closed_trades_this_loop") or [])
        for trade in true_closed or weak_closed:
            allowed_lifecycle, reason = telegram_elite_filter(trade)
            trade_id = str(trade.get("paper_trade_id") or "")
            dedup_key = f"{trade_id}:{reason}"
            if not allowed_lifecycle or not trade_id or dedup_key in reported["reported_closed_trade_ids"] or trade_id in reported["reported_closed_trade_ids"]:
                continue
            text = render_lifecycle_followup_message(trade, tp_dna, zone_context)
            messages.append({"message_type": reason, "paper_trade_id": trade_id, "event_id": trade.get("event_id"), "status": reason, "message_text": text, "message_hash": _hash_payload({"trade": trade_id, "status": reason})})
            reported["reported_closed_trade_ids"].add(dedup_key)
        for event in filtered_events:
            event_id = str(event.get("event_id") or "")
            allowed_event, reason = telegram_elite_filter(event)
            if not event_id or event_id in reported["reported_event_ids"] or not allowed_event:
                if event_id in reported["reported_event_ids"]:
                    dedup_suppressed += 1
                continue
            text, meta = render_elite_signal_message(event, {"context_type": "ELITE_CONTINUATION_CONTEXT", "direction": event.get("direction"), "conditions": event.get("grade_reasons") or []}, tp_dna, zone_context, factory, context)
            digest = _hash_payload({"event": event_id, "text": text})
            messages.append({"message_type": reason, "event_id": event_id, "status": reason, "message_text": text, "message_hash": digest})
            reported["reported_event_ids"].add(event_id)
    else:
        survival_report = update_model_survival_report(location=BLOCK_ID, allowed_count=0, blocked_items=[], registry=registry)
        allowed, rate_limit_status, elapsed = _summary_rate_limit_status()
        if not allowed:
            messages = []
            dedup_suppressed = 1
        else:
            text, summary_payload = _summary_message(factory, lifecycle, accounting, edge, event_payload, survival)
            digest = _hash_payload(summary_payload)
            if digest != _load_summary_hash():
                _write_summary_hash(digest, text)
                messages.append({"message_type": "NURNOVA_EDGE_LEARNING_REPORT", "paper_trade_id": None, "event_id": None, "status": "SUMMARY_READY", "message_text": text, "message_hash": digest})
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
                "model_survival_filter": str(MODEL_SURVIVAL_PATH),
                "model_survival_registry": "state/simple/epoch_v2/model_survival_registry.json",
                "edge_learning_dashboard": str(DASHBOARD_PATH),
                "model_survival_report": str(MODEL_SURVIVAL_REPORT_PATH),
                "elite_context": str(ELITE_CONTEXT_PATH),
                "tp_condition_dna": str(TP_DNA_PATH),
                "true_outcome": str(TRUE_OUTCOME_PATH),
                "zone_context": str(ZONE_CONTEXT_PATH),
            },
            "status": rate_limit_status if mode == "summary" and rate_limit_status == "SUPPRESSED_15M_RATE_LIMIT" else status if messages else ("SUPPRESSED_DUPLICATE" if dedup_suppressed else "NO_MESSAGES"),
            "summary": (_summary_message(factory, lifecycle, accounting, edge, event_payload, survival)[1] if mode == "summary" else None),
            "message_count": len(messages),
            "dedup_suppressed_count": dedup_suppressed,
            "rate_limit_status": rate_limit_status,
            "telegram_configured": bool(token and chat_id),
            "model_survival_registry": {"registry_status": survival_report.get("registry_status")},
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
                        "epoch_v2/latest_model_survival_filter.json": survival,
                        "epoch_v2/latest_edge_learning_dashboard.json": load_json(DASHBOARD_PATH) or {},
                        "epoch_v2/latest_tp_condition_dna.json": tp_dna,
                        "epoch_v2/latest_true_outcome.json": true_outcome,
                        "epoch_v2/latest_zone_context.json": load_json(EPOCH_ZONE_CONTEXT_PATH) or zone_context,
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
