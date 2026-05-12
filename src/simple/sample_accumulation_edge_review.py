"""S30 - Sample Accumulation + Edge Review.

Read-only research engine for accumulating paper outcomes and reviewing edge
across setup classes, families, grades, and observed conditions.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S30_SAMPLE_ACCUMULATION_EDGE_REVIEW"
FEEDS_NEXT = {"next_blocks": ["RESEARCH_SAMPLE_ACCUMULATION", "SIMPLE_ROBUST_ENGINE_V1_COMPLETE"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

OUTCOME_HISTORY_PATH = DATA_DIR / "outcome_monitor_history.jsonl"
LIFECYCLE_HISTORY_PATH = DATA_DIR / "paper_lifecycle_history.jsonl"
SETUP_CLASSIFIER_HISTORY_PATH = DATA_DIR / "setup_classifier_v2_history.jsonl"
DECISION_GATE_HISTORY_PATH = DATA_DIR / "decision_gate_history.jsonl"
TRADE_PLAN_HISTORY_PATH = DATA_DIR / "trade_plan_history.jsonl"
SETUP_CONTEXT_HISTORY_PATH = DATA_DIR / "setup_context_history.jsonl"
SCENARIO_TRIGGER_HISTORY_PATH = DATA_DIR / "scenario_trigger_history.jsonl"
EDGE_MATRIX_HISTORY_PATH = DATA_DIR / "edge_matrix_v2_history.jsonl"

LATEST_OUTCOME_PATH = STATE_DIR / "latest_outcome_monitor.json"
LATEST_LIFECYCLE_PATH = STATE_DIR / "latest_paper_lifecycle.json"
LATEST_SETUP_CLASSIFIER_PATH = STATE_DIR / "latest_setup_classifier_v2.json"
LATEST_DECISION_GATE_PATH = STATE_DIR / "latest_decision_gate.json"
LATEST_TRADE_PLAN_PATH = STATE_DIR / "latest_trade_plan.json"
LATEST_EDGE_MATRIX_PATH = STATE_DIR / "latest_edge_matrix_v2.json"
LATEST_SIMPLE_BRAIN_PATH = STATE_DIR / "latest_simple_brain_v2.json"
LATEST_CHAIN_AUDIT_PATH = STATE_DIR / "latest_full_chain_truth_audit.json"
LATEST_QUALITY_AUDIT_PATH = STATE_DIR / "latest_live_flow_quality_audit.json"

LATEST_STATE_PATH = STATE_DIR / "latest_sample_accumulation_edge_review.json"
S30_STATE_PATH = STATE_DIR / "s30_sample_accumulation_edge_review_state.json"
HISTORY_PATH = DATA_DIR / "sample_accumulation_edge_review_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s30_sample_accumulation_edge_review_latest_report.md"

MIN_REQUIRED_SAMPLE = 100
ROBUST_REQUIRED_SAMPLE = 500
VALIDATED_REQUIRED_SAMPLE = 1000
GROUP_RANK_MIN = 20
GROUP_CANDIDATE_MIN = 100
JOIN_WINDOW_SECONDS = 180

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
    except Exception:
        return []
    return records


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(ts: Any) -> float | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            value = float(ts)
            return value / 1000.0 if value > 1e12 else value
        if isinstance(ts, str):
            clean = ts.rstrip("Z")
            return datetime.fromisoformat(clean).replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None
    return None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 4)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _result_bucket(outcome_result: str, realized_r: float | None) -> tuple[bool, bool, bool, bool]:
    result = str(outcome_result or "UNKNOWN").upper()
    is_win = result in {"TP1", "TP2"}
    is_loss = result == "SL"
    is_invalidated = result == "INVALIDATED"
    invalidated_loss_like = is_invalidated and realized_r is not None and realized_r < 0
    return is_win, is_loss, is_invalidated, invalidated_loss_like


def _group_key(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip()
    return text if text else "UNKNOWN"


def _milestone_status(usable_closed_records: int) -> dict[str, Any]:
    if usable_closed_records >= VALIDATED_REQUIRED_SAMPLE:
        current = "REACHED_1000"
        next_target = 1000
        remaining = 0
    elif usable_closed_records >= ROBUST_REQUIRED_SAMPLE:
        current = "REACHED_500"
        next_target = 1000
        remaining = max(0, VALIDATED_REQUIRED_SAMPLE - usable_closed_records)
    elif usable_closed_records >= MIN_REQUIRED_SAMPLE:
        current = "REACHED_100"
        next_target = 500
        remaining = max(0, ROBUST_REQUIRED_SAMPLE - usable_closed_records)
    else:
        current = "BELOW_100"
        next_target = 100
        remaining = max(0, MIN_REQUIRED_SAMPLE - usable_closed_records)
    return {
        "reached_100_samples": usable_closed_records >= MIN_REQUIRED_SAMPLE,
        "reached_500_samples": usable_closed_records >= ROBUST_REQUIRED_SAMPLE,
        "reached_1000_samples": usable_closed_records >= VALIDATED_REQUIRED_SAMPLE,
        "current_milestone": current,
        "next_milestone_target": next_target,
        "samples_remaining_to_next_milestone": remaining,
    }


def _group_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [r for r in records if r.get("_closed_resolved")]
    realized = [r["_realized_r"] for r in records if r.get("_realized_r") is not None and r.get("_closed_resolved")]
    wins = [r for r in records if r.get("_is_win")]
    losses = [r for r in records if r.get("_is_loss")]
    tp1 = sum(1 for r in records if r.get("outcome_result") == "TP1")
    tp2 = sum(1 for r in records if r.get("outcome_result") == "TP2")
    sl = sum(1 for r in records if r.get("outcome_result") == "SL")
    invalidated = sum(1 for r in records if r.get("outcome_result") == "INVALIDATED")
    win_rate = round(len(wins) / (len(wins) + len(losses)), 4) if (len(wins) + len(losses)) > 0 else None
    expectancy = _avg(realized)
    quality = "INSUFFICIENT_GROUP_SAMPLE"
    if len(closed) >= GROUP_CANDIDATE_MIN:
        quality = "EDGE_CANDIDATE_REVIEW"
    elif len(closed) >= GROUP_RANK_MIN:
        quality = "EARLY_OBSERVATION_ONLY"
    return {
        "sample_count": len(records),
        "usable_closed_count": len(closed),
        "win_count": len(wins),
        "loss_count": len(losses),
        "tp1_count": tp1,
        "tp2_count": tp2,
        "sl_count": sl,
        "invalidated_count": invalidated,
        "win_rate": win_rate,
        "avg_realized_r": _avg(realized),
        "expectancy_r": expectancy,
        "quality": quality,
    }


def _group_by(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        buckets.setdefault(_group_key(record.get(key)), []).append(record)
    return {label: _group_stats(items) for label, items in buckets.items()}


def _top_labels(records: list[dict[str, Any]], key: str, limit: int = 3) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for record in records:
        counts[_group_key(record.get(key))] = counts.get(_group_key(record.get(key)), 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"label": label, "count": count} for label, count in ranked[:limit]]


def _rank_groups(grouped: dict[str, Any], positive: bool) -> list[dict[str, Any]]:
    eligible: list[tuple[str, dict[str, Any]]] = []
    for label, stats in grouped.items():
        expectancy = stats.get("expectancy_r")
        if stats.get("usable_closed_count", 0) < GROUP_RANK_MIN or expectancy is None:
            continue
        eligible.append((label, stats))
    eligible.sort(key=lambda item: item[1]["expectancy_r"], reverse=positive)
    return [{"label": label, **stats} for label, stats in eligible[:3]]


def _build_indices(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[tuple[float, dict[str, Any]]]]:
    by_id: dict[str, dict[str, Any]] = {}
    timed: list[tuple[float, dict[str, Any]]] = []
    for record in records:
        lifecycle_id = record.get("lifecycle_id")
        if lifecycle_id:
            by_id[str(lifecycle_id)] = record
        ts = _parse_ts(record.get("timestamp_utc"))
        if ts is not None:
            timed.append((ts, record))
    return by_id, sorted(timed, key=lambda item: item[0])


def _nearest_by_time(target_ts: float | None, timed_records: list[tuple[float, dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    if target_ts is None or not timed_records:
        return None, "INSUFFICIENT_LINKAGE"
    best: dict[str, Any] | None = None
    best_diff: float | None = None
    for ts, record in timed_records:
        diff = abs(ts - target_ts)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = record
    if best is None or best_diff is None or best_diff > JOIN_WINDOW_SECONDS:
        return None, "INSUFFICIENT_LINKAGE"
    return best, "MEDIUM" if best_diff > 10 else "HIGH"


def _resolve_link(
    outcome: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    timed_records: list[tuple[float, dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    lifecycle_id = outcome.get("lifecycle_id")
    if lifecycle_id and lifecycle_id in by_id:
        return by_id[lifecycle_id], "HIGH"
    return _nearest_by_time(_parse_ts(outcome.get("timestamp_utc")), timed_records)


def _enrich_outcomes(
    outcomes: list[dict[str, Any]],
    lifecycles: list[dict[str, Any]],
    setups: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    contexts: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    lifecycle_by_id, lifecycle_timed = _build_indices(lifecycles)
    setup_by_id, setup_timed = _build_indices(setups)
    decision_by_id, decision_timed = _build_indices(decisions)
    plan_by_id, plan_timed = _build_indices(plans)
    context_by_id, context_timed = _build_indices(contexts)
    scenario_by_id, scenario_timed = _build_indices(scenarios)

    join_quality_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INSUFFICIENT_LINKAGE": 0}
    enriched: list[dict[str, Any]] = []

    for outcome in outcomes:
        realized_r = _safe_float(outcome.get("realized_r"))
        is_win, is_loss, is_invalidated, invalidated_loss_like = _result_bucket(outcome.get("outcome_result", "UNKNOWN"), realized_r)
        closed_resolved = is_win or is_loss

        lifecycle, lifecycle_quality = _resolve_link(outcome, lifecycle_by_id, lifecycle_timed)
        setup, setup_quality = _resolve_link(outcome, setup_by_id, setup_timed)
        decision, decision_quality = _resolve_link(outcome, decision_by_id, decision_timed)
        plan, plan_quality = _resolve_link(outcome, plan_by_id, plan_timed)
        context, context_quality = _resolve_link(outcome, context_by_id, context_timed)
        scenario, scenario_quality = _resolve_link(outcome, scenario_by_id, scenario_timed)

        quality_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INSUFFICIENT_LINKAGE": 0}
        best_quality = min((lifecycle_quality, setup_quality, decision_quality, plan_quality, context_quality, scenario_quality), key=lambda item: quality_order[item])
        if setup is None and outcome.get("setup_context_snapshot"):
            setup = None
        if best_quality == "INSUFFICIENT_LINKAGE" and any(x is not None for x in (lifecycle, decision, plan, context, scenario)):
            best_quality = "LOW"
        join_quality_counts[best_quality] += 1

        setup_context_snapshot = outcome.get("setup_context_snapshot") or {}
        scenario_snapshot = outcome.get("scenario_trigger_snapshot") or {}
        decision_snapshot = outcome.get("decision_snapshot") or {}

        structure_bias = _group_key((setup or {}).get("structure_component", {}).get("bias"))
        liquidity_bias = _group_key((setup or {}).get("liquidity_component", {}).get("bias"))
        quality_label = _group_key((setup or {}).get("quality_component", {}).get("quality_label") or (outcome.get("data_quality") or {}).get("level"))
        setup_class = _group_key((setup or {}).get("setup_class"))
        setup_family = _group_key((setup or {}).get("setup_family"))
        setup_grade = _group_key((setup or {}).get("setup_grade") or decision_snapshot.get("final_grade"))
        side = _group_key(outcome.get("side"))
        decision_label = _group_key((decision or {}).get("decision") or decision_snapshot.get("decision"))
        scenario_label = _group_key((scenario or {}).get("scenario_label") or scenario_snapshot.get("scenario_label"))
        no_trade_reasons = (setup or {}).get("no_trade_reasons") or []
        if not isinstance(no_trade_reasons, list):
            no_trade_reasons = []

        record = {
            "timestamp_utc": outcome.get("timestamp_utc"),
            "lifecycle_id": outcome.get("lifecycle_id"),
            "outcome_status": _group_key(outcome.get("outcome_status")),
            "outcome_result": _group_key(outcome.get("outcome_result")),
            "setup_class": setup_class if setup is not None else "UNKNOWN",
            "setup_family": setup_family if setup is not None else "UNKNOWN",
            "setup_grade": setup_grade,
            "side": side,
            "decision": decision_label,
            "scenario_label": scenario_label,
            "structure_bias": structure_bias,
            "liquidity_bias": liquidity_bias,
            "quality_label": quality_label,
            "market_condition": "|".join([scenario_label, structure_bias, liquidity_bias, quality_label]),
            "rr_hint": _safe_float((plan or {}).get("rr_tp2") or (outcome.get("trade_plan_snapshot") or {}).get("rr_tp2")),
            "confidence_hint": _safe_float((setup or {}).get("setup_confidence") or (setup_context_snapshot or {}).get("confidence")),
            "join_quality": best_quality,
            "no_trade_reasons": no_trade_reasons or ["UNKNOWN"],
            "_is_win": is_win,
            "_is_loss": is_loss,
            "_is_invalidated": is_invalidated,
            "_invalidated_loss_like": invalidated_loss_like,
            "_closed_resolved": closed_resolved,
            "_realized_r": realized_r,
            "_mfe_r": _safe_float(outcome.get("mfe_r")),
            "_mae_r": _safe_float(outcome.get("mae_r")),
        }
        enriched.append(record)
    return enriched, join_quality_counts


def _overall_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    usable_closed = [r for r in records if r.get("_closed_resolved")]
    wins = [r for r in records if r.get("_is_win")]
    losses = [r for r in records if r.get("_is_loss")]
    neutrals = [r for r in records if r.get("_is_invalidated") and not r.get("_invalidated_loss_like")]
    realized = [r["_realized_r"] for r in usable_closed if r.get("_realized_r") is not None]
    mfe = [r["_mfe_r"] for r in usable_closed if r.get("_mfe_r") is not None]
    mae = [r["_mae_r"] for r in usable_closed if r.get("_mae_r") is not None]
    win_sum = sum(r["_realized_r"] for r in wins if r.get("_realized_r") is not None)
    loss_sum = sum(abs(r["_realized_r"]) for r in losses if r.get("_realized_r") is not None)
    return {
        "win_count": len(wins),
        "loss_count": len(losses),
        "neutral_count": len(neutrals),
        "win_rate": round(len(wins) / (len(wins) + len(losses)), 4) if (len(wins) + len(losses)) > 0 else None,
        "avg_realized_r": _avg(realized),
        "median_realized_r": _median(realized),
        "avg_mfe_r": _avg(mfe),
        "avg_mae_r": _avg(mae),
        "expectancy_r": _avg(realized),
        "profit_factor_r": round(win_sum / loss_sum, 4) if loss_sum > 0 else None,
        "max_win_r": round(max(realized), 4) if realized else None,
        "max_loss_r": round(min(realized), 4) if realized else None,
    }


def _edge_claim_policy(usable_closed: int, expectancy: float | None, grouped: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    caution_flags: list[str] = []
    positive_groups = [stats for stats in grouped.values() if stats.get("usable_closed_count", 0) >= GROUP_CANDIDATE_MIN and (stats.get("expectancy_r") or 0) > 0]
    negative_groups = [stats for stats in grouped.values() if stats.get("usable_closed_count", 0) >= GROUP_RANK_MIN and (stats.get("expectancy_r") or 0) <= 0]

    if usable_closed < MIN_REQUIRED_SAMPLE:
        edge_status = "NO_EDGE_CLAIM" if usable_closed == 0 else "RESEARCH_ONLY"
        allowed = False
        reason = "Usable closed sample is below 100."
        required_more = max(0, MIN_REQUIRED_SAMPLE - usable_closed)
    elif usable_closed < ROBUST_REQUIRED_SAMPLE:
        if expectancy is not None and expectancy > 0:
            edge_status = "EARLY_EDGE_CANDIDATE"
            allowed = True
            reason = "Positive expectancy with at least 100 usable closed samples."
        else:
            edge_status = "RESEARCH_ONLY"
            allowed = False
            reason = "Expectancy is not positive enough for early edge review."
        required_more = max(0, ROBUST_REQUIRED_SAMPLE - usable_closed)
        caution_flags.append("SUB_500_SAMPLE")
    elif usable_closed < VALIDATED_REQUIRED_SAMPLE:
        stable_distribution = len(positive_groups) >= 1
        if expectancy is not None and expectancy > 0 and stable_distribution:
            edge_status = "PROMISING_EDGE"
            allowed = True
            reason = "Positive expectancy with 500+ usable samples and at least one qualifying group."
        else:
            edge_status = "RESEARCH_ONLY"
            allowed = False
            reason = "500+ samples but distribution is not stable enough."
        required_more = max(0, VALIDATED_REQUIRED_SAMPLE - usable_closed)
        caution_flags.append("SUB_1000_SAMPLE")
    else:
        multi_group = len(positive_groups) >= 2
        if expectancy is not None and expectancy > 0 and multi_group:
            edge_status = "VALIDATED_EDGE"
            allowed = True
            reason = "Positive expectancy with 1000+ usable samples across multiple groups."
        elif expectancy is not None and expectancy > 0:
            edge_status = "PROMISING_EDGE"
            allowed = True
            reason = "1000+ samples reached but not enough positive qualifying groups."
            caution_flags.append("INSUFFICIENT_POSITIVE_GROUP_DIVERSITY")
        else:
            edge_status = "RESEARCH_ONLY"
            allowed = False
            reason = "1000+ samples reached but expectancy is not positive."
        required_more = 0

    return {
        "edge_claim_allowed": allowed,
        "edge_status": edge_status,
        "reason": reason,
        "required_more_samples": required_more,
        "caution_flags": caution_flags,
    }, positive_groups, negative_groups


def _pattern_review(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return _top_labels(records, key, limit=3)


def _success_pattern_review(records: list[dict[str, Any]]) -> dict[str, Any]:
    wins = [r for r in records if r.get("_is_win")]
    if len(wins) < 3:
        return {"status": "INSUFFICIENT_WIN_SAMPLE"}
    return {
        "status": "OK",
        "top_setup_class": _pattern_review(wins, "setup_class"),
        "top_setup_family": _pattern_review(wins, "setup_family"),
        "top_setup_grade": _pattern_review(wins, "setup_grade"),
        "top_side": _pattern_review(wins, "side"),
        "top_scenario_label": _pattern_review(wins, "scenario_label"),
        "top_structure_bias": _pattern_review(wins, "structure_bias"),
        "top_liquidity_bias": _pattern_review(wins, "liquidity_bias"),
        "top_quality_label": _pattern_review(wins, "quality_label"),
        "rr_range": {
            "min": min((r.get("rr_hint") for r in wins if r.get("rr_hint") is not None), default=None),
            "max": max((r.get("rr_hint") for r in wins if r.get("rr_hint") is not None), default=None),
        },
        "confidence_range": {
            "min": min((r.get("confidence_hint") for r in wins if r.get("confidence_hint") is not None), default=None),
            "max": max((r.get("confidence_hint") for r in wins if r.get("confidence_hint") is not None), default=None),
        },
    }


def _failure_pattern_review(records: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [r for r in records if r.get("_is_loss") or r.get("_is_invalidated")]
    if len(failures) < 3:
        return {"status": "INSUFFICIENT_FAILURE_SAMPLE"}
    no_trade_reasons: dict[str, int] = {}
    for record in failures:
        for reason in record.get("no_trade_reasons", ["UNKNOWN"]):
            no_trade_reasons[reason] = no_trade_reasons.get(reason, 0) + 1
    common_reasons = sorted(no_trade_reasons.items(), key=lambda item: (-item[1], item[0]))[:5]
    return {
        "status": "OK",
        "top_setup_class": _pattern_review(failures, "setup_class"),
        "top_setup_family": _pattern_review(failures, "setup_family"),
        "top_setup_grade": _pattern_review(failures, "setup_grade"),
        "top_side": _pattern_review(failures, "side"),
        "top_scenario_label": _pattern_review(failures, "scenario_label"),
        "top_structure_bias": _pattern_review(failures, "structure_bias"),
        "top_liquidity_bias": _pattern_review(failures, "liquidity_bias"),
        "top_quality_label": _pattern_review(failures, "quality_label"),
        "common_block_failure_reasons": [{"label": label, "count": count} for label, count in common_reasons],
    }


def _sample_gaps(summary: dict[str, Any], by_decision: dict[str, Any], outcomes: list[dict[str, Any]], chain_audit: dict[str, Any] | None) -> list[str]:
    gaps: list[str] = []
    if summary["no_lifecycle_records"] > 0:
        gaps.append("NO_LIFECYCLE_SAMPLES_PRESENT")
    if summary["closed_outcome_records"] == 0:
        gaps.append("NO_CLOSED_OUTCOMES")
    if summary["setup_classified_records"] == 0:
        gaps.append("NO_SETUP_CLASSIFIER_LINKAGE")
    if summary["tp1_count"] + summary["tp2_count"] + summary["sl_count"] == 0:
        gaps.append("NO_TP_SL_RESULTS")
    if summary["no_lifecycle_count"] > summary["total_outcome_records"] * 0.5 if summary["total_outcome_records"] else False:
        gaps.append("TOO_MANY_NO_LIFECYCLE")
    if by_decision.get("BLOCK", {}).get("sample_count", 0) > summary["total_outcome_records"] * 0.5 if summary["total_outcome_records"] else False:
        gaps.append("TOO_MANY_BLOCK_DECISIONS")
    if by_decision.get("ALLOW_PAPER", {}).get("sample_count", 0) == 0:
        gaps.append("NO_ALLOW_PAPER")
    if chain_audit and (chain_audit.get("telegram_signal_audit") or {}).get("SENT", 0) == 0:
        gaps.append("NO_TELEGRAM_SENT")
    diversity = len({r.get("setup_class") for r in outcomes if r.get("setup_class") not in ("UNKNOWN", "NO_SETUP_CLASS", "INSUFFICIENT_DATA_CLASS")})
    if diversity < 2:
        gaps.append("INSUFFICIENT_DIVERSITY")
    if any(r.get("structure_bias") == "UNKNOWN" or r.get("liquidity_bias") == "UNKNOWN" for r in outcomes):
        gaps.append("MISSING_STRUCTURE_OR_LIQUIDITY_TAGS")
    return gaps or ["NO_MAJOR_GAPS"]


def _collection_priority(summary: dict[str, Any], sample_gaps: list[str], quality_audit: dict[str, Any] | None) -> list[str]:
    priorities: list[str] = []
    if "NO_CLOSED_OUTCOMES" in sample_gaps:
        priorities.append("more closed lifecycle")
    if "NO_ALLOW_PAPER" in sample_gaps:
        priorities.append("more ALLOW_PAPER")
    if "TOO_MANY_BLOCK_DECISIONS" in sample_gaps:
        priorities.append("more PLAN_READY")
    if "NO_SETUP_CLASSIFIER_LINKAGE" in sample_gaps or "INSUFFICIENT_DIVERSITY" in sample_gaps:
        priorities.append("more setup candidates")
    if "MISSING_STRUCTURE_OR_LIQUIDITY_TAGS" in sample_gaps:
        priorities.append("better structure tags")
        priorities.append("better liquidity tags")
    if quality_audit and str(quality_audit.get("quality_label", "")).upper() in {"STALE", "DEGRADED", "NO_DATA"}:
        priorities.append("better quality audit")
        priorities.append("more live flow")
    if summary["usable_closed_records"] < MIN_REQUIRED_SAMPLE:
        priorities.append("more closed lifecycle")
    # de-dup preserve order
    out: list[str] = []
    for item in priorities:
        if item not in out:
            out.append(item)
    return out or ["more live flow"]


def compute_sample_accumulation_edge_review(inputs: dict[str, Any]) -> dict[str, Any]:
    ts = _utc_now()
    outcomes = inputs["outcome_history"]
    lifecycles = inputs["lifecycle_history"]
    setups = inputs["setup_classifier_history"]
    decisions = inputs["decision_gate_history"]
    plans = inputs["trade_plan_history"]
    contexts = inputs["setup_context_history"]
    scenarios = inputs["scenario_trigger_history"]
    edge_history = inputs["edge_matrix_history"]

    if not outcomes and inputs.get("latest_outcome"):
        outcomes = [inputs["latest_outcome"]]
    if not lifecycles and inputs.get("latest_lifecycle"):
        lifecycles = [inputs["latest_lifecycle"]]
    if not setups and inputs.get("latest_setup_classifier"):
        setups = [inputs["latest_setup_classifier"]]
    if not decisions and inputs.get("latest_decision_gate"):
        decisions = [inputs["latest_decision_gate"]]
    if not plans and inputs.get("latest_trade_plan"):
        plans = [inputs["latest_trade_plan"]]

    symbol = (
        (inputs.get("latest_outcome") or {}).get("symbol")
        or (inputs.get("latest_setup_classifier") or {}).get("symbol")
        or (inputs.get("latest_edge_matrix") or {}).get("symbol")
        or "UNKNOWN"
    )
    missing_sources = [name for name in ("outcome_history", "lifecycle_history", "setup_classifier_history", "decision_gate_history", "trade_plan_history", "setup_context_history", "scenario_trigger_history", "edge_matrix_history") if not inputs.get(name)]
    input_status = "OK" if not missing_sources else "PARTIAL" if len(missing_sources) < 8 else "MISSING"

    enriched, join_quality_counts = _enrich_outcomes(outcomes, lifecycles, setups, decisions, plans, contexts, scenarios)
    usable_closed_records = sum(1 for r in enriched if r.get("_closed_resolved"))
    closed_records = sum(1 for r in enriched if _group_key(r.get("outcome_status")) == "CLOSED")
    open_records = sum(1 for r in enriched if _group_key(r.get("outcome_result")) == "STILL_OPEN")
    no_lifecycle_records = sum(1 for r in enriched if _group_key(r.get("outcome_result")) == "NO_LIFECYCLE")
    setup_classified_records = sum(1 for r in enriched if r.get("setup_class") not in ("UNKNOWN",))
    unclassified_records = len(enriched) - setup_classified_records
    tp1_count = sum(1 for r in enriched if r.get("outcome_result") == "TP1")
    tp2_count = sum(1 for r in enriched if r.get("outcome_result") == "TP2")
    sl_count = sum(1 for r in enriched if r.get("outcome_result") == "SL")
    invalidated_count = sum(1 for r in enriched if r.get("outcome_result") == "INVALIDATED")
    still_open_count = sum(1 for r in enriched if r.get("outcome_result") == "STILL_OPEN")
    no_lifecycle_count = sum(1 for r in enriched if r.get("outcome_result") == "NO_LIFECYCLE")

    milestone_status = _milestone_status(usable_closed_records)
    overall = _overall_stats(enriched)
    by_setup_class = _group_by(enriched, "setup_class")
    by_setup_family = _group_by(enriched, "setup_family")
    by_setup_grade = _group_by(enriched, "setup_grade")
    by_side = _group_by(enriched, "side")
    by_decision = _group_by(enriched, "decision")
    by_market_condition = _group_by(enriched, "market_condition")

    reason_records: list[dict[str, Any]] = []
    for record in enriched:
        reasons = record.get("no_trade_reasons", ["UNKNOWN"])
        for reason in reasons:
            reason_records.append({"no_trade_reason": _group_key(reason), **record})
    by_no_trade_reason = _group_by(reason_records, "no_trade_reason")

    edge_claim_policy, edge_candidates, weak_negative = _edge_claim_policy(usable_closed_records, overall.get("expectancy_r"), by_setup_class)
    best_groups = _rank_groups(by_setup_class, positive=True)
    worst_groups = _rank_groups(by_setup_class, positive=False)
    success_pattern_review = _success_pattern_review(enriched)
    failure_pattern_review = _failure_pattern_review(enriched)
    sample_summary = {
        "total_outcome_records": len(enriched),
        "closed_outcome_records": closed_records,
        "open_outcome_records": open_records,
        "no_lifecycle_records": no_lifecycle_records,
        "usable_closed_records": usable_closed_records,
        "setup_classified_records": setup_classified_records,
        "unclassified_records": unclassified_records,
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "sl_count": sl_count,
        "invalidated_count": invalidated_count,
        "still_open_count": still_open_count,
        "no_lifecycle_count": no_lifecycle_count,
        "min_required_sample": MIN_REQUIRED_SAMPLE,
        "robust_required_sample": ROBUST_REQUIRED_SAMPLE,
    }
    sample_gaps = _sample_gaps(sample_summary, by_decision, enriched, inputs.get("latest_chain_audit"))
    collection_priority = _collection_priority(sample_summary, sample_gaps, inputs.get("latest_quality_audit"))
    research_mode = edge_claim_policy["edge_status"] in {"NO_EDGE_CLAIM", "RESEARCH_ONLY", "EARLY_EDGE_CANDIDATE"}

    final_answer = (
        f"Usable closed samples: {usable_closed_records}. "
        f"Milestone: {milestone_status['current_milestone']}. "
        f"Edge status: {edge_claim_policy['edge_status']}. "
        f"Reason: {edge_claim_policy['reason']}"
    )
    recommended_next_fix = collection_priority[0] if collection_priority else "more live flow"
    data_quality = {
        "level": "LOW" if usable_closed_records < MIN_REQUIRED_SAMPLE else "MEDIUM" if usable_closed_records < ROBUST_REQUIRED_SAMPLE else "HIGH",
        "score": round(min(1.0, usable_closed_records / VALIDATED_REQUIRED_SAMPLE), 4),
        "join_quality": join_quality_counts,
        "missing_sources": missing_sources,
    }
    reason_codes = [
        "S30_SAMPLE_ACCUMULATION_EDGE_REVIEW_RUN",
        f"INPUT_STATUS_{input_status}",
        f"TOTAL_OUTCOMES_{len(enriched)}",
        f"USABLE_CLOSED_{usable_closed_records}",
        f"EDGE_STATUS_{edge_claim_policy['edge_status']}",
        f"MILESTONE_{milestone_status['current_milestone']}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_LIVE_ORDERS",
        "RESEARCH_ONLY",
    ]
    if missing_sources:
        reason_codes.append("MISSING_HISTORIES")

    return {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": "S20_S21_S22_S29_HISTORY_REVIEW",
        "input_status": input_status,
        "sample_window": "all_available_history",
        "sample_summary": sample_summary,
        "milestone_status": milestone_status,
        "overall_outcome_stats": overall,
        "by_setup_class": by_setup_class,
        "by_setup_family": by_setup_family,
        "by_setup_grade": by_setup_grade,
        "by_side": by_side,
        "by_decision": by_decision,
        "by_no_trade_reason": by_no_trade_reason,
        "by_market_condition": by_market_condition,
        "success_pattern_review": success_pattern_review,
        "failure_pattern_review": failure_pattern_review,
        "edge_claim_policy": edge_claim_policy,
        "edge_candidates": best_groups,
        "weak_or_negative_edges": worst_groups,
        "sample_gaps": sample_gaps,
        "collection_priority": collection_priority,
        "research_mode": research_mode,
        "final_answer": final_answer,
        "recommended_next_fix": recommended_next_fix,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def _write_report(record: dict[str, Any]) -> None:
    lines = [
        "# S30 Sample Accumulation Edge Review - Latest Report",
        "",
        f"- **Total samples**: {record['sample_summary']['total_outcome_records']}",
        f"- **Closed samples**: {record['sample_summary']['closed_outcome_records']}",
        f"- **Usable samples**: {record['sample_summary']['usable_closed_records']}",
        f"- **100/500/1000 milestone progress**: {record['milestone_status']['current_milestone']} ({record['milestone_status']['samples_remaining_to_next_milestone']} remaining)",
        f"- **Current edge status**: {record['edge_claim_policy']['edge_status']}",
        f"- **Why edge can/cannot be claimed**: {record['edge_claim_policy']['reason']}",
        "",
        "## Best Observed Setup Groups",
        "",
    ]
    if record["edge_candidates"]:
        for item in record["edge_candidates"]:
            lines.append(f"- {item['label']}: expectancy={item.get('expectancy_r')} sample={item.get('usable_closed_count')}")
    else:
        lines.append("- None")
    lines += ["", "## Worst Observed Setup Groups", ""]
    if record["weak_or_negative_edges"]:
        for item in record["weak_or_negative_edges"]:
            lines.append(f"- {item['label']}: expectancy={item.get('expectancy_r')} sample={item.get('usable_closed_count')}")
    else:
        lines.append("- None")
    lines += [
        "",
        "## Success Pattern Summary",
        "",
        f"- {record['success_pattern_review']}",
        "",
        "## Failure Pattern Summary",
        "",
        f"- {record['failure_pattern_review']}",
        "",
        "## Sample Gaps",
        "",
    ]
    lines.extend(f"- {item}" for item in record["sample_gaps"])
    lines += ["", "## Next Collection Priority", ""]
    lines.extend(f"- {item}" for item in record["collection_priority"])
    lines += [
        "",
        "## Safety Confirmation",
        "",
        f"- safe_to_open_real_trade: {record['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {record['execution_safety']['private_api_used']}",
        f"- live_order_sent: {record['execution_safety']['live_order_sent']}",
    ]
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")


def run_sample_accumulation_edge_review() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    inputs = {
        "outcome_history": _load_jsonl(OUTCOME_HISTORY_PATH),
        "lifecycle_history": _load_jsonl(LIFECYCLE_HISTORY_PATH),
        "setup_classifier_history": _load_jsonl(SETUP_CLASSIFIER_HISTORY_PATH),
        "decision_gate_history": _load_jsonl(DECISION_GATE_HISTORY_PATH),
        "trade_plan_history": _load_jsonl(TRADE_PLAN_HISTORY_PATH),
        "setup_context_history": _load_jsonl(SETUP_CONTEXT_HISTORY_PATH),
        "scenario_trigger_history": _load_jsonl(SCENARIO_TRIGGER_HISTORY_PATH),
        "edge_matrix_history": _load_jsonl(EDGE_MATRIX_HISTORY_PATH),
        "latest_outcome": _load_json(LATEST_OUTCOME_PATH),
        "latest_lifecycle": _load_json(LATEST_LIFECYCLE_PATH),
        "latest_setup_classifier": _load_json(LATEST_SETUP_CLASSIFIER_PATH),
        "latest_decision_gate": _load_json(LATEST_DECISION_GATE_PATH),
        "latest_trade_plan": _load_json(LATEST_TRADE_PLAN_PATH),
        "latest_edge_matrix": _load_json(LATEST_EDGE_MATRIX_PATH),
        "latest_simple_brain": _load_json(LATEST_SIMPLE_BRAIN_PATH),
        "latest_chain_audit": _load_json(LATEST_CHAIN_AUDIT_PATH),
        "latest_quality_audit": _load_json(LATEST_QUALITY_AUDIT_PATH),
    }
    result = compute_sample_accumulation_edge_review(inputs)
    _atomic_write(LATEST_STATE_PATH, json.dumps(result, indent=2, ensure_ascii=False))
    state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S30_SAMPLE_ACCUMULATION_EDGE_REVIEW_STATE",
        "usable_closed_records": result["sample_summary"]["usable_closed_records"],
        "current_milestone": result["milestone_status"]["current_milestone"],
        "edge_status": result["edge_claim_policy"]["edge_status"],
        "edge_claim_allowed": result["edge_claim_policy"]["edge_claim_allowed"],
        "recommended_next_fix": result["recommended_next_fix"],
    }
    _atomic_write(S30_STATE_PATH, json.dumps(state, indent=2, ensure_ascii=False))
    _append_jsonl(HISTORY_PATH, result)
    _write_report(result)
    return result
