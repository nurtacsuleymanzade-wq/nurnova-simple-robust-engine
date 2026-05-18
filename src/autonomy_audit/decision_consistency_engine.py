from __future__ import annotations

from typing import Any

from .autonomy_registry import SAFETY_STATUS, clamp, risk_level_from_score, safety_status_from_positive_score, safety_status_from_risk_score


def _system_health_score(nova_brain: dict[str, Any]) -> float | None:
    status = str((nova_brain.get("system_health") or {}).get("status") or "UNKNOWN").upper()
    mapping = {"HEALTHY": 0.9, "STRESSED": 0.6, "DEGRADED": 0.35, "CRITICAL": 0.1}
    return mapping.get(status)


def evaluate_decision_consistency(
    *,
    lineage_audit: dict[str, Any] | None,
    trade_decision: dict[str, Any] | None,
    replay_engine: dict[str, Any] | None,
    nova_brain: dict[str, Any] | None,
    probabilistic_engine: dict[str, Any] | None,
    perspective_merger: dict[str, Any] | None,
    edge_matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    lineage_audit = lineage_audit or {}
    trade_decision = trade_decision or {}
    replay_engine = replay_engine or {}
    nova_brain = nova_brain or {}
    probabilistic_engine = probabilistic_engine or {}
    perspective_merger = perspective_merger or {}
    edge_matrix = edge_matrix or {}

    replay_status = str(replay_engine.get("replay_status") or "UNKNOWN").upper()
    if replay_status == "REPLAY_SUCCESS":
        replay_score = 0.85
    elif replay_status == "REPLAY_PARTIAL":
        replay_score = 0.55
    elif replay_status == "NO_REPLAY_DATA":
        replay_score = 0.1
    else:
        replay_score = 0.25
    replay_validation = {
        "status": safety_status_from_positive_score(replay_score),
        "score": replay_score,
        "replay_status": replay_status,
        "scenario_count": int((replay_engine.get("counterfactual_summary") or {}).get("scenario_count") or 0),
    }
    if replay_status == "NO_REPLAY_DATA":
        replay_validation["status"] = "FAIL"

    decision_quality_score = 0.55
    if str(trade_decision.get("decision_status") or "UNKNOWN").upper() == "ALLOW_PAPER":
        decision_quality_score += 0.1
    if str(trade_decision.get("decision_status") or "UNKNOWN").upper() == "BLOCK":
        decision_quality_score -= 0.15
    if str((nova_brain.get("decision_quality_overview") or {}).get("status") or "UNKNOWN").upper() == "UNKNOWN":
        decision_quality_score -= 0.15
    if str((perspective_merger.get("alignment_status") or "UNKNOWN")).upper() == "INSUFFICIENT_DATA":
        decision_quality_score -= 0.1
    if replay_status == "NO_REPLAY_DATA":
        decision_quality_score -= 0.15
    decision_quality_score = clamp(decision_quality_score)
    decision_quality = {
        "status": safety_status_from_positive_score(decision_quality_score),
        "score": decision_quality_score,
        "decision_status": trade_decision.get("decision_status"),
        "brain_decision_quality": (nova_brain.get("decision_quality_overview") or {}).get("status"),
    }

    fake_confidence_score = 0.0
    if float(((perspective_merger.get("confidence_adjustment") or {}).get("context_only_adjusted_confidence") or 0.0)) >= 0.7 and replay_status == "NO_REPLAY_DATA":
        fake_confidence_score += 0.25
    if float(((probabilistic_engine.get("dominant_path") or {}).get("estimated_probability") or 0.0)) >= 0.6 and int(edge_matrix.get("edge_eligible_outcome_count") or 0) == 0:
        fake_confidence_score += 0.35
    if str((nova_brain.get("decision_quality_overview") or {}).get("status") or "UNKNOWN").upper() == "UNKNOWN":
        fake_confidence_score += 0.15
    if float(trade_decision.get("decision_confidence") or 0.0) == 0.0 and str(trade_decision.get("decision_status") or "").upper() == "BLOCK":
        fake_confidence_score += 0.05
    fake_confidence_score = clamp(fake_confidence_score)
    fake_confidence_risk = {
        "status": safety_status_from_risk_score(fake_confidence_score),
        "score": fake_confidence_score,
        "risk_level": risk_level_from_score(fake_confidence_score),
    }

    missing_sources = len(lineage_audit.get("missing_source") or [])
    data_spine_score = clamp(1.0 - min(1.0, missing_sources / 10.0))
    if str((perspective_merger.get("data_quality") or "UNKNOWN")).upper() == "DEGRADED":
        data_spine_score = clamp(data_spine_score - 0.15)
    data_spine_health = {
        "status": safety_status_from_positive_score(data_spine_score),
        "score": data_spine_score,
        "missing_sources": missing_sources,
    }

    probability = float(((probabilistic_engine.get("dominant_path") or {}).get("estimated_probability") or 0.0))
    edge_support = int(edge_matrix.get("edge_eligible_outcome_count") or 0)
    probabilistic_score = clamp(0.8 if probability < 0.55 else 0.55 if edge_support > 0 else 0.2)
    if str(((probabilistic_engine.get("scenario_pressure_map") or {}).get("pressure_level") or "UNKNOWN")).upper() == "DANGEROUS":
        probabilistic_score = clamp(probabilistic_score - 0.1)
    probabilistic_consistency = {
        "status": safety_status_from_positive_score(probabilistic_score),
        "score": probabilistic_score,
        "dominant_probability": probability,
        "edge_support": edge_support,
    }

    perspective_score = 0.9
    alignment_status = str(perspective_merger.get("alignment_status") or "UNKNOWN").upper()
    if alignment_status == "FULL_ALIGNMENT":
        perspective_score = 0.9
    elif alignment_status in {"PARTIAL_ALIGNMENT", "CORE_SMC_ALIGNED", "CORE_MM_ALIGNED", "SMC_MM_ALIGNED"}:
        perspective_score = 0.6
    elif alignment_status == "INSUFFICIENT_DATA":
        perspective_score = 0.2
    elif alignment_status in {"CONFLICTED_ALIGNMENT", "NO_ALIGNMENT"}:
        perspective_score = 0.15
    perspective_alignment_consistency = {
        "status": safety_status_from_positive_score(perspective_score),
        "score": perspective_score,
        "alignment_status": alignment_status,
    }

    system_score = _system_health_score(nova_brain) if nova_brain else None
    system_health = {
        "status": safety_status_from_positive_score(system_score),
        "score": system_score,
        "health_status": (nova_brain.get("system_health") or {}).get("status"),
        "global_risk_level": (nova_brain.get("risk_map") or {}).get("global_risk_level"),
    }

    reason_codes = [
        f"REPLAY_{replay_status}",
        f"PERSPECTIVE_{alignment_status}",
    ]
    for section in (replay_validation, decision_quality, fake_confidence_risk, data_spine_health, probabilistic_consistency, perspective_alignment_consistency, system_health):
        assert section["status"] in SAFETY_STATUS
    return {
        "replay_validation": replay_validation,
        "decision_quality": decision_quality,
        "fake_confidence_risk": fake_confidence_risk,
        "data_spine_health": data_spine_health,
        "probabilistic_consistency": probabilistic_consistency,
        "perspective_alignment_consistency": perspective_alignment_consistency,
        "system_health": system_health,
        "reason_codes": reason_codes,
    }
