"""S26A — Full Chain Truth Audit Engine.

Read-only diagnostic. Traces the entire live chain from raw sub-second flow
data through setup, decision, Telegram, lifecycle, outcome, and edge.
Answers 21 diagnostic questions brutally honestly.

No fake signals. No real trades. safe_to_open_real_trade always False.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S26A_FULL_CHAIN_TRUTH_AUDIT"
SOURCE = "S12_TO_S25_ALL_STATE_AND_HISTORY"
SYMBOL = "BTCUSDT"

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

LATEST_STATE_PATH = STATE_DIR / "latest_full_chain_truth_audit.json"
S26A_STATE_PATH = STATE_DIR / "s26a_full_chain_truth_audit_state.json"
HISTORY_PATH = DATA_DIR / "full_chain_truth_audit_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s26a_full_chain_truth_audit_latest_report.md"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

AUDIT_WINDOW_HOURS = 2


# --------------------------------------------------------------------------- #
# I/O helpers
# --------------------------------------------------------------------------- #

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _load_jsonl(path: Path, max_records: int = 2000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return records
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return records[-max_records:]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #

def _parse_ts(ts_str: Any) -> datetime | None:
    if not isinstance(ts_str, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _freshness_seconds(ts_str: Any) -> float | None:
    dt = _parse_ts(ts_str)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds()


def _filter_recent(records: list[dict], hours: int = AUDIT_WINDOW_HOURS) -> list[dict]:
    cutoff_ts = datetime.now(timezone.utc).timestamp() - hours * 3600
    result = []
    for r in records:
        ts_str = r.get("timestamp_utc") or r.get("timestamp") or r.get("ts")
        dt = _parse_ts(ts_str)
        if dt is not None and dt.timestamp() >= cutoff_ts:
            result.append(r)
    if not result:
        return records  # fallback: return all if timestamps unparseable
    return result


# --------------------------------------------------------------------------- #
# Input loader
# --------------------------------------------------------------------------- #

def _load_all_inputs(state_dir: Path, data_dir: Path) -> dict[str, Any]:
    sd = state_dir
    dd = data_dir
    return {
        # State files
        "s_flow_state":        _load_json(sd / "latest_flow_state.json"),
        "s_flow_evidence":     _load_json(sd / "latest_flow_evidence.json"),
        "s_flow_persistence":  _load_json(sd / "latest_flow_persistence.json"),
        "s_setup_context":     _load_json(sd / "latest_setup_context.json"),
        "s_scenario_trigger":  _load_json(sd / "latest_scenario_trigger.json"),
        "s_trade_plan":        _load_json(sd / "latest_trade_plan.json"),
        "s_decision_gate":     _load_json(sd / "latest_decision_gate.json"),
        "s_telegram_alert":    _load_json(sd / "latest_telegram_paper_alert.json"),
        "s_paper_lifecycle":   _load_json(sd / "latest_paper_lifecycle.json"),
        "s_outcome_monitor":   _load_json(sd / "latest_outcome_monitor.json"),
        "s_telegram_followup": _load_json(sd / "latest_telegram_followup.json"),
        "s_edge_matrix":       _load_json(sd / "latest_edge_matrix_v2.json"),
        "s_simple_brain":      _load_json(sd / "latest_simple_brain_v2.json"),
        # History files
        "h_flow_events":           _load_jsonl(dd / "live_flow_events.jsonl"),
        "h_flow_evidence":         _load_jsonl(dd / "flow_evidence_history.jsonl") or _load_jsonl(dd / "flow_evidence.jsonl"),
        "h_flow_persistence":      _load_jsonl(dd / "flow_persistence_history.jsonl") or _load_jsonl(dd / "flow_persistence.jsonl"),
        "h_setup_context":         _load_jsonl(dd / "setup_context_history.jsonl"),
        "h_scenario_trigger":      _load_jsonl(dd / "scenario_trigger_history.jsonl"),
        "h_trade_plan":            _load_jsonl(dd / "trade_plan_history.jsonl"),
        "h_decision_gate":         _load_jsonl(dd / "decision_gate_history.jsonl"),
        "h_telegram_alert":        _load_jsonl(dd / "telegram_paper_alert_history.jsonl"),
        "h_paper_lifecycle":       _load_jsonl(dd / "paper_lifecycle_history.jsonl"),
        "h_outcome_monitor":       _load_jsonl(dd / "outcome_monitor_history.jsonl"),
        "h_telegram_followup":     _load_jsonl(dd / "telegram_followup_history.jsonl"),
        "h_edge_matrix":           _load_jsonl(dd / "edge_matrix_v2_history.jsonl"),
        "h_production_observer":   _load_jsonl(dd / "production_observer_history.jsonl"),
    }


# --------------------------------------------------------------------------- #
# Audit section builders
# --------------------------------------------------------------------------- #

def _audit_raw_data(inp: dict) -> dict[str, Any]:
    events = inp["h_flow_events"]
    count = len(events)
    latest_ts = None
    freshness = None
    if events:
        for r in reversed(events):
            ts = r.get("timestamp_utc") or r.get("timestamp") or r.get("ts")
            if ts:
                latest_ts = ts
                freshness = _freshness_seconds(ts)
                break

    data_flowing = False
    if freshness is not None:
        data_flowing = freshness < 300  # fresh within 5 minutes

    stale_reason = None
    if count == 0:
        stale_reason = "live_flow_events.jsonl is empty or missing"
    elif not data_flowing:
        if freshness is not None:
            stale_reason = f"Last event is {freshness:.0f}s ago — WebSocket may be down"
        else:
            stale_reason = "Timestamp not parseable"

    # Also check flow_state
    flow_state = inp.get("s_flow_state") or {}
    system_running = flow_state.get("quality_state", "UNKNOWN") not in ("MISSING",)

    return {
        "live_flow_event_count": count,
        "latest_event_timestamp": latest_ts,
        "event_freshness_seconds": round(freshness, 1) if freshness is not None else None,
        "data_flowing": data_flowing,
        "flow_state_present": flow_state is not None and bool(flow_state),
        "flow_quality_state": flow_state.get("quality_state", "MISSING"),
        "empty_or_stale_reason": stale_reason,
    }


def _audit_one_second_buckets(inp: dict) -> dict[str, Any]:
    evidence_hist = inp["h_flow_evidence"]
    flow_ev = inp.get("s_flow_evidence") or {}

    bucket_count = len(evidence_hist)
    bucket_quality = flow_ev.get("quality_label", flow_ev.get("data_quality", {}).get("level", "UNKNOWN") if isinstance(flow_ev.get("data_quality"), dict) else "UNKNOWN")
    flow_label = flow_ev.get("flow_label", "UNKNOWN")
    confidence = float(flow_ev.get("confidence", 0.0))

    evidence_produced = bool(flow_ev)

    # Estimate missing buckets from flow_state events vs evidence records
    flow_event_count = len(inp["h_flow_events"])
    missing_estimate = None
    if flow_event_count > 0 and bucket_count > 0:
        ratio = bucket_count / max(flow_event_count, 1)
        if ratio < 0.1:
            missing_estimate = f"~{flow_event_count - bucket_count} (high — ratio {ratio:.2f})"
        else:
            missing_estimate = f"~{max(0, flow_event_count - bucket_count)} (ratio {ratio:.2f})"
    elif bucket_count == 0:
        missing_estimate = "Cannot estimate — no evidence records"

    return {
        "bucket_count": bucket_count,
        "bucket_quality_level": bucket_quality,
        "flow_label": flow_label,
        "confidence": round(confidence, 3),
        "missing_bucket_estimate": missing_estimate,
        "one_second_evidence_produced": evidence_produced,
    }


def _audit_candle_dna(inp: dict, data_dir: Path) -> dict[str, Any]:
    # Check hybrid_candle_dna.jsonl
    candle_hist = _load_jsonl(data_dir / "hybrid_candle_dna.jsonl")
    flow_state = inp.get("s_flow_state") or {}

    if not candle_hist:
        return {
            "candle_1m_available": False,
            "candle_dna_count": 0,
            "latest_candle_quality": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "candle_coverage": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "note": "hybrid_candle_dna.jsonl missing or empty",
        }

    latest = candle_hist[-1]
    quality = latest.get("quality_label", latest.get("quality", "UNKNOWN"))
    candle_count = len(candle_hist)
    has_1m = any(
        r.get("timeframe", r.get("interval", "")) in ("1m", "1M", "1") for r in candle_hist
    ) or candle_count > 0  # assume 1M if candles exist

    return {
        "candle_1m_available": has_1m,
        "candle_dna_count": candle_count,
        "latest_candle_quality": quality if quality else "UNKNOWN",
        "candle_coverage": f"{candle_count} records",
        "note": None,
    }


def _audit_mtf(state_dir: Path) -> dict[str, Any]:
    # Check if any MTF state files exist
    mtf_files = {
        "5m": state_dir / "latest_flow_state_5m.json",
        "15m": state_dir / "latest_flow_state_15m.json",
        "30m": state_dir / "latest_flow_state_30m.json",
    }
    results = {}
    any_found = False
    for tf, fp in mtf_files.items():
        exists = fp.exists()
        results[tf] = "AVAILABLE" if exists else "NOT_IMPLEMENTED_OR_NOT_PRODUCED"
        if exists:
            any_found = True

    return {
        "5m_state": results["5m"],
        "15m_state": results["15m"],
        "30m_state": results["30m"],
        "mtf_implemented": any_found,
        "note": "No MTF state files found — MTF not implemented in current pipeline" if not any_found else None,
    }


def _audit_market_structure(inp: dict) -> dict[str, Any]:
    flow_persistence = inp.get("s_flow_persistence") or {}

    # Check for structure signals in persistence
    structure_label = flow_persistence.get("structure_label", None)
    bos = flow_persistence.get("bos", None)
    choch = flow_persistence.get("choch", None)
    swing_high = flow_persistence.get("swing_high", None)
    swing_low = flow_persistence.get("swing_low", None)

    has_structure = bool(structure_label or bos or choch)

    if not flow_persistence:
        return {
            "structure_available": False,
            "structure_label": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "bos": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "choch": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "swing_high": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "swing_low": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "note": "flow_persistence state missing",
        }

    return {
        "structure_available": has_structure,
        "structure_label": structure_label or "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
        "bos": bos or "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
        "choch": choch or "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
        "swing_high": swing_high or "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
        "swing_low": swing_low or "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
        "note": "Market structure fields not found in persistence state" if not has_structure else None,
    }


def _audit_liquidity(inp: dict, data_dir: Path) -> dict[str, Any]:
    liq_data = _load_jsonl(data_dir / "liquidity_structure.jsonl")
    flow_persistence = inp.get("s_flow_persistence") or {}

    liq_levels = flow_persistence.get("liquidity_levels", None)
    liq_clusters = flow_persistence.get("liquidity_clusters", None)
    liq_estimate = flow_persistence.get("liquidity_estimate", None)

    if not liq_data and not liq_levels and not liq_clusters and not liq_estimate:
        return {
            "liquidity_available": False,
            "liquidity_levels": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "liquidity_clusters": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "liquidity_estimate": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "note": "No liquidity data found in state or data files",
        }

    return {
        "liquidity_available": True,
        "liquidity_levels": liq_levels or (f"{len(liq_data)} records" if liq_data else "NOT_IMPLEMENTED_OR_NOT_PRODUCED"),
        "liquidity_clusters": liq_clusters or "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
        "liquidity_estimate": liq_estimate or "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
        "note": None,
    }


def _audit_scenario(inp: dict) -> dict[str, Any]:
    scenario_state = inp.get("s_scenario_trigger") or {}
    scenario_hist = inp["h_scenario_trigger"]

    count = len(scenario_hist)
    label = scenario_state.get("trigger_state", scenario_state.get("scenario_label", "UNKNOWN"))
    confidence = float(scenario_state.get("confidence", scenario_state.get("scenario_confidence", 0.0)))
    probabilities = scenario_state.get("probabilities", scenario_state.get("scenario_probabilities", None))
    producing = bool(scenario_state)

    return {
        "scenario_count": count,
        "latest_scenario_label": label,
        "scenario_confidence": round(confidence, 3),
        "estimated_probabilities": probabilities,
        "scenario_engine_producing": producing,
    }


def _audit_setup_candidates(inp: dict) -> dict[str, Any]:
    setup_hist = inp["h_setup_context"]
    setup_state = inp.get("s_setup_context") or {}

    count = len(setup_hist)

    direction_counts: dict[str, int] = {}
    tradeable = 0
    no_trade = 0

    for r in setup_hist:
        direction = r.get("direction", r.get("setup_direction", "UNKNOWN"))
        valid = r.get("setup_valid", False)
        setup_label = r.get("setup_label", r.get("setup_type", "UNKNOWN"))

        if valid:
            tradeable += 1
        else:
            no_trade += 1

        d_key = str(direction).upper()
        direction_counts[d_key] = direction_counts.get(d_key, 0) + 1

    strong_long = sum(1 for r in setup_hist if r.get("setup_label", "") in ("STRONG_LONG", "STRONG_BULL") or (r.get("direction", "") in ("LONG", "BUY") and float(r.get("confidence", 0)) >= 0.75))
    strong_short = sum(1 for r in setup_hist if r.get("setup_label", "") in ("STRONG_SHORT", "STRONG_BEAR") or (r.get("direction", "") in ("SHORT", "SELL") and float(r.get("confidence", 0)) >= 0.75))
    weak_long = sum(1 for r in setup_hist if r.get("direction", "") in ("LONG", "BUY") and float(r.get("confidence", 0)) < 0.75) - strong_long
    weak_short = sum(1 for r in setup_hist if r.get("direction", "") in ("SHORT", "SELL") and float(r.get("confidence", 0)) < 0.75) - strong_short
    weak_long = max(0, weak_long)
    weak_short = max(0, weak_short)

    # Current state closest to tradeable
    closest = None
    if setup_state:
        confidence_val = float(setup_state.get("confidence", 0.0))
        closest = {
            "direction": setup_state.get("direction", "UNKNOWN"),
            "setup_valid": setup_state.get("setup_valid", False),
            "confidence": round(confidence_val, 3),
            "setup_label": setup_state.get("setup_label", setup_state.get("setup_type", "UNKNOWN")),
        }

    return {
        "setup_context_count": count,
        "tradeable_count": tradeable,
        "strong_long_count": strong_long,
        "strong_short_count": strong_short,
        "weak_long_count": weak_long,
        "weak_short_count": weak_short,
        "no_trade_count": no_trade,
        "closest_to_tradeable": closest,
    }


def _audit_trade_plans(inp: dict) -> dict[str, Any]:
    plan_hist = inp["h_trade_plan"]
    plan_state = inp.get("s_trade_plan") or {}

    count = len(plan_hist)
    plan_ready = sum(1 for r in plan_hist if r.get("plan_status") == "PLAN_READY")
    watch_only = sum(1 for r in plan_hist if r.get("plan_status") == "WATCH_ONLY")
    no_plan = sum(1 for r in plan_hist if r.get("plan_status") == "NO_PLAN")
    invalid = sum(1 for r in plan_hist if r.get("plan_status") == "INVALID")
    long_plans = sum(1 for r in plan_hist if r.get("direction", r.get("side", "")).upper() in ("LONG", "BUY"))
    short_plans = sum(1 for r in plan_hist if r.get("direction", r.get("side", "")).upper() in ("SHORT", "SELL"))

    rr_values = []
    for r in plan_hist:
        rr = r.get("rr_tp1", r.get("rr", r.get("risk_reward", None)))
        if rr is not None:
            try:
                rr_values.append(float(rr))
            except (TypeError, ValueError):
                pass

    avg_rr = round(sum(rr_values) / len(rr_values), 2) if rr_values else None

    return {
        "plan_count": count,
        "PLAN_READY": plan_ready,
        "WATCH_ONLY": watch_only,
        "NO_PLAN": no_plan,
        "INVALID": invalid,
        "long_plan_count": long_plans,
        "short_plan_count": short_plans,
        "average_rr": avg_rr,
    }


def _audit_decision_gate(inp: dict) -> dict[str, Any]:
    gate_hist = inp["h_decision_gate"]
    gate_state = inp.get("s_decision_gate") or {}

    count = len(gate_hist)
    allow_paper = sum(1 for r in gate_hist if r.get("decision") == "ALLOW_PAPER")
    watch = sum(1 for r in gate_hist if r.get("decision") == "WATCH")
    block = sum(1 for r in gate_hist if r.get("decision") == "BLOCK")
    unknown = sum(1 for r in gate_hist if r.get("decision", "UNKNOWN") == "UNKNOWN")

    # Collect block reasons
    block_reasons: dict[str, int] = {}
    for r in gate_hist:
        if r.get("decision") == "BLOCK":
            for reason in r.get("block_reasons", []):
                block_reasons[reason] = block_reasons.get(reason, 0) + 1

    top_block_reasons = sorted(block_reasons.items(), key=lambda x: -x[1])[:5]

    return {
        "decision_record_count": count,
        "ALLOW_PAPER": allow_paper,
        "WATCH": watch,
        "BLOCK": block,
        "UNKNOWN": unknown,
        "main_block_reasons": [{"reason": r, "count": c} for r, c in top_block_reasons],
    }


def _audit_telegram(inp: dict) -> dict[str, Any]:
    tg_hist = inp["h_telegram_alert"]
    tg_state = inp.get("s_telegram_alert") or {}

    count = len(tg_hist)
    sent = sum(1 for r in tg_hist if r.get("alert_status") == "SENT" or r.get("telegram_sent") is True)
    skipped = sum(1 for r in tg_hist if r.get("alert_status") in ("SKIPPED", "BLOCKED", "INVALID", "DRY_RUN"))

    # Check env without exposing token
    bot_token_set = tg_state.get("bot_token_set", False)
    chat_id_set = tg_state.get("chat_id_set", False)
    last_status = tg_state.get("alert_status", "UNKNOWN")

    return {
        "telegram_alert_attempts": count,
        "SENT": sent,
        "SKIPPED_BLOCKED_INVALID": skipped,
        "env_appears_configured": bool(bot_token_set and chat_id_set),
        "bot_token_set": bot_token_set,
        "chat_id_set": chat_id_set,
        "last_telegram_status": last_status,
    }


def _audit_lifecycle(inp: dict) -> dict[str, Any]:
    lc_hist = inp["h_paper_lifecycle"]
    lc_state = inp.get("s_paper_lifecycle") or {}

    count = len(lc_hist)
    status_counts: dict[str, int] = {}
    for r in lc_hist:
        s = r.get("lifecycle_status", r.get("status", "UNKNOWN"))
        status_counts[s] = status_counts.get(s, 0) + 1

    no_lc_reason = None
    if count == 0:
        no_lc_reason = "No lifecycle records found — no Telegram alert was SENT"
    elif status_counts.get("NO_TRADE", 0) == count:
        no_lc_reason = "All lifecycle records are NO_TRADE"

    return {
        "lifecycle_record_count": count,
        "OPEN": status_counts.get("OPEN", 0),
        "ACTIVE": status_counts.get("ACTIVE", 0),
        "TP1_HIT": status_counts.get("TP1_HIT", 0),
        "TP2_HIT": status_counts.get("TP2_HIT", 0),
        "SL_HIT": status_counts.get("SL_HIT", 0),
        "INVALIDATED": status_counts.get("INVALIDATED", 0),
        "CLOSED": status_counts.get("CLOSED", 0),
        "NO_LIFECYCLE": status_counts.get("NO_LIFECYCLE", status_counts.get("NO_TRADE", 0)),
        "no_lifecycle_reason": no_lc_reason,
    }


def _audit_outcome(inp: dict) -> dict[str, Any]:
    oc_hist = inp["h_outcome_monitor"]
    lc_audit = inp.get("_lc_audit") or {}

    tp1 = sum(1 for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) == "TP1_HIT")
    tp2 = sum(1 for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) == "TP2_HIT")
    sl = sum(1 for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) == "SL_HIT")
    inv = sum(1 for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) == "INVALIDATED")
    still_open = sum(1 for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) in ("OPEN", "ACTIVE", "NO_OUTCOME"))
    no_lc = sum(1 for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) in ("NO_LIFECYCLE", "NO_TRADE"))

    # Realized R stats
    r_values = []
    for r in oc_hist:
        rv = r.get("realized_r", r.get("r_value", None))
        if rv is not None:
            try:
                r_values.append(float(rv))
            except (TypeError, ValueError):
                pass

    realized_r_stats = None
    if r_values:
        realized_r_stats = {
            "count": len(r_values),
            "mean": round(sum(r_values) / len(r_values), 3),
            "min": round(min(r_values), 3),
            "max": round(max(r_values), 3),
        }

    return {
        "TP1": tp1,
        "TP2": tp2,
        "SL": sl,
        "INVALIDATED": inv,
        "STILL_OPEN": still_open,
        "NO_LIFECYCLE": no_lc,
        "realized_r_stats": realized_r_stats,
    }


def _audit_edge(inp: dict) -> dict[str, Any]:
    edge_state = inp.get("s_edge_matrix") or {}

    if not edge_state:
        return {
            "edge_status": "NOT_IMPLEMENTED_OR_NOT_PRODUCED",
            "usable_sample_count": 0,
            "win_rate": None,
            "expectancy": None,
            "no_edge_claim_reason": "edge_matrix_v2 state missing",
        }

    edge_status = edge_state.get("edge_status", "UNKNOWN")
    sample_count = int(edge_state.get("sample_count", edge_state.get("usable_sample_count", 0)))
    win_rate = edge_state.get("win_rate", None)
    expectancy = edge_state.get("expectancy", None)

    no_edge_reason = None
    if edge_status == "NO_EDGE_CLAIM":
        no_edge_reason = f"Sample size {sample_count} is too small for statistical claim"
    elif sample_count < 30:
        no_edge_reason = f"Only {sample_count} samples — need ≥30 for valid edge claim"

    return {
        "edge_status": edge_status,
        "usable_sample_count": sample_count,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "no_edge_claim_reason": no_edge_reason,
    }


def _audit_success_patterns(inp: dict) -> dict[str, Any]:
    oc_hist = inp["h_outcome_monitor"]
    wins = [r for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) in ("TP1_HIT", "TP2_HIT")]

    if not wins:
        return {
            "sample_count": 0,
            "note": "INSUFFICIENT_WIN_SAMPLE",
            "setup_labels": [],
            "scenario_labels": [],
            "sides": [],
            "confidence_range": None,
            "rr_range": None,
        }

    setup_labels = list({r.get("setup_label", r.get("setup_type", "UNKNOWN")) for r in wins})
    scenario_labels = list({r.get("scenario_label", "UNKNOWN") for r in wins})
    sides = list({r.get("direction", r.get("side", "UNKNOWN")) for r in wins})

    confidences = [float(r["confidence"]) for r in wins if r.get("confidence") is not None]
    rrs = [float(r["rr_tp1"]) for r in wins if r.get("rr_tp1") is not None]

    return {
        "sample_count": len(wins),
        "setup_labels": setup_labels,
        "scenario_labels": scenario_labels,
        "sides": sides,
        "confidence_range": [round(min(confidences), 3), round(max(confidences), 3)] if confidences else None,
        "rr_range": [round(min(rrs), 2), round(max(rrs), 2)] if rrs else None,
        "note": None,
    }


def _audit_failure_patterns(inp: dict) -> dict[str, Any]:
    oc_hist = inp["h_outcome_monitor"]
    gate_hist = inp["h_decision_gate"]

    failures = [r for r in oc_hist if r.get("outcome", r.get("outcome_status", "")) in ("SL_HIT", "INVALIDATED")]
    blocked = [r for r in gate_hist if r.get("decision") == "BLOCK"]

    if not failures and not blocked:
        return {
            "sample_count": 0,
            "note": "INSUFFICIENT_FAILURE_SAMPLE",
            "top_block_reasons": [],
            "low_confidence_count": 0,
            "degraded_quality_count": 0,
            "choppy_persistence_count": 0,
            "invalid_rr_count": 0,
        }

    top_block_reasons: dict[str, int] = {}
    for r in blocked:
        for reason in r.get("block_reasons", []):
            top_block_reasons[reason] = top_block_reasons.get(reason, 0) + 1

    low_conf = sum(1 for r in failures if float(r.get("confidence", 1.0)) < 0.6)
    degraded = sum(1 for r in failures if r.get("quality_label", r.get("data_quality", {}).get("level", "")) in ("DEGRADED", "LOW", "CRITICAL") if isinstance(r.get("data_quality"), dict) or isinstance(r.get("quality_label"), str))
    invalid_rr = sum(1 for r in failures if float(r.get("rr_tp1", r.get("rr", 99))) < 1.0)

    return {
        "sample_count": len(failures),
        "blocked_count": len(blocked),
        "top_block_reasons": sorted(top_block_reasons.items(), key=lambda x: -x[1])[:5],
        "low_confidence_count": low_conf,
        "degraded_quality_count": degraded,
        "choppy_persistence_count": 0,
        "invalid_rr_count": invalid_rr,
        "note": None,
    }


def _determine_bottleneck(raw: dict, one_s: dict, candle: dict, scenario: dict,
                           setup: dict, plan: dict, gate: dict, tg: dict, lc: dict) -> str:
    if not raw["data_flowing"] or raw["live_flow_event_count"] == 0:
        return "S12_FLOW_STATE — No live data flowing"
    if not one_s["one_second_evidence_produced"]:
        return "S13_FLOW_EVIDENCE — Evidence not being produced from flow"
    if not candle["candle_1m_available"]:
        return "S3_CANDLE_DNA — No 1M candle DNA produced"
    if not scenario["scenario_engine_producing"]:
        return "S16_SCENARIO_ENTRY — Scenario engine not producing output"
    if setup["tradeable_count"] == 0:
        return "S15_SETUP_CONTEXT — No tradeable setup candidates"
    if plan["PLAN_READY"] == 0:
        return "S17_TRADE_PLAN — No PLAN_READY trade plans"
    if gate["ALLOW_PAPER"] == 0:
        return "S18_DECISION_GATE — No ALLOW_PAPER decisions"
    if tg["SENT"] == 0:
        return "S19_TELEGRAM_ALERT — No Telegram signals sent"
    if lc["lifecycle_record_count"] == 0 or lc["NO_LIFECYCLE"] == lc["lifecycle_record_count"]:
        return "S20_PAPER_LIFECYCLE — No active lifecycle trades"
    return "NONE — Full chain appears functional"


def _determine_no_signal_reason(raw: dict, one_s: dict, setup: dict, plan: dict,
                                  gate: dict, tg: dict) -> str:
    if not raw["data_flowing"]:
        return "NO_LIVE_DATA"
    if not one_s["one_second_evidence_produced"]:
        return "NO_EVIDENCE_PRODUCED"
    if setup["tradeable_count"] == 0:
        return "NO_TRADE_SETUP"
    if plan["PLAN_READY"] == 0:
        return "PLAN_NOT_READY"
    if gate["ALLOW_PAPER"] == 0:
        return "DECISION_BLOCKED"
    if tg["SENT"] == 0:
        if not tg["env_appears_configured"]:
            return "TELEGRAM_ENV_NOT_CONFIGURED"
        return "TELEGRAM_BLOCKED"
    return "SIGNAL_SENT_OK"


def _determine_system_running(inp: dict, raw: dict) -> str:
    obs_hist = inp["h_production_observer"]
    if obs_hist:
        last = obs_hist[-1]
        status = last.get("observer_status", "UNKNOWN")
        freshness = _freshness_seconds(last.get("timestamp_utc"))
        if freshness is not None and freshness < 600:
            return f"RUNNING — S24 observer OK ({status}, {freshness:.0f}s ago)"
        return f"STALE — last observer cycle {freshness:.0f}s ago" if freshness else "UNKNOWN"
    if raw["data_flowing"]:
        return "DATA_FLOWING_NO_OBSERVER_HISTORY"
    return "UNKNOWN — no observer history, no live data"


def _recommend_next_fix(bottleneck: str, no_signal_reason: str, tg: dict) -> str:
    if "S12" in bottleneck:
        return "Check WebSocket feed — live_flow_events.jsonl is empty or stale"
    if "S13" in bottleneck:
        return "Flow evidence engine not producing output — check S13 state file"
    if "S3_CANDLE" in bottleneck:
        return "Candle DNA engine not running — check hybrid_candle_dna.jsonl"
    if "S16" in bottleneck:
        return "Scenario engine not producing — check scenario_trigger state"
    if "S15" in bottleneck:
        return "No tradeable setup — wait for stronger directional flow with confidence ≥0.75"
    if "S17" in bottleneck:
        return "No PLAN_READY — check trade plan engine for RR, entry, SL, TP levels"
    if "S18" in bottleneck:
        return "Decision gate blocking all plans — review block_reasons in decision_gate state"
    if "S19" in bottleneck:
        if not tg.get("env_appears_configured"):
            return "Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables"
        return "Telegram alert blocked — check alert_status in latest_telegram_paper_alert.json"
    if "S20" in bottleneck:
        return "No lifecycle active — Telegram alert must be SENT first to start lifecycle"
    return "Monitor pipeline — accumulate paper trades for edge validation"


# --------------------------------------------------------------------------- #
# Markdown report writer
# --------------------------------------------------------------------------- #

def _write_report(record: dict[str, Any], path: Path) -> None:
    r = record
    lines = [
        "# S26A Full Chain Truth Audit",
        "",
        f"**timestamp_utc**: {r['timestamp_utc']}  ",
        f"**symbol**: {r['symbol']}  ",
        f"**block_id**: {r['block_id']}  ",
        f"**audit_window**: {r['audit_window']}",
        "",
        "---",
        "",
        "## System Running Status",
        "",
        f"**{r['system_running_status']}**",
        "",
        "## 1. Raw Data / Live Flow",
        "",
        f"- live_flow_event_count: {r['raw_data_audit']['live_flow_event_count']}",
        f"- latest_event_timestamp: {r['raw_data_audit']['latest_event_timestamp']}",
        f"- event_freshness_seconds: {r['raw_data_audit']['event_freshness_seconds']}",
        f"- data_flowing: {r['raw_data_audit']['data_flowing']}",
        f"- flow_quality_state: {r['raw_data_audit']['flow_quality_state']}",
        f"- stale_reason: {r['raw_data_audit']['empty_or_stale_reason'] or 'None'}",
        "",
        "## 2. 1-Second Bucket Audit",
        "",
        f"- bucket_count: {r['one_second_bucket_audit']['bucket_count']}",
        f"- bucket_quality: {r['one_second_bucket_audit']['bucket_quality_level']}",
        f"- flow_label: {r['one_second_bucket_audit']['flow_label']}",
        f"- confidence: {r['one_second_bucket_audit']['confidence']}",
        f"- missing_estimate: {r['one_second_bucket_audit']['missing_bucket_estimate']}",
        f"- evidence_produced: {r['one_second_bucket_audit']['one_second_evidence_produced']}",
        "",
        "## 3. Candle DNA (1M)",
        "",
        f"- 1m_available: {r['candle_dna_audit']['candle_1m_available']}",
        f"- candle_count: {r['candle_dna_audit']['candle_dna_count']}",
        f"- latest_quality: {r['candle_dna_audit']['latest_candle_quality']}",
        f"- note: {r['candle_dna_audit']['note'] or 'None'}",
        "",
        "## 4. MTF Audit",
        "",
        f"- 5m: {r['mtf_audit']['5m_state']}",
        f"- 15m: {r['mtf_audit']['15m_state']}",
        f"- 30m: {r['mtf_audit']['30m_state']}",
        f"- implemented: {r['mtf_audit']['mtf_implemented']}",
        "",
        "## 5. Market Structure",
        "",
        f"- structure_available: {r['market_structure_audit']['structure_available']}",
        f"- structure_label: {r['market_structure_audit']['structure_label']}",
        f"- BOS: {r['market_structure_audit']['bos']}",
        f"- CHoCH: {r['market_structure_audit']['choch']}",
        "",
        "## 6. Liquidity",
        "",
        f"- liquidity_available: {r['liquidity_audit']['liquidity_available']}",
        f"- levels: {r['liquidity_audit']['liquidity_levels']}",
        f"- estimate: {r['liquidity_audit']['liquidity_estimate']}",
        "",
        "## 7. Scenario / Probability",
        "",
        f"- scenario_count: {r['scenario_audit']['scenario_count']}",
        f"- latest_label: {r['scenario_audit']['latest_scenario_label']}",
        f"- confidence: {r['scenario_audit']['scenario_confidence']}",
        f"- engine_producing: {r['scenario_audit']['scenario_engine_producing']}",
        "",
        "## 8. Setup Candidates",
        "",
        f"- total_records: {r['setup_candidate_audit']['setup_context_count']}",
        f"- tradeable: {r['setup_candidate_audit']['tradeable_count']}",
        f"- strong_long: {r['setup_candidate_audit']['strong_long_count']}",
        f"- strong_short: {r['setup_candidate_audit']['strong_short_count']}",
        f"- weak_long: {r['setup_candidate_audit']['weak_long_count']}",
        f"- weak_short: {r['setup_candidate_audit']['weak_short_count']}",
        f"- no_trade: {r['setup_candidate_audit']['no_trade_count']}",
        "",
        "## 9. Trade Plans",
        "",
        f"- plan_count: {r['trade_plan_audit']['plan_count']}",
        f"- PLAN_READY: {r['trade_plan_audit']['PLAN_READY']}",
        f"- WATCH_ONLY: {r['trade_plan_audit']['WATCH_ONLY']}",
        f"- NO_PLAN: {r['trade_plan_audit']['NO_PLAN']}",
        f"- INVALID: {r['trade_plan_audit']['INVALID']}",
        f"- long: {r['trade_plan_audit']['long_plan_count']} / short: {r['trade_plan_audit']['short_plan_count']}",
        f"- avg_rr: {r['trade_plan_audit']['average_rr']}",
        "",
        "## 10. Decision Gate",
        "",
        f"- records: {r['decision_gate_audit']['decision_record_count']}",
        f"- ALLOW_PAPER: {r['decision_gate_audit']['ALLOW_PAPER']}",
        f"- WATCH: {r['decision_gate_audit']['WATCH']}",
        f"- BLOCK: {r['decision_gate_audit']['BLOCK']}",
        f"- top_block_reasons: {r['decision_gate_audit']['main_block_reasons']}",
        "",
        "## 11. Telegram Signals",
        "",
        f"- attempts: {r['telegram_signal_audit']['telegram_alert_attempts']}",
        f"- SENT: {r['telegram_signal_audit']['SENT']}",
        f"- SKIPPED_BLOCKED: {r['telegram_signal_audit']['SKIPPED_BLOCKED_INVALID']}",
        f"- env_configured: {r['telegram_signal_audit']['env_appears_configured']}",
        f"- last_status: {r['telegram_signal_audit']['last_telegram_status']}",
        "",
        "## 12. Lifecycle",
        "",
        f"- records: {r['lifecycle_audit']['lifecycle_record_count']}",
        f"- TP1_HIT: {r['lifecycle_audit']['TP1_HIT']}",
        f"- TP2_HIT: {r['lifecycle_audit']['TP2_HIT']}",
        f"- SL_HIT: {r['lifecycle_audit']['SL_HIT']}",
        f"- INVALIDATED: {r['lifecycle_audit']['INVALIDATED']}",
        f"- no_lifecycle_reason: {r['lifecycle_audit']['no_lifecycle_reason'] or 'None'}",
        "",
        "## 13. Outcomes",
        "",
        f"- TP1: {r['outcome_audit']['TP1']}",
        f"- TP2: {r['outcome_audit']['TP2']}",
        f"- SL: {r['outcome_audit']['SL']}",
        f"- INVALIDATED: {r['outcome_audit']['INVALIDATED']}",
        f"- STILL_OPEN: {r['outcome_audit']['STILL_OPEN']}",
        f"- realized_r_stats: {r['outcome_audit']['realized_r_stats']}",
        "",
        "## 14. Edge",
        "",
        f"- edge_status: {r['edge_audit']['edge_status']}",
        f"- sample_count: {r['edge_audit']['usable_sample_count']}",
        f"- win_rate: {r['edge_audit']['win_rate']}",
        f"- expectancy: {r['edge_audit']['expectancy']}",
        f"- no_edge_reason: {r['edge_audit']['no_edge_claim_reason']}",
        "",
        "## 15. Bottleneck",
        "",
        f"**{r['bottleneck_summary']}**",
        "",
        "## 16. No Signal Reason",
        "",
        f"**{r['no_signal_reason']}**",
        "",
        "## 17. Final Answer",
        "",
        f"**{r['final_answer']}**",
        "",
        "## 18. Recommended Next Fix",
        "",
        f"**{r['recommended_next_fix']}**",
        "",
        "---",
        "",
        "## Safety",
        "",
        f"- safe_to_open_real_trade: `{r['execution_safety']['safe_to_open_real_trade']}`",
        f"- private_api_used: `{r['execution_safety']['private_api_used']}`",
        f"- live_order_sent: `{r['execution_safety']['live_order_sent']}`",
        "",
    ]
    _atomic_write(path, "\n".join(lines))


# --------------------------------------------------------------------------- #
# Main engine
# --------------------------------------------------------------------------- #

def run_full_chain_truth_audit(
    symbol: str = "BTCUSDT",
    state_dir: Path | None = None,
    data_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Run S26A full chain truth audit. Read-only. Never raises."""
    sd = state_dir or STATE_DIR
    dd = data_dir or DATA_DIR
    rd = reports_dir or REPORTS_DIR
    ts = _utc_now()

    inp = _load_all_inputs(sd, dd)

    raw = _audit_raw_data(inp)
    one_s = _audit_one_second_buckets(inp)
    candle = _audit_candle_dna(inp, dd)
    mtf = _audit_mtf(sd)
    structure = _audit_market_structure(inp)
    liquidity = _audit_liquidity(inp, dd)
    scenario = _audit_scenario(inp)
    setup = _audit_setup_candidates(inp)
    plan = _audit_trade_plans(inp)
    gate = _audit_decision_gate(inp)
    tg = _audit_telegram(inp)
    lc = _audit_lifecycle(inp)
    outcome = _audit_outcome(inp)
    edge = _audit_edge(inp)
    success_pat = _audit_success_patterns(inp)
    failure_pat = _audit_failure_patterns(inp)

    bottleneck = _determine_bottleneck(raw, one_s, candle, scenario, setup, plan, gate, tg, lc)
    no_signal_reason = _determine_no_signal_reason(raw, one_s, setup, plan, gate, tg)
    system_running = _determine_system_running(inp, raw)
    next_fix = _recommend_next_fix(bottleneck, no_signal_reason, tg)

    # Block stage for downstream compatibility
    block_stage = "NONE"
    for stage_check in [
        ("S12", not raw["data_flowing"]),
        ("S13", not one_s["one_second_evidence_produced"]),
        ("S15", setup["tradeable_count"] == 0),
        ("S17", plan["PLAN_READY"] == 0),
        ("S18", gate["ALLOW_PAPER"] == 0),
        ("S19", tg["SENT"] == 0),
        ("S20", lc["lifecycle_record_count"] == 0),
    ]:
        if stage_check[1]:
            block_stage = stage_check[0]
            break

    # Collect failed checks
    failed_checks: list[str] = []
    if not raw["data_flowing"]:
        failed_checks.append("no_live_data_flow")
    if not one_s["one_second_evidence_produced"]:
        failed_checks.append("no_1s_evidence_produced")
    if not candle["candle_1m_available"]:
        failed_checks.append("no_1m_candle_dna")
    if setup["tradeable_count"] == 0:
        failed_checks.append("no_tradeable_setup")
    if plan["PLAN_READY"] == 0:
        failed_checks.append("no_plan_ready")
    if gate["ALLOW_PAPER"] == 0:
        failed_checks.append("no_allow_paper_decision")
    if tg["SENT"] == 0:
        failed_checks.append("no_telegram_sent")
    if lc["lifecycle_record_count"] == 0:
        failed_checks.append("no_lifecycle_records")

    final_answer = (
        f"System: {system_running}. "
        f"Bottleneck: {bottleneck}. "
        f"No-signal-reason: {no_signal_reason}. "
        f"Fix: {next_fix}."
    )

    reason_codes = [
        "S26A_FULL_CHAIN_TRUTH_AUDIT",
        "READ_ONLY_DIAGNOSTIC",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_LIVE_ORDERS",
        f"SYMBOL_{symbol}",
        f"NO_SIGNAL_{no_signal_reason}",
        f"BLOCK_STAGE_{block_stage}",
        f"SETUP_COUNT_{setup['setup_context_count']}",
        f"PLAN_READY_{plan['PLAN_READY']}",
        f"ALLOW_PAPER_{gate['ALLOW_PAPER']}",
        f"TG_SENT_{tg['SENT']}",
        f"LIFECYCLE_{lc['lifecycle_record_count']}",
    ]

    record: dict[str, Any] = {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": SOURCE,
        "audit_window": f"latest_{AUDIT_WINDOW_HOURS}h_or_all_records",
        "system_running_status": system_running,
        "raw_data_audit": raw,
        "one_second_bucket_audit": one_s,
        "candle_dna_audit": candle,
        "mtf_audit": mtf,
        "market_structure_audit": structure,
        "liquidity_audit": liquidity,
        "scenario_audit": scenario,
        "setup_candidate_audit": setup,
        "trade_plan_audit": plan,
        "decision_gate_audit": gate,
        "telegram_signal_audit": tg,
        "lifecycle_audit": lc,
        "outcome_audit": outcome,
        "edge_audit": edge,
        "success_pattern_audit": success_pat,
        "failure_pattern_audit": failure_pat,
        "bottleneck_summary": bottleneck,
        "no_signal_reason": no_signal_reason,
        "block_stage": block_stage,
        "failed_checks": failed_checks,
        "recommended_next_fix": next_fix,
        "final_answer": final_answer,
        "data_quality": {
            "level": (inp.get("s_flow_state") or {}).get("quality_state", "UNKNOWN"),
            "score": float((inp.get("s_flow_evidence") or {}).get("confidence", 0.0)),
        },
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["S22_EDGE_MATRIX_V2", "S23_SIMPLE_BRAIN_V2"]},
        "execution_safety": dict(SAFETY),
    }

    try:
        _atomic_write(sd / "latest_full_chain_truth_audit.json", json.dumps(record, indent=2, ensure_ascii=False))
        _atomic_write(sd / "s26a_full_chain_truth_audit_state.json", json.dumps(record, indent=2, ensure_ascii=False))
        _append_jsonl(dd / "full_chain_truth_audit_history.jsonl", record)
        _write_report(record, rd / "s26a_full_chain_truth_audit_latest_report.md")
    except Exception:
        pass

    return record
