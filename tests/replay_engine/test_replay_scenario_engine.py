from __future__ import annotations

from src.replay_engine.replay_scenario_engine import filter_replay_eligible_outcomes, generate_replay_scenarios


def _outcome(*, fate: str = "TP2_HIT", closed: bool = True, eligible: bool = True, r: float = 1.5) -> dict:
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "closed_at": "2026-05-18T00:05:00Z",
        "symbol": "BTCUSDT",
        "outcome_id": f"OUT_{fate}",
        "paper_trade_id": f"PPR_{fate}",
        "trade_fate": fate,
        "is_closed_outcome": closed,
        "edge_eligible": eligible,
        "r_multiple": r,
    }


def test_closed_edge_eligible_outcome_is_replay_input() -> None:
    result = filter_replay_eligible_outcomes([_outcome()])
    assert len(result["eligible_records"]) == 1


def test_timeout_is_not_replay_input() -> None:
    result = filter_replay_eligible_outcomes([_outcome(fate="DIAGNOSTIC_TIMEOUT", eligible=False)])
    assert len(result["eligible_records"]) == 0


def test_no_entry_is_not_replay_input() -> None:
    result = filter_replay_eligible_outcomes([_outcome(fate="NO_ENTRY_TOUCH", eligible=False)])
    assert len(result["eligible_records"]) == 0


def test_early_entry_scenario_is_created() -> None:
    scenarios = generate_replay_scenarios(_outcome())
    assert any(item["scenario_type"] == "EARLY_ENTRY" for item in scenarios)


def test_retest_entry_scenario_is_created() -> None:
    scenarios = generate_replay_scenarios(_outcome())
    assert any(item["scenario_type"] == "RETEST_ENTRY" for item in scenarios)


def test_no_trade_scenario_is_created() -> None:
    scenarios = generate_replay_scenarios(_outcome())
    assert any(item["scenario_type"] == "NO_TRADE" for item in scenarios)


def test_deterministic_scenario_id_stays_stable() -> None:
    first = generate_replay_scenarios(_outcome())
    second = generate_replay_scenarios(_outcome())
    first_map = {item["scenario_type"]: item["scenario_id"] for item in first}
    second_map = {item["scenario_type"]: item["scenario_id"] for item in second}
    assert first_map == second_map
