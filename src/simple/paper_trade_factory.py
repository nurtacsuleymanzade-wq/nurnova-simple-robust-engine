"""Paper Trade Factory for validated research model clusters."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.simple.jsonl_tail_reader import safe_read_json
from src.simple.research_runtime import (
    append_jsonl,
    current_runtime_context,
    load_json,
    safe_float,
    source_state_refs_from_paths,
    stamp_payload,
    utc_now,
    write_json,
)

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
RESEARCH_LIFECYCLE_PATH = STATE_DIR / "latest_research_paper_lifecycle.json"
RESEARCH_LIFECYCLE_HISTORY_PATH = DATA_DIR / "research_paper_lifecycle_history.jsonl"

MAX_OPEN_TOTAL = 20
MAX_OPEN_PER_MODEL_ID = 1
MAX_OPEN_PER_FAMILY_DIRECTION = 3
NEW_TRADES_CAP_PER_LOOP = 3
ALLOWED_RESEARCH_BANDS = {"STRONG_ACTIVE", "ACTIVE", "EARLY_RESEARCH"}
MAX_TOP_CANDIDATES = 20


def _current_price(observation: dict[str, Any], dna: dict[str, Any]) -> float | None:
    price = safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if price is not None:
        return price
    return safe_float((((dna.get("1m") or {}).get("close"))))


def _paper_trade_id(seed: str, entry: float | None) -> str:
    raw = f"{seed}|{entry}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _target_reference(direction: str, entry: float, liquidity: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for level in liquidity.get("detected_levels") or []:
        price = safe_float(level.get("price"))
        if price is None:
            continue
        if direction == "LONG" and price <= entry:
            continue
        if direction == "SHORT" and price >= entry:
            continue
        if best is None:
            best = level
            continue
        best_price = safe_float(best.get("price"))
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


def _cluster_priority(cluster: dict[str, Any], dominant_setup_family: str) -> tuple[float, float]:
    cluster_score = safe_float(cluster.get("cluster_score")) or 0.0
    setup_family = _cluster_setup_family(cluster)
    family_bonus = 1.0 if setup_family == dominant_setup_family else 0.0
    return family_bonus, cluster_score


def _activation_ready_clusters(activation: dict[str, Any]) -> list[dict[str, Any]]:
    activation_band = str(activation.get("activation_band") or "").upper()
    if (
        not activation
        or not bool(activation.get("ready_for_paper_research"))
        or activation_band not in ALLOWED_RESEARCH_BANDS
    ):
        return []

    activation_direction = str(activation.get("direction") or "NEUTRAL").upper()
    selected: list[dict[str, Any]] = []
    for cluster in activation.get("source_clusters") or []:
        if not isinstance(cluster, dict):
            continue
        representative = cluster.get("paper_representative") or {}
        direction = str(representative.get("direction") or cluster.get("direction") or "UNKNOWN").upper()
        if direction not in {"LONG", "SHORT"}:
            continue
        if activation_direction in {"LONG", "SHORT"} and direction != activation_direction:
            continue
        if representative:
            selected.append(cluster)
    dominant_setup_family = str(activation.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY")
    return sorted(
        selected,
        key=lambda item: _cluster_priority(item, dominant_setup_family),
        reverse=True,
    )


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
        records = [
            _singleton_cluster(model, "SEMANTIC_VALIDATION")
            for model in (semantic.get("validated_models") or [])
            if model.get("paper_allowed")
        ]
        return records, "MODEL_SEMANTIC_VALIDATION_FALLBACK", ["COOLDOWN_MISSING", "CLUSTERS_MISSING", "SEMANTIC_LAYER_USED"]

    return [], "NO_MODEL_INPUT", ["NO_TRADE_CANDIDATES"]


def _family_direction_key(trade: dict[str, Any]) -> str:
    family = str(trade.get("setup_family") or trade.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY")
    direction = str(trade.get("direction") or "UNKNOWN").upper()
    return f"{family}|{direction}"


def _context_contradiction_key(trade: dict[str, Any]) -> str:
    return "|".join(
        [
            str(trade.get("symbol") or "UNKNOWN"),
            str(trade.get("context_id") or "UNKNOWN"),
            str(trade.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY"),
            str(trade.get("liquidity_event") or "UNKNOWN"),
        ]
    )


def _model_family_context_key(trade: dict[str, Any]) -> str:
    return "|".join(
        [
            str(trade.get("symbol") or "UNKNOWN"),
            str(trade.get("context_id") or "UNKNOWN"),
            str(trade.get("model_family") or "UNKNOWN"),
        ]
    )


def _model_id_key(trade: dict[str, Any]) -> str:
    return str(
        trade.get("model_instance_id")
        or trade.get("model_id")
        or trade.get("dominant_model_id")
        or trade.get("cluster_id")
        or "UNKNOWN_MODEL"
    )


def _lifecycle_open_state(
    lifecycle: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str], dict[str, set[str]], dict[str, set[str]]]:
    open_trades = [trade for trade in (lifecycle.get("open_trades") or []) if str(trade.get("status") or "").upper() == "OPEN"]
    open_by_model_id: Counter[str] = Counter()
    open_by_family_direction: Counter[str] = Counter()
    open_context_directions: dict[str, set[str]] = {}
    open_model_family_directions: dict[str, set[str]] = {}
    for trade in open_trades:
        open_by_model_id[_model_id_key(trade)] += 1
        open_by_family_direction[_family_direction_key(trade)] += 1
        open_context_directions.setdefault(_context_contradiction_key(trade), set()).add(str(trade.get("direction") or "UNKNOWN").upper())
        open_model_family_directions.setdefault(_model_family_context_key(trade), set()).add(str(trade.get("direction") or "UNKNOWN").upper())
    return open_trades, open_by_model_id, open_by_family_direction, open_context_directions, open_model_family_directions


def _build_trade(
    cluster: dict[str, Any],
    source_selection_mode: str,
    current_price: float | None,
    atr_1m: float | None,
    liquidity: dict[str, Any],
    business_zone: dict[str, Any],
    context: dict[str, Any],
    activation_ready: bool,
    dominant_setup_family: str,
    activation_score: float,
    activation_reasons: list[str],
    activation_source_models: list[dict[str, Any]],
    activation_source_clusters: list[dict[str, Any]],
    activation_band: str,
    activation_risk_tags: list[str],
) -> dict[str, Any]:
    representative = dict(cluster.get("paper_representative") or {})
    direction = str(representative.get("direction") or cluster.get("direction") or "UNKNOWN").upper()
    setup_family = _cluster_setup_family(cluster)
    if setup_family == "NO_ACTIVE_SETUP_FAMILY" and activation_ready:
        setup_family = dominant_setup_family

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

    source_cluster = dict(cluster)
    source_cluster["paper_representative"] = representative
    source_state_refs = source_state_refs_from_paths(
        {
            "setup_family_activation": SETUP_ACTIVATION_PATH,
            "observation_factory": OBSERVATION_PATH,
            "mtf_candle_dna": DNA_PATH,
            "liquidity_map": LIQUIDITY_PATH,
            "business_zone": BUSINESS_ZONE_PATH,
            "atr_state": ATR_PATH,
            "research_paper_lifecycle": RESEARCH_LIFECYCLE_PATH,
        }
    )
    market_regime = str(representative.get("market_regime") or "UNKNOWN")
    direction_resolution = representative.get("direction_resolution") or {"resolution_mode": "UNRESOLVED"}
    return {
        "paper_trade_id": _paper_trade_id(str(cluster.get("cluster_id") or representative.get("model_instance_id")), entry),
        "context_id": context.get("context_id"),
        "loop_id": context.get("loop_id"),
        "symbol": context.get("symbol"),
        "model_instance_id": representative.get("model_instance_id"),
        "model_id": representative.get("model_id"),
        "model_family": representative.get("model_family") or cluster.get("cluster_family"),
        "setup_family": setup_family,
        "dominant_setup_family": dominant_setup_family if activation_ready else setup_family,
        "activation_score": activation_score if activation_ready else float(cluster.get("cluster_score") or representative.get("coherence_score") or representative.get("match_score") or 0.0),
        "activation_band": activation_band if activation_ready else "CLUSTER_FALLBACK",
        "risk_tags": activation_risk_tags if activation_ready else list(representative.get("risk_tags") or cluster.get("risk_tags") or []),
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
        "direction_resolution": direction_resolution,
        "market_regime": market_regime,
        "candle_category": representative.get("candle_category") or "UNKNOWN",
        "structure_label": representative.get("structure_label") or "UNKNOWN",
        "liquidity_event": representative.get("liquidity_event") or cluster.get("liquidity_event") or "UNKNOWN",
        "entry": entry,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "rr_tp1": rr_tp1,
        "rr_tp2": rr_tp2,
        "risk_distance": risk_distance,
        "target_reference": _target_reference(direction, entry or 0.0, liquidity) if entry is not None else None,
        "opened_at_utc": utc_now(),
        "max_holding_seconds": 1800,
        "status": "INVALID" if invalid_reason else "OPEN",
        "invalid_reason": invalid_reason,
        "invalid_for_edge": bool(invalid_reason) or not context.get("context_id") or not representative.get("model_id"),
        "reason_codes": sorted(set(reason_codes)),
        "source_model_instance": representative.get("source_model_instance") or representative,
        "source_cluster": source_cluster,
        "source_business_zone_ref": business_zone.get("timestamp_utc"),
        "source_state_refs": source_state_refs,
    }


def _compact_trade_snapshot(trade: dict[str, Any]) -> dict[str, Any]:
    keep_fields = (
        "paper_trade_id",
        "context_id",
        "loop_id",
        "symbol",
        "model_id",
        "model_family",
        "setup_family",
        "dominant_setup_family",
        "direction",
        "entry",
        "stop_loss",
        "tp1",
        "tp2",
        "risk_distance",
        "status",
        "invalid_reason",
        "activation_band",
        "activation_score",
        "reason_codes",
        "opened_at_utc",
        "max_holding_seconds",
        "invalid_for_edge",
    )
    return {field: trade.get(field) for field in keep_fields if field in trade}


def run_paper_trade_factory() -> dict[str, Any]:
    context = current_runtime_context()
    hunter = load_json(MODEL_HUNTER_PATH) or {}
    semantic = load_json(SEMANTIC_VALIDATION_PATH) or {}
    clusters = load_json(CLUSTERS_PATH) or {}
    cooldown = load_json(COOLDOWN_PATH) or {}
    activation = load_json(SETUP_ACTIVATION_PATH) or {}
    observation = load_json(OBSERVATION_PATH) or {}
    dna = load_json(DNA_PATH) or {}
    liquidity = load_json(LIQUIDITY_PATH) or {}
    business_zone = load_json(BUSINESS_ZONE_PATH) or {}
    atr = load_json(ATR_PATH) or {}
    lifecycle, lifecycle_reason = safe_read_json(RESEARCH_LIFECYCLE_PATH, default={}, max_bytes=500_000)
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}

    current_price = _current_price(observation, dna)
    atr_1m = safe_float(((atr.get("1m") or {}).get("atr_14")))
    selected_clusters, source_selection_mode, selection_reason_codes = _select_candidates(activation, semantic, clusters, cooldown)

    activation_band = str(activation.get("activation_band") or "WATCH_ONLY").upper()
    activation_ready = bool(activation.get("ready_for_paper_research")) and activation_band in ALLOWED_RESEARCH_BANDS
    dominant_setup_family = str(activation.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY")
    activation_score = float(activation.get("activation_score") or 0.0)
    activation_reasons = list(activation.get("activation_reasons") or [])
    activation_risk_tags = list(activation.get("risk_tags") or [])
    activation_source_models = list(activation.get("source_models") or [])
    activation_source_clusters = list(activation.get("source_clusters") or [])

    open_trades, open_by_model_id, open_by_family_direction, open_context_directions, open_model_family_directions = _lifecycle_open_state(lifecycle)
    pending_by_model_id: Counter[str] = Counter()
    pending_by_family_direction: Counter[str] = Counter()
    pending_context_directions: dict[str, set[str]] = {}
    pending_model_family_directions: dict[str, set[str]] = {}
    allowed_research_band_counts: Counter[str] = Counter()
    paper_safety = {
        "max_new_trades_per_loop": NEW_TRADES_CAP_PER_LOOP,
        "max_open_total": MAX_OPEN_TOTAL,
        "max_open_per_model_id": MAX_OPEN_PER_MODEL_ID,
        "max_open_per_family_direction": MAX_OPEN_PER_FAMILY_DIRECTION,
        "contradiction_guard_enabled": True,
        "contradiction_key_fields": ["symbol", "context_id", "dominant_setup_family", "liquidity_event"],
        "blocked_by_context_direction_conflict": 0,
        "blocked_by_model_family_direction_conflict": 0,
        "blocked_by_open_limit": 0,
        "blocked_by_family_limit": 0,
        "blocked_by_model_id_limit": 0,
        "blocked_by_new_trade_cap": 0,
        "allowed_research_band_counts": {},
    }

    trades: list[dict[str, Any]] = []
    new_trade_slots_used = 0

    ranked_clusters = sorted(
        selected_clusters,
        key=lambda item: _cluster_priority(item, dominant_setup_family),
        reverse=True,
    )

    for cluster in ranked_clusters:
        trade = _build_trade(
            cluster=cluster,
            source_selection_mode=source_selection_mode,
            current_price=current_price,
            atr_1m=atr_1m,
            liquidity=liquidity,
            business_zone=business_zone,
            context=context,
            activation_ready=activation_ready,
            dominant_setup_family=dominant_setup_family,
            activation_score=activation_score,
            activation_reasons=activation_reasons,
            activation_source_models=activation_source_models,
            activation_source_clusters=activation_source_clusters,
            activation_band=activation_band,
            activation_risk_tags=activation_risk_tags,
        )

        if trade.get("status") == "INVALID":
            trades.append(trade)
            continue

        model_id_key = _model_id_key(trade)
        family_direction_key = _family_direction_key(trade)
        context_conflict_key = _context_contradiction_key(trade)
        model_family_context_key = _model_family_context_key(trade)
        direction = str(trade.get("direction") or "UNKNOWN").upper()
        total_open_after_pending = len(open_trades) + new_trade_slots_used
        model_open_after_pending = open_by_model_id[model_id_key] + pending_by_model_id[model_id_key]
        family_direction_open_after_pending = (
            open_by_family_direction[family_direction_key]
            + pending_by_family_direction[family_direction_key]
        )
        seen_context_directions = set(open_context_directions.get(context_conflict_key, set()))
        seen_context_directions.update(pending_context_directions.get(context_conflict_key, set()))
        seen_model_family_directions = set(open_model_family_directions.get(model_family_context_key, set()))
        seen_model_family_directions.update(pending_model_family_directions.get(model_family_context_key, set()))

        guard_reason = None
        if any(existing != direction for existing in seen_context_directions if existing in {"LONG", "SHORT"}):
            paper_safety["blocked_by_context_direction_conflict"] += 1
            guard_reason = "CONTEXT_DIRECTION_CONFLICT"
        elif any(existing != direction for existing in seen_model_family_directions if existing in {"LONG", "SHORT"}):
            paper_safety["blocked_by_model_family_direction_conflict"] += 1
            guard_reason = "MODEL_FAMILY_DIRECTION_CONFLICT"
        elif total_open_after_pending >= MAX_OPEN_TOTAL:
            paper_safety["blocked_by_open_limit"] += 1
            guard_reason = "OPEN_LIMIT_REACHED"
        elif new_trade_slots_used >= NEW_TRADES_CAP_PER_LOOP:
            paper_safety["blocked_by_new_trade_cap"] += 1
            guard_reason = "NEW_TRADES_CAP_PER_LOOP_REACHED"
        elif model_open_after_pending >= MAX_OPEN_PER_MODEL_ID:
            paper_safety["blocked_by_model_id_limit"] += 1
            guard_reason = "MODEL_ID_ALREADY_OPEN"
        elif family_direction_open_after_pending >= MAX_OPEN_PER_FAMILY_DIRECTION:
            paper_safety["blocked_by_family_limit"] += 1
            guard_reason = "SETUP_FAMILY_DIRECTION_LIMIT_REACHED"

        if guard_reason:
            trade["status"] = "BLOCKED"
            trade["invalid_reason"] = guard_reason
            trade["reason_codes"] = sorted(set([*(trade.get("reason_codes") or []), guard_reason]))
            trades.append(trade)
            continue

        new_trade_slots_used += 1
        pending_by_model_id[model_id_key] += 1
        pending_by_family_direction[family_direction_key] += 1
        pending_context_directions.setdefault(context_conflict_key, set()).add(direction)
        pending_model_family_directions.setdefault(model_family_context_key, set()).add(direction)
        allowed_research_band_counts[str(trade.get("activation_band") or "UNKNOWN")] += 1
        trades.append(trade)

    paper_safety["allowed_research_band_counts"] = dict(allowed_research_band_counts)
    newest_opened_this_loop = [
        _compact_trade_snapshot(trade)
        for trade in trades
        if str(trade.get("status") or "").upper() == "OPEN"
    ][:MAX_TOP_CANDIDATES]
    top_candidate_diagnostics = [_compact_trade_snapshot(trade) for trade in trades[:MAX_TOP_CANDIDATES]]

    output = stamp_payload({
        "symbol": str(observation.get("symbol") or semantic.get("symbol") or hunter.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": source_selection_mode,
        },
        "newest_opened_this_loop": newest_opened_this_loop,
        "top_candidate_diagnostics": top_candidate_diagnostics,
        "paper_safety": paper_safety,
        "summary": {
            "candidate_models": len(hunter.get("detected_models") or []),
            "validated_models": len(semantic.get("validated_models") or []),
            "cluster_count": len(clusters.get("clusters") or []),
            "allowed_clusters": len(cooldown.get("allowed_clusters") or []),
            "setup_family_activation_ready": activation_ready,
            "activation_band": activation_band,
            "paper_trade_candidates": len([trade for trade in trades if str(trade.get("status") or "").upper() == "OPEN"]),
            "invalid_candidates": len([trade for trade in trades if trade.get("status") == "INVALID"]),
            "blocked_candidates": len([trade for trade in trades if trade.get("status") == "BLOCKED"]),
            "existing_open_trades": len(open_trades),
            "lifecycle_latest_read_status": lifecycle_reason or "OK",
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
                "latest_research_paper_lifecycle": lifecycle,
            }.items() if not payload],
        },
        "current_open_summary": {
            "existing_open_trades": len(open_trades),
            "open_by_model_id": dict(open_by_model_id),
            "open_by_family_direction": dict(open_by_family_direction),
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
    }, BLOCK_ID, str(observation.get("symbol") or semantic.get("symbol") or hunter.get("symbol") or "BTCUSDT"), context)

    write_json(OUTPUT_PATH, output)
    append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_paper_trade_factory(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
