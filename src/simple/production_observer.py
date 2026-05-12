"""S24 — Production Observer. 24/7 VPS systemd-ready cycle loop for S12-S23.

Paper-only. No private API. No real orders. No live trading.
safe_to_open_real_trade always False.
"""

from __future__ import annotations

import importlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S24_VPS_SYSTEMD_24_7_PRODUCTION_OBSERVER"
FEEDS_NEXT = {"next_blocks": ["SIMPLE_ROBUST_ENGINE_V1_COMPLETE"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")
LOGS_DIR = Path("logs/simple")

LATEST_STATE_PATH = STATE_DIR / "latest_production_observer.json"
S24_STATE_PATH = STATE_DIR / "s24_production_observer_state.json"
HISTORY_PATH = DATA_DIR / "production_observer_history.jsonl"
LOG_PATH = LOGS_DIR / "production_observer.log"
REPORT_PATH = REPORTS_DIR / "s24_production_observer_latest_report.md"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

# (module_path, function_name, label)
_MODULE_CHAIN: list[tuple[str, str, str]] = [
    ("src.simple.run_s12_flow_collector",         "main",                             "S12_FLOW_STATE"),
    ("src.simple.flow_evidence_engine",           "run_flow_evidence_engine",          "S13_FLOW_EVIDENCE"),
    ("src.simple.flow_persistence_engine",        "run_flow_persistence_engine",       "S14_FLOW_PERSISTENCE"),
    ("src.simple.flow_to_setup_context_engine",   "run_flow_to_setup_context_engine",  "S15_SETUP_CONTEXT"),
    ("src.simple.scenario_entry_trigger_engine",  "run_scenario_entry_trigger_engine", "S16_SCENARIO_ENTRY"),
    ("src.simple.trade_plan_engine",              "run_trade_plan_engine",             "S17_TRADE_PLAN"),
    ("src.simple.decision_gate_engine",           "run_decision_gate_engine",          "S18_DECISION_GATE"),
    ("src.simple.telegram_paper_alert_engine",    "run_telegram_paper_alert_engine",   "S19_TELEGRAM_ALERT"),
    ("src.simple.paper_lifecycle_tracker",        "run_paper_lifecycle_tracker",       "S20_PAPER_LIFECYCLE"),
    ("src.simple.outcome_monitor",                "run_outcome_monitor",               "S21_OUTCOME_MONITOR"),
    ("src.simple.telegram_followup_notifier",     "run_telegram_followup_notifier",    "S25_TELEGRAM_FOLLOWUP"),
    ("src.simple.explainability_engine",          "run_explainability_engine",          "S26_EXPLAINABILITY"),
    ("src.simple.full_chain_truth_audit",         "run_full_chain_truth_audit",         "S26A_FULL_CHAIN_TRUTH_AUDIT"),
    ("src.simple.live_flow_quality_audit",        "run_live_flow_quality_audit",        "S26B_LIVE_FLOW_QUALITY_AUDIT"),
    ("src.simple.depth_liquidity_memory",         "run_depth_liquidity_memory",         "S27_DEPTH_LIQUIDITY_MEMORY"),
    ("src.simple.market_structure_v2",            "run_market_structure_v2",            "S28_MARKET_STRUCTURE_V2"),
    ("src.simple.setup_classifier_v2",            "run_setup_classifier_v2",            "S29_SETUP_CLASSIFIER_V2"),
    ("src.simple.edge_matrix_v2",                 "run_edge_matrix_v2",                "S22_EDGE_MATRIX_V2"),
    ("src.simple.sample_accumulation_edge_review","run_sample_accumulation_edge_review","S30_SAMPLE_ACCUMULATION_EDGE_REVIEW"),
    ("src.simple.simple_brain_v2",                "run_simple_brain_v2",               "S23_SIMPLE_BRAIN_V2"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = _utc_now()
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        pass
    print(message)


def _run_module(module_path: str, func_name: str, label: str, dry_run_alerts: bool) -> tuple[str, dict[str, Any] | None, str | None]:
    """Run one module. Returns (label, result_or_None, error_or_None)."""
    try:
        mod = importlib.import_module(module_path)
        fn = getattr(mod, func_name)
        if label == "S19_TELEGRAM_ALERT":
            result = fn(mode="DRY_RUN" if dry_run_alerts else "SEND")
        else:
            result = fn()
        return label, result, None
    except Exception as exc:
        return label, None, str(exc)


def run_one_cycle(
    cycle_count: int,
    dry_run_alerts: bool = True,
) -> dict[str, Any]:
    """Run one full S12-S23 cycle. Never raises."""
    cycle_start = _utc_now()
    t0 = time.monotonic()

    modules_run: list[str] = []
    modules_failed: list[dict[str, str]] = []
    reason_codes: list[str] = [
        "PRODUCTION_OBSERVER_CYCLE",
        f"CYCLE_{cycle_count}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_LIVE_ORDERS",
        "PAPER_ONLY",
    ]

    brain_result: dict[str, Any] | None = None

    for module_path, func_name, label in _MODULE_CHAIN:
        lbl, result, err = _run_module(module_path, func_name, label, dry_run_alerts)
        if err is not None:
            modules_failed.append({"module": lbl, "error": err})
            reason_codes.append(f"MODULE_FAILED_{lbl}")
            _log(f"[S24] cycle={cycle_count} MODULE_FAILED label={lbl} err={err}")
        else:
            modules_run.append(lbl)
            if lbl == "S23_SIMPLE_BRAIN_V2" and result:
                brain_result = result

    cycle_end = _utc_now()
    duration = round(time.monotonic() - t0, 2)

    brain_status = "UNKNOWN"
    brain_mode = "UNKNOWN"
    latest_decision = "UNKNOWN"
    latest_alert_status = "UNKNOWN"
    latest_edge_status = "UNKNOWN"
    data_quality: dict[str, Any] = {"level": "UNKNOWN", "score": 0.0}

    if brain_result:
        brain_status = brain_result.get("brain_status", "UNKNOWN")
        brain_mode = brain_result.get("brain_mode", "UNKNOWN")
        data_quality = brain_result.get("data_quality", data_quality)
        primary = brain_result.get("primary_reading") or {}
        latest_decision = primary.get("decision", "UNKNOWN") if isinstance(primary, dict) else "UNKNOWN"
        alert = brain_result.get("alert_summary") or {}
        latest_alert_status = alert.get("alert_status", "UNKNOWN") if isinstance(alert, dict) else "UNKNOWN"
        edge = brain_result.get("edge_summary") or {}
        latest_edge_status = edge.get("edge_status", "UNKNOWN") if isinstance(edge, dict) else "UNKNOWN"

    observer_status = "OK" if not modules_failed else ("DEGRADED" if modules_run else "CRITICAL")
    loop_status = "RUNNING"

    record: dict[str, Any] = {
        "timestamp_utc": cycle_end,
        "block_id": BLOCK_ID,
        "symbol": "BTCUSDT",
        "observer_status": observer_status,
        "loop_status": loop_status,
        "cycle_count": cycle_count,
        "last_cycle_started_utc": cycle_start,
        "last_cycle_finished_utc": cycle_end,
        "last_cycle_duration_seconds": duration,
        "modules_run": modules_run,
        "modules_failed": modules_failed,
        "latest_brain_status": brain_status,
        "latest_brain_mode": brain_mode,
        "latest_decision": latest_decision,
        "latest_alert_status": latest_alert_status,
        "latest_edge_status": latest_edge_status,
        "systemd_ready": True,
        "restart_safe": True,
        "disk_safety": True,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "execution_safety": dict(SAFETY),
        "feeds_next": FEEDS_NEXT,
    }

    return record


def _write_report(record: dict[str, Any]) -> None:
    lines = [
        f"# S24 Production Observer — Cycle Report",
        f"",
        f"- **timestamp_utc**: {record['timestamp_utc']}",
        f"- **block_id**: {record['block_id']}",
        f"- **cycle_count**: {record['cycle_count']}",
        f"- **observer_status**: {record['observer_status']}",
        f"- **loop_status**: {record['loop_status']}",
        f"- **last_cycle_started_utc**: {record['last_cycle_started_utc']}",
        f"- **last_cycle_finished_utc**: {record['last_cycle_finished_utc']}",
        f"- **last_cycle_duration_seconds**: {record['last_cycle_duration_seconds']}",
        f"- **modules_run**: {len(record['modules_run'])}",
        f"- **modules_failed**: {len(record['modules_failed'])}",
        f"- **latest_brain_status**: {record['latest_brain_status']}",
        f"- **latest_brain_mode**: {record['latest_brain_mode']}",
        f"- **latest_decision**: {record['latest_decision']}",
        f"- **latest_alert_status**: {record['latest_alert_status']}",
        f"- **latest_edge_status**: {record['latest_edge_status']}",
        f"- **systemd_ready**: {record['systemd_ready']}",
        f"- **restart_safe**: {record['restart_safe']}",
        f"- **safe_to_open_real_trade**: {record['execution_safety']['safe_to_open_real_trade']}",
        f"- **private_api_used**: {record['execution_safety']['private_api_used']}",
        f"- **live_order_sent**: {record['execution_safety']['live_order_sent']}",
        f"",
        f"## Modules Run",
        "",
    ]
    for m in record["modules_run"]:
        lines.append(f"- {m}")
    lines.append("")
    lines.append("## Modules Failed")
    lines.append("")
    if record["modules_failed"]:
        for f in record["modules_failed"]:
            lines.append(f"- {f['module']}: {f['error']}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Reason Codes")
    lines.append("")
    for rc in record["reason_codes"]:
        lines.append(f"- {rc}")
    lines.append("")
    _atomic_write(REPORT_PATH, "\n".join(lines))


def run_observer_loop(
    interval_seconds: int = 60,
    dry_run_alerts: bool = True,
    max_cycles: int | None = None,
) -> None:
    """Main observer loop. Runs indefinitely or for max_cycles if specified."""
    cycle_count = 0
    _log(f"[S24] Production Observer starting — interval={interval_seconds}s dry_run={dry_run_alerts} max_cycles={max_cycles}")

    while True:
        cycle_count += 1
        _log(f"[S24] cycle={cycle_count} starting")

        record = run_one_cycle(cycle_count=cycle_count, dry_run_alerts=dry_run_alerts)

        # Write heartbeat / latest state
        _atomic_write(LATEST_STATE_PATH, json.dumps(record, indent=2, ensure_ascii=False))
        _atomic_write(S24_STATE_PATH, json.dumps(record, indent=2, ensure_ascii=False))

        # Append history
        _append_jsonl(HISTORY_PATH, record)

        # Write human-readable report
        _write_report(record)

        _log(
            f"[S24] cycle={cycle_count} status={record['observer_status']} "
            f"run={len(record['modules_run'])} failed={len(record['modules_failed'])} "
            f"duration={record['last_cycle_duration_seconds']}s"
        )

        if max_cycles is not None and cycle_count >= max_cycles:
            _log(f"[S24] Reached max_cycles={max_cycles}, stopping.")
            break

        time.sleep(interval_seconds)
