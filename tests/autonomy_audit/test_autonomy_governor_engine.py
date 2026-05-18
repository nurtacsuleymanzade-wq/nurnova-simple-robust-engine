from __future__ import annotations

from src.autonomy_audit.autonomy_governor_engine import evaluate_autonomy_governor
from src.autonomy_audit.autonomy_registry import build_autonomy_audit_id


def _sections(
    lineage_status: str,
    lineage_score: float,
    edge_status: str,
    edge_score: float,
    replay_status: str,
    replay_score: float,
    template_score: float,
    hallucination_score: float,
    decision_score: float,
    probabilistic_score: float,
    perspective_score: float,
    system_score: float,
    data_spine_score: float,
    decay_score: float,
) -> dict:
    return {
        "lineage_integrity": {"status": lineage_status, "score": lineage_score},
        "edge_stability": {"status": edge_status, "score": edge_score},
        "replay_validation": {"status": replay_status, "score": replay_score},
        "template_risk": {"status": "PASS" if template_score <= 0.25 else "PARTIAL" if template_score <= 0.55 else "FAIL", "score": template_score},
        "hallucination_risk": {"status": "PASS" if hallucination_score <= 0.25 else "PARTIAL" if hallucination_score <= 0.55 else "FAIL", "score": hallucination_score},
        "decision_consistency": {
            "decision_quality": {"status": "PASS", "score": decision_score},
            "probabilistic_consistency": {"status": "PASS", "score": probabilistic_score},
            "perspective_alignment_consistency": {"status": "PASS", "score": perspective_score},
            "system_health": {"status": "PASS", "score": system_score},
            "data_spine_health": {"status": "PASS", "score": data_spine_score},
        },
        "edge_decay_pressure": {"status": "PASS", "score": decay_score},
    }


def test_autonomy_score_is_calculated() -> None:
    s = _sections("PASS", 0.9, "PASS", 0.8, "PASS", 0.8, 0.1, 0.1, 0.8, 0.8, 0.8, 0.9, 0.9, 0.1)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "ALLOW_PAPER"},
        paper_outcome={"is_closed_outcome": True},
        perspective_merger={"alignment_status": "FULL_ALIGNMENT"},
    )
    assert 0.0 <= result["autonomy_score"] <= 1.0


def test_not_ready_is_created() -> None:
    s = _sections("FAIL", 0.1, "FAIL", 0.1, "FAIL", 0.1, 0.8, 0.8, 0.2, 0.2, 0.2, 0.5, 0.2, 0.7)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "BLOCK"},
        paper_outcome={"is_closed_outcome": False},
        perspective_merger={"alignment_status": "INSUFFICIENT_DATA"},
    )
    assert result["autonomy_status"] == "NOT_READY"


def test_paper_only_ready_is_created() -> None:
    s = _sections("PARTIAL", 0.6, "PARTIAL", 0.55, "PASS", 0.85, 0.2, 0.2, 0.65, 0.6, 0.55, 0.8, 0.75, 0.2)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "ALLOW_PAPER"},
        paper_outcome={"is_closed_outcome": True},
        perspective_merger={"alignment_status": "PARTIAL_ALIGNMENT"},
    )
    assert result["autonomy_status"] == "PAPER_ONLY_READY"


def test_supervised_ready_is_created() -> None:
    s = _sections("PASS", 0.82, "PASS", 0.8, "PASS", 0.85, 0.15, 0.2, 0.85, 0.8, 0.8, 0.85, 0.85, 0.2)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "ALLOW_PAPER"},
        paper_outcome={"is_closed_outcome": True},
        perspective_merger={"alignment_status": "FULL_ALIGNMENT"},
    )
    assert result["autonomy_status"] in {"SUPERVISED_READY", "LIMITED_AUTONOMY_READY"}


def test_hallucination_high_means_not_safe() -> None:
    s = _sections("PASS", 0.8, "PASS", 0.8, "PASS", 0.8, 0.1, 0.8, 0.8, 0.8, 0.8, 0.9, 0.9, 0.1)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "ALLOW_PAPER"},
        paper_outcome={"is_closed_outcome": True},
        perspective_merger={"alignment_status": "FULL_ALIGNMENT"},
    )
    assert result["safe_for_autonomy"] is False


def test_human_override_requirement_is_calculated() -> None:
    s = _sections("FAIL", 0.1, "PASS", 0.8, "PASS", 0.8, 0.1, 0.2, 0.8, 0.8, 0.8, 0.9, 0.9, 0.1)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "ALLOW_PAPER"},
        paper_outcome={"is_closed_outcome": True},
        perspective_merger={"alignment_status": "FULL_ALIGNMENT"},
    )
    assert result["human_override_required"] == "REQUIRED"


def test_critical_failures_are_created() -> None:
    s = _sections("FAIL", 0.1, "FAIL", 0.1, "FAIL", 0.1, 0.8, 0.8, 0.2, 0.2, 0.2, 0.5, 0.2, 0.7)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "BLOCK"},
        paper_outcome={"is_closed_outcome": False},
        perspective_merger={"alignment_status": "INSUFFICIENT_DATA"},
    )
    assert len(result["critical_failures"]) >= 1


def test_autonomy_blockers_are_created() -> None:
    s = _sections("FAIL", 0.1, "PARTIAL", 0.5, "FAIL", 0.1, 0.6, 0.7, 0.3, 0.2, 0.2, 0.6, 0.3, 0.6)
    result = evaluate_autonomy_governor(
        lineage_integrity=s["lineage_integrity"],
        edge_stability=s["edge_stability"],
        replay_validation=s["replay_validation"],
        template_risk=s["template_risk"],
        hallucination_risk=s["hallucination_risk"],
        decision_consistency=s["decision_consistency"],
        edge_decay_pressure=s["edge_decay_pressure"],
        trade_decision={"decision_status": "BLOCK"},
        paper_outcome={"is_closed_outcome": False},
        perspective_merger={"alignment_status": "INSUFFICIENT_DATA"},
    )
    assert len(result["autonomy_blockers"]) >= 1


def test_deterministic_autonomy_audit_id_is_stable() -> None:
    seed = {"autonomy_status": "NOT_READY", "autonomy_score": 0.1}
    assert build_autonomy_audit_id("BTCUSDT", seed) == build_autonomy_audit_id("BTCUSDT", seed)
