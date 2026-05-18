from __future__ import annotations

from src.paper_outcome.outcome_truth_engine import evaluate_outcome_truth
from src.paper_outcome.paper_lifecycle_engine import build_paper_lifecycle
from src.paper_outcome.paper_outcome_registry import build_lineage_id
from src.paper_outcome.paper_outcome_validator import validate_paper_outcome


def _valid_payload() -> dict:
    decision = {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "symbol": "BTCUSDT",
        "trade_plan_id": "TPN_1",
        "decision_id": "DEC_1",
        "lineage_id": "LIN_DECISION",
        "setup_candidate_id": "SETUP_1",
        "entry_trigger_id": "ENTRY_1",
        "decision_status": "ALLOW_PAPER",
        "side": "LONG",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit_1": 110.0,
        "take_profit_2": None,
        "invalidation_level": 89.0,
    }
    lifecycle = build_paper_lifecycle(decision, timestamp_utc="2026-05-18T00:00:00Z")
    payload = evaluate_outcome_truth(
        lifecycle,
        [{"timestamp_utc": "2026-05-18T00:01:00Z", "symbol": "BTCUSDT", "low": 99.0, "high": 111.0}],
        as_of_timestamp_utc="2026-05-18T00:10:00Z",
    )
    payload["timestamp_utc"] = "2026-05-18T00:10:00Z"
    payload["lineage_id"] = build_lineage_id("outcome", payload["paper_trade_id"], payload["trade_fate"])
    payload["parent_lineage_ids"] = [build_lineage_id("paper_trade", payload["paper_trade_id"])]
    return {k: v for k, v in payload.items() if not str(k).startswith("_")}


def test_invalid_enum_validator_detects_error() -> None:
    payload = _valid_payload()
    payload["trade_fate"] = "NOT_VALID"
    result = validate_paper_outcome(payload)
    assert not result["is_valid"]
    assert "INVALID_TRADE_FATE_ENUM" in result["errors"]


def test_missing_lineage_id_is_detected() -> None:
    payload = _valid_payload()
    payload["lineage_id"] = ""
    result = validate_paper_outcome(payload)
    assert not result["is_valid"]
    assert "MISSING_LINEAGE_ID" in result["errors"]


def test_output_required_fields_pass() -> None:
    payload = _valid_payload()
    result = validate_paper_outcome(payload)
    assert result["is_valid"]


def test_real_trade_and_private_api_fields_are_absent() -> None:
    payload = _valid_payload()
    assert "real_trade_allowed" not in payload
    assert "private_api_used" not in payload
    assert "safe_to_open_real_trade" not in payload
    result = validate_paper_outcome(payload)
    assert result["is_valid"]
