from __future__ import annotations

import pytest
from src.setup_entry.setup_entry_validator import validate_setup_entry


def _valid_payload(**overrides) -> dict:
    base = {
        "timestamp_utc": "2026-05-18T10:00:00Z",
        "block_id": "PHASE_5_SETUP_CANDIDATE_ENTRY_TRIGGER",
        "symbol": "BTCUSDT",
        "setup_candidate_id": "SCE_ABCDEFABCDEF123456789012",
        "entry_trigger_id": "ETG_ABCDEFABCDEF123456789012",
        "lineage_id": "LINCTX_ABCDEF1234",
        "parent_lineage_ids": [],
        "market_state_id": "MS_ABCDEF1234",
        "active_scenario_id": "ASC_ABCDEF1234",
        "flow_reaction_id": "FR_ABCDEF1234",
        "setup_candidate": "LONG_CONTINUATION_SETUP",
        "setup_direction": "LONG",
        "setup_quality": "A",
        "setup_confidence": 0.8,
        "entry_trigger_status": "TRIGGER_READY",
        "entry_trigger_quality": "HIGH",
        "entry_trigger_confidence": 0.75,
        "timeframe_context": {"primary_tf": "1m"},
        "evidence": {},
        "scores": {},
        "setup_reason_codes": ["SETUP_DETECTED"],
        "entry_trigger_reason_codes": ["TRIGGER_DETECTED"],
        "blocking_reason_codes": [],
        "conflict_reason_codes": [],
        "missing_evidence": [],
        "data_quality": "OK",
        "feeds_next": ["PHASE_6_TRADE_PLAN_DECISION_GATE"],
        "reason_codes": ["SETUP_ENTRY_COMPUTED"],
        "warnings": [],
    }
    base.update(overrides)
    return base


def test_valid_payload_passes():
    result = validate_setup_entry(_valid_payload())
    assert result["is_valid"] is True
    assert result["errors"] == []


def test_invalid_enum_validator_catches():
    payload = _valid_payload(setup_candidate="INVALID_SETUP")
    result = validate_setup_entry(payload)
    assert not result["is_valid"]
    assert any("INVALID_SETUP_CANDIDATE" in e for e in result["errors"])


def test_missing_lineage_id_validator_catches():
    payload = _valid_payload(lineage_id="")
    result = validate_setup_entry(payload)
    assert not result["is_valid"]
    assert any("MISSING_LINEAGE_ID" in e for e in result["errors"])


def test_confidence_range_out_of_bounds():
    payload = _valid_payload(setup_confidence=1.5)
    result = validate_setup_entry(payload)
    assert not result["is_valid"]
    assert any("INVALID_SETUP_CONFIDENCE_RANGE" in e for e in result["errors"])


def test_entry_trigger_confidence_range_out_of_bounds():
    payload = _valid_payload(entry_trigger_confidence=-0.1)
    result = validate_setup_entry(payload)
    assert not result["is_valid"]


def test_output_required_fields_pass():
    payload = _valid_payload()
    result = validate_setup_entry(payload)
    assert result["is_valid"]


def test_feeds_next_correct():
    payload = _valid_payload()
    assert isinstance(payload["feeds_next"], list)
    assert len(payload["feeds_next"]) > 0


def test_missing_market_state_id_reason_code():
    payload = _valid_payload(market_state_id="", reason_codes=["MARKET_STATE_MISSING"])
    result = validate_setup_entry(payload)
    assert result["is_valid"]


def test_missing_market_state_id_without_reason_code():
    payload = _valid_payload(market_state_id="", reason_codes=[])
    result = validate_setup_entry(payload)
    assert not result["is_valid"]


def test_missing_active_scenario_id_reason_code():
    payload = _valid_payload(active_scenario_id="", reason_codes=["ACTIVE_SCENARIO_MISSING"])
    result = validate_setup_entry(payload)
    assert result["is_valid"]


def test_missing_active_scenario_id_without_reason_code():
    payload = _valid_payload(active_scenario_id="", reason_codes=[])
    result = validate_setup_entry(payload)
    assert not result["is_valid"]


def test_missing_flow_reaction_id_reason_code():
    payload = _valid_payload(flow_reaction_id="", reason_codes=["FLOW_REACTION_MISSING"])
    result = validate_setup_entry(payload)
    assert result["is_valid"]


def test_missing_flow_reaction_id_without_reason_code():
    payload = _valid_payload(flow_reaction_id="", reason_codes=[])
    result = validate_setup_entry(payload)
    assert not result["is_valid"]
