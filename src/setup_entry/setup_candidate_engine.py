from __future__ import annotations

from typing import Any


def _safe_str(val: Any) -> str:
    return str(val).upper() if val else ""


def build_setup_candidate(
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    liquidity: dict[str, Any] | None,
    structure: dict[str, Any] | None,
    candle: dict[str, Any] | None,
    data_quality: str = "UNKNOWN",
) -> dict[str, Any]:
    """
    Produces setup_candidate enum + direction + quality + confidence + evidence.
    Context-only; no trade plan or entry prices emitted.
    """
    setup_reason_codes: list[str] = []
    conflict_reason_codes: list[str] = []
    missing_evidence: list[str] = []

    if data_quality == "INVALID":
        return {
            "setup_candidate": "UNKNOWN",
            "setup_direction": "UNKNOWN",
            "setup_quality": "INVALID",
            "setup_confidence": 0.0,
            "setup_reason_codes": ["DATA_QUALITY_INVALID"],
            "conflict_reason_codes": [],
            "missing_evidence": [],
            "evidence_dict": {},
        }

    # Extract evidence
    market_regime = "UNKNOWN"
    trend_state = "UNKNOWN"
    risk_state = "UNKNOWN"
    if market_state:
        market_regime = _safe_str(market_state.get("market_regime") or "UNKNOWN")
        trend_state = _safe_str(market_state.get("trend_state") or "UNKNOWN")
        risk_state = _safe_str(market_state.get("risk_state") or "UNKNOWN")

    scenario = "NO_ACTIVE_SCENARIO"
    scenario_bias = "UNKNOWN"
    scenario_conf = 0.0
    if active_scenario:
        scenario = _safe_str(active_scenario.get("active_scenario") or "NO_ACTIVE_SCENARIO")
        scenario_bias = _safe_str(active_scenario.get("scenario_bias") or "UNKNOWN")
        scenario_conf = float(active_scenario.get("scenario_confidence") or 0.0)

    flow_confirmation = "UNKNOWN"
    post_liquidity_reaction = "UNKNOWN"
    absorption_state = "UNKNOWN"
    trap_state = "UNKNOWN"
    flow_conf = 0.0
    if flow_reaction:
        flow_confirmation = _safe_str(flow_reaction.get("flow_confirmation") or "UNKNOWN")
        post_liquidity_reaction = _safe_str(flow_reaction.get("post_liquidity_reaction") or "UNKNOWN")
        absorption_state = _safe_str(flow_reaction.get("absorption_state") or "UNKNOWN")
        trap_state = _safe_str(flow_reaction.get("trap_state") or "UNKNOWN")
        flow_conf = float(flow_reaction.get("reaction_confidence") or 0.0)

    liq_pressure = "UNKNOWN"
    if liquidity:
        liq_pressure = _safe_str(liquidity.get("liquidity_pressure_state") or "UNKNOWN")

    has_any_evidence = any([market_state, active_scenario, flow_reaction, liquidity])
    if not has_any_evidence:
        missing_evidence.extend(["MARKET_STATE", "ACTIVE_SCENARIO", "FLOW_REACTION", "LIQUIDITY"])
        return {
            "setup_candidate": "UNKNOWN",
            "setup_direction": "UNKNOWN",
            "setup_quality": "INVALID",
            "setup_confidence": 0.0,
            "setup_reason_codes": ["NO_EVIDENCE_AVAILABLE"],
            "conflict_reason_codes": [],
            "missing_evidence": missing_evidence,
            "evidence_dict": {},
        }

    evidence_dict = {
        "market_regime": market_regime,
        "trend_state": trend_state,
        "risk_state": risk_state,
        "scenario": scenario,
        "scenario_bias": scenario_bias,
        "scenario_confidence": scenario_conf,
        "flow_confirmation": flow_confirmation,
        "post_liquidity_reaction": post_liquidity_reaction,
        "absorption_state": absorption_state,
        "trap_state": trap_state,
        "liquidity_pressure": liq_pressure,
    }

    # Setup classification logic
    setup_candidate = "NO_SETUP"
    setup_direction = "UNKNOWN"
    setup_quality = "INVALID"
    setup_confidence = 0.0

    # NO_SETUP / CONFLICTED check
    if market_state is None or scenario == "NO_ACTIVE_SCENARIO":
        setup_candidate = "NO_SETUP"
        setup_direction = "NO_TRADE"
        setup_quality = "INVALID"
        setup_confidence = 0.0
        missing_evidence.append("MARKET_STATE" if market_state is None else "ACTIVE_SCENARIO")
        setup_reason_codes.append("NO_SETUP_MISSING_CRITICAL_INPUT")
        return {
            "setup_candidate": setup_candidate,
            "setup_direction": setup_direction,
            "setup_quality": setup_quality,
            "setup_confidence": setup_confidence,
            "setup_reason_codes": setup_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
            "missing_evidence": missing_evidence,
            "evidence_dict": evidence_dict,
        }

    if risk_state == "NO_TRADE":
        setup_candidate = "NO_SETUP"
        setup_direction = "NO_TRADE"
        setup_quality = "INVALID"
        setup_confidence = 0.0
        conflict_reason_codes.append("RISK_STATE_NO_TRADE")
        setup_reason_codes.append("NO_SETUP_RISK_PROHIBITS_ENTRY")
        return {
            "setup_candidate": setup_candidate,
            "setup_direction": setup_direction,
            "setup_quality": setup_quality,
            "setup_confidence": setup_confidence,
            "setup_reason_codes": setup_reason_codes,
            "conflict_reason_codes": conflict_reason_codes,
            "missing_evidence": missing_evidence,
            "evidence_dict": evidence_dict,
        }

    # Scoring signals
    long_score = 0.0
    short_score = 0.0
    trap_indicators = 0
    special_setup = ""

    # Market regime alignment
    if market_regime == "UPTREND":
        long_score += 0.3
    elif market_regime == "DOWNTREND":
        short_score += 0.3
    elif market_regime == "EXPANSION":
        long_score += 0.15
        short_score += 0.15

    # Active scenario alignment
    if scenario in ("BULLISH_CONTINUATION", "BULLISH_REVERSAL", "RANGE_ROTATION_UP", "COMPRESSION_BREAKOUT_UP"):
        long_score += 0.4
    elif scenario in ("BEARISH_CONTINUATION", "BEARISH_REVERSAL", "RANGE_ROTATION_DOWN", "COMPRESSION_BREAKOUT_DOWN"):
        short_score += 0.4
    elif scenario in ("SELLERS_TRAPPED_CONTINUATION_LONG", "POST_SWEEP_RECLAIM_LONG", "LIQUIDITY_GRAB_CONTINUATION_LONG"):
        long_score += 0.4
        special_setup = scenario
        trap_indicators += 1
    elif scenario in ("BUYERS_TRAPPED_CONTINUATION_SHORT", "POST_SWEEP_REJECTION_SHORT", "LIQUIDITY_GRAB_CONTINUATION_SHORT"):
        short_score += 0.4
        special_setup = scenario
        trap_indicators += 1

    # Flow confirmation alignment
    if flow_confirmation == "CONFIRMED_LONG":
        long_score += 0.2
    elif flow_confirmation == "CONFIRMED_SHORT":
        short_score += 0.2
    elif flow_confirmation == "CONFLICTED":
        conflict_reason_codes.append("FLOW_CONFIRMATION_CONFLICTED")

    # Post-liquidity reaction alignment
    if post_liquidity_reaction in ("CONTINUATION_AFTER_SWEEP", "REAL_BREAKOUT", "RECLAIM_AFTER_SWEEP"):
        long_score += 0.15 if flow_confirmation != "CONFIRMED_SHORT" else -0.1
    elif post_liquidity_reaction in ("REVERSAL_AFTER_SWEEP", "REJECTION_AFTER_SWEEP"):
        short_score += 0.15 if flow_confirmation != "CONFIRMED_LONG" else -0.1

    # Trap state
    if trap_state == "BUYERS_TRAPPED":
        short_score += 0.2
        trap_indicators += 1
    elif trap_state == "SELLERS_TRAPPED":
        long_score += 0.2
        trap_indicators += 1

    # Absorption state
    if absorption_state == "BUY_ABSORPTION" and flow_confirmation != "CONFIRMED_LONG":
        long_score -= 0.1
    elif absorption_state == "SELL_ABSORPTION" and flow_confirmation != "CONFIRMED_SHORT":
        short_score -= 0.1

    # Liquidity pressure alignment
    if "BUY" in liq_pressure or liq_pressure == "UPSIDE":
        long_score += 0.1
    elif "SELL" in liq_pressure or liq_pressure == "DOWNSIDE":
        short_score += 0.1

    # Range mode handling
    if market_regime == "RANGE":
        if scenario == "RANGE_ROTATION_UP":
            long_score += 0.15
        elif scenario == "RANGE_ROTATION_DOWN":
            short_score += 0.15

    # Compression mode handling
    if market_regime == "COMPRESSION":
        if scenario == "COMPRESSION_BREAKOUT_UP":
            long_score += 0.15
        elif scenario == "COMPRESSION_BREAKOUT_DOWN":
            short_score += 0.15

    # Determine setup candidate
    long_dominant = long_score > short_score
    short_dominant = short_score > long_score

    # Special trap setups take priority
    if special_setup:
        if special_setup in ("POST_SWEEP_RECLAIM_LONG", "LIQUIDITY_GRAB_CONTINUATION_LONG", "SELLERS_TRAPPED_CONTINUATION_LONG"):
            setup_candidate = "SELLERS_TRAPPED_LONG_SETUP" if scenario_bias == "LONG" else "POST_SWEEP_RECLAIM_LONG_SETUP"
            if special_setup == "POST_SWEEP_RECLAIM_LONG":
                setup_candidate = "POST_SWEEP_RECLAIM_LONG_SETUP"
            setup_direction = "LONG"
            setup_confidence = min(1.0, scenario_conf + flow_conf) / 2.0
            setup_quality = "B" if setup_confidence >= 0.6 else "C"
            setup_reason_codes.append(f"{special_setup}_DETECTED")
        elif special_setup in ("POST_SWEEP_REJECTION_SHORT", "LIQUIDITY_GRAB_CONTINUATION_SHORT", "BUYERS_TRAPPED_CONTINUATION_SHORT"):
            setup_candidate = "BUYERS_TRAPPED_SHORT_SETUP" if scenario_bias == "SHORT" else "POST_SWEEP_REJECTION_SHORT_SETUP"
            if special_setup == "POST_SWEEP_REJECTION_SHORT":
                setup_candidate = "POST_SWEEP_REJECTION_SHORT_SETUP"
            setup_direction = "SHORT"
            setup_confidence = min(1.0, scenario_conf + flow_conf) / 2.0
            setup_quality = "B" if setup_confidence >= 0.6 else "C"
            setup_reason_codes.append(f"{special_setup}_DETECTED")
        elif scenario_bias == "SHORT" and trap_indicators > 0:
            setup_candidate = "BUYERS_TRAPPED_SHORT_SETUP"
            setup_direction = "SHORT"
            setup_confidence = min(1.0, scenario_conf + flow_conf) / 2.0
            setup_quality = "B" if setup_confidence >= 0.6 else "C"
            setup_reason_codes.append("BUYERS_TRAPPED_SETUP_DETECTED")
        elif scenario_bias == "LONG" and trap_indicators > 0:
            setup_candidate = "SELLERS_TRAPPED_LONG_SETUP"
            setup_direction = "LONG"
            setup_confidence = min(1.0, scenario_conf + flow_conf) / 2.0
            setup_quality = "B" if setup_confidence >= 0.6 else "C"
            setup_reason_codes.append("SELLERS_TRAPPED_SETUP_DETECTED")

    # Check for conflict between scenario_bias and flow_confirmation
    if not special_setup and flow_confirmation in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
        scenario_opposes_flow = (
            (scenario_bias == "LONG" and flow_confirmation == "CONFIRMED_SHORT") or
            (scenario_bias == "SHORT" and flow_confirmation == "CONFIRMED_LONG")
        )
        if scenario_opposes_flow:
            setup_candidate = "CONFLICTED_SETUP"
            setup_direction = "NEUTRAL"
            setup_quality = "INVALID"
            setup_confidence = 0.0
            conflict_reason_codes.append("SCENARIO_BIAS_FLOW_MISMATCH")
            setup_reason_codes.append("CONFLICTED_SETUP_SCENARIO_FLOW_OPPOSITE")
            return {
                "setup_candidate": setup_candidate,
                "setup_direction": setup_direction,
                "setup_quality": setup_quality,
                "setup_confidence": setup_confidence,
                "setup_reason_codes": setup_reason_codes,
                "conflict_reason_codes": conflict_reason_codes,
                "missing_evidence": missing_evidence,
                "evidence_dict": evidence_dict,
            }

    # Continuation setups
    if not special_setup:
        if scenario in ("BULLISH_CONTINUATION",) and long_dominant and scenario_conf >= 0.5:
            setup_candidate = "LONG_CONTINUATION_SETUP"
            setup_direction = "LONG"
            setup_confidence = scenario_conf * 0.7 + flow_conf * 0.3
            setup_quality = "A" if setup_confidence >= 0.7 else ("B" if setup_confidence >= 0.5 else "C")
            setup_reason_codes.append("BULLISH_CONTINUATION_SCENARIO_LONG_FLOW")
        elif scenario in ("BEARISH_CONTINUATION",) and short_dominant and scenario_conf >= 0.5:
            setup_candidate = "SHORT_CONTINUATION_SETUP"
            setup_direction = "SHORT"
            setup_confidence = scenario_conf * 0.7 + flow_conf * 0.3
            setup_quality = "A" if setup_confidence >= 0.7 else ("B" if setup_confidence >= 0.5 else "C")
            setup_reason_codes.append("BEARISH_CONTINUATION_SCENARIO_SHORT_FLOW")

        # Reversal setups
        elif scenario in ("BULLISH_REVERSAL", "POST_SWEEP_RECLAIM_LONG") and long_dominant:
            setup_candidate = "LONG_REVERSAL_SETUP"
            setup_direction = "LONG"
            setup_confidence = scenario_conf * 0.6 + flow_conf * 0.4
            setup_quality = "B" if setup_confidence >= 0.55 else "C"
            setup_reason_codes.append("BULLISH_REVERSAL_SCENARIO")
        elif scenario in ("BEARISH_REVERSAL", "POST_SWEEP_REJECTION_SHORT") and short_dominant:
            setup_candidate = "SHORT_REVERSAL_SETUP"
            setup_direction = "SHORT"
            setup_confidence = scenario_conf * 0.6 + flow_conf * 0.4
            setup_quality = "B" if setup_confidence >= 0.55 else "C"
            setup_reason_codes.append("BEARISH_REVERSAL_SCENARIO")

        # Range setups
        elif scenario == "RANGE_ROTATION_UP" and long_dominant:
            setup_candidate = "RANGE_LONG_SETUP"
            setup_direction = "LONG"
            setup_confidence = scenario_conf * 0.5 + flow_conf * 0.3
            setup_quality = "B" if setup_confidence >= 0.5 else "C"
            setup_reason_codes.append("RANGE_ROTATION_UP_SCENARIO")
        elif scenario == "RANGE_ROTATION_DOWN" and short_dominant:
            setup_candidate = "RANGE_SHORT_SETUP"
            setup_direction = "SHORT"
            setup_confidence = scenario_conf * 0.5 + flow_conf * 0.3
            setup_quality = "B" if setup_confidence >= 0.5 else "C"
            setup_reason_codes.append("RANGE_ROTATION_DOWN_SCENARIO")

        # Compression breakout setups
        elif scenario == "COMPRESSION_BREAKOUT_UP" and long_dominant:
            setup_candidate = "COMPRESSION_BREAKOUT_LONG_SETUP"
            setup_direction = "LONG"
            setup_confidence = scenario_conf * 0.65 + flow_conf * 0.35
            setup_quality = "B" if setup_confidence >= 0.6 else "C"
            setup_reason_codes.append("COMPRESSION_BREAKOUT_UP_SCENARIO")
        elif scenario == "COMPRESSION_BREAKOUT_DOWN" and short_dominant:
            setup_candidate = "COMPRESSION_BREAKOUT_SHORT_SETUP"
            setup_direction = "SHORT"
            setup_confidence = scenario_conf * 0.65 + flow_conf * 0.35
            setup_quality = "B" if setup_confidence >= 0.6 else "C"
            setup_reason_codes.append("COMPRESSION_BREAKOUT_DOWN_SCENARIO")

        # Default NO_SETUP
        elif abs(long_score - short_score) < 0.2:
            setup_candidate = "CONFLICTED_SETUP"
            setup_direction = "NEUTRAL"
            setup_quality = "INVALID"
            setup_confidence = 0.0
            conflict_reason_codes.append("LONG_SHORT_SCORES_TOO_CLOSE")
            setup_reason_codes.append("CONFLICTED_SETUP_NO_CLEAR_DIRECTION")
        else:
            setup_candidate = "NO_SETUP"
            setup_direction = "NO_TRADE"
            setup_quality = "INVALID"
            setup_confidence = 0.0
            setup_reason_codes.append("NO_SETUP_INSUFFICIENT_ALIGNMENT")

    setup_confidence = round(setup_confidence, 4)
    return {
        "setup_candidate": setup_candidate,
        "setup_direction": setup_direction,
        "setup_quality": setup_quality,
        "setup_confidence": setup_confidence,
        "setup_reason_codes": setup_reason_codes,
        "conflict_reason_codes": conflict_reason_codes,
        "missing_evidence": missing_evidence,
        "evidence_dict": evidence_dict,
        "long_score": round(long_score, 4),
        "short_score": round(short_score, 4),
    }
