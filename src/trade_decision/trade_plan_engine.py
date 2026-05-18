from __future__ import annotations

from typing import Any

from .trade_decision_registry import (
    RR_MIN_A_QUALITY,
    RR_MIN_NORMAL,
    RR_MIN_SCALP,
)

_PRICE_EQUALITY_TOLERANCE = 0.01  # prices within this % are considered "same" (degenerate)


def _pct_diff(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / abs(b)


def _is_degenerate(price_a: float | None, price_b: float | None) -> bool:
    if price_a is None or price_b is None:
        return True
    return _pct_diff(price_a, price_b) < _PRICE_EQUALITY_TOLERANCE


def _extract_liquidity_levels(liq_structure: dict[str, Any] | None) -> dict[str, Any]:
    if not liq_structure:
        return {}
    levels = liq_structure.get("liquidity_levels") or {}
    above = levels.get("nearest_liquidity_above") or {}
    below = levels.get("nearest_liquidity_below") or {}
    range_ctx = liq_structure.get("range_context") or {}
    return {
        "current_price": range_ctx.get("current_price"),
        "range_high": range_ctx.get("range_high"),
        "range_low": range_ctx.get("range_low"),
        "range_mid": range_ctx.get("range_mid"),
        "nearest_liquidity_above_price": above.get("price"),
        "nearest_liquidity_above_type": above.get("liquidity_type", "UNKNOWN"),
        "nearest_liquidity_below_price": below.get("price"),
        "nearest_liquidity_below_type": below.get("liquidity_type", "UNKNOWN"),
        "nearest_support": liq_structure.get("nearest_support"),
        "nearest_resistance": liq_structure.get("nearest_resistance"),
    }


def _determine_side(setup_entry: dict[str, Any] | None) -> str:
    if not setup_entry:
        return "UNKNOWN"
    direction = str(setup_entry.get("setup_direction") or "").upper()
    if direction == "LONG":
        return "LONG"
    if direction == "SHORT":
        return "SHORT"
    if direction in ("NO_TRADE", "NEUTRAL"):
        return "NO_TRADE"
    return "UNKNOWN"


def _determine_entry_model(
    side: str,
    setup_entry: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
) -> str:
    if side not in ("LONG", "SHORT"):
        return "NO_ENTRY"
    if not setup_entry:
        return "UNKNOWN"
    candidate = str(setup_entry.get("setup_candidate") or "").upper()
    scenario = str((active_scenario or {}).get("active_scenario") or "").upper()

    if "RECLAIM" in candidate:
        return "RECLAIM"
    if "BREAKOUT" in candidate:
        return "BREAKOUT"
    if "SWEEP" in candidate or "RETEST" in candidate:
        return "RETEST"
    if "REJECTION" in candidate:
        return "REJECTION"
    if "CONTINUATION" in candidate:
        return "CONTINUATION"
    if "ROTATION" in scenario or "RANGE" in candidate:
        return "RETEST"
    return "UNKNOWN"


def _compute_entry_price(
    side: str,
    entry_model: str,
    levels: dict[str, Any],
) -> tuple[float | None, list[str], str]:
    """Returns (price, reason_codes, source_label)."""
    current = levels.get("current_price")
    if current is None:
        return None, ["ENTRY_NO_PRICE_EVIDENCE"], "NO_EVIDENCE"

    support = levels.get("nearest_support")
    resistance = levels.get("nearest_resistance")
    range_low = levels.get("range_low")
    range_high = levels.get("range_high")
    liq_above = levels.get("nearest_liquidity_above_price")
    liq_below = levels.get("nearest_liquidity_below_price")

    reason_codes: list[str] = []
    price: float | None = None
    source = "CURRENT_PRICE"

    if side == "LONG":
        if entry_model == "RETEST" and support is not None and not _is_degenerate(support, current):
            price = support
            source = "STRUCTURAL_SUPPORT_RETEST"
            reason_codes.append("ENTRY_LONG_RETEST_SUPPORT")
        elif entry_model == "RECLAIM" and support is not None and not _is_degenerate(support, current):
            price = support
            source = "STRUCTURAL_SUPPORT_RECLAIM"
            reason_codes.append("ENTRY_LONG_RECLAIM_SUPPORT")
        elif entry_model == "BREAKOUT" and range_high is not None and not _is_degenerate(range_high, current):
            price = range_high
            source = "RANGE_HIGH_BREAKOUT"
            reason_codes.append("ENTRY_LONG_BREAKOUT_RANGE_HIGH")
        elif entry_model == "CONTINUATION":
            price = current
            source = "CURRENT_PRICE_CONTINUATION"
            reason_codes.append("ENTRY_LONG_CONTINUATION_CURRENT")
        else:
            price = current
            source = "CURRENT_PRICE"
            reason_codes.append("ENTRY_LONG_CURRENT_PRICE")

    elif side == "SHORT":
        if entry_model == "RETEST" and resistance is not None and not _is_degenerate(resistance, current):
            price = resistance
            source = "STRUCTURAL_RESISTANCE_RETEST"
            reason_codes.append("ENTRY_SHORT_RETEST_RESISTANCE")
        elif entry_model == "RECLAIM" and resistance is not None and not _is_degenerate(resistance, current):
            price = resistance
            source = "STRUCTURAL_RESISTANCE_RECLAIM"
            reason_codes.append("ENTRY_SHORT_RECLAIM_RESISTANCE")
        elif entry_model == "BREAKOUT" and range_low is not None and not _is_degenerate(range_low, current):
            price = range_low
            source = "RANGE_LOW_BREAKOUT"
            reason_codes.append("ENTRY_SHORT_BREAKOUT_RANGE_LOW")
        elif entry_model == "REJECTION":
            if resistance is not None and not _is_degenerate(resistance, current):
                price = resistance
                source = "STRUCTURAL_RESISTANCE_REJECTION"
                reason_codes.append("ENTRY_SHORT_REJECTION_RESISTANCE")
            else:
                price = current
                source = "CURRENT_PRICE_REJECTION"
                reason_codes.append("ENTRY_SHORT_CURRENT_PRICE_REJECTION")
        elif entry_model == "CONTINUATION":
            price = current
            source = "CURRENT_PRICE_CONTINUATION"
            reason_codes.append("ENTRY_SHORT_CONTINUATION_CURRENT")
        else:
            price = current
            source = "CURRENT_PRICE"
            reason_codes.append("ENTRY_SHORT_CURRENT_PRICE")

    if price is None:
        return None, ["ENTRY_PRICE_DERIVATION_FAILED"], "NO_EVIDENCE"

    return price, reason_codes, source


def _compute_stop_loss(
    side: str,
    entry_price: float,
    levels: dict[str, Any],
) -> tuple[float | None, float | None, list[str], list[str]]:
    """Returns (stop_loss, invalidation_level, sl_reason_codes, invalidation_reason_codes)."""
    support = levels.get("nearest_support")
    resistance = levels.get("nearest_resistance")
    liq_above = levels.get("nearest_liquidity_above_price")
    liq_below = levels.get("nearest_liquidity_below_price")
    range_low = levels.get("range_low")
    range_high = levels.get("range_high")

    sl_codes: list[str] = []
    inv_codes: list[str] = []

    if side == "LONG":
        candidates: list[tuple[float, str]] = []
        if support is not None and support < entry_price and not _is_degenerate(support, entry_price):
            candidates.append((support, "STRUCTURAL_LOW"))
        if liq_below is not None and liq_below < entry_price and not _is_degenerate(liq_below, entry_price):
            candidates.append((liq_below, "LIQUIDITY_BELOW"))
        if range_low is not None and range_low < entry_price and not _is_degenerate(range_low, entry_price):
            candidates.append((range_low, "RANGE_LOW"))

        if not candidates:
            return None, None, ["SL_NO_STRUCTURAL_LOW_AVAILABLE"], ["INVALIDATION_NO_LEVEL"]

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_price, best_source = candidates[0]
        sl_codes.append(f"SL_LONG_{best_source}")
        inv_codes.append(f"INVALIDATION_LONG_{best_source}")
        return best_price, best_price, sl_codes, inv_codes

    if side == "SHORT":
        candidates = []
        if resistance is not None and resistance > entry_price and not _is_degenerate(resistance, entry_price):
            candidates.append((resistance, "STRUCTURAL_HIGH"))
        if liq_above is not None and liq_above > entry_price and not _is_degenerate(liq_above, entry_price):
            candidates.append((liq_above, "LIQUIDITY_ABOVE"))
        if range_high is not None and range_high > entry_price and not _is_degenerate(range_high, entry_price):
            candidates.append((range_high, "RANGE_HIGH"))

        if not candidates:
            return None, None, ["SL_NO_STRUCTURAL_HIGH_AVAILABLE"], ["INVALIDATION_NO_LEVEL"]

        candidates.sort(key=lambda x: x[0])
        best_price, best_source = candidates[0]
        sl_codes.append(f"SL_SHORT_{best_source}")
        inv_codes.append(f"INVALIDATION_SHORT_{best_source}")
        return best_price, best_price, sl_codes, inv_codes

    return None, None, ["SL_SIDE_UNKNOWN"], ["INVALIDATION_SIDE_UNKNOWN"]


def _compute_take_profits(
    side: str,
    entry_price: float,
    stop_loss: float,
    levels: dict[str, Any],
) -> tuple[float | None, float | None, list[str]]:
    """Returns (tp1, tp2, tp_reason_codes). TP comes only from liquidity destinations."""
    liq_above = levels.get("nearest_liquidity_above_price")
    liq_below = levels.get("nearest_liquidity_below_price")
    range_high = levels.get("range_high")
    range_low = levels.get("range_low")

    tp_codes: list[str] = []
    tp1: float | None = None
    tp2: float | None = None

    if side == "LONG":
        tp1_candidates: list[tuple[float, str]] = []
        if (
            liq_above is not None
            and liq_above > entry_price
            and not _is_degenerate(liq_above, entry_price)
        ):
            tp1_candidates.append((liq_above, "LIQUIDITY_ABOVE"))
        if (
            range_high is not None
            and range_high > entry_price
            and not _is_degenerate(range_high, entry_price)
        ):
            tp1_candidates.append((range_high, "RANGE_HIGH"))

        if not tp1_candidates:
            return None, None, ["TP_NO_LIQUIDITY_DESTINATION_ABOVE"]

        tp1_candidates.sort(key=lambda x: x[0])
        tp1, tp1_src = tp1_candidates[0]
        tp_codes.append(f"TP1_LONG_{tp1_src}")

        tp2_candidates = [c for c in tp1_candidates if c[0] > tp1]
        if tp2_candidates:
            tp2, tp2_src = tp2_candidates[0]
            tp_codes.append(f"TP2_LONG_{tp2_src}")

    elif side == "SHORT":
        tp1_candidates = []
        if (
            liq_below is not None
            and liq_below < entry_price
            and not _is_degenerate(liq_below, entry_price)
        ):
            tp1_candidates.append((liq_below, "LIQUIDITY_BELOW"))
        if (
            range_low is not None
            and range_low < entry_price
            and not _is_degenerate(range_low, entry_price)
        ):
            tp1_candidates.append((range_low, "RANGE_LOW"))

        if not tp1_candidates:
            return None, None, ["TP_NO_LIQUIDITY_DESTINATION_BELOW"]

        tp1_candidates.sort(key=lambda x: x[0], reverse=True)
        tp1, tp1_src = tp1_candidates[0]
        tp_codes.append(f"TP1_SHORT_{tp1_src}")

        tp2_candidates = [c for c in tp1_candidates if c[0] < tp1]
        if tp2_candidates:
            tp2, tp2_src = tp2_candidates[0]
            tp_codes.append(f"TP2_SHORT_{tp2_src}")

    return tp1, tp2, tp_codes


def _compute_rr(
    side: str,
    entry: float | None,
    sl: float | None,
    tp: float | None,
) -> float | None:
    if entry is None or sl is None or tp is None:
        return None
    risk = abs(entry - sl)
    if risk < 0.001:
        return None
    reward = abs(tp - entry)
    return round(reward / risk, 4)


def _compute_plan_quality(
    setup_quality: str,
    entry_trigger_quality: str,
    rr: float | None,
    entry_price: float | None,
    stop_loss: float | None,
    tp1: float | None,
    invalidation: float | None,
) -> str:
    if any(v is None for v in [entry_price, stop_loss, tp1, invalidation]):
        return "INVALID"
    if rr is None or rr < RR_MIN_SCALP:
        return "INVALID"
    if setup_quality == "A" and entry_trigger_quality == "HIGH" and rr >= RR_MIN_A_QUALITY:
        return "A"
    if setup_quality in ("A", "B") and rr >= RR_MIN_NORMAL:
        return "B"
    if rr >= RR_MIN_SCALP:
        return "C"
    return "INVALID"


def _compute_risk_grade(plan_quality: str, rr: float | None) -> str:
    if plan_quality == "INVALID":
        return "NO_TRADE"
    if rr is None:
        return "UNKNOWN"
    if plan_quality == "A" and rr >= RR_MIN_A_QUALITY:
        return "LOW"
    if plan_quality in ("A", "B") and rr >= RR_MIN_NORMAL:
        return "MEDIUM"
    return "HIGH"


def _compute_template_risk_score(
    entry_price: float | None,
    current_price: float | None,
    entry_reason_codes: list[str],
    sl_reason_codes: list[str],
    tp_reason_codes: list[str],
    rr: float | None,
    evidence: dict[str, Any],
) -> float:
    score = 0.0

    if entry_price is not None and current_price is not None:
        if _is_degenerate(entry_price, current_price) and not entry_reason_codes:
            score += 0.3

    if tp_reason_codes and any("NO_LIQUIDITY_DESTINATION" in c for c in tp_reason_codes):
        score += 0.3

    if not sl_reason_codes:
        score += 0.2

    all_evidence_empty = all(
        not v for v in evidence.values()
    ) if evidence else True
    if all_evidence_empty:
        score += 0.2

    if rr is not None:
        round_values = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0)
        if any(abs(rr - rv) < 0.001 for rv in round_values):
            score += 0.1

    return min(round(score, 4), 1.0)


