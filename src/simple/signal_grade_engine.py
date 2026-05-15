from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.model_survival_registry import load_model_survival_registry, split_active_quarantined, update_model_survival_report
from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, source_state_refs_from_paths, stamp_payload, write_json

BLOCK_ID = "SIGNAL_GRADE_ENGINE"
STATE_DIR = Path("state/simple")
OUTPUT_PATH = epoch_state_path("latest_signal_grade.json")
HISTORY_PATH = epoch_data_path("signal_grade_history.jsonl")

SETUP_ACTIVATION_PATH = STATE_DIR / "latest_setup_family_activation.json"
TIMEFRAME_PATH = epoch_state_path("latest_timeframe_resolution.json")
PAPER_FACTORY_PATH = epoch_state_path("latest_paper_trade_factory.json")
EDGE_PATH = epoch_state_path("latest_research_edge_matrix.json")
ACCOUNTING_PATH = epoch_state_path("latest_outcome_accounting.json")


def _direction_valid(value: Any) -> bool:
    return str(value or "").upper() in {"LONG", "SHORT"}


def _data_quality_level(*payloads: dict[str, Any]) -> str:
    levels = [str((payload.get("data_quality") or {}).get("level") or "").upper() for payload in payloads if payload]
    if "LOW" in levels or "CRITICAL" in levels or "INVALID" in levels:
        return "LOW"
    if "MEDIUM" in levels:
        return "MEDIUM"
    return "HIGH" if levels else "MEDIUM"


