from __future__ import annotations

import json
from pathlib import Path

from src.simple.research_epoch import epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "MODEL_FEEDBACK_DIAGNOSTIC"
STATE_DIR = Path("state/simple")
OUTPUT_PATH = STATE_DIR / "latest_model_feedback.json"
EDGE_PATH = epoch_state_path("latest_research_edge_matrix.json")


def run_model_feedback_diagnostic() -> dict:
    context = current_runtime_context()
    edge = load_json(EDGE_PATH) or {}
    groups = list(edge.get("groups") or [])
    ranked = sorted(groups, key=lambda item: safe_float(item.get("expectancy")) or -9999, reverse=True)
    sample_building = [item for item in groups if item.get("sample_size", 0) < 20]
    worst = sorted(groups, key=lambda item: safe_float(item.get("expectancy")) or 9999)[:5]

    families_overtrading = sorted({str(item.get("setup_family") or "UNKNOWN") for item in groups if item.get("sample_size", 0) >= 20 and (safe_float(item.get("expectancy")) or 0.0) <= 0})
    families_underperforming = families_overtrading[:]
    best_models = ranked[:5]
    worst_models = worst

    payload = stamp_payload(
        {
            "symbol": "BTCUSDT",
            "block_id": BLOCK_ID,
            "source": {"source_mode": "RESEARCH_EDGE_MATRIX"},
            "best_models": best_models,
            "worst_models": worst_models,
            "models_needing_more_samples": sample_building[:10],
            "families_overtrading": families_overtrading,
            "families_underperforming": families_underperforming,
            "sample_building_models": sample_building[:10],
            "invalid_sample_reasons": edge.get("invalid_sample_reasons") or {},
            "recommended_threshold_adjustments": [
                {
                    "model_id": item.get("model_id"),
                    "current_activation_band": item.get("activation_band"),
                    "suggestion": "RAISE_THRESHOLD"
                    if (safe_float(item.get("expectancy")) or 0.0) <= 0.0 and int(item.get("sample_size") or 0) >= 20
                    else "HOLD_THRESHOLD"
                    if int(item.get("sample_size") or 0) < 20
                    else "KEEP_OBSERVING",
                }
                for item in ranked[:10]
            ],
            "diagnostic_only": True,
            "summary": {
                "best": best_models[0].get("model_id") if best_models else None,
                "worst": worst_models[0].get("model_id") if worst_models else None,
                "sample_building": len(sample_building),
            },
            "reason_codes": ["DIAGNOSTIC_ONLY", f"GROUPS_{len(groups)}"],
            "data_quality": {"level": "HIGH" if edge else "LOW", "missing_inputs": [] if edge else ["latest_research_edge_matrix"]},
            "feeds_next": ["MODEL_PROMOTION_ENGINE"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        "BTCUSDT",
        context,
    )
    write_json(OUTPUT_PATH, payload)
    return payload


def main() -> None:
    print(json.dumps(run_model_feedback_diagnostic(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
