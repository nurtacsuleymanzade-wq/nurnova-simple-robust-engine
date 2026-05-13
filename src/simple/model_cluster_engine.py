"""Collapse semantically coherent model duplicates into research clusters."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MODEL_CLUSTER_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

VALIDATION_PATH = STATE_DIR / "latest_model_semantic_validation.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
OUTPUT_PATH = STATE_DIR / "latest_model_clusters.json"
HISTORY_PATH = DATA_DIR / "model_clusters_history.jsonl"


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


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quality_rank(level: Any) -> float:
    return {
        "A_PLUS": 1.0,
        "HIGH": 0.85,
        "MEDIUM": 0.7,
        "LOW": 0.55,
    }.get(str(level or "UNKNOWN").upper(), 0.4)


def _entry_price(observation: dict[str, Any], dna: dict[str, Any]) -> float | None:
    price = _safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if price is not None:
        return price
    return _safe_float((((dna.get("1m") or {}).get("close"))))


def _entry_bucket(entry: float | None) -> float | None:
    if entry is None or entry <= 0:
        return None
    bucket_size = entry * 0.0005
    if bucket_size <= 0:
        return None
    return round(round(entry / bucket_size) * bucket_size, 8)


def _timestamp_bucket(model: dict[str, Any]) -> str:
    timestamp = str(model.get("timestamp_utc") or "")
    return timestamp[:16] if timestamp else "UNKNOWN"


def _top_condition_group(model: dict[str, Any]) -> str:
    matched = [str(item).upper() for item in (model.get("matched_conditions") or [])]
    groups = [
        ("LIQUIDITY_SWEEP", ("SWEEP", "STOP_RUN")),
        ("TRAP", ("TRAP", "TRAPPED")),
        ("ABSORPTION", ("ABSORPTION",)),
        ("DELTA_DIVERGENCE", ("DIVERGENCE",)),
        ("VALUE_AUCTION", ("VALUE", "ACCEPTANCE", "REJECTION")),
        ("STRUCTURE_FLOW", ("STRUCTURE", "BOS", "CHOCH", "MSS")),
        ("MOMENTUM", ("REAL_", "MOMENTUM", "CONTINUATION")),
    ]
    for name, tokens in groups:
        if any(any(token in condition for token in tokens) for condition in matched):
            return name
    return "GENERAL"


def _cluster_id(symbol: str, parts: tuple[Any, ...]) -> str:
    raw = "|".join(str(part) for part in (symbol, *parts))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _representative_key(model: dict[str, Any]) -> tuple[float, float, float, int]:
    return (
        _quality_rank(model.get("quality")),
        float(model.get("match_score") or 0.0),
        -(float(model.get("invalidation_score") or 0.0)),
        len(model.get("matched_conditions") or []),
    )


def _cluster_score(models: list[dict[str, Any]], representative: dict[str, Any]) -> float:
    if not models:
        return 0.0
    avg_match = sum(float(item.get("match_score") or 0.0) for item in models) / len(models)
    avg_coherence = sum(float(item.get("coherence_score") or 0.0) for item in models) / len(models)
    size_factor = min(1.0, len(models) / 4)
    score = (float(representative.get("match_score") or 0.0) * 0.35) + (avg_match * 0.25) + (avg_coherence * 0.25) + (size_factor * 0.15)
    return round(max(0.0, min(1.0, score)), 4)


def run_model_cluster_engine() -> dict[str, Any]:
    validation = _load_json(VALIDATION_PATH) or {}
    observation = _load_json(OBSERVATION_PATH) or {}
    dna = _load_json(DNA_PATH) or {}
    models = list(validation.get("validated_models") or [])
    symbol = str(observation.get("symbol") or validation.get("symbol") or "BTCUSDT")
    current_entry = _entry_price(observation, dna)
    entry_zone_bucket = _entry_bucket(current_entry)

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for model in models:
        enriched = dict(model)
        enriched["entry_zone_hint"] = current_entry
        enriched["entry_zone_bucket"] = entry_zone_bucket
        key = (
            str(model.get("direction") or "UNKNOWN"),
            str(model.get("dominant_context") or "UNKNOWN"),
            _timestamp_bucket(model),
            entry_zone_bucket,
            _top_condition_group(model),
        )
        grouped.setdefault(key, []).append(enriched)

    clusters: list[dict[str, Any]] = []
    suppressed_duplicate_count = 0
    for key, items in grouped.items():
        representative = max(items, key=_representative_key)
        suppressed_duplicates = [item for item in items if item.get("model_instance_id") != representative.get("model_instance_id")]
        suppressed_duplicate_count += len(suppressed_duplicates)
        cluster_direction, dominant_context, timestamp_bucket, zone_bucket, top_group = key
        model_families = sorted({str(item.get("model_family") or "UNKNOWN") for item in items})
        cluster_family = dominant_context if len(model_families) > 1 else model_families[0]
        cluster = {
            "cluster_id": _cluster_id(symbol, key),
            "direction": cluster_direction,
            "cluster_family": cluster_family,
            "model_families": model_families,
            "dominant_context": dominant_context,
            "timestamp_bucket": timestamp_bucket,
            "entry_zone_bucket": zone_bucket,
            "top_condition_group": top_group,
            "dominant_model_id": representative.get("model_id"),
            "models": items,
            "model_count": len(items),
            "best_quality": representative.get("quality"),
            "best_score": representative.get("match_score"),
            "cluster_score": _cluster_score(items, representative),
            "paper_representative": representative,
            "suppressed_duplicates": suppressed_duplicates,
            "reason_codes": [f"SUPPRESSED_DUPLICATES_{len(suppressed_duplicates)}"] if suppressed_duplicates else ["SINGLE_MODEL_CLUSTER"],
        }
        clusters.append(cluster)

    clusters.sort(key=lambda item: (float(item.get("cluster_score") or 0.0), item.get("model_count") or 0), reverse=True)
    output = {
        "timestamp_utc": _utc_now(),
        "symbol": symbol,
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "SEMANTIC_VALIDATION_CLUSTERING",
        },
        "clusters": clusters,
        "summary": {
            "validated_models": len(models),
            "cluster_count": len(clusters),
            "suppressed_duplicate_count": suppressed_duplicate_count,
        },
        "reason_codes": [
            f"VALIDATED_MODELS_{len(models)}",
            f"CLUSTERS_{len(clusters)}",
            f"SUPPRESSED_DUPLICATES_{suppressed_duplicate_count}",
        ],
        "data_quality": {
            "level": "HIGH" if validation else "LOW",
            "missing_inputs": [name for name, payload in {
                "latest_model_semantic_validation": validation,
                "latest_observation_factory": observation,
                "latest_mtf_candle_dna": dna,
            }.items() if not payload],
        },
        "feeds_next": [
            "MODEL_COOLDOWN_ENGINE",
            "PAPER_TRADE_FACTORY",
            "RESEARCH_PAPER_LIFECYCLE_ENGINE",
            "RESEARCH_EDGE_MATRIX_ENGINE",
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
    print(json.dumps(run_model_cluster_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
