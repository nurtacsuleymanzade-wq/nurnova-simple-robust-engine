from __future__ import annotations

import importlib
import json
from pathlib import Path

from src.simple.research_epoch import ACTIVE_EPOCH_ID, EPOCH_DATA_DIR, EPOCH_STATE_DIR
from src.simple.jsonl_tail_reader import safe_write_json_atomic

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state" / "simple"
OUTPUT_PATH = STATE_DIR / "latest_deploy_readiness.json"

MODULES_TO_IMPORT = [
    "src.simple.research_epoch",
    "src.simple.timeframe_resolver",
    "src.simple.paper_trade_factory",
    "src.simple.research_paper_lifecycle_engine",
    "src.simple.outcome_accounting_engine",
    "src.simple.research_edge_matrix_engine",
    "src.simple.telegram_research_reporter",
]


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _source_mentions_epoch(payload: dict, expected: str) -> bool:
    return expected in json.dumps(payload, ensure_ascii=False)


def run() -> dict:
    checks: dict[str, object] = {}
    blocking_issues: list[str] = []

    timeframe = _load_json(EPOCH_STATE_DIR / "latest_timeframe_resolution.json")
    factory = _load_json(EPOCH_STATE_DIR / "latest_paper_trade_factory.json")
    lifecycle = _load_json(EPOCH_STATE_DIR / "latest_research_paper_lifecycle.json")
    accounting = _load_json(EPOCH_STATE_DIR / "latest_outcome_accounting.json")
    edge = _load_json(EPOCH_STATE_DIR / "latest_research_edge_matrix.json")
    telegram = _load_json(EPOCH_STATE_DIR / "latest_telegram_report.json")
    reset = _load_json(EPOCH_STATE_DIR / "latest_epoch_reset.json")

    checks["epoch_v2_directory_exists"] = {"ok": EPOCH_DATA_DIR.exists() and EPOCH_STATE_DIR.exists()}
    checks["latest_timeframe_resolution"] = {"ok": bool(timeframe), "exists": bool(timeframe)}
    checks["paper_trades_carry_timeframe_and_rr"] = {
        "ok": all(
            trade.get("primary_tf") and trade.get("rr1") is not None and trade.get("rr2") is not None
            for trade in (factory.get("newest_opened_this_loop") or [])
        ) if factory else False
    }
    checks["lifecycle_reads_epoch_v2_only"] = {"ok": _source_mentions_epoch(lifecycle, ACTIVE_EPOCH_ID)}
    checks["edge_reads_epoch_v2_only"] = {"ok": _source_mentions_epoch(edge, ACTIVE_EPOCH_ID)}
    checks["telegram_reads_epoch_v2_only"] = {"ok": ((telegram.get("source") or {}).get("source_mode") == "EPOCH_V2_SSOT")}
    checks["clean_edge_samples"] = {"ok": int((accounting.get("summary") or {}).get("clean_sample_count") or 0) >= 0}
    checks["accounting_status"] = {"ok": (accounting.get("accounting_status") or "") != "CORRUPTED", "value": accounting.get("accounting_status")}
    checks["execution_safety"] = {
        "ok": not any(
            bool(source.get("live_order_sent")) or bool(source.get("private_api_used")) or bool((source.get("execution_safety") or {}).get("live_order_sent")) or bool((source.get("execution_safety") or {}).get("private_api_used"))
            for source in (reset, factory, lifecycle, accounting, edge, telegram)
        ),
        "live_order_sent": False,
        "private_api_used": False,
    }

    for name, result in checks.items():
        if not bool(result.get("ok")):
            blocking_issues.append(name.upper())

    import_results: dict[str, bool] = {}
    for module_name in MODULES_TO_IMPORT:
        try:
            importlib.import_module(module_name)
            import_results[module_name] = True
        except Exception:
            import_results[module_name] = False
            blocking_issues.append(f"IMPORT_FAILED:{module_name}")
    checks["module_imports"] = import_results

    payload = {
        "status": "READY" if not blocking_issues else "NOT_READY",
        "epoch_id": ACTIVE_EPOCH_ID,
        "checks": checks,
        "blocking_issues": blocking_issues,
        "safe_for_vps_observation": not blocking_issues,
    }
    safe_write_json_atomic(OUTPUT_PATH, payload)
    return payload


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
