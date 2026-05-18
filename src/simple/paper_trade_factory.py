"""Paper Trade Factory for validated research model clusters."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.core.model_survival_registry import load_model_survival_registry, split_active_quarantined, update_model_survival_report
from src.simple.jsonl_tail_reader import safe_read_json
from src.simple.model_timeframe_profile import get_timeframe_profile
from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import (
    current_runtime_context,
    load_json,
    safe_float,
    source_state_refs_from_paths,
    stamp_payload,
    utc_now,
    write_json,
)
from src.simple.lineage_event_logger import append_event, lineage_record, seen_ids
from src.simple.signal_event_consolidator import derive_event_id, enrich_trade_event_fields
from src.simple.signal_grade_engine import grade_signal_record

BLOCK_ID = "PAPER_TRADE_FACTORY"
STATE_DIR = Path("state/simple")

OUTPUT_PATH = epoch_state_path("latest_paper_trade_factory.json")
HISTORY_PATH = epoch_data_path("paper_trade_factory_history.jsonl")

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
RESEARCH_LIFECYCLE_PATH = epoch_state_path("latest_research_paper_lifecycle.json")
RESEARCH_LIFECYCLE_HISTORY_PATH = epoch_data_path("research_paper_lifecycle_history.jsonl")
TIMEFRAME_RESOLUTION_PATH = epoch_state_path("latest_timeframe_resolution.json")
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
MODEL_SURVIVAL_FILTER_PATH = epoch_state_path("latest_model_survival_filter.json")
RESEARCH_EDGE_MATRIX_PATH = epoch_state_path("latest_research_edge_matrix.json")
ZONE_CONTEXT_PATH = STATE_DIR / "latest_zone_context.json"
CONTRACT_DECISION_PATH = STATE_DIR / "latest_contract_decision_gate.json"
CONTRACT_TRADE_PLAN_PATH = STATE_DIR / "latest_contract_trade_plan.json"
SETUP_CONTRACT_PATH = STATE_DIR / "latest_setup_contract.json"
REGIME_CLASSIFIER_PATH = STATE_DIR / "latest_regime_classifier.json"
MARKET_STRUCTURE_V2_PATH = STATE_DIR / "latest_market_structure_v2.json"

MAX_OPEN_TOTAL = 6
MAX_OPEN_PER_MODEL_ID = 1
MAX_OPEN_PER_DIRECTION = 6
MAX_OPEN_PER_SETUP_FAMILY = 1
MAX_OPEN_PER_EVENT_ID = 1
NEW_TRADES_CAP_PER_LOOP = 1
ALLOWED_RESEARCH_BANDS = {"STRONG_ACTIVE", "ACTIVE", "EARLY_RESEARCH"}
MAX_TOP_CANDIDATES = 20
MAX_OPEN_PER_CONTRACT_DIRECTION = 2
MAX_OPEN_PER_CONTRACT_SIDE = 3


def _current_price(observation: dict[str, Any], dna: dict[str, Any]) -> float | None:
    price = safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if price is not None:
        return price
    return safe_float((((dna.get("1m") or {}).get("close"))))


def _paper_trade_id(seed: str, entry: float | None) -> str:
    raw = f"{seed}|{entry}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _derive_rr_fields(direction: str, entry: float | None, stop_loss: float | None, tp1: float | None, tp2: float | None) -> dict[str, float | None]:
    if entry is None or stop_loss is None:
        return {
            "risk_distance": None,
            "tp1_distance": None,
            "tp2_distance": None,
            "rr1": None,
            "rr2": None,
        }
    if direction == "LONG":
        risk_distance = entry - stop_loss
        tp1_distance = tp1 - entry if tp1 is not None else None
        tp2_distance = tp2 - entry if tp2 is not None else None
    else:
        risk_distance = stop_loss - entry
        tp1_distance = entry - tp1 if tp1 is not None else None
        tp2_distance = entry - tp2 if tp2 is not None else None
    if risk_distance is None or risk_distance <= 0:
        return {
            "risk_distance": risk_distance,
            "tp1_distance": tp1_distance,
            "tp2_distance": tp2_distance,
            "rr1": None,
            "rr2": None,
        }
    rr1 = round(tp1_distance / risk_distance, 4) if tp1_distance is not None and tp1_distance > 0 else None
    rr2 = round(tp2_distance / risk_distance, 4) if tp2_distance is not None and tp2_distance > 0 else None
    return {
        "risk_distance": round(risk_distance, 8),
        "tp1_distance": round(tp1_distance, 8) if tp1_distance is not None else None,
        "tp2_distance": round(tp2_distance, 8) if tp2_distance is not None else None,
        "rr1": rr1,
        "rr2": rr2,
    }


def _timeframe_style_bounds(primary_tf: str) -> tuple[int, int]:
    if primary_tf == "1m":
        return 2, 15
    if primary_tf == "5m":
        return 15, 90
    if primary_tf == "15m":
        return 60, 360
    if primary_tf == "1h":
        return 240, 1440
    return 15, 90


def _enrich_timeframe_plan(
    trade: dict[str, Any],
    timeframe_resolution: dict[str, Any],
    setup_family: str,
    model_id: str | None,
) -> dict[str, Any]:
    profile = get_timeframe_profile(setup_family, model_id=model_id)
    hold = dict(profile.get("expected_hold_minutes") or {})
    primary_tf = str(timeframe_resolution.get("primary_tf") or ((profile.get("preferred_primary_tf") or ["5m"])[0]))
    trigger_tf = str(timeframe_resolution.get("trigger_tf") or ((profile.get("allowed_trigger_tf") or [primary_tf])[0]))
    context_tf = str(timeframe_resolution.get("context_tf") or ((profile.get("context_tf") or ["15m"])[0]))
    structure_tf = str(timeframe_resolution.get("structure_tf") or primary_tf)
    rr_fields = _derive_rr_fields(
        str(trade.get("direction") or "UNKNOWN").upper(),
        safe_float(trade.get("entry")),
        safe_float(trade.get("stop_loss")),
        safe_float(trade.get("tp1")),
        safe_float(trade.get("tp2")),
    )
    reason_codes = list(trade.get("reason_codes") or [])
    if rr_fields["rr1"] is None and rr_fields["rr2"] is None:
        reason_codes.append("RR_INVALID")
    min_expected, max_expected = _timeframe_style_bounds(primary_tf)
    hold_min = int(timeframe_resolution.get("expected_hold_min_minutes") or hold.get("min") or min_expected)
    hold_max = int(timeframe_resolution.get("expected_hold_max_minutes") or hold.get("max") or max_expected)
    if hold_min < min_expected or hold_max > max_expected:
        reason_codes.append("TIMEFRAME_STYLE_MISMATCH_HOLD")
    if rr_fields["risk_distance"] is not None and rr_fields["risk_distance"] <= 0:
        reason_codes.append("TIMEFRAME_STYLE_MISMATCH_RISK")
    enriched = dict(trade)
    enriched.update(rr_fields)
    enriched.update(
        {
            "primary_tf": primary_tf,
            "trigger_tf": trigger_tf,
            "context_tf": context_tf,
            "structure_tf": structure_tf,
            "expected_hold_min_minutes": hold_min,
            "expected_hold_max_minutes": hold_max,
            "expected_hold_label": str(timeframe_resolution.get("expected_hold_label") or f"{hold_min}m–{hold_max}m"),
            "timeframe_confidence": float(timeframe_resolution.get("timeframe_confidence") or 0.0),
            "timeframe_reason": list(timeframe_resolution.get("timeframe_reason") or [f"{primary_tf} profile fallback"]),
            "plan_style": str(timeframe_resolution.get("profile", {}).get("plan_style") or profile.get("plan_style") or "DEFAULT_INTRADAY"),
            "max_holding_seconds": hold_max * 60,
            "rr_tp1": rr_fields["rr1"],
            "rr_tp2": rr_fields["rr2"],
            "reason_codes": sorted(set(reason_codes)),
        }
    )
    return enriched


def _cause_chain() -> list[str]:
    return [
        "raw_observation",
        "mtf_candle_dna",
        "market_structure",
        "liquidity_event",
        "interpretation",
        "setup_family_activation",
        "timeframe_resolution",
        "trade_plan",
    ]


def _edge_invalid(trade: dict[str, Any]) -> bool:
    missing_tf = not trade.get("primary_tf") or not trade.get("trigger_tf") or not trade.get("context_tf")
    missing_rr = trade.get("rr1") is None and trade.get("rr2") is None
    return missing_tf or missing_rr


def _required_field_issues(trade: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in (
        "symbol",
        "paper_trade_id",
        "context_id",
        "loop_id",
        "model_id",
        "setup_family",
        "direction",
        "entry",
        "stop_loss",
        "tp1",
        "tp2",
        "primary_tf",
        "trigger_tf",
        "context_tf",
        "structure_tf",
        "rr1",
        "rr2",
        "risk_distance",
        "tp1_distance",
        "tp2_distance",
        "cause_chain",
        "source_state_refs",
    ):
        value = trade.get(field)
        if value in (None, "", [], {}):
            missing.append(field)
    return missing


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


def _event_bucket_key(trade: dict[str, Any]) -> str:
    return "|".join(
        [
            str(trade.get("symbol") or "UNKNOWN"),
            str(trade.get("event_bucket_5m") or "UNKNOWN_BUCKET"),
        ]
    )


def _lifecycle_open_state(
    lifecycle: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str], Counter[str], Counter[str], dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    open_trades = [trade for trade in (lifecycle.get("open_trades") or []) if str(trade.get("status") or "").upper() == "OPEN"]
    open_by_model_id: Counter[str] = Counter()
    open_by_family_direction: Counter[str] = Counter()
    open_by_direction: Counter[str] = Counter()
    open_by_setup_family: Counter[str] = Counter()
    open_by_event_id: Counter[str] = Counter()
    open_context_directions: dict[str, set[str]] = {}
    open_model_family_directions: dict[str, set[str]] = {}
    open_event_bucket_directions: dict[str, set[str]] = {}
    for trade in open_trades:
        event_id = str(trade.get("event_id") or derive_event_id(trade))
        direction = str(trade.get("direction") or "UNKNOWN").upper()
        open_by_model_id[_model_id_key(trade)] += 1
        open_by_family_direction[_family_direction_key(trade)] += 1
        open_by_direction[direction] += 1
        open_by_setup_family[str(trade.get("setup_family") or "NO_ACTIVE_SETUP_FAMILY")] += 1
        open_by_event_id[event_id] += 1
        open_context_directions.setdefault(_context_contradiction_key(trade), set()).add(direction)
        open_model_family_directions.setdefault(_model_family_context_key(trade), set()).add(direction)
        open_event_bucket_directions.setdefault(_event_bucket_key(trade), set()).add(direction)
    return open_trades, open_by_model_id, open_by_family_direction, open_by_direction, open_by_setup_family, open_by_event_id, open_context_directions, open_model_family_directions, open_event_bucket_directions


def _bad_token(value: Any) -> bool:
    return str(value or "").strip().upper() in {"", "UNKNOWN", "NONE", "NO_EVENT", "NO_STRUCTURE", "NEUTRAL"}


def _has_hard_semantic_contradiction(trade: dict[str, Any]) -> bool:
    reason_text = " ".join(str(item).upper() for item in [
        *(trade.get("risk_tags") or []),
        *(trade.get("reason_codes") or []),
        *(trade.get("grade_blockers") or []),
        trade.get("semantic_status"),
    ])
    direction_resolution = trade.get("direction_resolution") or {}
    resolution_mode = str(direction_resolution.get("resolution_mode") or "").upper()
    return (
        "HARD_DIRECTION_CONFLICT" in reason_text
        or "SEMANTIC_CONTRADICTION" in reason_text
        or "OPPOSITE_DIRECTION_VALIDATED_MODEL" in reason_text
        or resolution_mode == "NEUTRAL_HARD_CONFLICT"
    )


def _mtf_alignment_contradictory(trade: dict[str, Any]) -> bool:
    direction_resolution = trade.get("direction_resolution") or {}
    mode = str(direction_resolution.get("resolution_mode") or "").upper()
    if mode == "NEUTRAL_HARD_CONFLICT":
        return True
    conflicts = direction_resolution.get("direction_conflicts") or []
    return bool(conflicts) and int(direction_resolution.get("conflict_count") or len(conflicts)) >= 2


def _hard_entry_gate_reason(trade: dict[str, Any]) -> str | None:
    grade = str(trade.get("signal_grade") or "D").upper()
    activation_score = safe_float(trade.get("activation_score")) or 0.0
    rr1 = safe_float(trade.get("rr1"))
    rr2 = safe_float(trade.get("rr2"))
    direction = str(trade.get("direction") or "NEUTRAL").upper()
    confluence_count = int(trade.get("event_confluence_count") or 0)
    if grade not in {"A_PLUS", "A"}:
        return f"SIGNAL_GRADE_{grade}_DIAGNOSTIC_ONLY"
    if activation_score < 0.80:
        return "ACTIVATION_SCORE_BELOW_0_80"
    if rr1 is None or rr1 < 1.2:
        return "RR1_BELOW_1_2"
    if rr2 is None or rr2 < 2.0:
        return "RR2_BELOW_2_0"
    if not trade.get("primary_tf"):
        return "PRIMARY_TF_MISSING"
    if not trade.get("context_tf"):
        return "CONTEXT_TF_MISSING"
    if direction not in {"LONG", "SHORT"}:
        return "DIRECTION_NEUTRAL_OR_INVALID"
    if confluence_count < 2:
        return "EVENT_CONFLUENCE_LT_2"
    if _mtf_alignment_contradictory(trade):
        return "MTF_ALIGNMENT_CONTRADICTORY"
    if _bad_token(trade.get("liquidity_event")):
        return "LIQUIDITY_EVENT_MISSING"
    if _bad_token(trade.get("structure_label")):
        return "STRUCTURE_LABEL_MISSING"
    if _has_hard_semantic_contradiction(trade):
        return "HARD_SEMANTIC_CONTRADICTION"
    return None


def _survival_record(model_survival: dict[str, Any], model_id: str) -> dict[str, Any]:
    record = (model_survival.get("models") or {}).get(model_id)
    if isinstance(record, dict):
        return record
    return {
        "model_id": model_id,
        "model_status": "SAMPLE_BUILDING",
        "sample_size": 0,
        "paper_open_allowed": False,
        "allowed_signal_grades": ["A_PLUS"],
    }


def _survival_gate_reason(trade: dict[str, Any], model_survival: dict[str, Any]) -> str | None:
    model_id = str(trade.get("model_id") or trade.get("dominant_model_id") or "UNKNOWN")
    grade = str(trade.get("signal_grade") or "D").upper()
    record = _survival_record(model_survival, model_id)
    trade["model_status"] = record.get("model_status")
    trade["survival_filter"] = record
    status = str(record.get("model_status") or "SAMPLE_BUILDING").upper()
    allowed_grades = {str(item).upper() for item in (record.get("allowed_signal_grades") or [])}
    if status == "SUPPRESSED_RESEARCH":
        return "MODEL_NEGATIVE_EDGE_SUPPRESSED"
    if status == "SAMPLE_BUILDING" and grade != "A_PLUS":
        return "MODEL_SAMPLE_BUILDING_A_PLUS_ONLY"
    if allowed_grades and grade not in allowed_grades:
        return "MODEL_SURVIVAL_GRADE_NOT_ALLOWED"
    if record.get("paper_open_allowed") is False and not allowed_grades:
        return "MODEL_NEGATIVE_EDGE_SUPPRESSED"
    return None


def _setup_family_negative_edge_reason(trade: dict[str, Any], edge: dict[str, Any]) -> str | None:
    family = str(trade.get("setup_family") or "UNKNOWN")
    for group in edge.get("groups") or []:
        if str(group.get("setup_family") or "UNKNOWN") != family:
            continue
        sample_size = int(group.get("sample_size") or 0)
        winrate = safe_float(group.get("winrate"))
        avg_r = safe_float(group.get("avg_r") or group.get("expectancy"))
        if sample_size >= 10 and ((winrate is not None and winrate < 0.35) or (avg_r is not None and avg_r < -0.25)):
            return "SETUP_FAMILY_NEGATIVE_EDGE_SUPPRESSED"
    return None



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
    timeframe_resolution: dict[str, Any],
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
        initial_risk_distance = max(atr_1m, entry * 0.001)
    else:
        initial_risk_distance = entry * 0.002 if entry is not None else None
        reason_codes.append("FALLBACK_STOP_DISTANCE_USED")
    if entry is None or initial_risk_distance is None or initial_risk_distance <= 0:
        invalid_reason = invalid_reason or "RISK_DISTANCE_INVALID"

    stop_loss = None
    tp1 = None
    tp2 = None
    rr_tp1 = None
    rr_tp2 = None
    if invalid_reason is None and entry is not None and initial_risk_distance is not None:
        if direction == "LONG":
            stop_loss = round(entry - initial_risk_distance, 8)
            tp1 = round(entry + 1.5 * initial_risk_distance, 8)
            tp2 = round(entry + 2.5 * initial_risk_distance, 8)
        else:
            stop_loss = round(entry + initial_risk_distance, 8)
            tp1 = round(entry - 1.5 * initial_risk_distance, 8)
            tp2 = round(entry - 2.5 * initial_risk_distance, 8)
        rr_tp1 = 1.5
        rr_tp2 = 2.5

    source_cluster = dict(cluster)
    source_cluster["paper_representative"] = representative
    source_state_refs = source_state_refs_from_paths(
        {
            "setup_activation": SETUP_ACTIVATION_PATH,
            "observation": OBSERVATION_PATH,
            "mtf_candle_dna": DNA_PATH,
            "market_structure": MARKET_STRUCTURE_PATH,
            "liquidity_map": LIQUIDITY_PATH,
            "interpretation": INTERPRETATION_PATH,
            "timeframe_resolution": TIMEFRAME_RESOLUTION_PATH,
        }
    )
    market_regime = str(representative.get("market_regime") or "UNKNOWN")
    direction_resolution = representative.get("direction_resolution") or {"resolution_mode": "UNRESOLVED"}
    trade = {
        "epoch_id": ACTIVE_EPOCH_ID,
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
        "risk_distance": initial_risk_distance,
        "target_reference": _target_reference(direction, entry or 0.0, liquidity) if entry is not None else None,
        "opened_at_utc": utc_now(),
        "max_holding_seconds": 1800,
        "status": "INVALID" if invalid_reason else "OPEN",
        "invalid_reason": invalid_reason,
        "invalid_for_edge": bool(invalid_reason) or not context.get("context_id") or not representative.get("model_id"),
        "valid_for_lifecycle": True,
        "valid_for_edge": True,
        "reason_codes": sorted(set(reason_codes)),
        "source_model_instance": representative.get("source_model_instance") or representative,
        "source_cluster": source_cluster,
        "source_business_zone_ref": business_zone.get("timestamp_utc"),
        "source_state_refs": source_state_refs,
        "cause_chain": _cause_chain(),
    }
    trade = _enrich_timeframe_plan(trade, timeframe_resolution, setup_family, representative.get("model_id"))
    activation_payload = {
        "activation_score": activation_score,
        "activation_band": activation_band,
        "direction": direction,
        "risk_tags": activation_risk_tags,
        "source_models": activation_source_models,
    }
    grade = grade_signal_record(trade, activation_payload, timeframe_resolution)
    trade.update(grade)
    trade = enrich_trade_event_fields(trade, grade)
    trade["execution_safety"] = {"live_order_sent": False, "private_api_used": False}
    edge_invalid = _edge_invalid(trade)
    required_issues = _required_field_issues(trade)
    trade["invalid_for_edge"] = bool(trade.get("invalid_for_edge")) or edge_invalid or bool(required_issues)
    trade["valid_for_edge"] = not bool(trade.get("invalid_for_edge"))
    trade["valid_for_lifecycle"] = not bool(required_issues)
    if edge_invalid:
        trade["reason_codes"] = sorted(set([*(trade.get("reason_codes") or []), "MISSING_TIMEFRAME_OR_RR"]))
        invalid_reason_codes = list(trade.get("invalid_reason_codes") or [])
        invalid_reason_codes.append("MISSING_TIMEFRAME_OR_RR")
        trade["invalid_reason_codes"] = sorted(set(invalid_reason_codes))
        if not trade.get("invalid_reason"):
            trade["invalid_reason"] = "MISSING_TIMEFRAME_OR_RR"
    if required_issues:
        trade["reason_codes"] = sorted(set([*(trade.get("reason_codes") or []), "FACTORY_REQUIRED_FIELDS_MISSING"]))
        reason = f"MISSING_FIELDS:{','.join(sorted(required_issues))}"
        trade["invalid_reason"] = "|".join(item for item in [trade.get("invalid_reason"), reason] if item)
        trade["invalid_reason_codes"] = sorted(set([*(trade.get("invalid_reason_codes") or []), *[f"MISSING_{field.upper()}" for field in required_issues]]))
    return trade


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
        "tp1_distance",
        "tp2_distance",
        "rr1",
        "rr2",
        "status",
        "invalid_reason",
        "valid_for_lifecycle",
        "valid_for_edge",
        "epoch_id",
        "activation_band",
        "activation_score",
        "primary_tf",
        "trigger_tf",
        "context_tf",
        "structure_tf",
        "expected_hold_label",
        "expected_hold_min_minutes",
        "expected_hold_max_minutes",
        "timeframe_confidence",
        "timeframe_reason",
        "plan_style",
            "reason_codes",
            "opened_at_utc",
            "max_holding_seconds",
            "invalid_for_edge",
            "cause_chain",
        "source_state_refs",
        "event_id",
        "event_bucket_5m",
        "event_confluence_count",
        "signal_grade",
        "grade_score",
        "grade_reasons",
        "grade_blockers",
        "a_plus_ready",
        "supporting_models",
        "supporting_setups",
        "execution_safety",
        "model_status",
        "survival_filter",
        "paper_source",
        "setup_id",
        "signal_id",
        "plan_id",
        "decision_id",
        "contract_id",
        "decision_status",
        "structure_bias",
        "primary_regime",
        "regime",
        "liquidity_bias",
        "opened_at",
    )
    return {field: trade.get(field) for field in keep_fields if field in trade}


def _entries_near(a: Any, b: Any) -> bool:
    av = safe_float(a)
    bv = safe_float(b)
    if av is None or bv is None:
        return False
    return abs(av - bv) <= max(0.05, abs(av) * 0.0005)


def _contract_duplicate_count(
    open_trades: list[dict[str, Any]],
    contract_id: str,
    direction: str,
    entry: float,
) -> int:
    count = 0
    for trade in open_trades:
        if str(trade.get("status") or "").upper() != "OPEN":
            continue
        if str(trade.get("contract_id") or "") != contract_id:
            continue
        if str(trade.get("direction") or "").upper() != direction:
            continue
        if _entries_near(trade.get("entry"), entry):
            count += 1
    return count


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
    timeframe_resolution = load_json(TIMEFRAME_RESOLUTION_PATH) or {}
    model_survival = load_json(MODEL_SURVIVAL_FILTER_PATH) or {}
    edge_matrix = load_json(RESEARCH_EDGE_MATRIX_PATH) or {}
    zone_context = load_json(ZONE_CONTEXT_PATH) or {}
    contract_decision = load_json(CONTRACT_DECISION_PATH) or {}
    contract_trade_plan = load_json(CONTRACT_TRADE_PLAN_PATH) or {}
    setup_contract = load_json(SETUP_CONTRACT_PATH) or {}
    regime_classifier = load_json(REGIME_CLASSIFIER_PATH) or {}
    market_structure_v2 = load_json(MARKET_STRUCTURE_V2_PATH) or {}
    registry = load_model_survival_registry()
    lifecycle, lifecycle_reason = safe_read_json(RESEARCH_LIFECYCLE_PATH, default={}, max_bytes=500_000)
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}

    current_price = _current_price(observation, dna)
    atr_1m = safe_float(((atr.get("1m") or {}).get("atr_14")))
    selected_clusters, source_selection_mode, selection_reason_codes = _select_candidates(activation, semantic, clusters, cooldown)
    selected_clusters, registry_blocked_clusters = split_active_quarantined(selected_clusters, BLOCK_ID)
    survival_report = update_model_survival_report(location=BLOCK_ID, allowed_count=len(selected_clusters), blocked_items=registry_blocked_clusters, registry=registry)

    activation_band = str(activation.get("activation_band") or "WATCH_ONLY").upper()
    activation_ready = bool(activation.get("ready_for_paper_research")) and activation_band in ALLOWED_RESEARCH_BANDS
    dominant_setup_family = str(activation.get("dominant_setup_family") or "NO_ACTIVE_SETUP_FAMILY")
    activation_score = float(activation.get("activation_score") or 0.0)
    activation_reasons = list(activation.get("activation_reasons") or [])
    activation_risk_tags = list(activation.get("risk_tags") or [])
    activation_source_models = list(activation.get("source_models") or [])
    activation_source_clusters = list(activation.get("source_clusters") or [])

    (
        open_trades,
        open_by_model_id,
        open_by_family_direction,
        open_by_direction,
        open_by_setup_family,
        open_by_event_id,
        open_context_directions,
        open_model_family_directions,
        open_event_bucket_directions,
    ) = _lifecycle_open_state(lifecycle)
    pending_by_model_id: Counter[str] = Counter()
    pending_by_family_direction: Counter[str] = Counter()
    pending_by_direction: Counter[str] = Counter()
    pending_by_setup_family: Counter[str] = Counter()
    pending_by_event_id: Counter[str] = Counter()
    pending_context_directions: dict[str, set[str]] = {}
    pending_model_family_directions: dict[str, set[str]] = {}
    pending_event_bucket_directions: dict[str, set[str]] = {}
    allowed_research_band_counts: Counter[str] = Counter()
    contract_bridge_reason_codes: list[str] = []
    paper_safety = {
        "max_new_trades_per_loop": NEW_TRADES_CAP_PER_LOOP,
        "max_open_total": MAX_OPEN_TOTAL,
        "max_open_per_model_id": MAX_OPEN_PER_MODEL_ID,
        "max_open_per_direction": MAX_OPEN_PER_DIRECTION,
        "max_open_per_setup_family": MAX_OPEN_PER_SETUP_FAMILY,
        "max_open_per_event_id": MAX_OPEN_PER_EVENT_ID,
        "contradiction_guard_enabled": True,
        "contradiction_key_fields": ["symbol", "context_id", "dominant_setup_family", "liquidity_event"],
        "blocked_by_context_direction_conflict": 0,
        "blocked_by_model_family_direction_conflict": 0,
        "blocked_by_open_limit": 0,
        "blocked_by_family_limit": 0,
        "blocked_by_direction_limit": 0,
        "blocked_by_event_limit": 0,
        "blocked_by_model_id_limit": 0,
        "blocked_by_new_trade_cap": 0,
        "blocked_by_hard_entry_gate": 0,
        "blocked_by_model_survival": 0,
        "blocked_by_model_survival_registry": len(registry_blocked_clusters),
        "blocked_by_setup_family_negative_edge": 0,
        "blocked_by_opposite_event_bucket": 0,
        "allowed_research_band_counts": {},
    }

    trades: list[dict[str, Any]] = []
    new_trade_slots_used = 0

    decision_status = str(contract_decision.get("paper_decision") or contract_decision.get("decision_status") or "").upper()
    paper_permission = bool(contract_decision.get("paper_permission") or contract_decision.get("paper_execution_permission"))
    setup_id = str(contract_trade_plan.get("setup_id") or contract_decision.get("setup_id") or "")
    signal_id = str(contract_trade_plan.get("signal_id") or contract_decision.get("signal_id") or "")
    plan_id = str(contract_trade_plan.get("plan_id") or contract_decision.get("plan_id") or "")
    decision_id = str(contract_decision.get("decision_id") or "")
    plan_status = str(contract_trade_plan.get("plan_status") or "").upper()
    contract_direction = str(contract_trade_plan.get("direction") or contract_decision.get("direction") or "UNKNOWN").upper()
    contract_entry = safe_float(contract_trade_plan.get("entry") or contract_trade_plan.get("entry_price"))
    contract_stop_loss = safe_float(contract_trade_plan.get("stop_loss"))
    contract_tp1 = safe_float(contract_trade_plan.get("tp1"))
    contract_tp2 = safe_float(contract_trade_plan.get("tp2"))
    contract_id = str(contract_trade_plan.get("contract_id") or contract_decision.get("contract_id") or "")
    setup_family = str(contract_trade_plan.get("setup_family") or contract_decision.get("setup_family") or "UNKNOWN")
    contract_trade_opened = False

    if not paper_permission:
        contract_bridge_reason_codes.append("PAPER_PERMISSION_NOT_GRANTED")
    elif decision_status != "ALLOW_PAPER":
        contract_bridge_reason_codes.append("CONTRACT_DECISION_NOT_ALLOWING")
    elif plan_status != "PLAN_READY":
        contract_bridge_reason_codes.append("CONTRACT_PLAN_INCOMPLETE")
    elif contract_entry is None or contract_stop_loss is None or contract_tp1 is None:
        contract_bridge_reason_codes.append("CONTRACT_PLAN_INCOMPLETE")
    elif contract_direction not in {"LONG", "SHORT"} or not contract_id:
        contract_bridge_reason_codes.append("CONTRACT_PLAN_INCOMPLETE")
    elif not setup_id or not signal_id or not plan_id or not decision_id:
        contract_bridge_reason_codes.append("CHAIN_ID_MISSING")
    else:
        duplicate_count = _contract_duplicate_count(open_trades, contract_id, contract_direction, contract_entry)
        direction_open_count = sum(
            1
            for trade in open_trades
            if str(trade.get("status") or "").upper() == "OPEN"
            and str(trade.get("direction") or "").upper() == contract_direction
        )
        if duplicate_count >= MAX_OPEN_PER_CONTRACT_DIRECTION:
            contract_bridge_reason_codes.append("CONTRACT_DUPLICATE_BLOCKED")
        elif direction_open_count >= MAX_OPEN_PER_CONTRACT_SIDE:
            contract_bridge_reason_codes.append("DIRECTION_OPEN_LIMIT_BLOCKED")
        else:
            rr_fields = _derive_rr_fields(contract_direction, contract_entry, contract_stop_loss, contract_tp1, contract_tp2)
            opened_ts = utc_now()
            contract_seed = f"{context.get('loop_id')}|{contract_id}|{contract_direction}|{contract_entry}"
            contract_event_suffix = plan_id or decision_id or opened_ts
            contract_event_id = f"CONTRACT|{contract_id}|{contract_direction}|{contract_event_suffix}"
            trades.append(
                {
                    "epoch_id": ACTIVE_EPOCH_ID,
                    "symbol": str(observation.get("symbol") or contract_trade_plan.get("symbol") or "BTCUSDT"),
                    "paper_trade_id": _paper_trade_id(contract_seed, contract_entry),
                    "context_id": context.get("context_id"),
                    "loop_id": context.get("loop_id"),
                    "paper_source": "CONTRACT_DECISION_GATE",
                    "setup_id": setup_id,
                    "signal_id": signal_id,
                    "plan_id": plan_id,
                    "decision_id": decision_id,
                    "contract_id": contract_id,
                    "setup_family": setup_family,
                    "direction": contract_direction,
                    "entry": contract_entry,
                    "stop_loss": contract_stop_loss,
                    "tp1": contract_tp1,
                    "tp2": contract_tp2,
                    "rr1": rr_fields.get("rr1"),
                    "rr2": rr_fields.get("rr2"),
                    "risk_distance": rr_fields.get("risk_distance"),
                    "tp1_distance": rr_fields.get("tp1_distance"),
                    "tp2_distance": rr_fields.get("tp2_distance"),
                    "decision_status": "ALLOW_PAPER",
                    "structure_bias": str((market_structure_v2 or {}).get("structure_bias") or ((contract_decision.get("metadata") or {}).get("structure_bias") or "UNKNOWN")),
                    "primary_regime": str((regime_classifier or {}).get("primary_regime") or "UNKNOWN"),
                    "regime": str((regime_classifier or {}).get("regime") or (regime_classifier or {}).get("primary_regime") or "UNKNOWN"),
                    "liquidity_bias": str((setup_contract or {}).get("liquidity_bias") or ((contract_decision.get("metadata") or {}).get("liquidity_bias") or "UNKNOWN")),
                    "status": "OPEN",
                    "outcome_status": "OPEN",
                    "opened_at": opened_ts,
                    "opened_at_utc": opened_ts,
                    "valid_for_lifecycle": True,
                    "valid_for_edge": True,
                    "invalid_for_edge": False,
                    "event_id": contract_event_id,
                    "event_bucket_5m": f"CONTRACT|{contract_id}",
                    "event_confluence_count": 1,
                    "cause_chain": [
                        "market_structure_v2",
                        "regime_classifier",
                        "setup_contract",
                        "contract_trade_plan",
                        "contract_decision_gate",
                    ],
                    "source_state_refs": source_state_refs_from_paths(
                        {
                            "contract_decision_gate": CONTRACT_DECISION_PATH,
                            "contract_trade_plan": CONTRACT_TRADE_PLAN_PATH,
                            "setup_contract": SETUP_CONTRACT_PATH,
                            "regime_classifier": REGIME_CLASSIFIER_PATH,
                            "market_structure_v2": MARKET_STRUCTURE_V2_PATH,
                        }
                    ),
                    "reason_codes": sorted(
                        {
                            "CONTRACT_DECISION_GATE_SOURCE",
                            "CONTRACT_BRIDGE_OPENED",
                            "PAPER_OPENED_FROM_CONTRACT_DRIVEN_CHAIN",
                            "PAPER_ONLY",
                            "NO_LIVE_EXECUTION",
                            "NO_PRIVATE_API",
                        }
                    ),
                    "blocked_by": [],
                    "execution_safety": {"safe_to_open_real_trade": False, "live_order_sent": False, "private_api_used": False},
                }
            )
            new_trade_slots_used += 1
            contract_trade_opened = True
            contract_bridge_reason_codes.append("CONTRACT_BRIDGE_TRADE_OPENED")
            contract_bridge_reason_codes.append("PAPER_OPENED_FROM_CONTRACT_DRIVEN_CHAIN")

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
            timeframe_resolution=timeframe_resolution,
        )

        if trade.get("status") == "INVALID":
            trades.append(trade)
            continue
        if zone_context:
            trade["zone_context"] = zone_context.get("zones") or []

        model_id_key = _model_id_key(trade)
        family_direction_key = _family_direction_key(trade)
        setup_family_key = str(trade.get("setup_family") or "NO_ACTIVE_SETUP_FAMILY")
        event_id_key = str(trade.get("event_id") or derive_event_id(trade))
        event_bucket_key = _event_bucket_key(trade)
        context_conflict_key = _context_contradiction_key(trade)
        model_family_context_key = _model_family_context_key(trade)
        direction = str(trade.get("direction") or "UNKNOWN").upper()
        total_open_after_pending = len(open_trades) + new_trade_slots_used
        model_open_after_pending = open_by_model_id[model_id_key] + pending_by_model_id[model_id_key]
        family_direction_open_after_pending = (
            open_by_family_direction[family_direction_key]
            + pending_by_family_direction[family_direction_key]
        )
        direction_open_after_pending = open_by_direction[direction] + pending_by_direction[direction]
        setup_family_open_after_pending = open_by_setup_family[setup_family_key] + pending_by_setup_family[setup_family_key]
        event_open_after_pending = open_by_event_id[event_id_key] + pending_by_event_id[event_id_key]
        seen_context_directions = set(open_context_directions.get(context_conflict_key, set()))
        seen_context_directions.update(pending_context_directions.get(context_conflict_key, set()))
        seen_model_family_directions = set(open_model_family_directions.get(model_family_context_key, set()))
        seen_model_family_directions.update(pending_model_family_directions.get(model_family_context_key, set()))
        seen_event_bucket_directions = set(open_event_bucket_directions.get(event_bucket_key, set()))
        seen_event_bucket_directions.update(pending_event_bucket_directions.get(event_bucket_key, set()))

        guard_reason = None
        gate_reason = _hard_entry_gate_reason(trade)
        survival_reason = _survival_gate_reason(trade, model_survival)
        setup_negative_reason = _setup_family_negative_edge_reason(trade, edge_matrix)
        registry_allowed_trade, registry_blocked_trade = split_active_quarantined([trade], BLOCK_ID)
        if registry_blocked_trade:
            paper_safety["blocked_by_model_survival_registry"] += 1
            guard_reason = "MODEL_SURVIVAL_REGISTRY_BLOCK"
        elif gate_reason:
            paper_safety["blocked_by_hard_entry_gate"] += 1
            guard_reason = gate_reason
        elif survival_reason:
            paper_safety["blocked_by_model_survival"] += 1
            guard_reason = survival_reason
        elif setup_negative_reason:
            paper_safety["blocked_by_setup_family_negative_edge"] += 1
            guard_reason = setup_negative_reason
        elif any(existing != direction for existing in seen_event_bucket_directions if existing in {"LONG", "SHORT"}):
            paper_safety["blocked_by_opposite_event_bucket"] += 1
            guard_reason = "OPPOSITE_DIRECTION_EVENT_5M_BUCKET"
        elif any(existing != direction for existing in seen_context_directions if existing in {"LONG", "SHORT"}):
            paper_safety["blocked_by_context_direction_conflict"] += 1
            guard_reason = "CONTEXT_DIRECTION_CONFLICT"
        elif any(existing != direction for existing in seen_model_family_directions if existing in {"LONG", "SHORT"}):
            paper_safety["blocked_by_model_family_direction_conflict"] += 1
            guard_reason = "MODEL_FAMILY_DIRECTION_CONFLICT"
        elif total_open_after_pending >= MAX_OPEN_TOTAL:
            paper_safety["blocked_by_open_limit"] += 1
            guard_reason = "PAPER_OPEN_LIMIT_REACHED"
        elif new_trade_slots_used >= NEW_TRADES_CAP_PER_LOOP:
            paper_safety["blocked_by_new_trade_cap"] += 1
            guard_reason = "NEW_TRADES_CAP_PER_LOOP_REACHED"
        elif event_open_after_pending >= MAX_OPEN_PER_EVENT_ID:
            paper_safety["blocked_by_event_limit"] += 1
            guard_reason = "EVENT_ALREADY_OPEN"
        elif direction_open_after_pending >= MAX_OPEN_PER_DIRECTION:
            paper_safety["blocked_by_direction_limit"] += 1
            guard_reason = "PAPER_OPEN_LIMIT_REACHED"
        elif setup_family_open_after_pending >= MAX_OPEN_PER_SETUP_FAMILY:
            paper_safety["blocked_by_family_limit"] += 1
            guard_reason = "SETUP_FAMILY_LIMIT_REACHED"
        elif model_open_after_pending >= MAX_OPEN_PER_MODEL_ID:
            paper_safety["blocked_by_model_id_limit"] += 1
            guard_reason = "MODEL_ID_ALREADY_OPEN"
        elif family_direction_open_after_pending >= MAX_OPEN_PER_SETUP_FAMILY:
            paper_safety["blocked_by_family_limit"] += 1
            guard_reason = "SETUP_FAMILY_LIMIT_REACHED"

        if guard_reason:
            trade["status"] = "BLOCKED"
            trade["valid_for_lifecycle"] = False
            trade["valid_for_edge"] = False
            trade["invalid_reason"] = guard_reason
            if guard_reason == "EVENT_ALREADY_OPEN":
                trade["supporting_models"] = sorted(set([*(trade.get("supporting_models") or []), str(trade.get("model_id") or "UNKNOWN")]))
                trade["supporting_setups"] = sorted(set([*(trade.get("supporting_setups") or []), str(trade.get("setup_family") or "UNKNOWN")]))
            trade["reason_codes"] = sorted(set([*(trade.get("reason_codes") or []), guard_reason]))
            trades.append(trade)
            continue

        new_trade_slots_used += 1
        pending_by_model_id[model_id_key] += 1
        pending_by_family_direction[family_direction_key] += 1
        pending_by_direction[direction] += 1
        pending_by_setup_family[setup_family_key] += 1
        pending_by_event_id[event_id_key] += 1
        pending_context_directions.setdefault(context_conflict_key, set()).add(direction)
        pending_model_family_directions.setdefault(model_family_context_key, set()).add(direction)
        pending_event_bucket_directions.setdefault(event_bucket_key, set()).add(direction)
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
        "epoch_id": ACTIVE_EPOCH_ID,
        "newest_opened_this_loop": newest_opened_this_loop,
        "top_candidate_diagnostics": top_candidate_diagnostics,
        "paper_safety": paper_safety,
        "summary": {
            "candidate_models": len(hunter.get("detected_models") or []),
            "validated_models": len(semantic.get("validated_models") or []),
            "cluster_count": len(clusters.get("clusters") or []),
            "allowed_clusters": len(cooldown.get("allowed_clusters") or []),
            "model_survival_registry_blocked_count": paper_safety["blocked_by_model_survival_registry"],
            "setup_family_activation_ready": activation_ready,
            "activation_band": activation_band,
                "paper_trade_candidates": len([trade for trade in trades if str(trade.get("status") or "").upper() == "OPEN"]),
                "contract_bridge_trade_opened": contract_trade_opened,
                "invalid_candidates": len([trade for trade in trades if trade.get("status") == "INVALID"]),
                "blocked_candidates": len([trade for trade in trades if trade.get("status") == "BLOCKED"]),
                "valid_for_lifecycle_count": len([trade for trade in trades if trade.get("valid_for_lifecycle") is True]),
                "valid_for_edge_count": len([trade for trade in trades if trade.get("valid_for_edge") is True]),
                "existing_open_trades": len(open_trades),
                "lifecycle_latest_read_status": lifecycle_reason or "OK",
            },
        "reason_codes": [
            f"PAPER_TRADES_{len(trades)}",
            *selection_reason_codes,
            *sorted(set(contract_bridge_reason_codes)),
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
                "latest_timeframe_resolution": timeframe_resolution,
                "latest_model_survival_filter": model_survival,
                "latest_research_edge_matrix": edge_matrix,
                "latest_research_paper_lifecycle": lifecycle,
                "latest_zone_context": zone_context,
            }.items() if not payload],
        },
        "model_survival_registry": {
            "registry_status": survival_report.get("registry_status"),
            "blocked_count": paper_safety["blocked_by_model_survival_registry"],
        },
        "current_open_summary": {
            "existing_open_trades": len(open_trades),
            "open_by_model_id": dict(open_by_model_id),
            "open_by_family_direction": dict(open_by_family_direction),
            "open_by_direction": dict(open_by_direction),
            "open_by_setup_family": dict(open_by_setup_family),
            "open_by_event_id": dict(open_by_event_id),
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
    append_epoch_jsonl("paper_trade_factory_history.jsonl", output)
    existing_open_ids = seen_ids("paper_trade_open_events.jsonl", "paper_trade_id")
    for trade in newest_opened_this_loop:
        paper_trade_id = str(trade.get("paper_trade_id") or "")
        if not paper_trade_id or paper_trade_id in existing_open_ids:
            continue
        append_event(
            "paper_trade_open_events.jsonl",
            lineage_record(
                record_type="paper_trade_open",
                event_id=f"OPEN_{paper_trade_id}",
                parent_id=str(trade.get("decision_id") or ""),
                setup_id=str(trade.get("setup_id") or ""),
                signal_id=str(trade.get("signal_id") or ""),
                plan_id=str(trade.get("plan_id") or ""),
                decision_id=str(trade.get("decision_id") or ""),
                paper_trade_id=paper_trade_id,
                context_id=trade.get("context_id"),
                loop_id=trade.get("loop_id"),
                reason_codes=list(trade.get("reason_codes") or []),
                blocked_by=list(trade.get("blocked_by") or []),
                feeds_next=["paper_trade_close_events", "outcome_events"],
                extra={
                    "entry": trade.get("entry"),
                    "stop_loss": trade.get("stop_loss"),
                    "tp1": trade.get("tp1"),
                    "tp2": trade.get("tp2"),
                    "rr1": trade.get("rr1"),
                    "rr2": trade.get("rr2"),
                },
            ),
        )
        existing_open_ids.add(paper_trade_id)
    return output


def main() -> None:
    print(json.dumps(run_paper_trade_factory(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
