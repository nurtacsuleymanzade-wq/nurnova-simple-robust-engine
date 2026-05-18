from __future__ import annotations

from src.nova_brain.brain_registry import build_brain_snapshot_id
from src.nova_brain.brain_snapshot_validator import validate_brain_snapshot


def _valid_payload() -> dict:
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "block_id": "PHASE_10_NOVA_BRAIN_SNAPSHOT",
        "symbol": "BTCUSDT",
        "brain_snapshot_id": "BRN_123",
        "lineage_id": "LIN_123",
        "system_health": {"status": "HEALTHY", "health_score": 0.9, "critical_failures": [], "degraded_components": [], "data_quality_pressure": 0.1},
        "edge_growth": {"growing_edges": [], "stable_edges": [], "decaying_edges": [], "dead_edges": []},
        "edge_decay": {},
        "risk_map": {"global_risk_level": "LOW", "regime_risk": {}, "fake_breakout_risk": {}, "data_degradation_risk": {}},
        "fake_scenario_pressure": {"pressure_level": "NORMAL", "top_fake_scenarios": []},
        "regime_risk": {},
        "setup_survival": {},
        "decision_quality_overview": {"status": "STABLE", "decision_quality_score": 0.6, "bad_decision_clusters": []},
        "replay_learning_summary": {},
        "operational_alerts": [],
        "dominant_market_story": {"primary_story": "story", "secondary_story": None, "market_bias": "LONG"},
        "brain_summary": [],
        "data_quality": "OK",
        "reason_codes": ["OK"],
        "feeds_next": ["PHASE_11_PROBABILISTIC_SCENARIO_ENGINE", "PHASE_12_META_LEARNING_LAYER"],
        "warnings": [],
    }


def test_deterministic_brain_snapshot_id_stays_stable() -> None:
    first = build_brain_snapshot_id("BTCUSDT", {"a": 1})
    second = build_brain_snapshot_id("BTCUSDT", {"a": 1})
    assert first == second


def test_invalid_enum_validator_detects_error() -> None:
    payload = _valid_payload()
    payload["system_health"]["status"] = "NOT_VALID"
    result = validate_brain_snapshot(payload)
    assert not result["is_valid"]
    assert "INVALID_SYSTEM_HEALTH_ENUM" in result["errors"]


def test_output_required_fields_pass() -> None:
    result = validate_brain_snapshot(_valid_payload())
    assert result["is_valid"]


def test_feeds_next_are_correct() -> None:
    payload = _valid_payload()
    assert payload["feeds_next"] == ["PHASE_11_PROBABILISTIC_SCENARIO_ENGINE", "PHASE_12_META_LEARNING_LAYER"]
