"""S17 — Trade Plan Engine. Converts S16 scenario trigger into a paper-only structured trade plan."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"
SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"
FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"
EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
MARKET_TRUTH_PATH = STATE_DIR / "latest_market_truth.json"
MODEL_REGISTRY_PATH = STATE_DIR / "latest_model_registry.json"

DEPTH_MEMORY_PATH = STATE_DIR / "latest_depth_liquidity_memory.json"
CONTEXT_SYNC_PATH = STATE_DIR / "latest_context_sync.json"

TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"
S17_STATE_PATH = STATE_DIR / "s17_trade_plan_state.json"
TRADE_PLAN_LOG_PATH = DATA_DIR / "trade_plan_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s17_trade_plan_latest_report.md"

MIN_RR_TP1 = 1.5
MIN_RR_TP2 = 2.0
MIN_STOP_PCT = 0.0015
MAX_STOP_PCT = 0.0080


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _extract_reference_price(flow_state: dict[str, Any] | None, evidence: dict[str, Any] | None) -> float | None:
    if flow_state:
        bucket = flow_state.get("latest_bucket") or {}
        for k in ("last_price", "mid_price", "vwap"):
            v = bucket.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        v = flow_state.get("last_price")
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    if evidence:
        for k in ("last_price", "reference_price"):
            v = evidence.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
    return None


def _structural_sl_tp(
    side: str,
    entry: float,
    depth_memory: dict,
) -> tuple[float | None, float | None, float | None, str]:
    """
    Order book duvarlarina gore yapisal SL ve TP hesapla.
    
    Returns: (stop_loss, tp1, tp2, method)
    method: "STRUCTURAL" veya "FALLBACK"
    """
    if not depth_memory or not depth_memory.get("available"):
        return None, None, None, "FALLBACK"

    bid_wall = depth_memory.get("bid_wall", {})
    ask_wall = depth_memory.get("ask_wall", {})
    sl_ref   = depth_memory.get("structural_sl_reference", {})

    if side == "LONG":
        # SL: bid duvarinin biraz altı (duvar kırılırsa senaryo bozuldu)
        bid_wall_price = bid_wall.get("wall_price") or sl_ref.get("long_sl_reference")
        if bid_wall_price and bid_wall_price < entry:
            sl = round(bid_wall_price * 0.9995, 4)  # duvarin %0.05 altı
            stop_dist = abs(entry - sl)
            if stop_dist > 0:
                tp1 = round(entry + stop_dist * 1.5, 4)  # min 1.5 RR
                tp2 = round(entry + stop_dist * 2.5, 4)  # min 2.5 RR
                # Ask duvarı varsa TP hedef olarak kullan
                ask_wall_price = ask_wall.get("wall_price")
                if ask_wall_price and ask_wall_price > entry:
                    tp1 = round(min(tp1, ask_wall_price * 0.9998), 4)
                return sl, tp1, tp2, "STRUCTURAL"

    elif side == "SHORT":
        # SL: ask duvarinin biraz üstü
        ask_wall_price = ask_wall.get("wall_price") or sl_ref.get("short_sl_reference")
        if ask_wall_price and ask_wall_price > entry:
            sl = round(ask_wall_price * 1.0005, 4)  # duvarin %0.05 ustü
            stop_dist = abs(sl - entry)
            if stop_dist > 0:
                tp1 = round(entry - stop_dist * 1.5, 4)
                tp2 = round(entry - stop_dist * 2.5, 4)
                # Bid duvarı varsa TP hedef olarak kullan
                bid_wall_price = bid_wall.get("wall_price")
                if bid_wall_price and bid_wall_price < entry:
                    tp1 = round(max(tp1, bid_wall_price * 1.0002), 4)
                return sl, tp1, tp2, "STRUCTURAL"

    return None, None, None, "FALLBACK"


def _stop_pct(trigger_strength: float, confidence: float) -> float:
    base = MAX_STOP_PCT - (MAX_STOP_PCT - MIN_STOP_PCT) * max(0.0, min(1.0, trigger_strength))
    base *= (1.05 - 0.10 * max(0.0, min(1.0, confidence)))
    return max(MIN_STOP_PCT, min(MAX_STOP_PCT, base))


def _grade_from_rr(rr1: float, rr2: float, trigger_strength: float, confidence: float) -> str:
    if rr1 < MIN_RR_TP1 or rr2 < MIN_RR_TP2:
        return "WATCH"
    composite = (rr2 * 0.45) + (trigger_strength * 0.30) + (confidence * 0.25)
    if composite >= 1.45 and rr2 >= 2.5:
        return "A_PLUS"
    if composite >= 1.20 and rr2 >= 2.0:
        return "A"
    if composite >= 0.95:
        return "B"
    return "C"


def _quality_score(rr1: float, rr2: float, trigger_strength: float, confidence: float, dq_score: float) -> float:
    rr_norm = max(0.0, min(1.0, (rr1 + rr2) / 6.0))
    raw = (rr_norm * 0.4) + (trigger_strength * 0.3) + (confidence * 0.2) + (dq_score * 0.1)
    return round(max(0.0, min(1.0, raw)), 4)


def _direction_ok(side: str, entry: float, sl: float, tp1: float, tp2: float) -> bool:
    if side == "LONG":
        return sl < entry < tp1 <= tp2
    if side == "SHORT":
        return sl > entry > tp1 >= tp2
    return False


def _market_candle_close_time(market_truth: dict[str, Any] | None) -> str:
    if not market_truth:
        return "UNKNOWN"
    return (
        market_truth.get("candle_close_time")
        or (market_truth.get("market_truth") or {}).get("candle_close_time")
        or market_truth.get("timestamp_utc")
        or (market_truth.get("official_candle") or {}).get("close_time_utc")
        or "UNKNOWN"
    )


def _model_identity(model_registry: dict[str, Any] | None) -> tuple[str | None, str]:
    active_signals = list((model_registry or {}).get("active_signals") or [])
    if active_signals:
        names = [str(sig.get("model", "UNKNOWN")) for sig in active_signals]
        model_name = "+".join(names)
        return hashlib.sha1(model_name.encode("utf-8")).hexdigest()[:16], model_name
    return None, "NO_MODEL"


def _build_identity(
    scenario_trigger: dict[str, Any],
    setup_context: dict[str, Any],
    model_registry: dict[str, Any] | None,
    context_sync: dict[str, Any] | None,
    candle_close_time: str,
) -> dict[str, Any]:
    base = dict((scenario_trigger.get("identity") or {}) or (setup_context.get("identity") or {}))
    model_id, model_name = _model_identity(model_registry)
    setup_id = base.get("setup_id")
    setup_family = base.get("setup_family", "NO_SETUP")
    candidate_id = base.get("candidate_id")
    context_id = (context_sync or {}).get("context_id") or base.get("context_id")
    if setup_id and candidate_id is None and scenario_trigger.get("scenario_label") not in (None, "NO_SCENARIO"):
        raw = f"{setup_id}|{scenario_trigger.get('scenario_label')}|{candle_close_time}"
        candidate_id = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return {
        "setup_id": setup_id,
        "setup_family": setup_family,
        "model_id": model_id,
        "model_name": model_name,
        "candidate_id": candidate_id,
        "context_id": context_id,
        "source_engine": "S17_TRADE_PLAN_ENGINE",
        "input_state_refs": [
            "state/simple/latest_scenario_trigger.json",
            "state/simple/latest_setup_context.json",
            "state/simple/latest_flow_state.json",
            "state/simple/latest_flow_evidence.json",
            "state/simple/latest_flow_persistence.json",
            "state/simple/latest_market_truth.json",
            "state/simple/latest_model_registry.json",
            "state/simple/latest_context_sync.json",
        ],
    }


def compute_trade_plan(
    scenario_trigger: dict[str, Any] | None,
    setup_context: dict[str, Any] | None,
    flow_state: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    persistence: dict[str, Any] | None,
    market_truth: dict[str, Any] | None = None,
    model_registry: dict[str, Any] | None = None,
    depth_memory: dict[str, Any] | None = None,
    context_sync: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ts = _now_utc()
    reason_codes: list[str] = []

    missing = []
    if scenario_trigger is None:
        missing.append("SCENARIO_TRIGGER_MISSING")
    if setup_context is None:
        missing.append("SETUP_CONTEXT_MISSING")
    if flow_state is None:
        missing.append("FLOW_STATE_MISSING")

    input_status = "OK"
    if scenario_trigger is None:
        input_status = "MISSING"

    scenario_trigger = scenario_trigger or {}
    setup_context = setup_context or {}
    flow_state = flow_state or {}
    evidence = evidence or {}
    persistence = persistence or {}
    market_truth = market_truth or {}
    if model_registry is None:
        model_registry = _load_json(MODEL_REGISTRY_PATH)

    symbol = (
        scenario_trigger.get("symbol")
        or setup_context.get("symbol")
        or flow_state.get("symbol")
        or "UNKNOWN"
    )
    source = scenario_trigger.get("block_id") or "S16_SCENARIO_ENTRY_TRIGGER"
    setup_label = setup_context.get("setup_context_label", "INSUFFICIENT_CONTEXT")
    setup_tradeable = bool(setup_context.get("tradeable", False))

    direction_bias = scenario_trigger.get("direction_bias", "UNKNOWN")
    trigger_state = scenario_trigger.get("trigger_state", "NO_TRIGGER")
    ready_for_entry = bool(scenario_trigger.get("ready_for_entry", False))
    trigger_strength = float(scenario_trigger.get("trigger_strength", 0.0))
    scenario_label = scenario_trigger.get("scenario_label", "INSUFFICIENT_DATA")
    confidence = float(setup_context.get("confidence", 0.0) or scenario_trigger.get("trigger_confidence", 0.0))

    dq = scenario_trigger.get("data_quality") or setup_context.get("data_quality") or {}
    dq_level = dq.get("level", "MISSING")
    dq_score = float(dq.get("score", 0.0))

    side = "UNKNOWN"
    if direction_bias == "LONG":
        side = "LONG"
    elif direction_bias == "SHORT":
        side = "SHORT"
    elif direction_bias == "NEUTRAL":
        side = "NEUTRAL"
    diagnostic_side = side

    ref_price = _extract_reference_price(flow_state, evidence)
    candle_close_time = _market_candle_close_time(market_truth)

    plan_status = "NO_PLAN"
    plan_grade = "NO_PLAN"
    entry_price: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    rr_tp1 = 0.0
    rr_tp2 = 0.0
    invalidation_price: float | None = None
    preview_plan: dict[str, Any] | None = None

    entry_reason = "No actionable trigger — no entry planned."
    stop_reason = "No plan — stop not defined."
    tp_reason = "No plan — targets not defined."
    invalidation_reason = "No plan — invalidation not defined."

    quality_score = 0.0
    model_veto = False
    model_veto_reason: str | None = None

    if input_status == "MISSING" or not scenario_trigger:
        plan_status = "NO_PLAN"
        reason_codes.extend(missing or ["INPUT_MISSING"])
        reason_codes.append("PLAN_BLOCKED_NO_INPUTS")
    elif ref_price is None:
        plan_status = "INVALID"
        reason_codes.append("REFERENCE_PRICE_MISSING")
    elif side not in ("LONG", "SHORT"):
        plan_status = "NO_PLAN"
        reason_codes.append(f"SIDE_NOT_DIRECTIONAL_{side}")
    elif dq_level not in ("OK", "HIGH"):
        plan_status = "WATCH_ONLY"
        reason_codes.append(f"DQ_DEGRADED_{dq_level}")
        entry_price = round(ref_price, 4)
        sp = _stop_pct(trigger_strength, confidence)
        if side == "LONG":
            stop_loss = round(entry_price * (1.0 - sp), 4)
            tp1 = round(entry_price * (1.0 + sp * 1.5), 4)
            tp2 = round(entry_price * (1.0 + sp * 2.5), 4)
        else:
            stop_loss = round(entry_price * (1.0 + sp), 4)
            tp1 = round(entry_price * (1.0 - sp * 1.5), 4)
            tp2 = round(entry_price * (1.0 - sp * 2.5), 4)
        invalidation_price = stop_loss
        stop_dist = abs(entry_price - stop_loss)
        if stop_dist > 0:
            rr_tp1 = round(abs(tp1 - entry_price) / stop_dist, 4)
            rr_tp2 = round(abs(tp2 - entry_price) / stop_dist, 4)
        entry_reason = f"Reference price {entry_price} taken but DQ={dq_level} — watch only, no plan readiness."
        stop_reason = f"Indicative stop at {stop_loss} (stop_pct={round(sp,5)}) — not actionable due to DQ."
        tp_reason = f"Indicative TP1/TP2 at {tp1}/{tp2} based on stop distance multiples."
        invalidation_reason = f"Invalidation aligned with stop at {invalidation_price}."
    elif not ready_for_entry or trigger_state != "READY_FOR_ENTRY":
        plan_status = "WATCH_ONLY"
        reason_codes.append(f"NOT_READY_TRIGGER_{trigger_state}")
        entry_price = round(ref_price, 4)
        sp = _stop_pct(trigger_strength, confidence)
        if side == "LONG":
            stop_loss = round(entry_price * (1.0 - sp), 4)
            tp1 = round(entry_price * (1.0 + sp * 1.5), 4)
            tp2 = round(entry_price * (1.0 + sp * 2.5), 4)
        else:
            stop_loss = round(entry_price * (1.0 + sp), 4)
            tp1 = round(entry_price * (1.0 - sp * 1.5), 4)
            tp2 = round(entry_price * (1.0 - sp * 2.5), 4)
        invalidation_price = stop_loss
        stop_dist = abs(entry_price - stop_loss)
        if stop_dist > 0:
            rr_tp1 = round(abs(tp1 - entry_price) / stop_dist, 4)
            rr_tp2 = round(abs(tp2 - entry_price) / stop_dist, 4)
        entry_reason = f"Scenario {scenario_label} not ready ({trigger_state}) — watch only."
        stop_reason = f"Indicative stop at {stop_loss} below/above entry based on side={side}."
        tp_reason = f"Indicative TP1/TP2 at {tp1}/{tp2} but not actionable."
        invalidation_reason = f"Invalidation aligned with stop at {invalidation_price}."
    else:
        entry_price = round(ref_price, 4)
        sp = _stop_pct(trigger_strength, confidence)
        if sp <= 0:
            plan_status = "INVALID"
            reason_codes.append("STOP_DISTANCE_INVALID")
        else:
            if side == "LONG":
                stop_loss = round(entry_price * (1.0 - sp), 4)
                tp1 = round(entry_price * (1.0 + sp * 1.5), 4)
                tp2 = round(entry_price * (1.0 + sp * 2.5), 4)
            else:
                stop_loss = round(entry_price * (1.0 + sp), 4)
                tp1 = round(entry_price * (1.0 - sp * 1.5), 4)
                tp2 = round(entry_price * (1.0 - sp * 2.5), 4)
            invalidation_price = stop_loss
            stop_dist = abs(entry_price - stop_loss)
            if stop_dist <= 0:
                plan_status = "INVALID"
                reason_codes.append("STOP_DISTANCE_ZERO")
            elif not _direction_ok(side, entry_price, stop_loss, tp1, tp2):
                plan_status = "INVALID"
                reason_codes.append("PRICE_DIRECTION_CONTRADICTION")
            else:
                rr_tp1 = round(abs(tp1 - entry_price) / stop_dist, 4)
                rr_tp2 = round(abs(tp2 - entry_price) / stop_dist, 4)
                if rr_tp1 < MIN_RR_TP1 or rr_tp2 < MIN_RR_TP2:
                    plan_status = "WATCH_ONLY"
                    reason_codes.append("LOW_RR_DOWNGRADE")
                else:
                    plan_status = "PLAN_READY"
                entry_reason = (
                    f"Scenario {scenario_label} READY_FOR_ENTRY with trigger_strength={trigger_strength}; "
                    f"entry at reference price {entry_price}."
                )
                stop_reason = (
                    f"Stop at {stop_loss} ({'below' if side=='LONG' else 'above'} entry) "
                    f"using stop_pct={round(sp,5)} derived from trigger_strength and confidence."
                )
                tp_reason = (
                    f"TP1={tp1} at 1.2× stop distance, TP2={tp2} at 2.0× stop distance — "
                    f"RR1={rr_tp1}, RR2={rr_tp2} derived from actual prices."
                )
                invalidation_reason = (
                    f"Plan invalidated if price reaches {invalidation_price} — same as stop, aligned with side={side}."
                )

    if model_registry and int(model_registry.get("active_model_count", 0) or 0) > 0:
        model_consensus = model_registry.get("consensus_direction", "NEUTRAL")
        model_strength = max(
            float(model_registry.get("long_probability_pct", 50.0)),
            float(model_registry.get("short_probability_pct", 50.0)),
        )
        if model_consensus != "NEUTRAL" and side != "NEUTRAL" and model_consensus != side and model_strength > 65.0:
            model_veto = True
            model_veto_reason = f"MODEL_VETO_{side}_CONSENSUS_{model_consensus}_STRENGTH_{model_strength}"
            reason_codes.append(model_veto_reason)
            plan_status = "INVALID"
            plan_grade = "NO_PLAN"
            quality_score = 0.0

    model_signal_count = int((model_registry or {}).get("active_model_count", 0) or 0)
    model_consensus = str((model_registry or {}).get("consensus_direction", "NEUTRAL")).upper()
    model_registry_present = model_registry is not None

    no_actionable_reasons: list[str] = []
    if scenario_label == "NO_SCENARIO":
        no_actionable_reasons.append("NO_ACTIONABLE_PLAN")
    if setup_label == "NO_TRADE_CONTEXT":
        no_actionable_reasons.append("BLOCKED_BY_NO_TRADE_CONTEXT")
    if not setup_tradeable and setup_label == "NO_TRADE_CONTEXT":
        no_actionable_reasons.append("NOT_TRADEABLE_CONTEXT")
    if (
        model_registry_present
        and model_consensus == "NEUTRAL"
        and model_signal_count == 0
        and (setup_label == "NO_TRADE_CONTEXT" or scenario_label == "NO_SCENARIO")
    ):
        no_actionable_reasons.append("BLOCKED_BY_NEUTRAL_MODEL_CONSENSUS")
    if dq_level in ("LOW", "CRITICAL", "INVALID") and setup_label == "NO_TRADE_CONTEXT":
        no_actionable_reasons.append("NO_ACTIONABLE_PLAN")

    no_actionable_reasons = list(dict.fromkeys(no_actionable_reasons))
    if side in ("LONG", "SHORT") and entry_price is not None:
        preview_plan = {
            "side": side,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rr_tp1": rr_tp1,
            "rr_tp2": rr_tp2,
            "preview_only": True,
        }

    if not model_veto and input_status != "MISSING" and no_actionable_reasons:
        plan_status = "NO_ACTIONABLE_PLAN"
        plan_grade = "NO_PLAN"
        quality_score = 0.0
        side = "NEUTRAL"
        entry_price = None
        stop_loss = None
        tp1 = None
        tp2 = None
        rr_tp1 = None
        rr_tp2 = None
        invalidation_price = None
        entry_reason = "No actionable trade plan — diagnostic preview only."
        stop_reason = "No actionable trade plan — stop level kept only in preview_plan."
        tp_reason = "No actionable trade plan — target levels kept only in preview_plan."
        invalidation_reason = "No actionable trade plan — invalidation kept only in preview_plan."
        reason_codes.extend(no_actionable_reasons)
        if preview_plan is not None:
            reason_codes.append("PREVIEW_ONLY_LEVELS")

    if plan_status == "PLAN_READY":
        plan_grade = _grade_from_rr(rr_tp1, rr_tp2, trigger_strength, confidence)
    elif plan_status == "WATCH_ONLY":
        plan_grade = "WATCH"
    elif plan_status in ("NO_PLAN", "INVALID", "NO_ACTIONABLE_PLAN"):
        plan_grade = "NO_PLAN"

    if plan_status not in ("NO_PLAN", "INVALID", "NO_ACTIONABLE_PLAN"):
        quality_score = _quality_score(rr_tp1, rr_tp2, trigger_strength, confidence, dq_score)

    plan_explanation = {
        "ready": "Plan ready — all gates passed." if plan_status == "PLAN_READY" else None,
        "watch": "Watch only — scenario present but gates not passed." if plan_status == "WATCH_ONLY" else None,
        "no_plan": "No plan — inputs missing or no actionable side." if plan_status == "NO_PLAN" else None,
        "invalid": "Invalid — price/direction or stop distance malformed." if plan_status == "INVALID" else None,
    }

    risk_context = {
        "stop_distance": (round(abs(entry_price - stop_loss), 6) if (entry_price is not None and stop_loss is not None) else 0.0),
        "tp1_distance": (round(abs(tp1 - entry_price), 6) if (entry_price is not None and tp1 is not None) else 0.0),
        "tp2_distance": (round(abs(tp2 - entry_price), 6) if (entry_price is not None and tp2 is not None) else 0.0),
        "min_rr_tp1": MIN_RR_TP1,
        "min_rr_tp2": MIN_RR_TP2,
        "trigger_strength": trigger_strength,
        "confidence": confidence,
        "plan_explanation": {k: v for k, v in plan_explanation.items() if v},
    }

    reason_codes += [
        f"SYMBOL_{symbol}",
        f"SIDE_{side}",
        f"PLAN_STATUS_{plan_status}",
        f"PLAN_GRADE_{plan_grade}",
        f"SCENARIO_{scenario_label}",
        f"TRIGGER_{trigger_state}",
        f"DQ_{dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_TELEGRAM",
        "NO_ORDER_EXECUTION",
        "PAPER_ONLY",
    ]

    # context_id'yi sync'ten al
    context_id = (context_sync or {}).get("context_id", "CTX_UNKNOWN") if context_sync else "CTX_UNKNOWN"
    identity = _build_identity(scenario_trigger, setup_context, model_registry, context_sync, candle_close_time)

    return {
        "timestamp_utc": ts,
        "block_id": "S17_TRADE_PLAN_ENGINE",
        "symbol": symbol,
        "source": source,
        "context_id": context_id,
        "identity": identity,
        "input_status": input_status,
        "plan_status": plan_status,
        "side": side,
        "diagnostic_side": diagnostic_side,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "rr_tp1": rr_tp1,
        "rr_tp2": rr_tp2,
        "invalidation_price": invalidation_price,
        "preview_plan": preview_plan,
        "plan_quality_score": quality_score,
        "plan_grade": plan_grade,
        "entry_reason": entry_reason,
        "stop_reason": stop_reason,
        "tp_reason": tp_reason,
        "invalidation_reason": invalidation_reason,
        "model_veto": model_veto,
        "model_veto_reason": model_veto_reason,
        "timeframe": "1m",
        "candle_close_time": candle_close_time,
        "risk_context": risk_context,
        "data_quality": {"level": dq_level, "score": dq_score},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_output(reason: str) -> dict[str, Any]:
    ts = _now_utc()
    return {
        "timestamp_utc": ts,
        "block_id": "S17_TRADE_PLAN_ENGINE",
        "symbol": "UNKNOWN",
        "source": "NONE",
        "input_status": "MISSING",
        "identity": {
            "setup_id": None,
            "setup_family": "NO_SETUP",
            "model_id": None,
            "model_name": "NO_MODEL",
            "candidate_id": None,
            "context_id": None,
            "source_engine": "S17_TRADE_PLAN_ENGINE",
            "input_state_refs": [],
        },
        "plan_status": "NO_PLAN",
        "side": "NEUTRAL",
        "diagnostic_side": "UNKNOWN",
        "entry_price": None,
        "stop_loss": None,
        "tp1": None,
        "tp2": None,
        "rr_tp1": None,
        "rr_tp2": None,
        "invalidation_price": None,
        "preview_plan": None,
        "plan_quality_score": 0.0,
        "plan_grade": "NO_PLAN",
        "entry_reason": "Inputs missing — no plan can be built.",
        "stop_reason": "No plan — stop not defined.",
        "tp_reason": "No plan — targets not defined.",
        "invalidation_reason": "No plan — invalidation not defined.",
        "model_veto": False,
        "model_veto_reason": None,
        "timeframe": "1m",
        "candle_close_time": "UNKNOWN",
        "risk_context": {
            "stop_distance": 0.0,
            "tp1_distance": 0.0,
            "tp2_distance": 0.0,
            "min_rr_tp1": MIN_RR_TP1,
            "min_rr_tp2": MIN_RR_TP2,
            "trigger_strength": 0.0,
            "confidence": 0.0,
            "plan_explanation": {"no_plan": "No inputs."},
        },
        "data_quality": {"level": "MISSING", "score": 0.0},
        "reason_codes": [
            "INPUT_MISSING",
            reason,
            "PLAN_STATUS_NO_PLAN",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_TELEGRAM",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ],
        "feeds_next": {"next_blocks": ["S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_trade_plan_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    scenario_trigger = _load_json(SCENARIO_TRIGGER_PATH)
    setup_context = _load_json(SETUP_CONTEXT_PATH)
    flow_state = _load_json(FLOW_STATE_PATH)
    evidence = _load_json(EVIDENCE_PATH)
    persistence = _load_json(PERSISTENCE_PATH)
    market_truth = _load_json(MARKET_TRUTH_PATH)
    model_registry = _load_json(MODEL_REGISTRY_PATH)
    depth_memory = _load_json(DEPTH_MEMORY_PATH)
    context_sync = _load_json(CONTEXT_SYNC_PATH)

    if scenario_trigger is None:
        result = no_valid_output("SCENARIO_TRIGGER_MISSING")
    else:
        try:
            result = compute_trade_plan(
                scenario_trigger, setup_context, flow_state, evidence, persistence,
                market_truth=market_truth,
                model_registry=model_registry,
                depth_memory=depth_memory, context_sync=context_sync,
            )
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    TRADE_PLAN_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s17_state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S17_TRADE_PLAN_STATE",
        "last_plan_status": result["plan_status"],
        "last_plan_grade": result["plan_grade"],
        "last_side": result["side"],
        "last_rr_tp1": result["rr_tp1"],
        "last_rr_tp2": result["rr_tp2"],
        "last_plan_quality_score": result["plan_quality_score"],
        "runs": 1,
    }
    S17_STATE_PATH.write_text(json.dumps(s17_state, indent=2), encoding="utf-8")

    with TRADE_PLAN_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)
    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S17 Trade Plan Engine — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Source:** {r['source']}",
        f"**Input Status:** {r['input_status']}",
        f"**Plan Status:** {r['plan_status']}",
        f"**Plan Grade:** {r['plan_grade']}",
        f"**Side:** {r['side']}",
        f"**Entry Price:** {r['entry_price']}",
        f"**Stop Loss:** {r['stop_loss']}",
        f"**TP1:** {r['tp1']}",
        f"**TP2:** {r['tp2']}",
        f"**RR TP1:** {r['rr_tp1']}",
        f"**RR TP2:** {r['rr_tp2']}",
        f"**Invalidation Price:** {r['invalidation_price']}",
        f"**Plan Quality Score:** {r['plan_quality_score']}",
        f"**Entry Reason:** {r['entry_reason']}",
        f"**Stop Reason:** {r['stop_reason']}",
        f"**TP Reason:** {r['tp_reason']}",
        f"**Invalidation Reason:** {r['invalidation_reason']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
