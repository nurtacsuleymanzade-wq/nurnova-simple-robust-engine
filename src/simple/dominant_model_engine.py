"""Dominant model engine for semantic narrative clustering."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "DOMINANT_MODEL_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

MODEL_HUNTER_PATH = STATE_DIR / "latest_model_hunter.json"
SEMANTIC_PATH = STATE_DIR / "latest_semantic_validation.json"
OUTPUT_PATH = STATE_DIR / "latest_dominant_model.json"
HISTORY_PATH = DATA_DIR / "dominant_model_history.jsonl"

QUALITY_WEIGHT = {
    "A_PLUS": 1.0,
    "HIGH": 0.85,
    "MEDIUM": 0.7,
    "LOW": 0.55,
    "UNKNOWN": 0.4,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _semantic_direction(state_name: str, dominant_side: str) -> str:
    if state_name in {"INITIATIVE_BUYING", "SELLER_EXHAUSTION", "SELLER_TRAP"}:
        return "LONG"
    if state_name in {"INITIATIVE_SELLING", "BUYER_EXHAUSTION", "BUYER_TRAP"}:
        return "SHORT"
    if state_name == "ABSORPTION":
        if dominant_side == "BUYERS":
            return "LONG"
        if dominant_side == "SELLERS":
            return "SHORT"
    return "NEUTRAL"


def _state_family_group(state_name: str) -> str:
    if state_name in {"BUYER_EXHAUSTION", "BUYER_TRAP", "INITIATIVE_SELLING"}:
        return "SELLERS"
    if state_name in {"SELLER_EXHAUSTION", "SELLER_TRAP", "INITIATIVE_BUYING"}:
        return "BUYERS"
    if state_name in {"BALANCED", "COMPRESSION", "ROTATION"}:
        return "NEUTRAL"
    if state_name == "ABSORPTION":
        return "TRANSITION"
    return "NEUTRAL"


def _compatible_states(candidate_state: str, dominant_state: str) -> bool:
    if candidate_state == dominant_state:
        return True
    candidate_group = _state_family_group(candidate_state)
    dominant_group = _state_family_group(dominant_state)
    if candidate_group == dominant_group and candidate_group in {"BUYERS", "SELLERS"}:
        return True
    if dominant_state in {"BALANCED", "COMPRESSION", "ROTATION"} and candidate_state in {"BALANCED", "COMPRESSION", "ROTATION"}:
        return True
    if dominant_state == "ABSORPTION" and candidate_state in {"BUYER_EXHAUSTION", "SELLER_EXHAUSTION", "ABSORPTION"}:
        return True
    return False


def _infer_model_state(model: dict[str, Any], dominant_state: str) -> str:
    matched = set(model.get("matched_conditions") or [])
    direction = str(model.get("direction") or "UNKNOWN")
    model_id = str(model.get("model_id") or "")
    model_family = str(model.get("model_family") or "")

    if direction == "SHORT" and {"COND_BUYERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_SELLERS_DEFENDING"} <= matched:
        if "COND_TRAPPED_BUYERS" in matched and "COND_LIQUIDITY_SWEEP_UP" in matched:
            return "BUYER_TRAP"
        return "BUYER_EXHAUSTION"
    if direction == "LONG" and {"COND_SELLERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_BUYERS_DEFENDING"} <= matched:
        if "COND_TRAPPED_SELLERS" in matched and "COND_LIQUIDITY_SWEEP_DOWN" in matched:
            return "SELLER_TRAP"
        return "SELLER_EXHAUSTION"
    if direction == "LONG" and {"COND_REGIME_MOMENTUM", "COND_BUYERS_ATTACKING"} & matched and "COND_ACCEPTANCE" in matched:
        return "INITIATIVE_BUYING"
    if direction == "SHORT" and {"COND_REGIME_MOMENTUM", "COND_SELLERS_ATTACKING"} & matched and "COND_ACCEPTANCE" in matched:
        return "INITIATIVE_SELLING"
    if "ABSORPTION" in model_family or "ABSORPTION" in model_id:
        return "BUYER_EXHAUSTION" if direction == "SHORT" else "SELLER_EXHAUSTION"
    if "TRAP" in model_family or "TRAP" in model_id:
        return "BUYER_EXHAUSTION" if direction == "SHORT" else "SELLER_EXHAUSTION"
    if model_family in {"VALUE_ROTATION", "BUSINESS_ZONE_ROTATION"}:
        return "ROTATION"
    if model_family == "SCENARIO_COMPRESSION_BREAK":
        return "COMPRESSION"
    if model_family in {"INITIATIVE_BREAKOUT", "TREND_IGNITION", "TREND_CONTINUATION", "MOMENTUM_CONTINUATION"}:
        return "INITIATIVE_BUYING" if direction == "LONG" else "INITIATIVE_SELLING"
    if model_family in {"FAILED_CONTINUATION_REVERSAL", "FAILED_BREAKOUT_TRAP", "CANDLE_QUALITY_REVERSAL", "EFFORT_VS_RESULT"}:
        return "BUYER_EXHAUSTION" if direction == "SHORT" else "SELLER_EXHAUSTION"
    if model_family in {"VOLATILITY_COLLAPSE_REVERSION", "DOUBLE_DISTRIBUTION_REVERSAL"}:
        return "BUYER_EXHAUSTION" if direction == "SHORT" else "SELLER_EXHAUSTION"
    if direction == _semantic_direction(dominant_state, "NEUTRAL") and _compatible_states(dominant_state, dominant_state):
        return dominant_state
    return "BALANCED"


def _cluster_score(cluster_models: list[dict[str, Any]], dominant_state: str) -> tuple[float, str]:
    if not cluster_models:
        return 0.0, "LOW"
    match_avg = sum(float(model.get("match_score") or 0.0) for model in cluster_models) / len(cluster_models)
    quality_avg = sum(QUALITY_WEIGHT.get(str(model.get("quality") or "UNKNOWN"), 0.4) for model in cluster_models) / len(cluster_models)
    aligned = sum(1 for model in cluster_models if _compatible_states(str(model.get("semantic_target_state") or "BALANCED"), dominant_state))
    alignment_ratio = aligned / len(cluster_models)
    score = round(min(0.99, 0.5 * match_avg + 0.3 * quality_avg + 0.2 * alignment_ratio), 4)
    if score >= 0.88:
        return score, "VERY_HIGH"
    if score >= 0.74:
        return score, "HIGH"
    if score >= 0.58:
        return score, "MEDIUM"
    return score, "LOW"


def _cluster_id(symbol: str, direction: str, semantic_state: str, model_ids: list[str]) -> str:
    raw = f"{symbol}|{direction}|{semantic_state}|{'|'.join(sorted(model_ids))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _compact_model_summary(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_instance_id": model.get("model_instance_id"),
        "model_id": model.get("model_id"),
        "model_family": model.get("model_family"),
        "direction": model.get("direction"),
        "quality": model.get("quality"),
        "match_score": model.get("match_score"),
        "semantic_target_state": model.get("semantic_target_state"),
        "canonical_semantic_state": model.get("canonical_semantic_state"),
        "semantic_conflict": bool(model.get("semantic_conflict")),
        "contradicts_dominant_narrative": bool(model.get("contradicts_dominant_narrative")),
    }


def run_dominant_model_engine() -> dict[str, Any]:
    hunter = _load_json(MODEL_HUNTER_PATH) or {}
    semantic = _load_json(SEMANTIC_PATH) or {}
    detected_models = list(hunter.get("detected_models") or [])
    semantic_truth = semantic.get("market_semantic_truth") or {}
    semantic_state = str(semantic_truth.get("market_state") or "BALANCED")
    dominant_side = str(semantic_truth.get("dominant_side") or "NEUTRAL")
    semantic_direction = _semantic_direction(semantic_state, dominant_side)
    symbol = str(hunter.get("symbol") or semantic.get("symbol") or "BTCUSDT")

    clusters: dict[tuple[str, str], list[dict[str, Any]]] = {}
    annotated_models: list[dict[str, Any]] = []
    for model in detected_models:
        annotated = dict(model)
        inferred_state = _infer_model_state(model, semantic_state)
        if str(model.get("direction") or "") == semantic_direction and _compatible_states(inferred_state, semantic_state):
            canonical_state = semantic_state
        else:
            canonical_state = inferred_state
        semantic_conflict = str(model.get("direction") or "") not in {"LONG", "SHORT"} or (
            semantic_direction != "NEUTRAL"
            and (
                str(model.get("direction") or "") != semantic_direction
                or not _compatible_states(canonical_state, semantic_state)
            )
        )
        annotated["semantic_target_state"] = inferred_state
        annotated["canonical_semantic_state"] = canonical_state
        annotated["semantic_conflict"] = semantic_conflict
        annotated["contradicts_dominant_narrative"] = False
        annotated_models.append(annotated)
        key = (str(model.get("direction") or "UNKNOWN"), canonical_state)
        clusters.setdefault(key, []).append(annotated)

    cluster_payloads: list[dict[str, Any]] = []
    for (direction, cluster_state), items in clusters.items():
        cluster_score, alignment = _cluster_score(items, semantic_state)
        representative = max(
            items,
            key=lambda item: (
                QUALITY_WEIGHT.get(str(item.get("quality") or "UNKNOWN"), 0.4),
                float(item.get("match_score") or 0.0),
                -float(item.get("invalidation_score") or 0.0),
                len(item.get("matched_conditions") or []),
            ),
        )
        model_ids = [str(item.get("model_id") or "UNKNOWN") for item in items]
        cluster_payloads.append({
            "cluster_id": _cluster_id(symbol, direction, cluster_state, model_ids),
            "direction": direction,
            "semantic_state": cluster_state,
            "model_ids": model_ids,
            "model_summaries": [_compact_model_summary(item) for item in items],
            "model_count": len(items),
            "dominant_model_id": representative.get("model_id"),
            "cluster_score": cluster_score,
            "semantic_alignment": alignment,
            "representative_model": _compact_model_summary(representative),
            "_full_models": items,
            "_representative_full": representative,
        })

    def _cluster_rank(item: dict[str, Any]) -> tuple[float, int, int]:
        direction_bonus = 1 if semantic_direction != "NEUTRAL" and item.get("direction") == semantic_direction else 0
        state_bonus = 1 if item.get("semantic_state") == semantic_state else 0
        return (
            float(item.get("cluster_score") or 0.0) + direction_bonus * 0.08 + state_bonus * 0.08,
            int(item.get("model_count") or 0),
            len(item.get("model_ids") or []),
        )

    dominant_cluster = max(cluster_payloads, key=_cluster_rank, default=None)

    contradicting_models: list[str] = []
    opposing_direction_count = 0
    if dominant_cluster:
        dominant_direction = str(dominant_cluster.get("direction") or "NEUTRAL")
        dominant_state = str(dominant_cluster.get("semantic_state") or semantic_state)
        dominant_model_ids = set(dominant_cluster.get("model_ids") or [])
        for annotated in annotated_models:
            contradicts = str(annotated.get("model_id") or "") not in dominant_model_ids and (
                dominant_direction != "NEUTRAL"
                and (
                    str(annotated.get("direction") or "") != dominant_direction
                    or not _compatible_states(str(annotated.get("canonical_semantic_state") or "BALANCED"), dominant_state)
                )
            )
            annotated["contradicts_dominant_narrative"] = contradicts
            if contradicts:
                contradicting_models.append(str(annotated.get("model_id") or "UNKNOWN"))
                if str(annotated.get("direction") or "") != dominant_direction:
                    opposing_direction_count += 1
        final_bias = dominant_direction
    else:
        dominant_direction = "NEUTRAL"
        dominant_state = semantic_state
        final_bias = "NEUTRAL"

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": symbol,
        "block_id": BLOCK_ID,
        "dominant_direction": dominant_direction,
        "dominant_semantic_state": dominant_state,
        "dominant_models": list(dominant_cluster.get("model_ids") or []) if dominant_cluster else [],
        "cluster_score": float(dominant_cluster.get("cluster_score") or 0.0) if dominant_cluster else 0.0,
        "semantic_alignment": str(dominant_cluster.get("semantic_alignment") or "LOW") if dominant_cluster else "LOW",
        "contradicting_models": contradicting_models,
        "final_research_bias": final_bias,
        "dominant_model_cluster": {
            "cluster_id": dominant_cluster.get("cluster_id") if dominant_cluster else None,
            "direction": dominant_direction,
            "semantic_state": dominant_state,
            "dominant_model_id": dominant_cluster.get("dominant_model_id") if dominant_cluster else None,
            "cluster_models": dominant_cluster.get("_full_models") if dominant_cluster else [],
            "cluster_model_summaries": [_compact_model_summary(item) for item in (dominant_cluster.get("_full_models") or [])] if dominant_cluster else [],
            "model_count": dominant_cluster.get("model_count") if dominant_cluster else 0,
            "cluster_score": dominant_cluster.get("cluster_score") if dominant_cluster else 0.0,
            "semantic_alignment": dominant_cluster.get("semantic_alignment") if dominant_cluster else "LOW",
            "representative_model": dominant_cluster.get("_representative_full") if dominant_cluster else None,
        },
        "model_annotations": [_compact_model_summary(item) for item in annotated_models],
        "clusters": [
            {key: value for key, value in cluster.items() if not key.startswith("_")}
            for cluster in cluster_payloads
        ],
        "summary": {
            "input_detected_models": len(detected_models),
            "cluster_count": len(cluster_payloads),
            "dominant_cluster_models": int(dominant_cluster.get("model_count") or 0) if dominant_cluster else 0,
            "contradicting_model_count": len(contradicting_models),
            "opposing_direction_count": opposing_direction_count,
        },
        "source": {
            "source_mode": "MODEL_CLUSTER_BY_SEMANTIC_NARRATIVE",
            "semantic_state": semantic_state,
            "semantic_direction": semantic_direction,
        },
        "data_quality": {
            "level": "HIGH" if hunter and semantic else "LOW",
            "missing_inputs": [
                name
                for name, payload in {
                    "latest_model_hunter": hunter,
                    "latest_semantic_validation": semantic,
                }.items()
                if not payload
            ],
        },
        "reason_codes": [
            f"DOMINANT_DIRECTION_{dominant_direction}",
            f"DOMINANT_STATE_{dominant_state}",
            f"CONTRADICTING_MODELS_{len(contradicting_models)}",
            "RAW_MODELS_PRESERVED",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "PAPER_TRADE_FACTORY",
            "RESEARCH_PAPER_LIFECYCLE_ENGINE",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_dominant_model_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
