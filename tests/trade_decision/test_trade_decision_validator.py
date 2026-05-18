from __future__ import annotations

import pytest
from src.trade_decision.trade_decision_validator import validate_trade_decision


def _valid_payload(**overrides) -> dict:
    base = {
        "timestamp_utc": "2026-05-18T10:00:00Z",
        "block_id": "PHASE_6_TRADE_PLAN_DECISION_GATE",
        "symbol": "BTCUSDT",
        "trade_plan_id": "TPN_ABCDEF1234567890123456",
        "decision_id": "DEC_ABCDEF1234567890123456",
        "lineage_id": "LINCTX_ABCDEF1234",
        "parent_lineage_ids": [],
        "setup_candidate_id": "SCE_ABCDEF1234",
        "entry_trigger_id": "ETG_ABCDEF1234",
        "market_state_id": "MS_ABCDEF1234",
        "active_scenario_id": "ASC_ABCDEF1234",
        "flow_reaction_id": "FR_ABCDEF1234",
        "side": "LONG",
        "entry_model": "RETEST",
        "entry_price": 100.0,
        "stop_loss": 96.0,
        "take_profit_1": 106.0,
        "take_profit_2": None,
        "invalidation_level": 96.0,
        "rr_to_tp1": 1.5,
        "rr_to_tp2": None,
        "risk_grade": "MEDIUM",
        "decision_status": "ALLOW_PAPER",
        "decision_confidence": 0.7,
        "plan_quality": "B",
        "position_policy": {
            "paper_only": True,
            "real_trade_allowed": False,
            "max_risk_pct": None,
            "risk_notes": [],
        },
        "entry_reason_codes": ["ENTRY_LONG_RETEST_SUPPORT"],
        "sl_reason_codes": ["SL_LONG_STRUCTURAL_LOW"],
        "tp_reason_codes": ["TP1_LONG_LIQUIDITY_ABOVE"],
        "invalidation_reason_codes": ["INVALIDATION_LONG_STRUCTURAL_LOW"],
        "blocking_reason_codes": [],
        "risk_reason_codes": [],
        "evidence": {
            "setup_entry_evidence": {},
            "market_state_evidence": {},
            "active_scenario_evidence": {},
            "flow_reaction_evidence": {},
            "liquidity_evidence": {},
            "structure_evidence": {},
            "candle_dna_evidence": {},
        },
        "scores": {
            "setup_quality_score": 0.7,
            "entry_trigger_score": 1.0,
            "liquidity_destination_score": 1.0,
            "structure_invalidation_score": 1.0,
            "rr_quality_score": 0.75,
            "risk_penalty": 0.0,
            "template_risk_score": 0.0,
        },
        "data_quality": "OK",
        "feeds_next": [
            "PHASE_7_PAPER_LIFECYCLE_OUTCOME_TRUTH",
            "PHASE_8_CONDITIONAL_EDGE_MATRIX",
            "PHASE_10_NOVA_BRAIN_SNAPSHOT",
        ],
        "reason_codes": ["TRADE_DECISION_COMPUTED"],
        "warnings": [],
    }
    base.update(overrides)
    return base


# ── Test 14: invalid enum validator catches ───────────────────────────────────

def test_invalid_side_enum_caught():
    result = validate_trade_decision(_valid_payload(side="BUY"))
    assert not result["is_valid"]
    assert any("INVALID_SIDE_ENUM" in e for e in result["errors"])


def test_invalid_entry_model_enum_caught():
    result = validate_trade_decision(_valid_payload(entry_model="MARKET"))
    assert not result["is_valid"]
    assert any("INVALID_ENTRY_MODEL_ENUM" in e for e in result["errors"])


def test_invalid_risk_grade_enum_caught():
    result = validate_trade_decision(_valid_payload(risk_grade="CRITICAL"))
    assert not result["is_valid"]
    assert any("INVALID_RISK_GRADE_ENUM" in e for e in result["errors"])


def test_invalid_decision_status_enum_caught():
    result = validate_trade_decision(_valid_payload(decision_status="MAYBE"))
    assert not result["is_valid"]
    assert any("INVALID_DECISION_STATUS_ENUM" in e for e in result["errors"])


def test_invalid_plan_quality_enum_caught():
    result = validate_trade_decision(_valid_payload(plan_quality="S"))
    assert not result["is_valid"]
    assert any("INVALID_PLAN_QUALITY_ENUM" in e for e in result["errors"])


# ── Test 15: confidence range validator catches ────────────────────────────────

def test_confidence_above_1_caught():
    result = validate_trade_decision(_valid_payload(decision_confidence=1.1))
    assert not result["is_valid"]
    assert any("INVALID_DECISION_CONFIDENCE_RANGE" in e for e in result["errors"])


