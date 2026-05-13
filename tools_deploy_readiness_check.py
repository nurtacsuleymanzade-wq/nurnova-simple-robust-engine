from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

from src.simple.jsonl_tail_reader import safe_write_json_atomic

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state" / "simple"
OUTPUT_PATH = STATE_DIR / "latest_deploy_readiness.json"

REQUIRED_GITIGNORE_RULES = [
    "*.log",
    "live.log",
    "telegram_summary.log",
    "pipeline_direct_debug.log",
    "runtime_topology_report.json",
    "archive/",
    "state/simple/runtime_loop.lock",
    "state/simple/telegram_reported_trades.json",
    "state/simple/latest_pipeline_failure.json",
]
RUNTIME_ARTIFACTS = [
    "live.log",
    "runtime_topology_report.json",
    "telegram_summary.log",
    "pipeline_direct_debug.log",
    "state/simple/runtime_loop.lock",
    "state/simple/telegram_reported_trades.json",
    "state/simple/latest_pipeline_failure.json",
]
MODULES_TO_IMPORT = [
    "src.simple.jsonl_tail_reader",
    "src.simple.research_paper_lifecycle_engine",
    "src.simple.research_edge_matrix_engine",
    "src.simple.paper_trade_factory",
    "src.simple.telegram_research_reporter",
]


def _git_output(*args: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20)
    except Exception as exc:
        return False, str(exc)
    return result.returncode == 0, result.stdout.strip() or result.stderr.strip()


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _file_size_check(path: Path, threshold_bytes: int) -> dict:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    return {
        "exists": exists,
        "size_bytes": size,
        "threshold_bytes": threshold_bytes,
        "ok": exists and size <= threshold_bytes,
    }


def run() -> dict:
    checks: dict[str, object] = {}
    blocking_issues: list[str] = []
    warnings: list[str] = []

    gitignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    missing_rules = [rule for rule in REQUIRED_GITIGNORE_RULES if rule not in gitignore_text]
    checks["gitignore_rules_present"] = {"ok": not missing_rules, "missing_rules": missing_rules}
    if missing_rules:
        blocking_issues.append("MISSING_GITIGNORE_RULES")

    ok, tracked_output = _git_output("ls-files", *RUNTIME_ARTIFACTS)
    tracked_runtime_artifacts = [line.strip() for line in tracked_output.splitlines() if line.strip()] if ok else []
    checks["tracked_runtime_artifacts"] = {"ok": ok and not tracked_runtime_artifacts, "tracked": tracked_runtime_artifacts}
    if not ok:
        warnings.append("GIT_TRACKING_CHECK_FAILED")
    elif tracked_runtime_artifacts:
        blocking_issues.append("RUNTIME_ARTIFACTS_STILL_TRACKED")

    lifecycle_check = _file_size_check(STATE_DIR / "latest_research_paper_lifecycle.json", 500_000)
    paper_factory_check = _file_size_check(STATE_DIR / "latest_paper_trade_factory.json", 500_000)
    telegram_check = _file_size_check(STATE_DIR / "latest_telegram_report.json", 300_000)
    checks["lifecycle_latest_size"] = lifecycle_check
    checks["paper_factory_latest_size"] = paper_factory_check
    checks["telegram_latest_size"] = telegram_check
    for name, check in (
        ("LIFECYCLE_FILE_TOO_LARGE", lifecycle_check),
        ("PAPER_FACTORY_FILE_TOO_LARGE", paper_factory_check),
        ("TELEGRAM_REPORT_FILE_TOO_LARGE", telegram_check),
    ):
        if not check["ok"]:
            blocking_issues.append(name)

    topology = _load_json(ROOT / "runtime_topology_report.json")
    checks["duplicate_guard"] = {
        "ok": topology.get("duplicate_loop_detected") is False,
        "duplicate_loop_detected": topology.get("duplicate_loop_detected"),
        "duplicate_processes": topology.get("duplicate_processes") or [],
    }
    if topology and topology.get("duplicate_loop_detected") is True:
        blocking_issues.append("DUPLICATE_GUARD_REGRESSION")

    safety_sources = [
        _load_json(STATE_DIR / "latest_live_eligibility_gate.json"),
        _load_json(STATE_DIR / "latest_research_paper_lifecycle.json"),
        _load_json(STATE_DIR / "latest_paper_trade_factory.json"),
        _load_json(STATE_DIR / "latest_telegram_report.json"),
    ]
    live_order_sent = any(
        bool(source.get("live_order_sent"))
        or bool((source.get("execution_safety") or {}).get("live_order_sent"))
        for source in safety_sources
    )
    private_api_used = any(
        bool(source.get("private_api_used"))
        or bool((source.get("execution_safety") or {}).get("private_api_used"))
        for source in safety_sources
    )
    checks["execution_safety"] = {
        "ok": not live_order_sent and not private_api_used,
        "live_order_sent": live_order_sent,
        "private_api_used": private_api_used,
    }
    if live_order_sent:
        blocking_issues.append("LIVE_ORDER_SENT_TRUE")
    if private_api_used:
        blocking_issues.append("PRIVATE_API_USED_TRUE")

    import_results: dict[str, bool] = {}
    for module_name in MODULES_TO_IMPORT:
        try:
            importlib.import_module(module_name)
            import_results[module_name] = True
        except Exception:
            import_results[module_name] = False
            blocking_issues.append(f"IMPORT_FAILED:{module_name}")
    checks["module_imports"] = import_results

    pipeline = _load_json(STATE_DIR / "latest_local_pipeline_run.json")
    pipeline_status = ((pipeline.get("execution_summary") or {}).get("pipeline_status"))
    checks["pipeline_status_complete"] = {"ok": pipeline_status == "COMPLETE", "pipeline_status": pipeline_status}
    if pipeline_status != "COMPLETE":
        warnings.append("PIPELINE_STATUS_NOT_COMPLETE")

    status = "READY" if not blocking_issues else "NOT_READY"
    payload = {
        "status": status,
        "checks": checks,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "safe_for_vps_observation": status == "READY",
    }
    safe_write_json_atomic(OUTPUT_PATH, payload)
    return payload


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
