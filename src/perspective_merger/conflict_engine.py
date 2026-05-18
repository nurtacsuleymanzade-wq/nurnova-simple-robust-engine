from __future__ import annotations

from typing import Any

from .perspective_merger_registry import CONFLICT_TYPES, confidence_to_score


def _modifier_from_alignment(status: str) -> float:
    if status == "FULL_ALIGNMENT":
        return 0.15
    if status in {"PARTIAL_ALIGNMENT", "CORE_SMC_ALIGNED", "CORE_MM_ALIGNED", "SMC_MM_ALIGNED"}:
        return 0.08
    if status == "CONFLICTED_ALIGNMENT":
        return -0.15
    if status == "INSUFFICIENT_DATA":
        return -0.05
    return 0.0


def _clamp(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def evaluate_conflicts(
    *,
    core_bias: str,
    smc_bias: str,
    mm_bias: str,
    core_confidence: str,
    smc_confidence: str,
    mm_confidence: str,
    alignment_status: str,
) -> dict[str, Any]:
    bias_conflicts: list[dict[str, Any]] = []
    conflict_sources: list[str] = []
    reason_codes: list[str] = []

    if smc_bias == "UNKNOWN":
        bias_conflicts.append({"conflict_type": "MISSING_SMC", "source": "smc", "details": "SMC perspective missing"})
        conflict_sources.append("SMC_MISSING")
        reason_codes.append("MISSING_SMC_PERSPECTIVE")
    if mm_bias == "UNKNOWN":
        bias_conflicts.append({"conflict_type": "MISSING_MM", "source": "mm", "details": "MM perspective missing"})
        conflict_sources.append("MM_MISSING")
        reason_codes.append("MISSING_MM_PERSPECTIVE")
    if core_bias == "UNKNOWN":
        bias_conflicts.append({"conflict_type": "MISSING_CORE", "source": "core", "details": "Core perspective missing"})
        conflict_sources.append("CORE_MISSING")
        reason_codes.append("MISSING_CORE_PERSPECTIVE")

    directional = {core_bias, smc_bias, mm_bias}
    if "LONG" in directional and "SHORT" in directional:
        if core_bias in {"LONG", "SHORT"} and smc_bias in {"LONG", "SHORT"} and core_bias != smc_bias:
            bias_conflicts.append({"conflict_type": "CORE_SMC_CONFLICT", "source": "core_vs_smc", "details": f"{core_bias} vs {smc_bias}"})
            conflict_sources.append("CORE_VS_SMC")
        if core_bias in {"LONG", "SHORT"} and mm_bias in {"LONG", "SHORT"} and core_bias != mm_bias:
            bias_conflicts.append({"conflict_type": "CORE_MM_CONFLICT", "source": "core_vs_mm", "details": f"{core_bias} vs {mm_bias}"})
            conflict_sources.append("CORE_VS_MM")
        if smc_bias in {"LONG", "SHORT"} and mm_bias in {"LONG", "SHORT"} and smc_bias != mm_bias:
            bias_conflicts.append({"conflict_type": "SMC_MM_CONFLICT", "source": "smc_vs_mm", "details": f"{smc_bias} vs {mm_bias}"})
            conflict_sources.append("SMC_VS_MM")
        if core_bias in {"LONG", "SHORT"} and smc_bias in {"LONG", "SHORT"} and mm_bias in {"LONG", "SHORT"}:
            bias_conflicts.append({"conflict_type": "THREE_WAY_CONFLICT", "source": "three_way", "details": "Directional conflict across perspectives"})
            conflict_sources.append("THREE_WAY")
        reason_codes.append("PERSPECTIVE_DIRECTIONAL_CONFLICT")

    if "LOW" in {core_confidence, smc_confidence, mm_confidence} and alignment_status == "CONFLICTED_ALIGNMENT":
        bias_conflicts.append({"conflict_type": "LOW_CONFIDENCE_CONFLICT", "source": "confidence", "details": "Conflict exists under low-confidence perspective"})
        conflict_sources.append("LOW_CONFIDENCE")
        reason_codes.append("LOW_CONFIDENCE_CONFLICT")

    before = confidence_to_score(core_confidence)
    modifier = _modifier_from_alignment(alignment_status)
    adjusted = None if before is None else _clamp(before + modifier)

    decision_note = f"Context-only alignment={alignment_status}, modifier={modifier:+.2f}; no decision gate override."
    nova_note = f"Perspective agreement core={core_bias}, smc={smc_bias}, mm={mm_bias}; use as context only."

    for item in bias_conflicts:
        assert item["conflict_type"] in CONFLICT_TYPES

    return {
        "bias_conflicts": bias_conflicts,
        "conflict_sources": list(dict.fromkeys(conflict_sources)),
        "confidence_adjustment": {
            "core_confidence_before": before,
            "alignment_modifier": modifier,
            "context_only_adjusted_confidence": adjusted,
        },
        "decision_gate_context_note": decision_note,
        "nova_brain_context_note": nova_note,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }
