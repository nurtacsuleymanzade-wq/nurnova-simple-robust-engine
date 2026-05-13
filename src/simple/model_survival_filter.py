from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "MODEL_SURVIVAL_FILTER"
OUTPUT_PATH = epoch_state_path("latest_model_survival_filter.json")
HISTORY_PATH = epoch_data_path("model_survival_filter_history.jsonl")
ACCOUNTING_PATH = epoch_state_path("latest_outcome_accounting.json")
EDGE_PATH = epoch_state_path("latest_research_edge_matrix.json")


def _is_loss(sample: dict[str, Any]) -> bool:
    return str(sample.get("close_reason") or "").upper() == "SL_HIT" or (safe_float(sample.get("r_result")) or 0.0) < 0


def _loss_streak(samples: list[dict[str, Any]]) -> int:
    streak = 0
    for sample in sorted(samples, key=lambda item: str(item.get("closed_at_utc") or item.get("opened_at_utc") or ""), reverse=True):
        if _is_loss(sample):
            streak += 1
            continue
        break
    return streak


def _metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for item in samples if str(item.get("close_reason") or "").upper() in {"TP1_HIT", "TP2_HIT"})
    losses = sum(1 for item in samples if str(item.get("close_reason") or "").upper() == "SL_HIT")
    winrate = round(wins / (wins + losses), 4) if wins + losses else 0.0
    avg_r = round(sum(safe_float(item.get("r_result")) or 0.0 for item in samples) / len(samples), 4) if samples else 0.0
    return {
        "sample_size": len(samples),
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "avg_r": avg_r,
        "loss_streak": _loss_streak(samples),
    }


def _status(metrics: dict[str, Any]) -> tuple[str, bool, list[str]]:
    sample_size = int(metrics.get("sample_size") or 0)
    winrate = safe_float(metrics.get("winrate")) or 0.0
    avg_r = safe_float(metrics.get("avg_r")) or 0.0
    loss_streak = int(metrics.get("loss_streak") or 0)
    if sample_size >= 10 and (winrate < 0.35 or avg_r < -0.25 or loss_streak >= 4):
        return "SUPPRESSED_RESEARCH", False, []
    if sample_size >= 20 and winrate >= 0.50 and avg_r > 0.20:
        return "PROMISING", True, ["A_PLUS", "A"]
    if sample_size < 10:
        return "SAMPLE_BUILDING", False, ["A_PLUS"]
    return "RESEARCH_ONLY", True, ["A_PLUS", "A"]


def run_model_survival_filter() -> dict[str, Any]:
    context = current_runtime_context()
    accounting = load_json(ACCOUNTING_PATH) or {}
    edge = load_json(EDGE_PATH) or {}
    clean_samples = list(accounting.get("closed_samples") or [])
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in clean_samples:
        model_id = str(sample.get("model_id") or "UNKNOWN")
        by_model[model_id].append(sample)

    edge_groups_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in edge.get("groups") or []:
        edge_groups_by_model[str(group.get("model_id") or "UNKNOWN")].append(group)

    models: dict[str, dict[str, Any]] = {}
    for model_id in sorted(set(by_model) | set(edge_groups_by_model)):
        metrics = _metrics(by_model.get(model_id, []))
        model_status, paper_open_allowed, allowed_grades = _status(metrics)
        models[model_id] = {
            "model_id": model_id,
            **metrics,
            "model_status": model_status,
            "paper_open_allowed": paper_open_allowed,
            "allowed_signal_grades": allowed_grades,
            "sample_building_a_plus_only": model_status == "SAMPLE_BUILDING",
            "edge_groups": edge_groups_by_model.get(model_id, [])[:20],
        }

    suppressed = sorted([model_id for model_id, item in models.items() if item.get("model_status") == "SUPPRESSED_RESEARCH"])
    promising = sorted([model_id for model_id, item in models.items() if item.get("model_status") == "PROMISING"])
    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "block_id": BLOCK_ID,
            "source": {"source_mode": "OUTCOME_ACCOUNTING_CLEAN_SAMPLES_AND_EDGE_MATRIX"},
            "models": models,
            "summary": {
                "model_count": len(models),
                "suppressed_count": len(suppressed),
                "promising_count": len(promising),
                "suppressed_models": suppressed,
                "promising_models": promising,
                "clean_sample_count": int((accounting.get("summary") or {}).get("clean_sample_count") or len(clean_samples)),
            },
            "data_quality": {
                "level": "HIGH" if accounting else "MEDIUM",
                "missing_inputs": [name for name, payload in {"latest_outcome_accounting": accounting, "latest_research_edge_matrix": edge}.items() if not payload],
            },
            "reason_codes": [
                f"MODELS_{len(models)}",
                f"SUPPRESSED_{len(suppressed)}",
                f"PROMISING_{len(promising)}",
                "OUTCOME_ACCOUNTING_SSOT",
                "PAPER_ONLY",
                "NO_LIVE_EXECUTION",
                "NO_PRIVATE_API",
            ],
            "feeds_next": ["PAPER_TRADE_FACTORY", "TELEGRAM_RESEARCH_REPORTER"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str((clean_samples[-1] if clean_samples else {}).get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("model_survival_filter_history.jsonl", output)
    return output


def main() -> None:
    print(json.dumps(run_model_survival_filter(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
