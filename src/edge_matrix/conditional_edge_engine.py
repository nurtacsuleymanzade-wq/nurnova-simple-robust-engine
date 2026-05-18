from __future__ import annotations

from collections import defaultdict
from typing import Any

from .edge_matrix_registry import ELIGIBLE_TRADE_FATES, GROUPING_FIELDS


def _candidate_record(record: dict[str, Any]) -> bool:
    return any(
        key in record
        for key in (
            "trade_fate",
            "outcome_status",
            "outcome_result",
            "is_closed_outcome",
            "edge_eligible",
            "paper_trade_id",
            "outcome_id",
        )
    )


def _record_reason_codes(record: dict[str, Any]) -> list[str]:
    raw = record.get("reason_codes")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def _extract_context(
    record: dict[str, Any],
    latest_context: dict[str, dict[str, Any] | None],
) -> tuple[dict[str, Any], list[str]]:
    reason_codes: list[str] = []
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    trade_decision_evidence = evidence.get("trade_decision_evidence") if isinstance(evidence.get("trade_decision_evidence"), dict) else {}

    latest_trade_decision = latest_context.get("trade_decision") or {}
    latest_setup_entry = latest_context.get("setup_entry") or {}
    latest_active_scenario = latest_context.get("active_scenario") or {}
    latest_market_state = latest_context.get("market_state") or {}
    latest_flow_reaction = latest_context.get("flow_reaction") or {}

    decision_matches = bool(
        record.get("decision_id")
        and latest_trade_decision
        and str(record.get("decision_id")) == str(latest_trade_decision.get("decision_id") or "")
    )
    setup_matches = bool(
        record.get("setup_candidate_id")
        and latest_setup_entry
        and str(record.get("setup_candidate_id")) == str(latest_setup_entry.get("setup_candidate_id") or "")
    )
    scenario_matches = bool(
        trade_decision_evidence.get("active_scenario_id")
        and latest_active_scenario
        and str(trade_decision_evidence.get("active_scenario_id")) == str(latest_active_scenario.get("active_scenario_id") or "")
    )
    market_matches = bool(
        trade_decision_evidence.get("market_state_id")
        and latest_market_state
        and str(trade_decision_evidence.get("market_state_id")) == str(latest_market_state.get("market_state_id") or "")
    )
    flow_matches = bool(
        trade_decision_evidence.get("flow_reaction_id")
        and latest_flow_reaction
        and str(trade_decision_evidence.get("flow_reaction_id")) == str(latest_flow_reaction.get("flow_reaction_id") or "")
    )

    setup_candidate = latest_setup_entry.get("setup_candidate") if setup_matches else None
    setup_direction = latest_setup_entry.get("setup_direction") if setup_matches else None
    entry_trigger_status = latest_setup_entry.get("entry_trigger_status") if setup_matches else None

    market_regime = latest_market_state.get("market_regime") if market_matches else None
    trend_state = latest_market_state.get("trend_state") if market_matches else None
    volatility_state = latest_market_state.get("volatility_state") if market_matches else None
    liquidity_state = latest_market_state.get("liquidity_state") if market_matches else None

    active_scenario = latest_active_scenario.get("active_scenario") if scenario_matches else None

    flow_confirmation = latest_flow_reaction.get("flow_confirmation") if flow_matches else None
    post_liquidity_reaction = latest_flow_reaction.get("post_liquidity_reaction") if flow_matches else None
    trap_state = latest_flow_reaction.get("trap_state") if flow_matches else None
    absorption_state = latest_flow_reaction.get("absorption_state") if flow_matches else None

    entry_model = latest_trade_decision.get("entry_model") if decision_matches else None
    risk_grade = latest_trade_decision.get("risk_grade") if decision_matches else None
    plan_quality = latest_trade_decision.get("plan_quality") if decision_matches else None

    pattern = setup_candidate or active_scenario or entry_model or "UNKNOWN"

    group_key = {
        "pattern": pattern or "UNKNOWN",
        "market_regime": market_regime or "UNKNOWN",
        "trend_state": trend_state or "UNKNOWN",
        "volatility_state": volatility_state or "UNKNOWN",
        "liquidity_state": liquidity_state or "UNKNOWN",
        "active_scenario": active_scenario or "UNKNOWN",
        "flow_confirmation": flow_confirmation or "UNKNOWN",
        "post_liquidity_reaction": post_liquidity_reaction or "UNKNOWN",
        "trap_state": trap_state or "UNKNOWN",
        "absorption_state": absorption_state or "UNKNOWN",
        "setup_candidate": setup_candidate or "UNKNOWN",
        "setup_direction": setup_direction or "UNKNOWN",
        "entry_trigger_status": entry_trigger_status or "UNKNOWN",
        "side": str(record.get("side") or trade_decision_evidence.get("side") or "UNKNOWN").upper(),
        "entry_model": entry_model or "UNKNOWN",
        "risk_grade": risk_grade or "UNKNOWN",
        "plan_quality": plan_quality or "UNKNOWN",
    }

    if any(value == "UNKNOWN" for value in group_key.values()):
        reason_codes.append("UNKNOWN_CONTEXT")

    return group_key, reason_codes


def _exclude_reason(record: dict[str, Any]) -> str | None:
    trade_fate = str(record.get("trade_fate") or record.get("outcome_result") or record.get("outcome_status") or "UNKNOWN").upper()
    if record.get("is_closed_outcome") is not True:
        return "NOT_CLOSED_OUTCOME"
    if record.get("edge_eligible") is not True:
        return "EDGE_ELIGIBLE_FALSE"
    if trade_fate not in ELIGIBLE_TRADE_FATES:
        return f"EXCLUDED_TRADE_FATE_{trade_fate}"
    return None


def build_conditional_edge_rows(
    records: list[dict[str, Any]],
    *,
    latest_context: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    source_records = [record for record in records if isinstance(record, dict) and _candidate_record(record)]
    excluded_breakdown: dict[str, int] = defaultdict(int)
    eligible_records: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in source_records:
        reason = _exclude_reason(record)
        if reason is not None:
            excluded_breakdown[reason] += 1
            continue

        group_key, context_reasons = _extract_context(record, latest_context)
        enriched = dict(record)
        enriched["group_key"] = group_key
        enriched["group_reason_codes"] = _record_reason_codes(record) + context_reasons
        eligible_records.append(enriched)
        grouped[str(group_key)].append(enriched)

    conditional_rows = []
    for items in grouped.values():
        group_key = dict(items[0]["group_key"])
        conditional_rows.append(
            {
                "group_key": group_key,
                "records": items,
                "source_outcome_ids": sorted({str(item.get("outcome_id") or "") for item in items if item.get("outcome_id")}),
                "source_paper_trade_ids": sorted({str(item.get("paper_trade_id") or "") for item in items if item.get("paper_trade_id")}),
                "reason_codes": list(
                    dict.fromkeys(
                        code
                        for item in items
                        for code in item.get("group_reason_codes", [])
                        if code
                    )
                ),
            }
        )

    return {
        "source_records": source_records,
        "eligible_records": eligible_records,
        "conditional_rows": conditional_rows,
        "excluded_breakdown": dict(sorted(excluded_breakdown.items())),
        "excluded_outcome_count": sum(excluded_breakdown.values()),
        "reason_codes": ["NO_DATA"] if not eligible_records else [],
    }
