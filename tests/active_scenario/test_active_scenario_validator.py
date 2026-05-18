from __future__ import annotations

from src.active_scenario.active_scenario_candidate_engine import build_scenario_candidates
from src.active_scenario.active_scenario_selector import select_active_scenario
from src.active_scenario.active_scenario_validator import validate_active_scenario


def _evidence() -> dict:
    return {
        "market_state_evidence": {
            "market_state_id": "MS_TEST",
            "market_regime": "UPTREND",
            "trend_state": "BULLISH",
            "volatility_state": "NORMAL",
            "structure_state": "HH_HL",
            "liquidity_pressure_state": "ABOVE",
            "flow_state": "BUY_PRESSURE",
            "maturity_state": "MID",
            "risk_state": "LOW",
        },
        "liquidity_evidence": {"liquidity_pressure_state": "ABOVE"},
        "structure_evidence": {"structure_state": "HH_HL"},
        "flow_evidence": {"flow_state": "BUY_PRESSURE"},
        "reaction_evidence": {},
        "risk_evidence": {"risk_state": "LOW"},
    }


def _valid_payload() -> dict:
    ev = _evidence()
    candidates, frame = build_scenario_candidates(ev, "OK")
    selected = select_active_scenario(
        candidates=candidates,
        feature_frame=frame,
        data_quality="OK",
        market_state_present=True,
    )
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "block_id": "PHASE_3_ACTIVE_SCENARIO_ENGINE",
        "symbol": "BTCUSDT",
        "active_scenario_id": "ASC_TEST",
        "lineage_id": "LINCTX_TEST",
        "parent_lineage_ids": ["LIN_PARENT"],
        "market_state_id": "MS_TEST",
        "active_scenario": selected["active_scenario"],
        "scenario_bias": selected["scenario_bias"],
        "scenario_confidence": selected["scenario_confidence"],
        "scenario_quality": selected["scenario_quality"],
        "selection_reason_codes": selected["selection_reason_codes"],
        "rejection_reason_codes": selected["rejection_reason_codes"],
        "conflict_reason_codes": selected["conflict_reason_codes"],
        "scenario_candidates": candidates,
        "selected_candidate": selected["selected_candidate"],
        "evidence": ev,
        "candidate_scores": selected["candidate_scores"],
        "data_quality": "OK",
        "feeds_next": selected["feeds_next"],
        "reason_codes": ["OK"],
        "warnings": [],
    }


def test_invalid_active_scenario_enum_detected() -> None:
    payload = _valid_payload()
    payload["active_scenario"] = "NOT_VALID"
    res = validate_active_scenario(payload)
    assert not res["is_valid"]
    assert "INVALID_ACTIVE_SCENARIO" in res["errors"]


def test_missing_lineage_id_detected() -> None:
    payload = _valid_payload()
    payload["lineage_id"] = ""
    res = validate_active_scenario(payload)
    assert not res["is_valid"]
    assert "MISSING_LINEAGE_ID" in res["errors"]


def test_confidence_out_of_range_detected() -> None:
    payload = _valid_payload()
    payload["scenario_confidence"] = 1.5
    res = validate_active_scenario(payload)
    assert not res["is_valid"]
    assert "INVALID_SCENARIO_CONFIDENCE_RANGE" in res["errors"]


def test_required_fields_pass() -> None:
    res = validate_active_scenario(_valid_payload())
    assert res["is_valid"]