def test_confidence_below_0_caught():
    result = validate_trade_decision(_valid_payload(decision_confidence=-0.1))
    assert not result["is_valid"]
    assert any("INVALID_DECISION_CONFIDENCE_RANGE" in e for e in result["errors"])


# ── Test 16: output required fields PASS ──────────────────────────────────────

def test_valid_payload_passes():
    result = validate_trade_decision(_valid_payload())
    assert result["is_valid"] is True
    assert result["errors"] == []


# ── Test 17: feeds_next correct ───────────────────────────────────────────────

def test_feeds_next_correct():
    payload = _valid_payload()
    assert isinstance(payload["feeds_next"], list)
    assert "PHASE_7_PAPER_LIFECYCLE_OUTCOME_TRUTH" in payload["feeds_next"]
    assert "PHASE_8_CONDITIONAL_EDGE_MATRIX" in payload["feeds_next"]
    assert "PHASE_10_NOVA_BRAIN_SNAPSHOT" in payload["feeds_next"]


# ── Test 18: real_trade_allowed must be false ──────────────────────────────────

def test_real_trade_allowed_must_be_false():
    policy = {"paper_only": True, "real_trade_allowed": True, "max_risk_pct": None, "risk_notes": []}
    result = validate_trade_decision(_valid_payload(position_policy=policy))
    assert not result["is_valid"]
    assert any("REAL_TRADE_ALLOWED_MUST_BE_FALSE" in e for e in result["errors"])


def test_real_trade_allowed_false_passes():
    result = validate_trade_decision(_valid_payload())
    assert result["is_valid"]


# ── ALLOW_PAPER enforcement ────────────────────────────────────────────────────

def test_allow_paper_missing_entry_price():
    result = validate_trade_decision(_valid_payload(entry_price=None))
    assert not result["is_valid"]
    assert any("ALLOW_PAPER_REQUIRES_ENTRY_PRICE" in e for e in result["errors"])


def test_allow_paper_missing_stop_loss():
    result = validate_trade_decision(_valid_payload(stop_loss=None))
    assert not result["is_valid"]
    assert any("ALLOW_PAPER_REQUIRES_STOP_LOSS" in e for e in result["errors"])


def test_allow_paper_missing_take_profit_1():
    result = validate_trade_decision(_valid_payload(take_profit_1=None))
    assert not result["is_valid"]
    assert any("ALLOW_PAPER_REQUIRES_TAKE_PROFIT_1" in e for e in result["errors"])


def test_allow_paper_missing_invalidation():
    result = validate_trade_decision(_valid_payload(invalidation_level=None))
    assert not result["is_valid"]
    assert any("ALLOW_PAPER_REQUIRES_INVALIDATION_LEVEL" in e for e in result["errors"])


def test_allow_paper_zero_rr_fails():
    result = validate_trade_decision(_valid_payload(rr_to_tp1=0.0))
    assert not result["is_valid"]
    assert any("ALLOW_PAPER_REQUIRES_POSITIVE_RR" in e for e in result["errors"])


# ── Missing required field caught ─────────────────────────────────────────────

def test_missing_trade_plan_id():
    payload = _valid_payload()
    del payload["trade_plan_id"]
    result = validate_trade_decision(payload)
    assert not result["is_valid"]
    assert any("trade_plan_id" in e for e in result["errors"])


def test_missing_lineage_id():
    result = validate_trade_decision(_valid_payload(lineage_id=""))
    assert not result["is_valid"]
    assert any("MISSING_LINEAGE_ID" in e for e in result["errors"])


# ── Evidence and scores must be dicts ─────────────────────────────────────────

def test_evidence_not_dict_caught():
    result = validate_trade_decision(_valid_payload(evidence=[]))
    assert not result["is_valid"]
    assert any("EVIDENCE_NOT_DICT" in e for e in result["errors"])


def test_scores_not_dict_caught():
    result = validate_trade_decision(_valid_payload(scores=None))
    assert not result["is_valid"]
    assert any("SCORES_NOT_DICT" in e for e in result["errors"])


# ── NO_TRADE is a valid decision (non-ALLOW_PAPER validation skipped) ─────────

def test_no_trade_decision_with_null_levels():
    payload = _valid_payload(
        decision_status="NO_TRADE",
        decision_confidence=0.0,
        side="NO_TRADE",
        entry_price=None,
        stop_loss=None,
        take_profit_1=None,
        invalidation_level=None,
        rr_to_tp1=None,
        plan_quality="INVALID",
        risk_grade="NO_TRADE",
        entry_reason_codes=[],
        sl_reason_codes=[],
        tp_reason_codes=[],
        invalidation_reason_codes=[],
        reason_codes=["NO_SETUP_AVAILABLE"],
    )
    result = validate_trade_decision(payload)
    assert result["is_valid"] is True
