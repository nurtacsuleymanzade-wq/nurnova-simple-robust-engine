from __future__ import annotations

import json
from pathlib import Path

from src.simple.research_epoch import epoch_state_path
from src.simple.research_runtime import append_jsonl, current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "MODEL_PROMOTION_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
OUTPUT_PATH = STATE_DIR / "latest_model_promotion.json"
HISTORY_PATH = DATA_DIR / "model_promotion_history.jsonl"
EDGE_PATH = epoch_state_path("latest_research_edge_matrix.json")
FEEDBACK_PATH = STATE_DIR / "latest_model_feedback.json"


def _stage(group: dict) -> str:
    sample_size = int(group.get("sample_size") or 0)
    expectancy = safe_float(group.get("expectancy")) or 0.0
    winrate = safe_float(group.get("winrate")) or 0.0
    avg_r = safe_float(group.get("avg_r")) or 0.0
    profit_factor = safe_float(group.get("profit_factor")) or 0.0
    max_drawdown_r = safe_float(group.get("max_drawdown_r")) or 999.0
    if sample_size < 20:
        return "NEEDS_MORE_SAMPLE"
    if expectancy <= 0:
        return "REJECTED" if sample_size >= 20 else "WATCHLIST_NEGATIVE"
    if sample_size >= 300 and expectancy > 0.15 and profit_factor > 1.2 and max_drawdown_r <= 3.0:
        return "LIVE_ELIGIBLE_DIAGNOSTIC_ONLY"
    if sample_size >= 100 and expectancy > 0.10 and avg_r > 0:
        return "PAPER_VALIDATED"
    if sample_size >= 50 and expectancy > 0 and winrate >= 0.45:
        return "PROBATION"
    return "WATCHLIST"


def run_model_promotion_engine() -> dict:
    context = current_runtime_context()
    edge = load_json(EDGE_PATH) or {}
    feedback = load_json(FEEDBACK_PATH) or {}
    groups = list(edge.get("groups") or [])

    promoted_models = []
    rejected_models = []
    probation_models = []
    paper_validated_models = []
    live_eligible_diagnostic_only = []
    needs_more_sample = []
    watchlist_models = []

    for group in groups:
        record = dict(group)
        record["stage"] = _stage(group)
        if record["stage"] == "REJECTED":
            rejected_models.append(record)
        elif record["stage"] == "PROBATION":
            probation_models.append(record)
            promoted_models.append(record)
        elif record["stage"] == "PAPER_VALIDATED":
            paper_validated_models.append(record)
            promoted_models.append(record)
        elif record["stage"] == "LIVE_ELIGIBLE_DIAGNOSTIC_ONLY":
            live_eligible_diagnostic_only.append(record)
            promoted_models.append(record)
        elif record["stage"] == "NEEDS_MORE_SAMPLE":
            needs_more_sample.append(record)
        else:
            watchlist_models.append(record)

    payload = stamp_payload(
        {
            "symbol": "BTCUSDT",
            "block_id": BLOCK_ID,
            "source": {"source_mode": "RESEARCH_EDGE_AND_FEEDBACK"},
            "promoted_models": promoted_models,
            "rejected_models": rejected_models,
            "probation_models": probation_models,
            "paper_validated_models": paper_validated_models,
            "live_eligible_diagnostic_only": live_eligible_diagnostic_only,
            "needs_more_sample": needs_more_sample,
            "watchlist_models": watchlist_models,
            "feedback_summary": feedback.get("summary") or {},
            "promotion_summary": {
                "research": 0,
                "watchlist": len(watchlist_models),
                "probation": len(probation_models),
                "paper_validated": len(paper_validated_models),
                "live_eligible_diagnostic_only": len(live_eligible_diagnostic_only),
                "rejected": len(rejected_models),
                "needs_more_sample": len(needs_more_sample),
            },
            "execution_safety": {
                "live_order_sent": False,
                "private_api_used": False,
                "diagnostic_only": True,
            },
            "reason_codes": ["DIAGNOSTIC_ONLY", f"GROUPS_{len(groups)}"],
            "data_quality": {"level": "HIGH" if edge else "LOW", "missing_inputs": [] if edge else ["latest_research_edge_matrix"]},
            "feeds_next": ["LIVE_ELIGIBILITY_GATE"],
        },
        BLOCK_ID,
        "BTCUSDT",
        context,
    )
    write_json(OUTPUT_PATH, payload)
    append_jsonl(HISTORY_PATH, payload)
    return payload


def main() -> None:
    print(json.dumps(run_model_promotion_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
