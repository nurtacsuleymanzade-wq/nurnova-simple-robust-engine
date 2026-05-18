#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE_DIR = BASE / "state" / "live_pipeline"
DATA_DIR = BASE / "data" / "live"
REPORT_DIR = BASE / "reports" / "live_pipeline"
LOG_DIR = BASE / "logs"

for p in [STATE_DIR, DATA_DIR, REPORT_DIR, LOG_DIR]:
    p.mkdir(parents=True, exist_ok=True)

PHASES = [
    ("market_state", "src.market_state.run_market_state_engine"),
    ("active_scenario", "src.active_scenario.run_active_scenario_engine"),
    ("flow_reaction", "src.flow_reaction.run_flow_reaction_engine"),
    ("setup_entry", "src.setup_entry.run_setup_entry_engine"),
    ("trade_decision", "src.trade_decision.run_trade_decision_engine"),
    ("paper_outcome", "src.paper_outcome.run_paper_outcome_engine"),
    ("edge_matrix", "src.edge_matrix.run_conditional_edge_matrix"),
    ("replay_engine", "src.replay_engine.run_replay_engine"),
    ("nova_brain", "src.nova_brain.run_nova_brain_snapshot"),
    ("probabilistic_engine", "src.probabilistic_engine.run_probabilistic_engine"),
    ("perspective_merger", "src.perspective_merger.run_perspective_merger"),
    ("autonomy_audit", "src.autonomy_audit.run_autonomy_audit"),
]

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

def append_jsonl(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

def run_module(module_name, timeout=60):
    started = utc_now()
    cmd = [sys.executable, "-m", module_name]
    try:
        p = subprocess.run(
            cmd,
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "module": module_name,
            "returncode": p.returncode,
            "ok": p.returncode == 0,
            "stdout_tail": (p.stdout or "")[-4000:],
            "stderr_tail": (p.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired as e:
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "module": module_name,
            "returncode": 124,
            "ok": False,
            "stdout_tail": (e.stdout or "")[-4000:] if isinstance(e.stdout, str) else "",
            "stderr_tail": (e.stderr or "")[-4000:] if isinstance(e.stderr, str) else "TIMEOUT",
        }
    except Exception as e:
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "module": module_name,
            "returncode": 1,
            "ok": False,
            "stdout_tail": "",
            "stderr_tail": repr(e),
        }

def run_cycle(cycle_no, timeout):
    cycle_started = utc_now()
    phase_results = []
    for phase_name, module_name in PHASES:
        result = run_module(module_name, timeout=timeout)
        result["phase_name"] = phase_name
        phase_results.append(result)

    failed = [r for r in phase_results if not r["ok"]]
    status = "OK" if not failed else "DEGRADED"

    payload = {
        "timestamp_utc": utc_now(),
        "block_id": "LIVE_PIPELINE_ORCHESTRATOR",
        "cycle_no": cycle_no,
        "cycle_started_at": cycle_started,
        "cycle_finished_at": utc_now(),
        "pipeline_status": status,
        "phase_count": len(PHASES),
        "failed_phase_count": len(failed),
        "failed_phases": [r["phase_name"] for r in failed],
        "phase_results": phase_results,
        "feeds_next": ["SYSTEMD_24_7_RUNTIME"],
        "reason_codes": [] if not failed else ["ONE_OR_MORE_PHASES_FAILED"],
    }

    write_json(STATE_DIR / "latest_live_pipeline.json", payload)
    append_jsonl(DATA_DIR / "live_pipeline_events.jsonl", payload)

    report = [
        "# Live Pipeline Latest Report",
        f"- timestamp_utc: {payload['timestamp_utc']}",
        f"- pipeline_status: {payload['pipeline_status']}",
        f"- cycle_no: {payload['cycle_no']}",
        f"- failed_phase_count: {payload['failed_phase_count']}",
        f"- failed_phases: {payload['failed_phases']}",
        "",
        "## Phase Summary",
    ]
    for r in phase_results:
        report.append(f"- {r['phase_name']}: {'PASS' if r['ok'] else 'FAIL'} rc={r['returncode']}")
    (REPORT_DIR / "live_pipeline_latest_report.md").write_text("\n".join(report), encoding="utf-8")

    print(json.dumps({
        "cycle_no": cycle_no,
        "pipeline_status": status,
        "failed_phases": payload["failed_phases"],
        "state": str(STATE_DIR / "latest_live_pipeline.json"),
        "report": str(REPORT_DIR / "live_pipeline_latest_report.md"),
    }, ensure_ascii=False))

    return payload

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval-seconds", type=int, default=60)
    ap.add_argument("--phase-timeout-seconds", type=int, default=60)
    ap.add_argument("--cycles", type=int, default=1)
    args = ap.parse_args()

    cycle_no = 0
    while True:
        cycle_no += 1
        run_cycle(cycle_no, args.phase_timeout_seconds)

        if not args.loop:
            break
        if args.cycles and cycle_no >= args.cycles:
            break
        time.sleep(args.interval_seconds)

if __name__ == "__main__":
    main()
