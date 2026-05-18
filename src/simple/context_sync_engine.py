from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import (
    RUNTIME_CONTEXT_PATH,
    current_runtime_context,
    initialize_runtime_context,
    load_json,
    parse_ts,
    stamp_payload,
    utc_now,
    write_json,
)
from src.simple.research_epoch import epoch_state_path

STATE_DIR = Path("state/simple")
OUTPUT_PATH = STATE_DIR / "latest_context_sync.json"
S0_STATE_PATH = STATE_DIR / "s0_context_sync_state.json"

ACTIVE_CHAIN_FILES: dict[str, Path] = {
    "RUNTIME_CONTEXT": RUNTIME_CONTEXT_PATH,
    "OBSERVATION_FACTORY": STATE_DIR / "latest_observation_factory.json",
    "MTF_CANDLE_DNA_FACTORY": STATE_DIR / "latest_mtf_candle_dna.json",
    "ATR_ENGINE": STATE_DIR / "latest_atr_state.json",
    "MARKET_STRUCTURE_ENGINE": STATE_DIR / "latest_market_structure.json",
    "LIQUIDITY_MAP_ENGINE": STATE_DIR / "latest_liquidity_map.json",
    "INTERPRETATION_ENGINE": STATE_DIR / "latest_interpretation.json",
    "THREE_SCENARIO_ENGINE": STATE_DIR / "latest_three_scenarios.json",
    "BUSINESS_ZONE_ENGINE": STATE_DIR / "latest_business_zone.json",
    "MARKET_REGIME_CLASSIFIER": STATE_DIR / "latest_market_regime.json",
    "INTENT_ENGINE": STATE_DIR / "latest_intent_analysis.json",
    "UNIFIED_CONTEXT_ENGINE": STATE_DIR / "latest_unified_context.json",
    "MODEL_DEFINITION_REGISTRY": STATE_DIR / "latest_model_definitions.json",
    "MODEL_HUNTER_ENGINE": STATE_DIR / "latest_model_hunter.json",
    "MODEL_SEMANTIC_VALIDATOR": STATE_DIR / "latest_model_semantic_validation.json",
    "MODEL_CLUSTER_ENGINE": STATE_DIR / "latest_model_clusters.json",
    "MODEL_COOLDOWN_ENGINE": STATE_DIR / "latest_model_cooldown.json",
    "SETUP_FAMILY_ACTIVATION_ENGINE": STATE_DIR / "latest_setup_family_activation.json",
    "TIMEFRAME_RESOLVER": epoch_state_path("latest_timeframe_resolution.json"),
    "PAPER_TRADE_FACTORY": epoch_state_path("latest_paper_trade_factory.json"),
    # "RESEARCH_PAPER_LIFECYCLE_ENGINE": epoch_state_path("latest_research_paper_lifecycle.json"),
    # "OUTCOME_ACCOUNTING_ENGINE": epoch_state_path("latest_outcome_accounting.json"),
    "RESEARCH_EDGE_MATRIX_ENGINE": epoch_state_path("latest_research_edge_matrix.json"),
    "TELEGRAM_RESEARCH_REPORTER": epoch_state_path("latest_telegram_report.json"),
    "MODEL_FEEDBACK_DIAGNOSTIC": STATE_DIR / "latest_model_feedback.json",
    "MODEL_PROMOTION_ENGINE": STATE_DIR / "latest_model_promotion.json",
    "LIVE_ELIGIBILITY_GATE_DIAGNOSTIC": STATE_DIR / "latest_live_eligibility_gate.json",
    "SYSTEM_AUDITOR_ENGINE": STATE_DIR / "latest_system_audit.json",
    "SYSTEM_QUERY_STATE_BUILDER": STATE_DIR / "latest_system_query_state.json",
}

LEGACY_BRIDGE_FILES: dict[str, Path] = {
    "S15_FLOW_TO_SETUP_CONTEXT": STATE_DIR / "latest_setup_context.json",
    "S16_SCENARIO_ENTRY_TRIGGER": STATE_DIR / "latest_scenario_trigger.json",
    "S17_TRADE_PLAN": STATE_DIR / "latest_trade_plan.json",
    "S18_DECISION_GATE": STATE_DIR / "latest_decision_gate.json",
    "S20_PAPER_LIFECYCLE": STATE_DIR / "latest_paper_lifecycle.json",
    "S21_OUTCOME_MONITOR": STATE_DIR / "latest_outcome_monitor.json",
    "S22_EDGE_MATRIX_V2": STATE_DIR / "latest_edge_matrix_v2.json",
}

CRITICAL_ACTIVE_BLOCKS = {
    "OBSERVATION_FACTORY",
    # "MTF_CANDLE_DNA_FACTORY",  # FIX-A
    "UNIFIED_CONTEXT_ENGINE",
    "MODEL_HUNTER_ENGINE",
    "SETUP_FAMILY_ACTIVATION_ENGINE",
    "TIMEFRAME_RESOLVER",
    "PAPER_TRADE_FACTORY",
    # "RESEARCH_PAPER_LIFECYCLE_ENGINE",
    # "OUTCOME_ACCOUNTING_ENGINE",
    "RESEARCH_EDGE_MATRIX_ENGINE",
    "TELEGRAM_RESEARCH_REPORTER",
    "SYSTEM_AUDITOR_ENGINE",
    "SYSTEM_QUERY_STATE_BUILDER",
}

