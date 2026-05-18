from __future__ import annotations

from src.autonomy_audit.autonomy_validator import validate_autonomy_audit


def _payload() -> dict:
    return {
        "timestamp_utc": "2026-05-18T09:00:00Z",
        "block_id": "PHASE_13_AUTONOMOUS_INTELLIGENCE_READINESS",
        "symbol": "BTCUSDT",
        "autonomy_audit_id": "AUD_1",
        "lineage_id": "LIN_1",
        "autonomy_status": "NOT_READY",
        "autonomy_score": 0.1,
        "safe_for_autonomy": False,
        "human_override_required": "REQUIRED",
        "global_risk_level": "EXTREME",
        "lineage_integrity": {"status": "FAIL", "score": 0.1},
        "edge_stability": {"status": "FAIL", "score": 0.1},
        "replay_validation": {"status": "FAIL", "score": 0.1},
        "template_risk": {"status": "FAIL", "score": 0.8},
        "hallucination_risk": {"status": "FAIL", "score": 0.8},
        "fake_confidence_risk": {},
        "data_spine_health": {},
        "decision_quality": {},
        "probabilistic_consistency": {},
        "perspective_alignment_consistency": {},
        "system_health": {},
        "edge_decay_pressure": {},
        "operational_stability": {},
        "critical_failures": [],
        "autonomy_blockers": [],
        "autonomy_strengths": [],
        "safety_constraints": [],
        "recommended_human_controls": [],
        "autonomy_notes": [],
        "brain_governor_summary": {},
        "data_quality": "DEGRADED",
        "reason_codes": [],
        "feeds_next": ["PHASE_14_META_GOVERNOR", "PHASE_15_EVOLUTION_LAYER"],
        "warnings": [],
    }


def test_invalid_enum_is_caught() -> None:
    payload = _payload()
    payload["autonomy_status"] = "BAD"
    result = validate_autonomy_audit(payload)
    assert "INVALID_AUTONOMY_STATUS_ENUM" in result["errors"]


def test_output_required_fields_pass() -> None:
    result = validate_autonomy_audit(_payload())
    assert result["is_valid"] is True


def test_feeds_next_is_correct() -> None:
    assert _payload()["feeds_next"] == ["PHASE_14_META_GOVERNOR", "PHASE_15_EVOLUTION_LAYER"]
