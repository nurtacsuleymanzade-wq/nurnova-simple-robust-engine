from __future__ import annotations

import pytest
from src.flow_reaction.flow_reaction_validator import validate_flow_reaction


def _valid_payload(**overrides) -> dict:
    base = {
        "timestamp_utc": "2026-05-18T10:00:00Z",
        "block_id": "PHASE_4_FLOW_CONFIRMATION_POST_LIQUIDITY_REACTION",
        "symbol": "BTCUSDT",
        "flow_reaction_id": "FR_ABCDEFABCDEF123456789012",
        "lineage_id": "LINCTX_ABCDEF1234",
        "parent_lineage_ids": [],
        "market_state_id": "MS_ABCDEF1234",
        "active_scenario_id": "ASC_ABCDEF1234",
        "flow_confirmation": "CONFIRMED_LONG",
        "post_liquidity_reaction": "CONTINUATION_AFTER_SWEEP",
        "absorption_state": "NONE",
        "trap_state": "NONE",
        "reaction_bias": "LONG",
        "reaction_confidence": 0.75,
        "reaction_quality": "HIGH",
        "evidence": {},
        "scores": {},
        "confirmation_reason_codes": ["SCENARIO_BIAS_LONG"],
        "rejection_reason_codes": [],
        "trap_reason_codes": [],
        "absorption_reason_codes": [],
        "conflict_reason_codes": [],
        "data_quality": "OK",
        "feeds_next": ["PHASE_5_SETUP_CANDIDATE_ENTRY_TRIGGER"],
        "reason_codes": ["FLOW_REACTION_COMPUTED"],
        "warnings": [],
    }
    base.update(overrides)
    return base


def test_valid_payload_passes():
    result = validate_flow_reaction(_valid_payload())
    assert result["is_valid"] is True
    assert result["errors"] == []


def test_invalid_enum_validator_catches():
    payload = _valid_payload(flow_confirmation="MADE_UP_VALUE")
    result = validate_flow_reaction(payload)
    assert not result["is_valid"]
    assert any("INVALID_FLOW_CONFIRMATION" in e for e in result["errors"])


def test_missing_lineage_id_validator_catches():
    payload = _valid_payload(lineage_id="")
    result = validate_flow_reaction(payload)
    assert not result["is_valid"]
    assert any("MISSING_LINEAGE_ID" in e for e in result["errors"])


def test_confidence_range_out_of_bounds():
    payload = _valid_payload(reaction_confidence=1.5)
    result = validate_flow_reaction(payload)
    assert not result["is_valid"]
    assert any("INVALID_REACTION_CONFIDENCE_RANGE" in e for e in result["errors"])


def test_confidence_negative_out_of_bounds():
    payload = _valid_payload(reaction_confidence=-0.1)
    result = validate_flow_reaction(payload)
    assert not result["is_valid"]


def test_output_required_fields_pass():
    payload = _valid_payload()
    result = validate_flow_reaction(payload)
    assert result["is_valid"]


def test_feeds_next_correct():
    payload = _valid_payload()
    assert isinstance(payload["feeds_next"], list)
    assert len(payload["feeds_next"]) > 0


def test_missing_market_state_id_reason_code():
    payload = _valid_payload(market_state_id="", reason_codes=["MARKET_STATE_MISSING"])
    result = validate_flow_reaction(payload)
    assert result["is_valid"]


def test_missing_market_state_id_without_reason_code():
    payload = _valid_payload(market_state_id="", reason_codes=[])
    result = validate_flow_reaction(payload)
    assert not result["is_valid"]
    assert any("MARKET_STATE_ID_MISSING_WITHOUT_REASON_CODE" in e for e in result["errors"])


def test_missing_active_scenario_id_reason_code():
    payload = _valid_payload(active_scenario_id="", reason_codes=["ACTIVE_SCENARIO_MISSING"])
    result = validate_flow_reaction(payload)
    assert result["is_valid"]


def test_missing_active_scenario_id_without_reason_code():
    payload = _valid_payload(active_scenario_id="", reason_codes=[])
    result = validate_flow_reaction(payload)
    assert not result["is_valid"]
    assert any("ACTIVE_SCENARIO_ID_MISSING_WITHOUT_REASON_CODE" in e for e in result["errors"])
