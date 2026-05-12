"""S20 — Paper Lifecycle Tracker. Paper-only lifecycle state from S18/S19 alerts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S20_PAPER_LIFECYCLE_TRACKER"
FEEDS_NEXT = {"next_blocks": ["S21_OUTCOME_MONITOR"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

DECISION_GATE_PATH    = STATE_DIR / "latest_decision_gate.json"
TRADE_PLAN_PATH       = STATE_DIR / "latest_trade_plan.json"
ALERT_PATH            = STATE_DIR / "latest_telegram_paper_alert.json"
FLOW_STATE_PATH       = STATE_DIR / "latest_flow_state.json"
CONTEXT_SYNC_PATH     = STATE_DIR / "latest_context_sync.json"
SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"
SETUP_CANDIDATE_PATH  = STATE_DIR / "latest_setup_candidate.json"
DEPTH_MEMORY_PATH     = STATE_DIR / "latest_depth_liquidity_memory.json"
WALL_LIFECYCLE_PATH   = STATE_DIR / "latest_wall_lifecycle.json"

LIFECYCLE_PATH = STATE_DIR / "latest_paper_lifecycle.json"
S20_STATE_PATH = STATE_DIR / "s20_paper_lifecycle_state.json"
HISTORY_PATH = DATA_DIR / "paper_lifecycle_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s20_paper_lifecycle_latest_report.md"

ALLOWED_LIFECYCLE_STATUS = {
    "NOT_STARTED",
    "OPEN",
    "ACTIVE",
    "TP1_HIT",
    "TP2_HIT",
    "SL_HIT",
    "INVALIDATED",
    "CLOSED",
    "NO_LIFECYCLE",
}

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _extract_current_price(flow_state: dict[str, Any] | None) -> float | None:
    if not flow_state:
        return None
    lb = flow_state.get("latest_bucket") or {}
    for key in ("last_price", "vwap", "mid_price"):
        v = lb.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _allowed_for_lifecycle(decision_gate: dict[str, Any] | None, alert: dict[str, Any] | None) -> bool:
    if not decision_gate or not alert:
        return False
    decision = decision_gate.get("decision")
    alert_status = alert.get("alert_status")
    return decision == "ALLOW_PAPER" and alert_status in ("SENT", "DRY_RUN_READY")


def _make_lifecycle_id(ts: str, symbol: str, side: str, entry: Any) -> str:
    raw = f"{ts}|{symbol}|{side}|{entry}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _classify_dq(score: float, missing_price: bool) -> dict[str, Any]:
    issues: list[str] = []
    if missing_price:
        issues.append("MISSING_CURRENT_PRICE")
        level = "DEGRADED"
        score = min(score, 0.4)
    elif score >= 0.8:
        level = "HIGH"
    elif score >= 0.5:
        level = "MEDIUM"
    elif score >= 0.2:
        level = "LOW"
    else:
        level = "CRITICAL"
    return {"score": round(max(0.0, min(1.0, score)), 4), "level": level, "issues": issues}


def _no_lifecycle(
    symbol: str,
    source: str,
    reason: str,
    decision_gate: dict[str, Any] | None,
    alert: dict[str, Any] | None,
) -> dict[str, Any]:
    decision = (decision_gate or {}).get("decision", "UNKNOWN")
    alert_status = (alert or {}).get("alert_status", "UNKNOWN")
    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": source,
        "input_status": "OK" if decision_gate else "MISSING",
        "lifecycle_id": None,
        "lifecycle_status": "NO_LIFECYCLE",
        "side": (decision_gate or {}).get("selected_side", "UNKNOWN"),
        "entry_price": None,
        "stop_loss": None,
        "tp1": None,
        "tp2": None,
        "current_price": None,
        "entry_touched": False,
        "tp1_hit": False,
        "tp2_hit": False,
        "stop_hit": False,
        "invalidated": False,
        "unrealized_r": None,
        "realized_r": None,
        "max_favorable_excursion_r": 0.0,
        "max_adverse_excursion_r": 0.0,
        "lifecycle_events": [],
        "data_quality": {"score": 0.0, "level": "MISSING", "issues": [reason]},
        "reason_codes": [
            f"SYMBOL_{symbol}",
            f"DECISION_{decision}",
            f"ALERT_STATUS_{alert_status}",
            f"LIFECYCLE_STATUS_NO_LIFECYCLE",
            f"REASON_{reason}",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "PAPER_ONLY",
        ],
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def compute_paper_lifecycle(
    decision_gate: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    alert: dict[str, Any] | None,
    flow_state: dict[str, Any] | None,
    prior: dict[str, Any] | None = None,
    context_sync: dict[str, Any] | None = None,
    scenario_trigger: dict[str, Any] | None = None,
    setup_candidate: dict[str, Any] | None = None,
    depth_memory: dict[str, Any] | None = None,
    wall_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ts = _utc_now()
    symbol = (decision_gate or {}).get("symbol") or (alert or {}).get("symbol") or "UNKNOWN"
    source = (decision_gate or {}).get("block_id") or "S18_DECISION_GATE"

    if decision_gate is None or alert is None:
        return _no_lifecycle(symbol, source, "MISSING_INPUTS", decision_gate, alert)

    if not _allowed_for_lifecycle(decision_gate, alert):
        return _no_lifecycle(symbol, source, "DECISION_NOT_ALLOWED_FOR_PAPER", decision_gate, alert)

    side = str(decision_gate.get("selected_side", "UNKNOWN")).upper()
    entry = decision_gate.get("selected_entry")
    sl = decision_gate.get("selected_stop_loss")
    tp1 = decision_gate.get("selected_tp1")
    tp2 = decision_gate.get("selected_tp2")
    invalidation = (trade_plan or {}).get("invalidation_price")

    if side not in ("LONG", "SHORT") or entry is None or sl is None or tp1 is None or tp2 is None:
        return _no_lifecycle(symbol, source, "PLAN_FIELDS_MISSING", decision_gate, alert)

    entry_f = float(entry)
    sl_f = float(sl)
    tp1_f = float(tp1)
    tp2_f = float(tp2)
    risk = abs(entry_f - sl_f)
    current_price = _extract_current_price(flow_state)

    prior_events: list[dict[str, Any]] = []
    prior_mfe = 0.0
    prior_mae = 0.0
    prior_status: str | None = None
    lifecycle_id: str | None = None
    if prior and prior.get("lifecycle_status") not in (None, "NO_LIFECYCLE"):
        prior_entry = prior.get("entry_price")
        prior_side = prior.get("side")
        prior_sl = prior.get("stop_loss")
        if (
            prior_entry == entry_f
            and prior_side == side
            and prior_sl == sl_f
        ):
            prior_events = list(prior.get("lifecycle_events") or [])
            prior_mfe = float(prior.get("max_favorable_excursion_r") or 0.0)
            prior_mae = float(prior.get("max_adverse_excursion_r") or 0.0)
            prior_status = prior.get("lifecycle_status")
            lifecycle_id = prior.get("lifecycle_id")

    if lifecycle_id is None:
        lifecycle_id = _make_lifecycle_id(ts, symbol, side, entry_f)

    events: list[dict[str, Any]] = list(prior_events)

    def _event(kind: str, detail: str) -> None:
        events.append({"timestamp_utc": ts, "event": kind, "detail": detail})

    if not prior_events:
        _event("LIFECYCLE_CREATED", f"side={side} entry={entry_f} sl={sl_f}")

    missing_price = current_price is None
    dq_score = 1.0
    if missing_price:
        dq_score = 0.4
    dq = _classify_dq(dq_score, missing_price)

    entry_touched = False
    tp1_hit = False
    tp2_hit = False
    stop_hit = False
    invalidated = False

    if current_price is not None:
        cp = float(current_price)
        if side == "LONG":
            entry_touched = cp >= entry_f
            tp1_hit = cp >= tp1_f
            tp2_hit = cp >= tp2_f
            stop_hit = cp <= sl_f
        else:  # SHORT
            entry_touched = cp <= entry_f
            tp1_hit = cp <= tp1_f
            tp2_hit = cp <= tp2_f
            stop_hit = cp >= sl_f
        if invalidation is not None:
            inv_f = float(invalidation)
            if side == "LONG":
                invalidated = cp <= inv_f and not entry_touched
            else:
                invalidated = cp >= inv_f and not entry_touched

    # Merge with prior touches (sticky)
    if prior:
        entry_touched = entry_touched or bool(prior.get("entry_touched"))
        tp1_hit = tp1_hit or bool(prior.get("tp1_hit"))
        tp2_hit = tp2_hit or bool(prior.get("tp2_hit"))
        stop_hit = stop_hit or bool(prior.get("stop_hit"))
        invalidated = invalidated or bool(prior.get("invalidated"))

    # Compute unrealized R
    unrealized_r: float | None = None
    if current_price is not None and risk > 0:
        cp = float(current_price)
        if side == "LONG":
            unrealized_r = (cp - entry_f) / risk
        else:
            unrealized_r = (entry_f - cp) / risk
        unrealized_r = round(unrealized_r, 4)

    # MFE/MAE
    mfe = prior_mfe
    mae = prior_mae
    if unrealized_r is not None:
        if unrealized_r > mfe:
            mfe = unrealized_r
        if unrealized_r < mae:
            mae = unrealized_r

    # Determine lifecycle_status
    realized_r: float | None = None
    if missing_price and not entry_touched:
        lifecycle_status = "NOT_STARTED"
    elif stop_hit:
        lifecycle_status = "SL_HIT"
        realized_r = -1.0
    elif tp2_hit:
        lifecycle_status = "TP2_HIT"
        realized_r = round((tp2_f - entry_f) / risk if side == "LONG" else (entry_f - tp2_f) / risk, 4) if risk > 0 else None
    elif tp1_hit:
        lifecycle_status = "TP1_HIT"
        realized_r = round((tp1_f - entry_f) / risk if side == "LONG" else (entry_f - tp1_f) / risk, 4) if risk > 0 else None
    elif invalidated:
        lifecycle_status = "INVALIDATED"
    elif entry_touched:
        lifecycle_status = "ACTIVE"
    else:
        lifecycle_status = "OPEN"

    # Event diff vs prior
    if prior_status and lifecycle_status != prior_status:
        _event("STATUS_CHANGED", f"{prior_status} -> {lifecycle_status}")
    if not prior or not prior.get("entry_touched"):
        if entry_touched:
            _event("ENTRY_TOUCHED", f"price={current_price}")
    if not prior or not prior.get("tp1_hit"):
        if tp1_hit:
            _event("TP1_HIT", f"price={current_price}")
    if not prior or not prior.get("tp2_hit"):
        if tp2_hit:
            _event("TP2_HIT", f"price={current_price}")
    if not prior or not prior.get("stop_hit"):
        if stop_hit:
            _event("SL_HIT", f"price={current_price}")
    if not prior or not prior.get("invalidated"):
        if invalidated:
            _event("INVALIDATED", f"price={current_price}")

    assert lifecycle_status in ALLOWED_LIFECYCLE_STATUS

    # Build lineage — birth_timestamp from prior if continuing, else now
    birth_ts = (prior or {}).get("lineage", {}).get("birth_timestamp") or ts
    lineage = {
        "context_id": (context_sync or {}).get("context_id"),
        "source_scenario_id": (scenario_trigger or {}).get("scenario_label"),
        "source_setup_status": ((setup_candidate or {}).get("setup_candidate") or {}).get("setup_status"),
        "source_setup_grade": ((setup_candidate or {}).get("setup_candidate") or {}).get("setup_grade"),
        "source_trigger_strength": (scenario_trigger or {}).get("trigger_strength"),
        "source_confidence": (scenario_trigger or {}).get("trigger_confidence"),
        "source_liquidity_bias": (depth_memory or {}).get("liquidity_bias"),
        "source_wall_lifecycle": ((wall_lifecycle or {}).get("liquidity_intelligence") or {}).get("dominant_real_side"),
        "birth_timestamp": birth_ts,
    }

    reason_codes = [
        f"SYMBOL_{symbol}",
        f"SIDE_{side}",
        f"DECISION_{decision_gate.get('decision')}",
        f"ALERT_STATUS_{alert.get('alert_status')}",
        f"LIFECYCLE_STATUS_{lifecycle_status}",
        f"DQ_{dq['level']}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
        "PAPER_ONLY",
    ]
    if entry_touched:
        reason_codes.append("ENTRY_TOUCHED")
    if tp1_hit:
        reason_codes.append("TP1_HIT")
    if tp2_hit:
        reason_codes.append("TP2_HIT")
    if stop_hit:
        reason_codes.append("SL_HIT")
    if invalidated:
        reason_codes.append("INVALIDATED")
    if missing_price:
        reason_codes.append("MISSING_CURRENT_PRICE")

    return {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": source,
        "input_status": "OK",
        "lifecycle_id": lifecycle_id,
        "lifecycle_status": lifecycle_status,
        "side": side,
        "entry_price": entry_f,
        "stop_loss": sl_f,
        "tp1": tp1_f,
        "tp2": tp2_f,
        "current_price": current_price,
        "entry_touched": entry_touched,
        "tp1_hit": tp1_hit,
        "tp2_hit": tp2_hit,
        "stop_hit": stop_hit,
        "invalidated": invalidated,
        "unrealized_r": unrealized_r,
        "realized_r": realized_r,
        "max_favorable_excursion_r": round(mfe, 4),
        "max_adverse_excursion_r": round(mae, 4),
        "lifecycle_events": events,
        "lineage": lineage,
        "data_quality": dq,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def run_paper_lifecycle_tracker() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    decision_gate    = _load_json(DECISION_GATE_PATH)
    trade_plan       = _load_json(TRADE_PLAN_PATH)
    alert            = _load_json(ALERT_PATH)
    flow_state       = _load_json(FLOW_STATE_PATH)
    prior            = _load_json(LIFECYCLE_PATH)
    context_sync     = _load_json(CONTEXT_SYNC_PATH)
    scenario_trigger = _load_json(SCENARIO_TRIGGER_PATH)
    setup_candidate  = _load_json(SETUP_CANDIDATE_PATH)
    depth_memory     = _load_json(DEPTH_MEMORY_PATH)
    wall_lifecycle   = _load_json(WALL_LIFECYCLE_PATH)

    result = compute_paper_lifecycle(
        decision_gate, trade_plan, alert, flow_state, prior,
        context_sync, scenario_trigger, setup_candidate, depth_memory, wall_lifecycle,
    )

    _atomic_write(LIFECYCLE_PATH, json.dumps(result, indent=2))

    state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S20_PAPER_LIFECYCLE_STATE",
        "last_lifecycle_id": result["lifecycle_id"],
        "last_lifecycle_status": result["lifecycle_status"],
        "last_symbol": result["symbol"],
        "last_side": result["side"],
        "runs": int(((prior or {}).get("runs") or 0)) + 1,
    }
    _atomic_write(S20_STATE_PATH, json.dumps(state, indent=2))

    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)
    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S20 Paper Lifecycle Tracker — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Source:** {r['source']}",
        f"**Input Status:** {r['input_status']}",
        f"**Lifecycle ID:** {r['lifecycle_id']}",
        f"**Lifecycle Status:** {r['lifecycle_status']}",
        f"**Side:** {r['side']}",
        f"**Entry:** {r['entry_price']}",
        f"**Stop Loss:** {r['stop_loss']}",
        f"**TP1:** {r['tp1']}",
        f"**TP2:** {r['tp2']}",
        f"**Current Price:** {r['current_price']}",
        f"**Entry Touched:** {r['entry_touched']}",
        f"**TP1 Hit:** {r['tp1_hit']}",
        f"**TP2 Hit:** {r['tp2_hit']}",
        f"**Stop Hit:** {r['stop_hit']}",
        f"**Invalidated:** {r['invalidated']}",
        f"**Unrealized R:** {r['unrealized_r']}",
        f"**Realized R:** {r['realized_r']}",
        f"**MFE (R):** {r['max_favorable_excursion_r']}",
        f"**MAE (R):** {r['max_adverse_excursion_r']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
        "",
        "## Lifecycle Events",
        "",
    ]
    for e in r["lifecycle_events"]:
        lines.append(f"- {e.get('timestamp_utc')} — {e.get('event')} — {e.get('detail')}")
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")
