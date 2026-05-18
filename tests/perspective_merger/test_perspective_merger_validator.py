from __future__ import annotations

from src.perspective_merger.perspective_merger_validator import validate_perspective_merger


def _payload() -> dict:
    return {
        "timestamp_utc": "2026-05-18T08:00:00Z",
        "block_id": "PHASE_12_PERSPECTIVE_MERGER",
        "symbol": "BTCUSDT",
        "perspective_merger_id": "PMG_1",
        "lineage_id": "LIN_1",
        "core_bias": "LONG",
        "smc_bias": "UNKNOWN",
        "mm_bias": "UNKNOWN",
        "core_confidence": "HIGH",
        "smc_confidence": "UNKNOWN",
        "mm_confidence": "UNKNOWN",
        "alignment_status": "INSUFFICIENT_DATA",
        "alignment_score": 0.0,
        "perspective_agreement": {"core_smc": False, "core_mm": False, "smc_mm": False, "three_way": False},
        "bias_conflicts": [],
        "conflict_sources": [],
        "confidence_adjustment": {},
        "core_summary": {},
        "smc_summary": {},
        "mm_summary": {},
        "merged_context": {},
        "decision_gate_context_note": None,
        "nova_brain_context_note": None,
        "data_quality": "DEGRADED",
        "reason_codes": ["MISSING_SMC_PERSPECTIVE", "MISSING_MM_PERSPECTIVE", "MISSING_PERSPECTIVE"],
        "feeds_next": [
            "PHASE_10_NOVA_BRAIN_SNAPSHOT",
            "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
            "PHASE_13_ADAPTIVE_INTELLIGENCE",
        ],
        "warnings": [],
    }


def test_invalid_enum_is_caught() -> None:
    payload = _payload()
    payload["core_bias"] = "BAD"
    result = validate_perspective_merger(payload)
    assert "INVALID_CORE_BIAS_ENUM" in result["errors"]


def test_output_required_fields_pass() -> None:
    result = validate_perspective_merger(_payload())
    assert result["is_valid"] is True


def test_feeds_next_is_correct() -> None:
    assert _payload()["feeds_next"] == [
        "PHASE_10_NOVA_BRAIN_SNAPSHOT",
        "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
        "PHASE_13_ADAPTIVE_INTELLIGENCE",
    ]
