from __future__ import annotations

from typing import Any

from .active_scenario_registry import ACTIVE_SCENARIOS


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _tokenize(payload: Any) -> list[str]:
    out: list[str] = []
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for v in item.values():
                stack.append(v)
        elif isinstance(item, list):
            for v in item:
                stack.append(v)
        elif isinstance(item, str):
            out.append(item.upper())
    return out


def _contains_any(tokens: list[str], needles: tuple[str, ...]) -> bool:
    return any(any(n in tok for n in needles) for tok in tokens)


def _extract_reaction_flags(evidence: dict[str, Any]) -> dict[str, bool]:
    tokens = _tokenize(evidence)
    reaction_evidence = evidence.get("reaction_evidence") if isinstance(evidence, dict) else {}
    if not isinstance(reaction_evidence, dict):
        reaction_evidence = {}
    return {
        "downside_sweep": bool(reaction_evidence.get("downside_sweep")) or _contains_any(tokens, ("DOWNSIDE_SWEEP", "SWEEP_DOWN", "STOP_RUN_DOWN", "LIQUIDITY_BELOW_TAKEN")),
        "upside_sweep": bool(reaction_evidence.get("upside_sweep")) or _contains_any(tokens, ("UPSIDE_SWEEP", "SWEEP_UP", "STOP_RUN_UP", "LIQUIDITY_ABOVE_TAKEN")),
        "reclaim": bool(reaction_evidence.get("reclaim")) or _contains_any(tokens, ("RECLAIM", "RE-ACCEPTED", "ACCEPTED_AFTER_SWEEP")),
        "rejection": bool(reaction_evidence.get("rejection")) or _contains_any(tokens, ("REJECTION", "FAILED_RECLAIM", "REJECTED_AFTER_SWEEP")),
        "buy_absorption": bool(reaction_evidence.get("buy_absorption")) or _contains_any(tokens, ("BUY_ABSORPTION", "ABSORPTION_BUY")),
        "sell_absorption": bool(reaction_evidence.get("sell_absorption")) or _contains_any(tokens, ("SELL_ABSORPTION", "ABSORPTION_SELL")),
        "buy_pressure_failed": bool(reaction_evidence.get("buy_pressure_failed")) or _contains_any(tokens, ("BUY_PRESSURE_FAILED", "BUYER_EXHAUSTION", "DELTA_BUY_FAILURE")),
        "sell_pressure_failed": bool(reaction_evidence.get("sell_pressure_failed")) or _contains_any(tokens, ("SELL_PRESSURE_FAILED", "SELLER_EXHAUSTION", "DELTA_SELL_FAILURE")),
        "buy_reaction": bool(reaction_evidence.get("buy_reaction")) or _contains_any(tokens, ("BUY_REACTION", "BUY_PRESSURE_RETURNED")),
        "sell_reaction": bool(reaction_evidence.get("sell_reaction")) or _contains_any(tokens, ("SELL_REACTION", "SELL_PRESSURE_RETURNED")),
        "liquidity_above_taken": bool(reaction_evidence.get("liquidity_above_taken")) or _contains_any(tokens, ("LIQUIDITY_ABOVE_TAKEN", "SWEEP_UP", "STOP_RUN_UP")),
        "liquidity_below_taken": bool(reaction_evidence.get("liquidity_below_taken")) or _contains_any(tokens, ("LIQUIDITY_BELOW_TAKEN", "SWEEP_DOWN", "STOP_RUN_DOWN")),
        "compressing_to_expanding": bool(reaction_evidence.get("compressing_to_expanding")) or _contains_any(tokens, ("COMPRESSING_TO_EXPANDING", "SQUEEZE_RELEASE")),
    }


