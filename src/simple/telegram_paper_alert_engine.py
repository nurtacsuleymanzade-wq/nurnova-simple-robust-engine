"""S19 — Telegram Paper Alert Engine. Paper-only alert formatter/sender."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

DECISION_GATE_PATH = STATE_DIR / "latest_decision_gate.json"
TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"
SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"
SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"

ALERT_PATH = STATE_DIR / "latest_telegram_paper_alert.json"
S19_STATE_PATH = STATE_DIR / "s19_telegram_paper_alert_state.json"
ALERT_LOG_PATH = DATA_DIR / "telegram_paper_alert_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s19_telegram_paper_alert_latest_report.md"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _format_message(
    symbol: str,
    side: str,
    entry: Any,
    sl: Any,
    tp1: Any,
    tp2: Any,
    rr1: Any,
    rr2: Any,
    grade: str,
    decision: str,
    reason_summary: str,
) -> str:
    lines = [
        "PAPER ONLY / REAL TRADE DISABLED",
        f"Symbol: {symbol}",
        f"Side: {side}",
        f"Entry: {entry}",
        f"SL: {sl}",
        f"TP1: {tp1}",
        f"TP2: {tp2}",
        f"RR_TP1: {rr1}",
        f"RR_TP2: {rr2}",
        f"Grade: {grade}",
        f"Decision: {decision}",
        f"Reason: {reason_summary}",
        "safe_to_open_real_trade=false",
        "private_api_used=false",
        "live_order_sent=false",
    ]
    return "\n".join(lines)


def compute_telegram_paper_alert(
    decision_gate: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    scenario_trigger: dict[str, Any] | None,
    setup_context: dict[str, Any] | None,
    mode: str = "DRY_RUN",
) -> dict[str, Any]:
    ts = _now_utc()
    telegram_mode = mode if mode in ("DRY_RUN", "SEND") else "DRY_RUN"
    dry_run = telegram_mode == "DRY_RUN"
    reason_codes: list[str] = []

    if decision_gate is None:
        symbol = "UNKNOWN"
        decision = "BLOCK"
        side = "UNKNOWN"
        entry = sl = tp1 = tp2 = None
        rr1 = rr2 = 0.0
        final_grade = "BLOCKED"
        plan_reasons: list[str] = []
        dq_level = "MISSING"
        dq_score = 0.0
        input_status = "MISSING"
        source = "NONE"
        alert_status = "INVALID"
        reason_codes.append("DECISION_GATE_MISSING")
    else:
        symbol = decision_gate.get("symbol", "UNKNOWN")
        decision = decision_gate.get("decision", "BLOCK")
        side = decision_gate.get("selected_side", "UNKNOWN")
        entry = decision_gate.get("selected_entry")
        sl = decision_gate.get("selected_stop_loss")
        tp1 = decision_gate.get("selected_tp1")
        tp2 = decision_gate.get("selected_tp2")
        rr1 = decision_gate.get("selected_rr_tp1", 0.0)
        rr2 = decision_gate.get("selected_rr_tp2", 0.0)
        final_grade = decision_gate.get("final_grade", "BLOCKED")
        dq = decision_gate.get("data_quality", {}) or {}
        dq_level = dq.get("level", "MISSING")
        dq_score = float(dq.get("score", 0.0))
        plan_reasons = (trade_plan or {}).get("reason_codes", []) if trade_plan else []
        input_status = decision_gate.get("input_status", "OK")
        source = decision_gate.get("block_id", "S18_DECISION_GATE")
        alert_status = "PENDING"

    block_reasons = (decision_gate or {}).get("block_reasons", [])
    warning_reasons = (decision_gate or {}).get("warning_reasons", [])

    if plan_reasons:
        reason_summary = ", ".join(plan_reasons[:3])
    elif block_reasons:
        reason_summary = ", ".join(block_reasons[:3])
    elif warning_reasons:
        reason_summary = ", ".join(warning_reasons[:3])
    else:
        reason_summary = f"DECISION_{decision}"

    safety_summary = "safe_to_open_real_trade=false; private_api_used=false; live_order_sent=false"

    message_text = _format_message(
        symbol, side, entry, sl, tp1, tp2, rr1, rr2, final_grade, decision, reason_summary
    )

    sent = False

    if decision_gate is None:
        alert_status = "INVALID"
    elif decision == "BLOCK":
        alert_status = "BLOCKED"
        reason_codes.append("DECISION_IS_BLOCK")
    elif decision == "WATCH":
        alert_status = "SKIPPED"
        reason_codes.append("DECISION_IS_WATCH")
    elif decision == "ALLOW_PAPER":
        if telegram_mode == "DRY_RUN":
            alert_status = "DRY_RUN_READY"
            reason_codes.append("DRY_RUN_MODE")
        else:
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")
            if not token or not chat_id:
                alert_status = "INVALID"
                reason_codes.append("TELEGRAM_ENV_MISSING")
            else:
                alert_status = "SENT"
                sent = True
                reason_codes.append("SEND_MODE")
    else:
        alert_status = "INVALID"
        reason_codes.append(f"UNKNOWN_DECISION_{decision}")

    reason_codes += [
        f"SYMBOL_{symbol}",
        f"DECISION_{decision}",
        f"ALERT_STATUS_{alert_status}",
        f"TELEGRAM_MODE_{telegram_mode}",
        f"SIDE_{side}",
        f"GRADE_{final_grade}",
        f"DQ_{dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
        "PAPER_ONLY",
    ]

    return {
        "timestamp_utc": ts,
        "block_id": "S19_TELEGRAM_PAPER_ALERT",
        "symbol": symbol,
        "source": source,
        "input_status": input_status,
        "alert_status": alert_status,
        "telegram_mode": telegram_mode,
        "message_text": message_text,
        "sent": sent,
        "dry_run": dry_run,
        "decision": decision,
        "side": side,
        "entry_price": entry,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr_tp1": rr1,
        "rr_tp2": rr2,
        "final_grade": final_grade,
        "reason_summary": reason_summary,
        "safety_summary": safety_summary,
        "data_quality": {"level": dq_level, "score": dq_score},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["S20_PAPER_LIFECYCLE_TRACKER"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_output(reason: str) -> dict[str, Any]:
    ts = _now_utc()
    return {
        "timestamp_utc": ts,
        "block_id": "S19_TELEGRAM_PAPER_ALERT",
        "symbol": "UNKNOWN",
        "source": "NONE",
        "input_status": "MISSING",
        "alert_status": "INVALID",
        "telegram_mode": "DRY_RUN",
        "message_text": "PAPER ONLY / REAL TRADE DISABLED\nsafe_to_open_real_trade=false",
        "sent": False,
        "dry_run": True,
        "decision": "BLOCK",
        "side": "UNKNOWN",
        "entry_price": None,
        "stop_loss": None,
        "tp1": None,
        "tp2": None,
        "rr_tp1": 0.0,
        "rr_tp2": 0.0,
        "final_grade": "BLOCKED",
        "reason_summary": reason,
        "safety_summary": "safe_to_open_real_trade=false; private_api_used=false; live_order_sent=false",
        "data_quality": {"level": "MISSING", "score": 0.0},
        "reason_codes": [
            "INPUT_MISSING",
            reason,
            "ALERT_STATUS_INVALID",
            "TELEGRAM_MODE_DRY_RUN",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ],
        "feeds_next": {"next_blocks": ["S20_PAPER_LIFECYCLE_TRACKER"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def run_telegram_paper_alert_engine(mode: str = "DRY_RUN") -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    decision_gate = _load_json(DECISION_GATE_PATH)
    trade_plan = _load_json(TRADE_PLAN_PATH)
    scenario_trigger = _load_json(SCENARIO_TRIGGER_PATH)
    setup_context = _load_json(SETUP_CONTEXT_PATH)

    if decision_gate is None:
        result = no_valid_output("DECISION_GATE_MISSING")
    else:
        try:
            result = compute_telegram_paper_alert(
                decision_gate, trade_plan, scenario_trigger, setup_context, mode=mode
            )
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    _atomic_write(ALERT_PATH, json.dumps(result, indent=2))

    s19_state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S19_TELEGRAM_PAPER_ALERT_STATE",
        "last_alert_status": result["alert_status"],
        "last_telegram_mode": result["telegram_mode"],
        "last_decision": result["decision"],
        "last_sent": result["sent"],
        "last_final_grade": result["final_grade"],
        "runs": 1,
    }
    _atomic_write(S19_STATE_PATH, json.dumps(s19_state, indent=2))

    with ALERT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)
    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S19 Telegram Paper Alert — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Source:** {r['source']}",
        f"**Input Status:** {r['input_status']}",
        f"**Alert Status:** {r['alert_status']}",
        f"**Telegram Mode:** {r['telegram_mode']}",
        f"**Dry Run:** {r['dry_run']}",
        f"**Sent:** {r['sent']}",
        f"**Decision:** {r['decision']}",
        f"**Side:** {r['side']}",
        f"**Entry:** {r['entry_price']}",
        f"**Stop Loss:** {r['stop_loss']}",
        f"**TP1:** {r['tp1']}",
        f"**TP2:** {r['tp2']}",
        f"**RR TP1:** {r['rr_tp1']}",
        f"**RR TP2:** {r['rr_tp2']}",
        f"**Final Grade:** {r['final_grade']}",
        f"**Reason Summary:** {r['reason_summary']}",
        f"**Safety Summary:** {r['safety_summary']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
        "",
        "## Message",
        "",
        "```",
        r["message_text"],
        "```",
    ]
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")
