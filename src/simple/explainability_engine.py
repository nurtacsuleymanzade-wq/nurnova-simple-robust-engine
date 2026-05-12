"""S26 — Explainability / Failure Chain Report Engine.

Read-only diagnostic engine. Explains why Telegram signals did not happen
and where the pipeline blocked. No mutations. No real trades.
safe_to_open_real_trade always False.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S26_EXPLAINABILITY_FAILURE_CHAIN"
SOURCE = "S12_TO_S25_PIPELINE_INPUTS"

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

LATEST_REPORT_PATH = STATE_DIR / "latest_explainability_report.json"
S26_STATE_PATH = STATE_DIR / "s26_explainability_state.json"
HISTORY_PATH = DATA_DIR / "explainability_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s26_explainability_latest_report.md"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

# --------------------------------------------------------------------------- #
# Allowed enum values
# --------------------------------------------------------------------------- #

VALID_NO_SIGNAL_REASONS = {
    "NO_TRADE_SETUP", "WEAK_FLOW", "LOW_CONFIDENCE", "DEGRADED_DATA",
    "DECISION_BLOCKED", "PLAN_NOT_READY", "TELEGRAM_BLOCKED",
    "NO_LIFECYCLE", "NO_EDGE_CLAIM", "SYSTEM_ERROR", "UNKNOWN",
}

VALID_BLOCK_STAGES = {
    "S12_FLOW_STATE", "S13_FLOW_EVIDENCE", "S14_FLOW_PERSISTENCE",
    "S15_SETUP_CONTEXT", "S16_SCENARIO_ENTRY", "S17_TRADE_PLAN",
    "S18_DECISION_GATE", "S19_TELEGRAM_ALERT", "S20_PAPER_LIFECYCLE",
    "S21_OUTCOME_MONITOR", "S25_TELEGRAM_FOLLOWUP",
    "S22_EDGE_MATRIX_V2", "S23_SIMPLE_BRAIN_V2", "NONE", "UNKNOWN",
}

# --------------------------------------------------------------------------- #
# I/O helpers
# --------------------------------------------------------------------------- #

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Input loading
# --------------------------------------------------------------------------- #

def _load_inputs(state_dir: Path, data_dir: Path) -> dict[str, Any | None]:
    sd = state_dir
    return {
        "flow_state":          _load_json(sd / "latest_flow_state.json"),
        "flow_evidence":       _load_json(sd / "latest_flow_evidence.json"),
        "flow_persistence":    _load_json(sd / "latest_flow_persistence.json"),
        "setup_context":       _load_json(sd / "latest_setup_context.json"),
        "scenario_trigger":    _load_json(sd / "latest_scenario_trigger.json"),
        "trade_plan":          _load_json(sd / "latest_trade_plan.json"),
        "decision_gate":       _load_json(sd / "latest_decision_gate.json"),
        "telegram_alert":      _load_json(sd / "latest_telegram_paper_alert.json"),
        "paper_lifecycle":     _load_json(sd / "latest_paper_lifecycle.json"),
        "outcome_monitor":     _load_json(sd / "latest_outcome_monitor.json"),
        "telegram_followup":   _load_json(sd / "latest_telegram_followup.json"),
        "edge_matrix":         _load_json(sd / "latest_edge_matrix_v2.json"),
        "simple_brain":        _load_json(sd / "latest_simple_brain_v2.json"),
    }


def _input_status(inputs: dict[str, Any | None]) -> str:
    missing = [k for k, v in inputs.items() if v is None]
    if not missing:
        return "OK"
    if len(missing) >= len(inputs) // 2:
        return "CRITICAL"
    return "PARTIAL"


# --------------------------------------------------------------------------- #
# Diagnostic probes
# --------------------------------------------------------------------------- #

def _probe_flow(inputs: dict) -> tuple[str | None, list[str], list[str]]:
    """Returns (block_stage_or_None, failed_checks, weak_signals)."""
    failed: list[str] = []
    weak: list[str] = []

    flow_state = inputs.get("flow_state") or {}
    flow_evidence = inputs.get("flow_evidence") or {}
    flow_persistence = inputs.get("flow_persistence") or {}

    if not flow_state:
        failed.append("flow_state_missing")
        return "S12_FLOW_STATE", failed, weak

    flow_label = flow_evidence.get("flow_label", "")
    confidence = float(flow_evidence.get("confidence", 0.0))

    if flow_label in ("NEUTRAL_FLOW", ""):
        weak.append(f"flow_label={flow_label or 'MISSING'}")

    if confidence < 0.6:
        weak.append(f"flow_confidence={confidence:.2f}")

    quality_state = flow_state.get("quality_state", "")
    if quality_state in ("DEGRADED", "CRITICAL", "INVALID"):
        failed.append(f"quality_state={quality_state}")
        return "S12_FLOW_STATE", failed, weak

    if not flow_evidence:
        failed.append("flow_evidence_missing")
        return "S13_FLOW_EVIDENCE", failed, weak

    if not flow_persistence:
        failed.append("flow_persistence_missing")
        return "S14_FLOW_PERSISTENCE", failed, weak

    return None, failed, weak


def _probe_setup(inputs: dict) -> tuple[str | None, list[str]]:
    setup_context = inputs.get("setup_context") or {}
    scenario_trigger = inputs.get("scenario_trigger") or {}

    if not setup_context:
        return "S15_SETUP_CONTEXT", ["setup_context_missing"]

    setup_valid = setup_context.get("setup_valid", False)
    if not setup_valid:
        return "S15_SETUP_CONTEXT", ["setup_not_valid"]

    if not scenario_trigger:
        return "S16_SCENARIO_ENTRY", ["scenario_trigger_missing"]

    trigger_state = scenario_trigger.get("trigger_state", "")
    if trigger_state not in ("READY_FOR_ENTRY", "READY"):
        return "S16_SCENARIO_ENTRY", [f"trigger_state={trigger_state or 'MISSING'}"]

    return None, []


def _probe_trade_plan(inputs: dict) -> tuple[str | None, list[str]]:
    trade_plan = inputs.get("trade_plan") or {}
    if not trade_plan:
        return "S17_TRADE_PLAN", ["trade_plan_missing"]

    plan_status = trade_plan.get("plan_status", "")
    if plan_status != "PLAN_READY":
        return "S17_TRADE_PLAN", [f"plan_status={plan_status or 'MISSING'}"]

    return None, []


def _probe_decision(inputs: dict) -> tuple[str | None, list[str], str]:
    decision_gate = inputs.get("decision_gate") or {}
    if not decision_gate:
        return "S18_DECISION_GATE", ["decision_gate_missing"], "UNKNOWN"

    decision = decision_gate.get("decision", "UNKNOWN")
    if decision in ("BLOCK", "UNKNOWN"):
        block_reasons = decision_gate.get("block_reasons", [])
        return "S18_DECISION_GATE", [f"decision={decision}"] + block_reasons, decision

    return None, [], decision


def _probe_telegram(inputs: dict) -> tuple[str | None, list[str], dict[str, Any]]:
    alert = inputs.get("telegram_alert") or {}
    diag: dict[str, Any] = {}

    if not alert:
        return "S19_TELEGRAM_ALERT", ["telegram_alert_state_missing"], diag

    alert_status = alert.get("alert_status", "UNKNOWN")
    diag["alert_status"] = alert_status
    diag["telegram_sent"] = alert.get("telegram_sent", False)

    bot_token_set = alert.get("bot_token_set", False)
    chat_id_set = alert.get("chat_id_set", False)
    diag["bot_token_set"] = bot_token_set
    diag["chat_id_set"] = chat_id_set

    if alert_status in ("BLOCKED", "INVALID", "SKIPPED", "DRY_RUN"):
        checks = []
        if not bot_token_set:
            checks.append("TELEGRAM_BOT_TOKEN_NOT_SET")
        if not chat_id_set:
            checks.append("TELEGRAM_CHAT_ID_NOT_SET")
        if alert_status == "DRY_RUN":
            checks.append("TELEGRAM_DRY_RUN_MODE")
        elif alert_status == "BLOCKED":
            checks.append(f"alert_status={alert_status}")
        elif alert_status == "SKIPPED":
            checks.append(f"alert_status={alert_status}")
        elif alert_status == "INVALID":
            checks.append(f"alert_status={alert_status}")
        return "S19_TELEGRAM_ALERT", checks, diag

    return None, [], diag


def _probe_lifecycle(inputs: dict) -> tuple[str | None, list[str], dict[str, Any]]:
    lifecycle = inputs.get("paper_lifecycle") or {}
    diag: dict[str, Any] = {}

    if not lifecycle:
        return "S20_PAPER_LIFECYCLE", ["paper_lifecycle_missing"], diag

    lifecycle_status = lifecycle.get("lifecycle_status", "UNKNOWN")
    diag["lifecycle_status"] = lifecycle_status
    diag["active_trade"] = lifecycle.get("active_trade", False)

    if lifecycle_status in ("NO_TRADE", "INACTIVE", "UNKNOWN", "NO_LIFECYCLE"):
        return "S20_PAPER_LIFECYCLE", [f"lifecycle_status={lifecycle_status}"], diag

    return None, [], diag


def _probe_followup(inputs: dict) -> tuple[str | None, list[str]]:
    followup = inputs.get("telegram_followup") or {}
    if not followup:
        return "S25_TELEGRAM_FOLLOWUP", ["telegram_followup_missing"]

    followup_status = followup.get("followup_status", "UNKNOWN")
    if followup_status == "NO_LIFECYCLE":
        return "S25_TELEGRAM_FOLLOWUP", ["followup_status=NO_LIFECYCLE"]

    return None, []


def _probe_edge(inputs: dict) -> tuple[str | None, list[str]]:
    edge = inputs.get("edge_matrix") or {}
    if not edge:
        return "S22_EDGE_MATRIX_V2", ["edge_matrix_missing"]

    edge_status = edge.get("edge_status", "UNKNOWN")
    if edge_status == "NO_EDGE_CLAIM":
        return "S22_EDGE_MATRIX_V2", [f"edge_status={edge_status}"]

    return None, []


def _probe_data_quality(inputs: dict) -> tuple[str, dict[str, Any]]:
    flow_state = inputs.get("flow_state") or {}
    quality_state = flow_state.get("quality_state", "UNKNOWN")

    brain = inputs.get("simple_brain") or {}
    dq = brain.get("data_quality") or {}
    dq_level = dq.get("level", quality_state)
    dq_score = float(dq.get("score", 0.0))

    diag = {"quality_state": quality_state, "dq_level": dq_level, "dq_score": dq_score}

    if dq_level in ("DEGRADED", "CRITICAL", "INVALID", "LOW"):
        return "DEGRADED_DATA", diag
    return "OK", diag


# --------------------------------------------------------------------------- #
# Closest-to-signal probe
# --------------------------------------------------------------------------- #

def _closest_to_signal(
    block_stage: str,
    all_failed: list[str],
    decision: str,
    trade_plan: dict | None,
) -> str:
    if block_stage == "NONE":
        return "PIPELINE_COMPLETE_NO_BLOCK"
    if block_stage == "S18_DECISION_GATE":
        if decision == "WATCH":
            return "DECISION_IS_WATCH_NEEDS_STRONGER_SETUP"
        gate = (trade_plan or {})
        rr2 = float(gate.get("rr_tp2", 0.0))
        if rr2 > 0:
            return f"TRADE_PLAN_EXISTS_BUT_DECISION_BLOCKED_RR2={rr2:.2f}"
        return "DECISION_BLOCKED_NO_VALID_PLAN"
    if block_stage in ("S16_SCENARIO_ENTRY", "S17_TRADE_PLAN"):
        return "FLOW_AND_SETUP_OK_NEED_SCENARIO_OR_PLAN"
    if block_stage in ("S15_SETUP_CONTEXT",):
        return "FLOW_OK_NEED_VALID_SETUP"
    if block_stage in ("S12_FLOW_STATE", "S13_FLOW_EVIDENCE", "S14_FLOW_PERSISTENCE"):
        return "NEED_STRONGER_DIRECTIONAL_FLOW"
    if block_stage == "S19_TELEGRAM_ALERT":
        return "DECISION_PASSED_TELEGRAM_ENV_NOT_CONFIGURED"
    if block_stage == "S20_PAPER_LIFECYCLE":
        return "ALERT_SENT_NO_ACTIVE_LIFECYCLE"
    if block_stage in ("S25_TELEGRAM_FOLLOWUP",):
        return "NO_LIFECYCLE_SO_NO_TP_SL_FOLLOWUP"
    if block_stage in ("S22_EDGE_MATRIX_V2",):
        return "EDGE_NOT_STATISTICALLY_VALIDATED_YET"
    return "UNKNOWN_CLOSEST"


# --------------------------------------------------------------------------- #
# Recommended next fix
# --------------------------------------------------------------------------- #

def _recommend_next_fix(block_stage: str, no_signal_reason: str, failed_checks: list[str]) -> str:
    # Only recommend Telegram env fix when Telegram is the actual block point
    if block_stage == "S19_TELEGRAM_ALERT":
        if "TELEGRAM_BOT_TOKEN_NOT_SET" in failed_checks:
            return "Set TELEGRAM_BOT_TOKEN env variable"
        if "TELEGRAM_CHAT_ID_NOT_SET" in failed_checks:
            return "Set TELEGRAM_CHAT_ID env variable"
        if "TELEGRAM_DRY_RUN_MODE" in failed_checks:
            return "Pass mode=SEND to telegram_paper_alert_engine to enable live alerts"
    mapping = {
        "S12_FLOW_STATE":       "Improve flow data quality — check WebSocket feed health",
        "S13_FLOW_EVIDENCE":    "Strengthen directional flow evidence — wait for higher confidence",
        "S14_FLOW_PERSISTENCE": "Wait for flow to persist across multiple buckets",
        "S15_SETUP_CONTEXT":    "Need a valid setup_valid=True from flow-to-setup-context engine",
        "S16_SCENARIO_ENTRY":   "Wait for READY_FOR_ENTRY trigger state",
        "S17_TRADE_PLAN":       "Trade plan not ready — check RR, entry, SL, TP levels",
        "S18_DECISION_GATE":    "Decision blocked — review block_reasons in decision_gate state",
        "S19_TELEGRAM_ALERT":   "Configure Telegram bot token and chat ID in environment",
        "S20_PAPER_LIFECYCLE":  "No active paper trade lifecycle — alert must be sent first",
        "S21_OUTCOME_MONITOR":  "Outcome monitor not recording — check paper_lifecycle state",
        "S25_TELEGRAM_FOLLOWUP":"No lifecycle active, TP/SL follow-up requires active paper trade",
        "S22_EDGE_MATRIX_V2":   "Accumulate more paper trades to build statistical edge claim",
        "S23_SIMPLE_BRAIN_V2":  "Brain V2 not reporting — check edge_matrix and decision_gate",
        "NONE":                 "System is healthy — monitor for setup conditions",
        "UNKNOWN":              "Investigate missing state files and module errors",
    }
    return mapping.get(block_stage, "Investigate pipeline state files for errors")


# --------------------------------------------------------------------------- #
# Confidence-to-next-signal estimate
# --------------------------------------------------------------------------- #

def _confidence_to_next_signal(block_stage: str, weak_signals: list[str], failed_checks: list[str]) -> float:
    base = 0.5
    # Penalise by how deep the block is
    stage_penalty = {
        "S12_FLOW_STATE": 0.4, "S13_FLOW_EVIDENCE": 0.35, "S14_FLOW_PERSISTENCE": 0.3,
        "S15_SETUP_CONTEXT": 0.25, "S16_SCENARIO_ENTRY": 0.2, "S17_TRADE_PLAN": 0.15,
        "S18_DECISION_GATE": 0.1, "S19_TELEGRAM_ALERT": 0.05,
        "S20_PAPER_LIFECYCLE": 0.02, "S25_TELEGRAM_FOLLOWUP": 0.02,
        "S22_EDGE_MATRIX_V2": 0.05, "S23_SIMPLE_BRAIN_V2": 0.05,
        "NONE": 0.0, "UNKNOWN": 0.45,
    }
    score = base - stage_penalty.get(block_stage, 0.3)
    score -= len(failed_checks) * 0.03
    score -= len(weak_signals) * 0.02
    return round(max(0.0, min(1.0, score)), 2)


# --------------------------------------------------------------------------- #
# Markdown report writer
# --------------------------------------------------------------------------- #

def _write_markdown_report(record: dict[str, Any]) -> None:
    ts = record["timestamp_utc"]
    sym = record["symbol"]
    final = record["final_answer"]
    reason = record["no_signal_reason"]
    stage = record["block_stage"]
    fix = record["recommended_next_fix"]
    safe = record["execution_safety"]["safe_to_open_real_trade"]
    tg = record["telegram_diagnosis"]
    bot_ok = tg.get("bot_token_set", "?")
    chat_ok = tg.get("chat_id_set", "?")

    lines = [
        f"# S26 Explainability — Failure Chain Report",
        f"",
        f"**timestamp_utc**: {ts}  ",
        f"**symbol**: {sym}  ",
        f"**block_id**: {record['block_id']}",
        f"",
        f"---",
        f"",
        f"## 1. Why no Telegram signal?",
        f"",
        f"**{reason}** — {final}",
        f"",
        f"## 2. Where did the chain stop?",
        f"",
        f"**block_stage**: `{stage}`",
        f"",
        f"**block_chain**:",
    ]
    for step in record.get("block_chain", []):
        lines.append(f"- {step}")
    lines += [
        f"",
        f"## 3. What is the closest missing condition?",
        f"",
        f"**closest_to_signal**: {record['closest_to_signal']}",
        f"",
        f"**failed_checks**:",
    ]
    for fc in record.get("failed_checks", []):
        lines.append(f"- {fc}")
    if record.get("weak_signals"):
        lines.append(f"")
        lines.append(f"**weak_signals**:")
        for ws in record["weak_signals"]:
            lines.append(f"- {ws}")
    lines += [
        f"",
        f"## 4. What should be fixed next?",
        f"",
        f"**recommended_next_fix**: {fix}",
        f"",
        f"**confidence_to_next_signal**: {record['confidence_to_next_signal']}",
        f"",
        f"## 5. Is the system running?",
        f"",
        f"**input_status**: {record['input_status']}",
        f"**system_health**: {record['system_health_diagnosis'].get('status', 'UNKNOWN')}",
        f"",
        f"## 6. Is Telegram configured?",
        f"",
        f"- **bot_token_set**: {bot_ok}",
        f"- **chat_id_set**: {chat_ok}",
        f"- **alert_status**: {tg.get('alert_status', 'UNKNOWN')}",
        f"- **telegram_sent**: {tg.get('telegram_sent', False)}",
        f"",
        f"## 7. Is it safe?",
        f"",
        f"**safe_to_open_real_trade**: `{safe}`  ",
        f"**private_api_used**: `{record['execution_safety']['private_api_used']}`  ",
        f"**live_order_sent**: `{record['execution_safety']['live_order_sent']}`",
        f"",
        f"---",
        f"",
        f"## Reason Codes",
        f"",
    ]
    for rc in record.get("reason_codes", []):
        lines.append(f"- {rc}")
    lines.append("")
    _atomic_write(REPORT_PATH, "\n".join(lines))


# --------------------------------------------------------------------------- #
# Main engine
# --------------------------------------------------------------------------- #

def run_explainability_engine(
    symbol: str = "BTCUSDT",
    state_dir: Path | None = None,
    data_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Run S26 diagnostic engine. Read-only. Never raises."""
    sd = state_dir or STATE_DIR
    dd = data_dir or DATA_DIR
    rd = reports_dir or REPORTS_DIR

    ts = _utc_now()
    inputs = _load_inputs(sd, dd)
    input_status = _input_status(inputs)

    all_failed: list[str] = []
    all_weak: list[str] = []
    block_chain: list[str] = []
    block_stage = "NONE"
    no_signal_reason = "UNKNOWN"
    reason_codes: list[str] = ["S26_EXPLAINABILITY", "SAFE_TO_OPEN_REAL_TRADE_FALSE", "NO_PRIVATE_API"]

    # --- Flow probes ---
    flow_block, flow_failed, flow_weak = _probe_flow(inputs)
    all_failed.extend(flow_failed)
    all_weak.extend(flow_weak)
    if flow_block:
        block_stage = flow_block
        block_chain.append(f"BLOCKED_AT_{flow_block}")
        no_signal_reason = "WEAK_FLOW" if flow_weak else "DEGRADED_DATA"

    # --- Data quality ---
    dq_status, dq_diag = _probe_data_quality(inputs)
    if dq_status == "DEGRADED_DATA":
        if block_stage == "NONE":
            block_stage = "S12_FLOW_STATE"
            block_chain.append("BLOCKED_AT_S12_FLOW_STATE_DATA_QUALITY")
        no_signal_reason = "DEGRADED_DATA"
        all_failed.append("data_quality_degraded")

    # --- Setup probes ---
    if block_stage == "NONE":
        setup_block, setup_failed = _probe_setup(inputs)
        all_failed.extend(setup_failed)
        if setup_block:
            block_stage = setup_block
            block_chain.append(f"BLOCKED_AT_{setup_block}")
            no_signal_reason = "NO_TRADE_SETUP"

    # --- Trade plan ---
    if block_stage == "NONE":
        plan_block, plan_failed = _probe_trade_plan(inputs)
        all_failed.extend(plan_failed)
        if plan_block:
            block_stage = plan_block
            block_chain.append(f"BLOCKED_AT_{plan_block}")
            no_signal_reason = "PLAN_NOT_READY"

    # --- Decision gate ---
    decision_value = "UNKNOWN"
    if block_stage == "NONE":
        dec_block, dec_failed, decision_value = _probe_decision(inputs)
        all_failed.extend(dec_failed)
        if dec_block:
            block_stage = dec_block
            block_chain.append(f"BLOCKED_AT_{dec_block}")
            no_signal_reason = "DECISION_BLOCKED"
    else:
        dg = inputs.get("decision_gate") or {}
        decision_value = dg.get("decision", "UNKNOWN")

    # --- Telegram ---
    tg_block, tg_failed, tg_diag = _probe_telegram(inputs)
    all_failed.extend(tg_failed)
    if tg_block and block_stage == "NONE":
        block_stage = tg_block
        block_chain.append(f"BLOCKED_AT_{tg_block}")
        no_signal_reason = "TELEGRAM_BLOCKED"

    # --- Lifecycle ---
    lc_block, lc_failed, lc_diag = _probe_lifecycle(inputs)
    all_failed.extend(lc_failed)
    lifecycle_diag = lc_diag
    if lc_block and block_stage == "NONE":
        block_stage = lc_block
        block_chain.append(f"BLOCKED_AT_{lc_block}")
        no_signal_reason = "NO_LIFECYCLE"

    # --- Follow-up ---
    fu_block, fu_failed = _probe_followup(inputs)
    all_failed.extend(fu_failed)
    if fu_block and block_stage == "NONE":
        block_stage = fu_block
        block_chain.append(f"BLOCKED_AT_{fu_block}")
        if no_signal_reason == "UNKNOWN":
            no_signal_reason = "NO_LIFECYCLE"

    # --- Edge ---
    edge_block, edge_failed = _probe_edge(inputs)
    all_failed.extend(edge_failed)
    edge_diag: dict[str, Any] = {"edge_status": (inputs.get("edge_matrix") or {}).get("edge_status", "UNKNOWN")}
    if edge_block and block_stage == "NONE":
        block_stage = edge_block
        block_chain.append(f"BLOCKED_AT_{edge_block}")
        no_signal_reason = "NO_EDGE_CLAIM"

    # --- Weak flow / low confidence override ---
    if all_weak and no_signal_reason == "UNKNOWN":
        no_signal_reason = "WEAK_FLOW"
    if any("flow_confidence" in w for w in all_weak) and no_signal_reason in ("UNKNOWN", "WEAK_FLOW"):
        confidence_val = 0.0
        for w in all_weak:
            if w.startswith("flow_confidence="):
                try:
                    confidence_val = float(w.split("=")[1])
                except ValueError:
                    pass
        if confidence_val < 0.6:
            no_signal_reason = "LOW_CONFIDENCE"

    # --- Input missing check ---
    if input_status == "CRITICAL" and no_signal_reason == "UNKNOWN":
        no_signal_reason = "SYSTEM_ERROR"
        if block_stage == "NONE":
            block_stage = "UNKNOWN"

    if not block_chain:
        block_chain.append("NO_BLOCK_DETECTED")

    # --- Build final_answer ---
    stage_labels = {
        "S12_FLOW_STATE": "flow state collection",
        "S13_FLOW_EVIDENCE": "flow evidence engine",
        "S14_FLOW_PERSISTENCE": "flow persistence engine",
        "S15_SETUP_CONTEXT": "setup context engine",
        "S16_SCENARIO_ENTRY": "scenario entry trigger",
        "S17_TRADE_PLAN": "trade plan engine",
        "S18_DECISION_GATE": "decision gate",
        "S19_TELEGRAM_ALERT": "Telegram alert env/config",
        "S20_PAPER_LIFECYCLE": "paper lifecycle tracker",
        "S21_OUTCOME_MONITOR": "outcome monitor",
        "S25_TELEGRAM_FOLLOWUP": "Telegram follow-up (no lifecycle)",
        "S22_EDGE_MATRIX_V2": "edge matrix (no statistical claim yet)",
        "S23_SIMPLE_BRAIN_V2": "simple brain v2",
        "NONE": "no block — system healthy",
        "UNKNOWN": "unknown stage",
    }
    stage_label = stage_labels.get(block_stage, block_stage)
    final_answer = f"No Telegram signal. Blocked at {stage_label}. Reason: {no_signal_reason}."

    # --- Reason codes ---
    reason_codes.append(f"NO_SIGNAL_{no_signal_reason}")
    reason_codes.append(f"BLOCK_STAGE_{block_stage}")
    reason_codes.append(f"SYMBOL_{symbol}")
    reason_codes.append(f"INPUT_STATUS_{input_status}")
    if all_failed:
        reason_codes.append(f"FAILED_CHECKS_{len(all_failed)}")
    if all_weak:
        reason_codes.append(f"WEAK_SIGNALS_{len(all_weak)}")

    closest = _closest_to_signal(block_stage, all_failed, decision_value, inputs.get("trade_plan"))
    next_fix = _recommend_next_fix(block_stage, no_signal_reason, all_failed)
    confidence = _confidence_to_next_signal(block_stage, all_weak, all_failed)

    system_health: dict[str, Any] = {
        "status": "DEGRADED" if input_status != "OK" else "OK",
        "inputs_loaded": sum(1 for v in inputs.values() if v is not None),
        "inputs_total": len(inputs),
        "input_status": input_status,
    }

    decision_diag: dict[str, Any] = {
        "decision": decision_value,
        "block_reasons": (inputs.get("decision_gate") or {}).get("block_reasons", []),
        "allowed_for_paper_alert": (inputs.get("decision_gate") or {}).get("allowed_for_paper_alert", False),
    }

    record: dict[str, Any] = {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": SOURCE,
        "input_status": input_status,
        "final_answer": final_answer,
        "no_signal_reason": no_signal_reason,
        "block_stage": block_stage,
        "block_chain": block_chain,
        "failed_checks": all_failed,
        "weak_signals": all_weak,
        "closest_to_signal": closest,
        "telegram_diagnosis": tg_diag,
        "lifecycle_diagnosis": lifecycle_diag,
        "data_quality_diagnosis": dq_diag,
        "decision_diagnosis": decision_diag,
        "edge_diagnosis": edge_diag,
        "system_health_diagnosis": system_health,
        "recommended_next_fix": next_fix,
        "confidence_to_next_signal": confidence,
        "data_quality": {"level": dq_diag.get("dq_level", "UNKNOWN"), "score": dq_diag.get("dq_score", 0.0)},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["S22_EDGE_MATRIX_V2", "S23_SIMPLE_BRAIN_V2"]},
        "execution_safety": dict(SAFETY),
    }

    # Write outputs (never raises)
    try:
        _atomic_write(sd / "latest_explainability_report.json", json.dumps(record, indent=2, ensure_ascii=False))
        _atomic_write(sd / "s26_explainability_state.json", json.dumps(record, indent=2, ensure_ascii=False))
        _append_jsonl(dd / "explainability_history.jsonl", record)
        _write_markdown_report_to(record, rd / "s26_explainability_latest_report.md")
    except Exception:
        pass

    return record