def build_feature_frame(evidence: dict[str, Any]) -> dict[str, Any]:
    ms = evidence.get("market_state_evidence") if isinstance(evidence, dict) else {}
    liq = evidence.get("liquidity_evidence") if isinstance(evidence, dict) else {}
    st = evidence.get("structure_evidence") if isinstance(evidence, dict) else {}
    flow = evidence.get("flow_evidence") if isinstance(evidence, dict) else {}
    risk = evidence.get("risk_evidence") if isinstance(evidence, dict) else {}
    if not isinstance(ms, dict):
        ms = {}
    if not isinstance(liq, dict):
        liq = {}
    if not isinstance(st, dict):
        st = {}
    if not isinstance(flow, dict):
        flow = {}
    if not isinstance(risk, dict):
        risk = {}

    liq_tokens = _tokenize(liq)
    st_tokens = _tokenize(st)
    flow_tokens = _tokenize(flow)
    ms_tokens = _tokenize(ms)
    all_tokens = liq_tokens + st_tokens + flow_tokens + ms_tokens
    reaction_flags = _extract_reaction_flags(evidence)

    market_regime = str(ms.get("market_regime") or "UNKNOWN").upper()
    trend_state = str(ms.get("trend_state") or "UNKNOWN").upper()
    volatility_state = str(ms.get("volatility_state") or "UNKNOWN").upper()
    structure_state = str(ms.get("structure_state") or "UNKNOWN").upper()
    liquidity_pressure_state = str(ms.get("liquidity_pressure_state") or "UNKNOWN").upper()
    flow_state = str(ms.get("flow_state") or "UNKNOWN").upper()
    maturity_state = str(ms.get("maturity_state") or "UNKNOWN").upper()
    risk_state = str(ms.get("risk_state") or "UNKNOWN").upper()

    if structure_state == "UNKNOWN":
        if _contains_any(st_tokens, ("HH_HL", "HH", "HL")):
            structure_state = "HH_HL"
        elif _contains_any(st_tokens, ("LH_LL", "LH", "LL")):
            structure_state = "LH_LL"
        elif _contains_any(st_tokens, ("RANGE", "RANGE_BOUND")):
            structure_state = "RANGE_BOUND"
        elif _contains_any(st_tokens, ("BROKEN", "CHOCH", "MSS")):
            structure_state = "BROKEN_STRUCTURE"

    if liquidity_pressure_state == "UNKNOWN":
        above = _contains_any(liq_tokens, ("ABOVE", "PREMIUM", "ASK"))
        below = _contains_any(liq_tokens, ("BELOW", "DISCOUNT", "BID"))
        both = _contains_any(liq_tokens, ("BOTH", "BALANCED_LIQUIDITY"))
        if both or (above and below):
            liquidity_pressure_state = "BOTH"
        elif above:
            liquidity_pressure_state = "ABOVE"
        elif below:
            liquidity_pressure_state = "BELOW"

    if flow_state == "UNKNOWN":
        if _contains_any(flow_tokens, ("DIVERGENT", "DIVERGENCE")):
            flow_state = "DIVERGENT"
        elif _contains_any(flow_tokens, ("BUY_PRESSURE", "LONG_PRESSURE", "DOMINANT_BUY")):
            flow_state = "BUY_PRESSURE"
        elif _contains_any(flow_tokens, ("SELL_PRESSURE", "SHORT_PRESSURE", "DOMINANT_SELL")):
            flow_state = "SELL_PRESSURE"
        elif _contains_any(flow_tokens, ("BALANCED", "CHOPPY", "NEUTRAL")):
            flow_state = "BALANCED"

    if market_regime == "UNKNOWN":
        if _contains_any(ms_tokens, ("UPTREND", "TREND_UP")):
            market_regime = "UPTREND"
        elif _contains_any(ms_tokens, ("DOWNTREND", "TREND_DOWN")):
            market_regime = "DOWNTREND"
        elif _contains_any(ms_tokens, ("COMPRESSION",)):
            market_regime = "COMPRESSION"
        elif _contains_any(ms_tokens, ("EXPANSION", "EXPANDING")):
            market_regime = "EXPANSION"
        elif _contains_any(ms_tokens, ("RANGE", "BALANCE_MODE")):
            market_regime = "RANGE"

    if trend_state == "UNKNOWN":
        if structure_state == "HH_HL":
            trend_state = "BULLISH"
        elif structure_state == "LH_LL":
            trend_state = "BEARISH"
        elif structure_state == "RANGE_BOUND":
            trend_state = "NEUTRAL"

    if risk_state == "UNKNOWN":
        if _contains_any(all_tokens, ("NO_TRADE", "INVALID")):
            risk_state = "NO_TRADE"
        elif _contains_any(all_tokens, ("HIGH_RISK", "RISK_HIGH")):
            risk_state = "HIGH"
        elif _contains_any(all_tokens, ("RISK_LOW",)):
            risk_state = "LOW"
        else:
            risk_state = "MEDIUM"

    return {
        "market_regime": market_regime,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure_state,
        "liquidity_pressure_state": liquidity_pressure_state,
        "flow_state": flow_state,
        "maturity_state": maturity_state,
        "risk_state": risk_state,
        "reaction": reaction_flags,
    }


