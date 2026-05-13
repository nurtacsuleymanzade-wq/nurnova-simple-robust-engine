"""Semantic validation engine for dominant market narrative resolution."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "SEMANTIC_VALIDATION_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_semantic_validation.json"
HISTORY_PATH = DATA_DIR / "semantic_validation_history.jsonl"

INPUT_ALIASES: dict[str, list[str]] = {
    "observation": ["latest_observation.json", "latest_observation_factory.json"],
    "candle_dna": ["latest_candle_dna.json", "latest_mtf_candle_dna.json"],
    "structure": ["latest_structure.json", "latest_market_structure.json"],
    "liquidity_map": ["latest_liquidity_map.json"],
    "interpretation": ["latest_interpretation.json"],
    "scenarios": ["latest_scenarios.json", "latest_three_scenarios.json"],
    "business_zone": ["latest_business_zone.json"],
    "market_regime": ["latest_market_regime.json"],
    "intent_analysis": ["latest_intent_analysis.json"],
    "positioning_context": ["latest_positioning_context.json"],
    "unified_context": ["latest_unified_context.json"],
    "model_hunter": ["latest_model_hunter.json"],
}

SEMANTIC_STATE_PROBABILITIES: dict[str, tuple[float, float]] = {
    "BALANCED": (0.50, 0.50),
    "INITIATIVE_BUYING": (0.82, 0.18),
    "INITIATIVE_SELLING": (0.82, 0.18),
    "BUYER_EXHAUSTION": (0.22, 0.78),
    "SELLER_EXHAUSTION": (0.22, 0.78),
    "BUYER_TRAP": (0.15, 0.85),
    "SELLER_TRAP": (0.15, 0.85),
    "ABSORPTION": (0.58, 0.42),
    "COMPRESSION": (0.46, 0.54),
    "ROTATION": (0.48, 0.52),
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


def _load_state_bundle() -> tuple[dict[str, dict[str, Any]], dict[str, str], list[str]]:
    bundle: dict[str, dict[str, Any]] = {}
    resolved_paths: dict[str, str] = {}
    missing_inputs: list[str] = []
    for key, aliases in INPUT_ALIASES.items():
        payload = None
        resolved_name = None
        for alias in aliases:
            payload = _load_json(STATE_DIR / alias)
            if payload:
                resolved_name = alias
                break
        if payload is None:
            payload = {}
            missing_inputs.append(key)
        else:
            resolved_paths[key] = resolved_name or aliases[0]
        bundle[key] = payload
    return bundle, resolved_paths, missing_inputs


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_from_str(text: Any, truthy: str) -> bool:
    return str(text or "").upper() == truthy


def _quality_score(level: str) -> float:
    return {
        "HIGH": 1.0,
        "OK": 0.85,
        "REDUCED": 0.65,
        "LOW": 0.45,
        "MISSING": 0.25,
        "CRITICAL": 0.15,
        "INVALID": 0.0,
    }.get(str(level or "").upper(), 0.4)


def _structure_views(structure: dict[str, Any]) -> list[dict[str, Any]]:
    return [structure.get(tf) or {} for tf in ("1m", "5m", "15m", "1h")]


def _liquidity_flags(liquidity_map: dict[str, Any], current_price: float | None) -> dict[str, Any]:
    flags = {
        "liquidity_above_available": False,
        "liquidity_below_available": False,
        "liquidity_above_near": False,
        "liquidity_below_near": False,
        "liquidity_reference": "visible liquidity",
    }
    if current_price is None:
        return flags

    nearest_above = None
    nearest_below = None
    for level in liquidity_map.get("detected_levels") or []:
        price = _safe_float(level.get("price"))
        if price is None:
            continue
        bucket = str(level.get("bucket") or "")
        if price >= current_price:
            flags["liquidity_above_available"] = True
            if bucket == "NEAR":
                flags["liquidity_above_near"] = True
            if nearest_above is None or price < nearest_above:
                nearest_above = price
        if price <= current_price:
            flags["liquidity_below_available"] = True
            if bucket == "NEAR":
                flags["liquidity_below_near"] = True
            if nearest_below is None or price > nearest_below:
                nearest_below = price

    if flags["liquidity_above_near"]:
        flags["liquidity_reference"] = "near liquidity above"
    elif flags["liquidity_below_near"]:
        flags["liquidity_reference"] = "near liquidity below"
    elif flags["liquidity_above_available"]:
        flags["liquidity_reference"] = "liquidity above"
    elif flags["liquidity_below_available"]:
        flags["liquidity_reference"] = "liquidity below"

    return flags


def _count_condition_matches(models: list[dict[str, Any]], condition_id: str) -> int:
    return sum(1 for model in models if condition_id in (model.get("matched_conditions") or []))


def _derive_semantic_evidence(bundle: dict[str, dict[str, Any]]) -> dict[str, Any]:
    observation = bundle["observation"]
    dna = bundle["candle_dna"]
    structure = bundle["structure"]
    liquidity_map = bundle["liquidity_map"]
    interpretation = bundle["interpretation"]
    scenarios = bundle["scenarios"]
    business_zone = bundle["business_zone"]
    regime = bundle["market_regime"]
    intent_analysis = bundle["intent_analysis"]
    unified_context = bundle["unified_context"]
    detected_models = list((bundle["model_hunter"].get("detected_models") or []))

    market_snapshot = observation.get("market_snapshot") or {}
    war = observation.get("war_reading") or {}
    aggression = observation.get("aggression") or {}
    volume_flow = observation.get("volume_flow") or {}
    intent = intent_analysis.get("intent_analysis") or {}
    positioning = (bundle.get("positioning_context") or {}).get("positioning") or {}
    one_minute_dna = dna.get("1m") or {}
    one_minute_war = one_minute_dna.get("war_summary") or {}
    one_minute_volatility = one_minute_dna.get("volatility") or {}
    one_minute_interpretation = interpretation.get("1m") or {}
    value_area = business_zone.get("value_area") or {}
    auction = business_zone.get("auction_summary") or {}
    orderflow_context = unified_context.get("orderflow_context") or {}
    intent_context = unified_context.get("intent_context") or {}
    auction_context = unified_context.get("auction_context") or {}
    current_price = _safe_float(market_snapshot.get("price"))
    liquidity_flags = _liquidity_flags(liquidity_map, current_price)
    structures = _structure_views(structure)

    bullish_structure_count = sum(1 for view in structures if str(view.get("structure_label") or "").upper() in {"HH", "HL"})
    bearish_structure_count = sum(1 for view in structures if str(view.get("structure_label") or "").upper() in {"LH", "LL"})
    structure_expansion = any(
        bool(view.get("bos_detected")) or bool(view.get("choch_detected")) or bool(view.get("mss_detected"))
        for view in structures
    )
    no_structure_expansion = not structure_expansion

    bullish_trend_alignment = bullish_structure_count >= 2 or sum(
        1 for view in structures if str(view.get("trend_state") or "").upper() in {"UPTREND", "BULLISH"}
    ) >= 2
    bearish_trend_alignment = bearish_structure_count >= 2 or sum(
        1 for view in structures if str(view.get("trend_state") or "").upper() in {"DOWNTREND", "BEARISH"}
    ) >= 2

    buyers_attacking = _bool_from_str(war.get("who_attacked"), "BUYERS") or _bool_from_str(aggression.get("aggressor_side"), "BUYERS")
    sellers_attacking = _bool_from_str(war.get("who_attacked"), "SELLERS") or _bool_from_str(aggression.get("aggressor_side"), "SELLERS")
    buyers_defending = _bool_from_str(war.get("who_defended"), "BUYERS")
    sellers_defending = _bool_from_str(war.get("who_defended"), "SELLERS")

    delta = _safe_float(aggression.get("delta"))
    if delta is None:
        delta = _safe_float(volume_flow.get("delta"))
    if delta is None:
        delta = _safe_float(one_minute_dna.get("delta"))
    price_advanced = bool(war.get("price_advanced"))
    price_failed_to_advance = bool(war.get("price_failed_to_advance"))
    price_failed_to_decline = sellers_attacking and price_failed_to_advance and buyers_defending

    trapped_buyers = str(intent.get("trapped_side") or intent_context.get("trapped_side") or "").upper() == "BUYERS"
    trapped_sellers = str(intent.get("trapped_side") or intent_context.get("trapped_side") or "").upper() == "SELLERS"
    if not trapped_buyers:
        trapped_buyers = _count_condition_matches(detected_models, "COND_TRAPPED_BUYERS") > 0 or str(
            ((bundle.get("positioning_context") or {}).get("ltf_confirmation") or {}).get("trap_context") or ""
        ).upper() == "BUYERS_TRAPPED"
    if not trapped_sellers:
        trapped_sellers = _count_condition_matches(detected_models, "COND_TRAPPED_SELLERS") > 0 or str(
            ((bundle.get("positioning_context") or {}).get("ltf_confirmation") or {}).get("trap_context") or ""
        ).upper() == "SELLERS_TRAPPED"

    liquidity_event = str(one_minute_dna.get("liquidity_event") or one_minute_interpretation.get("raw_context", {}).get("liquidity_event") or "").upper()
    candle_category = str((one_minute_dna.get("candle_category") or {}).get("primary") or "").upper()
    liquidity_sweep_up = candle_category in {"LIQUIDITY_SWEEP_UP", "STOP_RUN_UP"} or _count_condition_matches(detected_models, "COND_LIQUIDITY_SWEEP_UP") > 0
    liquidity_sweep_down = candle_category in {"LIQUIDITY_SWEEP_DOWN", "STOP_RUN_DOWN"} or _count_condition_matches(detected_models, "COND_LIQUIDITY_SWEEP_DOWN") > 0
    liquidity_sweep = liquidity_sweep_up or liquidity_sweep_down or liquidity_event == "SWEEP"

    delta_divergence_bearish = (
        _count_condition_matches(detected_models, "COND_DELTA_PRICE_DIVERGENCE_BEARISH") > 0
        or (bool(orderflow_context.get("cvd_divergence")) and buyers_attacking and sellers_defending and price_failed_to_advance)
    )
    delta_divergence_bullish = (
        _count_condition_matches(detected_models, "COND_DELTA_PRICE_DIVERGENCE_BULLISH") > 0
        or (bool(orderflow_context.get("cvd_divergence")) and sellers_attacking and buyers_defending and price_failed_to_advance)
    )

    accepted_outside_value = bool(auction.get("acceptance")) and str(value_area.get("value_position") or "").upper() in {
        "ABOVE_VALUE",
        "BELOW_VALUE",
        "OUTSIDE_VALUE",
    }
    accepted_breakout = accepted_outside_value and structure_expansion
    inside_value = str(value_area.get("value_position") or "").upper() == "INSIDE_VALUE"

    regime_name = str(regime.get("regime") or "").upper()
    balance_mode = regime_name == "BALANCE_MODE"
    momentum_mode = regime_name == "MOMENTUM_MODE"
    atr_contracting = str(regime.get("evidence", {}).get("atr_expansion") or "").upper() == "CONTRACTING"

    passive_strength = _safe_float(intent.get("passive_strength"))
    aggressive_pressure = _safe_float(intent.get("aggressive_pressure"))
    absorption = bool((observation.get("micro_candidates") or {}).get("absorption_candidate"))
    if not absorption:
        absorption = (
            passive_strength is not None
            and aggressive_pressure is not None
            and passive_strength > aggressive_pressure
            and price_failed_to_advance
        )
    if not absorption:
        absorption = "ABSORPTION" in candle_category or _count_condition_matches(detected_models, "COND_ABSORPTION_INTENT") > 0

    initiative_buying = buyers_attacking and price_advanced and not price_failed_to_advance and (
        momentum_mode or bullish_trend_alignment or str(unified_context.get("dominant_context") or "").upper() == "MOMENTUM_CONTINUATION"
    )
    initiative_selling = sellers_attacking and not price_advanced and not price_failed_to_decline and (
        momentum_mode or bearish_trend_alignment or str(unified_context.get("dominant_context") or "").upper() == "MOMENTUM_CONTINUATION"
    )
    initiative_move = initiative_buying or initiative_selling

    both_defending = buyers_defending and sellers_defending
    if not both_defending:
        both_defending = balance_mode and liquidity_flags["liquidity_above_available"] and liquidity_flags["liquidity_below_available"] and not initiative_move

    no_accepted_breakout = not accepted_breakout
    no_accepted_outside_value = not accepted_outside_value
    compression = balance_mode and no_structure_expansion and atr_contracting and no_accepted_outside_value
    neutral_range_quality = str((scenarios.get("neutral_range_scenario") or {}).get("quality") or "").upper()
    if neutral_range_quality in {"HIGH", "MEDIUM"} and no_structure_expansion and no_accepted_outside_value:
        compression = True

    rotation_context = (
        balance_mode
        and inside_value
        and no_structure_expansion
        and not initiative_move
        and (buyers_attacking or sellers_attacking or delta_divergence_bearish or delta_divergence_bullish)
    )

    dominant_side = str(war.get("who_won") or orderflow_context.get("imbalance") or "UNKNOWN").upper()
    if dominant_side == "BUY":
        dominant_side = "BUYERS"
    if dominant_side == "SELL":
        dominant_side = "SELLERS"
    if dominant_side not in {"BUYERS", "SELLERS"}:
        dominant_side = "NEUTRAL"

    trend_alignment = False
    if dominant_side == "BUYERS":
        trend_alignment = bullish_trend_alignment
    elif dominant_side == "SELLERS":
        trend_alignment = bearish_trend_alignment

    return {
        "buyers_attacking": buyers_attacking,
        "sellers_attacking": sellers_attacking,
        "buyers_defending": buyers_defending,
        "sellers_defending": sellers_defending,
        "delta_divergence": delta_divergence_bearish or delta_divergence_bullish,
        "delta_divergence_bearish": delta_divergence_bearish,
        "delta_divergence_bullish": delta_divergence_bullish,
        "price_advanced": price_advanced,
        "price_failed_to_advance": price_failed_to_advance,
        "price_failed_to_decline": price_failed_to_decline,
        "trapped_buyers": trapped_buyers,
        "trapped_sellers": trapped_sellers,
        "accepted_outside_value": accepted_outside_value,
        "accepted_breakout": accepted_breakout,
        "liquidity_sweep": liquidity_sweep,
        "liquidity_sweep_up": liquidity_sweep_up,
        "liquidity_sweep_down": liquidity_sweep_down,
        "absorption": absorption,
        "trend_alignment": trend_alignment,
        "trend_alignment_buyers": bullish_trend_alignment,
        "trend_alignment_sellers": bearish_trend_alignment,
        "initiative_move": initiative_move,
        "initiative_buying": initiative_buying,
        "initiative_selling": initiative_selling,
        "liquidity_above_available": liquidity_flags["liquidity_above_available"],
        "liquidity_below_available": liquidity_flags["liquidity_below_available"],
        "both_sides_defending": both_defending,
        "no_structure_expansion": no_structure_expansion,
        "no_accepted_breakout": no_accepted_breakout,
        "balance_mode": balance_mode,
        "compression_context": compression,
        "rotation_context": rotation_context,
        "inside_value": inside_value,
        "dominant_side_hint": dominant_side,
        "liquidity_reference": liquidity_flags["liquidity_reference"],
        "candle_truth_1m": str(one_minute_war.get("candle_truth") or "UNKNOWN").upper(),
        "candle_category_1m": candle_category or "UNKNOWN",
        "atr_contracting": atr_contracting,
        "data_quality_bias": min(
            1.0,
            (
                _quality_score(str((observation.get("data_quality") or {}).get("level") or "LOW"))
                + _quality_score(str((dna.get("data_quality") or {}).get("level") or "LOW"))
                + _quality_score(str((structure.get("data_quality") or {}).get("level") or "LOW"))
                + _quality_score(str((regime.get("data_quality") or {}).get("level") or "LOW"))
            ) / 4.0,
        ),
        "positioning_squeeze_risk": str(positioning.get("squeeze_risk") or "UNKNOWN").upper(),
    }


def _state_direction(state_name: str, dominant_side: str) -> str:
    if state_name in {"INITIATIVE_BUYING", "SELLER_EXHAUSTION", "SELLER_TRAP"}:
        return "BUYERS"
    if state_name in {"INITIATIVE_SELLING", "BUYER_EXHAUSTION", "BUYER_TRAP"}:
        return "SELLERS"
    if state_name == "ABSORPTION":
        return dominant_side
    return "NEUTRAL"


def _rule_outcome(
    state_name: str,
    evidence: dict[str, Any],
    base_confidence: float,
    narrative: str,
    rule_trace: list[str],
) -> dict[str, Any]:
    continuation, reversal = SEMANTIC_STATE_PROBABILITIES[state_name]
    confirmations = 0
    if evidence.get("trapped_buyers") or evidence.get("trapped_sellers"):
        confirmations += 1
    if evidence.get("absorption"):
        confirmations += 1
    if evidence.get("trend_alignment"):
        confirmations += 1
    if evidence.get("liquidity_above_available") or evidence.get("liquidity_below_available"):
        confirmations += 1
    confidence = min(0.97, base_confidence + confirmations * 0.03)
    quality_adjustment = 0.85 + 0.15 * float(evidence.get("data_quality_bias") or 1.0)
    confidence = round(confidence * quality_adjustment, 4)
    return {
        "dominant_side": _state_direction(state_name, str(evidence.get("dominant_side_hint") or "NEUTRAL")),
        "market_state": state_name,
        "continuation_probability": round(continuation, 4),
        "reversal_probability": round(reversal, 4),
        "semantic_confidence": confidence,
        "narrative": narrative,
        "rule_trace": rule_trace,
    }


def _resolve_market_truth(evidence: dict[str, Any]) -> dict[str, Any]:
    liquidity_ref = str(evidence.get("liquidity_reference") or "visible liquidity")

    if evidence["buyers_attacking"] and evidence["liquidity_sweep_up"] and evidence["trapped_buyers"]:
        return _rule_outcome(
            "BUYER_TRAP",
            evidence,
            0.84,
            f"Buyers pushed into a sweep and then became trapped around {liquidity_ref}. This favors a short-side reversal narrative.",
            ["BUYERS_ATTACKING", "LIQUIDITY_SWEEP_UP", "TRAPPED_BUYERS"],
        )

    if evidence["sellers_attacking"] and evidence["liquidity_sweep_down"] and evidence["trapped_sellers"]:
        return _rule_outcome(
            "SELLER_TRAP",
            evidence,
            0.84,
            f"Sellers pushed into a sweep and then became trapped around {liquidity_ref}. This favors a long-side reversal narrative.",
            ["SELLERS_ATTACKING", "LIQUIDITY_SWEEP_DOWN", "TRAPPED_SELLERS"],
        )

    if evidence["buyers_attacking"] and evidence["price_failed_to_advance"] and evidence["sellers_defending"] and evidence["delta_divergence_bearish"]:
        return _rule_outcome(
            "BUYER_EXHAUSTION",
            evidence,
            0.82,
            f"Buyers attacked but failed to advance price while sellers defended around {liquidity_ref}. This suggests buyer exhaustion and possible downside rotation.",
            ["BUYERS_ATTACKING", "PRICE_FAILED_TO_ADVANCE", "SELLERS_DEFENDING", "DELTA_DIVERGENCE_BEARISH"],
        )

    if evidence["sellers_attacking"] and evidence["price_failed_to_advance"] and evidence["buyers_defending"] and evidence["delta_divergence_bullish"]:
        return _rule_outcome(
            "SELLER_EXHAUSTION",
            evidence,
            0.82,
            f"Sellers attacked but failed to press price lower while buyers defended around {liquidity_ref}. This suggests seller exhaustion and possible upside rotation.",
            ["SELLERS_ATTACKING", "PRICE_FAILED_TO_ADVANCE", "BUYERS_DEFENDING", "DELTA_DIVERGENCE_BULLISH"],
        )

    if evidence["initiative_buying"] and evidence["accepted_outside_value"] and evidence["trend_alignment_buyers"] and evidence["liquidity_above_available"]:
        return _rule_outcome(
            "INITIATIVE_BUYING",
            evidence,
            0.83,
            "Buyers are lifting offers, price is accepted outside value, and structure is aligned higher. This supports bullish initiative continuation.",
            ["INITIATIVE_BUYING", "ACCEPTED_OUTSIDE_VALUE", "TREND_ALIGNMENT_BUYERS", "LIQUIDITY_ABOVE_AVAILABLE"],
        )

    if evidence["initiative_selling"] and evidence["accepted_outside_value"] and evidence["trend_alignment_sellers"] and evidence["liquidity_below_available"]:
        return _rule_outcome(
            "INITIATIVE_SELLING",
            evidence,
            0.83,
            "Sellers are pressing bids, price is accepted outside value, and structure is aligned lower. This supports bearish initiative continuation.",
            ["INITIATIVE_SELLING", "ACCEPTED_OUTSIDE_VALUE", "TREND_ALIGNMENT_SELLERS", "LIQUIDITY_BELOW_AVAILABLE"],
        )

    if evidence["absorption"] and (
        (evidence["buyers_attacking"] and evidence["sellers_defending"])
        or (evidence["sellers_attacking"] and evidence["buyers_defending"])
    ):
        return _rule_outcome(
            "ABSORPTION",
            evidence,
            0.74,
            f"Aggression is being absorbed near {liquidity_ref} rather than cleanly extending. The market is still deciding whether that absorption becomes continuation or reversal.",
            ["ABSORPTION", "ATTACK_DEFENSE_OVERLAP"],
        )

    if evidence["compression_context"]:
        return _rule_outcome(
            "COMPRESSION",
            evidence,
            0.72,
            "Both sides remain contained, volatility is contracting, and no accepted breakout is present. This is a compression regime until expansion resolves it.",
            ["BALANCE_MODE", "NO_STRUCTURE_EXPANSION", "NO_ACCEPTED_OUTSIDE_VALUE", "ATR_CONTRACTING"],
        )

    if evidence["both_sides_defending"] and evidence["no_structure_expansion"] and evidence["no_accepted_breakout"] and evidence["balance_mode"]:
        return _rule_outcome(
            "BALANCED",
            evidence,
            0.76,
            "Both sides are defending, structure is not expanding, and the auction remains in balance. No dominant initiative has been validated yet.",
            ["BOTH_SIDES_DEFENDING", "NO_STRUCTURE_EXPANSION", "NO_ACCEPTED_BREAKOUT", "BALANCE_MODE"],
        )

    if evidence["rotation_context"]:
        state_evidence = dict(evidence)
        state_evidence["dominant_side_hint"] = "SELLERS" if evidence["buyers_attacking"] else "BUYERS" if evidence["sellers_attacking"] else "NEUTRAL"
        return _rule_outcome(
            "ROTATION",
            state_evidence,
            0.68,
            "The market remains inside value, but one-sided effort is rotating across the auction instead of establishing true initiative. This is rotational trade rather than clean trend expansion.",
            ["INSIDE_VALUE", "BALANCE_MODE", "ROTATION_CONTEXT"],
        )

    fallback = dict(evidence)
    fallback["dominant_side_hint"] = "NEUTRAL"
    return _rule_outcome(
        "BALANCED",
        fallback,
        0.52,
        "The current inputs do not validate a dominant initiative or a clean trap. Market structure remains unresolved, so the semantic read stays balanced.",
        ["FALLBACK_BALANCED"],
    )


def _semantic_quality(truth: dict[str, Any], missing_inputs: list[str], evidence: dict[str, Any]) -> str:
    confidence = float(truth.get("semantic_confidence") or 0.0)
    if len(missing_inputs) >= 5:
        return "INVALID"
    if confidence >= 0.88 and truth.get("market_state") not in {"BALANCED"}:
        return "VERY_HIGH"
    if confidence >= 0.74:
        return "HIGH"
    if confidence >= 0.56:
        return "MEDIUM"
    if confidence >= 0.35:
        return "LOW"
    if evidence.get("balance_mode") and truth.get("market_state") == "BALANCED":
        return "MEDIUM"
    return "INVALID"


def run_semantic_validation_engine() -> dict[str, Any]:
    bundle, resolved_paths, missing_inputs = _load_state_bundle()
    evidence = _derive_semantic_evidence(bundle)
    truth = _resolve_market_truth(evidence)
    quality = _semantic_quality(truth, missing_inputs, evidence)

    observation = bundle["observation"]
    symbol = str(observation.get("symbol") or bundle["model_hunter"].get("symbol") or "BTCUSDT")
    timestamp = _utc_now()

    output = {
        "timestamp_utc": timestamp,
        "symbol": symbol,
        "block_id": BLOCK_ID,
        "market_semantic_truth": {
            "dominant_side": truth["dominant_side"],
            "market_state": truth["market_state"],
            "continuation_probability": truth["continuation_probability"],
            "reversal_probability": truth["reversal_probability"],
            "semantic_confidence": truth["semantic_confidence"],
            "narrative": truth["narrative"],
        },
        "semantic_evidence": {
            "buyers_attacking": evidence["buyers_attacking"],
            "sellers_defending": evidence["sellers_defending"],
            "delta_divergence": evidence["delta_divergence"],
            "price_failed_to_advance": evidence["price_failed_to_advance"],
            "trapped_buyers": evidence["trapped_buyers"],
            "accepted_outside_value": evidence["accepted_outside_value"],
            "liquidity_sweep": evidence["liquidity_sweep"],
            "absorption": evidence["absorption"],
            "trend_alignment": evidence["trend_alignment"],
            "initiative_move": evidence["initiative_move"],
            "sellers_attacking": evidence["sellers_attacking"],
            "buyers_defending": evidence["buyers_defending"],
            "trapped_sellers": evidence["trapped_sellers"],
            "liquidity_sweep_up": evidence["liquidity_sweep_up"],
            "liquidity_sweep_down": evidence["liquidity_sweep_down"],
            "liquidity_above_available": evidence["liquidity_above_available"],
            "liquidity_below_available": evidence["liquidity_below_available"],
            "both_sides_defending": evidence["both_sides_defending"],
            "no_structure_expansion": evidence["no_structure_expansion"],
            "no_accepted_breakout": evidence["no_accepted_breakout"],
            "balance_mode": evidence["balance_mode"],
            "compression_context": evidence["compression_context"],
            "rotation_context": evidence["rotation_context"],
            "candle_truth_1m": evidence["candle_truth_1m"],
            "candle_category_1m": evidence["candle_category_1m"],
        },
        "semantic_quality": quality,
        "semantic_rule_trace": truth.get("rule_trace") or [],
        "source": {
            "source_mode": "STATE_SEMANTIC_HIERARCHY",
            "resolved_inputs": resolved_paths,
        },
        "data_quality": {
            "level": "HIGH" if not missing_inputs else "REDUCED" if len(missing_inputs) <= 3 else "LOW",
            "missing_inputs": missing_inputs,
        },
        "reason_codes": [
            f"STATE_{truth['market_state']}",
            f"DOMINANT_{truth['dominant_side']}",
            f"SEMANTIC_QUALITY_{quality}",
            "NO_RANDOM_SCORING",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "DOMINANT_MODEL_ENGINE",
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
    print(json.dumps(run_semantic_validation_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
