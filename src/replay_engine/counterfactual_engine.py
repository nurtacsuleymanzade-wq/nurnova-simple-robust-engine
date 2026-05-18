from __future__ import annotations

from typing import Any


def _alt_r(item: dict[str, Any]) -> float | None:
    value = item.get("alternative_r_multiple")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _base_r(source_outcome: dict[str, Any]) -> float:
    value = source_outcome.get("r_multiple")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_counterfactual_summary(
    source_outcome: dict[str, Any],
    replay_scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    original_r = _base_r(source_outcome)
    valid = [item for item in replay_scenarios if _alt_r(item) is not None]

    if not valid:
        return {
            "replay_status": "REPLAY_FAILED",
            "counterfactual_summary": {
                "original_r_multiple": original_r,
                "trade_skipped_better": False,
                "late_entry_better": False,
                "tighter_stop_hurt": False,
                "farther_tp_better": False,
                "scenario_count": 0,
            },
            "best_alternative_outcome": {},
            "worst_alternative_outcome": {},
            "learning_signals": ["NO_VALID_COUNTERFACTUALS"],
        }

    best = max(valid, key=lambda item: _alt_r(item) if _alt_r(item) is not None else -999999)
    worst = min(valid, key=lambda item: _alt_r(item) if _alt_r(item) is not None else 999999)

    by_type = {str(item.get("scenario_type") or "UNKNOWN"): item for item in valid}
    no_trade_r = _alt_r(by_type.get("NO_TRADE", {}))
    late_entry_r = max(
        [_alt_r(by_type.get(name, {})) for name in ("LATE_ENTRY", "ENTRY_DELAY", "WAIT_INSTEAD_OF_ENTRY") if _alt_r(by_type.get(name, {})) is not None] or [None]
    )
    tighter_stop_r = _alt_r(by_type.get("TIGHTER_STOP", {}))
    farther_tp_r = _alt_r(by_type.get("FARTHER_TP", {}))

    learning_signals: list[str] = []
    if no_trade_r is not None and no_trade_r > original_r:
        learning_signals.append("NO_TRADE_WOULD_HAVE_BEEN_BETTER")
    if late_entry_r is not None and late_entry_r > original_r:
        learning_signals.append("LATE_ENTRY_IMPROVES_OUTCOME")
    if tighter_stop_r is not None and tighter_stop_r < original_r:
        learning_signals.append("TIGHTER_STOP_HURTS_TRADE")
    if farther_tp_r is not None and farther_tp_r > original_r:
        learning_signals.append("FARTHER_TP_IMPROVES_EXPECTANCY")
    if not learning_signals:
        learning_signals.append("ORIGINAL_DECISION_BROADLY_CONFIRMED")

    success_count = sum(1 for item in valid if item.get("better_than_original"))
    fail_count = sum(1 for item in valid if item.get("worse_than_original"))
    replay_status = "REPLAY_SUCCESS"
    if success_count == 0 or fail_count == 0:
        replay_status = "REPLAY_PARTIAL"

    return {
        "replay_status": replay_status,
        "counterfactual_summary": {
            "original_r_multiple": original_r,
            "trade_skipped_better": no_trade_r is not None and no_trade_r > original_r,
            "late_entry_better": late_entry_r is not None and late_entry_r > original_r,
            "tighter_stop_hurt": tighter_stop_r is not None and tighter_stop_r < original_r,
            "farther_tp_better": farther_tp_r is not None and farther_tp_r > original_r,
            "scenario_count": len(valid),
            "better_scenario_count": success_count,
            "worse_scenario_count": fail_count,
        },
        "best_alternative_outcome": {
            "scenario_type": best.get("scenario_type"),
            "alternative_outcome": best.get("alternative_outcome"),
            "alternative_r_multiple": best.get("alternative_r_multiple"),
        },
        "worst_alternative_outcome": {
            "scenario_type": worst.get("scenario_type"),
            "alternative_outcome": worst.get("alternative_outcome"),
            "alternative_r_multiple": worst.get("alternative_r_multiple"),
        },
        "learning_signals": learning_signals,
    }
