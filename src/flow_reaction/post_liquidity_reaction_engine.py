from __future__ import annotations

from typing import Any

_MIN_DELTA = 100  # minimum magnitude to count delta as directional signal
_TRAP_MIN_BODY = 0.45  # body_ratio threshold for trap classification
_TRAP_MIN_DELTA = 200  # delta magnitude for trap classification


def _safe_str(val: Any) -> str:
    return str(val).upper() if val else ""


def _extract_liquidity_event(liquidity: dict[str, Any] | None) -> dict[str, Any]:
    """Extract liquidity event signals from explicit flags only (no wick inference)."""
    event: dict[str, Any] = {
        "sweep_detected": False,
        "liquidity_taken": False,
        "upside_sweep": False,
        "downside_sweep": False,
        "wick_above": False,
        "wick_below": False,
        "reclaim_detected": False,
        "rejection_detected": False,
        "liquidity_above_taken": False,
        "liquidity_below_taken": False,
    }

    if not liquidity:
        return event

    flags = liquidity.get("reaction_flags") or {}
    lp = _safe_str(liquidity.get("liquidity_pressure_state") or "")

    event["upside_sweep"] = bool(flags.get("upside_sweep") or "UPSIDE_SWEEP" in lp)
    event["downside_sweep"] = bool(flags.get("downside_sweep") or "DOWNSIDE_SWEEP" in lp)
    event["liquidity_above_taken"] = bool(flags.get("liquidity_above_taken"))
    event["liquidity_below_taken"] = bool(flags.get("liquidity_below_taken"))
    event["reclaim_detected"] = bool(flags.get("reclaim"))
    event["rejection_detected"] = bool(flags.get("rejection"))
    event["sweep_detected"] = event["upside_sweep"] or event["downside_sweep"]
    event["liquidity_taken"] = event["liquidity_above_taken"] or event["liquidity_below_taken"]

    return event


def _extract_candle_reaction(candle: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bullish_close": False,
        "bearish_close": False,
        "body_ratio": 0.0,
        "upper_wick_ratio": 0.0,
        "lower_wick_ratio": 0.0,
        "indecision": False,
    }
    if not candle:
        return result
    official = candle.get("official_candle") or candle
    o = float(official.get("open") or 0)
    c = float(official.get("close") or 0)
    h = float(official.get("high") or 0)
    lo = float(official.get("low") or 0)
    rng = h - lo if h > lo else 1
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - lo
    result["body_ratio"] = round(body / rng, 4) if rng > 0 else 0.0
    result["upper_wick_ratio"] = round(upper_wick / rng, 4) if rng > 0 else 0.0
    result["lower_wick_ratio"] = round(lower_wick / rng, 4) if rng > 0 else 0.0
    result["bullish_close"] = c > o
    result["bearish_close"] = c < o
    result["indecision"] = result["body_ratio"] < 0.2
    return result


def _detect_absorption(
    delta: float,
    candle_rx: dict[str, Any],
    fp_buy_dominant: bool,
    fp_sell_dominant: bool,
) -> tuple[bool, bool, list[str]]:
    """Returns (buy_absorption, sell_absorption, reason_codes)."""
    buy_absorption = False
    sell_absorption = False
    codes: list[str] = []

    if delta > _TRAP_MIN_DELTA and candle_rx["upper_wick_ratio"] > 0.3:
        buy_absorption = True
        codes.append("BUY_DELTA_POSITIVE_UPPER_WICK")
    if delta < -_TRAP_MIN_DELTA and candle_rx["lower_wick_ratio"] > 0.3:
        sell_absorption = True
        codes.append("SELL_DELTA_NEGATIVE_LOWER_WICK")
    if fp_buy_dominant and candle_rx["upper_wick_ratio"] > 0.35:
        buy_absorption = True
        codes.append("FP_BUY_DOMINANT_UPPER_WICK")
    if fp_sell_dominant and candle_rx["lower_wick_ratio"] > 0.35:
        sell_absorption = True
        codes.append("FP_SELL_DOMINANT_LOWER_WICK")

    return buy_absorption, sell_absorption, codes


