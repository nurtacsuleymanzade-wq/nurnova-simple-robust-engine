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

_VALID_FAMILIES = (
    "MOMENTUM_CONTINUATION",
    "TRAP_REVERSAL",
    "DOUBLE_DISTRIBUTION_REVERSAL",
    "ABSORPTION_REVERSAL",
    "LIQUIDITY_SWEEP_REVERSAL",
)

_POSITIVE_WEIGHTS = {
    "dominant_model_agreement": 0.20,
    "validated_semantic_agreement": 0.20,
    "cooldown_allowed_cluster": 0.15,
    "matching_market_regime": 0.15,
    "matching_scenario_direction": 0.10,
    "matching_candle_category": 0.10,
    "matching_interpretation_evidence": 0.10,
}

_NEGATIVE_WEIGHTS = {
    "semantic_contradiction": -0.30,
    "cooldown_blocked_dominant_cluster": -0.25,
    "missing_scenario": -0.10,
    "missing_regime": -0.10,
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


def _upper_text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).upper()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


def _component(applied: bool, value: float, evidence: str) -> dict[str, Any]:
    return {
        "applied": bool(applied),
        "value": round(value if applied else 0.0, 4),
        "evidence": evidence,
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


def _direction(value: Any) -> str:
    direction = str(value or "NEUTRAL").upper()
    return direction if direction in {"LONG", "SHORT"} else "NEUTRAL"


def _best_cluster(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    if not clusters:
        return {}
    return max(clusters, key=lambda item: _safe_float(item.get("cluster_score")))


def _best_model(models: list[dict[str, Any]]) -> dict[str, Any]:
    if not models:
        return {}
    return max(
        models,
        key=lambda item: max(
            _safe_float(item.get("coherence_score")),
            _safe_float(item.get("match_score")),
        ),
    )


def _scenario_exists(scenarios: dict[str, Any], direction: str) -> bool:
    if direction == "LONG":
        scenario = scenarios.get("bullish_scenario") or {}
    elif direction == "SHORT":
        scenario = scenarios.get("bearish_scenario") or {}
    else:
        return False
    return bool(scenario.get("condition") or scenario.get("quality"))


def _scenario_direction(scenarios: dict[str, Any], preferred_direction: str) -> str:
    preferred = _direction(preferred_direction)
    if preferred in {"LONG", "SHORT"} and _scenario_exists(scenarios, preferred):
        return preferred

    bullish = scenarios.get("bullish_scenario") or {}
    bearish = scenarios.get("bearish_scenario") or {}
    bullish_quality = str(bullish.get("quality") or "").upper()
    bearish_quality = str(bearish.get("quality") or "").upper()
    quality_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    if quality_rank.get(bullish_quality, 0) > quality_rank.get(bearish_quality, 0):
        return "LONG"
    if quality_rank.get(bearish_quality, 0) > quality_rank.get(bullish_quality, 0):
        return "SHORT"
    if bullish:
        return "LONG"
    if bearish:
        return "SHORT"
    return "NEUTRAL"


def _interpretation_tokens(interpretation: dict[str, Any]) -> set[str]:
    one_min = interpretation.get("1m") or {}
    raw_context = one_min.get("raw_context") or {}
    text = _upper_text(
        one_min.get("candle_label"),
        raw_context.get("candle_category"),
        raw_context.get("liquidity_event"),
        raw_context.get("fake_signal"),
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
        "WALL_REACTION",
        "ABSORPTION",
        "RETURN_TO_VALUE",
        "OUTSIDE_VALUE",
        "VALUE_MIGRATION",
        "ACCEPTED_DIRECTIONAL_BREAK",
    ):
        if token in text:
            found.add(token)
    return found


def _candle_direction(tokens: set[str], trapped_side: str) -> str:
    if "LIQUIDITY_SWEEP_UP" in tokens or "STOP_RUN_UP" in tokens or "FAKE_BULLISH" in tokens:
        return "SHORT"
    if "LIQUIDITY_SWEEP_DOWN" in tokens or "STOP_RUN_DOWN" in tokens or "FAKE_BEARISH" in tokens:
        return "LONG"
    if "TRAP_CANDLE" in tokens:
        if trapped_side == "BUYERS":
            return "SHORT"
        if trapped_side == "SELLERS":
            return "LONG"
    return "NEUTRAL"


def _interpretation_direction(
    interpretation: dict[str, Any],
    trapped_side: str,
    liquidity_event: str,
) -> str:
    one_min = interpretation.get("1m") or {}
    raw_context = one_min.get("raw_context") or {}
    text = _upper_text(
        one_min.get("interpretation"),
        one_min.get("trap_summary"),
        one_min.get("liquidity_summary"),
        raw_context.get("fake_signal"),
        raw_context.get("attacking_side"),
        raw_context.get("defending_side"),
    )
    if any(token in text for token in ("FAKE_BULLISH", "BUYERS_TRAPPED", "TRAPPED_BUYERS")):
        return "SHORT"
    if any(token in text for token in ("FAKE_BEARISH", "SELLERS_TRAPPED", "TRAPPED_SELLERS")):
        return "LONG"
    if "WALL_REACTION" in liquidity_event:
        if trapped_side == "BUYERS":
            return "SHORT"
        if trapped_side == "SELLERS":
            return "LONG"
    return "NEUTRAL"


def _liquidity_event(interpretation: dict[str, Any]) -> str:
    return str((((interpretation.get("1m") or {}).get("raw_context") or {}).get("liquidity_event") or "UNKNOWN")).upper()


def _semantic_states(
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
        direction = _direction(model.get("direction"))
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


def _semantic_state_direction(semantic_states: set[str]) -> str:
    long_states = {"SELLER_EXHAUSTION", "SELLER_TRAP"}
    short_states = {"BUYER_EXHAUSTION", "BUYER_TRAP"}
    long_count = len(semantic_states & long_states)
    short_count = len(semantic_states & short_states)
    if long_count > short_count:
        return "LONG"
    if short_count > long_count:
        return "SHORT"
    return "NEUTRAL"


def _liquidity_event_direction(liquidity_event: str, candle_tokens: set[str], trapped_side: str) -> str:
    text = _upper_text(liquidity_event, " ".join(candle_tokens))
    if any(token in text for token in ("LIQUIDITY_SWEEP_UP", "STOP_RUN_UP", "FAKE_BULLISH")):
        return "SHORT"
    if any(token in text for token in ("LIQUIDITY_SWEEP_DOWN", "STOP_RUN_DOWN", "FAKE_BEARISH")):
        return "LONG"
    if "WALL_REACTION" in text:
        if trapped_side == "BUYERS":
            return "SHORT"
        if trapped_side == "SELLERS":
            return "LONG"
    return "NEUTRAL"


def _activation_band(score: float) -> str:
    if score >= 0.75:
        return "STRONG_ACTIVE"
    if score >= 0.55:
        return "ACTIVE"
    if score >= 0.45:
        return "EARLY_RESEARCH"
    return "WATCH_ONLY"


def _regime_match(family: str, market_regime: dict[str, Any]) -> tuple[bool, str]:
    regime = str(market_regime.get("regime") or "UNKNOWN").upper()
    day_type = str(market_regime.get("day_type") or "UNKNOWN").upper()
    if family == "MOMENTUM_CONTINUATION":
        matched = regime in {"MOMENTUM_MODE", "TRANSITION_MODE"}
        return matched, f"REGIME_{regime}"
    if family == "TRAP_REVERSAL":
        matched = regime in {"BALANCE_MODE", "TRANSITION_MODE"}
        return matched, f"REGIME_{regime}"
    if family == "DOUBLE_DISTRIBUTION_REVERSAL":
        matched = day_type == "DOUBLE_DISTRIBUTION_DAY" or regime == "TRANSITION_MODE"
        return matched, f"DAY_TYPE_{day_type}_REGIME_{regime}"
    if family == "ABSORPTION_REVERSAL":
        matched = regime in {"BALANCE_MODE", "TRANSITION_MODE"}
        return matched, f"REGIME_{regime}"
    if family == "LIQUIDITY_SWEEP_REVERSAL":
        matched = regime in {"BALANCE_MODE", "TRANSITION_MODE"}
        return matched, f"REGIME_{regime}"
    return False, "REGIME_UNKNOWN"


def _candle_match(
    family: str,
    direction: str,
    candle_tokens: set[str],
    trapped_side: str,
) -> tuple[bool, str]:
    candle_direction = _candle_direction(candle_tokens, trapped_side)
    if family == "MOMENTUM_CONTINUATION":
        matched = (
            direction in {"LONG", "SHORT"}
            and (
                ("ACCEPTED_DIRECTIONAL_BREAK" in candle_tokens and candle_direction == direction)
                or (not candle_tokens and False)
            )
        )
        return matched, "ACCEPTED_DIRECTIONAL_BREAK" if matched else "CANDLE_CATEGORY_NOT_MOMENTUM"
    if family == "TRAP_REVERSAL":
        matched = bool(
            candle_tokens
            & {
                "TRAP_CANDLE",
                "LIQUIDITY_SWEEP_UP",
                "LIQUIDITY_SWEEP_DOWN",
                "STOP_RUN_UP",
                "STOP_RUN_DOWN",
                "FAKE_BULLISH",
                "FAKE_BEARISH",
            }
        ) and candle_direction == direction
        return matched, ",".join(sorted(candle_tokens)) if matched else "CANDLE_CATEGORY_NOT_TRAP"
    if family == "DOUBLE_DISTRIBUTION_REVERSAL":
        matched = bool(candle_tokens & {"RETURN_TO_VALUE", "OUTSIDE_VALUE", "VALUE_MIGRATION"})
        return matched, ",".join(sorted(candle_tokens)) if matched else "CANDLE_CATEGORY_NOT_VALUE_ROTATION"
    if family == "ABSORPTION_REVERSAL":
        matched = bool(candle_tokens & {"STOP_RUN_UP", "STOP_RUN_DOWN", "FAKE_BULLISH", "FAKE_BEARISH"}) and candle_direction == direction
        return matched, ",".join(sorted(candle_tokens)) if matched else "CANDLE_CATEGORY_NOT_ABSORPTION"
    if family == "LIQUIDITY_SWEEP_REVERSAL":
        matched = bool(candle_tokens & {"LIQUIDITY_SWEEP_UP", "LIQUIDITY_SWEEP_DOWN", "STOP_RUN_UP", "STOP_RUN_DOWN"}) and candle_direction == direction
        return matched, ",".join(sorted(candle_tokens)) if matched else "CANDLE_CATEGORY_NOT_SWEEP"
    return False, "CANDLE_CATEGORY_UNKNOWN"


def _interpretation_match(
    family: str,
    direction: str,
    interpretation: dict[str, Any],
    trapped_side: str,
    liquidity_event: str,
    business_zone: dict[str, Any],
    liquidity_map: dict[str, Any],
) -> tuple[bool, str]:
    one_min = interpretation.get("1m") or {}
    text = _upper_text(
        one_min.get("interpretation"),
        one_min.get("trap_summary"),
        one_min.get("liquidity_summary"),
        liquidity_event,
    )
    interpretation_direction = _interpretation_direction(interpretation, trapped_side, liquidity_event)
    near_liquidity = bool(liquidity_map.get("near_liquidity") or [])
    value_area = business_zone.get("value_area") or {}
    value_position = str(value_area.get("value_position") or "").upper()
    value_migration = str(value_area.get("value_migration") or "").upper()

    if family == "MOMENTUM_CONTINUATION":
        matched = interpretation_direction == direction and any(token in text for token in ("CONTINUATION", "BREAKOUT", "ACCEPTED DIRECTIONAL BREAK"))
        return matched, "INTERPRETATION_CONTINUATION" if matched else "INTERPRETATION_NOT_MOMENTUM"
    if family == "TRAP_REVERSAL":
        matched = interpretation_direction == direction and (
            "WALL_REACTION" in liquidity_event
            or any(token in text for token in ("STALL", "TRAP", "FAILED TO ADVANCE", "FAKE"))
            or trapped_side in {"BUYERS", "SELLERS"}
        )
        return matched, "INTERPRETATION_TRAP_CONTEXT" if matched else "INTERPRETATION_NOT_TRAP"
    if family == "DOUBLE_DISTRIBUTION_REVERSAL":
        matched = (
            any(token in text for token in ("RETURN TO VALUE", "OUTSIDE VALUE", "VALUE MIGRATION", "ROTATION"))
            or value_migration not in {"", "UNKNOWN", "FLAT"}
            or value_position in {"ABOVE_VALUE", "BELOW_VALUE"}
        )
        return matched, "INTERPRETATION_VALUE_ROTATION" if matched else "INTERPRETATION_NOT_DOUBLE_DISTRIBUTION"
    if family == "ABSORPTION_REVERSAL":
        matched = interpretation_direction == direction and near_liquidity and (
            "WALL_REACTION" in liquidity_event
            or "ABSORPTION" in text
            or "STALL" in text
        )
        return matched, "INTERPRETATION_ABSORPTION_CONTEXT" if matched else "INTERPRETATION_NOT_ABSORPTION"
    if family == "LIQUIDITY_SWEEP_REVERSAL":
        matched = interpretation_direction == direction and any(
            token in text
            for token in ("LIQUIDITY SWEEP", "STOP RUN", "WALL_REACTION", "FAILED TO ADVANCE")
        )
        return matched, "INTERPRETATION_SWEEP_CONTEXT" if matched else "INTERPRETATION_NOT_SWEEP"
    return False, "INTERPRETATION_UNKNOWN"


def _validated_semantic_match(
    family: str,
    direction: str,
    family_models: list[dict[str, Any]],
    semantic_states: set[str],
) -> tuple[bool, str]:
    directional_models = [
        model
        for model in family_models
        if _direction(model.get("direction")) == direction
        and str(model.get("semantic_status") or "").upper() in {"VALID", "MIXED_BUT_RESEARCHABLE"}
    ]
    if family == "TRAP_REVERSAL":
        semantic_match = bool(semantic_states & {"BUYER_EXHAUSTION", "SELLER_EXHAUSTION", "BUYER_TRAP", "SELLER_TRAP", "ABSORPTION"})
        return bool(directional_models) and semantic_match, "SEMANTIC_TRAP_OR_EXHAUSTION"
    if family == "ABSORPTION_REVERSAL":
        semantic_match = bool(semantic_states & {"ABSORPTION", "BUYER_EXHAUSTION", "SELLER_EXHAUSTION"})
        return bool(directional_models) and semantic_match, "SEMANTIC_ABSORPTION_OR_EXHAUSTION"
    return bool(directional_models), "SEMANTIC_VALIDATED_DIRECTIONAL_MODEL"


def _semantic_contradiction(
    direction: str,
    family_models: list[dict[str, Any]],
    dominant_model: dict[str, Any],
) -> tuple[bool, str]:
    dominant_direction = _direction(dominant_model.get("dominant_direction"))
    if dominant_direction in {"LONG", "SHORT"} and direction in {"LONG", "SHORT"} and dominant_direction != direction:
        return True, f"DOMINANT_DIRECTION_{dominant_direction}_CONTRADICTS_{direction}"

    directional_models = [model for model in family_models if _direction(model.get("direction")) == direction]
    opposite_models = [model for model in family_models if _direction(model.get("direction")) in {"LONG", "SHORT"} and _direction(model.get("direction")) != direction]
    best_directional = _best_model(directional_models)
    best_opposite = _best_model(opposite_models)
    if best_directional and best_opposite:
        if _safe_float(best_opposite.get("match_score")) >= _safe_float(best_directional.get("match_score")):
            return True, f"OPPOSITE_DIRECTION_VALIDATED_MODEL_{best_opposite.get('model_id')}"
    return False, "NO_SEMANTIC_CONTRADICTION"


def _direction_resolution(
    family: str,
    family_allowed: list[dict[str, Any]],
    family_clusters: list[dict[str, Any]],
    family_models: list[dict[str, Any]],
    dominant_model: dict[str, Any],
    scenarios: dict[str, Any],
    interpretation: dict[str, Any],
    trapped_side: str,
    liquidity_event: str,
    semantic_states: set[str],
) -> dict[str, Any]:
    dominant_cluster = _best_cluster(family_allowed) or _best_cluster(family_clusters)
    cluster_direction = _direction(dominant_cluster.get("direction"))

    dominant_model_matches = _matches_family(family, dominant_model)
    if dominant_model_matches:
        model_direction = _direction(dominant_model.get("dominant_direction"))
        model_evidence = str(dominant_model.get("dominant_models") or dominant_model.get("dominant_model_cluster") or "GLOBAL_DOMINANT_MODEL")
    else:
        family_top_model = _best_model(family_models)
        model_direction = _direction(family_top_model.get("direction"))
        model_evidence = str(family_top_model.get("model_id") or "FAMILY_TOP_MODEL")

    preferred_direction = cluster_direction if cluster_direction in {"LONG", "SHORT"} else model_direction
    scenario_direction = _scenario_direction(scenarios, preferred_direction)
    interpretation_direction = _interpretation_direction(interpretation, trapped_side, liquidity_event)
    candle_tokens = _interpretation_tokens(interpretation)
    candle_direction = _candle_direction(candle_tokens, trapped_side)
    liquidity_direction = _liquidity_event_direction(liquidity_event, candle_tokens, trapped_side)
    semantic_direction = _semantic_state_direction(semantic_states)

    direction_sources = {
        "dominant_validated_cluster": cluster_direction,
        "dominant_model": model_direction,
        "liquidity_event_direction": liquidity_direction,
        "scenario_direction": scenario_direction,
        "interpretation_direction": interpretation_direction,
        "candle_category_direction": candle_direction,
        "semantic_state_direction": semantic_direction,
    }

    authority_sources = {
        "dominant_validated_cluster": cluster_direction,
        "dominant_model": model_direction,
        "liquidity_event_direction": liquidity_direction,
        "candle_category_direction": candle_direction,
        "semantic_state_direction": semantic_direction,
    }
    agreement_count = {
        "LONG": sum(1 for value in authority_sources.values() if value == "LONG"),
        "SHORT": sum(1 for value in authority_sources.values() if value == "SHORT"),
    }

    resolved = "NEUTRAL"
    resolution_mode = "NEUTRAL_HARD_CONFLICT"
    dominant_cluster_exists = cluster_direction in {"LONG", "SHORT"}
    if dominant_cluster_exists and agreement_count.get(cluster_direction, 0) >= 2:
        resolved = cluster_direction
        resolution_mode = "DOMINANT_CLUSTER_AUTHORITY"
    else:
        best_direction = max(("LONG", "SHORT"), key=lambda item: agreement_count.get(item, 0))
        if agreement_count.get(best_direction, 0) >= 2:
            resolved = best_direction
            resolution_mode = "MAJORITY_WITH_RISK_TAG"

    conflicts: list[dict[str, str]] = []
    if resolved in {"LONG", "SHORT"}:
        for key, candidate in direction_sources.items():
            if candidate in {"LONG", "SHORT"} and candidate != resolved:
                conflicts.append({"source": key, "direction": candidate})

    conflict_count = len(conflicts)
    if resolution_mode != "DOMINANT_CLUSTER_AUTHORITY" and conflict_count >= 4 and not dominant_cluster_exists:
        resolved = "NEUTRAL"
        resolution_mode = "NEUTRAL_HARD_CONFLICT"

    return {
        "resolved_direction": resolved,
        "direction_sources": direction_sources,
        "direction_conflicts": conflicts,
        "agreement_count": agreement_count,
        "conflict_count": conflict_count,
        "resolution_mode": resolution_mode,
        "dominant_cluster_id": dominant_cluster.get("cluster_id"),
        "dominant_model_evidence": model_evidence,
    }


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
    family_models_all = [model for model in validated_models if _matches_family(family, model)]
    family_clusters_all = [cluster for cluster in clusters if _matches_family(family, cluster)]
    family_allowed_all = [cluster for cluster in allowed_clusters if _matches_family(family, cluster)]
    family_blocked_all = [cluster for cluster in blocked_clusters if _matches_family(family, cluster)]

    trapped_side = str((unified_context.get("intent_context") or {}).get("trapped_side") or "UNKNOWN").upper()
    liquidity_event = _liquidity_event(interpretation)
    direction_resolution = _direction_resolution(
        family=family,
        family_allowed=family_allowed_all,
        family_clusters=family_clusters_all,
        family_models=family_models_all,
        dominant_model=dominant_model,
        scenarios=scenarios,
        interpretation=interpretation,
        trapped_side=trapped_side,
        liquidity_event=liquidity_event,
        semantic_states=semantic_states,
    )
    direction = direction_resolution["resolved_direction"]

    family_models = [
        model
        for model in family_models_all
        if direction == "NEUTRAL" or _direction(model.get("direction")) == direction
    ]
    family_clusters = [
        cluster
        for cluster in family_clusters_all
        if direction == "NEUTRAL" or _direction(cluster.get("direction")) == direction
    ]
    family_allowed = [
        cluster
        for cluster in family_allowed_all
        if direction == "NEUTRAL" or _direction(cluster.get("direction")) == direction
    ]
    family_blocked = [
        cluster
        for cluster in family_blocked_all
        if direction == "NEUTRAL" or _direction(cluster.get("direction")) == direction
    ]

    dominant_cluster = _best_cluster(family_allowed) or _best_cluster(family_clusters)
    blocked_dominant_cluster = _best_cluster(family_blocked)

    candle_tokens = _interpretation_tokens(interpretation)
    regime_matched, regime_evidence = _regime_match(family, market_regime)
    scenario_matched = direction in {"LONG", "SHORT"} and _scenario_exists(scenarios, direction)
    candle_matched, candle_evidence = _candle_match(family, direction, candle_tokens, trapped_side)
    interpretation_matched, interpretation_evidence = _interpretation_match(
        family=family,
        direction=direction,
        interpretation=interpretation,
        trapped_side=trapped_side,
        liquidity_event=liquidity_event,
        business_zone=business_zone,
        liquidity_map=liquidity_map,
    )
    semantic_matched, semantic_evidence = _validated_semantic_match(
        family=family,
        direction=direction,
        family_models=family_models,
        semantic_states=semantic_states,
    )
    contradiction_applied, contradiction_evidence = _semantic_contradiction(direction, family_models_all, dominant_model)
    risk_tags: list[str] = []
    if (
        direction in {"LONG", "SHORT"}
        and _direction(direction_resolution["direction_sources"].get("scenario_direction")) in {"LONG", "SHORT"}
        and _direction(direction_resolution["direction_sources"].get("scenario_direction")) != direction
    ):
        risk_tags.append("SCENARIO_DIRECTION_CONFLICT")

    dominant_agreement_applied = False
    dominant_agreement_evidence = "NO_DOMINANT_MODEL_OR_CLUSTER_AGREEMENT"
    if dominant_cluster and direction in {"LONG", "SHORT"} and _direction(dominant_cluster.get("direction")) == direction:
        dominant_agreement_applied = True
        dominant_agreement_evidence = f"DOMINANT_CLUSTER_{dominant_cluster.get('cluster_id')}"
    elif _matches_family(family, dominant_model) and _direction(dominant_model.get("dominant_direction")) == direction:
        dominant_agreement_applied = True
        dominant_agreement_evidence = f"DOMINANT_MODEL_{dominant_model.get('dominant_direction')}"

    blocked_cluster_penalty = False
    blocked_cluster_evidence = "NO_BLOCKED_DOMINANT_CLUSTER"
    if blocked_dominant_cluster:
        allowed_score = _safe_float(dominant_cluster.get("cluster_score")) if dominant_cluster else 0.0
        blocked_score = _safe_float(blocked_dominant_cluster.get("cluster_score"))
        if not dominant_cluster or blocked_score >= allowed_score:
            blocked_cluster_penalty = True
            blocked_cluster_evidence = f"BLOCKED_CLUSTER_{blocked_dominant_cluster.get('cluster_id')}"

    score_breakdown = {
        "dominant_model_agreement": _component(
            dominant_agreement_applied,
            _POSITIVE_WEIGHTS["dominant_model_agreement"],
            dominant_agreement_evidence,
        ),
        "validated_semantic_agreement": _component(
            semantic_matched,
            _POSITIVE_WEIGHTS["validated_semantic_agreement"],
            semantic_evidence,
        ),
        "cooldown_allowed_cluster": _component(
            bool(family_allowed),
            _POSITIVE_WEIGHTS["cooldown_allowed_cluster"],
            f"ALLOWED_CLUSTERS_{len(family_allowed)}" if family_allowed else "NO_ALLOWED_CLUSTER",
        ),
        "matching_market_regime": _component(
            regime_matched,
            _POSITIVE_WEIGHTS["matching_market_regime"],
            regime_evidence,
        ),
        "matching_scenario_direction": _component(
            scenario_matched,
            _POSITIVE_WEIGHTS["matching_scenario_direction"],
            f"SCENARIO_{direction}" if scenario_matched else "SCENARIO_MISSING",
        ),
        "matching_candle_category": _component(
            candle_matched,
            _POSITIVE_WEIGHTS["matching_candle_category"],
            candle_evidence,
        ),
        "matching_interpretation_evidence": _component(
            interpretation_matched,
            _POSITIVE_WEIGHTS["matching_interpretation_evidence"],
            interpretation_evidence,
        ),
        "semantic_contradiction": _component(
            contradiction_applied,
            _NEGATIVE_WEIGHTS["semantic_contradiction"],
            contradiction_evidence,
        ),
        "cooldown_blocked_dominant_cluster": _component(
            blocked_cluster_penalty,
            _NEGATIVE_WEIGHTS["cooldown_blocked_dominant_cluster"],
            blocked_cluster_evidence,
        ),
        "missing_scenario": _component(
            direction in {"LONG", "SHORT"} and not scenario_matched,
            _NEGATIVE_WEIGHTS["missing_scenario"],
            f"SCENARIO_{direction}_MISSING" if direction in {"LONG", "SHORT"} else "SCENARIO_DIRECTION_UNRESOLVED",
        ),
        "missing_regime": _component(
            not regime_matched,
            _NEGATIVE_WEIGHTS["missing_regime"],
            regime_evidence if regime_evidence else "REGIME_MISSING",
        ),
    }

    raw_score = sum(item["value"] for item in score_breakdown.values())
    has_liquidity_evidence = bool(liquidity_map.get("near_liquidity") or []) or liquidity_event not in {"", "UNKNOWN"}
    has_model_cluster_evidence = bool(family_clusters_all or family_allowed_all)
    interpretation_missing_soft = not interpretation_matched
    if interpretation_missing_soft:
        risk_tags.append("INTERPRETATION_MISSING_SOFT_PENALTY")
    score_breakdown["missing_interpretation_soft_penalty"] = _component(
        interpretation_missing_soft,
        -0.10,
        "INTERPRETATION_MISSING_SOFT_PENALTY" if interpretation_missing_soft else "INTERPRETATION_PRESENT_OR_NOT_REQUIRED",
    )
    adjusted_raw_score = raw_score + score_breakdown["missing_interpretation_soft_penalty"]["value"]
    clamped_score = round(max(0.0, min(1.0, adjusted_raw_score)), 4)
    band = _activation_band(clamped_score)
    if band == "EARLY_RESEARCH":
        risk_tags.append("LOW_CONFIDENCE_RESEARCH")
    score_breakdown["raw_activation_score"] = round(raw_score, 4)
    score_breakdown["adjusted_total_before_clamp"] = round(adjusted_raw_score, 4)
    score_breakdown["total_before_clamp"] = round(adjusted_raw_score, 4)
    score_breakdown["clamped_score"] = clamped_score

    activation_reasons = [
        evidence["evidence"]
        for key, evidence in score_breakdown.items()
        if isinstance(evidence, dict) and evidence.get("applied") and evidence.get("value", 0.0) > 0.0
    ]
    blocking_reasons = [
        evidence["evidence"]
        for key, evidence in score_breakdown.items()
        if isinstance(evidence, dict) and evidence.get("applied") and evidence.get("value", 0.0) < 0.0
        and key != "missing_interpretation_soft_penalty"
    ]
    missing: list[str] = []
    if not family_models_all:
        missing.append("SOURCE_MODELS_MISSING")
    if not family_clusters_all:
        missing.append("SOURCE_CLUSTERS_MISSING")
    if not regime_matched:
        missing.append("MATCHING_REGIME_MISSING")
    if direction in {"LONG", "SHORT"} and not scenario_matched:
        missing.append("MATCHING_SCENARIO_DIRECTION_MISSING")
    if not candle_matched:
        missing.append("MATCHING_CANDLE_CATEGORY_MISSING")
    if not interpretation_matched:
        missing.append("MATCHING_INTERPRETATION_EVIDENCE_MISSING")
    if direction == "NEUTRAL":
        missing.append("DIRECTION_UNRESOLVED")

    hard_interpretation_block = interpretation_missing_soft and not has_liquidity_evidence and not has_model_cluster_evidence
    if hard_interpretation_block:
        blocking_reasons.append("INTERPRETATION_MISSING_HARD_NO_LIQUIDITY_OR_CLUSTER")
    hard_direction_conflict = direction_resolution.get("resolution_mode") == "NEUTRAL_HARD_CONFLICT"
    if hard_direction_conflict:
        blocking_reasons.append("DIRECTION_CONFLICT")

    active = band in {"STRONG_ACTIVE", "ACTIVE", "EARLY_RESEARCH"} and direction in {"LONG", "SHORT"}
    paper_ready = active and direction in {"LONG", "SHORT"}
    if hard_direction_conflict or hard_interpretation_block:
        paper_ready = False

    if band == "STRONG_ACTIVE":
        activation_reasons.append("ACTIVATION_STRONG")
    elif band == "ACTIVE":
        activation_reasons.append("ACTIVATION_ACTIVE")
    elif band == "EARLY_RESEARCH":
        activation_reasons.append("ACTIVATION_EARLY_RESEARCH")

    return {
        "family": family,
        "direction": direction,
        "activation_score": clamped_score,
        "raw_activation_score": round(raw_score, 4),
        "adjusted_activation_score": clamped_score,
        "activation_band": band,
        "active": active,
        "paper_ready": paper_ready,
        "source_models": [_compact_model(model) for model in family_models],
        "source_clusters": [_compact_cluster(cluster) for cluster in (family_allowed or family_clusters or family_blocked)],
        "activation_reasons": sorted(set(activation_reasons)),
        "blocking_reasons": sorted(set(blocking_reasons)),
        "missing": sorted(set(missing)),
        "risk_tags": sorted(set(risk_tags)),
        "score_breakdown": score_breakdown,
        "direction_sources": direction_resolution["direction_sources"],
        "direction_conflicts": direction_resolution["direction_conflicts"],
        "conflict_count": direction_resolution["conflict_count"],
        "direction_resolution": direction_resolution,
        "dominant_cluster_id": direction_resolution["dominant_cluster_id"],
        "liquidity_event": liquidity_event,
    }


def _collapse_family_overlap(active_assessments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], bool]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in active_assessments:
        key = (
            str(item.get("direction") or "NEUTRAL"),
            str(item.get("dominant_cluster_id") or ""),
            str(item.get("liquidity_event") or "UNKNOWN"),
        )
        grouped.setdefault(key, []).append(item)

    primary: list[dict[str, Any]] = []
    secondary: list[str] = []
    collapsed = False
    for key, items in grouped.items():
        if len(items) == 1 or not key[1]:
            primary.extend(items)
            continue
        ranked = sorted(items, key=lambda entry: _safe_float(entry.get("activation_score")), reverse=True)
        primary.append(ranked[0])
        secondary.extend(str(entry.get("family")) for entry in ranked[1:])
        collapsed = True
    primary.sort(key=lambda entry: _safe_float(entry.get("activation_score")), reverse=True)
    return primary, secondary, collapsed


def _sync_unified_context_overlay(output: dict[str, Any]) -> None:
    unified_context = _load_json(UNIFIED_CONTEXT_PATH)
    if not unified_context:
        return
    unified_context["active_setup_families"] = list(output.get("active_families") or [])
    unified_context["secondary_active_families"] = list(output.get("secondary_active_families") or [])
    unified_context["dominant_setup_family"] = output.get("dominant_setup_family", "NO_ACTIVE_SETUP_FAMILY")
    unified_context["activation_score"] = output.get("activation_score", 0.0)
    unified_context["activation_band"] = output.get("activation_band", "WATCH_ONLY")
    unified_context["raw_activation_score"] = output.get("raw_activation_score", 0.0)
    unified_context["adjusted_activation_score"] = output.get("adjusted_activation_score", 0.0)
    unified_context["setup_risk_tags"] = list(output.get("risk_tags") or [])
    unified_context["ready_for_paper_research"] = bool(output.get("ready_for_paper_research"))
    unified_context["setup_direction"] = output.get("direction", "NEUTRAL")
    unified_context["setup_blocking_reasons"] = list(output.get("blocking_reasons") or [])
    unified_context["score_breakdown"] = dict(output.get("score_breakdown") or {})
    unified_context["direction_resolution"] = dict(output.get("direction_resolution") or {})
    unified_context["missing"] = list(output.get("missing") or [])
    readiness = dict(unified_context.get("readiness") or {})
    readiness["context_ready_for_setup_selection"] = bool(output.get("ready_for_paper_research"))
    readiness["missing_before_setup"] = list(output.get("missing") or [])
    unified_context["readiness"] = readiness
    UNIFIED_CONTEXT_PATH.write_text(json.dumps(unified_context, ensure_ascii=False, indent=2), encoding="utf-8")


def run_setup_family_activation_engine() -> dict[str, Any]:
    semantic = _load_json(SEMANTIC_PATH) or {}
    clusters_payload = _load_json(CLUSTERS_PATH) or {}
    cooldown = _load_json(COOLDOWN_PATH) or {}
    dominant_model = _load_json(DOMINANT_MODEL_PATH) or {}
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
    semantic_states = _semantic_states(validated_models, dominant_model, unified_context)

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
    active_after_collapse, secondary_active_families, family_overlap_collapsed = _collapse_family_overlap(active_assessments)

    ranked_assessments = active_after_collapse or sorted(
        assessments,
        key=lambda item: _safe_float(item.get("activation_score")),
        reverse=True,
    )
    dominant = ranked_assessments[0] if ranked_assessments else None

    dominant_setup_family = "NO_ACTIVE_SETUP_FAMILY"
    direction = "NEUTRAL"
    activation_score = 0.0
    ready_for_paper_research = False
    source_models: list[dict[str, Any]] = []
    source_clusters: list[dict[str, Any]] = []
    activation_reasons: list[str] = []
    blocking_reasons: list[str] = []
    missing: list[str] = ["NO_ACTIVE_SETUP_FAMILY"]
    score_breakdown: dict[str, Any] = {
        "total_before_clamp": 0.0,
        "clamped_score": 0.0,
    }
    direction_sources = {
        "dominant_validated_cluster": "NEUTRAL",
        "dominant_model": "NEUTRAL",
        "liquidity_event_direction": "NEUTRAL",
        "scenario_direction": "NEUTRAL",
        "interpretation_direction": "NEUTRAL",
        "candle_category_direction": "NEUTRAL",
        "semantic_state_direction": "NEUTRAL",
    }
    direction_conflicts: list[dict[str, str]] = []
    conflict_count = 0
    direction_resolution: dict[str, Any] = {
        "resolved_direction": "NEUTRAL",
        "direction_sources": direction_sources,
        "direction_conflicts": direction_conflicts,
        "agreement_count": {"LONG": 0, "SHORT": 0},
        "conflict_count": 0,
        "resolution_mode": "NEUTRAL_HARD_CONFLICT",
    }
    raw_activation_score = 0.0
    adjusted_activation_score = 0.0
    activation_band = "WATCH_ONLY"
    risk_tags: list[str] = []

    if dominant:
        direction = str(dominant.get("direction") or "NEUTRAL")
        activation_score = _safe_float(dominant.get("activation_score"))
        raw_activation_score = _safe_float(dominant.get("raw_activation_score"))
        adjusted_activation_score = _safe_float(dominant.get("adjusted_activation_score"))
        activation_band = str(dominant.get("activation_band") or "WATCH_ONLY")
        source_models = list(dominant.get("source_models") or [])
        source_clusters = list(dominant.get("source_clusters") or [])
        activation_reasons = list(dominant.get("activation_reasons") or [])
        blocking_reasons = list(dominant.get("blocking_reasons") or [])
        missing = list(dominant.get("missing") or [])
        risk_tags = list(dominant.get("risk_tags") or [])
        score_breakdown = dict(dominant.get("score_breakdown") or score_breakdown)
        direction_sources = dict(dominant.get("direction_sources") or direction_sources)
        direction_conflicts = list(dominant.get("direction_conflicts") or [])
        conflict_count = int(dominant.get("conflict_count") or 0)
        direction_resolution = dict(dominant.get("direction_resolution") or direction_resolution)

        if dominant.get("active"):
            dominant_setup_family = str(dominant.get("family") or "NO_ACTIVE_SETUP_FAMILY")
        ready_for_paper_research = bool(dominant.get("paper_ready"))

    if not source_models and not source_clusters:
        dominant_setup_family = "NO_ACTIVE_SETUP_FAMILY"
        ready_for_paper_research = False
        activation_score = 0.0
        raw_activation_score = 0.0
        adjusted_activation_score = 0.0
        activation_band = "WATCH_ONLY"
        blocking_reasons = sorted(set([*blocking_reasons, "NO_EVIDENCE"]))
        missing = sorted(set([*missing, "NO_EVIDENCE"]))
        score_breakdown["total_before_clamp"] = 0.0
        score_breakdown["clamped_score"] = 0.0

    if dominant_setup_family == "NO_ACTIVE_SETUP_FAMILY":
        ready_for_paper_research = False
        if "NO_ACTIVE_SETUP_FAMILY" not in missing:
            missing.append("NO_ACTIVE_SETUP_FAMILY")

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(semantic.get("symbol") or clusters_payload.get("symbol") or cooldown.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "VALIDATED_CLUSTERED_SETUP_FAMILY_ACTIVATION",
        },
        "active_families": [item.get("family") for item in active_after_collapse],
        "secondary_active_families": secondary_active_families,
        "family_overlap_collapsed": family_overlap_collapsed,
        "dominant_setup_family": dominant_setup_family,
        "direction": direction,
        "activation_score": round(activation_score, 4),
        "raw_activation_score": round(raw_activation_score, 4),
        "adjusted_activation_score": round(adjusted_activation_score, 4),
        "activation_band": activation_band,
        "score_breakdown": score_breakdown,
        "ready_for_paper_research": ready_for_paper_research,
        "source_models": source_models,
        "source_clusters": source_clusters,
        "activation_reasons": sorted(set(activation_reasons)),
        "blocking_reasons": sorted(set(blocking_reasons)),
        "risk_tags": sorted(set(risk_tags)),
        "missing": sorted(set(missing)),
        "direction_sources": direction_sources,
        "direction_conflicts": direction_conflicts,
        "conflict_count": conflict_count,
        "direction_resolution": direction_resolution,
        "reason_codes": [
            f"ACTIVE_FAMILIES_{len(active_after_collapse)}",
            f"DOMINANT_SETUP_FAMILY_{dominant_setup_family}",
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
