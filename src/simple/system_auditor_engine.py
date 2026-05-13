from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, history_tail, load_json, stamp_payload, write_json

BLOCK_ID = "SYSTEM_AUDITOR_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
OUTPUT_PATH = STATE_DIR / "latest_system_audit.json"

SYNC_PATH = STATE_DIR / "latest_context_sync.json"
PAPER_FACTORY_PATH = epoch_state_path("latest_paper_trade_factory.json")
LIFECYCLE_PATH = epoch_state_path("latest_research_paper_lifecycle.json")
ACCOUNTING_PATH = epoch_state_path("latest_outcome_accounting.json")
EDGE_PATH = epoch_state_path("latest_research_edge_matrix.json")
LIVE_GATE_PATH = STATE_DIR / "latest_live_eligibility_gate.json"

REQUIRED_STATE_FILES = {
    "latest_runtime_context.json": STATE_DIR / "latest_runtime_context.json",
    "latest_context_sync.json": SYNC_PATH,
    "latest_observation_factory.json": STATE_DIR / "latest_observation_factory.json",
    "latest_mtf_candle_dna.json": STATE_DIR / "latest_mtf_candle_dna.json",
    "latest_unified_context.json": STATE_DIR / "latest_unified_context.json",
    "latest_setup_family_activation.json": STATE_DIR / "latest_setup_family_activation.json",
    "latest_paper_trade_factory.json": PAPER_FACTORY_PATH,
    "latest_research_paper_lifecycle.json": LIFECYCLE_PATH,
    "latest_outcome_accounting.json": ACCOUNTING_PATH,
    "latest_research_edge_matrix.json": EDGE_PATH,
    "latest_model_feedback.json": STATE_DIR / "latest_model_feedback.json",
    "latest_model_promotion.json": STATE_DIR / "latest_model_promotion.json",
    "latest_live_eligibility_gate.json": LIVE_GATE_PATH,
    "latest_system_query_state.json": STATE_DIR / "latest_system_query_state.json",
}