def build_post_liquidity_reaction(
    liquidity: dict[str, Any] | None,
    candle: dict[str, Any] | None,
    order_flow: dict[str, Any] | None,
    footprint: dict[str, Any] | None,
    structure: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    market_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Classifies post-liquidity reaction, absorption, and trap states.
    Context-only; no trade permissions emitted.
    """
    liq_event = _extract_liquidity_event(liquidity)
    candle_rx = _extract_candle_reaction(candle)

    delta = 0.0
    if order_flow:
        delta = float(order_flow.get("delta") or order_flow.get("net_delta") or 0)

    fp_buy_dominant = False
    fp_sell_dominant = False
    if footprint:
        fp_buy_dominant = bool(footprint.get("buy_dominant") or footprint.get("buyer_dominated"))
        fp_sell_dominant = bool(footprint.get("sell_dominant") or footprint.get("seller_dominated"))

    flow_state = "UNKNOWN"
    if market_state:
        flow_state = _safe_str(market_state.get("flow_state") or "UNKNOWN")

    reaction_reason_codes: list[str] = []
    absorption_reason_codes: list[str] = []
    trap_reason_codes: list[str] = []

    buy_absorption, sell_absorption, abs_codes = _detect_absorption(
        delta, candle_rx, fp_buy_dominant, fp_sell_dominant
    )
    absorption_reason_codes.extend(abs_codes)

    if buy_absorption and sell_absorption:
        absorption_state = "BOTH"
    elif buy_absorption:
        absorption_state = "BUY_ABSORPTION"
    elif sell_absorption:
        absorption_state = "SELL_ABSORPTION"
    else:
        absorption_state = "NONE"

    # --- No liquidity event: check for breakout or absorption without sweep ---
    if not liq_event["sweep_detected"] and not liq_event["liquidity_taken"]:
        # Absorption without sweep
        if buy_absorption or sell_absorption:
            reaction_reason_codes.extend(absorption_reason_codes)
            return _build_result(
                "ABSORPTION_DETECTED", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )
        # Real breakout: strong directional candle + confirming flow, no sweep needed
        if (
            candle_rx["body_ratio"] > 0.6
            and not candle_rx["indecision"]
            and abs(delta) > _MIN_DELTA
        ):
            if candle_rx["bullish_close"] and delta > _MIN_DELTA and "BUY" in flow_state:
                reaction_reason_codes.append("STRONG_BULLISH_BODY_BUY_FLOW_BREAKOUT")
                return _build_result(
                    "REAL_BREAKOUT", absorption_state, "NONE",
                    reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                    liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
                )
            if candle_rx["bearish_close"] and delta < -_MIN_DELTA and "SELL" in flow_state:
                reaction_reason_codes.append("STRONG_BEARISH_BODY_SELL_FLOW_BREAKOUT")
                return _build_result(
                    "REAL_BREAKOUT", absorption_state, "NONE",
                    reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                    liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
                )
        # Failed breakout: directional attempt but wick rejection
        if (candle_rx["upper_wick_ratio"] > 0.4 or candle_rx["lower_wick_ratio"] > 0.4) and (
            candle is not None or order_flow is not None
        ):
            reaction_reason_codes.append("BREAKOUT_WICK_REJECTION")
            return _build_result(
                "FAILED_BREAKOUT", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )
        reaction_reason_codes.append("NO_SWEEP_OR_LIQUIDITY_TAKEN")
        return _build_result(
            "NO_LIQUIDITY_EVENT", absorption_state, "NONE",
            reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
            liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
        )

    # --- Liquidity event exists: check for sufficient evidence ---
    has_flow_evidence = order_flow is not None or footprint is not None
    has_candle_evidence = candle is not None
    if not has_flow_evidence and not has_candle_evidence:
        reaction_reason_codes.append("LIQUIDITY_EVENT_BUT_NO_FLOW_OR_CANDLE")
        return _build_result(
            "INSUFFICIENT_EVIDENCE", absorption_state, "NONE",
            reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
            liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
        )

    # --- Upside sweep / liquidity above taken ---
    if liq_event["upside_sweep"] or liq_event["liquidity_above_taken"]:
        # BUYERS_TRAPPED: strong bearish reversal after upside sweep (high confidence)
        if (
            candle_rx["bearish_close"]
            and candle_rx["body_ratio"] > _TRAP_MIN_BODY
            and delta < -_TRAP_MIN_DELTA
        ):
            trap_reason_codes.append("UPSIDE_SWEEP_STRONG_BEARISH_BODY_NEGATIVE_DELTA")
            return _build_result(
                "BUYERS_TRAPPED", absorption_state, "BUYERS_TRAPPED",
                trap_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # CONTINUATION: bullish follow-through (close stays long side, positive delta)
        if candle_rx["bullish_close"] and candle_rx["body_ratio"] > 0.3 and delta >= 0:
            reaction_reason_codes.append("UPSIDE_SWEEP_BULLISH_CLOSE_FOLLOW_THROUGH")
            return _build_result(
                "CONTINUATION_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # REJECTION: upper wick dominant
        if candle_rx["upper_wick_ratio"] > 0.4:
            reaction_reason_codes.append("UPSIDE_SWEEP_UPPER_WICK_REJECTION")
            return _build_result(
                "REJECTION_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # REVERSAL: moderate bearish close
        if candle_rx["bearish_close"] and candle_rx["body_ratio"] > 0.2:
            reaction_reason_codes.append("UPSIDE_SWEEP_BEARISH_REVERSAL")
            return _build_result(
                "REVERSAL_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # RECLAIM
        if liq_event["reclaim_detected"]:
            reaction_reason_codes.append("UPSIDE_SWEEP_RECLAIM")
            return _build_result(
                "RECLAIM_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        reaction_reason_codes.append("UPSIDE_SWEEP_REACTION_UNCLEAR")
        return _build_result(
            "INSUFFICIENT_EVIDENCE", absorption_state, "NONE",
            reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
            liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
        )

    # --- Downside sweep / liquidity below taken ---
    if liq_event["downside_sweep"] or liq_event["liquidity_below_taken"]:
        # RECLAIM first (explicit flag overrides trap)
        if liq_event["reclaim_detected"] and candle_rx["bullish_close"]:
            reaction_reason_codes.append("DOWNSIDE_SWEEP_RECLAIM")
            return _build_result(
                "RECLAIM_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # SELLERS_TRAPPED: strong bullish reversal after downside sweep
        if (
            candle_rx["bullish_close"]
            and candle_rx["body_ratio"] > _TRAP_MIN_BODY
            and delta > _TRAP_MIN_DELTA
        ):
            trap_reason_codes.append("DOWNSIDE_SWEEP_STRONG_BULLISH_BODY_POSITIVE_DELTA")
            return _build_result(
                "SELLERS_TRAPPED", absorption_state, "SELLERS_TRAPPED",
                trap_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # CONTINUATION: bearish follow-through
        if candle_rx["bearish_close"] and candle_rx["body_ratio"] > 0.3 and delta <= 0:
            reaction_reason_codes.append("DOWNSIDE_SWEEP_BEARISH_CLOSE_FOLLOW_THROUGH")
            return _build_result(
                "CONTINUATION_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # REJECTION: lower wick dominant
        if candle_rx["lower_wick_ratio"] > 0.4:
            reaction_reason_codes.append("DOWNSIDE_SWEEP_LOWER_WICK_REJECTION")
            return _build_result(
                "REJECTION_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        # REVERSAL: moderate bullish close
        if candle_rx["bullish_close"] and candle_rx["body_ratio"] > 0.2:
            reaction_reason_codes.append("DOWNSIDE_SWEEP_BULLISH_REVERSAL")
            return _build_result(
                "REVERSAL_AFTER_SWEEP", absorption_state, "NONE",
                reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
                liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
            )

        reaction_reason_codes.append("DOWNSIDE_SWEEP_REACTION_UNCLEAR")
        return _build_result(
            "INSUFFICIENT_EVIDENCE", absorption_state, "NONE",
            reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
            liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
        )

    reaction_reason_codes.append("SWEEP_DETECTED_BUT_REACTION_UNCLEAR")
    return _build_result(
        "INSUFFICIENT_EVIDENCE", absorption_state, "NONE",
        reaction_reason_codes, absorption_reason_codes, trap_reason_codes,
        liq_event, candle_rx, delta, fp_buy_dominant, fp_sell_dominant,
    )


def _build_result(
    post_liquidity_reaction: str,
    absorption_state: str,
    trap_state: str,
    reaction_reason_codes: list[str],
    absorption_reason_codes: list[str],
    trap_reason_codes: list[str],
    liq_event: dict[str, Any],
    candle_rx: dict[str, Any],
    delta: float,
    fp_buy_dominant: bool,
    fp_sell_dominant: bool,
) -> dict[str, Any]:
    return {
        "post_liquidity_reaction": post_liquidity_reaction,
        "absorption_state": absorption_state,
        "trap_state": trap_state,
        "reaction_reason_codes": reaction_reason_codes,
        "absorption_reason_codes": absorption_reason_codes,
        "trap_reason_codes": trap_reason_codes,
        "evidence": {
            "liquidity_event": liq_event,
            "candle_reaction": candle_rx,
            "delta": delta,
            "fp_buy_dominant": fp_buy_dominant,
            "fp_sell_dominant": fp_sell_dominant,
        },
    }
