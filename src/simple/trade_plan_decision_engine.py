"""S7 Trade Plan + Decision Gate — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S7_TRADE_PLAN_DECISION_GATE"
FEEDS_NEXT = {"next_blocks": ["S8_PAPER_OUTCOME_TRACKER"]}

_FAKE_S1: dict[str, Any] = {
    "available": True,
    "current_price": 105000.0,
    "is_official_binance_1m": True,
}

_FAKE_S4: dict[str, Any] = {
    "available": True,
    "quality_weight": 0.9513,
    "quality_label": "HIGH_QUALITY",
}

_FAKE_S5: dict[str, Any] = {
    "available": True,
    "nearest_support": 104200.0,
    "nearest_resistance": 105500.0,
    "structure_bias": "BULLISH",
}

_FAKE_S6: dict[str, Any] = {
    "available": True,
    "setup_type": "LONG_CONTINUATION",
    "setup_direction": "LONG",
    "setup_grade": "A",
    "setup_status": "READY_FOR_PLAN",
    "quality_adjusted_setup_score": 72.39,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_input_status(
    s1: dict[str, Any] | None,
    s4: dict[str, Any] | None,
    s5: dict[str, Any] | None,
    s6: dict[str, Any] | None,
) -> dict[str, Any]:
    mt = s1 is not None and bool(s1.get("available", False))
    qw = s4 is not None and bool(s4.get("available", False))
    ls = s5 is not None and bool(s5.get("available", False))
    sc = s6 is not None and bool(s6.get("available", False))
    missing: list[str] = []
    if not mt:
        missing.append("S1_MARKET_TRUTH")
    if not qw:
        missing.append("S4_QUALITY_WEIGHT")
    if not ls:
        missing.append("S5_LIQUIDITY_STRUCTURE")
    if not sc:
        missing.append("S6_SETUP_CANDIDATE")
    return {
        "market_truth_available": mt,
        "quality_weight_available": qw,
        "liquidity_structure_available": ls,
        "setup_candidate_available": sc,
        "missing_inputs": missing,
    }


def _calc_setup_reference(s6: dict[str, Any] | None) -> dict[str, Any]:
    if s6 is None or not s6.get("available"):
        return {
            "setup_type": "UNKNOWN",
            "setup_direction": "UNKNOWN",
            "setup_grade": "UNKNOWN",
            "setup_status": "INVALID",
            "quality_adjusted_setup_score": 0.0,
        }
    return {
        "setup_type": str(s6.get("setup_type", "UNKNOWN")),
        "setup_direction": str(s6.get("setup_direction", "UNKNOWN")),
        "setup_grade": str(s6.get("setup_grade", "UNKNOWN")),
        "setup_status": str(s6.get("setup_status", "INVALID")),
        "quality_adjusted_setup_score": float(s6.get("quality_adjusted_setup_score", 0.0)),
    }


def _invalid_plan(direction: str, entry: float | None, stop: float | None, tp1: float | None) -> dict[str, Any]:
    return {
        "trade_direction": direction,
        "entry_price": round(entry, 4) if entry is not None else None,
        "stop_loss": round(stop, 4) if stop is not None else None,
        "tp1": round(tp1, 4) if tp1 is not None else None,
        "tp2": None,
        "invalidation_price": round(stop, 4) if stop is not None else None,
        "plan_status": "INVALID",
    }


def _calc_trade_plan(
    s1: dict[str, Any] | None,
    s5: dict[str, Any] | None,
    s6: dict[str, Any] | None,
) -> dict[str, Any]:
    setup_status = (
        str(s6.get("setup_status", "INVALID")).upper()
        if s6 is not None and s6.get("available")
        else "INVALID"
    )
    direction = (
        str(s6.get("setup_direction", "UNKNOWN")).upper()
        if s6 is not None and s6.get("available")
        else "UNKNOWN"
    )

    if setup_status == "NO_SETUP":
        return {
            "trade_direction": "NONE",
            "entry_price": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "invalidation_price": None,
            "plan_status": "NO_PLAN",
        }

    if setup_status == "INVALID" or s6 is None or not s6.get("available"):
        return _invalid_plan("UNKNOWN", None, None, None)

    if s1 is None or not s1.get("available"):
        return _invalid_plan(direction, None, None, None)

    entry = float(s1.get("current_price", 0.0))
    if entry <= 0.0:
        return _invalid_plan(direction, None, None, None)

    if s5 is None or not s5.get("available"):
        return _invalid_plan(direction, entry, None, None)

    nearest_support = s5.get("nearest_support")
    nearest_resistance = s5.get("nearest_resistance")
    if nearest_support is None or nearest_resistance is None:
        return _invalid_plan(direction, entry, None, None)

    nearest_support = float(nearest_support)
    nearest_resistance = float(nearest_resistance)

    if direction == "LONG":
        stop = nearest_support
        tp1 = nearest_resistance
        risk = entry - stop
        if risk <= 0.0 or stop >= entry or tp1 <= entry:
            return _invalid_plan(direction, entry, stop, tp1)
        tp2 = round(entry + risk * 2.0, 4)
        if tp1 > tp2:
            tp2 = round(tp1, 4)
        plan_status = "PLAN_READY" if setup_status == "READY_FOR_PLAN" else "WATCH_ONLY"
        return {
            "trade_direction": direction,
            "entry_price": round(entry, 4),
            "stop_loss": round(stop, 4),
            "tp1": round(tp1, 4),
            "tp2": tp2,
            "invalidation_price": round(stop, 4),
            "plan_status": plan_status,
        }

    if direction == "SHORT":
        stop = nearest_resistance
        tp1 = nearest_support
        risk = stop - entry
        if risk <= 0.0 or stop <= entry or tp1 >= entry:
            return _invalid_plan(direction, entry, stop, tp1)
        tp2 = round(entry - risk * 2.0, 4)
        if tp2 > tp1:
            tp2 = round(tp1, 4)
        plan_status = "PLAN_READY" if setup_status == "READY_FOR_PLAN" else "WATCH_ONLY"
        return {
            "trade_direction": direction,
            "entry_price": round(entry, 4),
            "stop_loss": round(stop, 4),
            "tp1": round(tp1, 4),
            "tp2": tp2,
            "invalidation_price": round(stop, 4),
            "plan_status": plan_status,
        }

    return _invalid_plan(direction, entry, None, None)


def _calc_risk_reward(plan: dict[str, Any]) -> dict[str, Any]:
    _null = {
        "risk_abs": None,
        "reward_tp1_abs": None,
        "reward_tp2_abs": None,
        "rr_tp1": None,
        "rr_tp2": None,
        "rr_label": "INVALID_RR",
    }
    if plan["plan_status"] in ("INVALID", "NO_PLAN"):
        return _null
    entry = plan.get("entry_price")
    stop = plan.get("stop_loss")
    tp1 = plan.get("tp1")
    tp2 = plan.get("tp2")
    if entry is None or stop is None or tp1 is None or tp2 is None:
        return _null
    risk = abs(float(entry) - float(stop))
    if risk <= 0.0:
        return _null
    reward_tp1 = abs(float(tp1) - float(entry))
    reward_tp2 = abs(float(tp2) - float(entry))
    rr_tp1 = round(reward_tp1 / risk, 4)
    rr_tp2 = round(reward_tp2 / risk, 4)
    if rr_tp2 >= 2.0:
        label = "GOOD_RR"
    elif rr_tp2 >= 1.5:
        label = "ACCEPTABLE_RR"
    else:
        label = "POOR_RR"
    return {
        "risk_abs": round(risk, 4),
        "reward_tp1_abs": round(reward_tp1, 4),
        "reward_tp2_abs": round(reward_tp2, 4),
        "rr_tp1": rr_tp1,
        "rr_tp2": rr_tp2,
        "rr_label": label,
    }


def _calc_decision_gate(
    s1: dict[str, Any] | None,
    s6: dict[str, Any] | None,
    plan: dict[str, Any],
    rr: dict[str, Any],
    quality_weight: float,
) -> dict[str, Any]:
    # Check S1 availability first — missing S1 is always INVALID
    if s1 is None or not s1.get("available"):
        return {
            "decision": "INVALID",
            "decision_reason": "Missing S1 or unavailable market truth.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    # Check S6 availability
    if s6 is None or not s6.get("available"):
        return {
            "decision": "INVALID",
            "decision_reason": "S6 setup candidate missing.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    setup_status = str(s6.get("setup_status", "INVALID")).upper()

    # S6 setup_status checks come before plan checks (plan may have no entry for NO_SETUP)
    if setup_status == "INVALID":
        return {
            "decision": "INVALID",
            "decision_reason": "S6 setup status is INVALID.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    if setup_status == "NO_SETUP":
        return {
            "decision": "BLOCK",
            "decision_reason": "S6 produced NO_SETUP — no setup candidate available.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    if setup_status == "WATCH_SETUP":
        return {
            "decision": "WATCH",
            "decision_reason": "S6 setup is WATCH_SETUP — monitoring only, no paper trade.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    # READY_FOR_PLAN path — now validate plan entry price
    if plan.get("entry_price") is None:
        return {
            "decision": "INVALID",
            "decision_reason": "Missing current price — cannot compute trade plan.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    if plan["plan_status"] == "INVALID":
        return {
            "decision": "BLOCK",
            "decision_reason": "Trade plan invalid — price ordering constraint violated.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    rr_label = rr.get("rr_label", "INVALID_RR")
    if rr_label in ("POOR_RR", "INVALID_RR"):
        return {
            "decision": "BLOCK",
            "decision_reason": f"Risk/reward insufficient: {rr_label}.",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
        }

    edge_eligible = quality_weight >= 0.5 and rr_label in ("GOOD_RR", "ACCEPTABLE_RR")
    return {
        "decision": "ALLOW_PAPER",
        "decision_reason": f"Setup READY_FOR_PLAN with {rr_label} — paper trade allowed.",
        "paper_eligible": True,
        "edge_eligible_if_outcome_closes": edge_eligible,
    }


def _calc_quality_context(
    s4: dict[str, Any] | None,
    qa_setup: float,
    rr_tp2: float | None,
) -> dict[str, Any]:
    if s4 is not None and s4.get("available"):
        qw = float(s4.get("quality_weight", 0.5))
        ql = str(s4.get("quality_label", "UNKNOWN"))
    else:
        qw = 0.5
        ql = "UNKNOWN"
    rr_mult = min(1.0, float(rr_tp2) / 2.0) if rr_tp2 is not None else 0.0
    adj_score = round(float(qa_setup) * rr_mult, 2)
    return {
        "inherited_quality_weight": qw,
        "inherited_quality_label": ql,
        "quality_adjusted_decision_score": adj_score,
    }


def _build_execution_safety() -> dict[str, Any]:
    return {
        "safe_to_open_real_trade": False,
        "private_api_used": False,
        "live_order_sent": False,
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
        base = max(0.0, base - 0.40)
    if not input_status["setup_candidate_available"]:
        base = max(0.0, base - 0.40)
    if not input_status["liquidity_structure_available"]:
        base = max(0.0, base - 0.20)
    if not input_status["quality_weight_available"]:
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
    setup_ref: dict[str, Any],
    plan: dict[str, Any],
    rr: dict[str, Any],
    gate: dict[str, Any],
    data_quality: dict[str, Any],
) -> list[str]:
    codes: list[str] = [f"SOURCE_{source_mode}"]
    for m in input_status["missing_inputs"]:
        codes.append(f"MISSING_{m}")
    codes.append(f"SETUP_STATUS_{setup_ref['setup_status']}")
    codes.append(f"SETUP_GRADE_{setup_ref['setup_grade']}")
    codes.append(f"PLAN_{plan['plan_status']}")
    codes.append(f"RR_{rr['rr_label']}")
    codes.append(f"DECISION_{gate['decision']}")
    codes.append(f"PAPER_ELIGIBLE_{str(gate['paper_eligible']).upper()}")
    codes.append("SAFE_TO_OPEN_REAL_TRADE_FALSE")
    codes.append(f"DATA_QUALITY_{data_quality['level']}")
    return codes


def build_trade_plan_decision(
    symbol: str,
    s1: dict[str, Any] | None,
    s4: dict[str, Any] | None,
    s5: dict[str, Any] | None,
    s6: dict[str, Any] | None,
    source_mode: str,
) -> dict[str, Any]:
    input_status = _calc_input_status(s1, s4, s5, s6)
    quality_weight = (
        float(s4.get("quality_weight", 0.5))
        if s4 is not None and s4.get("available")
        else 0.5
    )

    setup_ref = _calc_setup_reference(s6)
    plan = _calc_trade_plan(s1, s5, s6)
    rr = _calc_risk_reward(plan)
    gate = _calc_decision_gate(s1, s6, plan, rr, quality_weight)
    qa_setup = float(setup_ref.get("quality_adjusted_setup_score", 0.0))
    quality_ctx = _calc_quality_context(s4, qa_setup, rr.get("rr_tp2"))
    safety = _build_execution_safety()
    data_quality = _build_data_quality(input_status, s4)
    reason_codes = _build_reason_codes(
        source_mode, input_status, setup_ref, plan, rr, gate, data_quality
    )

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "input_status": input_status,
        "setup_reference": setup_ref,
        "trade_plan": plan,
        "risk_reward": rr,
        "decision_gate": gate,
        "quality_context": quality_ctx,
        "execution_safety": safety,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_trade_plan_decision(
        symbol, _FAKE_S1, _FAKE_S4, _FAKE_S5, _FAKE_S6, "FAKE_SAMPLE"
    )
