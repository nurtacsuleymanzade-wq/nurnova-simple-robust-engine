from __future__ import annotations

from collections import Counter
from typing import Any

from .perspective_merger_registry import BIAS_VALUES, PERSPECTIVE_CONFIDENCE, normalize_bias


def _score_to_confidence(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 0.75:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "INVALID"


def _confidence_from_payload(payload: dict[str, Any] | None) -> str:
    payload = payload or {}
    explicit = str(payload.get("confidence_label") or payload.get("confidence") or "").upper()
    if explicit in PERSPECTIVE_CONFIDENCE:
        return explicit
    data_quality = str(payload.get("data_quality") or "").upper()
    quality = str(payload.get("quality") or payload.get("perspective_quality") or "").upper()
    if data_quality == "OK" or quality == "HIGH":
        return "HIGH"
    if data_quality == "ACCEPTABLE" or quality == "MEDIUM":
        return "MEDIUM"
    if data_quality in {"DEGRADED", "LOW"} or quality == "LOW":
        return "LOW"
    if data_quality == "INVALID":
        return "INVALID"
    return "UNKNOWN"


def _path_bias(probabilistic_engine: dict[str, Any] | None) -> str:
    dominant_path = str(((probabilistic_engine or {}).get("dominant_path") or {}).get("scenario_path") or "").upper()
    if dominant_path in {"BULLISH_CONTINUATION_PATH", "COMPRESSION_BREAKOUT_UP_PATH"}:
        return "LONG"
    if dominant_path in {"BEARISH_CONTINUATION_PATH", "COMPRESSION_BREAKOUT_DOWN_PATH"}:
        return "SHORT"
    if dominant_path in {"RANGE_ROTATION_PATH", "MEAN_REVERSION_PATH", "REVERSAL_PATH"}:
        return "NEUTRAL"
    return "UNKNOWN"


def _extract_core_bias(inputs: dict[str, Any]) -> tuple[str, str, dict[str, Any], list[str]]:
    trade_decision = inputs.get("trade_decision") or {}
    setup_entry = inputs.get("setup_entry") or {}
    active_scenario = inputs.get("active_scenario") or {}
    probabilistic_engine = inputs.get("probabilistic_engine") or {}
    nova_brain = inputs.get("nova_brain") or {}

    evidence = {
        "trade_decision_side": normalize_bias(trade_decision.get("side")),
        "setup_direction": normalize_bias(setup_entry.get("setup_direction")),
        "scenario_bias": normalize_bias(active_scenario.get("scenario_bias")),
        "probabilistic_bias": _path_bias(probabilistic_engine),
        "nova_brain_bias": normalize_bias(((nova_brain.get("dominant_market_story") or {}).get("market_bias"))),
    }
    reason_codes: list[str] = []
    votes = [value for value in evidence.values() if value in {"LONG", "SHORT", "NEUTRAL", "NO_TRADE"}]
    if not votes:
        return "UNKNOWN", "UNKNOWN", evidence, ["MISSING_CORE_PERSPECTIVE"]

    counts = Counter(votes)
    top_bias, top_count = counts.most_common(1)[0]
    if top_count >= 3 and top_bias in {"LONG", "SHORT"}:
        confidence = "HIGH"
    elif top_count >= 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    if len({bias for bias in votes if bias in {"LONG", "SHORT"}}) > 1:
        top_bias = "CONFLICTED"
        confidence = "LOW"
        reason_codes.append("CORE_INTERNAL_BIAS_CONFLICT")
    reason_codes.append(f"CORE_BIAS_{top_bias}")
    assert top_bias in BIAS_VALUES
    assert confidence in PERSPECTIVE_CONFIDENCE
    return top_bias, confidence, evidence, reason_codes


def _extract_external_bias(
    payload: dict[str, Any] | None,
    *,
    missing_reason: str,
    label: str,
) -> tuple[str, str, dict[str, Any], list[str]]:
    if not payload:
        return "UNKNOWN", "UNKNOWN", {}, [missing_reason]

    summary = {
        "bias": normalize_bias(
            payload.get("bias")
            or payload.get("market_bias")
            or payload.get("directional_bias")
            or payload.get("side")
            or payload.get("perspective_bias")
        ),
        "lineage_id": payload.get("lineage_id"),
        "data_quality": payload.get("data_quality"),
    }
    confidence = _confidence_from_payload(payload)
    reason_codes = [f"{label}_BIAS_{summary['bias']}"]
    return summary["bias"], confidence, summary, reason_codes


def extract_perspective_biases(inputs: dict[str, Any]) -> dict[str, Any]:
    core_bias, core_confidence, core_summary, core_reasons = _extract_core_bias(inputs)
    smc_bias, smc_confidence, smc_summary, smc_reasons = _extract_external_bias(
        inputs.get("smc"),
        missing_reason="MISSING_SMC_PERSPECTIVE",
        label="SMC",
    )
    mm_bias, mm_confidence, mm_summary, mm_reasons = _extract_external_bias(
        inputs.get("mm"),
        missing_reason="MISSING_MM_PERSPECTIVE",
        label="MM",
    )

    return {
        "core_bias": core_bias,
        "smc_bias": smc_bias,
        "mm_bias": mm_bias,
        "core_confidence": core_confidence,
        "smc_confidence": smc_confidence,
        "mm_confidence": mm_confidence,
        "core_summary": core_summary,
        "smc_summary": smc_summary,
        "mm_summary": mm_summary,
        "reason_codes": list(dict.fromkeys(core_reasons + smc_reasons + mm_reasons)),
    }