def _compute_scores(
    setup_quality: str,
    entry_trigger_quality: str,
    tp1: float | None,
    tp1_src: str,
    sl: float | None,
    sl_src: str,
    rr: float | None,
    template_risk_score: float,
) -> dict[str, float]:
    sq = {"A": 1.0, "B": 0.7, "C": 0.5, "INVALID": 0.0, "UNKNOWN": 0.0}.get(setup_quality, 0.0)
    etq = {"HIGH": 1.0, "MEDIUM": 0.65, "LOW": 0.35, "INVALID": 0.0, "UNKNOWN": 0.0}.get(entry_trigger_quality, 0.0)

    liq_score = 0.0
    if tp1 is not None:
        if "LIQUIDITY" in tp1_src:
            liq_score = 1.0
        elif "RANGE" in tp1_src:
            liq_score = 0.5

    struct_score = 0.0
    if sl is not None:
        if "STRUCTURAL" in sl_src:
            struct_score = 1.0
        elif "LIQUIDITY" in sl_src or "RANGE" in sl_src:
            struct_score = 0.6

    rr_score = 0.0
    if rr is not None:
        if rr >= RR_MIN_A_QUALITY:
            rr_score = 1.0
        elif rr >= RR_MIN_NORMAL:
            rr_score = 0.75
        elif rr >= RR_MIN_SCALP:
            rr_score = 0.5

    return {
        "setup_quality_score": round(sq, 4),
        "entry_trigger_score": round(etq, 4),
        "liquidity_destination_score": round(liq_score, 4),
        "structure_invalidation_score": round(struct_score, 4),
        "rr_quality_score": round(rr_score, 4),
        "risk_penalty": round(template_risk_score, 4),
        "template_risk_score": round(template_risk_score, 4),
    }


