from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .replay_registry import ELIGIBLE_TRADE_FATES, REPLAY_SCENARIOS, build_scenario_id


def _parse_ts(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _base_r(record: dict[str, Any]) -> float | None:
    value = record.get("r_multiple")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _eligible_reason(record: dict[str, Any]) -> str | None:
    fate = str(record.get("trade_fate") or record.get("outcome_result") or record.get("outcome_status") or "UNKNOWN").upper()
    if record.get("is_closed_outcome") is not True:
        return "NOT_CLOSED_OUTCOME"
    if record.get("edge_eligible") is not True:
        return "EDGE_ELIGIBLE_FALSE"
    if fate not in ELIGIBLE_TRADE_FATES:
        return f"EXCLUDED_TRADE_FATE_{fate}"
    return None


def filter_replay_eligible_outcomes(records: list[dict[str, Any]]) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    excluded_breakdown: dict[str, int] = {}

    for record in records:
        if not isinstance(record, dict):
            continue
        if not any(key in record for key in ("outcome_id", "paper_trade_id", "trade_fate", "is_closed_outcome", "edge_eligible")):
            continue
        reason = _eligible_reason(record)
        if reason is not None:
            excluded_breakdown[reason] = excluded_breakdown.get(reason, 0) + 1
            continue
        eligible.append(record)

    eligible.sort(key=lambda item: _parse_ts(item.get("closed_at") or item.get("timestamp_utc")), reverse=True)
    return {
        "eligible_records": eligible,
        "excluded_breakdown": dict(sorted(excluded_breakdown.items())),
        "excluded_count": sum(excluded_breakdown.values()),
        "reason_codes": ["NO_REPLAY_DATA"] if not eligible else [],
    }


def _adjust_r(base_r: float | None, scenario_type: str) -> tuple[float | None, str]:
    if base_r is None:
        return None, "MISSING_BASE_R"

    mapping = {
        "EARLY_ENTRY": base_r + 0.2 if base_r >= 0 else base_r - 0.2,
        "LATE_ENTRY": base_r - 0.2 if base_r >= 0 else base_r + 0.2,
        "RETEST_ENTRY": base_r + 0.1 if base_r >= 0 else base_r + 0.05,
        "BREAKOUT_ENTRY": base_r + 0.05 if base_r >= 0 else base_r - 0.1,
        "RECLAIM_ENTRY": base_r + 0.08 if base_r >= 0 else base_r + 0.02,
        "TIGHTER_STOP": base_r + 0.1 if base_r > 0 else base_r - 0.25,
        "WIDER_STOP": base_r - 0.1 if base_r > 0 else base_r + 0.25,
        "CLOSER_TP": max(0.05, base_r * 0.75) if base_r > 0 else base_r,
        "FARTHER_TP": base_r * 1.2 if base_r > 0 else base_r,
        "NO_TRADE": 0.0,
        "WAIT_INSTEAD_OF_ENTRY": 0.0 if base_r < 0 else max(0.0, base_r * 0.25),
        "BLOCK_INSTEAD_OF_ENTRY": 0.0,
        "ENTRY_DELAY": base_r - 0.15 if base_r > 0 else base_r + 0.15,
        "EARLY_EXIT": base_r * 0.5,
        "HOLD_LONGER": base_r * 1.15 if base_r > 0 else base_r * 1.1,
    }
    if scenario_type not in mapping:
        return None, "UNKNOWN_REPLAY_SCENARIO"
    return round(mapping[scenario_type], 4), "REPLAY_SCENARIO_COMPUTED"


def _alternative_outcome(original: dict[str, Any], scenario_type: str, alternative_r: float | None) -> dict[str, Any]:
    if alternative_r is None:
        return {
            "trade_fate": "UNKNOWN",
            "close_reason": "REPLAY_INPUT_INSUFFICIENT",
            "r_multiple": None,
        }

    if scenario_type in {"NO_TRADE", "WAIT_INSTEAD_OF_ENTRY", "BLOCK_INSTEAD_OF_ENTRY"}:
        return {
            "trade_fate": "NO_TRADE",
            "close_reason": "COUNTERFACTUAL_NO_TRADE",
            "r_multiple": alternative_r,
        }
    if alternative_r > 0:
        trade_fate = "TP2_HIT" if alternative_r >= 1.5 else "TP1_HIT"
    elif alternative_r < 0:
        trade_fate = "SL_HIT" if alternative_r <= -0.5 else "PARTIAL_LOSS"
    else:
        trade_fate = "BREAKEVEN"
    return {
        "trade_fate": trade_fate,
        "close_reason": f"COUNTERFACTUAL_{scenario_type}",
        "r_multiple": alternative_r,
        "original_trade_fate": original.get("trade_fate"),
    }


def generate_replay_scenarios(source_outcome: dict[str, Any]) -> list[dict[str, Any]]:
    scenario_types = [scenario for scenario in REPLAY_SCENARIOS if scenario != "UNKNOWN"]
    base_r = _base_r(source_outcome)
    original_r = base_r if base_r is not None else 0.0
    scenarios: list[dict[str, Any]] = []

    for scenario_type in scenario_types:
        alternative_r, reason = _adjust_r(base_r, scenario_type)
        alternative_outcome = _alternative_outcome(source_outcome, scenario_type, alternative_r)
        scenario_id = build_scenario_id(
            source_outcome.get("outcome_id"),
            scenario_type,
            {
                "source_trade_fate": source_outcome.get("trade_fate"),
                "source_r_multiple": source_outcome.get("r_multiple"),
                "alternative_r_multiple": alternative_r,
            },
        )
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "alternative_outcome": alternative_outcome,
                "alternative_r_multiple": alternative_r,
                "better_than_original": alternative_r is not None and alternative_r > original_r,
                "worse_than_original": alternative_r is not None and alternative_r < original_r,
                "reason_codes": [reason] if reason else [],
            }
        )

    if not scenarios:
        scenarios.append(
            {
                "scenario_id": build_scenario_id(source_outcome.get("outcome_id"), "UNKNOWN", {}),
                "scenario_type": "UNKNOWN",
                "alternative_outcome": {"trade_fate": "UNKNOWN"},
                "alternative_r_multiple": None,
                "better_than_original": False,
                "worse_than_original": False,
                "reason_codes": ["NO_REPLAY_SCENARIOS_GENERATED"],
            }
        )
    return scenarios
