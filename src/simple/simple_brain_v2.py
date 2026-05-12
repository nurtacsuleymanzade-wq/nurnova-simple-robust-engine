"""S23 — Simple Brain v2. Read-only market intelligence report layer.

Aggregates the full S12-S22 chain into a single brain report. This block
performs NO trade execution, NO private API calls, NO order placement,
NO Telegram sending, NO Decision Gate override, NO new trade plan, and
NO edge claim derivation. It only summarizes existing system state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S23_SIMPLE_BRAIN_V2"
FEEDS_NEXT = {"next_blocks": ["S24_VPS_SYSTEMD_24_7_PRODUCTION_OBSERVER"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"
FLOW_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
FLOW_PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"
SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"
TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"
DECISION_GATE_PATH = STATE_DIR / "latest_decision_gate.json"
TELEGRAM_ALERT_PATH = STATE_DIR / "latest_telegram_paper_alert.json"
PAPER_LIFECYCLE_PATH = STATE_DIR / "latest_paper_lifecycle.json"
OUTCOME_MONITOR_PATH = STATE_DIR / "latest_outcome_monitor.json"
EDGE_MATRIX_V2_PATH = STATE_DIR / "latest_edge_matrix_v2.json"

LATEST_BRAIN_PATH = STATE_DIR / "latest_simple_brain_v2.json"
S23_STATE_PATH = STATE_DIR / "s23_simple_brain_v2_state.json"
BRAIN_HISTORY_PATH = DATA_DIR / "simple_brain_v2_history.jsonl"
REPORT_PATH = REPORTS_DIR / "simple_brain_v2_latest_report.md"

ALLOWED_BRAIN_STATUS = {
    "READY",
    "RESEARCH_READY",
    "DEGRADED",
    "BLOCKED",
    "INSUFFICIENT_DATA",
}
ALLOWED_BRAIN_MODE = {
    "OBSERVER_MODE",
    "RESEARCH_MODE",
    "PAPER_ALERT_MODE",
    "SAMPLE_ACCUMULATION_MODE",
    "NO_TRADE_MODE",
}

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

CORE_INPUT_KEYS = {
    "flow_evidence",
    "setup_context",
    "decision_gate",
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


def load_all_inputs(
    paths: dict[str, Path] | None = None,
) -> dict[str, dict[str, Any] | None]:
    p = paths or {
        "flow_state": FLOW_STATE_PATH,
        "flow_evidence": FLOW_EVIDENCE_PATH,
        "flow_persistence": FLOW_PERSISTENCE_PATH,
        "setup_context": SETUP_CONTEXT_PATH,
        "scenario_trigger": SCENARIO_TRIGGER_PATH,
        "trade_plan": TRADE_PLAN_PATH,
        "decision_gate": DECISION_GATE_PATH,
        "telegram_alert": TELEGRAM_ALERT_PATH,
        "paper_lifecycle": PAPER_LIFECYCLE_PATH,
        "outcome_monitor": OUTCOME_MONITOR_PATH,
        "edge_matrix_v2": EDGE_MATRIX_V2_PATH,
    }
    return {k: _load_json(v) for k, v in p.items()}


def _resolve_symbol(inputs: dict[str, dict[str, Any] | None]) -> str:
    for key in (
        "flow_evidence",
        "setup_context",
        "scenario_trigger",
        "trade_plan",
        "decision_gate",
        "telegram_alert",
        "paper_lifecycle",
        "outcome_monitor",
        "edge_matrix_v2",
    ):
        d = inputs.get(key) or {}
        sym = d.get("symbol")
        if sym:
            return str(sym)
    return "UNKNOWN"


def _input_status(inputs: dict[str, dict[str, Any] | None]) -> tuple[str, list[str]]:
    present = [k for k, v in inputs.items() if v]
    missing = [k for k, v in inputs.items() if not v]
    missing_core = [k for k in CORE_INPUT_KEYS if not inputs.get(k)]
    if not present:
        return "MISSING", missing
    if missing_core:
        return "DEGRADED", missing
    if missing:
        return "PARTIAL", missing
    return "OK", missing


def _flow_summary(fs: dict[str, Any] | None, fe: dict[str, Any] | None) -> dict[str, Any]:
    if not fe and not fs:
        return {"available": False}
    out: dict[str, Any] = {"available": True}
    if fe:
        out.update({
            "evidence_label": fe.get("evidence_label"),
            "evidence_score": fe.get("evidence_score"),
            "confidence": fe.get("confidence"),
            "input_status": fe.get("input_status"),
        })
    if fs:
        out.update({
            "heartbeat_timestamp": fs.get("heartbeat_timestamp"),
            "quality_state": fs.get("quality_state"),
        })
    return out


def _persistence_summary(fp: dict[str, Any] | None) -> dict[str, Any]:
    if not fp:
        return {"available": False}
    return {
        "available": True,
        "persistence_label": fp.get("persistence_label"),
        "persistence_score": fp.get("persistence_score"),
        "direction_label": fp.get("direction_label"),
        "continuation_quality": fp.get("continuation_quality"),
        "decay_risk": fp.get("decay_risk"),
        "flip_risk": fp.get("flip_risk"),
    }


def _setup_context_summary(sc: dict[str, Any] | None) -> dict[str, Any]:
    if not sc:
        return {"available": False}
    return {
        "available": True,
        "setup_context_label": sc.get("setup_context_label"),
        "setup_context_score": sc.get("setup_context_score"),
        "direction_bias": sc.get("direction_bias"),
        "long_probability": sc.get("long_probability"),
        "short_probability": sc.get("short_probability"),
        "tradeable": sc.get("tradeable"),
        "confidence": sc.get("confidence"),
    }


def _scenario_summary(sc: dict[str, Any] | None) -> dict[str, Any]:
    if not sc:
        return {"available": False}
    return {
        "available": True,
        "scenario_label": sc.get("scenario_label"),
        "scenario_score": sc.get("scenario_score"),
        "direction_bias": sc.get("direction_bias"),
        "trigger_state": sc.get("trigger_state"),
        "trigger_strength": sc.get("trigger_strength"),
        "market_regime": sc.get("market_regime"),
        "ready_for_entry": sc.get("ready_for_entry"),
        "tradeable": sc.get("tradeable"),
    }


def _trade_plan_summary(tp: dict[str, Any] | None) -> dict[str, Any]:
    if not tp:
        return {"available": False}
    return {
        "available": True,
        "plan_status": tp.get("plan_status"),
        "side": tp.get("side"),
        "entry_price": tp.get("entry_price"),
        "stop_loss": tp.get("stop_loss"),
        "tp1": tp.get("tp1"),
        "tp2": tp.get("tp2"),
        "rr_tp1": tp.get("rr_tp1"),
        "rr_tp2": tp.get("rr_tp2"),
        "plan_grade": tp.get("plan_grade"),
        "plan_quality_score": tp.get("plan_quality_score"),
    }


def _decision_summary(dg: dict[str, Any] | None) -> dict[str, Any]:
    if not dg:
        return {"available": False}
    return {
        "available": True,
        "decision": dg.get("decision"),
        "decision_status": dg.get("decision_status"),
        "allowed_for_paper_alert": dg.get("allowed_for_paper_alert"),
        "allowed_for_paper_lifecycle": dg.get("allowed_for_paper_lifecycle"),
        "block_reasons": dg.get("block_reasons") or [],
        "warning_reasons": dg.get("warning_reasons") or [],
        "final_grade": dg.get("final_grade"),
        "decision_score": dg.get("decision_score"),
    }


def _lifecycle_summary(
    ta: dict[str, Any] | None, pl: dict[str, Any] | None
) -> dict[str, Any]:
    out: dict[str, Any] = {"available": bool(ta or pl)}
    if ta:
        out["telegram_alert"] = {
            "alert_status": ta.get("alert_status"),
            "telegram_mode": ta.get("telegram_mode"),
            "sent": ta.get("sent"),
            "dry_run": ta.get("dry_run"),
            "decision": ta.get("decision"),
        }
    if pl:
        out["paper_lifecycle"] = {
            "lifecycle_id": pl.get("lifecycle_id"),
            "lifecycle_status": pl.get("lifecycle_status"),
            "entry_touched": pl.get("entry_touched"),
            "tp1_hit": pl.get("tp1_hit"),
            "tp2_hit": pl.get("tp2_hit"),
            "stop_hit": pl.get("stop_hit"),
            "invalidated": pl.get("invalidated"),
            "unrealized_r": pl.get("unrealized_r"),
            "realized_r": pl.get("realized_r"),
        }
    return out


def _outcome_summary(om: dict[str, Any] | None) -> dict[str, Any]:
    if not om:
        return {"available": False}
    return {
        "available": True,
        "outcome_status": om.get("outcome_status"),
        "outcome_result": om.get("outcome_result"),
        "lifecycle_id": om.get("lifecycle_id"),
        "realized_r": om.get("realized_r"),
        "mfe_r": om.get("mfe_r"),
        "mae_r": om.get("mae_r"),
        "close_reason": om.get("close_reason"),
    }


def _edge_summary(em: dict[str, Any] | None) -> dict[str, Any]:
    if not em:
        return {"available": False}
    ss = em.get("sample_summary") or {}
    eq = em.get("edge_quality") or {}
    ov = em.get("overall_stats") or {}
    return {
        "available": True,
        "sample_status": ss.get("sample_status"),
        "total_records": ss.get("total_records"),
        "closed_records": ss.get("closed_records"),
        "usable_closed_records": ss.get("usable_closed_records"),
        "min_required_sample": ss.get("min_required_sample"),
        "edge_status": eq.get("edge_status"),
        "edge_score": eq.get("edge_score"),
        "confidence_level": eq.get("confidence_level"),
        "caution_reason": eq.get("caution_reason"),
        "win_rate": ov.get("win_rate"),
        "expectancy_r": ov.get("expectancy_r"),
    }


def _decide_brain_status(
    input_status: str,
    decision_summary: dict[str, Any],
    edge_summary: dict[str, Any],
) -> str:
    if input_status == "MISSING":
        return "INSUFFICIENT_DATA"
    if input_status == "DEGRADED":
        return "DEGRADED"
    decision = decision_summary.get("decision")
    if decision == "BLOCK":
        return "BLOCKED"
    edge_status = edge_summary.get("edge_status")
    if edge_status in {"NO_EDGE_CLAIM", "RESEARCH_ONLY"} or not edge_summary.get("available"):
        return "RESEARCH_READY"
    return "READY"


def _decide_brain_mode(
    brain_status: str,
    decision_summary: dict[str, Any],
    edge_summary: dict[str, Any],
    lifecycle_summary: dict[str, Any],
) -> str:
    if brain_status in {"INSUFFICIENT_DATA", "DEGRADED"}:
        return "OBSERVER_MODE"
    if brain_status == "BLOCKED":
        return "NO_TRADE_MODE"

    edge_status = edge_summary.get("edge_status")
    sample_status = edge_summary.get("sample_status")

    if edge_status in {"NO_EDGE_CLAIM", "RESEARCH_ONLY"}:
        if sample_status in {"EARLY_SAMPLE", "USABLE_SAMPLE"}:
            return "SAMPLE_ACCUMULATION_MODE"
        return "RESEARCH_MODE"

    decision = decision_summary.get("decision")
    ta = (lifecycle_summary or {}).get("telegram_alert") or {}
    if decision == "ALLOW_PAPER" and (ta.get("dry_run") or ta.get("sent") or ta.get("alert_status")):
        return "PAPER_ALERT_MODE"

    return "RESEARCH_MODE"


def _primary_reading(
    flow_summary: dict[str, Any],
    persistence_summary: dict[str, Any],
    setup_context_summary: dict[str, Any],
    scenario_summary: dict[str, Any],
) -> str:
    parts: list[str] = []
    if flow_summary.get("available"):
        parts.append(f"flow={flow_summary.get('evidence_label') or 'UNKNOWN'}")
    if persistence_summary.get("available"):
        parts.append(
            f"persistence={persistence_summary.get('persistence_label') or 'UNKNOWN'}"
            f"/{persistence_summary.get('direction_label') or 'UNKNOWN'}"
        )
    if setup_context_summary.get("available"):
        parts.append(
            f"setup={setup_context_summary.get('setup_context_label') or 'UNKNOWN'}"
            f" bias={setup_context_summary.get('direction_bias') or 'UNKNOWN'}"
        )
    if scenario_summary.get("available"):
        parts.append(
            f"scenario={scenario_summary.get('scenario_label') or 'UNKNOWN'}"
            f" trigger={scenario_summary.get('trigger_state') or 'UNKNOWN'}"
        )
    return "; ".join(parts) if parts else "NO_READING"


def _primary_risk(
    persistence_summary: dict[str, Any],
    scenario_summary: dict[str, Any],
    decision_summary: dict[str, Any],
    edge_summary: dict[str, Any],
) -> str:
    risks: list[str] = []
    if persistence_summary.get("decay_risk"):
        risks.append(f"DECAY={persistence_summary['decay_risk']}")
    if persistence_summary.get("flip_risk"):
        risks.append(f"FLIP={persistence_summary['flip_risk']}")
    if (scenario_summary.get("estimated_fakeout_probability") is not None):
        risks.append(f"FAKEOUT={scenario_summary['estimated_fakeout_probability']}")
    blocks = decision_summary.get("block_reasons") or []
    if blocks:
        risks.append(f"BLOCK_REASONS={len(blocks)}")
    warns = decision_summary.get("warning_reasons") or []
    if warns:
        risks.append(f"WARNINGS={len(warns)}")
    if edge_summary.get("edge_status") in {"NO_EDGE_CLAIM", "RESEARCH_ONLY"}:
        risks.append("NO_VALIDATED_EDGE")
    return "; ".join(risks) if risks else "NO_NOTABLE_RISK"


def _primary_next_action(
    brain_status: str,
    brain_mode: str,
    decision_summary: dict[str, Any],
    edge_summary: dict[str, Any],
) -> str:
    if brain_status == "INSUFFICIENT_DATA":
        return "WAIT_FOR_INPUTS: core state files missing; do not act."
    if brain_status == "DEGRADED":
        return "REPAIR_INPUTS: core inputs degraded; do not trust paper alert."
    if brain_status == "BLOCKED" or decision_summary.get("decision") == "BLOCK":
        reasons = decision_summary.get("block_reasons") or []
        rs = ", ".join(reasons[:3]) if reasons else "no plan/quality"
        return f"NO_TRADE: S18 decision is BLOCK ({rs}); ignore any paper alert."
    if edge_summary.get("edge_status") in {"NO_EDGE_CLAIM", "RESEARCH_ONLY"}:
        return (
            "OBSERVE_AND_ACCUMULATE: no validated edge yet; "
            "continue collecting paper samples for S22."
        )
    if brain_mode == "PAPER_ALERT_MODE":
        return (
            "PAPER_ALERT_ONLY: S18 allowed paper, S19 dry-run/sent; "
            "no real trade — paper-only research."
        )
    return "OBSERVE: no actionable readiness; continue research."


def _system_health(
    input_status: str,
    inputs: dict[str, dict[str, Any] | None],
    missing: list[str],
) -> dict[str, Any]:
    quality_levels: list[str] = []
    for v in inputs.values():
        if isinstance(v, dict):
            dq = v.get("data_quality")
            if isinstance(dq, dict) and dq.get("level"):
                quality_levels.append(str(dq["level"]))
    return {
        "input_status": input_status,
        "missing_inputs": missing,
        "present_inputs_count": sum(1 for v in inputs.values() if v),
        "total_inputs_expected": len(inputs),
        "downstream_quality_levels": quality_levels,
    }


def _data_quality(input_status: str, missing: list[str]) -> dict[str, Any]:
    if input_status == "MISSING":
        return {"score": 0.0, "level": "MISSING", "issues": ["ALL_INPUTS_MISSING"]}
    if input_status == "DEGRADED":
        return {
            "score": 0.3,
            "level": "LOW",
            "issues": [f"MISSING_CORE_{','.join(missing)}"],
        }
    if input_status == "PARTIAL":
        return {
            "score": 0.7,
            "level": "MEDIUM",
            "issues": [f"MISSING_{','.join(missing)}"],
        }
    return {"score": 1.0, "level": "HIGH", "issues": []}


def _limitations(
    input_status: str,
    edge_summary: dict[str, Any],
    decision_summary: dict[str, Any],
) -> list[str]:
    lim: list[str] = [
        "READ_ONLY_REPORT_LAYER",
        "NO_NEW_DECISION",
        "NO_TRADE_PLAN_CREATION",
        "NO_DECISION_GATE_OVERRIDE",
        "PAPER_ONLY",
    ]
    if input_status != "OK":
        lim.append(f"INPUT_STATUS_{input_status}")
    if not edge_summary.get("available"):
        lim.append("NO_EDGE_MATRIX_AVAILABLE")
    elif edge_summary.get("edge_status") in {"NO_EDGE_CLAIM", "RESEARCH_ONLY"}:
        lim.append("NO_VALIDATED_EDGE_CLAIM")
    if decision_summary.get("decision") == "BLOCK":
        lim.append("S18_DECISION_BLOCK")
    return lim


def build_brain_report(
    inputs: dict[str, dict[str, Any] | None],
    symbol: str | None = None,
    source: str = "S12-S22_CHAIN",
) -> dict[str, Any]:
    if symbol is None:
        symbol = _resolve_symbol(inputs)

    input_status, missing = _input_status(inputs)

    flow_summary = _flow_summary(inputs.get("flow_state"), inputs.get("flow_evidence"))
    persistence_summary = _persistence_summary(inputs.get("flow_persistence"))
    setup_context_summary = _setup_context_summary(inputs.get("setup_context"))
    scenario_summary = _scenario_summary(inputs.get("scenario_trigger"))
    trade_plan_summary = _trade_plan_summary(inputs.get("trade_plan"))
    decision_summary = _decision_summary(inputs.get("decision_gate"))
    lifecycle_summary = _lifecycle_summary(
        inputs.get("telegram_alert"), inputs.get("paper_lifecycle")
    )
    outcome_summary = _outcome_summary(inputs.get("outcome_monitor"))
    edge_summary = _edge_summary(inputs.get("edge_matrix_v2"))

    brain_status = _decide_brain_status(input_status, decision_summary, edge_summary)
    assert brain_status in ALLOWED_BRAIN_STATUS
    brain_mode = _decide_brain_mode(
        brain_status, decision_summary, edge_summary, lifecycle_summary
    )
    assert brain_mode in ALLOWED_BRAIN_MODE

    primary_reading = _primary_reading(
        flow_summary, persistence_summary, setup_context_summary, scenario_summary
    )
    primary_risk = _primary_risk(
        persistence_summary, scenario_summary, decision_summary, edge_summary
    )
    primary_next_action = _primary_next_action(
        brain_status, brain_mode, decision_summary, edge_summary
    )

    system_health = _system_health(input_status, inputs, missing)
    data_quality = _data_quality(input_status, missing)
    limitations = _limitations(input_status, edge_summary, decision_summary)

    reason_codes: list[str] = [
        f"SYMBOL_{symbol}",
        f"INPUT_STATUS_{input_status}",
        f"BRAIN_STATUS_{brain_status}",
        f"BRAIN_MODE_{brain_mode}",
        f"DQ_{data_quality['level']}",
        f"PRESENT_INPUTS_{system_health['present_inputs_count']}",
        f"EXPECTED_INPUTS_{system_health['total_inputs_expected']}",
        "READ_ONLY_AGGREGATION",
        "NO_NEW_DECISION",
        "NO_DECISION_GATE_OVERRIDE",
        "NO_TRADE_PLAN_CREATION",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
        "NO_TELEGRAM_SENDING",
        "PAPER_ONLY",
    ]
    if missing:
        reason_codes.append(f"MISSING_INPUTS_{','.join(missing)}")
    if decision_summary.get("decision"):
        reason_codes.append(f"S18_DECISION_{decision_summary['decision']}")
    if edge_summary.get("edge_status"):
        reason_codes.append(f"S22_EDGE_{edge_summary['edge_status']}")
    if edge_summary.get("sample_status"):
        reason_codes.append(f"S22_SAMPLE_{edge_summary['sample_status']}")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": source,
        "input_status": input_status,
        "market_flow_summary": flow_summary,
        "persistence_summary": persistence_summary,
        "setup_context_summary": setup_context_summary,
        "scenario_summary": scenario_summary,
        "trade_plan_summary": trade_plan_summary,
        "decision_summary": decision_summary,
        "lifecycle_summary": lifecycle_summary,
        "outcome_summary": outcome_summary,
        "edge_summary": edge_summary,
        "brain_status": brain_status,
        "brain_mode": brain_mode,
        "primary_reading": primary_reading,
        "primary_risk": primary_risk,
        "primary_next_action": primary_next_action,
        "system_health": system_health,
        "limitations": limitations,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def _write_report(r: dict[str, Any]) -> None:
    def _kv(d: dict[str, Any]) -> list[str]:
        return [f"- {k}: {v}" for k, v in d.items()]

    lines: list[str] = [
        "# S23 Simple Brain v2 — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Source:** {r['source']}",
        f"**Input Status:** {r['input_status']}",
        f"**Brain Status:** {r['brain_status']}",
        f"**Brain Mode:** {r['brain_mode']}",
        "",
        "## Current Flow",
        *_kv(r["market_flow_summary"]),
        "",
        "## Persistence",
        *_kv(r["persistence_summary"]),
        "",
        "## Setup Context",
        *_kv(r["setup_context_summary"]),
        "",
        "## Scenario",
        *_kv(r["scenario_summary"]),
        "",
        "## Trade Plan",
        *_kv(r["trade_plan_summary"]),
        "",
        "## Decision",
        *_kv(r["decision_summary"]),
        "",
        "## Lifecycle",
        *_kv(r["lifecycle_summary"]),
        "",
        "## Latest Outcome",
        *_kv(r["outcome_summary"]),
        "",
        "## Edge Status",
        *_kv(r["edge_summary"]),
        "",
        "## Brain Status",
        f"- brain_status: {r['brain_status']}",
        f"- brain_mode: {r['brain_mode']}",
        f"- primary_reading: {r['primary_reading']}",
        f"- primary_risk: {r['primary_risk']}",
        "",
        "## Brain Mode",
        f"- {r['brain_mode']}",
        "",
        "## Primary Next Action",
        f"- {r['primary_next_action']}",
        "",
        "## System Health",
        *_kv(r["system_health"]),
        "",
        "## Limitations",
        *(f"- {x}" for x in r["limitations"]),
        "",
        "## Data Quality",
        *_kv(r["data_quality"]),
        "",
        "## Safety Summary",
        f"- safe_to_open_real_trade: {r['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {r['execution_safety']['private_api_used']}",
        f"- live_order_sent: {r['execution_safety']['live_order_sent']}",
        "",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
    ]
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")


def run_simple_brain_v2() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    inputs = load_all_inputs()
    prior_state = _load_json(S23_STATE_PATH)
    report = build_brain_report(inputs)

    _atomic_write(LATEST_BRAIN_PATH, json.dumps(report, indent=2))

    state = {
        "timestamp_utc": report["timestamp_utc"],
        "block_id": "S23_SIMPLE_BRAIN_V2_STATE",
        "last_symbol": report["symbol"],
        "last_input_status": report["input_status"],
        "last_brain_status": report["brain_status"],
        "last_brain_mode": report["brain_mode"],
        "runs": int(((prior_state or {}).get("runs") or 0)) + 1,
    }
    _atomic_write(S23_STATE_PATH, json.dumps(state, indent=2))

    summary_record = {
        "timestamp_utc": report["timestamp_utc"],
        "block_id": BLOCK_ID,
        "symbol": report["symbol"],
        "input_status": report["input_status"],
        "brain_status": report["brain_status"],
        "brain_mode": report["brain_mode"],
        "primary_next_action": report["primary_next_action"],
        "reason_codes": report["reason_codes"],
        "execution_safety": report["execution_safety"],
    }
    BRAIN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BRAIN_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary_record) + "\n")

    _write_report(report)
    return report
