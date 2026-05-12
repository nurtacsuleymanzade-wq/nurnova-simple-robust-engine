"""S22 — Edge Matrix v2. Builds robust grouped statistics from closed paper
outcome records. Paper-only learning block: no orders, no private API,
no Telegram, no real trade execution.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

BLOCK_ID = "S22_EDGE_MATRIX_V2"
FEEDS_NEXT = {"next_blocks": ["S23_SIMPLE_BRAIN_V2"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

OUTCOME_HISTORY_PATH = DATA_DIR / "outcome_monitor_history.jsonl"
LATEST_OUTCOME_PATH = STATE_DIR / "latest_outcome_monitor.json"

SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"
SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"
DECISION_GATE_PATH = STATE_DIR / "latest_decision_gate.json"
TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"

LATEST_MATRIX_PATH = STATE_DIR / "latest_edge_matrix_v2.json"
S22_STATE_PATH = STATE_DIR / "s22_edge_matrix_v2_state.json"
MATRIX_HISTORY_PATH = DATA_DIR / "edge_matrix_v2_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s22_edge_matrix_v2_latest_report.md"

MIN_REQUIRED_SAMPLE = 30
ROBUST_SAMPLE_THRESHOLD = 100

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

ALLOWED_SAMPLE_STATUS = {
    "INSUFFICIENT_SAMPLE",
    "EARLY_SAMPLE",
    "USABLE_SAMPLE",
    "ROBUST_SAMPLE",
}
ALLOWED_EDGE_STATUS = {
    "NO_EDGE_CLAIM",
    "RESEARCH_ONLY",
    "WEAK_EDGE",
    "PROMISING_EDGE",
    "VALIDATED_EDGE",
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


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_outcome_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    return records


def _classify_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Classify one outcome record into a normalized shape for stats."""
    status = str(rec.get("outcome_status") or "UNKNOWN").upper()
    result = str(rec.get("outcome_result") or "UNKNOWN").upper()
    side = str(rec.get("side") or "UNKNOWN").upper() or "UNKNOWN"
    realized_r = _safe_float(rec.get("realized_r"))
    mfe_r = _safe_float(rec.get("mfe_r")) or 0.0
    mae_r = _safe_float(rec.get("mae_r")) or 0.0

    closed = status == "CLOSED" and result in {"TP1", "TP2", "SL", "INVALIDATED"}
    is_open = status == "OPEN" or result == "STILL_OPEN"
    no_lifecycle = result == "NO_LIFECYCLE"

    is_win = closed and result in {"TP1", "TP2"}
    is_loss = closed and result == "SL"
    is_invalidated = closed and result == "INVALIDATED"
    invalidated_loss_like = is_invalidated and (realized_r is not None and realized_r < 0)

    # Grouping keys, default UNKNOWN if missing.
    setup_label = (
        ((rec.get("setup_context_snapshot") or {}).get("setup_context_label"))
        or "UNKNOWN"
    )
    scenario_label = (
        ((rec.get("scenario_trigger_snapshot") or {}).get("scenario_label"))
        or "UNKNOWN"
    )
    decision_label = (
        ((rec.get("decision_snapshot") or {}).get("decision"))
        or "UNKNOWN"
    )
    final_grade = (
        ((rec.get("decision_snapshot") or {}).get("final_grade"))
        or "UNKNOWN"
    )

    return {
        "status": status,
        "result": result,
        "side": side or "UNKNOWN",
        "realized_r": realized_r,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "closed": closed,
        "is_open": is_open,
        "no_lifecycle": no_lifecycle,
        "is_win": is_win,
        "is_loss": is_loss,
        "is_invalidated": is_invalidated,
        "invalidated_loss_like": invalidated_loss_like,
        "setup_context_label": setup_label or "UNKNOWN",
        "scenario_label": scenario_label or "UNKNOWN",
        "decision": decision_label or "UNKNOWN",
        "final_grade": final_grade or "UNKNOWN",
    }