def build_trade_plan(
    setup_entry: dict[str, Any] | None,
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    liquidity_structure: dict[str, Any] | None,
    data_quality: str = "UNKNOWN",
) -> dict[str, Any]:
    """Build a trade plan from available evidence. Never produces TP from fixed RR formula."""

    trigger_status = str((setup_entry or {}).get("entry_trigger_status") or "TRIGGER_UNKNOWN").upper()
    setup_quality = str((setup_entry or {}).get("setup_quality") or "INVALID").upper()
    trigger_quality = str((setup_entry or {}).get("entry_trigger_quality") or "INVALID").upper()
    setup_candidate = str((setup_entry or {}).get("setup_candidate") or "NO_SETUP").upper()

    blocking_codes: list[str] = []
    preliminary_decision = "UNKNOWN"

    if setup_entry is None or "NO_SETUP" in setup_candidate or setup_candidate == "UNKNOWN":
        return {
            "side": "NO_TRADE",
            "entry_model": "NO_ENTRY",
            "entry_price": None,
            "stop_loss": None,
            "invalidation_level": None,
            "take_profit_1": None,
            "take_profit_2": None,
            "rr_to_tp1": None,
            "rr_to_tp2": None,
            "plan_quality": "INVALID",
            "risk_grade": "NO_TRADE",
            "entry_reason_codes": [],
            "sl_reason_codes": [],
            "tp_reason_codes": [],
            "invalidation_reason_codes": [],
            "blocking_reason_codes": ["NO_SETUP_AVAILABLE"],
            "risk_reason_codes": [],
            "template_risk_score": 0.0,
            "scores": _compute_scores("INVALID", "INVALID", None, "", None, "", None, 0.0),
            "evidence": {},
            "_trigger_status": trigger_status,
            "_preliminary_decision": "NO_TRADE",
            "_entry_source": "NO_EVIDENCE",
            "_sl_source": "NO_EVIDENCE",
        }

    if trigger_status in ("TRIGGER_INVALID", "TRIGGER_CONFLICTED"):
        blocking_codes.append(f"TRIGGER_STATUS_{trigger_status}")
        preliminary_decision = "BLOCK"
    elif trigger_status in ("TRIGGER_WAIT", "TRIGGER_NEAR"):
        preliminary_decision = "WAIT"
    elif trigger_status == "TRIGGER_UNKNOWN":
        preliminary_decision = "NO_TRADE"
    elif trigger_status == "TRIGGER_READY":
        preliminary_decision = "ALLOW"
    else:
        blocking_codes.append("TRIGGER_STATUS_UNRECOGNIZED")
        preliminary_decision = "BLOCK"

    side = _determine_side(setup_entry)
    if side not in ("LONG", "SHORT"):
        blocking_codes.append("SIDE_UNDETERMINED")
        preliminary_decision = "BLOCK" if preliminary_decision == "ALLOW" else preliminary_decision

    entry_model = _determine_entry_model(side, setup_entry, active_scenario)
    levels = _extract_liquidity_levels(liquidity_structure)

    evidence_snap: dict[str, Any] = {
        "setup_candidate": setup_candidate,
        "setup_quality": setup_quality,
        "trigger_status": trigger_status,
        "trigger_quality": trigger_quality,
        "scenario": (active_scenario or {}).get("active_scenario"),
        "current_price": levels.get("current_price"),
        "range_high": levels.get("range_high"),
        "range_low": levels.get("range_low"),
        "nearest_liquidity_above": levels.get("nearest_liquidity_above_price"),
        "nearest_liquidity_below": levels.get("nearest_liquidity_below_price"),
        "nearest_support": levels.get("nearest_support"),
        "nearest_resistance": levels.get("nearest_resistance"),
        "flow_confirmation": (flow_reaction or {}).get("flow_confirmation"),
        "market_regime": (market_state or {}).get("market_regime"),
    }

    entry_price, entry_codes, entry_source = _compute_entry_price(side, entry_model, levels)
    if entry_price is None:
        blocking_codes.append("ENTRY_PRICE_MISSING")
        if preliminary_decision == "ALLOW":
            preliminary_decision = "BLOCK"

    stop_loss = None
    invalidation = None
    sl_codes: list[str] = []
    inv_codes: list[str] = []
    sl_source = "NO_EVIDENCE"

    if entry_price is not None:
        stop_loss, invalidation, sl_codes, inv_codes = _compute_stop_loss(side, entry_price, levels)
        if stop_loss is not None:
            sl_source = sl_codes[0] if sl_codes else "UNKNOWN"
        if stop_loss is None:
            blocking_codes.append("STOP_LOSS_MISSING")
            if preliminary_decision == "ALLOW":
                preliminary_decision = "BLOCK"

    tp1 = None
    tp2 = None
    tp_codes: list[str] = []
    tp1_source = "NO_EVIDENCE"

    if entry_price is not None and stop_loss is not None:
        tp1, tp2, tp_codes = _compute_take_profits(side, entry_price, stop_loss, levels)
        if tp1 is not None:
            tp1_source = tp_codes[0] if tp_codes else "UNKNOWN"
        if tp1 is None:
            blocking_codes.append("TAKE_PROFIT_MISSING")
            if preliminary_decision == "ALLOW":
                preliminary_decision = "BLOCK"

    rr1 = _compute_rr(side, entry_price, stop_loss, tp1)
    rr2 = _compute_rr(side, entry_price, stop_loss, tp2)

    if rr1 is not None and rr1 < RR_MIN_SCALP:
        blocking_codes.append("RR_BELOW_MINIMUM")
        if preliminary_decision == "ALLOW":
            preliminary_decision = "BLOCK"

    template_risk = _compute_template_risk_score(
        entry_price=entry_price,
        current_price=levels.get("current_price"),
        entry_reason_codes=entry_codes,
        sl_reason_codes=sl_codes,
        tp_reason_codes=tp_codes,
        rr=rr1,
        evidence=evidence_snap,
    )

    if template_risk >= 0.5:
        blocking_codes.append("TEMPLATE_RISK_HIGH")
        if preliminary_decision == "ALLOW":
            preliminary_decision = "BLOCK"

    plan_quality = _compute_plan_quality(
        setup_quality=setup_quality,
        entry_trigger_quality=trigger_quality,
        rr=rr1,
        entry_price=entry_price,
        stop_loss=stop_loss,
        tp1=tp1,
        invalidation=invalidation,
    )

    risk_grade = _compute_risk_grade(plan_quality, rr1)

    risk_codes: list[str] = []
    if rr1 is not None and rr1 < RR_MIN_NORMAL:
        risk_codes.append("RR_BELOW_NORMAL_THRESHOLD")
    if template_risk >= 0.3:
        risk_codes.append("TEMPLATE_RISK_ELEVATED")
    if data_quality in ("DEGRADED", "INVALID"):
        risk_codes.append("DATA_QUALITY_RISK")

    scores = _compute_scores(
        setup_quality=setup_quality,
        entry_trigger_quality=trigger_quality,
        tp1=tp1,
        tp1_src=tp1_source,
        sl=stop_loss,
        sl_src=sl_source,
        rr=rr1,
        template_risk_score=template_risk,
    )

    return {
        "side": side,
        "entry_model": entry_model,
        "entry_price": round(entry_price, 2) if entry_price is not None else None,
        "stop_loss": round(stop_loss, 2) if stop_loss is not None else None,
        "invalidation_level": round(invalidation, 2) if invalidation is not None else None,
        "take_profit_1": round(tp1, 2) if tp1 is not None else None,
        "take_profit_2": round(tp2, 2) if tp2 is not None else None,
        "rr_to_tp1": rr1,
        "rr_to_tp2": rr2,
        "plan_quality": plan_quality,
        "risk_grade": risk_grade,
        "entry_reason_codes": entry_codes,
        "sl_reason_codes": sl_codes,
        "tp_reason_codes": tp_codes,
        "invalidation_reason_codes": inv_codes,
        "blocking_reason_codes": blocking_codes,
        "risk_reason_codes": risk_codes,
        "template_risk_score": template_risk,
        "scores": scores,
        "evidence": evidence_snap,
        "_trigger_status": trigger_status,
        "_preliminary_decision": preliminary_decision,
        "_entry_source": entry_source,
        "_sl_source": sl_source,
    }