def _base_candidate(
    scenario: str,
    bias: str,
    components: dict[str, float],
    supporting: list[str],
    opposing: list[str],
    missing: list[str],
    evidence_snapshot: dict[str, Any],
) -> dict[str, Any]:
    raw_score = (
        components["market_state_alignment"]
        + components["liquidity_alignment"]
        + components["structure_alignment"]
        + components["flow_alignment"]
        + components["reaction_alignment"]
        - components["conflict_penalty"]
        - components["data_quality_penalty"]
        - components["late_maturity_penalty"]
    )
    normalized = _clamp((raw_score + 2.0) / 7.0)
    return {
        "scenario": scenario,
        "bias": bias,
        "raw_score": round(raw_score, 4),
        "normalized_score": round(normalized, 4),
        "supporting_reason_codes": sorted(set(supporting)),
        "opposing_reason_codes": sorted(set(opposing)),
        "required_evidence_present": len(missing) == 0,
        "missing_evidence": sorted(set(missing)),
        "evidence_snapshot": evidence_snapshot,
        "candidate_scores": {
            "market_state_alignment": round(components["market_state_alignment"], 4),
            "liquidity_alignment": round(components["liquidity_alignment"], 4),
            "structure_alignment": round(components["structure_alignment"], 4),
            "flow_alignment": round(components["flow_alignment"], 4),
            "reaction_alignment": round(components["reaction_alignment"], 4),
            "conflict_penalty": round(components["conflict_penalty"], 4),
            "data_quality_penalty": round(components["data_quality_penalty"], 4),
            "late_maturity_penalty": round(components["late_maturity_penalty"], 4),
        },
    }


