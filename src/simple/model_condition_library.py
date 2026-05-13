"""Executable condition library for research model taxonomy."""

from __future__ import annotations

import json
from typing import Any, Callable


def _get(payload: Any, *path: str) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _contains_code(payload: dict[str, Any] | None, needle: str) -> bool:
    if not isinstance(payload, dict):
        return False
    values = payload.get("reason_codes") or []
    return any(needle in str(item).upper() for item in values)


def _result(
    condition_id: str,
    matched: bool | None,
    evidence: list[str] | None = None,
    reason_codes: list[str] | None = None,
    source: str = "state_bundle",
) -> dict[str, Any]:
    if matched is True:
        status = "MATCHED"
    elif matched is False:
        status = "NOT_MATCHED"
    elif matched is None and reason_codes and any("MISSING" in code or "UNAVAILABLE" in code for code in reason_codes):
        status = "MISSING"
    else:
        status = "UNKNOWN"
    return {
        "condition_id": condition_id,
        "matched": matched,
        "status": status,
        "evidence": evidence or [],
        "reason_codes": reason_codes or [],
        "source": source,
    }


def _missing(condition_id: str, source: str, reason: str) -> dict[str, Any]:
    return _result(condition_id, None, [], [reason], source)


def _observation(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("observation") or {}


def _dna(state: dict[str, Any], tf: str = "1m") -> dict[str, Any]:
    return ((state.get("dna") or {}).get(tf)) or {}


def _structure(state: dict[str, Any], tf: str = "1m") -> dict[str, Any]:
    return ((state.get("structure") or {}).get(tf)) or {}


def _interpretation_1m(state: dict[str, Any]) -> dict[str, Any]:
    return ((state.get("interpretation") or {}).get("1m")) or {}


def _liquidity(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("liquidity") or {}


def _business_zone(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("business_zone") or {}


def _regime(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("regime") or {}


def _intent(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("intent") or {}


def _scenarios(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("scenarios") or {}


def _atr(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("atr") or {}


def _current_price(state: dict[str, Any]) -> float | None:
    price = _safe_float(_get(_observation(state), "market_snapshot", "price"))
    if price is not None:
        return price
    return _safe_float(_liquidity(state).get("current_price"))


def _detected_levels(state: dict[str, Any], buckets: tuple[str, ...] = ("near_liquidity", "mid_liquidity")) -> list[dict[str, Any]]:
    liquidity = _liquidity(state)
    levels: list[dict[str, Any]] = []
    for bucket in buckets:
        levels.extend(list(liquidity.get(bucket) or []))
    return levels


def _has_level_above(state: dict[str, Any], buckets: tuple[str, ...] = ("near_liquidity", "mid_liquidity"), ltype: str | None = None) -> bool | None:
    current_price = _current_price(state)
    if current_price is None:
        return None
    levels = _detected_levels(state, buckets)
    if not levels:
        return False
    for level in levels:
        price = _safe_float(level.get("price"))
        if price is None or price <= current_price:
            continue
        if ltype is None or str(level.get("liquidity_type", "")).lower() == ltype.lower():
            return True
    return False


def _has_level_below(state: dict[str, Any], buckets: tuple[str, ...] = ("near_liquidity", "mid_liquidity"), ltype: str | None = None) -> bool | None:
    current_price = _current_price(state)
    if current_price is None:
        return None
    levels = _detected_levels(state, buckets)
    if not levels:
        return False
    for level in levels:
        price = _safe_float(level.get("price"))
        if price is None or price >= current_price:
            continue
        if ltype is None or str(level.get("liquidity_type", "")).lower() == ltype.lower():
            return True
    return False


def _candle_category(state: dict[str, Any], tf: str = "1m") -> str:
    return str(_get(_dna(state, tf), "candle_category", "primary") or "UNKNOWN")


def _war_summary(state: dict[str, Any], tf: str = "1m") -> dict[str, Any]:
    return _get(_dna(state, tf), "war_summary") or {}


def _cvd_state(state: dict[str, Any]) -> str:
    return str(_get(_interpretation_1m(state), "raw_context", "cvd_state") or "UNKNOWN")


def _structure_label_or_trend(state: dict[str, Any], tf: str) -> tuple[str, str]:
    payload = _structure(state, tf)
    return str(payload.get("structure_label", "UNKNOWN")), str(payload.get("trend_state", "UNKNOWN"))


def _bool_result(condition_id: str, result: dict[str, Any]) -> bool:
    return result.get("matched") is True or result.get("status") == "MATCHED"


def _string_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = str(value or "").upper()
        if not text:
            continue
        tokens.add(text)
        tokens.update(part for part in text.replace("-", "_").split("_") if part)
    return tokens


def _structure_bias_from_label(label: str) -> str:
    tokens = _string_tokens(label)
    if {"EQH", "EQL", "RANGE"} & tokens:
        return "RANGE"
    if "BOS" in tokens:
        if "BULLISH" in tokens or "UP" in tokens:
            return "BULLISH"
        if "BEARISH" in tokens or "DOWN" in tokens:
            return "BEARISH"
    if "HH" in tokens or "HL" in tokens:
        return "BULLISH"
    if "LH" in tokens or "LL" in tokens:
        return "BEARISH"
    return "UNKNOWN"


def _logic_flow_attack(state: dict[str, Any], side: str) -> dict[str, Any]:
    cond = f"COND_{side}_ATTACKING"
    observation = _observation(state)
    dna = _dna(state, "1m")
    war_side = str(_get(observation, "war_reading", "who_attacked") or "UNKNOWN")
    dominant = str(_get(dna, "war_summary", "dominant_side") or "UNKNOWN")
    delta = _safe_float(_get(observation, "volume_flow", "delta"))
    evidence = ["source_priority=war_reading>volume_flow.delta>dna.1m.war_summary.dominant_side"]
    reason_codes: list[str] = []
    delta_side = "BUYERS" if delta is not None and delta > 0 else "SELLERS" if delta is not None and delta < 0 else "NEUTRAL"
    strongest_side = "UNKNOWN"
    strongest_source = "dna.1m.war_summary.dominant_side"

    if war_side not in ("UNKNOWN", "NONE", "NEUTRAL", "BALANCED"):
        strongest_side = war_side
        strongest_source = "war_reading.who_attacked"
    elif delta_side in ("BUYERS", "SELLERS"):
        strongest_side = delta_side
        strongest_source = "observation.volume_flow.delta"
    elif dominant not in ("UNKNOWN", "NONE", "NEUTRAL", "BALANCED"):
        strongest_side = dominant

    strongest_value = war_side if strongest_source == "war_reading.who_attacked" else delta if strongest_source == "observation.volume_flow.delta" else dominant
    evidence.append(f"{strongest_source}={strongest_value}")
    evidence.append(f"observation.volume_flow.delta={delta}")
    evidence.append(f"dna.1m.war_summary.dominant_side={dominant}")

    aligned_sides = {candidate for candidate in (war_side, delta_side, dominant) if candidate in ("BUYERS", "SELLERS")}
    if strongest_side in ("BUYERS", "SELLERS") and any(candidate != strongest_side for candidate in aligned_sides):
        reason_codes.append("SOURCE_CONFLICT")

    return _result(cond, strongest_side == side, evidence, reason_codes, "observation/dna")


def _logic_flow_defend(state: dict[str, Any], side: str) -> dict[str, Any]:
    cond = f"COND_{side}_DEFENDING"
    war_side = str(_get(_observation(state), "war_reading", "who_defended") or "UNKNOWN")
    cvd = _cvd_state(state)
    cvd_expected = "SELL_PRESSURE_ABSORBED" if side == "BUYERS" else "BUY_PRESSURE_ABSORBED"
    matched = war_side == side or cvd == cvd_expected
    evidence: list[str] = []
    if war_side == side:
        evidence.append(f"war_reading.who_defended={side}")
    if cvd == cvd_expected:
        evidence.append(f"interpretation.1m.cvd_state={cvd_expected}")
    return _result(cond, matched, evidence, [], "observation/interpretation")


def cond_buyers_attacking(state: dict[str, Any]) -> dict[str, Any]:
    return _logic_flow_attack(state, "BUYERS")


def cond_sellers_attacking(state: dict[str, Any]) -> dict[str, Any]:
    return _logic_flow_attack(state, "SELLERS")


def cond_buyers_defending(state: dict[str, Any]) -> dict[str, Any]:
    return _logic_flow_defend(state, "BUYERS")


def cond_sellers_defending(state: dict[str, Any]) -> dict[str, Any]:
    return _logic_flow_defend(state, "SELLERS")


def cond_price_failed_to_advance(state: dict[str, Any]) -> dict[str, Any]:
    value = _get(_observation(state), "war_reading", "price_failed_to_advance")
    if value is None:
        return _missing("COND_PRICE_FAILED_TO_ADVANCE", "observation", "WAR_READING_MISSING")
    return _result("COND_PRICE_FAILED_TO_ADVANCE", bool(value), [f"price_failed_to_advance={value}"], [], "observation")


def _delta_condition(state: dict[str, Any], positive: bool) -> dict[str, Any]:
    cond = "COND_POSITIVE_DELTA" if positive else "COND_NEGATIVE_DELTA"
    obs_delta = _safe_float(_get(_observation(state), "volume_flow", "delta"))
    dna_delta = _safe_float(_dna(state, "1m").get("delta"))
    if obs_delta is None and dna_delta is None:
        return _missing(cond, "observation/dna", "DELTA_NOT_AVAILABLE")
    reason_codes: list[str] = []
    evidence = [f"observation.volume_flow.delta={obs_delta}", f"dna.1m.delta={dna_delta}"]
    if positive:
        if obs_delta is not None:
            matched = obs_delta > 0
            evidence.append("source=observation.volume_flow.delta")
            if obs_delta < 0 and dna_delta is not None and dna_delta > 0:
                reason_codes.append("CURRENT_OBSERVATION_NEGATIVE")
            elif obs_delta > 0 and dna_delta is not None and dna_delta < 0:
                reason_codes.append("SOURCE_CONFLICT")
            return _result(cond, matched, evidence, reason_codes, "observation/dna")
        evidence.append("source=dna.1m.delta")
        return _result(cond, dna_delta is not None and dna_delta > 0, evidence, reason_codes, "observation/dna")

    if obs_delta is not None:
        matched = obs_delta < 0
        evidence.append("source=observation.volume_flow.delta")
        if obs_delta > 0 and dna_delta is not None and dna_delta < 0:
            reason_codes.append("CURRENT_OBSERVATION_POSITIVE")
        elif obs_delta < 0 and dna_delta is not None and dna_delta > 0:
            reason_codes.append("SOURCE_CONFLICT")
        return _result(cond, matched, evidence, reason_codes, "observation/dna")
    evidence.append("source=dna.1m.delta")
    return _result(cond, dna_delta is not None and dna_delta < 0, evidence, reason_codes, "observation/dna")


def cond_positive_delta(state: dict[str, Any]) -> dict[str, Any]:
    return _delta_condition(state, True)


def cond_negative_delta(state: dict[str, Any]) -> dict[str, Any]:
    return _delta_condition(state, False)


def _divergence(state: dict[str, Any], bullish: bool) -> dict[str, Any]:
    cond = "COND_DELTA_PRICE_DIVERGENCE_BULLISH" if bullish else "COND_DELTA_PRICE_DIVERGENCE_BEARISH"
    obs_delta = _safe_float(_get(_observation(state), "volume_flow", "delta"))
    candle_truth = str(_get(_dna(state, "1m"), "war_summary", "candle_truth") or "UNKNOWN")
    defended = evaluate_condition("COND_BUYERS_DEFENDING" if bullish else "COND_SELLERS_DEFENDING", state)
    failed_up = bool(_get(_observation(state), "war_reading", "price_failed_to_advance"))
    fake_condition = evaluate_condition("COND_FAKE_BEARISH" if bullish else "COND_FAKE_BULLISH", state)
    real_condition = evaluate_condition("COND_REAL_BEARISH" if bullish else "COND_REAL_BULLISH", state)
    if obs_delta is None and candle_truth == "UNKNOWN":
        return _missing(cond, "observation/dna", "DELTA_AND_CANDLE_TRUTH_MISSING")
    evidence = [
        f"observation.volume_flow.delta={obs_delta}",
        f"candle_truth={candle_truth}",
        f"defense={defended['status']}",
        f"fake_signal={fake_condition['status']}",
        f"price_failed_to_advance={failed_up}",
    ]
    if _bool_result(cond, real_condition):
        contradiction = "REAL_BEARISH_CONTINUATION_PRESENT" if bullish else "REAL_BULLISH_CONTINUATION_PRESENT"
        return _result(cond, False, evidence, [contradiction], "observation/dna/interpretation")
    if bullish:
        matched = (
            obs_delta is not None
            and obs_delta < 0
            and (_bool_result(cond, defended) or _bool_result(cond, fake_condition))
            and candle_truth not in ("REAL_BEARISH", "WEAK_BEARISH")
        )
    else:
        matched = (
            obs_delta is not None
            and obs_delta > 0
            and (failed_up or _bool_result(cond, defended) or _bool_result(cond, fake_condition))
            and (_bool_result(cond, defended) or _bool_result(cond, fake_condition))
            and candle_truth not in ("REAL_BULLISH", "WEAK_BULLISH")
        )
    return _result(cond, matched, evidence, [], "observation/dna/interpretation")


def cond_delta_price_divergence_bullish(state: dict[str, Any]) -> dict[str, Any]:
    return _divergence(state, True)


def cond_delta_price_divergence_bearish(state: dict[str, Any]) -> dict[str, Any]:
    return _divergence(state, False)


def cond_trap_candle(state: dict[str, Any]) -> dict[str, Any]:
    categories = [_candle_category(state, "1m"), _candle_category(state, "5m")]
    matched = any(category == "TRAP_CANDLE" for category in categories)
    return _result("COND_TRAP_CANDLE", matched, [f"categories={categories}"], [], "dna")


def _imbalance_condition(state: dict[str, Any], buy_side: bool) -> dict[str, Any]:
    cond = "COND_BUY_IMBALANCE" if buy_side else "COND_SELL_IMBALANCE"
    category = _candle_category(state, "1m")
    delta = _safe_float(_dna(state, "1m").get("delta"))
    buy_volume = _safe_float(_dna(state, "1m").get("buy_volume"))
    sell_volume = _safe_float(_dna(state, "1m").get("sell_volume"))
    matched = False
    if buy_side:
        matched = category == "BUY_IMBALANCE" or (delta is not None and delta > 0 and buy_volume is not None and sell_volume is not None and buy_volume > sell_volume)
    else:
        matched = category == "SELL_IMBALANCE" or (delta is not None and delta < 0 and buy_volume is not None and sell_volume is not None and sell_volume > buy_volume)
    return _result(cond, matched, [f"category={category}", f"delta={delta}", f"buy={buy_volume}", f"sell={sell_volume}"], [], "dna")


def cond_buy_imbalance(state: dict[str, Any]) -> dict[str, Any]:
    return _imbalance_condition(state, True)


def cond_sell_imbalance(state: dict[str, Any]) -> dict[str, Any]:
    return _imbalance_condition(state, False)


def _sweep_condition(state: dict[str, Any], down: bool) -> dict[str, Any]:
    cond = "COND_LIQUIDITY_SWEEP_DOWN" if down else "COND_LIQUIDITY_SWEEP_UP"
    category = _candle_category(state, "1m")
    event = str(_dna(state, "1m").get("liquidity_event") or "UNKNOWN")
    matching_categories = {"LIQUIDITY_SWEEP_DOWN", "STOP_RUN_DOWN"} if down else {"LIQUIDITY_SWEEP_UP", "STOP_RUN_UP"}
    matched = category in matching_categories or event == "SWEEP"
    evidence = [f"category={category}", f"liquidity_event={event}"]
    return _result(cond, matched, evidence, [], "dna/liquidity")


def cond_liquidity_sweep_down(state: dict[str, Any]) -> dict[str, Any]:
    return _sweep_condition(state, True)


def cond_liquidity_sweep_up(state: dict[str, Any]) -> dict[str, Any]:
    return _sweep_condition(state, False)


def _fake_real_bull_bear(state: dict[str, Any], fake: bool, bullish: bool) -> dict[str, Any]:
    name = (
        "COND_FAKE_BULLISH" if fake and bullish else
        "COND_FAKE_BEARISH" if fake and not bullish else
        "COND_REAL_BULLISH" if bullish else
        "COND_REAL_BEARISH"
    )
    candle_truth = str(_get(_dna(state, "1m"), "war_summary", "candle_truth") or "UNKNOWN")
    category = _candle_category(state, "1m")
    trapped_buyers = _bool_result("COND_TRAPPED_BUYERS", evaluate_condition("COND_TRAPPED_BUYERS", state))
    trapped_sellers = _bool_result("COND_TRAPPED_SELLERS", evaluate_condition("COND_TRAPPED_SELLERS", state))
    positive_delta = _bool_result("COND_POSITIVE_DELTA", evaluate_condition("COND_POSITIVE_DELTA", state))
    negative_delta = _bool_result("COND_NEGATIVE_DELTA", evaluate_condition("COND_NEGATIVE_DELTA", state))
    buyers_attacking = _bool_result("COND_BUYERS_ATTACKING", evaluate_condition("COND_BUYERS_ATTACKING", state))
    sellers_attacking = _bool_result("COND_SELLERS_ATTACKING", evaluate_condition("COND_SELLERS_ATTACKING", state))
    buyers_defending = _bool_result("COND_BUYERS_DEFENDING", evaluate_condition("COND_BUYERS_DEFENDING", state))
    sellers_defending = _bool_result("COND_SELLERS_DEFENDING", evaluate_condition("COND_SELLERS_DEFENDING", state))
    structure_bullish = _bool_result("COND_STRUCTURE_BULLISH", evaluate_condition("COND_STRUCTURE_BULLISH", state))
    structure_bearish = _bool_result("COND_STRUCTURE_BEARISH", evaluate_condition("COND_STRUCTURE_BEARISH", state))
    failed_up = bool(_get(_observation(state), "war_reading", "price_failed_to_advance"))
    evidence = [f"candle_truth={candle_truth}", f"category={category}", f"price_failed_to_advance={failed_up}"]
    reason_codes: list[str] = []

    if not fake and bullish and candle_truth == "REAL_BEARISH":
        return _result(name, False, evidence, ["REAL_BEARISH_CONTRADICTS_REAL_BULLISH"], "dna/intent")
    if not fake and not bullish and candle_truth == "REAL_BULLISH":
        return _result(name, False, evidence, ["REAL_BULLISH_CONTRADICTS_REAL_BEARISH"], "dna/intent")

    if fake and bullish:
        matched = (
            candle_truth == "FAKE_BULLISH"
            or (category == "TRAP_CANDLE" and buyers_attacking and (trapped_buyers or sellers_defending or failed_up))
            or (positive_delta and failed_up and sellers_defending)
        )
        if candle_truth == "REAL_BEARISH":
            matched = False
            reason_codes.append("REAL_BEARISH_CONTRADICTS_FAKE_BULLISH")
    elif fake and not bullish:
        matched = (
            candle_truth == "FAKE_BEARISH"
            or (category == "TRAP_CANDLE" and sellers_attacking and (trapped_sellers or buyers_defending))
            or (negative_delta and (buyers_defending or trapped_sellers))
        )
        if candle_truth == "REAL_BULLISH":
            matched = False
            reason_codes.append("REAL_BULLISH_CONTRADICTS_FAKE_BEARISH")
    elif bullish:
        strong_continuation = (
            candle_truth not in ("FAKE_BULLISH", "REAL_BEARISH")
            and positive_delta
            and buyers_attacking
            and structure_bullish
            and not failed_up
        )
        matched = candle_truth == "REAL_BULLISH" or strong_continuation
        if not matched:
            reason_codes.append("REAL_BULLISH_EVIDENCE_NOT_PRESENT")
    else:
        strong_continuation = (
            candle_truth not in ("FAKE_BEARISH", "REAL_BULLISH")
            and negative_delta
            and sellers_attacking
            and structure_bearish
            and (failed_up or not buyers_defending)
        )
        matched = candle_truth == "REAL_BEARISH" or strong_continuation
        if not matched:
            reason_codes.append("REAL_BEARISH_EVIDENCE_NOT_PRESENT")

    if fake and matched and category == "TRAP_CANDLE":
        evidence.append("trap_failure_confirmed=True")
    if not fake and matched and candle_truth not in ("REAL_BULLISH", "REAL_BEARISH"):
        evidence.append("continuation_evidence=STRONG")
    evidence.extend([
        f"buyers_attacking={buyers_attacking}",
        f"sellers_attacking={sellers_attacking}",
        f"buyers_defending={buyers_defending}",
        f"sellers_defending={sellers_defending}",
        f"positive_delta={positive_delta}",
        f"negative_delta={negative_delta}",
        f"trapped_buyers={trapped_buyers}",
        f"trapped_sellers={trapped_sellers}",
        f"structure_bullish={structure_bullish}",
        f"structure_bearish={structure_bearish}",
    ])
    return _result(name, matched, evidence, reason_codes, "dna/intent")


def cond_fake_bullish(state: dict[str, Any]) -> dict[str, Any]:
    return _fake_real_bull_bear(state, True, True)


def cond_fake_bearish(state: dict[str, Any]) -> dict[str, Any]:
    return _fake_real_bull_bear(state, True, False)


def cond_real_bullish(state: dict[str, Any]) -> dict[str, Any]:
    return _fake_real_bull_bear(state, False, True)


def cond_real_bearish(state: dict[str, Any]) -> dict[str, Any]:
    return _fake_real_bull_bear(state, False, False)


def _structure_condition(state: dict[str, Any], bullish: bool) -> dict[str, Any]:
    cond = "COND_STRUCTURE_BULLISH" if bullish else "COND_STRUCTURE_BEARISH"
    labels = []
    trends = []
    biases = []
    reason_codes: list[str] = []
    for tf in ("1m", "5m"):
        label, trend = _structure_label_or_trend(state, tf)
        labels.append(str(label).upper())
        trends.append(str(trend).upper())
        biases.append(_structure_bias_from_label(label))
    range_labels = {"EQH", "EQL", "RANGE"}
    explicit_trend = "UPTREND" if bullish else "DOWNTREND"
    explicit_bias = "BULLISH" if bullish else "BEARISH"
    matched = any(bias == explicit_bias for bias in biases) or any(trend == explicit_trend for trend in trends)
    if not matched and any(label in range_labels for label in labels):
        reason_codes.append("RANGE_NOT_BULLISH_STRUCTURE" if bullish else "RANGE_NOT_BEARISH_STRUCTURE")
    return _result(cond, matched, [f"labels={labels}", f"trends={trends}", f"biases={biases}"], reason_codes, "structure")


def cond_structure_bullish(state: dict[str, Any]) -> dict[str, Any]:
    return _structure_condition(state, True)


def cond_structure_bearish(state: dict[str, Any]) -> dict[str, Any]:
    return _structure_condition(state, False)


def cond_structure_range(state: dict[str, Any]) -> dict[str, Any]:
    labels = []
    trends = []
    for tf in ("1m", "5m"):
        label, trend = _structure_label_or_trend(state, tf)
        labels.append(label)
        trends.append(trend)
    matched = any(trend == "RANGE" for trend in trends) or any(label in ("EQH", "EQL", "RANGE") for label in labels)
    return _result("COND_STRUCTURE_RANGE", matched, [f"labels={labels}", f"trends={trends}"], [], "structure")


def cond_choch_or_mss(state: dict[str, Any]) -> dict[str, Any]:
    flags = []
    for tf in ("1m", "5m"):
        payload = _structure(state, tf)
        flags.append(bool(payload.get("choch_detected")) or bool(payload.get("mss_detected")))
    return _result("COND_CHOCH_OR_MSS", any(flags), [f"flags={flags}"], [], "structure")


def cond_near_liquidity_above(state: dict[str, Any]) -> dict[str, Any]:
    matched = _has_level_above(state)
    if matched is None:
        return _missing("COND_NEAR_LIQUIDITY_ABOVE", "liquidity", "CURRENT_PRICE_MISSING")
    return _result("COND_NEAR_LIQUIDITY_ABOVE", matched, [], [], "liquidity")


def cond_near_liquidity_below(state: dict[str, Any]) -> dict[str, Any]:
    matched = _has_level_below(state)
    if matched is None:
        return _missing("COND_NEAR_LIQUIDITY_BELOW", "liquidity", "CURRENT_PRICE_MISSING")
    return _result("COND_NEAR_LIQUIDITY_BELOW", matched, [], [], "liquidity")


def cond_liquidity_target_available(state: dict[str, Any]) -> dict[str, Any]:
    levels = _liquidity(state).get("detected_levels") or []
    matched = bool(levels)
    return _result("COND_LIQUIDITY_TARGET_AVAILABLE", matched, [f"levels={len(levels)}"], [], "liquidity")


def cond_resting_wall_above(state: dict[str, Any]) -> dict[str, Any]:
    matched = _has_level_above(state, ("near_liquidity", "mid_liquidity", "far_liquidity"), "resting_limit_wall")
    if matched is None:
        return _missing("COND_RESTING_WALL_ABOVE", "liquidity", "CURRENT_PRICE_MISSING")
    return _result("COND_RESTING_WALL_ABOVE", matched, [], [], "liquidity")


def cond_resting_wall_below(state: dict[str, Any]) -> dict[str, Any]:
    matched = _has_level_below(state, ("near_liquidity", "mid_liquidity", "far_liquidity"), "resting_limit_wall")
    if matched is None:
        return _missing("COND_RESTING_WALL_BELOW", "liquidity", "CURRENT_PRICE_MISSING")
    return _result("COND_RESTING_WALL_BELOW", matched, [], [], "liquidity")


def _value_position(state: dict[str, Any], expected: str) -> dict[str, Any]:
    cond = f"COND_{expected}"
    position = str(_get(_business_zone(state), "value_area", "value_position") or "UNKNOWN")
    if position == "UNKNOWN":
        return _missing(cond, "business_zone", "VALUE_POSITION_MISSING")
    return _result(cond, position == expected, [f"value_position={position}"], [], "business_zone")


def cond_inside_value(state: dict[str, Any]) -> dict[str, Any]:
    return _value_position(state, "INSIDE_VALUE")


def cond_above_value(state: dict[str, Any]) -> dict[str, Any]:
    return _value_position(state, "ABOVE_VALUE")


def cond_below_value(state: dict[str, Any]) -> dict[str, Any]:
    return _value_position(state, "BELOW_VALUE")


def cond_acceptance(state: dict[str, Any]) -> dict[str, Any]:
    biz_acceptance = _get(_business_zone(state), "auction_summary", "acceptance")
    acceptance_state = str(_regime(state).get("acceptance_state", "UNKNOWN"))
    matched = bool(biz_acceptance) or "ACCEPTED" in acceptance_state
    if biz_acceptance is None and acceptance_state == "UNKNOWN":
        return _missing("COND_ACCEPTANCE", "business_zone/regime", "ACCEPTANCE_STATE_MISSING")
    return _result("COND_ACCEPTANCE", matched, [f"acceptance={biz_acceptance}", f"acceptance_state={acceptance_state}"], [], "business_zone/regime")


def cond_rejection(state: dict[str, Any]) -> dict[str, Any]:
    biz_rejection = _get(_business_zone(state), "auction_summary", "rejection")
    acceptance_state = str(_regime(state).get("acceptance_state", "UNKNOWN"))
    matched = bool(biz_rejection) or "REJECTED" in acceptance_state
    if biz_rejection is None and acceptance_state == "UNKNOWN":
        return _missing("COND_REJECTION", "business_zone/regime", "REJECTION_STATE_MISSING")
    return _result("COND_REJECTION", matched, [f"rejection={biz_rejection}", f"acceptance_state={acceptance_state}"], [], "business_zone/regime")


def cond_business_zone_available(state: dict[str, Any]) -> dict[str, Any]:
    zone = _business_zone(state)
    value_area = zone.get("value_area") or {}
    business_zones = zone.get("business_zones") or {}
    matched = any(value_area.get(key) is not None for key in ("poc", "vah", "val")) or any(business_zones.get(key) is not None for key in ("upper_business_zone", "lower_business_zone"))
    return _result("COND_BUSINESS_ZONE_AVAILABLE", matched, [], [], "business_zone")


def _regime_condition(state: dict[str, Any], expected: str) -> dict[str, Any]:
    cond = f"COND_REGIME_{expected.split('_')[0]}"
    regime = str(_regime(state).get("regime", "UNKNOWN"))
    if regime == "UNKNOWN":
        return _missing(cond, "regime", "REGIME_MISSING")
    reason_codes: list[str] = []
    if expected == "MOMENTUM_MODE" and regime in {"TRANSITION_MODE", "BALANCE_MODE"}:
        reason_codes.append("REGIME_NOT_MOMENTUM_MODE")
    return _result(cond, regime == expected, [f"regime={regime}"], reason_codes, "regime")


def cond_regime_momentum(state: dict[str, Any]) -> dict[str, Any]:
    return _regime_condition(state, "MOMENTUM_MODE")


def cond_regime_balance(state: dict[str, Any]) -> dict[str, Any]:
    return _regime_condition(state, "BALANCE_MODE")


def cond_regime_transition(state: dict[str, Any]) -> dict[str, Any]:
    return _regime_condition(state, "TRANSITION_MODE")


def cond_double_distribution_day(state: dict[str, Any]) -> dict[str, Any]:
    day_type = str(_regime(state).get("day_type", "UNKNOWN"))
    if day_type == "UNKNOWN":
        return _missing("COND_DOUBLE_DISTRIBUTION_DAY", "regime", "DAY_TYPE_MISSING")
    return _result("COND_DOUBLE_DISTRIBUTION_DAY", day_type == "DOUBLE_DISTRIBUTION_DAY", [f"day_type={day_type}"], [], "regime")


def _iceberg_spoof_side(state: dict[str, Any], kind: str, side: str) -> dict[str, Any]:
    cond = f"COND_{kind}_{side}"
    payload = _get(_intent(state), kind.lower()) or {}
    detected = payload.get("detected")
    found_side = str(payload.get("side", "UNKNOWN"))
    if detected is None and not payload:
        return _missing(cond, "intent", f"{kind}_STATE_MISSING")
    return _result(cond, bool(detected) and found_side == side, [f"detected={detected}", f"side={found_side}"], [], "intent")


def cond_iceberg_buy(state: dict[str, Any]) -> dict[str, Any]:
    return _iceberg_spoof_side(state, "ICEBERG", "BUY")


def cond_iceberg_sell(state: dict[str, Any]) -> dict[str, Any]:
    return _iceberg_spoof_side(state, "ICEBERG", "SELL")


def cond_spoof_buy(state: dict[str, Any]) -> dict[str, Any]:
    return _iceberg_spoof_side(state, "SPOOF", "BUY")


def cond_spoof_sell(state: dict[str, Any]) -> dict[str, Any]:
    return _iceberg_spoof_side(state, "SPOOF", "SELL")


def _trapped_side(state: dict[str, Any], side: str) -> dict[str, Any]:
    cond = f"COND_TRAPPED_{side}"
    trapped_side = str(_get(_intent(state), "intent_analysis", "trapped_side") or "UNKNOWN")
    unified_side = str(_get(state.get("unified_context") or {}, "intent_context", "trapped_side") or "UNKNOWN")
    position_trap = str(_get(state.get("positioning") or {}, "ltf_confirmation", "trap_context") or "UNKNOWN")
    expected = side
    matched = trapped_side == expected or unified_side == expected or position_trap == f"{expected}_TRAPPED"
    return _result(cond, matched, [f"intent={trapped_side}", f"unified={unified_side}", f"positioning={position_trap}"], [], "intent/unified_context/positioning")


def cond_trapped_buyers(state: dict[str, Any]) -> dict[str, Any]:
    return _trapped_side(state, "BUYERS")


def cond_trapped_sellers(state: dict[str, Any]) -> dict[str, Any]:
    return _trapped_side(state, "SELLERS")


def cond_absorption_intent(state: dict[str, Any]) -> dict[str, Any]:
    intent_name = str(_get(_intent(state), "intent_analysis", "intent") or "UNKNOWN")
    if intent_name == "UNKNOWN":
        return _missing("COND_ABSORPTION_INTENT", "intent", "INTENT_MISSING")
    return _result("COND_ABSORPTION_INTENT", intent_name == "ABSORPTION", [f"intent={intent_name}"], [], "intent")


def cond_manipulation_intent(state: dict[str, Any]) -> dict[str, Any]:
    intent_name = str(_get(_intent(state), "intent_analysis", "intent") or "UNKNOWN")
    if intent_name == "UNKNOWN":
        return _missing("COND_MANIPULATION_INTENT", "intent", "INTENT_MISSING")
    return _result("COND_MANIPULATION_INTENT", intent_name == "MANIPULATION", [f"intent={intent_name}"], [], "intent")


def _scenario_available(state: dict[str, Any], key: str, condition_id: str) -> dict[str, Any]:
    scenario = _get(_scenarios(state), key) or {}
    quality = str(scenario.get("quality", "UNKNOWN"))
    condition = scenario.get("condition")
    if not scenario:
        return _missing(condition_id, "scenarios", "SCENARIO_MISSING")
    matched = quality != "UNKNOWN" or bool(condition)
    return _result(condition_id, matched, [f"quality={quality}", f"condition={condition}"], [], "scenarios")


def cond_bullish_scenario_available(state: dict[str, Any]) -> dict[str, Any]:
    return _scenario_available(state, "bullish_scenario", "COND_BULLISH_SCENARIO_AVAILABLE")


def cond_bearish_scenario_available(state: dict[str, Any]) -> dict[str, Any]:
    return _scenario_available(state, "bearish_scenario", "COND_BEARISH_SCENARIO_AVAILABLE")


def cond_neutral_range_scenario(state: dict[str, Any]) -> dict[str, Any]:
    return _scenario_available(state, "neutral_range_scenario", "COND_NEUTRAL_RANGE_SCENARIO")


def cond_atr_available(state: dict[str, Any]) -> dict[str, Any]:
    atr_state = _atr(state)
    atr_1m = _safe_float(_get(atr_state, "1m", "atr_14"))
    atr_5m = _safe_float(_get(atr_state, "5m", "atr_14"))
    if atr_1m is None and atr_5m is None:
        return _missing("COND_ATR_AVAILABLE", "atr", "ATR_NOT_AVAILABLE")
    return _result("COND_ATR_AVAILABLE", atr_1m is not None or atr_5m is not None, [f"atr_1m={atr_1m}", f"atr_5m={atr_5m}"], [], "atr")


def cond_atr_expanding(state: dict[str, Any]) -> dict[str, Any]:
    atr_state = _atr(state)
    payload = _get(atr_state, "1m") or {}
    if not payload:
        return _missing("COND_ATR_EXPANDING", "atr", "ATR_STATE_MISSING")
    atr_14 = _safe_float(payload.get("atr_14"))
    tr_latest = _safe_float(payload.get("true_range_latest"))
    quality = str(payload.get("atr_quality", "UNKNOWN"))
    if atr_14 is None or tr_latest is None or quality == "MISSING":
        return _result("COND_ATR_EXPANDING", None, [f"atr_quality={quality}"], ["INSUFFICIENT_ATR_HISTORY"], "atr")
    return _result("COND_ATR_EXPANDING", tr_latest > atr_14, [f"atr_14={atr_14}", f"tr_latest={tr_latest}"], [], "atr")


def cond_data_invalid(state: dict[str, Any]) -> dict[str, Any]:
    observation = _observation(state)
    current_price = _current_price(state)
    levels = [
        str(_get(observation, "data_quality", "level") or "UNKNOWN"),
        str(_get(state.get("dna") or {}, "data_quality", "level") or "UNKNOWN"),
        str(_get(_liquidity(state), "data_quality", "level") or "UNKNOWN"),
    ]
    matched = current_price is None or not observation or any(level in ("INVALID", "MISSING") for level in levels)
    return _result("COND_DATA_INVALID", matched, [f"current_price={current_price}", f"levels={levels}"], [], "observation/dna/liquidity")


def cond_chop_balanced(state: dict[str, Any]) -> dict[str, Any]:
    structure_range = evaluate_condition("COND_STRUCTURE_RANGE", state)["matched"] is True
    candle_truth = str(_get(_dna(state, "1m"), "war_summary", "candle_truth") or "UNKNOWN")
    dominant_side = str(_get(_dna(state, "1m"), "war_summary", "dominant_side") or "UNKNOWN")
    category = _candle_category(state, "1m")
    balanced_candle = candle_truth == "BALANCED" or category in ("NORMAL_BALANCED", "UNKNOWN")
    no_dominant = dominant_side in ("BALANCED", "UNKNOWN", "NEUTRAL")
    matched = structure_range and balanced_candle and no_dominant
    return _result("COND_CHOP_BALANCED", matched, [f"candle_truth={candle_truth}", f"category={category}", f"dominant_side={dominant_side}"], [], "dna/structure")


def cond_sweep_risk_imminent(state: dict[str, Any]) -> dict[str, Any]:
    liquidity = _liquidity(state)
    reason_codes = [str(code).upper() for code in (liquidity.get("reason_codes") or [])]
    observation_codes = [str(code).upper() for code in ((_observation(state).get("reason_codes") or []))]
    matched = any("SWEEP_RISK" in code for code in reason_codes + observation_codes)
    if not matched:
        matched = any(str(level.get("liquidity_type", "")).lower() == "resting_limit_wall" for level in (_detected_levels(state, ("near_liquidity",)) or []))
    return _result("COND_SWEEP_RISK_IMMINENT", matched, reason_codes[:3], [], "liquidity/observation")


CONDITION_MAP: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "COND_BUYERS_ATTACKING": cond_buyers_attacking,
    "COND_SELLERS_ATTACKING": cond_sellers_attacking,
    "COND_BUYERS_DEFENDING": cond_buyers_defending,
    "COND_SELLERS_DEFENDING": cond_sellers_defending,
    "COND_PRICE_FAILED_TO_ADVANCE": cond_price_failed_to_advance,
    "COND_POSITIVE_DELTA": cond_positive_delta,
    "COND_NEGATIVE_DELTA": cond_negative_delta,
    "COND_DELTA_PRICE_DIVERGENCE_BULLISH": cond_delta_price_divergence_bullish,
    "COND_DELTA_PRICE_DIVERGENCE_BEARISH": cond_delta_price_divergence_bearish,
    "COND_TRAP_CANDLE": cond_trap_candle,
    "COND_BUY_IMBALANCE": cond_buy_imbalance,
    "COND_SELL_IMBALANCE": cond_sell_imbalance,
    "COND_LIQUIDITY_SWEEP_DOWN": cond_liquidity_sweep_down,
    "COND_LIQUIDITY_SWEEP_UP": cond_liquidity_sweep_up,
    "COND_FAKE_BULLISH": cond_fake_bullish,
    "COND_FAKE_BEARISH": cond_fake_bearish,
    "COND_REAL_BULLISH": cond_real_bullish,
    "COND_REAL_BEARISH": cond_real_bearish,
    "COND_STRUCTURE_BULLISH": cond_structure_bullish,
    "COND_STRUCTURE_BEARISH": cond_structure_bearish,
    "COND_STRUCTURE_RANGE": cond_structure_range,
    "COND_CHOCH_OR_MSS": cond_choch_or_mss,
    "COND_NEAR_LIQUIDITY_ABOVE": cond_near_liquidity_above,
    "COND_NEAR_LIQUIDITY_BELOW": cond_near_liquidity_below,
    "COND_LIQUIDITY_TARGET_AVAILABLE": cond_liquidity_target_available,
    "COND_RESTING_WALL_ABOVE": cond_resting_wall_above,
    "COND_RESTING_WALL_BELOW": cond_resting_wall_below,
    "COND_INSIDE_VALUE": cond_inside_value,
    "COND_ABOVE_VALUE": cond_above_value,
    "COND_BELOW_VALUE": cond_below_value,
    "COND_ACCEPTANCE": cond_acceptance,
    "COND_REJECTION": cond_rejection,
    "COND_BUSINESS_ZONE_AVAILABLE": cond_business_zone_available,
    "COND_REGIME_MOMENTUM": cond_regime_momentum,
    "COND_REGIME_BALANCE": cond_regime_balance,
    "COND_REGIME_TRANSITION": cond_regime_transition,
    "COND_DOUBLE_DISTRIBUTION_DAY": cond_double_distribution_day,
    "COND_ICEBERG_BUY": cond_iceberg_buy,
    "COND_ICEBERG_SELL": cond_iceberg_sell,
    "COND_SPOOF_BUY": cond_spoof_buy,
    "COND_SPOOF_SELL": cond_spoof_sell,
    "COND_TRAPPED_BUYERS": cond_trapped_buyers,
    "COND_TRAPPED_SELLERS": cond_trapped_sellers,
    "COND_ABSORPTION_INTENT": cond_absorption_intent,
    "COND_MANIPULATION_INTENT": cond_manipulation_intent,
    "COND_BULLISH_SCENARIO_AVAILABLE": cond_bullish_scenario_available,
    "COND_BEARISH_SCENARIO_AVAILABLE": cond_bearish_scenario_available,
    "COND_NEUTRAL_RANGE_SCENARIO": cond_neutral_range_scenario,
    "COND_ATR_AVAILABLE": cond_atr_available,
    "COND_ATR_EXPANDING": cond_atr_expanding,
    "COND_DATA_INVALID": cond_data_invalid,
    "COND_CHOP_BALANCED": cond_chop_balanced,
    "COND_SWEEP_RISK_IMMINENT": cond_sweep_risk_imminent,
}


def evaluate_condition(condition_id: str, state: dict[str, Any]) -> dict[str, Any]:
    fn = CONDITION_MAP.get(condition_id)
    if fn is None:
        return _result(condition_id, None, [], ["CONDITION_NOT_IMPLEMENTED"], "model_condition_library")
    try:
        return fn(state)
    except Exception as exc:
        return _result(condition_id, None, [], [f"EVALUATION_ERROR_{type(exc).__name__.upper()}"], "model_condition_library")


def evaluate_condition_group(condition_ids: list[str], state: dict[str, Any]) -> dict[str, Any]:
    results = {condition_id: evaluate_condition(condition_id, state) for condition_id in condition_ids}
    matched = [cid for cid, result in results.items() if result.get("status") == "MATCHED"]
    missing = [cid for cid, result in results.items() if result.get("status") == "MISSING"]
    unknown = [cid for cid, result in results.items() if result.get("status") == "UNKNOWN"]
    not_matched = [cid for cid, result in results.items() if result.get("status") == "NOT_MATCHED"]
    return {
        "results": results,
        "matched_conditions": matched,
        "missing_conditions": missing,
        "unknown_conditions": unknown,
        "not_matched_conditions": not_matched,
    }


def run_condition_semantic_selftest() -> dict[str, Any]:
    range_structure = {
        "1m": {"structure_label": "EQH", "trend_state": "RANGE"},
        "5m": {"structure_label": "RANGE", "trend_state": "RANGE"},
    }
    bullish_state = {
        "observation": {"war_reading": {"who_attacked": "BUYERS", "who_defended": "SELLERS", "price_failed_to_advance": False}, "volume_flow": {"delta": 1.0}},
        "dna": {"1m": {"war_summary": {"candle_truth": "REAL_BULLISH", "dominant_side": "BUYERS"}, "candle_category": {"primary": "CONTINUATION_CANDLE"}, "delta": 1.0}},
        "structure": {"1m": {"structure_label": "HH", "trend_state": "UPTREND"}, "5m": {"structure_label": "HL", "trend_state": "UPTREND"}},
        "regime": {"regime": "MOMENTUM_MODE"},
    }
    bearish_state = {
        "observation": {"war_reading": {"who_attacked": "SELLERS", "who_defended": "BUYERS", "price_failed_to_advance": False}, "volume_flow": {"delta": -1.0}},
        "dna": {"1m": {"war_summary": {"candle_truth": "REAL_BEARISH", "dominant_side": "SELLERS"}, "candle_category": {"primary": "CONTINUATION_CANDLE"}, "delta": -1.0}},
        "structure": {"1m": {"structure_label": "LL", "trend_state": "DOWNTREND"}, "5m": {"structure_label": "LH", "trend_state": "DOWNTREND"}},
        "regime": {"regime": "MOMENTUM_MODE"},
    }
    range_state = {
        "observation": {"war_reading": {"who_attacked": "UNKNOWN", "who_defended": "UNKNOWN", "price_failed_to_advance": False}, "volume_flow": {"delta": 0.0}},
        "dna": {"1m": {"war_summary": {"candle_truth": "BALANCED", "dominant_side": "BALANCED"}, "candle_category": {"primary": "UNKNOWN"}, "delta": 0.0}},
        "structure": range_structure,
        "regime": {"regime": "TRANSITION_MODE"},
    }
    fake_bullish_fail_state = {
        "observation": {"war_reading": {"who_attacked": "BUYERS", "who_defended": "SELLERS", "price_failed_to_advance": True}, "volume_flow": {"delta": 1.0}},
        "dna": {"1m": {"war_summary": {"candle_truth": "FAKE_BULLISH", "dominant_side": "BUYERS"}, "candle_category": {"primary": "TRAP_CANDLE"}, "delta": 1.0}},
        "structure": range_structure,
        "intent": {"intent_analysis": {"trapped_side": "BUYERS"}},
        "positioning": {"ltf_confirmation": {"trap_context": "BUYERS_TRAPPED"}},
    }
    fake_bearish_fail_state = {
        "observation": {"war_reading": {"who_attacked": "SELLERS", "who_defended": "BUYERS", "price_failed_to_advance": False}, "volume_flow": {"delta": -1.0}},
        "dna": {"1m": {"war_summary": {"candle_truth": "FAKE_BEARISH", "dominant_side": "SELLERS"}, "candle_category": {"primary": "TRAP_CANDLE"}, "delta": -1.0}},
        "structure": range_structure,
        "intent": {"intent_analysis": {"trapped_side": "SELLERS"}},
        "positioning": {"ltf_confirmation": {"trap_context": "SELLERS_TRAPPED"}},
    }

    checks = {
        "REAL_BULLISH_DOES_NOT_MATCH_REAL_BEARISH": evaluate_condition("COND_REAL_BULLISH", bearish_state).get("status") != "MATCHED",
        "REAL_BEARISH_DOES_NOT_MATCH_REAL_BULLISH": evaluate_condition("COND_REAL_BEARISH", bullish_state).get("status") != "MATCHED",
        "STRUCTURE_BULLISH_DOES_NOT_MATCH_RANGE_EQH": evaluate_condition("COND_STRUCTURE_BULLISH", range_state).get("status") != "MATCHED",
        "STRUCTURE_BEARISH_DOES_NOT_MATCH_RANGE_EQH": evaluate_condition("COND_STRUCTURE_BEARISH", range_state).get("status") != "MATCHED",
        "MOMENTUM_DOES_NOT_MATCH_TRANSITION_MODE": evaluate_condition("COND_REGIME_MOMENTUM", range_state).get("status") != "MATCHED",
        "FAKE_BULLISH_DOES_NOT_MATCH_OPPOSITE_REAL": evaluate_condition("COND_FAKE_BULLISH", bearish_state).get("status") != "MATCHED",
        "FAKE_BEARISH_DOES_NOT_MATCH_OPPOSITE_REAL": evaluate_condition("COND_FAKE_BEARISH", bullish_state).get("status") != "MATCHED",
        "FAKE_BULLISH_CAN_MATCH_BUYER_FAILURE": evaluate_condition("COND_FAKE_BULLISH", fake_bullish_fail_state).get("status") == "MATCHED",
        "FAKE_BEARISH_CAN_MATCH_SELLER_FAILURE": evaluate_condition("COND_FAKE_BEARISH", fake_bearish_fail_state).get("status") == "MATCHED",
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "semantic_health": "PASS" if not failed else "FAILED",
        "checks": checks,
        "failed_tests": failed,
    }


def main() -> None:
    result = run_condition_semantic_selftest()
    if result["failed_tests"]:
        print("FAILED_TESTS=" + ",".join(result["failed_tests"]))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
