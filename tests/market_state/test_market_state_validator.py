from __future__ import annotations

from src.market_state.market_state_classifier import classify_market_state
from src.market_state.market_state_registry import REQUIRED_FIELDS
from src.market_state.market_state_validator import validate_market_state


def _valid_payload() -> dict:
    return classify_market_state(
        symbol="BTCUSDT",
        evidence_records={
            "candle_dna": {"timestamp_utc": "2026-05-18T00:00:00Z", "symbol": "BTCUSDT"},
            "structure": {"timestamp_utc": "2026-05-18T00:00:01Z", "trend_state": "UPTREND", "structure_label": "HH"},
            "liquidity": {"timestamp_utc": "2026-05-18T00:00:02Z", "draw_on_liquidity": "ABOVE"},
            "flow": {"timestamp_utc": "2026-05-18T00:00:03Z", "cvd_state": "BUY_PRESSURE"},
            "context": {"timestamp_utc": "2026-05-18T00:00:04Z", "auction_state": "ACCEPTANCE", "volatility_state": "NORMAL"},
        },
        source_files_used=["state/simple/latest_market_structure_v2.json"],
        missing_sources=[],
        parent_lineage_ids=["LIN_PARENT"],
    )


def test_invalid_registry_value_detected() -> None:
    payload = _valid_payload()
    payload["market_regime"] = "NOT_VALID"
    result = validate_market_state(payload)
    assert not result["is_valid"]
    assert "INVALID_MARKET_REGIME" in result["errors"]


def test_missing_lineage_id_detected() -> None:
    payload = _valid_payload()
    payload["lineage_id"] = ""
    result = validate_market_state(payload)
    assert not result["is_valid"]
    assert "MISSING_LINEAGE_ID" in result["errors"]


def test_confidence_out_of_range_detected() -> None:
    payload = _valid_payload()
    payload["confidence"] = 1.5
    result = validate_market_state(payload)
    assert not result["is_valid"]
    assert "INVALID_CONFIDENCE_RANGE" in result["errors"]


def test_output_required_fields_pass() -> None:
    payload = _valid_payload()
    result = validate_market_state(payload)
    assert result["is_valid"]
    for field in REQUIRED_FIELDS:
        assert field in payload

