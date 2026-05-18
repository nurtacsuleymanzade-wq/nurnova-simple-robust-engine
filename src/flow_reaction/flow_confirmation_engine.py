from __future__ import annotations

from typing import Any

_MIN_DELTA = 100  # minimum delta magnitude to count as a signal


def _safe_str(val: Any) -> str:
    return str(val).upper() if val else ""


def build_flow_confirmation(
    active_scenario: dict[str, Any] | None,
    market_state: dict[str, Any] | None,
    candle: dict[str, Any] | None,
    footprint: dict[str, Any] | None,
    order_flow: dict[str, Any] | None,
    liquidity: dict[str, Any] | None,
    data_quality: str = "UNKNOWN",
) -> dict[str, Any]:
    """
    Produces flow_confirmation enum + evidence + reason_codes.
    Context-only; no trade permissions emitted.
    """
    confirmation_reason_codes: list[str] = []
    rejection_reason_codes: list[str] = []
    conflict_reason_codes: list[str] = []

    if data_quality == "INVALID":
        return {
            "flow_confirmation": "UNKNOWN",
            "confirmation_reason_codes": [],
            "rejection_reason_codes": ["DATA_QUALITY_INVALID"],
            "conflict_reason_codes": [],
            "evidence_used": {},
        }

    scenario_bias = "UNKNOWN"
    scenario_confidence = 0.0
    if active_scenario:
        scenario_bias = _safe_str(active_scenario.get("scenario_bias", "UNKNOWN"))
        scenario_confidence = float(active_scenario.get("scenario_confidence") or 0.0)

    market_trend = "UNKNOWN"
    flow_state = "UNKNOWN"
    if market_state:
        market_trend = _safe_str(market_state.get("trend_state", "UNKNOWN"))
        flow_state = _safe_str(market_state.get("flow_state", "UNKNOWN"))

    candle_bullish = False
    candle_bearish = False
    candle_body_ratio = 0.0
    if candle:
        official = candle.get("official_candle") or candle
        o = float(official.get("open") or 0)
        c = float(official.get("close") or 0)
        h = float(official.get("high") or 0)
        lo = float(official.get("low") or 0)
        rng = h - lo if h > lo else 1
        body = abs(c - o)
        candle_body_ratio = body / rng if rng > 0 else 0.0
        candle_bullish = c > o
        candle_bearish = c < o

    delta = 0.0
    cvd_trend = "UNKNOWN"
    if order_flow:
        delta = float(order_flow.get("delta") or order_flow.get("net_delta") or 0)
        cvd_trend = _safe_str(order_flow.get("cvd_trend") or order_flow.get("cumulative_delta_trend") or "UNKNOWN")

    fp_buy_dominant = False
    fp_sell_dominant = False
    if footprint:
        fp_buy_dominant = bool(footprint.get("buy_dominant") or footprint.get("buyer_dominated"))
        fp_sell_dominant = bool(footprint.get("sell_dominant") or footprint.get("seller_dominated"))

    liquidity_upside = False
    liquidity_downside = False
    if liquidity:
        lp = _safe_str(liquidity.get("liquidity_pressure_state") or liquidity.get("side") or "")
        liquidity_upside = "BUY" in lp or "UPSIDE" in lp or lp == "BOTH"
        liquidity_downside = "SELL" in lp or "DOWNSIDE" in lp or lp == "BOTH"

    has_any_evidence = any([
        active_scenario is not None,
        market_state is not None,
        candle is not None,
        order_flow is not None,
        footprint is not None,
    ])
    if not has_any_evidence:
        return {
            "flow_confirmation": "UNKNOWN",
            "confirmation_reason_codes": ["NO_EVIDENCE_AVAILABLE"],
            "rejection_reason_codes": [],
            "conflict_reason_codes": [],
            "evidence_used": {},
        }

    evidence_used = {
        "scenario_bias": scenario_bias,
        "scenario_confidence": scenario_confidence,
        "market_trend": market_trend,
        "flow_state": flow_state,
        "candle_bullish": candle_bullish,
        "candle_bearish": candle_bearish,
        "candle_body_ratio": round(candle_body_ratio, 4),
        "delta": delta,
        "cvd_trend": cvd_trend,
        "fp_buy_dominant": fp_buy_dominant,
        "fp_sell_dominant": fp_sell_dominant,
        "liquidity_upside": liquidity_upside,
        "liquidity_downside": liquidity_downside,
    }

    long_signals = 0
    short_signals = 0

    if scenario_bias == "LONG":
        long_signals += 2
        confirmation_reason_codes.append("SCENARIO_BIAS_LONG")
    elif scenario_bias == "SHORT":
        short_signals += 2
        confirmation_reason_codes.append("SCENARIO_BIAS_SHORT")

    if market_trend in ("BULLISH", "UPTREND"):
        long_signals += 1
        confirmation_reason_codes.append("MARKET_TREND_BULLISH")
    elif market_trend in ("BEARISH", "DOWNTREND"):
        short_signals += 1
        confirmation_reason_codes.append("MARKET_TREND_BEARISH")

    if "BUY" in flow_state and "SELL" not in flow_state:
        long_signals += 1
        confirmation_reason_codes.append("FLOW_STATE_BUY_PRESSURE")
    elif "SELL" in flow_state and "BUY" not in flow_state:
        short_signals += 1
        confirmation_reason_codes.append("FLOW_STATE_SELL_PRESSURE")

    if candle_bullish and candle_body_ratio > 0.4:
        long_signals += 1
        confirmation_reason_codes.append("CANDLE_BULLISH_CLOSE")
    elif candle_bearish and candle_body_ratio > 0.4:
        short_signals += 1
        confirmation_reason_codes.append("CANDLE_BEARISH_CLOSE")

    # Only count delta if it is meaningful
    if delta > _MIN_DELTA:
        long_signals += 1
        confirmation_reason_codes.append("DELTA_POSITIVE")
    elif delta < -_MIN_DELTA:
        short_signals += 1
        confirmation_reason_codes.append("DELTA_NEGATIVE")

    if fp_buy_dominant:
        long_signals += 1
        confirmation_reason_codes.append("FOOTPRINT_BUY_DOMINANT")
    elif fp_sell_dominant:
        short_signals += 1
        confirmation_reason_codes.append("FOOTPRINT_SELL_DOMINANT")

    if "UP" in cvd_trend or "BULL" in cvd_trend or cvd_trend == "POSITIVE":
        long_signals += 1
    elif "DOWN" in cvd_trend or "BEAR" in cvd_trend or cvd_trend == "NEGATIVE":
        short_signals += 1

    # Conflict: scenario bias opposes the dominant flow direction
    scenario_opposes_flow = (
        scenario_bias == "LONG" and short_signals >= long_signals
    ) or (
        scenario_bias == "SHORT" and long_signals >= short_signals
    )

    if scenario_bias == "LONG" and (
        delta < -_MIN_DELTA or flow_state in ("SELL_PRESSURE", "SELLING")
    ):
        conflict_reason_codes.append("LONG_SCENARIO_BUT_NEGATIVE_DELTA_OR_SELL_FLOW")

    if scenario_bias == "SHORT" and (
        delta > _MIN_DELTA or flow_state in ("BUY_PRESSURE", "BUYING")
    ):
        conflict_reason_codes.append("SHORT_SCENARIO_BUT_POSITIVE_DELTA_OR_BUY_FLOW")

    if candle_bullish and delta < -_MIN_DELTA:
        conflict_reason_codes.append("PRICE_UP_DELTA_NEGATIVE")
    if candle_bearish and delta > _MIN_DELTA:
        conflict_reason_codes.append("PRICE_DOWN_DELTA_POSITIVE")

    # CONFLICTED: scenario bias directly opposes clear multi-signal direction
    if conflict_reason_codes and scenario_opposes_flow and abs(long_signals - short_signals) <= 2:
        return {
            "flow_confirmation": "CONFLICTED",
            "confirmation_reason_codes": confirmation_reason_codes,
            "rejection_reason_codes": rejection_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
            "evidence_used": evidence_used,
        }

    # CONFIRMED_LONG: need >= 4 signals (including scenario 2pts) dominated by long
    if long_signals >= 4 and long_signals > short_signals * 1.2:
        return {
            "flow_confirmation": "CONFIRMED_LONG",
            "confirmation_reason_codes": confirmation_reason_codes,
            "rejection_reason_codes": rejection_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
            "evidence_used": evidence_used,
        }

    # CONFIRMED_SHORT: need >= 4 signals dominated by short
    if short_signals >= 4 and short_signals > long_signals * 1.2:
        return {
            "flow_confirmation": "CONFIRMED_SHORT",
            "confirmation_reason_codes": confirmation_reason_codes,
            "rejection_reason_codes": rejection_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
            "evidence_used": evidence_used,
        }

    # Residual conflict check
    if conflict_reason_codes:
        return {
            "flow_confirmation": "CONFLICTED",
            "confirmation_reason_codes": confirmation_reason_codes,
            "rejection_reason_codes": rejection_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
            "evidence_used": evidence_used,
        }

    rejection_reason_codes.append("INSUFFICIENT_FLOW_ALIGNMENT")
    return {
        "flow_confirmation": "NOT_CONFIRMED",
        "confirmation_reason_codes": confirmation_reason_codes,
        "rejection_reason_codes": rejection_reason_codes,
        "conflict_reason_codes": conflict_reason_codes,
        "evidence_used": evidence_used,
    }