def _write_markdown_report_to(record: dict[str, Any], path: Path) -> None:
    ts = record["timestamp_utc"]
    sym = record["symbol"]
    final = record["final_answer"]
    reason = record["no_signal_reason"]
    stage = record["block_stage"]
    fix = record["recommended_next_fix"]
    safe = record["execution_safety"]["safe_to_open_real_trade"]
    tg = record["telegram_diagnosis"]
    bot_ok = tg.get("bot_token_set", "?")
    chat_ok = tg.get("chat_id_set", "?")

    lines = [
        "# S26 Explainability — Failure Chain Report",
        "",
        f"**timestamp_utc**: {ts}  ",
        f"**symbol**: {sym}  ",
        f"**block_id**: {record['block_id']}",
        "",
        "---",
        "",
        "## 1. Why no Telegram signal?",
        "",
        f"**{reason}** — {final}",
        "",
        "## 2. Where did the chain stop?",
        "",
        f"**block_stage**: `{stage}`",
        "",
        "**block_chain**:",
    ]
    for step in record.get("block_chain", []):
        lines.append(f"- {step}")
    lines += [
        "",
        "## 3. What is the closest missing condition?",
        "",
        f"**closest_to_signal**: {record['closest_to_signal']}",
        "",
        "**failed_checks**:",
    ]
    for fc in record.get("failed_checks", []):
        lines.append(f"- {fc}")
    if record.get("weak_signals"):
        lines.append("")
        lines.append("**weak_signals**:")
        for ws in record["weak_signals"]:
            lines.append(f"- {ws}")
    lines += [
        "",
        "## 4. What should be fixed next?",
        "",
        f"**recommended_next_fix**: {fix}",
        "",
        f"**confidence_to_next_signal**: {record['confidence_to_next_signal']}",
        "",
        "## 5. Is the system running?",
        "",
        f"**input_status**: {record['input_status']}",
        f"**system_health**: {record['system_health_diagnosis'].get('status', 'UNKNOWN')}",
        "",
        "## 6. Is Telegram configured?",
        "",
        f"- **bot_token_set**: {bot_ok}",
        f"- **chat_id_set**: {chat_ok}",
        f"- **alert_status**: {tg.get('alert_status', 'UNKNOWN')}",
        f"- **telegram_sent**: {tg.get('telegram_sent', False)}",
        "",
        "## 7. Is it safe?",
        "",
        f"**safe_to_open_real_trade**: `{safe}`  ",
        f"**private_api_used**: `{record['execution_safety']['private_api_used']}`  ",
        f"**live_order_sent**: `{record['execution_safety']['live_order_sent']}`",
        "",
        "---",
        "",
        "## Reason Codes",
        "",
    ]
    for rc in record.get("reason_codes", []):
        lines.append(f"- {rc}")
    lines.append("")
    _atomic_write(path, "\n".join(lines))
