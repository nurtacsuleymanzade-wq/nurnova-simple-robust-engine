"""S18 — Decision Gate Engine. Evaluates S17 trade plan and decides paper-only ALLOW/WATCH/BLOCK."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"
SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"
SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"
FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"
EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"

DECISION_GATE_PATH = STATE_DIR / "latest_decision_gate.json"
S18_STATE_PATH = STATE_DIR / "s18_decision_gate_state.json"
DECISION_GATE_LOG_PATH = DATA_DIR / "decision_gate_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s18_decision_gate_latest_report.md"

MIN_RR_TP1 = 1.0
MIN_RR_TP2 = 1.5


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _price_logic_valid(side: str, entry: Any, sl: Any, tp1: Any, tp2: Any) -> bool:
    if not all(isinstance(v, (int, float)) for v in (entry, sl, tp1, tp2)):
        return False
    if side == "LONG":
        return sl < entry < tp1 <= tp2
    if side == "SHORT":
        return sl > entry > tp1 >= tp2
    return False


def _grade(decision: str, rr1: float, rr2: float, dq_score: float, trigger_strength: float) -> str:
    if decision == "BLOCK":
        return "BLOCKED"
    if decision == "WATCH":
        return "WATCH"
    composite = (rr2 * 0.4) + (trigger_strength * 0.35) + (dq_score * 0.25)
    if composite >= 1.55 and rr2 >= 2.5:
        return "A_PLUS"
    if composite >= 1.30 and rr2 >= 2.0:
        return "A"
    if composite >= 1.05:
        return "B"
    return "C"


def compute_decision_gate(
    trade_plan: dict[str, Any] | None,
    scenario_trigger: dict[str, Any] | None,
    setup_context: dict[str, Any] | None,
    flow_state: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    persistence: dict[str, Any] | None,
) -> dict[str, Any]:
    ts = _now_utc()
    block_reasons: list[str] = []
    warning_reasons: list[str] = []
    reason_codes: list[str] = []

    input_available = trade_plan is not None
    input_status = "OK" if input_available else "MISSING"

    if trade_plan is None:
        block_reasons.append("TRADE_PLAN_MISSING")
    if scenario_trigger is None:
        warning_reasons.append("SCENARIO_TRIGGER_MISSING")

    trade_plan = trade_plan or {}
    scenario_trigger = scenario_trigger or {}
    setup_context = setup_context or {}
    flow_state = flow_state or {}
    evidence = evidence or {}
    persistence = persistence or {}

    symbol = (
        trade_plan.get("symbol")
        or scenario_trigger.get("symbol")
        or setup_context.get("symbol")
        or "UNKNOWN"
    )
    source = trade_plan.get("block_id") or "S17_TRADE_PLAN_ENGINE"

    plan_status = trade_plan.get("plan_status", "NO_PLAN")
    side = trade_plan.get("side", "UNKNOWN")
    entry = trade_plan.get("entry_price")
    sl = trade_plan.get("stop_loss")
    tp1 = trade_plan.get("tp1")
    tp2 = trade_plan.get("tp2")
    rr1 = float(trade_plan.get("rr_tp1", 0.0) or 0.0)
    rr2 = float(trade_plan.get("rr_tp2", 0.0) or 0.0)
    plan_reason_codes = trade_plan.get("reason_codes", []) or []
    plan_exec_safety = trade_plan.get("execution_safety", {}) or {}
    plan_dq = trade_plan.get("data_quality", {}) or {}
    dq_level = plan_dq.get("level", "MISSING")
    dq_score = float(plan_dq.get("score", 0.0))

    ready_for_entry = bool(scenario_trigger.get("ready_for_entry", False))
    trigger_strength = float(scenario_trigger.get("trigger_strength", 0.0))
    trigger_state = scenario_trigger.get("trigger_state", "NO_TRIGGER")

    plan_ready = plan_status == "PLAN_READY"
    side_valid = side in ("LONG", "SHORT")
    price_logic_valid = _price_logic_valid(side, entry, sl, tp1, tp2) if side_valid else False
    rr_valid = rr1 > 0 and rr2 > 0
    rr_threshold_valid = rr1 >= MIN_RR_TP1 and rr2 >= MIN_RR_TP2
    data_quality_valid = dq_level in ("OK", "HIGH")
    trigger_ready = ready_for_entry and trigger_state == "READY_FOR_ENTRY"

    safety_valid = (
        plan_exec_safety.get("safe_to_open_real_trade", True) is False
        and plan_exec_safety.get("private_api_used", True) is False
        and plan_exec_safety.get("live_order_sent", True) is False
    )
    reasons_present = len(plan_reason_codes) > 0

    if not input_available:
        block_reasons.append("INPUT_NOT_AVAILABLE")
    if plan_status == "INVALID":
        block_reasons.append("PLAN_STATUS_INVALID")
    if not side_valid and input_available:
        block_reasons.append(f"SIDE_NOT_DIRECTIONAL_{side}")
    if input_available and side_valid and not price_logic_valid:
        block_reasons.append("PRICE_LOGIC_CONTRADICTION")
    if input_available and not rr_valid:
        block_reasons.append("RR_INVALID")
    if input_available and not safety_valid:
        block_reasons.append("UNSAFE_FLAGS_DETECTED")
    if input_available and not reasons_present:
        block_reasons.append("EMPTY_PLAN_REASONS")
    if input_available and dq_level in ("INVALID", "MISSING"):
        block_reasons.append(f"DATA_QUALITY_INVALID_{dq_level}")

    if input_available and dq_level == "LOW":
        warning_reasons.append("DATA_QUALITY_LOW")
    if input_available and not trigger_ready:
        warning_reasons.append(f"TRIGGER_NOT_READY_{trigger_state}")
    if input_available and not plan_ready:
        warning_reasons.append(f"PLAN_NOT_READY_{plan_status}")
    if input_available and rr_valid and not rr_threshold_valid:
        warning_reasons.append("RR_BELOW_THRESHOLD")

    invalid = (
        not input_available
        or plan_status == "INVALID"
        or (input_available and side_valid and not price_logic_valid)
        or (input_available and not safety_valid)
    )

    if invalid:
        decision = "BLOCK"
        decision_status = "INVALID" if (plan_status == "INVALID" or not input_available) else "BLOCKED"
    elif block_reasons:
        decision = "BLOCK"
        decision_status = "BLOCKED"
    elif (
        plan_ready
        and side_valid
        and price_logic_valid
        and rr_valid
        and rr_threshold_valid
        and data_quality_valid
        and trigger_ready
        and safety_valid
        and reasons_present
    ):
        decision = "ALLOW_PAPER"
        decision_status = "PASSED"
    else:
        decision = "WATCH"
        decision_status = "WATCH_ONLY"

    allowed_for_paper_alert = decision == "ALLOW_PAPER"
    allowed_for_paper_lifecycle = decision == "ALLOW_PAPER"

    gate_checks = {
        "input_available": input_available,
        "plan_ready": plan_ready,
        "side_valid": side_valid,
        "price_logic_valid": price_logic_valid,
        "rr_valid": rr_valid,
        "rr_threshold_valid": rr_threshold_valid,
        "data_quality_valid": data_quality_valid,
        "trigger_ready": trigger_ready,
        "safety_valid": safety_valid,
        "reasons_present": reasons_present,
    }

    passed_checks = sum(1 for v in gate_checks.values() if v)
    decision_score = round(passed_checks / len(gate_checks), 4)

    final_grade = _grade(decision, rr1, rr2, dq_score, trigger_strength)

    selected_side = side if side_valid and decision != "BLOCK" else ("NEUTRAL" if not side_valid else side)
    selected_entry = entry if decision != "BLOCK" else None
    selected_sl = sl if decision != "BLOCK" else None
    selected_tp1 = tp1 if decision != "BLOCK" else None
    selected_tp2 = tp2 if decision != "BLOCK" else None
    selected_rr1 = rr1 if decision != "BLOCK" else 0.0
    selected_rr2 = rr2 if decision != "BLOCK" else 0.0

    reason_codes += [
        f"SYMBOL_{symbol}",
        f"DECISION_{decision}",
        f"DECISION_STATUS_{decision_status}",
        f"SIDE_{side}",
        f"PLAN_STATUS_{plan_status}",
        f"TRIGGER_{trigger_state}",
        f"DQ_{dq_level}",
        f"GRADE_{final_grade}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_TELEGRAM",
        "NO_ORDER_EXECUTION",
        "PAPER_ONLY",
    ]
    if block_reasons:
        reason_codes += [f"BLOCK_{b}" for b in block_reasons]
    if warning_reasons:
        reason_codes += [f"WARN_{w}" for w in warning_reasons]

    return {
        "timestamp_utc": ts,
        "block_id": "S18_DECISION_GATE",
        "symbol": symbol,
        "source": source,
        "input_status": input_status,
        "decision": decision,
        "decision_status": decision_status,
        "allowed_for_paper_alert": allowed_for_paper_alert,
        "allowed_for_paper_lifecycle": allowed_for_paper_lifecycle,
        "block_reasons": block_reasons,
        "warning_reasons": warning_reasons,
        "decision_score": decision_score,
        "final_grade": final_grade,
        "selected_side": selected_side,
        "selected_entry": selected_entry,
        "selected_stop_loss": selected_sl,
        "selected_tp1": selected_tp1,
        "selected_tp2": selected_tp2,
        "selected_rr_tp1": selected_rr1,
        "selected_rr_tp2": selected_rr2,
        "gate_checks": gate_checks,
        "data_quality": {"level": dq_level, "score": dq_score},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["S19_TELEGRAM_PAPER_ALERT"]},
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
        "block_id": "S18_DECISION_GATE",
        "symbol": "UNKNOWN",
        "source": "NONE",
        "input_status": "MISSING",
        "decision": "BLOCK",
        "decision_status": "INVALID",
        "allowed_for_paper_alert": False,
        "allowed_for_paper_lifecycle": False,
        "block_reasons": ["INPUT_NOT_AVAILABLE", reason],
        "warning_reasons": [],
        "decision_score": 0.0,
        "final_grade": "BLOCKED",
        "selected_side": "UNKNOWN",
        "selected_entry": None,
        "selected_stop_loss": None,
        "selected_tp1": None,
        "selected_tp2": None,
        "selected_rr_tp1": 0.0,
        "selected_rr_tp2": 0.0,
        "gate_checks": {
            "input_available": False,
            "plan_ready": False,
            "side_valid": False,
            "price_logic_valid": False,
            "rr_valid": False,
            "rr_threshold_valid": False,
            "data_quality_valid": False,
            "trigger_ready": False,
            "safety_valid": False,
            "reasons_present": False,
        },
        "data_quality": {"level": "MISSING", "score": 0.0},
        "reason_codes": [
            "INPUT_MISSING",
            reason,
            "DECISION_BLOCK",
            "DECISION_STATUS_INVALID",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_TELEGRAM",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ],
        "feeds_next": {"next_blocks": ["S19_TELEGRAM_PAPER_ALERT"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_decision_gate_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    trade_plan = _load_json(TRADE_PLAN_PATH)
    scenario_trigger = _load_json(SCENARIO_TRIGGER_PATH)
    setup_context = _load_json(SETUP_CONTEXT_PATH)
    flow_state = _load_json(FLOW_STATE_PATH)
    evidence = _load_json(EVIDENCE_PATH)
    persistence = _load_json(PERSISTENCE_PATH)

    if trade_plan is None:
        result = no_valid_output("TRADE_PLAN_MISSING")
    else:
        try:
            result = compute_decision_gate(
                trade_plan, scenario_trigger, setup_context, flow_state, evidence, persistence
            )
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    DECISION_GATE_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s18_state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S18_DECISION_GATE_STATE",
        "last_decision": result["decision"],
        "last_decision_status": result["decision_status"],
        "last_final_grade": result["final_grade"],
        "last_decision_score": result["decision_score"],
        "last_selected_side": result["selected_side"],
        "runs": 1,
    }
    S18_STATE_PATH.write_text(json.dumps(s18_state, indent=2), encoding="utf-8")

    with DECISION_GATE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)
    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S18 Decision Gate — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Source:** {r['source']}",
        f"**Input Status:** {r['input_status']}",
        f"**Decision:** {r['decision']}",
        f"**Decision Status:** {r['decision_status']}",
        f"**Final Grade:** {r['final_grade']}",
        f"**Allowed For Paper Alert:** {r['allowed_for_paper_alert']}",
        f"**Allowed For Paper Lifecycle:** {r['allowed_for_paper_lifecycle']}",
        f"**Decision Score:** {r['decision_score']}",
        f"**Selected Side:** {r['selected_side']}",
        f"**Selected Entry:** {r['selected_entry']}",
        f"**Selected Stop Loss:** {r['selected_stop_loss']}",
        f"**Selected TP1:** {r['selected_tp1']}",
        f"**Selected TP2:** {r['selected_tp2']}",
        f"**Selected RR TP1:** {r['selected_rr_tp1']}",
        f"**Selected RR TP2:** {r['selected_rr_tp2']}",
        f"**Block Reasons:** {', '.join(r['block_reasons']) or '(none)'}",
        f"**Warning Reasons:** {', '.join(r['warning_reasons']) or '(none)'}",
        f"**Gate Checks:** {r['gate_checks']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
