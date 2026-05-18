from __future__ import annotations

from typing import Any

from .autonomy_registry import SAFETY_STATUS, clamp, safety_status_from_risk_score


def evaluate_hallucination_risk(
    *,
    trade_decision: dict[str, Any] | None,
    paper_outcome: dict[str, Any] | None,
    edge_matrix: dict[str, Any] | None,
    replay_engine: dict[str, Any] | None,
    nova_brain: dict[str, Any] | None,
    probabilistic_engine: dict[str, Any] | None,
    perspective_merger: dict[str, Any] | None,
) -> dict[str, Any]:
    trade_decision = trade_decision or {}
    paper_outcome = paper_outcome or {}
    edge_matrix = edge_matrix or {}
    replay_engine = replay_engine or {}
    nova_brain = nova_brain or {}
    probabilistic_engine = probabilistic_engine or {}
    perspective_merger = perspective_merger or {}

    if not any([trade_decision, paper_outcome, edge_matrix, replay_engine, nova_brain, probabilistic_engine, perspective_merger]):
        return {"status": "UNKNOWN", "score": None, "reason_codes": ["UNKNOWN_AUTONOMY_STATE"]}

    eligible = int(edge_matrix.get("edge_eligible_outcome_count") or 0)
    outcome_edge_claim = int(edge_matrix.get("source_outcome_count") or 0) > 0 and eligible == 0
    strong_prob_without_edge = (
        float(((probabilistic_engine.get("dominant_path") or {}).get("estimated_probability") or 0.0)) >= 0.6
        and eligible == 0
    )
    brain_strong_story_without_validation = (
        str(((nova_brain.get("dominant_market_story") or {}).get("market_bias") or "UNKNOWN")).upper() in {"LONG", "SHORT"}
        and str((nova_brain.get("decision_quality_overview") or {}).get("status") or "UNKNOWN").upper() == "UNKNOWN"
    )
    replay_contradiction = str(replay_engine.get("replay_status") or "UNKNOWN").upper() == "REPLAY_SUCCESS" and str(replay_engine.get("decision_quality") or "").upper() in {"POOR", "TERRIBLE"}
    fake_scenario_pressure = float(((probabilistic_engine.get("fake_breakout_probabilities") or {}).get("probability") or 0.0))
    missing_perspectives = "MISSING_PERSPECTIVE" in {str(code).upper() for code in (perspective_merger.get("reason_codes") or [])}
    decision_zero_conf = float(trade_decision.get("decision_confidence") or 0.0) == 0.0
    confidence_gap = decision_zero_conf and brain_strong_story_without_validation

    risk_score = 0.0
    if outcome_edge_claim:
        risk_score += 0.25
    if strong_prob_without_edge:
        risk_score += 0.3
    if brain_strong_story_without_validation:
        risk_score += 0.15
    if replay_contradiction:
        risk_score += 0.15
    if missing_perspectives:
        risk_score += 0.05
    if confidence_gap:
        risk_score += 0.1
    risk_score += min(0.2, fake_scenario_pressure * 0.2)
    risk_score = clamp(risk_score)
    status = safety_status_from_risk_score(risk_score)

    assert status in SAFETY_STATUS
    return {
        "status": status,
        "score": risk_score,
        "edge_claim_without_closed_truth": outcome_edge_claim,
        "probabilistic_edge_contradiction": strong_prob_without_edge,
        "strong_story_without_validation": brain_strong_story_without_validation,
        "replay_contradiction": replay_contradiction,
        "fake_scenario_density": fake_scenario_pressure,
        "reason_codes": [
            "EDGE_WITHOUT_CLOSED_OUTCOME" if outcome_edge_claim else "EDGE_TRUTH_LINK_OK_OR_NO_EDGE",
            "PROBABILITY_WITHOUT_EDGE_SUPPORT" if strong_prob_without_edge else "PROBABILITY_EDGE_RELATION_OK_OR_WEAK",
        ],
    }
