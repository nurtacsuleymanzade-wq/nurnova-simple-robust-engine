"""S6 Scenario + Setup Candidate — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.simple.lineage_event_logger import stable_id

BLOCK_ID = "S6_SCENARIO_SETUP_CANDIDATE"
FEEDS_NEXT = {"next_blocks": ["SIGNAL_EVENT_CONSOLIDATOR"]}

_FAKE_S1: dict[str, Any] = {
    "available": True,
    "current_price": 105000.0,
    "is_official_binance_1m": True,
}

_FAKE_S2: dict[str, Any] = {
    "available": True,
    "evidence_label": "LONG_PRESSURE",
    "micro_winner": "LONG",
    "evidence_score": 6.2105,
}

_FAKE_S3: dict[str, Any] = {
    "available": True,
    "candle_direction": "BULLISH",
    "intent_label": "BUY_PRESSURE_CONFIRMED",
    "intent_score": 0.621053,
    "shape_label": "BULLISH_SPINNING_TOP",
}

_FAKE_S4: dict[str, Any] = {
    "available": True,
    "quality_weight": 0.9513,
    "quality_label": "HIGH_QUALITY",
}

_FAKE_S5: dict[str, Any] = {
    "available": True,
    "structure_bias": "BULLISH",
    "structure_event": "RANGE_BALANCE",
    "structure_score": 0.4259,
    "draw_on_liquidity": "ABOVE",
    "liquidity_context_label": "BUY_SIDE_NEAR",
    "liquidity_score": 0.4259,
    "context_label": "BULLISH_CONTEXT",
    "context_score": 76.1,
    "usable_for_setup_candidate": True,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_input_status(
    s1: dict[str, Any] | None,
    s2: dict[str, Any] | None,
    s3: dict[str, Any] | None,
    s4: dict[str, Any] | None,
    s5: dict[str, Any] | None,
) -> dict[str, Any]:
    mt = s1 is not None and bool(s1.get("available", False))
    ev = s2 is not None and bool(s2.get("available", False))
    hc = s3 is not None and bool(s3.get("available", False))
    qw = s4 is not None and bool(s4.get("available", False))
    ls = s5 is not None and bool(s5.get("available", False))
    missing: list[str] = []
    if not mt:
        missing.append("S1_MARKET_TRUTH")
    if not ev:
        missing.append("S2_EVIDENCE")
    if not hc:
        missing.append("S3_HYBRID_CANDLE")
    if not qw:
        missing.append("S4_QUALITY_WEIGHT")
    if not ls:
        missing.append("S5_LIQUIDITY_STRUCTURE")
    return {
        "market_truth_available": mt,
        "evidence_available": ev,
        "hybrid_candle_available": hc,
        "quality_weight_available": qw,
        "liquidity_structure_available": ls,
        "missing_inputs": missing,
    }


def _is_official_candle_valid(s1: dict[str, Any] | None) -> bool:
    if s1 is None or not s1.get("available"):
        return False
    return bool(s1.get("is_official_binance_1m", False))


def _direction_from_flow(s2: dict[str, Any] | None) -> str:
    if s2 is None or not s2.get("available"):
        return "UNKNOWN"
    mw = str(s2.get("micro_winner", "UNKNOWN")).upper()
    if mw == "LONG":
        return "LONG"
    if mw == "SHORT":
        return "SHORT"
    return "NEUTRAL"


def _direction_from_candle(s3: dict[str, Any] | None) -> str:
    if s3 is None or not s3.get("available"):
        return "UNKNOWN"
    cd = str(s3.get("candle_direction", "UNKNOWN")).upper()
    if cd == "BULLISH":
        return "LONG"
    if cd == "BEARISH":
        return "SHORT"
    return "NEUTRAL"


def _direction_from_structure(s5: dict[str, Any] | None) -> str:
    if s5 is None or not s5.get("available"):
        return "UNKNOWN"
    sb = str(s5.get("structure_bias", "UNKNOWN")).upper()
    if sb == "BULLISH":
        return "LONG"
    if sb == "BEARISH":
        return "SHORT"
    if sb == "RANGE":
        return "NEUTRAL"
    return "UNKNOWN"


def _direction_from_liquidity(s5: dict[str, Any] | None) -> str:
    if s5 is None or not s5.get("available"):
        return "UNKNOWN"
    dl = str(s5.get("draw_on_liquidity", "UNKNOWN")).upper()
    if dl == "ABOVE":
        return "LONG"
    if dl == "BELOW":
        return "SHORT"
    if dl == "BOTH":
        return "NEUTRAL"
    return "UNKNOWN"


def _calc_evidence_alignment(
    s2: dict[str, Any] | None,
    s3: dict[str, Any] | None,
    s5: dict[str, Any] | None,
) -> dict[str, Any]:
    flow = _direction_from_flow(s2)
    candle = _direction_from_candle(s3)
    structure = _direction_from_structure(s5)
    liquidity = _direction_from_liquidity(s5)

    dirs = [flow, candle, structure, liquidity]
    long_count = sum(1 for d in dirs if d == "LONG")
    short_count = sum(1 for d in dirs if d == "SHORT")
    unknown_count = sum(1 for d in dirs if d == "UNKNOWN")

    if unknown_count >= 3:
        label = "UNKNOWN"
        score = 0.0
    elif long_count >= 3 and short_count == 0:
        label = "ALIGNED_LONG"
        score = round(long_count / 4.0, 4)
    elif short_count >= 3 and long_count == 0:
        label = "ALIGNED_SHORT"
        score = round(short_count / 4.0, 4)
    elif long_count > 0 and short_count > 0:
        label = "CONFLICTED"
        score = round(min(0.4, 1.0 - abs(long_count - short_count) / 4.0), 4)
    else:
        label = "MIXED"
        dominant = max(long_count, short_count)
        score = round(0.3 + dominant * 0.1, 4)

    return {
        "flow_direction": flow,
        "candle_intent": candle,
        "structure_bias": structure,
        "liquidity_bias": liquidity,
        "alignment_label": label,
        "alignment_score": score,
    }


def _calc_scenario(
    s5: dict[str, Any] | None,
    alignment: dict[str, Any],
) -> dict[str, Any]:
    if s5 is None or not s5.get("available"):
        return {
            "scenario_type": "NO_CLEAR_SCENARIO",
            "scenario_direction": "UNKNOWN",
            "scenario_score": 0.0,
            "scenario_label": "S5_MISSING",
            "scenario_reason": "S5 liquidity/structure context unavailable.",
        }

    label = alignment["alignment_label"]
    structure_bias = str(s5.get("structure_bias", "UNKNOWN")).upper()
    context_score = float(s5.get("context_score", 0.0))

    if label == "UNKNOWN":
        return {
            "scenario_type": "UNKNOWN",
            "scenario_direction": "UNKNOWN",
            "scenario_score": 0.0,
            "scenario_label": "UNKNOWN_INPUTS",
            "scenario_reason": "Insufficient evidence to determine scenario direction.",
        }

    if label == "CONFLICTED":
        return {
            "scenario_type": "NO_CLEAR_SCENARIO",
            "scenario_direction": "NEUTRAL",
            "scenario_score": round(context_score * 0.3, 2),
            "scenario_label": "CONFLICTING_SIGNALS",
            "scenario_reason": "Flow, candle, structure, and liquidity disagree.",
        }

    if structure_bias == "RANGE":
        return {
            "scenario_type": "RANGE_REACTION",
            "scenario_direction": "NEUTRAL",
            "scenario_score": round(context_score * 0.5, 2),
            "scenario_label": "RANGE_BALANCE",
            "scenario_reason": "Structure shows balance — favouring range reactions.",
        }

    if "LONG" in label:
        direction = "LONG"
    elif "SHORT" in label:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    if (direction == "LONG" and structure_bias == "BULLISH") or (
        direction == "SHORT" and structure_bias == "BEARISH"
    ):
        scenario_type = "CONTINUATION"
        scenario_label = f"{direction}_CONTINUATION_WITH_STRUCTURE"
        reason = "Evidence aligned with prevailing structure — continuation."
        score_mult = 1.0
    elif (direction == "LONG" and structure_bias == "BEARISH") or (
        direction == "SHORT" and structure_bias == "BULLISH"
    ):
        scenario_type = "REVERSAL"
        scenario_label = f"{direction}_REVERSAL_AGAINST_STRUCTURE"
        reason = "Evidence opposes structure bias — potential reversal."
        score_mult = 0.7
    else:
        scenario_type = "NO_CLEAR_SCENARIO"
        scenario_label = "STRUCTURE_UNKNOWN"
        reason = "Structure bias unclear."
        score_mult = 0.4

    raw = context_score * float(alignment["alignment_score"]) * score_mult
    return {
        "scenario_type": scenario_type,
        "scenario_direction": direction,
        "scenario_score": round(min(100.0, raw), 2),
        "scenario_label": scenario_label,
        "scenario_reason": reason,
    }


def _calc_setup_candidate(
    scenario: dict[str, Any],
    quality_weight: float,
    official_candle_valid: bool,
) -> dict[str, Any]:
    if not official_candle_valid:
        return {
            "setup_type": "NO_SETUP",
            "setup_direction": "UNKNOWN",
            "raw_setup_score": 0.0,
            "quality_adjusted_setup_score": 0.0,
            "setup_grade": "NO_SETUP",
            "setup_status": "INVALID",
            "setup_reason": "Official candle invalid or missing — cannot generate setup candidate.",
        }

    s_type = scenario["scenario_type"]
    direction = scenario["scenario_direction"]
    raw_score = float(scenario["scenario_score"])

    if s_type in ("NO_CLEAR_SCENARIO", "UNKNOWN"):
        setup_type = "NO_SETUP"
    elif s_type == "RANGE_REACTION":
        setup_type = "RANGE_REACTION"
    elif s_type == "CONTINUATION" and direction == "LONG":
        setup_type = "LONG_CONTINUATION"
    elif s_type == "CONTINUATION" and direction == "SHORT":
        setup_type = "SHORT_CONTINUATION"
    elif s_type == "REVERSAL" and direction == "LONG":
        setup_type = "LONG_REVERSAL"
    elif s_type == "REVERSAL" and direction == "SHORT":
        setup_type = "SHORT_REVERSAL"
    else:
        setup_type = "NO_SETUP"

    qa_score = round(raw_score * float(quality_weight), 2)

    if qa_score >= 85.0:
        grade = "A_PLUS"
    elif qa_score >= 70.0:
        grade = "A"
    elif qa_score >= 55.0:
        grade = "B"
    elif qa_score >= 40.0:
        grade = "C"
    elif qa_score >= 20.0:
        grade = "WATCH"
    else:
        grade = "NO_SETUP"

    if setup_type == "NO_SETUP" or grade == "NO_SETUP":
        status = "NO_SETUP"
        setup_direction = "UNKNOWN"
    elif grade in ("A_PLUS", "A"):
        status = "READY_FOR_PLAN"
        setup_direction = direction
    else:
        status = "WATCH_SETUP"
        setup_direction = direction

    setup_family = setup_type if status != "NO_SETUP" else "NO_SETUP"
    return {
        "setup_family": setup_family,
        "setup_context": scenario.get("scenario_label", "UNKNOWN"),
        "required_conditions": [
            f"alignment={scenario.get('scenario_type', 'UNKNOWN')}",
            f"quality_weight>={quality_weight:.2f}",
        ],
        "invalidation_context": scenario.get("scenario_reason", "UNKNOWN"),
        "setup_type": setup_type if status != "NO_SETUP" else "NO_SETUP",
        "setup_direction": setup_direction,
        "raw_setup_score": round(raw_score, 2),
        "quality_adjusted_setup_score": qa_score,
        "setup_grade": grade,
        "setup_status": status,
        "setup_reason": f"{setup_type} grade={grade} qa_score={qa_score}",
    }


def _calc_quality_context(s4: dict[str, Any] | None) -> dict[str, Any]:
    if s4 is None or not s4.get("available"):
        return {
            "inherited_quality_weight": 0.5,
            "inherited_quality_label": "UNKNOWN",
            "quality_allows_setup_candidate": False,
        }
    qw = float(s4.get("quality_weight", 0.5))
    ql = str(s4.get("quality_label", "UNKNOWN"))
    allows = qw >= 0.2 and ql.upper() not in ("CRITICAL", "INVALID", "UNKNOWN")
    return {
        "inherited_quality_weight": qw,
        "inherited_quality_label": ql,
        "quality_allows_setup_candidate": allows,
    }


def _calc_risk(
    scenario: dict[str, Any],
    alignment: dict[str, Any],
) -> dict[str, Any]:
    label = alignment["alignment_label"]
    s_type = scenario["scenario_type"]

    if label == "UNKNOWN":
        return {
            "setup_risk_label": "INVALID",
            "trap_risk": True,
            "conflict_risk": True,
            "reason": "Unknown evidence alignment — cannot assess risk.",
        }
    if label == "CONFLICTED":
        return {
            "setup_risk_label": "HIGH",
            "trap_risk": True,
            "conflict_risk": True,
            "reason": "Conflicting flow/candle/structure/liquidity signals.",
        }
    if label == "MIXED":
        return {
            "setup_risk_label": "MEDIUM",
            "trap_risk": s_type == "REVERSAL",
            "conflict_risk": False,
            "reason": "Mixed alignment — moderate risk.",
        }
    if s_type == "REVERSAL":
        return {
            "setup_risk_label": "MEDIUM",
            "trap_risk": True,
            "conflict_risk": False,
            "reason": "Aligned reversal against structure — elevated trap risk.",
        }
    return {
        "setup_risk_label": "LOW",
        "trap_risk": False,
        "conflict_risk": False,
        "reason": "Aligned evidence with prevailing structure.",
    }


def _build_data_quality(
    input_status: dict[str, Any],
    s4: dict[str, Any] | None,
) -> dict[str, Any]:
    issues = list(input_status["missing_inputs"])
    if s4 is not None and s4.get("available"):
        base = float(s4.get("quality_weight", 0.5))
    else:
        base = 0.5
    if not input_status["market_truth_available"]:
        base = max(0.0, base - 0.50)
    if not input_status["liquidity_structure_available"]:
        base = max(0.0, base - 0.30)
    if not input_status["hybrid_candle_available"]:
        base = max(0.0, base - 0.15)
    if not input_status["evidence_available"]:
        base = max(0.0, base - 0.10)
    score = round(max(0.0, min(1.0, base)), 4)
    if score >= 0.8:
        level = "HIGH"
    elif score >= 0.5:
        level = "MEDIUM"
    elif score >= 0.2:
        level = "LOW"
    else:
        level = "CRITICAL"
    return {"score": score, "level": level, "issues": issues}


def _build_reason_codes(
    source_mode: str,
    input_status: dict[str, Any],
    alignment: dict[str, Any],
    scenario: dict[str, Any],
    setup: dict[str, Any],
    risk: dict[str, Any],
    data_quality: dict[str, Any],
) -> list[str]:
    codes: list[str] = [f"SOURCE_{source_mode}"]
    for m in input_status["missing_inputs"]:
        codes.append(f"MISSING_{m}")
    codes.append(f"ALIGNMENT_{alignment['alignment_label']}")
    codes.append(f"SCENARIO_{scenario['scenario_type']}")
    codes.append(f"SETUP_{setup['setup_type']}")
    codes.append(f"GRADE_{setup['setup_grade']}")
    codes.append(f"STATUS_{setup['setup_status']}")
    codes.append(f"RISK_{risk['setup_risk_label']}")
    codes.append(f"DATA_QUALITY_{data_quality['level']}")
    return codes


def build_setup_candidate(
    symbol: str,
    s1: dict[str, Any] | None,
    s2: dict[str, Any] | None,
    s3: dict[str, Any] | None,
    s4: dict[str, Any] | None,
    s5: dict[str, Any] | None,
    source_mode: str,
) -> dict[str, Any]:
    timestamp = _utc_now()
    setup_id = stable_id("SETUP", symbol, source_mode, timestamp)
    input_status = _calc_input_status(s1, s2, s3, s4, s5)
    quality_weight = (
        float(s4.get("quality_weight", 0.5))
        if s4 is not None and s4.get("available")
        else 0.5
    )
    official_valid = _is_official_candle_valid(s1)

    alignment = _calc_evidence_alignment(s2, s3, s5)
    scenario = _calc_scenario(s5, alignment)
    setup = _calc_setup_candidate(scenario, quality_weight, official_valid)
    quality_ctx = _calc_quality_context(s4)
    risk = _calc_risk(scenario, alignment)

    if (
        not quality_ctx["quality_allows_setup_candidate"]
        and setup["setup_status"] == "READY_FOR_PLAN"
    ):
        setup["setup_status"] = "WATCH_SETUP"
        setup["setup_reason"] = setup["setup_reason"] + " (quality below threshold)"

    data_quality = _build_data_quality(input_status, s4)
    reason_codes = _build_reason_codes(
        source_mode, input_status, alignment, scenario, setup, risk, data_quality
    )

    return {
        "timestamp_utc": timestamp,
        "block_id": BLOCK_ID,
        "record_type": "setup_candidate",
        "event_id": setup_id,
        "setup_id": setup_id,
        "signal_id": None,
        "plan_id": None,
        "decision_id": None,
        "paper_trade_id": None,
        "outcome_id": None,
        "parent_id": None,
        "blocked_by": [],
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "input_status": input_status,
        "scenario": scenario,
        "setup_candidate": setup,
        "evidence_alignment": alignment,
        "quality_context": quality_ctx,
        "risk": risk,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_setup_candidate(
        symbol, _FAKE_S1, _FAKE_S2, _FAKE_S3, _FAKE_S4, _FAKE_S5, "FAKE_SAMPLE"
    )
