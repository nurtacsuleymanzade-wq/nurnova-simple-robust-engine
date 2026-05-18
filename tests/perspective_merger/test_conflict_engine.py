from __future__ import annotations

from src.perspective_merger.conflict_engine import evaluate_conflicts
from src.perspective_merger.perspective_merger_registry import build_perspective_merger_id


def test_conflict_source_is_generated() -> None:
    result = evaluate_conflicts(
        core_bias="LONG",
        smc_bias="SHORT",
        mm_bias="UNKNOWN",
        core_confidence="MEDIUM",
        smc_confidence="LOW",
        mm_confidence="UNKNOWN",
        alignment_status="CONFLICTED_ALIGNMENT",
    )
    assert len(result["conflict_sources"]) >= 1


def test_confidence_adjustment_is_context_only() -> None:
    result = evaluate_conflicts(
        core_bias="LONG",
        smc_bias="LONG",
        mm_bias="UNKNOWN",
        core_confidence="HIGH",
        smc_confidence="MEDIUM",
        mm_confidence="UNKNOWN",
        alignment_status="PARTIAL_ALIGNMENT",
    )
    assert result["confidence_adjustment"]["alignment_modifier"] is not None
    assert "override" in result["decision_gate_context_note"].lower()


def test_deterministic_perspective_merger_id_is_stable() -> None:
    seed = {"core_bias": "LONG", "smc_bias": "UNKNOWN", "mm_bias": "UNKNOWN", "alignment_status": "INSUFFICIENT_DATA"}
    first = build_perspective_merger_id("BTCUSDT", seed)
    second = build_perspective_merger_id("BTCUSDT", seed)
    assert first == second
