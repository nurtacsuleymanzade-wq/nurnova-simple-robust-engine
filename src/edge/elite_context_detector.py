from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, source_state_refs_from_paths, stamp_payload, write_json

BLOCK_ID = "ELITE_CONTEXT_DETECTOR"
STATE_DIR = Path("state/simple")
UNIFIED_CONTEXT_PATH = STATE_DIR / "latest_unified_context.json"
MODEL_CLUSTERS_PATH = STATE_DIR / "latest_model_clusters.json"
SETUP_ACTIVATION_PATH = STATE_DIR / "latest_setup_family_activation.json"
OUTPUT_PATH = epoch_state_path("latest_elite_context.json")
REQUIRED_CONDITIONS = {
    "COND_STRUCTURE_BULLISH",
    "COND_REGIME_MOMENTUM",
    "COND_BUYERS_ATTACKING",
    "COND_NEAR_LIQUIDITY_ABOVE",
    "COND_ATR_EXPANDING",
}


def _collect_conditions(*payloads: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    keys = ("conditions", "matched_conditions", "activation_reasons", "reason_codes", "grade_reasons")
    stack: list[Any] = list(payloads)
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key in keys and isinstance(value, list):
                    found.update(str(part).upper() for part in value)
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return found


def detect_elite_continuation_context(unified_context: dict[str, Any], model_clusters: dict[str, Any], setup_activation: dict[str, Any]) -> dict[str, Any]:
    conditions = _collect_conditions(unified_context, model_clusters, setup_activation)
    detected = REQUIRED_CONDITIONS.issubset(conditions)
    candidates = []
    for cluster in model_clusters.get("clusters") or []:
        model_id = cluster.get("dominant_model_id") or ((cluster.get("paper_representative") or {}).get("model_id") if isinstance(cluster.get("paper_representative"), dict) else None)
        if model_id:
            candidates.append(str(model_id))
    if setup_activation.get("source_models"):
        candidates.extend(str(item.get("model_id")) for item in setup_activation.get("source_models") or [] if isinstance(item, dict) and item.get("model_id"))
    return {
        "context_type": "ELITE_CONTINUATION_CONTEXT" if detected else "NO_ELITE_CONTEXT",
        "direction": "LONG" if detected else str(setup_activation.get("direction") or "NEUTRAL"),
        "conditions": sorted(REQUIRED_CONDITIONS if detected else conditions),
        "source_state_refs": source_state_refs_from_paths(
            {
                "unified_context": UNIFIED_CONTEXT_PATH,
                "model_clusters": MODEL_CLUSTERS_PATH,
                "setup_family_activation": SETUP_ACTIVATION_PATH,
            }
        ),
        "model_candidates": sorted(set(candidates)),
        "quality_label": "ELITE_CONTEXT_CANDIDATE" if detected else "NO_ELITE_CONTEXT",
        "telegram_allowed": bool(detected),
        "paper_research_allowed": bool(detected),
    }


def run_elite_context_detector() -> dict[str, Any]:
    context = current_runtime_context()
    unified_context = load_json(UNIFIED_CONTEXT_PATH) or {}
    model_clusters = load_json(MODEL_CLUSTERS_PATH) or {}
    setup_activation = load_json(SETUP_ACTIVATION_PATH) or {}
    detected = detect_elite_continuation_context(unified_context, model_clusters, setup_activation)
    output = stamp_payload(
        {
            **detected,
            "source": {"source_mode": "CONDITION_CONSTELLATION_OVERLAY"},
            "data_quality": {
                "level": "HIGH" if unified_context and model_clusters and setup_activation else "MEDIUM",
                "missing_inputs": [
                    name for name, payload in {
                        "latest_unified_context": unified_context,
                        "latest_model_clusters": model_clusters,
                        "latest_setup_family_activation": setup_activation,
                    }.items() if not payload
                ],
            },
            "feeds_next": ["SIGNAL_GRADE_ENGINE", "SIGNAL_EVENT_CONSOLIDATOR", "TELEGRAM_RESEARCH_REPORTER", "PAPER_TRADE_FACTORY"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str(unified_context.get("symbol") or setup_activation.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_jsonl_stream(epoch_data_path("elite_context_history.jsonl"), output)
    return output


def main() -> None:
    print(json.dumps(run_elite_context_detector(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