MAX_ACTIVE_DRIFT_SECONDS = 180.0
MAX_LEGACY_STALE_SECONDS = 900.0


def active_chain_declaration() -> list[str]:
    return list(ACTIVE_CHAIN_FILES)


def _seconds_between(left: datetime | None, right: datetime | None) -> float | None:
    if left is None or right is None:
        return None
    return abs((left - right).total_seconds())


def _inspect_file(
    block_id: str,
    path: Path,
    expected_context_id: str,
    expected_loop_id: int,
    loop_started_at: datetime | None,
    critical: bool,
) -> dict[str, Any]:
    payload = load_json(path)
    item = {
        "block_id": block_id,
        "path": str(path),
        "critical": critical,
        "exists": payload is not None,
        "corrupted": False,
        "context_id": None,
        "loop_id": None,
        "timestamp_utc": None,
        "age_seconds": None,
        "status": "OK",
        "reasons": [],
    }
    if payload is None:
        item["status"] = "MISSING"
        item["reasons"].append("MISSING")
        return item

    ts = parse_ts(payload.get("timestamp_utc"))
    item["timestamp_utc"] = payload.get("timestamp_utc")
    item["context_id"] = payload.get("context_id")
    item["loop_id"] = payload.get("loop_id")
    if ts is None:
        item["status"] = "CORRUPTED"
        item["corrupted"] = True
        item["reasons"].append("TIMESTAMP_INVALID")
    elif loop_started_at is not None:
        age = _seconds_between(ts, datetime.now(timezone.utc))
        item["age_seconds"] = round(age, 3) if age is not None else None
        drift = _seconds_between(ts, loop_started_at)
        if drift is not None and drift > MAX_ACTIVE_DRIFT_SECONDS:
            item["status"] = "STALE"
            item["reasons"].append(f"TIMESTAMP_DRIFT_{round(drift, 3)}")

    if payload.get("context_id") != expected_context_id:
        item["reasons"].append("CONTEXT_ID_MISMATCH")
        item["status"] = "MISMATCH"
    if int(payload.get("loop_id") or -1) != int(expected_loop_id):
        item["reasons"].append("LOOP_ID_MISMATCH")
        item["status"] = "MISMATCH"
    if payload.get("block_id") != block_id:
        item["reasons"].append("BLOCK_ID_MISMATCH")
        item["status"] = "MISMATCH"
    if not payload.get("context_id"):
        item["reasons"].append("CONTEXT_ID_MISSING")
        item["status"] = "MISSING_CONTEXT"
    return item


def _inspect_legacy_file(path: Path, context_id: str, loop_id: int, loop_started_at: datetime | None) -> dict[str, Any] | None:
    payload = load_json(path)
    if payload is None:
        return None
    ts = parse_ts(payload.get("timestamp_utc"))
    stale = False
    if ts is not None and loop_started_at is not None:
        drift = _seconds_between(ts, loop_started_at)
        stale = bool(drift is not None and drift > MAX_LEGACY_STALE_SECONDS)
    stale = stale or payload.get("context_id") not in (None, "", context_id) or int(payload.get("loop_id") or loop_id) != loop_id
    if not stale:
        return None
    return {
        "path": str(path),
        "context_id": payload.get("context_id"),
        "loop_id": payload.get("loop_id"),
        "timestamp_utc": payload.get("timestamp_utc"),
        "status": "LEGACY_STALE",
    }


