"""Paper Trade Factory for validated research model clusters."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "PAPER_TRADE_FACTORY"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_paper_trade_factory.json"
HISTORY_PATH = DATA_DIR / "paper_trade_factory_history.jsonl"

MODEL_HUNTER_PATH = STATE_DIR / "latest_model_hunter.json"
SEMANTIC_VALIDATION_PATH = STATE_DIR / "latest_model_semantic_validation.json"
CLUSTERS_PATH = STATE_DIR / "latest_model_clusters.json"
COOLDOWN_PATH = STATE_DIR / "latest_model_cooldown.json"
SETUP_ACTIVATION_PATH = STATE_DIR / "latest_setup_family_activation.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
LIQUIDITY_PATH = STATE_DIR / "latest_liquidity_map.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
ATR_PATH = STATE_DIR / "latest_atr_state.json"


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


def _current_price(observation: dict[str, Any], dna: dict[str, Any]) -> float | None:
    price = _safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if price is not None:
        return price
    return _safe_float((((dna.get("1m") or {}).get("close"))))


def _paper_trade_id(seed: str, entry: float | None) -> str:
    raw = f"{seed}|{entry}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _target_reference(direction: str, entry: float, liquidity: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for level in liquidity.get("detected_levels") or []:
        price = _safe_float(level.get("price"))
        if price is None:
            continue
        if direction == "LONG" and price <= entry:
            continue
        if direction == "SHORT" and price >= entry:
            continue
        if best is None:
            best = level
            continue
        best_price = _safe_float(best.get("price"))
        if best_price is None:
            best = level
            continue
        if direction == "LONG" and price < best_price:
            best = level
        if direction == "SHORT" and price > best_price:
            best = level
    return best


def _compact_model(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_instance_id": model.get("model_instance_id"),
        "model_id": model.get("model_id"),
        "model_family": model.get("model_family"),
        "direction": model.get("direction"),
        "match_score": model.get("match_score"),
        "coherence_score": model.get("coherence_score"),
        "dominant_context": model.get("dominant_context"),
        "semantic_status": model.get("semantic_status"),
    }


def _singleton_cluster(model: dict[str, Any], source_mode: str) -> dict[str, Any]:
    cluster_id = f"SINGLETON_{model.get('model_instance_id')}"
    return {
        "cluster_id": cluster_id,
        "direction": model.get("direction"),
        "cluster_family": model.get("model_family"),
        "dominant_context": model.get("dominant_context"),
        "dominant_model_id": model.get("model_id"),
        "models": [model],
        "model_count": 1,
        "best_quality": model.get("quality"),
        "best_score": model.get("match_score"),
        "cluster_score": model.get("coherence_score") or model.get("match_score"),
        "paper_representative": model,
        "suppressed_duplicates": [],
        "reason_codes": [f"{source_mode}_SINGLETON_CLUSTER"],
    }


def _canonical_setup_family(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).upper()
    if any(token in text for token in ("LIQUIDITY_SWEEP_REVERSAL", "LSR_", "PLR_")):
        return "LIQUIDITY_SWEEP_REVERSAL"
    if any(token in text for token in ("ABSORPTION_REVERSAL", "ABSORPTION", "AR01", "DAF", "ICEBERG_ABSORPTION")):
        return "ABSORPTION_REVERSAL"
    if any(token in text for token in ("DOUBLE_DISTRIBUTION_REVERSAL", "VALUE_ROTATION", "BUSINESS_ZONE_ROTATION")):
        return "DOUBLE_DISTRIBUTION_REVERSAL"
    if any(token in text for token in ("TRAP_REVERSAL", "FAILED_BREAKOUT_TRAP", "STOP_RUN_ABSORPTION", "TRAP_BUYERS", "TRAP_SELLERS", "FCR")):
        return "TRAP_REVERSAL"
    if any(token in text for token in ("MOMENTUM_CONTINUATION", "ACCEPTANCE_BREAKOUT", "INITIATIVE_BREAKOUT", "MTF_ALIGNMENT", "VOLATILITY_EXPANSION_CONTINUATION", "CONTINUATION")):
        return "MOMENTUM_CONTINUATION"
    return "NO_ACTIVE_SETUP_FAMILY"


def _cluster_setup_family(cluster: dict[str, Any]) -> str:
    representative = cluster.get("paper_representative") or {}
    return _canonical_setup_family(
        cluster.get("cluster_family"),
        cluster.get("dominant_context"),
        cluster.get("dominant_model_id"),
        representative.get("model_family"),
        representative.get("model_id"),
        " ".join(str(item) for item in (cluster.get("model_families") or [])),
    )


def _activation_ready_clusters(activation: dict[str, Any]) -> list[dict[str, Any]]:
    if not activation or not bool(activation.get("ready_for_paper_research")):
        return []
    selected: list[dict[str, Any]] = []
    for cluster in activation.get("source_clusters") or []:
        if not isinstance(cluster, dict):
            continue
        direction = str(cluster.get("direction") or "UNKNOWN").upper()
        if direction in {"LONG", "SHORT"} and cluster.get("paper_representative"):
            selected.append(cluster)
    return selected


def _select_candidates(
    activation: dict[str, Any],
    semantic: dict[str, Any],
    clusters: dict[str, Any],
    cooldown: dict[str, Any],
) -> tuple[list[dict[str, Any]], str, list[str]]:
    activation_clusters = _activation_ready_clusters(activation)
    if activation_clusters:
        return activation_clusters, "SETUP_FAMILY_ACTIVATION_READY", ["SETUP_FAMILY_ACTIVATION_USED"]

    if cooldown:
        if cooldown.get("allowed_clusters"):
            return list(cooldown.get("allowed_clusters") or []), "MODEL_COOLDOWN_ALLOWED_CLUSTERS", ["COOLDOWN_LAYER_USED"]
        return [], "MODEL_COOLDOWN_BLOCKED", ["COOLDOWN_LAYER_USED", "NO_ALLOWED_CLUSTERS"]

    if clusters and clusters.get("clusters"):
        if semantic and semantic.get("validated_models"):
            return list(clusters.get("clusters") or []), "MODEL_CLUSTER_FALLBACK", ["COOLDOWN_MISSING", "CLUSTER_LAYER_USED"]
        return [], "MODEL_CLUSTER_BLOCKED", ["COOLDOWN_MISSING", "SEMANTIC_LAYER_MISSING"]

    if semantic and (semantic.get("validated_models") or semantic.get("blocked_models")):
        records = [_singleton_cluster(model, "SEMANTIC_VALIDATION") for model in (semantic.get("validated_models") or []) if model.get("paper_allowed")]
        return records, "MODEL_SEMANTIC_VALIDATION_FALLBACK", ["COOLDOWN_MISSING", "CLUSTERS_MISSING", "SEMANTIC_LAYER_USED"]

    return [], "NO_MODEL_INPUT", ["NO_TRADE_CANDIDATES"]


def run_paper_trade_factory() -> dict[str, Any]:
    hunter = _load_json(MODEL_HUNTER_PATH) or {}
    semantic = _load_json(SEMANTIC_VALIDATION_PATH) or {}
    clusters = _load_json(CLUSTERS_PATH) or {}
    cooldown = _load_json(COOLDOWN_PATH) or {}
    activation = _load_json(SETUP_ACTIVATION_PATH) or {}
    observation = _load_json(OBSERVATION_PATH) or {}
    dna = _load_json(DNA_PATH) or {}
    liquidity = _load_json(LIQUIDITY_PATH) or {}
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    atr = _load_json(ATR_PATH) or {}

    current_price = _current_price(observation, dna)
    atr_1m = _safe_float(((atr.get("1m") or {}).get("atr_14")))
    selected_clusters, source_selection_mode, selection_reason_codes = _select_candidates(activation, semantic, clusters, cooldown)
    trades: list[dict[str, Any]] = []

    activation_ready = bool(activation.get("ready_for_paper_research"))
    dominant_setup_family = str(activation.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY")
    activation_score = float(activation.get("activation_score") or 0.0)
    activation_reasons = list(activation.get("activation_reasons") or [])
    activation_source_models = list(activation.get("source_models") or [])
    activation_source_clusters = list(activation.get("source_clusters") or [])

    for cluster in selected_clusters:
        representative = dict(cluster.get("paper_representative") or {})
        direction = str(representative.get("direction") or cluster.get("direction") or "UNKNOWN").upper()
        if direction not in ("LONG", "SHORT"):
            continue

        entry = current_price
        invalid_reason = None
        reason_codes: list[str] = list(cluster.get("reason_codes") or [])
        if source_selection_mode == "MODEL_COOLDOWN_ALLOWED_CLUSTERS":
            reason_codes.append("COOLDOWN_PASSED")
        if source_selection_mode == "SETUP_FAMILY_ACTIVATION_READY":
            reason_codes.append("SETUP_FAMILY_ACTIVATION_READY")
        if entry is None or entry <= 0:
            invalid_reason = "INVALID_ENTRY_PRICE"

        if atr_1m is not None and atr_1m > 0 and entry is not None:
            risk_distance = max(atr_1m, entry * 0.001)
        else:
            risk_distance = entry * 0.002 if entry is not None else None
            reason_codes.append("FALLBACK_STOP_DISTANCE_USED")
        if entry is None or risk_distance is None or risk_distance <= 0:
            invalid_reason = invalid_reason or "RISK_DISTANCE_INVALID"

        stop_loss = None
        tp1 = None
        tp2 = None
        rr_tp1 = None
        rr_tp2 = None
        if invalid_reason is None and entry is not None and risk_distance is not None:
            if direction == "LONG":
                stop_loss = round(entry - risk_distance, 8)
                tp1 = round(entry + 1.5 * risk_distance, 8)
                tp2 = round(entry + 2.5 * risk_distance, 8)
            else:
                stop_loss = round(entry + risk_distance, 8)
                tp1 = round(entry - 1.5 * risk_distance, 8)
                tp2 = round(entry - 2.5 * risk_distance, 8)
            rr_tp1 = 1.5
            rr_tp2 = 2.5

        setup_family = dominant_setup_family if activation_ready else _cluster_setup_family(cluster)
        source_cluster = dict(cluster)
        source_cluster["paper_representative"] = representative
        trade = {
            "paper_trade_id": _paper_trade_id(str(cluster.get("cluster_id") or representative.get("model_instance_id")), entry),
            "model_instance_id": representative.get("model_instance_id"),
            "model_id": representative.get("model_id"),
            "model_family": representative.get("model_family") or cluster.get("cluster_family"),
            "setup_family": setup_family,
            "dominant_setup_family": setup_family,
            "activation_score": activation_score if activation_ready else float(cluster.get("cluster_score") or representative.get("coherence_score") or representative.get("match_score") or 0.0),
            "activation_reasons": activation_reasons if activation_ready else ["ACTIVATION_LAYER_NOT_READY_FALLBACK_TO_ALLOWED_CLUSTER"],
            "source_models": activation_source_models if activation_ready else [_compact_model(representative)],
            "source_clusters": activation_source_clusters if activation_ready else [source_cluster],
            "cluster_id": cluster.get("cluster_id"),
            "dominant_model_id": cluster.get("dominant_model_id") or representative.get("model_id"),
            "direction": direction,
            "quality": representative.get("quality"),
            "match_score": representative.get("match_score"),
            "semantic_status": representative.get("semantic_status", "UNKNOWN"),
            "coherence_score": representative.get("coherence_score") or cluster.get("cluster_score"),
            "cooldown_key": representative.get("cooldown_key") or cluster.get("cooldown_key"),
            "entry": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rr_tp1": rr_tp1,
            "rr_tp2": rr_tp2,
            "risk_distance": risk_distance,
            "target_reference": _target_reference(direction, entry or 0.0, liquidity) if entry is not None else None,
            "opened_at": _utc_now(),
            "max_holding_seconds": 1800,
            "status": "INVALID" if invalid_reason else "OPEN_CANDIDATE",
            "invalid_reason": invalid_reason,
            "reason_codes": sorted(set(reason_codes)),
            "source_model_instance": representative.get("source_model_instance") or representative,
            "source_cluster": source_cluster,
            "source_business_zone_ref": business_zone.get("timestamp_utc"),
        }
        trades.append(trade)

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(observation.get("symbol") or semantic.get("symbol") or hunter.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": source_selection_mode,
        },
        "paper_trades": trades,
        "summary": {
            "candidate_models": len(hunter.get("detected_models") or []),
            "validated_models": len(semantic.get("validated_models") or []),
            "cluster_count": len(clusters.get("clusters") or []),
            "allowed_clusters": len(cooldown.get("allowed_clusters") or []),
            "setup_family_activation_ready": activation_ready,
            "paper_trade_candidates": len([trade for trade in trades if trade.get("status") == "OPEN_CANDIDATE"]),
            "invalid_candidates": len([trade for trade in trades if trade.get("status") == "INVALID"]),
        },
        "reason_codes": [
            f"PAPER_TRADES_{len(trades)}",
            *selection_reason_codes,
            "LOW_QUALITY_MODELS_ALLOWED",
            "NO_LIVE_EXECUTION",
            "NO_PRIVATE_API",
            "PAPER_ONLY",
        ],
        "data_quality": {
            "level": "HIGH" if any((semantic, clusters, cooldown, activation)) else "LOW",
            "missing_inputs": [name for name, payload in {
                "latest_model_semantic_validation": semantic,
                "latest_model_clusters": clusters,
                "latest_model_cooldown": cooldown,
                "latest_setup_family_activation": activation,
                "latest_observation_factory": observation,
                "latest_mtf_candle_dna": dna,
                "latest_liquidity_map": liquidity,
                "latest_business_zone": business_zone,
                "latest_atr_state": atr,
            }.items() if not payload],
        },
        "raw_model_observability": {
            "raw_detected_models": list(hunter.get("detected_models") or []),
            "validated_models": list(semantic.get("validated_models") or []),
            "blocked_semantic_models": list(semantic.get("blocked_models") or []),
            "clusters": list(clusters.get("clusters") or []),
            "cooldown_blocked_clusters": list(cooldown.get("blocked_clusters") or []),
            "setup_family_activation": activation,
        },
        "feeds_next": [
            "RESEARCH_PAPER_LIFECYCLE_ENGINE",
            "RESEARCH_EDGE_MATRIX_ENGINE",
            "S15_FLOW_TO_SETUP_CONTEXT",
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
    print(json.dumps(run_paper_trade_factory(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