def _scenario_rule(scenario: str, f: dict[str, Any], data_quality: str) -> dict[str, Any]:
    rg = f["market_regime"]
    tr = f["trend_state"]
    vol = f["volatility_state"]
    st = f["structure_state"]
    lp = f["liquidity_pressure_state"]
    fl = f["flow_state"]
    mt = f["maturity_state"]
    rk = f["risk_state"]
    re = f["reaction"]

    components = {
        "market_state_alignment": 0.0,
        "liquidity_alignment": 0.0,
        "structure_alignment": 0.0,
        "flow_alignment": 0.0,
        "reaction_alignment": 0.0,
        "conflict_penalty": 0.0,
        "data_quality_penalty": 0.0,
        "late_maturity_penalty": 0.0,
    }
    support: list[str] = []
    oppose: list[str] = []
    missing: list[str] = []

    if data_quality in ("DEGRADED", "INVALID", "UNKNOWN"):
        components["data_quality_penalty"] += 0.35
        oppose.append("DATA_QUALITY_PENALTY")
    if mt in ("LATE", "EXHAUSTED"):
        components["late_maturity_penalty"] += 0.2
        oppose.append("LATE_MATURITY_PENALTY")

    bias = "UNKNOWN"

    if scenario == "BULLISH_CONTINUATION":
        bias = "LONG"
        if rg in ("UPTREND", "EXPANSION"):
            components["market_state_alignment"] += 1.0
            support.append("REGIME_SUPPORTS_BULLISH_CONTINUATION")
        else:
            missing.append("market_regime")
        if tr == "BULLISH":
            components["structure_alignment"] += 0.9
            support.append("TREND_BULLISH")
        if fl == "BUY_PRESSURE":
            components["flow_alignment"] += 0.9
            support.append("FLOW_BUY_PRESSURE")
        if st == "HH_HL":
            components["structure_alignment"] += 0.9
            support.append("STRUCTURE_HH_HL")
        if lp in ("ABOVE", "BOTH"):
            components["liquidity_alignment"] += 0.7
            support.append("LIQUIDITY_UPSIDE")
        if rk in ("HIGH", "NO_TRADE"):
            components["conflict_penalty"] += 0.6
            oppose.append("RISK_BLOCKS_BULLISH_CONTINUATION")

    elif scenario == "BEARISH_CONTINUATION":
        bias = "SHORT"
        if rg in ("DOWNTREND", "EXPANSION"):
            components["market_state_alignment"] += 1.0
            support.append("REGIME_SUPPORTS_BEARISH_CONTINUATION")
        else:
            missing.append("market_regime")
        if tr == "BEARISH":
            components["structure_alignment"] += 0.9
            support.append("TREND_BEARISH")
        if fl == "SELL_PRESSURE":
            components["flow_alignment"] += 0.9
            support.append("FLOW_SELL_PRESSURE")
        if st == "LH_LL":
            components["structure_alignment"] += 0.9
            support.append("STRUCTURE_LH_LL")
        if lp in ("BELOW", "BOTH"):
            components["liquidity_alignment"] += 0.7
            support.append("LIQUIDITY_DOWNSIDE")
        if rk in ("HIGH", "NO_TRADE"):
            components["conflict_penalty"] += 0.6
            oppose.append("RISK_BLOCKS_BEARISH_CONTINUATION")

    elif scenario == "RANGE_ROTATION_UP":
        bias = "LONG"
        if rg == "RANGE":
            components["market_state_alignment"] += 1.0
            support.append("REGIME_RANGE")
        if lp in ("BELOW", "BOTH"):
            components["liquidity_alignment"] += 0.8
            support.append("LIQUIDITY_BELOW_OR_BOTH")
        if fl in ("BUY_PRESSURE", "DIVERGENT"):
            components["flow_alignment"] += 0.8
            support.append("FLOW_BUY_OR_DIVERGENT")

    elif scenario == "RANGE_ROTATION_DOWN":
        bias = "SHORT"
        if rg == "RANGE":
            components["market_state_alignment"] += 1.0
            support.append("REGIME_RANGE")
        if lp in ("ABOVE", "BOTH"):
            components["liquidity_alignment"] += 0.8
            support.append("LIQUIDITY_ABOVE_OR_BOTH")
        if fl in ("SELL_PRESSURE", "DIVERGENT"):
            components["flow_alignment"] += 0.8
            support.append("FLOW_SELL_OR_DIVERGENT")

    elif scenario == "COMPRESSION_BREAKOUT_UP":
        bias = "LONG"
        if rg == "COMPRESSION":
            components["market_state_alignment"] += 1.0
            support.append("REGIME_COMPRESSION")
        if vol == "EXPANDING" or re["compressing_to_expanding"]:
            components["reaction_alignment"] += 0.8
            support.append("VOLATILITY_EXPANDING_AFTER_COMPRESSION")
        if fl == "BUY_PRESSURE":
            components["flow_alignment"] += 0.8
            support.append("FLOW_BUY_PRESSURE")
        if lp in ("ABOVE", "BOTH"):
            components["liquidity_alignment"] += 0.8
            support.append("LIQUIDITY_UPSIDE_TARGET")

    elif scenario == "COMPRESSION_BREAKOUT_DOWN":
        bias = "SHORT"
        if rg == "COMPRESSION":
            components["market_state_alignment"] += 1.0
            support.append("REGIME_COMPRESSION")
        if vol == "EXPANDING" or re["compressing_to_expanding"]:
            components["reaction_alignment"] += 0.8
            support.append("VOLATILITY_EXPANDING_AFTER_COMPRESSION")
        if fl == "SELL_PRESSURE":
            components["flow_alignment"] += 0.8
            support.append("FLOW_SELL_PRESSURE")
        if lp in ("BELOW", "BOTH"):
            components["liquidity_alignment"] += 0.8
            support.append("LIQUIDITY_DOWNSIDE_TARGET")

    elif scenario == "BUYERS_TRAPPED_CONTINUATION_SHORT":
        bias = "SHORT"
        if lp == "ABOVE" or re["liquidity_above_taken"]:
            components["liquidity_alignment"] += 1.0
            support.append("LIQUIDITY_ABOVE_TAKEN")
        if re["buy_pressure_failed"]:
            components["reaction_alignment"] += 0.9
            support.append("BUY_PRESSURE_FAILED")
        if st in ("LH_LL", "BROKEN_STRUCTURE") or re["rejection"]:
            components["structure_alignment"] += 0.8
            support.append("BEARISH_STRUCTURE_OR_REJECTION")
        if fl in ("SELL_PRESSURE", "DIVERGENT"):
            components["flow_alignment"] += 0.7
            support.append("FLOW_SELL_OR_DIVERGENT")

    elif scenario == "SELLERS_TRAPPED_CONTINUATION_LONG":
        bias = "LONG"
        if lp == "BELOW" or re["liquidity_below_taken"]:
            components["liquidity_alignment"] += 1.0
            support.append("LIQUIDITY_BELOW_TAKEN")
        if re["sell_pressure_failed"]:
            components["reaction_alignment"] += 0.9
            support.append("SELL_PRESSURE_FAILED")
        if st in ("HH_HL", "BROKEN_STRUCTURE") or re["reclaim"]:
            components["structure_alignment"] += 0.8
            support.append("BULLISH_STRUCTURE_OR_RECLAIM")
        if fl in ("BUY_PRESSURE", "DIVERGENT"):
            components["flow_alignment"] += 0.7
            support.append("FLOW_BUY_OR_DIVERGENT")

    elif scenario == "POST_SWEEP_RECLAIM_LONG":
        bias = "LONG"
        if re["downside_sweep"]:
            components["liquidity_alignment"] += 1.0
            support.append("DOWNSIDE_SWEEP")
        if re["reclaim"]:
            components["reaction_alignment"] += 0.9
            support.append("RECLAIM_EVIDENCE")
        if re["sell_absorption"]:
            components["reaction_alignment"] += 0.6
            support.append("SELL_ABSORPTION")
        if re["buy_reaction"]:
            components["flow_alignment"] += 0.6
            support.append("BUY_REACTION")

    elif scenario == "POST_SWEEP_REJECTION_SHORT":
        bias = "SHORT"
        if re["upside_sweep"]:
            components["liquidity_alignment"] += 1.0
            support.append("UPSIDE_SWEEP")
        if re["rejection"]:
            components["reaction_alignment"] += 0.9
            support.append("REJECTION_EVIDENCE")
        if re["buy_absorption"]:
            components["reaction_alignment"] += 0.6
            support.append("BUY_ABSORPTION")
        if re["sell_reaction"]:
            components["flow_alignment"] += 0.6
            support.append("SELL_REACTION")

    elif scenario in ("BULLISH_REVERSAL", "LIQUIDITY_SWEEP_REVERSAL_LONG", "LIQUIDITY_GRAB_CONTINUATION_LONG"):
        bias = "LONG"
        if mt in ("LATE", "EXHAUSTED") or re["downside_sweep"]:
            components["market_state_alignment"] += 0.7
            support.append("REVERSAL_LONG_SETUP")
        if fl in ("BUY_PRESSURE", "DIVERGENT"):
            components["flow_alignment"] += 0.6
            support.append("FLOW_SUPPORT_LONG_REVERSAL")

    elif scenario in ("BEARISH_REVERSAL", "LIQUIDITY_SWEEP_REVERSAL_SHORT", "LIQUIDITY_GRAB_CONTINUATION_SHORT"):
        bias = "SHORT"
        if mt in ("LATE", "EXHAUSTED") or re["upside_sweep"]:
            components["market_state_alignment"] += 0.7
            support.append("REVERSAL_SHORT_SETUP")
        if fl in ("SELL_PRESSURE", "DIVERGENT"):
            components["flow_alignment"] += 0.6
            support.append("FLOW_SUPPORT_SHORT_REVERSAL")

    else:
        bias = "UNKNOWN"
        missing.append("unsupported_scenario_rule")

    if not support:
        missing.append("INSUFFICIENT_EVIDENCE")
        oppose.append("NO_STRONG_SUPPORT")

    return _base_candidate(
        scenario=scenario,
        bias=bias,
        components=components,
        supporting=support,
        opposing=oppose,
        missing=missing,
        evidence_snapshot={
            "market_regime": rg,
            "trend_state": tr,
            "volatility_state": vol,
            "structure_state": st,
            "liquidity_pressure_state": lp,
            "flow_state": fl,
            "maturity_state": mt,
            "risk_state": rk,
            "reaction_flags": re,
        },
    )


def build_scenario_candidates(evidence: dict[str, Any], data_quality: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frame = build_feature_frame(evidence)
    scenario_candidates: list[dict[str, Any]] = []
    for scenario in ACTIVE_SCENARIOS:
        if scenario in ("NO_ACTIVE_SCENARIO", "CONFLICTED_SCENARIO", "UNKNOWN"):
            continue
        scenario_candidates.append(_scenario_rule(scenario=scenario, f=frame, data_quality=data_quality))
    return scenario_candidates, frame