def run_context_sync(symbol: str = "BTCUSDT", mode: str = "post") -> dict[str, Any]:
    context = current_runtime_context(symbol)
    if mode == "start":
        context = initialize_runtime_context(symbol)
    context_id = str(context.get("context_id") or "CTX_UNKNOWN")
    loop_id = int(context.get("loop_id") or 0)
    loop_started_at = parse_ts(context.get("loop_started_at_utc") or context.get("timestamp_utc"))

    critical_missing: list[str] = []
    critical_stale: list[str] = []
    context_mismatches: list[str] = []
    timestamp_drift: list[str] = []
    legacy_stale: list[dict[str, Any]] = []
    degraded_reasons: list[str] = []
    active_chain_status: dict[str, dict[str, Any]] = {}

    for block_id, path in ACTIVE_CHAIN_FILES.items():
        item = _inspect_file(block_id, path, context_id, loop_id, loop_started_at, block_id in CRITICAL_ACTIVE_BLOCKS)
        active_chain_status[block_id] = item
        reasons = set(item.get("reasons") or [])
        if item["status"] == "MISSING":
            if item["critical"]:
                critical_missing.append(block_id)
            else:
                degraded_reasons.append(f"{block_id}:missing")
            continue
        if item["corrupted"]:
            if item["critical"]:
                critical_stale.append(block_id)
            else:
                degraded_reasons.append(f"{block_id}:corrupted")
        if "TIMESTAMP_DRIFT" in ",".join(reasons):
            timestamp_drift.append(block_id)
            if item["critical"]:
                critical_stale.append(block_id)
            else:
                degraded_reasons.append(f"{block_id}:stale")
        if "CONTEXT_ID_MISMATCH" in reasons or "LOOP_ID_MISMATCH" in reasons:
            context_mismatches.append(block_id)
            if item["critical"]:
                critical_stale.append(block_id)
            else:
                degraded_reasons.append(f"{block_id}:mismatch")
        if "CONTEXT_ID_MISSING" in reasons:
            if item["critical"]:
                critical_stale.append(block_id)
            else:
                degraded_reasons.append(f"{block_id}:context_missing")

    for _, path in LEGACY_BRIDGE_FILES.items():
        stale_item = _inspect_legacy_file(path, context_id, loop_id, loop_started_at)
        if stale_item:
            legacy_stale.append(stale_item)

    critical_missing = sorted(set(critical_missing))
    critical_stale = sorted(set(critical_stale))
    context_mismatches = sorted(set(context_mismatches))
    timestamp_drift = sorted(set(timestamp_drift))
    degraded_reasons = sorted(set(degraded_reasons))

    active_chain_ok = not critical_missing and not critical_stale
    if active_chain_ok and degraded_reasons:
        sync_status = "SYNC_DEGRADED"
    elif active_chain_ok:
        sync_status = "SYNC_OK"
    else:
        sync_status = "SYNC_BROKEN"

    failed_reason = None
    if sync_status == "SYNC_BROKEN":
        failed_reason = ";".join(
            [f"missing={','.join(critical_missing)}" if critical_missing else "", f"stale={','.join(critical_stale)}" if critical_stale else ""]
        ).strip(";") or "ACTIVE_CHAIN_ALIGNMENT_FAILED"

    payload = stamp_payload(
        {
            "sync_status": sync_status,
            "active_chain_ok": active_chain_ok,
            "critical_missing": critical_missing,
            "critical_stale": critical_stale,
            "context_mismatches": context_mismatches,
            "timestamp_drift": timestamp_drift,
            "legacy_stale": legacy_stale,
            "legacy_bridge_status": {
                "mode": "LEGACY_BRIDGE",
                "present": any(load_json(path) for path in LEGACY_BRIDGE_FILES.values()),
                "files": {block_id: str(path) for block_id, path in LEGACY_BRIDGE_FILES.items()},
            },
            "failed_reason": failed_reason,
            "active_chain_blocks": active_chain_declaration(),
            "active_chain_status": active_chain_status,
            "loop_started_at_utc": context.get("loop_started_at_utc"),
            "pipeline_ready": active_chain_ok,
            "source": {"source_mode": "S0_CONTEXT_SYNC_POST_VALIDATION" if mode != "start" else "CONTEXT_SYNC_START"},
            "reason_codes": [
                f"SYNC_STATUS_{sync_status}",
                f"ACTIVE_CHAIN_OK_{str(active_chain_ok).upper()}",
                f"CRITICAL_MISSING_{len(critical_missing)}",
                f"CRITICAL_STALE_{len(critical_stale)}",
                f"LEGACY_STALE_{len(legacy_stale)}",
            ],
            "data_quality": {
                "level": "HIGH" if sync_status == "SYNC_OK" else "MEDIUM" if sync_status == "SYNC_DEGRADED" else "LOW",
                "score": 1.0 if sync_status == "SYNC_OK" else 0.65 if sync_status == "SYNC_DEGRADED" else 0.15,
                "issues": critical_missing + critical_stale + degraded_reasons,
            },
            "feeds_next": {"next_blocks": ["MODEL_FEEDBACK_DIAGNOSTIC", "MODEL_PROMOTION_ENGINE", "LIVE_ELIGIBILITY_GATE"]},
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        "S0_CONTEXT_SYNC_POST_VALIDATION" if mode != "start" else "CONTEXT_SYNC_START",
        symbol,
        context,
    )

    write_json(OUTPUT_PATH, payload)
    write_json(
        S0_STATE_PATH,
        {
            "timestamp_utc": utc_now(),
            "block_id": "S0_CONTEXT_SYNC_STATE",
            "symbol": payload.get("symbol"),
            "context_id": context_id,
            "loop_id": loop_id,
            "sync_status": sync_status,
            "active_chain_ok": active_chain_ok,
            "failed_reason": failed_reason,
        },
    )
    return payload


def get_current_context_id() -> str | None:
    return (load_json(OUTPUT_PATH) or load_json(RUNTIME_CONTEXT_PATH) or {}).get("context_id")


def is_pipeline_ready() -> bool:
    return bool((load_json(OUTPUT_PATH) or {}).get("pipeline_ready"))


def main() -> None:
    print(json.dumps(run_context_sync(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
