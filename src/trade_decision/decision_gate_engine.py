from __future__ import annotations

from typing import Any

from .trade_decision_registry import (
    RR_MIN_SCALP,
    TEMPLATE_RISK_BLOCK_THRESHOLD,
)


def _gate_confidence(
    plan_quality: str,
    trigger_status: str,
    rr: float | None,
    template_risk: float,
    blocking_count: int,
) -> float:
    base = {"A": 0.85, "B": 0.70, "C": 0.55, "INVALID": 0.0, "UNKNOWN": 0.0}.get(plan_quality, 0.0)
    if trigger_status == "TRIGGER_READY":
        base *= 1.0
    elif trigger_status == "TRIGGER_NEAR":
        base *= 0.6
    elif trigger_status == "TRIGGER_WAIT":
        base *= 0.4
    else:
        base *= 0.0

    if rr is not None and rr >= 1.8:
        base = min(base * 1.1, 1.0)

    base -= template_risk * 0.3
    base -= blocking_count * 0.05
    return round(max(0.0, min(1.0, base)), 4)


def run_decision_gate(
    plan: dict[str, Any],
    data_quality: str,
) -> dict[str, Any]:
    """Evaluate the trade plan and produce a decision status."""

    preliminary = plan.get("_preliminary_decision", "UNKNOWN")
    trigger_status = plan.get("_trigger_status", "TRIGGER_UNKNOWN")
    plan_quality = plan.get("plan_quality", "INVALID")
    blocking_codes: list[str] = list(plan.get("blocking_reason_codes") or [])
    template_risk = float(plan.get("template_risk_score") or 0.0)

    entry_price = plan.get("entry_price")
    stop_loss = plan.get("stop_loss")
    tp1 = plan.get("take_profit_1")
    invalidation = plan.get("invalidation_level")
    rr1 = plan.get("rr_to_tp1")
    side = plan.get("side", "UNKNOWN")

    decision_status: str
    extra_blocks: list[str] = []

    if preliminary == "NO_TRADE" or side in ("NO_TRADE", "UNKNOWN"):
        decision_status = "NO_TRADE"

    elif data_quality == "INVALID":
        extra_blocks.append("DATA_QUALITY_INVALID")
        decision_status = "BLOCK"

    elif preliminary == "BLOCK":
        decision_status = "BLOCK"

    elif preliminary == "WAIT":
        decision_status = "WAIT"

    elif preliminary == "ALLOW":
        missing: list[str] = []
        if entry_price is None:
            missing.append("ENTRY_PRICE_REQUIRED_FOR_ALLOW")
        if stop_loss is None:
            missing.append("STOP_LOSS_REQUIRED_FOR_ALLOW")
        if tp1 is None:
            missing.append("TAKE_PROFIT_REQUIRED_FOR_ALLOW")
        if invalidation is None:
            missing.append("INVALIDATION_REQUIRED_FOR_ALLOW")
        if rr1 is None or rr1 <= 0:
            missing.append("VALID_RR_REQUIRED_FOR_ALLOW")

        if missing:
            extra_blocks.extend(missing)
            decision_status = "BLOCK"
        elif template_risk >= TEMPLATE_RISK_BLOCK_THRESHOLD:
            extra_blocks.append("TEMPLATE_RISK_BLOCKS_ALLOW")
            decision_status = "BLOCK"
        elif plan_quality == "INVALID":
            extra_blocks.append("PLAN_QUALITY_INVALID")
            decision_status = "BLOCK"
        elif rr1 is not None and rr1 < RR_MIN_SCALP:
            extra_blocks.append("RR_TOO_LOW_FOR_ALLOW")
            decision_status = "BLOCK"
        else:
            decision_status = "ALLOW_PAPER"
    else:
        decision_status = "UNKNOWN"

    all_blocking = blocking_codes + extra_blocks

    confidence = _gate_confidence(
        plan_quality=plan_quality,
        trigger_status=trigger_status,
        rr=rr1,
        template_risk=template_risk,
        blocking_count=len(all_blocking),
    )

    if decision_status != "ALLOW_PAPER":
        confidence = 0.0

    return {
        "decision_status": decision_status,
        "decision_confidence": confidence,
        "blocking_reason_codes": all_blocking,
    }