def _compute_overall(classified: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [c for c in classified if c["closed"]]
    tp1 = sum(1 for c in closed if c["result"] == "TP1")
    tp2 = sum(1 for c in closed if c["result"] == "TP2")
    sl = sum(1 for c in closed if c["result"] == "SL")
    invalidated = sum(1 for c in closed if c["is_invalidated"])

    win = sum(1 for c in closed if c["is_win"])
    loss = sum(1 for c in closed if c["is_loss"])

    # win_rate uses closed records that resolved as win or loss
    wl_total = win + loss
    win_rate = round(win / wl_total, 4) if wl_total > 0 else None

    rr_vals = [c["realized_r"] for c in closed if c["realized_r"] is not None]
    avg_r = round(sum(rr_vals) / len(rr_vals), 4) if rr_vals else None

    mfe_vals = [c["mfe_r"] for c in closed]
    mae_vals = [c["mae_r"] for c in closed]
    avg_mfe = round(sum(mfe_vals) / len(mfe_vals), 4) if mfe_vals else None
    avg_mae = round(sum(mae_vals) / len(mae_vals), 4) if mae_vals else None

    # expectancy_r = avg of realized_r for wins/losses (closed and resolved)
    wl_rr = [
        c["realized_r"]
        for c in closed
        if (c["is_win"] or c["is_loss"]) and c["realized_r"] is not None
    ]
    expectancy = round(sum(wl_rr) / len(wl_rr), 4) if wl_rr else None

    return {
        "tp1_count": tp1,
        "tp2_count": tp2,
        "sl_count": sl,
        "invalidated_count": invalidated,
        "win_count": win,
        "loss_count": loss,
        "win_rate": win_rate,
        "avg_realized_r": avg_r,
        "avg_mfe_r": avg_mfe,
        "avg_mae_r": avg_mae,
        "expectancy_r": expectancy,
    }


def _group_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [c for c in items if c["closed"]]
    win = sum(1 for c in closed if c["is_win"])
    loss = sum(1 for c in closed if c["is_loss"])
    tp1 = sum(1 for c in closed if c["result"] == "TP1")
    tp2 = sum(1 for c in closed if c["result"] == "TP2")
    sl = sum(1 for c in closed if c["result"] == "SL")
    inv = sum(1 for c in closed if c["is_invalidated"])
    wl_total = win + loss
    win_rate = round(win / wl_total, 4) if wl_total > 0 else None
    rr_vals = [c["realized_r"] for c in closed if c["realized_r"] is not None]
    avg_r = round(sum(rr_vals) / len(rr_vals), 4) if rr_vals else None
    wl_rr = [
        c["realized_r"] for c in closed
        if (c["is_win"] or c["is_loss"]) and c["realized_r"] is not None
    ]
    expectancy = round(sum(wl_rr) / len(wl_rr), 4) if wl_rr else None
    return {
        "sample_count": len(items),
        "closed_count": len(closed),
        "tp1_count": tp1,
        "tp2_count": tp2,
        "sl_count": sl,
        "invalidated_count": inv,
        "win_count": win,
        "loss_count": loss,
        "win_rate": win_rate,
        "avg_realized_r": avg_r,
        "expectancy_r": expectancy,
    }


def _group_by(classified: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for c in classified:
        k = c.get(key) or "UNKNOWN"
        buckets.setdefault(str(k), []).append(c)
    return {k: _group_stats(v) for k, v in buckets.items()}


def _sample_status(usable_closed: int) -> str:
    if usable_closed >= ROBUST_SAMPLE_THRESHOLD:
        return "ROBUST_SAMPLE"
    if usable_closed >= MIN_REQUIRED_SAMPLE:
        return "USABLE_SAMPLE"
    if usable_closed > 0:
        return "EARLY_SAMPLE"
    return "INSUFFICIENT_SAMPLE"


def _edge_quality(
    usable_closed: int,
    overall: dict[str, Any],
) -> dict[str, Any]:
    wr = overall.get("win_rate")
    exp = overall.get("expectancy_r")
    caution_reason = ""

    if usable_closed < MIN_REQUIRED_SAMPLE:
        if usable_closed == 0:
            status = "NO_EDGE_CLAIM"
            caution_reason = "NO_CLOSED_RESOLVED_SAMPLES"
        else:
            status = "RESEARCH_ONLY"
            caution_reason = (
                f"SAMPLE_BELOW_MIN_REQUIRED_{MIN_REQUIRED_SAMPLE}"
            )
        score = 0.0
        if wr is not None and exp is not None:
            score = round(max(0.0, wr * exp), 4)
        confidence = "VERY_LOW" if usable_closed > 0 else "NONE"
        return {
            "edge_status": status,
            "edge_score": score,
            "confidence_level": confidence,
            "caution_reason": caution_reason,
        }

    # usable_closed >= MIN_REQUIRED_SAMPLE
    score = 0.0
    if wr is not None and exp is not None:
        score = round(wr * exp, 4)

    if usable_closed >= ROBUST_SAMPLE_THRESHOLD:
        if wr is not None and exp is not None and wr >= 0.5 and exp > 0:
            status = "VALIDATED_EDGE"
            confidence = "HIGH"
            caution_reason = ""
        elif exp is not None and exp > 0:
            status = "PROMISING_EDGE"
            confidence = "MEDIUM"
            caution_reason = "ROBUST_SAMPLE_LOW_WIN_RATE"
        else:
            status = "WEAK_EDGE"
            confidence = "LOW"
            caution_reason = "NEGATIVE_OR_ZERO_EXPECTANCY"
    else:
        # usable sample but not robust
        if exp is not None and exp > 0 and wr is not None and wr >= 0.5:
            status = "PROMISING_EDGE"
            confidence = "MEDIUM"
            caution_reason = "USABLE_BUT_NOT_ROBUST_SAMPLE"
        elif exp is not None and exp > 0:
            status = "WEAK_EDGE"
            confidence = "LOW"
            caution_reason = "USABLE_BUT_LOW_WIN_RATE"
        else:
            status = "WEAK_EDGE"
            confidence = "LOW"
            caution_reason = "USABLE_BUT_NON_POSITIVE_EXPECTANCY"

    return {
        "edge_status": status,
        "edge_score": score,
        "confidence_level": confidence,
        "caution_reason": caution_reason,
    }


def _best_worst(grouped: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pick best/worst group by expectancy_r (then win_rate)."""
    scored = []
    for label, stats in grouped.items():
        exp = stats.get("expectancy_r")
        if exp is None:
            continue
        scored.append((label, stats))
    if not scored:
        return ({}, {})
    scored_sorted = sorted(
        scored,
        key=lambda t: (
            t[1].get("expectancy_r") if t[1].get("expectancy_r") is not None else 0.0,
            t[1].get("win_rate") if t[1].get("win_rate") is not None else 0.0,
        ),
    )
    worst_label, worst_stats = scored_sorted[0]
    best_label, best_stats = scored_sorted[-1]
    return (
        {"label": best_label, **best_stats},
        {"label": worst_label, **worst_stats},
    )


def build_edge_matrix(
    records: Iterable[dict[str, Any]],
    symbol: str,
    source: str,
    input_status: str,
) -> dict[str, Any]:
    records = list(records)
    classified = [_classify_record(r) for r in records]

    total = len(classified)
    closed_records = sum(1 for c in classified if c["closed"])
    open_records = sum(1 for c in classified if c["is_open"])
    no_lifecycle_records = sum(1 for c in classified if c["no_lifecycle"])
    usable_closed = sum(1 for c in classified if c["is_win"] or c["is_loss"])
    sample_status = _sample_status(usable_closed)

    sample_summary = {
        "total_records": total,
        "closed_records": closed_records,
        "open_records": open_records,
        "no_lifecycle_records": no_lifecycle_records,
        "usable_closed_records": usable_closed,
        "min_required_sample": MIN_REQUIRED_SAMPLE,
        "sample_status": sample_status,
    }
    assert sample_status in ALLOWED_SAMPLE_STATUS

    overall = _compute_overall(classified)
    by_side = _group_by(classified, "side")
    by_grade = _group_by(classified, "final_grade")
    by_setup = _group_by(classified, "setup_context_label")
    by_scenario = _group_by(classified, "scenario_label")
    by_decision = _group_by(classified, "decision")

    edge_quality = _edge_quality(usable_closed, overall)
    assert edge_quality["edge_status"] in ALLOWED_EDGE_STATUS

    best_setup, worst_setup = _best_worst(by_setup)
    best_scenario, worst_scenario = _best_worst(by_scenario)
    best_grade, worst_grade = _best_worst(by_grade)

    best_observed = {
        "by_setup_context": best_setup,
        "by_scenario_label": best_scenario,
        "by_grade": best_grade,
    }
    worst_observed = {
        "by_setup_context": worst_setup,
        "by_scenario_label": worst_scenario,
        "by_grade": worst_grade,
    }

    limitations: list[str] = []
    if usable_closed < MIN_REQUIRED_SAMPLE:
        limitations.append("SAMPLE_TOO_SMALL_FOR_EDGE_CLAIM")
    if usable_closed < ROBUST_SAMPLE_THRESHOLD:
        limitations.append("NOT_ROBUST_SAMPLE")
    if open_records > 0:
        limitations.append("OPEN_RECORDS_EXCLUDED_FROM_EXPECTANCY")
    if no_lifecycle_records > 0:
        limitations.append("NO_LIFECYCLE_RECORDS_EXCLUDED_FROM_EXPECTANCY")
    if total == 0:
        limitations.append("EMPTY_HISTORY")

    # Data quality scoring
    if total == 0:
        dq_level = "MISSING"
        dq_score = 0.0
        dq_issues = ["EMPTY_HISTORY"]
    elif usable_closed == 0:
        dq_level = "LOW"
        dq_score = 0.1
        dq_issues = ["NO_USABLE_CLOSED_RECORDS"]
    elif usable_closed < MIN_REQUIRED_SAMPLE:
        dq_level = "LOW"
        dq_score = 0.3
        dq_issues = ["SAMPLE_BELOW_MIN_REQUIRED"]
    elif usable_closed < ROBUST_SAMPLE_THRESHOLD:
        dq_level = "MEDIUM"
        dq_score = 0.6
        dq_issues = []
    else:
        dq_level = "HIGH"
        dq_score = 1.0
        dq_issues = []

    data_quality = {"score": dq_score, "level": dq_level, "issues": dq_issues}

    reason_codes = [
        f"SYMBOL_{symbol}",
        f"INPUT_STATUS_{input_status}",
        f"TOTAL_RECORDS_{total}",
        f"CLOSED_RECORDS_{closed_records}",
        f"OPEN_RECORDS_{open_records}",
        f"NO_LIFECYCLE_RECORDS_{no_lifecycle_records}",
        f"USABLE_CLOSED_{usable_closed}",
        f"SAMPLE_STATUS_{sample_status}",
        f"EDGE_STATUS_{edge_quality['edge_status']}",
        f"CONFIDENCE_{edge_quality['confidence_level']}",
        f"DQ_{dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
        "NO_TELEGRAM",
        "PAPER_ONLY",
    ]
    if edge_quality.get("caution_reason"):
        reason_codes.append(f"CAUTION_{edge_quality['caution_reason']}")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": source,
        "input_status": input_status,
        "sample_summary": sample_summary,
        "overall_stats": overall,
        "by_side": by_side,
        "by_grade": by_grade,
        "by_setup_context": by_setup,
        "by_scenario_label": by_scenario,
        "by_decision": by_decision,
        "edge_quality": edge_quality,
        "best_observed_conditions": best_observed,
        "worst_observed_conditions": worst_observed,
        "limitations": limitations,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def _resolve_symbol(
    latest: dict[str, Any] | None,
    history: list[dict[str, Any]],
) -> str:
    if latest and latest.get("symbol"):
        return str(latest["symbol"])
    for r in reversed(history):
        sym = r.get("symbol")
        if sym:
            return str(sym)
    return "UNKNOWN"


def run_edge_matrix_v2() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    latest_outcome = _load_json(LATEST_OUTCOME_PATH)
    history = load_outcome_records(OUTCOME_HISTORY_PATH)
    prior_state = _load_json(S22_STATE_PATH)

    if not history and not latest_outcome:
        input_status = "MISSING"
    elif not history and latest_outcome:
        input_status = "PARTIAL"
        history = [latest_outcome]
    else:
        input_status = "OK"

    symbol = _resolve_symbol(latest_outcome, history)
    source = "S21_OUTCOME_MONITOR"

    result = build_edge_matrix(history, symbol, source, input_status)

    _atomic_write(LATEST_MATRIX_PATH, json.dumps(result, indent=2))

    state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S22_EDGE_MATRIX_V2_STATE",
        "last_symbol": symbol,
        "last_sample_status": result["sample_summary"]["sample_status"],
        "last_edge_status": result["edge_quality"]["edge_status"],
        "last_total_records": result["sample_summary"]["total_records"],
        "last_usable_closed_records": result["sample_summary"]["usable_closed_records"],
        "runs": int(((prior_state or {}).get("runs") or 0)) + 1,
    }
    _atomic_write(S22_STATE_PATH, json.dumps(state, indent=2))

    summary_record = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "sample_summary": result["sample_summary"],
        "overall_stats": result["overall_stats"],
        "edge_quality": result["edge_quality"],
        "reason_codes": result["reason_codes"],
        "execution_safety": result["execution_safety"],
    }
    with MATRIX_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary_record) + "\n")

    _write_report(result)
    return result


def _write_report(r: dict[str, Any]) -> None:
    ss = r["sample_summary"]
    ov = r["overall_stats"]
    eq = r["edge_quality"]
    lines = [
        "# S22 Edge Matrix v2 — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Source:** {r['source']}",
        f"**Input Status:** {r['input_status']}",
        "",
        "## Sample Summary",
        f"- total_records: {ss['total_records']}",
        f"- closed_records: {ss['closed_records']}",
        f"- open_records: {ss['open_records']}",
        f"- no_lifecycle_records: {ss['no_lifecycle_records']}",
        f"- usable_closed_records: {ss['usable_closed_records']}",
        f"- min_required_sample: {ss['min_required_sample']}",
        f"- sample_status: {ss['sample_status']}",
        "",
        "## Overall Stats",
        f"- tp1_count: {ov['tp1_count']}",
        f"- tp2_count: {ov['tp2_count']}",
        f"- sl_count: {ov['sl_count']}",
        f"- invalidated_count: {ov['invalidated_count']}",
        f"- win_count: {ov['win_count']}",
        f"- loss_count: {ov['loss_count']}",
        f"- win_rate: {ov['win_rate']}",
        f"- avg_realized_r: {ov['avg_realized_r']}",
        f"- avg_mfe_r: {ov['avg_mfe_r']}",
        f"- avg_mae_r: {ov['avg_mae_r']}",
        f"- expectancy_r: {ov['expectancy_r']}",
        "",
        "## Edge Quality",
        f"- edge_status: {eq['edge_status']}",
        f"- edge_score: {eq['edge_score']}",
        f"- confidence_level: {eq['confidence_level']}",
        f"- caution_reason: {eq['caution_reason']}",
        "",
        "## Groupings",
        f"- by_side keys: {list(r['by_side'].keys())}",
        f"- by_grade keys: {list(r['by_grade'].keys())}",
        f"- by_setup_context keys: {list(r['by_setup_context'].keys())}",
        f"- by_scenario_label keys: {list(r['by_scenario_label'].keys())}",
        f"- by_decision keys: {list(r['by_decision'].keys())}",
        "",
        "## Best Observed Conditions",
        f"- by_setup_context: {r['best_observed_conditions']['by_setup_context']}",
        f"- by_scenario_label: {r['best_observed_conditions']['by_scenario_label']}",
        f"- by_grade: {r['best_observed_conditions']['by_grade']}",
        "",
        "## Worst Observed Conditions",
        f"- by_setup_context: {r['worst_observed_conditions']['by_setup_context']}",
        f"- by_scenario_label: {r['worst_observed_conditions']['by_scenario_label']}",
        f"- by_grade: {r['worst_observed_conditions']['by_grade']}",
        "",
        "## Limitations",
    ]
    if r["limitations"]:
        lines.extend(f"- {x}" for x in r["limitations"])
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "## Data Quality",
        f"- score: {r['data_quality']['score']}",
        f"- level: {r['data_quality']['level']}",
        f"- issues: {r['data_quality']['issues']}",
        "",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
    ])
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")
