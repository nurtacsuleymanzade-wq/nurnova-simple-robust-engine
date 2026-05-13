from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "simple"
EPOCH = STATE / "epoch_v2"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _contains(path: Path, text: str) -> bool:
    try:
        return text in path.read_text(encoding="utf-8")
    except Exception:
        return False


def _opened(factory: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in factory.get("newest_opened_this_loop") or [] if str(item.get("status") or "").upper() == "OPEN"]


def _diagnostics(factory: dict[str, Any]) -> list[dict[str, Any]]:
    return list(factory.get("top_candidate_diagnostics") or [])


def _check(name: str, ok: bool, details: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "details": details}


def run_audit() -> dict[str, Any]:
    factory = _read_json(EPOCH / "latest_paper_trade_factory.json")
    survival = _read_json(EPOCH / "latest_model_survival_filter.json")
    accounting = _read_json(EPOCH / "latest_outcome_accounting.json")
    telegram = _read_json(EPOCH / "latest_telegram_report.json")
    lifecycle = _read_json(EPOCH / "latest_research_paper_lifecycle.json")

    opened = _opened(factory)
    diagnostics = _diagnostics(factory)
    open_event_ids = [str(item.get("event_id") or "") for item in [*opened, *(lifecycle.get("open_trades") or [])] if item.get("event_id")]
    bucket_dirs: dict[str, set[str]] = {}
    for item in [*opened, *(lifecycle.get("open_trades") or [])]:
        direction = str(item.get("direction") or "").upper()
        if direction in {"LONG", "SHORT"}:
            bucket_dirs.setdefault("|".join([str(item.get("symbol") or "UNKNOWN"), str(item.get("event_bucket_5m") or "UNKNOWN")]), set()).add(direction)

    suppressed = set((survival.get("summary") or {}).get("suppressed_models") or [])
    checks = [
        _check("paper_opens_only_a_or_a_plus", all(str(item.get("signal_grade") or "") in {"A", "A_PLUS"} for item in opened)),
        _check("b_c_d_do_not_open", all(str(item.get("status") or "").upper() != "OPEN" for item in diagnostics if str(item.get("signal_grade") or "") in {"B", "C", "D"})),
        _check("suppressed_models_cannot_open", all(str(item.get("model_id") or "") not in suppressed for item in opened)),
        _check("duplicate_events_blocked", len(open_event_ids) == len(set(open_event_ids))),
        _check("opposite_events_blocked", all(len(values) <= 1 for values in bucket_dirs.values())),
        _check("max_open_total_lte_6", int((lifecycle.get("summary") or {}).get("open") or len(lifecycle.get("open_trades") or [])) <= 6),
        _check("winrate_avg_r_from_outcome_accounting_only", _contains(ROOT / "src" / "simple" / "model_survival_filter.py", "ACCOUNTING_PATH") and accounting.get("accounting_status") in {"OK", None, ""}),
        _check("telegram_reads_epoch_ssot_only", "EPOCH_V2_SSOT" in str((telegram.get("source") or {}).get("source_mode") or "") and _contains(ROOT / "src" / "simple" / "telegram_research_reporter.py", "epoch_state_path")),
        _check("live_order_sent_false", factory.get("execution_safety", {}).get("live_order_sent") is False and telegram.get("execution_safety", {}).get("live_order_sent") is False),
        _check("private_api_used_false", factory.get("execution_safety", {}).get("private_api_used") is False and telegram.get("execution_safety", {}).get("private_api_used") is False),
    ]
    status = "EDGE_RESEARCH_MOTOR_READY" if all(item["ok"] for item in checks) else "EDGE_RESEARCH_MOTOR_NOT_READY"
    return {
        "status": status,
        "checks": checks,
        "summary": {
            "open_trades": int((lifecycle.get("summary") or {}).get("open") or len(lifecycle.get("open_trades") or [])),
            "factory_opened_this_loop": len(opened),
            "suppressed_models": sorted(suppressed),
        },
        "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
    }


def main() -> None:
    result = run_audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "EDGE_RESEARCH_MOTOR_READY":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
