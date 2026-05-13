"""Setup-family activation layer for paper-research progression."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "SETUP_FAMILY_ACTIVATION_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

SEMANTIC_PATH = STATE_DIR / "latest_model_semantic_validation.json"
CLUSTERS_PATH = STATE_DIR / "latest_model_clusters.json"
COOLDOWN_PATH = STATE_DIR / "latest_model_cooldown.json"
DOMINANT_MODEL_PATH = STATE_DIR / "latest_dominant_model.json"
UNIFIED_CONTEXT_PATH = STATE_DIR / "latest_unified_context.json"
SCENARIOS_PATH = STATE_DIR / "latest_three_scenarios.json"
MARKET_REGIME_PATH = STATE_DIR / "latest_market_regime.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"

OUTPUT_PATH = STATE_DIR / "latest_setup_family_activation.json"
HISTORY_PATH = DATA_DIR / "setup_family_activation_history.jsonl"

_FRESHNESS_WINDOW_SECONDS = 900
_VALID_FAMILIES = (
    "MOMENTUM_CONTINUATION",
    "TRAP_REVERSAL",
    "DOUBLE_DISTRIBUTION_REVERSAL",
    "ABSORPTION_REVERSAL",
    "LIQUIDITY_SWEEP_REVERSAL",
)


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


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _upper_text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).upper()


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


def _compact_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    representative = dict(cluster.get("paper_representative") or {})
    return {
        "cluster_id": cluster.get("cluster_id"),
        "cluster_family": cluster.get("cluster_family"),
        "direction": cluster.get("direction"),
        "dominant_context": cluster.get("dominant_context"),
        "dominant_model_id": cluster.get("dominant_model_id"),
        "cluster_score": cluster.get("cluster_score"),
        "paper_allowed_after_cooldown": cluster.get("paper_allowed_after_cooldown"),
        "cooldown_remaining_seconds": cluster.get("cooldown_remaining_seconds"),
        "cooldown_reason": cluster.get("cooldown_reason"),
        "paper_representative": _compact_model(representative) if representative else {},
        "model_families": list(cluster.get("model_families") or []),
        "reason_codes": list(cluster.get("reason_codes") or []),
    }


def _matching_family_tokens(family: str) -> tuple[str, ...]:
    if family == "MOMENTUM_CONTINUATION":
        return (
            "MOMENTUM_CONTINUATION",
            "ACCEPTANCE_BREAKOUT",
            "INITIATIVE_BREAKOUT",
            "MTF_ALIGNMENT",
            "VOLATILITY_EXPANSION_CONTINUATION",
        )
    if family == "TRAP_REVERSAL":
        return (
            "TRAP_REVERSAL",
            "TRAP_BUYERS_SHORT",
            "TRAP_SELLERS_LONG",
            "FAILED_BREAKOUT_TRAP",
            "STOP_RUN_ABSORPTION",
            "LIQUIDITY_SWEEP_REVERSAL",
            "AR01",
            "DAF",
            "FCR",
        )
    if family == "DOUBLE_DISTRIBUTION_REVERSAL":
        return ("DOUBLE_DISTRIBUTION_REVERSAL", "VALUE_ROTATION")
    if family == "ABSORPTION_REVERSAL":
        return ("ABSORPTION_REVERSAL", "ABSORPTION", "AR01", "DAF", "ICEBERG_ABSORPTION")
    if family == "LIQUIDITY_SWEEP_REVERSAL":
        return ("LIQUIDITY_SWEEP_REVERSAL", "LSR_", "PLR_")
    return ()


def _matches_family(family: str, payload: dict[str, Any]) -> bool:
    text = _upper_text(
        payload.get("model_id"),
        payload.get("model_family"),
        payload.get("dominant_context"),
        payload.get("cluster_family"),
        payload.get("dominant_model_id"),
        " ".join(str(item) for item in (payload.get("model_families") or [])),
    )
    return any(token in text for token in _matching_family_tokens(family))


def _scenario_exists(scenarios: dict[str, Any], direction: str) -> bool:
    if direction == "LONG":
        scenario = scenarios.get("bullish_scenario") or {}
    elif direction == "SHORT":
        scenario = scenarios.get("bearish_scenario") or {}
    else:
        return False
    return bool(scenario.get("condition") or scenario.get("quality"))


def _interpretation_tokens(interpretation: dict[str, Any]) -> set[str]:
    one_min = interpretation.get("1m") or {}
    raw_context = one_min.get("raw_context") or {}
    text = _upper_text(
        one_min.get("candle_label"),
        raw_context.get("candle_category"),
        raw_context.get("liquidity_event"),
        one_min.get("trap_summary"),
        one_min.get("liquidity_summary"),
        one_min.get("interpretation"),
        " ".join(str(item) for item in (one_min.get("reason_codes") or [])),
    )
    found: set[str] = set()
    for token in (
        "TRAP_CANDLE",
        "LIQUIDITY_SWEEP_UP",
        "LIQUIDITY_SWEEP_DOWN",
        "STOP_RUN_UP",
        "STOP_RUN_DOWN",
        "FAKE_BULLISH",
        "FAKE_BEARISH",
    ):
        if token in text:
            found.add(token)
    return found


def _infer_semantic_states(
    validated_models: list[dict[str, Any]],
    dominant_model: dict[str, Any],
    unified_context: dict[str, Any],
) -> set[str]:
    states: set[str] = set()
    dominant_state = str(dominant_model.get("dominant_semantic_state") or "").upper()
    if dominant_state:
        states.add(dominant_state)

    intent_context = unified_context.get("intent_context") or {}
    orderflow_context = unified_context.get("orderflow_context") or {}
    trapped_side = str(intent_context.get("trapped_side") or "UNKNOWN").upper()
    if trapped_side == "BUYERS":
        states.add("BUYER_TRAP")
    elif trapped_side == "SELLERS":
        states.add("SELLER_TRAP")
    if bool(orderflow_context.get("absorption")):
        states.add("ABSORPTION")

    for model in validated_models:
        matched = {str(item).upper() for item in (model.get("matched_conditions") or [])}
        direction = str(model.get("direction") or "NEUTRAL").upper()
        text = _upper_text(model.get("model_id"), model.get("model_family"), model.get("dominant_context"))
        if "ABSORPTION" in text or "AR01" in text or "DAF" in text or "ICEBERG" in text:
            states.add("ABSORPTION")
        if "COND_TRAPPED_BUYERS" in matched or "TRAP_BUYERS" in text:
            states.add("BUYER_TRAP")
        if "COND_TRAPPED_SELLERS" in matched or "TRAP_SELLERS" in text:
            states.add("SELLER_TRAP")
        if direction == "SHORT" and (
            {"COND_BUYERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_SELLERS_DEFENDING"} <= matched
            or "COND_FAKE_BULLISH" in matched
            or "COND_DELTA_PRICE_DIVERGENCE_BEARISH" in matched
        ):
            states.add("BUYER_EXHAUSTION")
        if direction == "LONG" and (
            {"COND_SELLERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_BUYERS_DEFENDING"} <= matched
            or "COND_FAKE_BEARISH" in matched
            or "COND_DELTA_PRICE_DIVERGENCE_BULLISH" in matched
        ):
            states.add("SELLER_EXHAUSTION")
    return states


def _fresh_dominant_model(dominant_model: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    if not dominant_model:
        return {}
    dominant_ts = _parse_ts(dominant_model.get("timestamp_utc"))
    semantic_ts = _parse_ts(semantic.get("timestamp_utc"))
    if dominant_ts is None or semantic_ts is None:
        return {}
    if abs((semantic_ts - dominant_ts).total_seconds()) > _FRESHNESS_WINDOW_SECONDS:
        return {}
    return dominant_model


def _sync_unified_context_overlay(output: dict[str, Any]) -> None:
    unified_context = _load_json(UNIFIED_CONTEXT_PATH)
    if not unified_context:
        return
    unified_context["active_setup_families"] = list(output.get("active_families") or [])
    unified_context["dominant_setup_family"] = output.get("dominant_setup_family", "NO_ACTIVE_SETUP_FAMILY")
    unified_context["ready_for_paper_research"] = bool(output.get("ready_for_paper_research"))
    unified_context["missing"] = list(output.get("missing") or [])
    readiness = dict(unified_context.get("readiness") or {})
    readiness["context_ready_for_setup_selection"] = bool(output.get("ready_for_paper_research"))
    readiness["missing_before_setup"] = list(output.get("missing") or [])
    unified_context["readiness"] = readiness
    UNIFIED_CONTEXT_PATH.write_text(json.dumps(unified_context, ensure_ascii=False, indent=2), encoding="utf-8")


def _rank_direction(items: list[dict[str, Any]]) -> str:
    scores = {"LONG": 0.0, "SHORT": 0.0}
    for item in items:
        direction = str(item.get("direction") or "NEUTRAL").upper()
        if direction not in scores:
            continue
        score = float(item.get("cluster_score") or item.get("match_score") or item.get("coherence_score") or 0.0)
        scores[direction] += score
    if scores["LONG"] > scores["SHORT"]:
        return "LONG"
    if scores["SHORT"] > scores["LONG"]:
        return "SHORT"
    return "NEUTRAL"


def _family_assessment(
    family: str,
    validated_models: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    allowed_clusters: list[dict[str, Any]],
    blocked_clusters: list[dict[str, Any]],
    dominant_model: dict[str, Any],
    unified_context: dict[str, Any],
    scenarios: dict[str, Any],
    market_regime: dict[str, Any],
    interpretation: dict[str, Any],
    business_zone: dict[str, Any],
    liquidity_map: dict[str, Any],
    semantic_states: set[str],
) -> dict[str, Any]:
    family_models = [model for model in validated_models if _matches_family(family, model)]
    family_clusters = [cluster for cluster in clusters if _matches_family(family, cluster)]
    family_allowed = [cluster for cluster in allowed_clusters if _matches_family(family, cluster)]
    family_blocked = [cluster for cluster in blocked_clusters if _matches_family(family, cluster)]

    direction_sources = family_allowed or family_clusters or family_models
    direction = _rank_direction(direction_sources)
    dominant_direction = str(dominant_model.get("dominant_direction") or "NEUTRAL").upper()
    if direction == "NEUTRAL" and dominant_direction in {"LONG", "SHORT"}:
        direction = dominant_direction

    reasons: list[str] = []
    blocking: list[str] = []
    missing: list[str] = []
    score = 0.0

    regime = str(market_regime.get("regime") or "UNKNOWN").upper()
    day_type = str(market_regime.get("day_type") or "UNKNOWN").upper()
    interpretation_flags = _interpretation_tokens(interpretation)
    scenario_ok = direction in {"LONG", "SHORT"} and _scenario_exists(scenarios, direction)
    semantic_contradiction = dominant_direction in {"LONG", "SHORT"} and direction in {"LONG", "SHORT"} and dominant_direction != direction
    has_near_liquidity = bool(liquidity_map.get("near_liquidity") or (unified_context.get("liquidity_context") or {}).get("liquidity_cluster") == "NEAR")

    value_area = business_zone.get("value_area") or {}
    auction_summary = business_zone.get("auction_summary") or {}
    value_position = str(value_area.get("value_position") or "UNKNOWN").upper()
    value_migration = str(value_area.get("value_migration") or "UNKNOWN").upper()
    business_zone_support = (
        value_migration not in {"", "UNKNOWN", "FLAT"}
        or value_position in {"ABOVE_VALUE", "BELOW_VALUE"}
        or str(auction_summary.get("auction_state") or "").upper() == "ACCEPTANCE"
    )

    family_evidence = bool(family_models or family_clusters or family_allowed)
    if family_evidence:
        reasons.append("MODEL_OR_CLUSTER_FAMILY_MATCH")
    else:
        missing.append("MODEL_OR_CLUSTER_FAMILY_MISSING")

    if family == "MOMENTUM_CONTINUATION":
        regime_ok = regime in {"MOMENTUM_MODE", "TRANSITION_MODE"}
        if family_evidence:
            score += 0.22
        if regime_ok:
            score += 0.22
            reasons.append(f"REGIME_{regime}")
        else:
            blocking.append(f"REGIME_NOT_MOMENTUM_OR_TRANSITION_{regime}")
        if scenario_ok:
            score += 0.14
            reasons.append(f"SCENARIO_{direction}")
        else:
            missing.append("SCENARIO_DIRECTION_MISSING")
        if family_allowed:
            score += 0.28
            reasons.append("COOLDOWN_ALLOWED_CLUSTER_PRESENT")
        else:
            blocking.append("NO_ALLOWED_CLUSTER_AFTER_COOLDOWN")
        if not semantic_contradiction:
            score += 0.14
            reasons.append("NO_DOMINANT_SEMANTIC_CONTRADICTION")
        else:
            blocking.append(f"DOMINANT_DIRECTION_CONTRADICTION_{dominant_direction}")
        if not regime_ok:
            score = min(score, 0.54)
    elif family == "TRAP_REVERSAL":
        trap_interpretation = bool(
            interpretation_flags
            & {
                "TRAP_CANDLE",
                "LIQUIDITY_SWEEP_UP",
                "LIQUIDITY_SWEEP_DOWN",
                "STOP_RUN_UP",
                "STOP_RUN_DOWN",
                "FAKE_BULLISH",
                "FAKE_BEARISH",
            }
        )
        trap_semantic = bool(semantic_states & {"BUYER_EXHAUSTION", "SELLER_EXHAUSTION", "BUYER_TRAP", "SELLER_TRAP", "ABSORPTION"})
        if family_evidence:
            score += 0.28
        if trap_interpretation:
            score += 0.18
            reasons.append("INTERPRETATION_TRAP_EVIDENCE")
        else:
            missing.append("TRAP_INTERPRETATION_MISSING")
        if trap_semantic:
            score += 0.22
            reasons.append("SEMANTIC_TRAP_OR_EXHAUSTION")
        else:
            missing.append("TRAP_SEMANTIC_STATE_MISSING")
        if family_allowed:
            score += 0.22
            reasons.append("COOLDOWN_ALLOWED_CLUSTER_PRESENT")
        else:
            blocking.append("NO_ALLOWED_CLUSTER_AFTER_COOLDOWN")
        if dominant_direction == direction and direction in {"LONG", "SHORT"}:
            score += 0.10
            reasons.append("DOMINANT_DIRECTION_ALIGNED")
    elif family == "DOUBLE_DISTRIBUTION_REVERSAL":
        regime_ok = day_type == "DOUBLE_DISTRIBUTION_DAY" or regime == "TRANSITION_MODE"
        if family_evidence:
            score += 0.22
        else:
            missing.append("DOUBLE_DISTRIBUTION_MODEL_FAMILY_MISSING")
        if regime_ok:
            score += 0.22
            reasons.append(f"DAY_OR_REGIME_{day_type}_{regime}")
        else:
            blocking.append("DAY_TYPE_OR_REGIME_NOT_DOUBLE_DISTRIBUTION")
        if business_zone_support:
            score += 0.18
            reasons.append("BUSINESS_ZONE_ROTATION_EVIDENCE")
        else:
            missing.append("BUSINESS_ZONE_ROTATION_MISSING")
        if scenario_ok:
            score += 0.16
            reasons.append(f"SCENARIO_{direction}")
        else:
            missing.append("SCENARIO_DIRECTION_MISSING")
        if family_allowed:
            score += 0.22
            reasons.append("COOLDOWN_ALLOWED_CLUSTER_PRESENT")
        elif family_clusters:
            blocking.append("NO_ALLOWED_CLUSTER_AFTER_COOLDOWN")
        if not regime_ok:
            score = min(score, 0.54)
    elif family == "ABSORPTION_REVERSAL":
        absorption_semantic = bool(semantic_states & {"ABSORPTION", "BUYER_EXHAUSTION", "SELLER_EXHAUSTION"})
        if family_evidence:
            score += 0.32
        else:
            missing.append("ABSORPTION_MODEL_FAMILY_MISSING")
        if absorption_semantic:
            score += 0.22
            reasons.append("SEMANTIC_ABSORPTION_OR_EXHAUSTION")
        else:
            missing.append("ABSORPTION_SEMANTIC_STATE_MISSING")
        if has_near_liquidity:
            score += 0.18
            reasons.append("NEAR_LIQUIDITY_PRESENT")
        else:
            missing.append("NEAR_LIQUIDITY_MISSING")
        if family_allowed:
            score += 0.18
            reasons.append("COOLDOWN_ALLOWED_CLUSTER_PRESENT")
        elif family_clusters:
            blocking.append("NO_ALLOWED_CLUSTER_AFTER_COOLDOWN")
        if dominant_direction == direction and direction in {"LONG", "SHORT"}:
            score += 0.10
            reasons.append("DOMINANT_DIRECTION_ALIGNED")
    elif family == "LIQUIDITY_SWEEP_REVERSAL":
        sweep_candle = bool(interpretation_flags & {"LIQUIDITY_SWEEP_UP", "LIQUIDITY_SWEEP_DOWN", "STOP_RUN_UP", "STOP_RUN_DOWN"})
        sweep_model = any(
            token in _upper_text(model.get("model_id"), model.get("model_family"))
            for model in family_models
            for token in ("LSR_", "PLR_", "LIQUIDITY_SWEEP_REVERSAL")
        ) or any(
            token in _upper_text(cluster.get("dominant_model_id"), cluster.get("cluster_family"))
            for cluster in family_clusters
            for token in ("LSR_", "PLR_", "LIQUIDITY_SWEEP_REVERSAL")
        )
        if sweep_model:
            score += 0.34
            reasons.append("SWEEP_MODEL_PRESENT")
        else:
            missing.append("SWEEP_MODEL_MISSING")
        if sweep_candle:
            score += 0.24
            reasons.append("SWEEP_CANDLE_PRESENT")
        else:
            missing.append("SWEEP_CANDLE_MISSING")
        if dominant_direction == direction and direction in {"LONG", "SHORT"}:
            score += 0.18
            reasons.append("DOMINANT_DIRECTION_ALIGNED")
        else:
            blocking.append("DOMINANT_DIRECTION_NOT_SWEEP_ALIGNED")
        if family_allowed:
            score += 0.16
            reasons.append("COOLDOWN_ALLOWED_CLUSTER_PRESENT")
        elif family_clusters:
            blocking.append("NO_ALLOWED_CLUSTER_AFTER_COOLDOWN")

    score = round(max(0.0, min(1.0, score)), 4)
    active = score >= 0.55
    paper_ready = active and bool(family_allowed) and direction in {"LONG", "SHORT"}
    if family == "MOMENTUM_CONTINUATION" and regime not in {"MOMENTUM_MODE", "TRANSITION_MODE"}:
        paper_ready = False
    if family == "DOUBLE_DISTRIBUTION_REVERSAL" and day_type != "DOUBLE_DISTRIBUTION_DAY" and regime != "TRANSITION_MODE":
        paper_ready = False
    if family == "LIQUIDITY_SWEEP_REVERSAL" and dominant_direction != direction:
        paper_ready = False

    if score >= 0.75:
        reasons.append("ACTIVATION_STRONG")
    elif active:
        reasons.append("ACTIVATION_ACTIVE")

    source_clusters = family_allowed or family_clusters or family_blocked
    return {
        "family": family,
        "direction": direction if direction in {"LONG", "SHORT"} else "NEUTRAL",
        "score": score,
        "active": active,
        "paper_ready": paper_ready,
        "source_models": [_compact_model(model) for model in family_models],
        "source_clusters": [_compact_cluster(cluster) for cluster in source_clusters],
        "activation_reasons": sorted(set(reasons)),
        "blocking_reasons": sorted(set(blocking)),
        "missing": sorted(set(missing)),
    }


def run_setup_family_activation_engine() -> dict[str, Any]:
    semantic = _load_json(SEMANTIC_PATH) or {}
    clusters_payload = _load_json(CLUSTERS_PATH) or {}
    cooldown = _load_json(COOLDOWN_PATH) or {}
    dominant_model_raw = _load_json(DOMINANT_MODEL_PATH) or {}
    unified_context = _load_json(UNIFIED_CONTEXT_PATH) or {}
    scenarios = _load_json(SCENARIOS_PATH) or {}
    market_regime = _load_json(MARKET_REGIME_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}

    validated_models = [model for model in (semantic.get("validated_models") or []) if bool(model.get("paper_allowed", True))]
    clusters = list(clusters_payload.get("clusters") or [])
    allowed_clusters = list(cooldown.get("allowed_clusters") or [])
    blocked_clusters = list(cooldown.get("blocked_clusters") or [])
    dominant_model = _fresh_dominant_model(dominant_model_raw, semantic)
    semantic_states = _infer_semantic_states(validated_models, dominant_model, unified_context)

    assessments = [
        _family_assessment(
            family=family,
            validated_models=validated_models,
            clusters=clusters,
            allowed_clusters=allowed_clusters,
            blocked_clusters=blocked_clusters,
            dominant_model=dominant_model,
            unified_context=unified_context,
            scenarios=scenarios,
            market_regime=market_regime,
            interpretation=interpretation,
            business_zone=business_zone,
            liquidity_map=liquidity_map,
            semantic_states=semantic_states,
        )
        for family in _VALID_FAMILIES
    ]

    active_assessments = [item for item in assessments if item.get("active")]
    ready_assessments = [item for item in active_assessments if item.get("paper_ready")]
    ranked_assessments = ready_assessments or active_assessments or sorted(assessments, key=lambda item: float(item.get("score") or 0.0), reverse=True)
    dominant = ranked_assessments[0] if ranked_assessments else None

    dominant_family = "NO_ACTIVE_SETUP_FAMILY"
    direction = "NEUTRAL"
    activation_score = 0.0
    ready_for_paper_research = False
    source_models: list[dict[str, Any]] = []
    source_clusters: list[dict[str, Any]] = []
    activation_reasons: list[str] = []
    blocking_reasons: list[str] = []
    missing: list[str] = ["NO_VALIDATED_MODELS_OR_CLUSTERS"]

    if dominant is not None:
        direction = str(dominant.get("direction") or "NEUTRAL")
        activation_score = float(dominant.get("score") or 0.0)
        ready_for_paper_research = bool(dominant.get("paper_ready"))
        source_models = list(dominant.get("source_models") or [])
        source_clusters = list(dominant.get("source_clusters") or [])
        activation_reasons = list(dominant.get("activation_reasons") or [])
        blocking_reasons = list(dominant.get("blocking_reasons") or [])
        missing = list(dominant.get("missing") or [])
        if dominant.get("active"):
            dominant_family = str(dominant.get("family") or "NO_ACTIVE_SETUP_FAMILY")
        elif not missing:
            missing = ["NO_FAMILY_SCORE_ABOVE_THRESHOLD"]

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(semantic.get("symbol") or clusters_payload.get("symbol") or cooldown.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "VALIDATED_CLUSTERED_SETUP_FAMILY_ACTIVATION",
        },
        "active_families": [item.get("family") for item in sorted(active_assessments, key=lambda entry: float(entry.get("score") or 0.0), reverse=True)],
        "dominant_setup_family": dominant_family,
        "direction": direction if direction in {"LONG", "SHORT"} else "NEUTRAL",
        "activation_score": round(activation_score, 4),
        "ready_for_paper_research": ready_for_paper_research,
        "source_models": source_models,
        "source_clusters": source_clusters,
        "activation_reasons": activation_reasons,
        "blocking_reasons": blocking_reasons,
        "missing": missing,
        "reason_codes": [
            f"ACTIVE_FAMILIES_{len(active_assessments)}",
            f"DOMINANT_SETUP_FAMILY_{dominant_family}",
            f"READY_FOR_PAPER_{str(ready_for_paper_research).upper()}",
            "NO_LIVE_EXECUTION",
            "NO_PRIVATE_API",
            "PAPER_ONLY",
        ],
        "data_quality": {
            "level": "HIGH" if semantic and clusters_payload and cooldown else "MEDIUM" if semantic or clusters_payload else "LOW",
            "missing_inputs": [
                name
                for name, payload in {
                    "latest_model_semantic_validation": semantic,
                    "latest_model_clusters": clusters_payload,
                    "latest_model_cooldown": cooldown,
                    "latest_unified_context": unified_context,
                    "latest_three_scenarios": scenarios,
                    "latest_market_regime": market_regime,
                    "latest_interpretation": interpretation,
                    "latest_business_zone": business_zone,
                    "latest_liquidity_map": liquidity_map,
                }.items()
                if not payload
            ],
        },
        "feeds_next": [
            "PAPER_TRADE_FACTORY",
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
    _sync_unified_context_overlay(output)
    _append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_setup_family_activation_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