def _read_json(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return {}, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, True
    return (payload if isinstance(payload, dict) else {}), False


def _history_file_size_risk() -> list[str]:
    warnings: list[str] = []
    for path in DATA_DIR.glob("*.jsonl"):
        try:
            if path.stat().st_size > 10_000_000:
                warnings.append(f"HISTORY_FILE_SIZE_RISK:{path.name}")
        except Exception:
            continue
    return warnings


def _paper_direction_conflicts(open_trades: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, set[str]] = {}
    issues: list[str] = []
    for trade in open_trades:
        key = "|".join(
            [
                str(trade.get("symbol") or "UNKNOWN"),
                str(trade.get("context_id") or "UNKNOWN"),
                str(trade.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY"),
                str(trade.get("liquidity_event") or "UNKNOWN"),
            ]
        )
        direction = str(trade.get("direction") or "UNKNOWN").upper()
        seen.setdefault(key, set()).add(direction)
    for key, directions in seen.items():
        if "LONG" in directions and "SHORT" in directions:
            issues.append(f"PAPER_DIRECTION_CONFLICT:{key}")
    return issues


def run_system_auditor_engine() -> dict[str, Any]:
    context = current_runtime_context()
    sync = load_json(SYNC_PATH) or {}
    paper_factory = load_json(PAPER_FACTORY_PATH) or {}
    lifecycle = load_json(LIFECYCLE_PATH) or {}
    accounting = load_json(ACCOUNTING_PATH) or {}
    edge = load_json(EDGE_PATH) or {}
    live_gate = load_json(LIVE_GATE_PATH) or {}

    critical_issues: list[str] = []
    warnings: list[str] = []
    self_healing_actions_taken: list[str] = []
    recommended_next_actions: list[str] = []

    missing_state_files: list[str] = []
    stale_state_files: list[str] = []
    json_corruption: list[str] = []
    for name, path in REQUIRED_STATE_FILES.items():
        payload, corrupted = _read_json(path)
        if not path.exists():
            missing_state_files.append(name)
            continue
        if corrupted:
            json_corruption.append(name)
            quarantine_path = path.with_suffix(path.suffix + ".corrupt")
            try:
                if not quarantine_path.exists():
                    path.replace(quarantine_path)
                    self_healing_actions_taken.append(f"QUARANTINED_CORRUPTED_JSON:{name}")
            except Exception:
                pass
            continue
        if sync and name in {path.name for block_id, path in []}:
            pass
        if payload and payload.get("context_id") not in {None, context.get("context_id")} and name != "latest_system_query_state.json":
            stale_state_files.append(name)

    if not sync.get("active_chain_ok"):
        critical_issues.append("ACTIVE_CHAIN_NOT_OK")
    if sync.get("sync_status") == "SYNC_BROKEN":
        critical_issues.append("CONTEXT_SYNC_BROKEN")
    elif sync.get("sync_status") == "SYNC_DEGRADED":
        warnings.append("CONTEXT_SYNC_DEGRADED")

    if missing_state_files:
        critical_issues.extend(f"MISSING_STATE_FILE:{name}" for name in missing_state_files if name != "latest_system_query_state.json")
    if stale_state_files:
        warnings.extend(f"STALE_STATE_FILE:{name}" for name in stale_state_files)
    if json_corruption:
        critical_issues.extend(f"JSON_CORRUPTION:{name}" for name in json_corruption)

    open_trades = list(lifecycle.get("open_trades") or [])
    closed_trades = list(lifecycle.get("closed_trades") or [])
    direction_conflicts = _paper_direction_conflicts(open_trades)
    if direction_conflicts:
        critical_issues.extend(direction_conflicts)

    lineage_missing_open = [
        trade.get("paper_trade_id")
        for trade in open_trades
        if not trade.get("context_id") or not trade.get("model_id")
    ]
    lineage_missing_closed = [
        trade.get("paper_trade_id")
        for trade in closed_trades
        if not trade.get("context_id") or not trade.get("model_id")
    ]
    if lineage_missing_open:
        critical_issues.append("LINEAGE_MISSING_OPEN_TRADE")
    elif lineage_missing_closed:
        warnings.append("LINEAGE_MISSING_HISTORICAL_CLOSED_TRADE")
    if any(not trade.get("context_id") for trade in open_trades):
        critical_issues.append("PAPER_WITHOUT_CONTEXT")
    if any(trade.get("outcome_status") == "CLOSED" and not trade.get("r_result") and trade.get("close_reason") != "PRICE_MISSING" for trade in closed_trades):
        warnings.append("CLOSED_WITHOUT_OUTCOME")

    clean_samples = int((accounting.get("summary") or {}).get("clean_sample_count") or 0)
    if edge.get("groups") and clean_samples == 0:
        critical_issues.append("EDGE_WITHOUT_CLEAN_SAMPLE")
    if any((group.get("sample_size") or 0) < 20 and group.get("edge_status") not in {"SAMPLE_BUILDING"} for group in (edge.get("groups") or [])):
        critical_issues.append("EDGE_OVERCLAIM")

    paper_safety = paper_factory.get("paper_safety") or {}
    if paper_safety.get("contradiction_guard_enabled") is not True:
        critical_issues.append("PAPER_DIRECTION_CONFLICT_GUARD_DISABLED")

    if live_gate.get("live_enabled") is True or live_gate.get("live_order_sent") is True:
        critical_issues.append("LIVE_SAFETY_VIOLATION")
    if live_gate.get("private_api_used") is True:
        critical_issues.append("PRIVATE_API_VIOLATION")

    warnings.extend(_history_file_size_risk())
    if history_tail(epoch_data_path("research_paper_lifecycle_history.jsonl"), max_lines=5) == []:
        warnings.append("HISTORY_TAIL_EMPTY")
    if len(open_trades) > 15:
        warnings.append("MEMORY_RISK_OPEN_TRADES_HIGH")

    legacy_stale = sync.get("legacy_stale") or []
    if legacy_stale:
        warnings.append("LEGACY_POLLUTION_REPORTED")

    if missing_state_files:
        recommended_next_actions.append("RESTORE_MISSING_ACTIVE_CHAIN_OUTPUTS")
    if clean_samples < 20:
        recommended_next_actions.append("ACCUMULATE_CLEAN_CLOSED_SAMPLES")
    if lineage_missing_open or lineage_missing_closed:
        recommended_next_actions.append("FIX_TRADE_LINEAGE_PROPAGATION")

    total_penalty = len(critical_issues) * 15 + len(warnings) * 4
    score_100 = max(0, 100 - total_penalty)
    if critical_issues:
        system_status = "BROKEN"
    elif warnings:
        system_status = "DEGRADED"
    else:
        system_status = "HEALTHY"

    payload = stamp_payload(
        {
            "symbol": str(context.get("symbol") or "BTCUSDT"),
            "block_id": BLOCK_ID,
            "source": {"source_mode": "SYSTEM_HEALTH_AUDIT"},
            "system_status": system_status,
            "score_100": score_100,
            "critical_issues": sorted(set(critical_issues)),
            "warnings": sorted(set(warnings)),
            "self_healing_actions_taken": self_healing_actions_taken,
            "recommended_next_actions": sorted(set(recommended_next_actions)),
            "can_continue_collecting_samples": not any(
                issue in {"ACTIVE_CHAIN_NOT_OK", "CONTEXT_SYNC_BROKEN", "LIVE_SAFETY_VIOLATION", "PRIVATE_API_VIOLATION"}
                for issue in critical_issues
            ),
            "live_order_sent": False,
            "reason_codes": [
                f"SYSTEM_STATUS_{system_status}",
                f"CRITICAL_{len(set(critical_issues))}",
                f"WARNINGS_{len(set(warnings))}",
            ],
            "data_quality": {
                "level": "HIGH" if system_status == "HEALTHY" else "MEDIUM" if system_status == "DEGRADED" else "LOW",
                "missing_inputs": missing_state_files,
            },
            "feeds_next": ["SYSTEM_QUERY_STATE_BUILDER", "S0_CONTEXT_SYNC_POST_VALIDATION"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        str(context.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, payload)
    return payload


def main() -> None:
    print(json.dumps(run_system_auditor_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
