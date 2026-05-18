from __future__ import annotations

from typing import Any

from .perspective_merger_registry import ALIGNMENT_STATUSES


def _directional(bias: str) -> bool:
    return bias in {"LONG", "SHORT"}


def _same_direction(left: str, right: str) -> bool:
    return _directional(left) and left == right


def compute_alignment(core_bias: str, smc_bias: str, mm_bias: str) -> dict[str, Any]:
    core_smc = _same_direction(core_bias, smc_bias)
    core_mm = _same_direction(core_bias, mm_bias)
    smc_mm = _same_direction(smc_bias, mm_bias)
    three_way = core_smc and core_mm

    if core_bias == "UNKNOWN" or (smc_bias == "UNKNOWN" and mm_bias == "UNKNOWN"):
        status = "INSUFFICIENT_DATA"
        score = 0.0
    elif three_way:
        status = "FULL_ALIGNMENT"
        score = 1.0
    elif any(
        [
            core_smc and mm_bias in {"UNKNOWN", "NEUTRAL"},
            core_mm and smc_bias in {"UNKNOWN", "NEUTRAL"},
            smc_mm and core_bias in {"UNKNOWN", "NEUTRAL"},
        ]
    ):
        status = "PARTIAL_ALIGNMENT"
        score = 0.75
    elif core_smc:
        status = "CORE_SMC_ALIGNED"
        score = 0.66
    elif core_mm:
        status = "CORE_MM_ALIGNED"
        score = 0.66
    elif smc_mm:
        status = "SMC_MM_ALIGNED"
        score = 0.6
    elif "LONG" in {core_bias, smc_bias, mm_bias} and "SHORT" in {core_bias, smc_bias, mm_bias}:
        status = "CONFLICTED_ALIGNMENT"
        score = 0.2
    elif all(bias in {"NEUTRAL", "NO_TRADE", "UNKNOWN"} for bias in {core_bias, smc_bias, mm_bias}):
        status = "NO_ALIGNMENT"
        score = 0.1
    else:
        status = "NO_ALIGNMENT"
        score = 0.15

    assert status in ALIGNMENT_STATUSES
    return {
        "alignment_status": status,
        "alignment_score": round(score, 4),
        "perspective_agreement": {
            "core_smc": core_smc,
            "core_mm": core_mm,
            "smc_mm": smc_mm,
            "three_way": three_way,
        },
    }
