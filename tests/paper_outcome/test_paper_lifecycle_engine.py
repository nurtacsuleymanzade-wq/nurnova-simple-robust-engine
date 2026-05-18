from __future__ import annotations

from src.paper_outcome.paper_lifecycle_engine import build_paper_lifecycle


def _decision(status: str = "ALLOW_PAPER") -> dict:
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "symbol": "BTCUSDT",
        "trade_plan_id": "TPN_1",
        "decision_id": "DEC_1",
        "lineage_id": "LIN_DECISION",
        "setup_candidate_id": "SETUP_1",
        "entry_trigger_id": "ENTRY_1",
        "decision_status": status,
        "side": "LONG",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit_1": 110.0,
        "take_profit_2": 120.0,
        "invalidation_level": 89.0,
    }


def test_allow_paper_creates_paper_trade() -> None:
    payload = build_paper_lifecycle(_decision(), timestamp_utc="2026-05-18T01:00:00Z")
    assert payload["paper_trade_id"].startswith("PPR_")
    assert payload["lifecycle_state"] == "WAITING_ENTRY"
    assert payload["trade_fate"] == "NO_ENTRY_TOUCH"


def test_block_does_not_create_paper_trade() -> None:
    payload = build_paper_lifecycle(_decision("BLOCK"), timestamp_utc="2026-05-18T01:00:00Z")
    assert payload["lifecycle_state"] == "UNKNOWN"
    assert payload["trade_fate"] == "NO_ACTIONABLE_DECISION"
    assert "DECISION_STATUS_BLOCK" in payload["reason_codes"]
    assert "NO_ACTIONABLE_DECISION" in payload["reason_codes"]
    assert "NO_OPEN_PAPER_TRADE" in payload["reason_codes"]
    assert payload["edge_eligible"] is False


def test_wait_does_not_create_paper_trade() -> None:
    payload = build_paper_lifecycle(_decision("WAIT"), timestamp_utc="2026-05-18T01:00:00Z")
    assert payload["lifecycle_state"] == "UNKNOWN"
    assert payload["trade_fate"] == "NO_ACTIONABLE_DECISION"
    assert "DECISION_STATUS_WAIT" in payload["reason_codes"]
    assert "NO_ACTIONABLE_DECISION" in payload["reason_codes"]
    assert "NO_OPEN_PAPER_TRADE" in payload["reason_codes"]


def test_deterministic_paper_trade_id_stays_stable() -> None:
    first = build_paper_lifecycle(_decision(), timestamp_utc="2026-05-18T01:00:00Z")
    second = build_paper_lifecycle(_decision(), timestamp_utc="2026-05-18T02:00:00Z")
    assert first["paper_trade_id"] == second["paper_trade_id"]


def test_feeds_next_are_produced() -> None:
    payload = build_paper_lifecycle(_decision(), timestamp_utc="2026-05-18T01:00:00Z")
    assert payload["feeds_next"] == [
        "PHASE_8_CONDITIONAL_EDGE_MATRIX",
        "PHASE_10_NOVA_BRAIN_SNAPSHOT",
    ]