def grade_signal_record(
    trade: dict[str, Any],
    setup: dict[str, Any] | None = None,
    timeframe: dict[str, Any] | None = None,
    edge: dict[str, Any] | None = None,
    accounting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    setup = setup or {}
    timeframe = timeframe or {}
    edge = edge or {}
    accounting = accounting or {}
    activation_score = safe_float(trade.get("activation_score")) or safe_float(setup.get("activation_score")) or 0.0
    rr1 = safe_float(trade.get("rr1"))
    rr2 = safe_float(trade.get("rr2"))
    direction = str(trade.get("direction") or setup.get("direction") or "NEUTRAL").upper()
    primary_tf = trade.get("primary_tf") or timeframe.get("primary_tf")
    context_tf = trade.get("context_tf") or timeframe.get("context_tf")
    trigger_tf = trade.get("trigger_tf") or timeframe.get("trigger_tf")
    confluence_count = int(trade.get("event_confluence_count") or len(trade.get("source_models") or []) or len(setup.get("source_models") or []) or 1)
    data_quality = _data_quality_level(setup, timeframe, edge, accounting)
    risk_tags = {str(item).upper() for item in (trade.get("risk_tags") or setup.get("risk_tags") or [])}
    reason_codes = {str(item).upper() for item in (trade.get("reason_codes") or [])}
    liquidity_event = str(trade.get("liquidity_event") or "").upper()
    structure_label = str(trade.get("structure_label") or "").upper()
    direction_resolution = trade.get("direction_resolution") or setup.get("direction_resolution") or {}
    resolution_mode = str(direction_resolution.get("resolution_mode") or "").upper()
    direction_conflicts = direction_resolution.get("direction_conflicts") or []

    blockers: list[str] = []
    reasons: list[str] = []
    registry = load_model_survival_registry()
    model_id = trade.get("model_id") or trade.get("dominant_model_id") or trade.get("primary_model")
    if model_id and str(model_id) in {str(item) for item in registry.get("quarantined_models") or []}:
        blockers.append("MODEL_SURVIVAL_REGISTRY_BLOCK")
    if not _direction_valid(direction):
        blockers.append("DIRECTION_INVALID")
    if not primary_tf or not context_tf:
        blockers.append("MISSING_TIMEFRAME")
    if rr1 is None or rr2 is None:
        blockers.append("MISSING_RR")
    elif rr1 < 1.2 or rr2 < 2.0:
        reasons.append("RR_BELOW_A_GATE")
    if activation_score < 0.80:
        reasons.append("ACTIVATION_SCORE_BELOW_A_GATE")
    if confluence_count < 2:
        reasons.append("EVENT_CONFLUENCE_LT_2")
    if liquidity_event in {"", "UNKNOWN", "NONE", "NO_EVENT"}:
        reasons.append("LIQUIDITY_EVENT_MISSING")
    if structure_label in {"", "UNKNOWN", "NONE", "NO_STRUCTURE"}:
        reasons.append("STRUCTURE_LABEL_MISSING")
    if data_quality not in {"HIGH", "MEDIUM"}:
        blockers.append("DATA_QUALITY_LOW")
    if (
        "HARD_DIRECTION_CONFLICT" in risk_tags
        or "DIRECTION_CONFLICT" in reason_codes
        or "SEMANTIC_CONTRADICTION" in reason_codes
        or resolution_mode == "NEUTRAL_HARD_CONFLICT"
    ):
        blockers.append("HARD_DIRECTION_CONFLICT")
    if direction_conflicts and int(direction_resolution.get("conflict_count") or len(direction_conflicts)) >= 2:
        blockers.append("MTF_ALIGNMENT_CONTRADICTORY")
    if bool(trade.get("execution_safety", {}).get("live_order_sent")) or bool(trade.get("live_order_sent")):
        blockers.append("LIVE_ORDER_SENT_TRUE")

    if activation_score >= 0.85:
        reasons.append("ACTIVATION_SCORE_A_PLUS")
    elif activation_score >= 0.80:
        reasons.append("ACTIVATION_SCORE_A")
    elif activation_score >= 0.60:
        reasons.append("ACTIVATION_SCORE_B")
    elif activation_score >= 0.45:
        reasons.append("ACTIVATION_SCORE_C")
    else:
        blockers.append("ACTIVATION_SCORE_WEAK")
    if rr1 is not None and rr2 is not None:
        reasons.append("RR_PRESENT")
    if primary_tf and context_tf and trigger_tf:
        reasons.append("TIMEFRAME_VALID")
    if confluence_count >= 2:
        reasons.append("EVENT_CONFLUENCE_GE_2")
    edge_status = str(edge.get("edge_status") or "").upper()
    if edge_status in {"EDGE_ACTIVE", "SAMPLE_BUILDING"}:
        reasons.append(f"EDGE_{edge_status}")

    grade = "D"
    if blockers:
        grade = "D"
    elif activation_score >= 0.85 and (rr1 or 0.0) >= 1.2 and (rr2 or 0.0) >= 2.0 and primary_tf and context_tf and confluence_count >= 2:
        grade = "A_PLUS"
    elif activation_score >= 0.80 and (rr1 or 0.0) >= 1.2 and (rr2 or 0.0) >= 2.0 and primary_tf and context_tf and confluence_count >= 2 and _direction_valid(direction):
        grade = "A"
    elif activation_score >= 0.60 and (rr1 or 0.0) >= 1.0 and _direction_valid(direction):
        grade = "B"
    elif activation_score >= 0.45:
        grade = "C"

    grade_floor = {"D": 0.2, "C": 0.45, "B": 0.6, "A": 0.75, "A_PLUS": 0.9}[grade]
    rr_score = min(((rr1 or 0.0) / 1.2 + (rr2 or 0.0) / 2.0) / 2.0, 1.0) if rr1 is not None and rr2 is not None else 0.0
    tf_score = 1.0 if primary_tf and context_tf else 0.5 if primary_tf or trigger_tf else 0.0
    confluence_score = min(confluence_count / 3.0, 1.0)
    grade_score = round(max(grade_floor, activation_score * 0.45 + rr_score * 0.25 + tf_score * 0.15 + confluence_score * 0.15), 4)
    a_plus_ready = grade == "A_PLUS"
    return {
        "signal_grade": grade,
        "grade_score": grade_score,
        "grade_reasons": sorted(set(reasons)),
        "grade_blockers": sorted(set(blockers)),
        "a_plus_ready": a_plus_ready,
        "source_state_refs": source_state_refs_from_paths(
            {
                "setup_activation": SETUP_ACTIVATION_PATH,
                "timeframe_resolution": TIMEFRAME_PATH,
                "paper_trade_factory": PAPER_FACTORY_PATH,
                "research_edge_matrix": EDGE_PATH,
                "outcome_accounting": ACCOUNTING_PATH,
            }
        ),
    }


def run_signal_grade_engine() -> dict[str, Any]:
    context = current_runtime_context()
    setup = load_json(SETUP_ACTIVATION_PATH) or {}
    timeframe = load_json(TIMEFRAME_PATH) or {}
    factory = load_json(PAPER_FACTORY_PATH) or {}
    edge = load_json(EDGE_PATH) or {}
    accounting = load_json(ACCOUNTING_PATH) or {}
    registry = load_model_survival_registry()
    raw_trades = list(factory.get("newest_opened_this_loop") or factory.get("top_candidate_diagnostics") or [])
    trades, blocked_trades = split_active_quarantined(raw_trades, BLOCK_ID)
    survival_report = update_model_survival_report(location=BLOCK_ID, allowed_count=len(trades), blocked_items=blocked_trades, registry=registry)
    graded = []
    for trade in trades:
        record = dict(trade)
        record.update(grade_signal_record(record, setup, timeframe, edge, accounting))
        graded.append(record)
    primary = max(graded, key=lambda item: safe_float(item.get("grade_score")) or 0.0) if graded else grade_signal_record({}, setup, timeframe, edge, accounting)
    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "source": {"source_mode": "EPOCH_V2_CANONICAL_SIGNAL_INPUTS"},
            "primary_grade": primary,
            "graded_signals": graded[:50],
            "summary": {
                "graded_signal_count": len(graded),
                "model_survival_blocked_count": len(blocked_trades),
                "a_plus_count": sum(1 for item in graded if item.get("signal_grade") == "A_PLUS"),
                "best_grade": primary.get("signal_grade"),
                "best_grade_score": primary.get("grade_score"),
            },
            "data_quality": {"level": "HIGH" if factory else "MEDIUM", "missing_inputs": [name for name, payload in {"paper_trade_factory": factory, "setup_activation": setup, "timeframe_resolution": timeframe}.items() if not payload]},
            "reason_codes": ["SIGNAL_GRADE_CONSTITUTION_ACTIVE", "PAPER_ONLY", "NO_LIVE_EXECUTION", "NO_PRIVATE_API"],
            "model_survival_registry": {"registry_status": survival_report.get("registry_status"), "blocked_count": len(blocked_trades)},
            "feeds_next": ["SIGNAL_EVENT_CONSOLIDATOR", "TELEGRAM_RESEARCH_REPORTER"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str(factory.get("symbol") or context.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("signal_grade_history.jsonl", output)
    return output


def main() -> None:
    print(json.dumps(run_signal_grade_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
