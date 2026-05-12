"""S21 — Outcome Monitor. Converts paper lifecycle state into a clean outcome
record for future Edge Matrix learning. Paper-only, no real orders, no
private API, no Telegram.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S21_OUTCOME_MONITOR"
FEEDS_NEXT = {"next_blocks": ["S22_EDGE_MATRIX_V2"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

LIFECYCLE_PATH = STATE_DIR / "latest_paper_lifecycle.json"
TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"
DECISION_GATE_PATH = STATE_DIR / "latest_decision_gate.json"
SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"
SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"

OUTCOME_PATH = STATE_DIR / "latest_outcome_monitor.json"
S21_STATE_PATH = STATE_DIR / "s21_outcome_monitor_state.json"
HISTORY_PATH = DATA_DIR / "outcome_monitor_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s21_outcome_monitor_latest_report.md"

ALLOWED_OUTCOME_STATUS = {"OPEN", "CLOSED", "NO_OUTCOME", "INVALID"}
ALLOWED_OUTCOME_RESULT = {
    "TP1",
    "TP2",
    "SL",
    "INVALIDATED",
    "STILL_OPEN",
    "NO_LIFECYCLE",
    "UNKNOWN",
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


def _snap(d: dict[str, Any] | None, keys: list[str]) -> dict[str, Any]:
    if not d:
        return {}
    return {k: d.get(k) for k in keys if k in d}


def _setup_snap(s: dict[str, Any] | None) -> dict[str, Any]:
    return _snap(
        s,
        [
            "timestamp_utc",
            "setup_context_label",
            "setup_context_score",
            "direction_bias",
            "long_probability",
            "short_probability",
            "confidence",
            "tradeable",
            "context_reason",
        ],
    )


def _scenario_snap(s: dict[str, Any] | None) -> dict[str, Any]:
    return _snap(
        s,
        [
            "timestamp_utc",
            "scenario_label",
            "scenario_score",
            "direction_bias",
            "trigger_state",
            "trigger_strength",
            "trigger_confidence",
            "estimated_move_probability",
            "estimated_failure_probability",
            "estimated_fakeout_probability",
            "market_regime",
            "tradeable",
            "ready_for_entry",
        ],
    )


def _decision_snap(d: dict[str, Any] | None) -> dict[str, Any]:
    return _snap(
        d,
        [
            "timestamp_utc",
            "decision",
            "decision_status",
            "allowed_for_paper_alert",
            "allowed_for_paper_lifecycle",
            "decision_score",
            "final_grade",
            "selected_side",
            "selected_entry",
            "selected_stop_loss",
            "selected_tp1",
            "selected_tp2",
            "selected_rr_tp1",
            "selected_rr_tp2",
        ],
    )


def _plan_snap(p: dict[str, Any] | None) -> dict[str, Any]:
    return _snap(
        p,
        [
            "timestamp_utc",
            "plan_status",
            "side",
            "entry_price",
            "stop_loss",
            "tp1",
            "tp2",
            "rr_tp1",
            "rr_tp2",
            "invalidation_price",
            "plan_quality_score",
            "plan_grade",
        ],
    )


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _calc_r(side: str, entry: float | None, sl: float | None, price: float | None) -> float | None:
    if entry is None or sl is None or price is None:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    if side == "LONG":
        return round((price - entry) / risk, 4)
    if side == "SHORT":
        return round((entry - price) / risk, 4)
    return None


def _no_outcome(
    symbol: str,
    source: str,
    reason: str,
    lifecycle: dict[str, Any] | None,
    setup_context: dict[str, Any] | None,
    scenario_trigger: dict[str, Any] | None,
    decision_gate: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    invalid: bool = False,
) -> dict[str, Any]:
    outcome_status = "INVALID" if invalid else "NO_OUTCOME"
    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": source,
        "input_status": "MISSING" if lifecycle is None else "OK",
        "outcome_status": outcome_status,
        "outcome_result": "NO_LIFECYCLE",
        "lifecycle_id": (lifecycle or {}).get("lifecycle_id"),
        "side": (lifecycle or {}).get("side", "UNKNOWN"),
        "entry_price": (lifecycle or {}).get("entry_price"),
        "stop_loss": (lifecycle or {}).get("stop_loss"),
        "tp1": (lifecycle or {}).get("tp1"),
        "tp2": (lifecycle or {}).get("tp2"),
        "final_price": (lifecycle or {}).get("current_price"),
        "realized_r": None,
        "mfe_r": (lifecycle or {}).get("max_favorable_excursion_r", 0.0),
        "mae_r": (lifecycle or {}).get("max_adverse_excursion_r", 0.0),
        "close_reason": reason,
        "setup_context_snapshot": _setup_snap(setup_context),
        "scenario_trigger_snapshot": _scenario_snap(scenario_trigger),
        "decision_snapshot": _decision_snap(decision_gate),
        "trade_plan_snapshot": _plan_snap(trade_plan),
        "outcome_reason": reason,
        "data_quality": {
            "score": 0.0,
            "level": "MISSING",
            "issues": [reason],
        },
        "reason_codes": [
            f"SYMBOL_{symbol}",
            f"OUTCOME_STATUS_{outcome_status}",
            "OUTCOME_RESULT_NO_LIFECYCLE",
            f"REASON_{reason}",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
            "NO_TELEGRAM",
            "PAPER_ONLY",
        ],
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def compute_outcome(
    lifecycle: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    decision_gate: dict[str, Any] | None,
    setup_context: dict[str, Any] | None,
    scenario_trigger: dict[str, Any] | None,
) -> dict[str, Any]:
    ts = _utc_now()
    symbol = (
        (lifecycle or {}).get("symbol")
        or (decision_gate or {}).get("symbol")
        or (trade_plan or {}).get("symbol")
        or "UNKNOWN"
    )
    source = (lifecycle or {}).get("block_id") or "S20_PAPER_LIFECYCLE_TRACKER"

    if lifecycle is None:
        return _no_outcome(
            symbol, source, "MISSING_LIFECYCLE_INPUT",
            lifecycle, setup_context, scenario_trigger, decision_gate, trade_plan,
        )

    lifecycle_status = lifecycle.get("lifecycle_status")
    lifecycle_id = lifecycle.get("lifecycle_id")

    if lifecycle_status == "NO_LIFECYCLE" or lifecycle_id is None:
        return _no_outcome(
            symbol, source, "NO_LIFECYCLE_PRESENT",
            lifecycle, setup_context, scenario_trigger, decision_gate, trade_plan,
        )

    side = str(lifecycle.get("side", "UNKNOWN")).upper()
    entry = _safe_float(lifecycle.get("entry_price"))
    sl = _safe_float(lifecycle.get("stop_loss"))
    tp1 = _safe_float(lifecycle.get("tp1"))
    tp2 = _safe_float(lifecycle.get("tp2"))
    current_price = _safe_float(lifecycle.get("current_price"))
    mfe = _safe_float(lifecycle.get("max_favorable_excursion_r")) or 0.0
    mae = _safe_float(lifecycle.get("max_adverse_excursion_r")) or 0.0
    realized_r_lc = _safe_float(lifecycle.get("realized_r"))

    # Map lifecycle status -> outcome
    outcome_status = "OPEN"
    outcome_result = "STILL_OPEN"
    close_reason = "LIFECYCLE_OPEN"
    final_price = current_price
    realized_r: float | None = None

    tp2_hit = bool(lifecycle.get("tp2_hit"))
    tp1_hit = bool(lifecycle.get("tp1_hit"))
    stop_hit = bool(lifecycle.get("stop_hit"))
    invalidated = bool(lifecycle.get("invalidated"))

    if lifecycle_status == "TP2_HIT" or (lifecycle_status == "CLOSED" and tp2_hit):
        outcome_status = "CLOSED"
        outcome_result = "TP2"
        close_reason = "TP2_REACHED"
        final_price = tp2 if tp2 is not None else current_price
        realized_r = realized_r_lc if realized_r_lc is not None else _calc_r(side, entry, sl, tp2)
    elif lifecycle_status == "TP1_HIT":
        outcome_result = "TP1"
        close_reason = "TP1_REACHED"
        # CLOSED only if lifecycle explicitly says CLOSED; here it says TP1_HIT -> still OPEN
        outcome_status = "OPEN"
        final_price = tp1 if tp1 is not None else current_price
        realized_r = realized_r_lc if realized_r_lc is not None else _calc_r(side, entry, sl, tp1)
    elif lifecycle_status == "CLOSED" and tp1_hit and not tp2_hit:
        outcome_status = "CLOSED"
        outcome_result = "TP1"
        close_reason = "TP1_CLOSED"
        final_price = tp1 if tp1 is not None else current_price
        realized_r = realized_r_lc if realized_r_lc is not None else _calc_r(side, entry, sl, tp1)
    elif lifecycle_status == "SL_HIT" or (lifecycle_status == "CLOSED" and stop_hit):
        outcome_status = "CLOSED"
        outcome_result = "SL"
        close_reason = "STOP_LOSS_HIT"
        final_price = sl if sl is not None else current_price
        realized_r = realized_r_lc if realized_r_lc is not None else -1.0
    elif lifecycle_status == "INVALIDATED" or (lifecycle_status == "CLOSED" and invalidated):
        outcome_status = "CLOSED"
        outcome_result = "INVALIDATED"
        close_reason = "SETUP_INVALIDATED"
        final_price = current_price
        realized_r = realized_r_lc
    elif lifecycle_status in ("OPEN", "ACTIVE", "NOT_STARTED"):
        outcome_status = "OPEN"
        outcome_result = "STILL_OPEN"
        close_reason = f"LIFECYCLE_{lifecycle_status}"
        final_price = current_price
        realized_r = None
    else:
        outcome_status = "INVALID"
        outcome_result = "UNKNOWN"
        close_reason = f"UNKNOWN_LIFECYCLE_STATUS_{lifecycle_status}"
        realized_r = None

    assert outcome_status in ALLOWED_OUTCOME_STATUS
    assert outcome_result in ALLOWED_OUTCOME_RESULT

    # Data quality from lifecycle
    lc_dq = lifecycle.get("data_quality") or {}
    dq = {
        "score": lc_dq.get("score", 0.0),
        "level": lc_dq.get("level", "UNKNOWN"),
        "issues": list(lc_dq.get("issues") or []),
    }

    reason_codes = [
        f"SYMBOL_{symbol}",
        f"SIDE_{side}",
        f"LIFECYCLE_STATUS_{lifecycle_status}",
        f"OUTCOME_STATUS_{outcome_status}",
        f"OUTCOME_RESULT_{outcome_result}",
        f"CLOSE_REASON_{close_reason}",
        f"DQ_{dq['level']}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
        "NO_TELEGRAM",
        "PAPER_ONLY",
    ]
    if tp1_hit:
        reason_codes.append("TP1_HIT")
    if tp2_hit:
        reason_codes.append("TP2_HIT")
    if stop_hit:
        reason_codes.append("SL_HIT")
    if invalidated:
        reason_codes.append("INVALIDATED")

    return {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": source,
        "input_status": "OK",
        "outcome_status": outcome_status,
        "outcome_result": outcome_result,
        "lifecycle_id": lifecycle_id,
        "side": side,
        "entry_price": entry,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "final_price": final_price,
        "realized_r": realized_r,
        "mfe_r": round(mfe, 4),
        "mae_r": round(mae, 4),
        "close_reason": close_reason,
        "setup_context_snapshot": _setup_snap(setup_context),
        "scenario_trigger_snapshot": _scenario_snap(scenario_trigger),
        "decision_snapshot": _decision_snap(decision_gate),
        "trade_plan_snapshot": _plan_snap(trade_plan),
        "outcome_reason": close_reason,
        "data_quality": dq,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def run_outcome_monitor() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lifecycle = _load_json(LIFECYCLE_PATH)
    trade_plan = _load_json(TRADE_PLAN_PATH)
    decision_gate = _load_json(DECISION_GATE_PATH)
    setup_context = _load_json(SETUP_CONTEXT_PATH)
    scenario_trigger = _load_json(SCENARIO_TRIGGER_PATH)
    prior_state = _load_json(S21_STATE_PATH)

    result = compute_outcome(lifecycle, trade_plan, decision_gate, setup_context, scenario_trigger)

    _atomic_write(OUTCOME_PATH, json.dumps(result, indent=2))

    state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S21_OUTCOME_MONITOR_STATE",
        "last_lifecycle_id": result["lifecycle_id"],
        "last_outcome_status": result["outcome_status"],
        "last_outcome_result": result["outcome_result"],
        "last_symbol": result["symbol"],
        "last_side": result["side"],
        "runs": int(((prior_state or {}).get("runs") or 0)) + 1,
    }
    _atomic_write(S21_STATE_PATH, json.dumps(state, indent=2))

    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)
    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S21 Outcome Monitor — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Source:** {r['source']}",
        f"**Input Status:** {r['input_status']}",
        f"**Lifecycle ID:** {r['lifecycle_id']}",
        f"**Outcome Status:** {r['outcome_status']}",
        f"**Outcome Result:** {r['outcome_result']}",
        f"**Close Reason:** {r['close_reason']}",
        f"**Side:** {r['side']}",
        f"**Entry:** {r['entry_price']}",
        f"**Stop Loss:** {r['stop_loss']}",
        f"**TP1:** {r['tp1']}",
        f"**TP2:** {r['tp2']}",
        f"**Final Price:** {r['final_price']}",
        f"**Realized R:** {r['realized_r']}",
        f"**MFE (R):** {r['mfe_r']}",
        f"**MAE (R):** {r['mae_r']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
        "",
        "## Snapshots",
        "",
        f"- setup_context_snapshot keys: {list(r['setup_context_snapshot'].keys())}",
        f"- scenario_trigger_snapshot keys: {list(r['scenario_trigger_snapshot'].keys())}",
        f"- decision_snapshot keys: {list(r['decision_snapshot'].keys())}",
        f"- trade_plan_snapshot keys: {list(r['trade_plan_snapshot'].keys())}",
    ]
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")
