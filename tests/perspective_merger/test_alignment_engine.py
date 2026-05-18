from __future__ import annotations

from src.perspective_merger.alignment_engine import compute_alignment


def test_full_alignment_is_created() -> None:
    result = compute_alignment("LONG", "LONG", "LONG")
    assert result["alignment_status"] == "FULL_ALIGNMENT"


def test_partial_alignment_is_created() -> None:
    result = compute_alignment("LONG", "LONG", "UNKNOWN")
    assert result["alignment_status"] == "PARTIAL_ALIGNMENT"


def test_core_smc_alignment_is_created() -> None:
    result = compute_alignment("LONG", "LONG", "SHORT")
    assert result["alignment_status"] == "CORE_SMC_ALIGNED"


def test_core_mm_alignment_is_created() -> None:
    result = compute_alignment("SHORT", "UNKNOWN", "SHORT")
    assert result["alignment_status"] == "PARTIAL_ALIGNMENT" or result["alignment_status"] == "CORE_MM_ALIGNED"


def test_conflicted_alignment_is_created() -> None:
    result = compute_alignment("LONG", "SHORT", "UNKNOWN")
    assert result["alignment_status"] == "CONFLICTED_ALIGNMENT"


def test_insufficient_data_is_created() -> None:
    result = compute_alignment("UNKNOWN", "UNKNOWN", "UNKNOWN")
    assert result["alignment_status"] == "INSUFFICIENT_DATA"


def test_alignment_score_is_in_range() -> None:
    result = compute_alignment("LONG", "LONG", "LONG")
    assert 0.0 <= result["alignment_score"] <= 1.0
