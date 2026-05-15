from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, source_state_refs_from_paths, stamp_payload

BLOCK_ID = "FULL_LINEAGE_TRACKER"
STATE_DIR = Path("state/simple")
PATHS = {
    "raw_observation": STATE_DIR / "latest_observation_factory.json",
    "1s_evidence": STATE_DIR / "latest_1s_evidence.json",
    "hybrid_candle_dna": STATE_DIR / "latest_hybrid_candle_dna.json",
    "mtf_candle_dna": STATE_DIR / "latest_mtf_candle_dna.json",
    "market_structure": STATE_DIR / "latest_market_structure.json",
    "liquidity_map": STATE_DIR / "latest_liquidity_map.json",
    "zone_context": STATE_DIR / "latest_zone_context.json",
    "interpretation": STATE_DIR / "latest_interpretation.json",
    "scenario": STATE_DIR / "latest_three_scenarios.json",
    "unified_context": STATE_DIR / "latest_unified_context.json",
    "model_cluster": STATE_DIR / "latest_model_clusters.json",
    "setup_activation": STATE_DIR / "latest_setup_family_activation.json",
    "timeframe_resolution": epoch_state_path("latest_timeframe_resolution.json"),
    "signal_grade": epoch_state_path("latest_signal_grade.json"),
    "signal_event": epoch_state_path("latest_signal_event.json"),
    "paper_trade": epoch_state_path("latest_paper_trade_factory.json"),
    "lifecycle": epoch_state_path("latest_research_paper_lifecycle.json"),
    "outcome": epoch_state_path("latest_outcome_accounting.json"),
    "edge_report": epoch_state_path("latest_edge_query_report.json"),
    "telegram": epoch_state_path("latest_telegram_report.json"),
    "condition_dna": epoch_state_path("latest_tp_condition_dna.json"),
}
OUTPUT_HISTORY = epoch_data_path("full_lineage_history.jsonl")
OUTPUT_STATE = epoch_state_path("latest_full_lineage.json")


def _first(*items: Any) -> Any:
    for item in items:
        if item not in (None, "", [], {}):
            return item
    return None


def _latest_trade(factory: dict[str, Any], lifecycle: dict[str, Any], outcome: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    for collection in (
        factory.get("newest_opened_this_loop"),
        factory.get("top_candidate_diagnostics"),
        lifecycle.get("trades_closed_this_loop"),
        lifecycle.get("open_trades"),
        outcome.get("closed_trades_this_loop"),
        event.get("events"),
    ):
        if collection and isinstance(collection, list) and isinstance(collection[0], dict):
            return dict(collection[0])
    if isinstance(event.get("latest_event"), dict):
        return dict(event["latest_event"])
    return {}


def run_full_lineage_tracker() -> dict[str, Any]:
    context = current_runtime_context()
    payloads = {name: load_json(path) or {} for name, path in PATHS.items()}
    trade = _latest_trade(payloads["paper_trade"], payloads["lifecycle"], payloads["outcome"], payloads["signal_event"])
    event = payloads["signal_event"].get("latest_event") or {}
    lineage = {
        "paper_trade_id": _first(trade.get("paper_trade_id"), event.get("paper_trade_id")),
        "event_id": _first(trade.get("event_id"), event.get("event_id")),
        "context_id": _first(trade.get("context_id"), event.get("context_id"), context.get("context_id")),
        "loop_id": _first(trade.get("loop_id"), event.get("loop_id"), context.get("loop_id")),
        "model_id": _first(trade.get("model_id"), event.get("primary_model")),
        "setup_family": _first(trade.get("setup_family"), event.get("primary_setup")),
        "direction": _first(trade.get("direction"), event.get("direction")),
        "entry": _first(trade.get("entry"), event.get("entry")),
        "stop_loss": _first(trade.get("stop_loss"), event.get("stop_loss")),
        "tp1": _first(trade.get("tp1"), event.get("tp1")),
        "tp2": _first(trade.get("tp2"), event.get("tp2")),
        "source_state_refs": source_state_refs_from_paths(PATHS),
        "cause_chain": list(PATHS.keys()),
        "zone_context": payloads["zone_context"].get("zones") or trade.get("zone_context") or [],
        "condition_dna": payloads["condition_dna"].get("tp_edge_conditions") or [],
        "final_result": _first(trade.get("close_reason"), trade.get("result"), trade.get("status")),
        "r_result": trade.get("r_result"),
        "mfe": trade.get("mfe"),
        "mae": trade.get("mae"),
        "hold_seconds": _first(trade.get("hold_seconds"), trade.get("holding_seconds")),
        "telegram_sent": bool((payloads["telegram"].get("message_count") or 0) > 0),
        "tp_notification_sent": any(str(item.get("message_type") or "").upper() in {"TP1_HIT", "TP2_HIT"} for item in payloads["telegram"].get("messages") or []),
        "sl_notification_sent": any(str(item.get("message_type") or "").upper() == "SL_HIT" for item in payloads["telegram"].get("messages") or []),
    }
    output = stamp_payload(
        {
            **lineage,
            "data_quality": {"level": "HIGH" if trade or event else "LOW", "missing_inputs": [name for name, payload in payloads.items() if not payload]},
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str(trade.get("symbol") or event.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json_atomic(OUTPUT_STATE, output)
    append_jsonl_stream(OUTPUT_HISTORY, output)
    return output


def main() -> None:
    print(json.dumps(run_full_lineage_tracker(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
