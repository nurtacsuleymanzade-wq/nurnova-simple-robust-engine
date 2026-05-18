from __future__ import annotations

from typing import Any

from .autonomy_registry import AUTONOMY_STATUS, HUMAN_OVERRIDE, RISK_LEVEL, SAFETY_STATUS, clamp, risk_level_from_score


def _positive(section: dict[str, Any] | None, *, invert_risk: bool = False) -> float:
    section = section or {}
    score = section.get("score")
    if score is None:
        return 0.0
    value = float(score)
    return clamp(1.0 - value) if invert_risk else clamp(value)


def evaluate_autonomy_governor(
    *,
    lineage_integrity: dict[str, Any],
    edge_stability: dict[str, Any],
    replay_validation: dict[str, Any],
    template_risk: dict[str, Any],
    hallucination_risk: dict[str, Any],
    decision_consistency: dict[str, Any],
    edge_decay_pressure: dict[str, Any],
    trade_decision: dict[str, Any] | None,
    paper_outcome: dict[str, Any] | None,
    perspective_merger: dict[str, Any] | None,
) -> dict[str, Any]:
    trade_decision = trade_decision or {}
    paper_outcome = paper_outcome or {}
    perspective_merger = perspective_merger or {}

    weighted_score = (
        _positive(lineage_integrity) * 0.2
        + _positive(edge_stability) * 0.15
        + _positive(replay_validation) * 0.15
        + _positive(template_risk, invert_risk=True) * 0.1
        + _positive(hallucination_risk, invert_risk=True) * 0.15
        + _positive(decision_consistency.get("decision_quality")) * 0.08
        + _positive(decision_consistency.get("probabilistic_consistency")) * 0.05
        + _positive(decision_consistency.get("perspective_alignment_consistency")) * 0.04
        + _positive(decision_consistency.get("system_health")) * 0.04
        + _positive(decision_consistency.get("data_spine_health")) * 0.04
    )
    autonomy_score = clamp(weighted_score)

    critical_failures: list[str] = []
    autonomy_blockers: list[str] = []
    autonomy_strengths: list[str] = []
    safety_constraints = [
        "PAPER_ONLY_EXECUTION_ONLY",
        "NO_PRIVATE_API",
        "NO_DECISION_GATE_OVERRIDE",
        "NO_REAL_ORDER_EXECUTION",
        "REQUIRE_CLOSED_EDGE_ELIGIBLE_OUTCOMES_FOR_AUTONOMY_ESCALATION",
        "REQUIRE_REPLAY_VALIDATION_FOR_AUTONOMY_ESCALATION",
    ]
    recommended_human_controls: list[str] = []
    autonomy_notes: list[str] = []

    if lineage_integrity.get("status") == "FAIL":
        critical_failures.append("LINEAGE_FAIL")
        autonomy_blockers.append("LINEAGE_INTEGRITY_BLOCKER")
    if edge_stability.get("status") == "FAIL":
        critical_failures.append("EDGE_STABILITY_FAIL")
        autonomy_blockers.append("NO_STABLE_EDGE_BLOCKER")
    if replay_validation.get("status") == "FAIL":
        critical_failures.append("REPLAY_VALIDATION_FAIL")
        autonomy_blockers.append("NO_REPLAY_VALIDATION_BLOCKER")
    if hallucination_risk.get("status") == "FAIL":
        critical_failures.append("HALLUCINATION_RISK_HIGH")
        autonomy_blockers.append("HALLUCINATION_BLOCKER")
    if template_risk.get("status") == "FAIL":
        autonomy_blockers.append("TEMPLATE_RISK_BLOCKER")
    if str((perspective_merger.get("alignment_status") or "UNKNOWN")).upper() == "INSUFFICIENT_DATA":
        autonomy_blockers.append("PERSPECTIVE_GAP_BLOCKER")
    if float(((decision_consistency.get("probabilistic_consistency") or {}).get("score") or 0.0)) < 0.3:
        autonomy_blockers.append("PROBABILITY_EDGE_CONTRADICTION_BLOCKER")
    if str(trade_decision.get("decision_status") or "UNKNOWN").upper() == "BLOCK":
        autonomy_notes.append("Latest trade decision is BLOCK with invalid plan economics.")
    if not bool(paper_outcome.get("is_closed_outcome")):
        autonomy_notes.append("Latest paper outcome is not a closed truth sample.")

    if not autonomy_blockers:
        autonomy_strengths.append("NO_HARD_BLOCKER_DETECTED")
    if lineage_integrity.get("status") == "PASS":
        autonomy_strengths.append("LINEAGE_INTEGRITY_STRONG")
    if replay_validation.get("status") == "PASS":
        autonomy_strengths.append("REPLAY_VALIDATION_STRONG")
    if hallucination_risk.get("status") == "PASS":
        autonomy_strengths.append("HALLUCINATION_RISK_LOW")

    combined_risk = max(
        float(hallucination_risk.get("score") or 0.0),
        float(template_risk.get("score") or 0.0),
        float(edge_decay_pressure.get("score") or 0.0),
        1.0 - float(lineage_integrity.get("score") or 0.0),
        1.0 - float(edge_stability.get("score") or 0.0),
    )
    global_risk_level = risk_level_from_score(clamp(combined_risk))

    if critical_failures:
        human_override_required = "REQUIRED"
    elif autonomy_blockers:
        human_override_required = "STRONGLY_RECOMMENDED"
    elif autonomy_score >= 0.75:
        human_override_required = "OPTIONAL"
    else:
        human_override_required = "STRONGLY_RECOMMENDED"

    safe_for_autonomy = False
    if autonomy_score >= 0.8 and not critical_failures and human_override_required in {"OPTIONAL", "NOT_REQUIRED"}:
        safe_for_autonomy = True

    lineage_status = str(lineage_integrity.get("status") or "UNKNOWN").upper()
    edge_status = str(edge_stability.get("status") or "UNKNOWN").upper()
    replay_status = str(replay_validation.get("status") or "UNKNOWN").upper()
    hallucination_status = str(hallucination_risk.get("status") or "UNKNOWN").upper()
    template_status = str(template_risk.get("status") or "UNKNOWN").upper()

    if critical_failures:
        autonomy_status = "NOT_READY"
    elif autonomy_score >= 0.82 and safe_for_autonomy:
        autonomy_status = "LIMITED_AUTONOMY_READY"
    elif (
        autonomy_score >= 0.72
        and lineage_status == "PASS"
        and edge_status == "PASS"
        and replay_status == "PASS"
        and hallucination_status != "FAIL"
        and template_status != "FAIL"
    ):
        autonomy_status = "SUPERVISED_READY"
    elif (
        autonomy_score >= 0.55
        and replay_status == "PASS"
        and hallucination_status != "FAIL"
        and template_status != "FAIL"
    ):
        autonomy_status = "PAPER_ONLY_READY"
    elif lineage_status == "PARTIAL" or edge_status == "PARTIAL" or replay_status != "PASS":
        autonomy_status = "EARLY_EXPERIMENTAL"
    elif autonomy_score >= 0.75 and not safe_for_autonomy:
        autonomy_status = "FULL_AUTONOMY_UNSAFE"
    else:
        autonomy_status = "NOT_READY"

    if human_override_required == "REQUIRED":
        recommended_human_controls.extend(
            [
                "MANUAL_SIGNOFF_BEFORE_ANY_EXECUTION_MODE_CHANGE",
                "BLOCK_AUTONOMOUS_ORDERING",
                "REQUIRE_LINEAGE_AUDIT_PASS",
                "REQUIRE_REPLAY_AND_EDGE_COVERAGE_MINIMUMS",
            ]
        )
    else:
        recommended_human_controls.append("KEEP_PAPER_ONLY_SUPERVISION")

    operational_score = clamp(
        (
            _positive(decision_consistency.get("system_health"))
            + _positive(decision_consistency.get("data_spine_health"))
            + _positive(edge_stability)
        )
        / 3.0
    )
    operational_stability = {
        "status": "PASS" if operational_score >= 0.75 else "PARTIAL" if operational_score >= 0.45 else "FAIL",
        "score": operational_score,
        "critical_failure_count": len(critical_failures),
        "blocker_count": len(autonomy_blockers),
    }
    assert operational_stability["status"] in SAFETY_STATUS
    assert autonomy_status in AUTONOMY_STATUS
    assert human_override_required in HUMAN_OVERRIDE
    assert global_risk_level in RISK_LEVEL

    return {
        "autonomy_status": autonomy_status,
        "autonomy_score": autonomy_score,
        "safe_for_autonomy": safe_for_autonomy,
        "human_override_required": human_override_required,
        "global_risk_level": global_risk_level,
        "critical_failures": critical_failures,
        "autonomy_blockers": autonomy_blockers,
        "autonomy_strengths": autonomy_strengths,
        "safety_constraints": safety_constraints,
        "recommended_human_controls": recommended_human_controls,
        "autonomy_notes": autonomy_notes,
        "operational_stability": operational_stability,
        "brain_governor_summary": {
            "autonomy_status": autonomy_status,
            "largest_risk": global_risk_level,
            "safe_for_autonomy": safe_for_autonomy,
            "primary_blocker": autonomy_blockers[0] if autonomy_blockers else None,
        },
    }
