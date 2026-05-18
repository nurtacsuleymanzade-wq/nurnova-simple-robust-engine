from __future__ import annotations

from typing import Any

from .brain_registry import DECISION_QUALITY_OVERVIEW, RISK_LEVEL, SCENARIO_PRESSURE


def _risk_label(score: float) -> str:
    if score >= 0.85:
        return "EXTREME"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"


def _pressure_label(score: float) -> str:
    if score >= 0.85:
        return "EXTREME"
    if score >= 0.6:
        return "DANGEROUS"
    if score >= 0.3:
        return "ELEVATED"
    return "NORMAL"


def analyze_risk_intelligence(
    *,
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    trade_decision: dict[str, Any] | None,
    paper_outcome: dict[str, Any] | None,
    edge_matrix: dict[str, Any] | None,
    replay_engine: dict[str, Any] | None,
    edge_intelligence: dict[str, Any] | None,
) -> dict[str, Any]:
    market_state = market_state or {}
    active_scenario = active_scenario or {}
    flow_reaction = flow_reaction or {}
    trade_decision = trade_decision or {}
    paper_outcome = paper_outcome or {}
    edge_matrix = edge_matrix or {}
    replay_engine = replay_engine or {}
    edge_intelligence = edge_intelligence or {}

    scenario_text = " ".join(
        [
            str(active_scenario.get("active_scenario") or ""),
            str(flow_reaction.get("post_liquidity_reaction") or ""),
            str(flow_reaction.get("trap_state") or ""),
            str(flow_reaction.get("flow_confirmation") or ""),
        ]
    ).upper()
    fake_breakout_score = 0.0
    if "BREAKOUT" in scenario_text:
        fake_breakout_score += 0.35
    if any(token in scenario_text for token in ("FAILED", "TRAP", "REJECTION", "NOT_CONFIRMED")):
        fake_breakout_score += 0.35
    if str(paper_outcome.get("trade_fate") or "").upper() in {"SL_HIT", "INVALIDATED_AFTER_ENTRY"}:
        fake_breakout_score += 0.15
    if "NO_TRADE_WOULD_HAVE_BEEN_BETTER" in (replay_engine.get("learning_signals") or []):
        fake_breakout_score += 0.15
    fake_breakout_score = round(min(fake_breakout_score, 1.0), 4)

    regime_score = 0.0
    if str(market_state.get("volatility_state") or "").upper() in {"HIGH", "EXTREME"}:
        regime_score += 0.3
    if str(market_state.get("market_regime") or "").upper() in {"UNKNOWN", "CHOPPY", "RANGING"}:
        regime_score += 0.25
    if str(trade_decision.get("risk_grade") or "").upper() == "HIGH":
        regime_score += 0.15
    if str(replay_engine.get("decision_quality") or "").upper() in {"POOR", "TERRIBLE"}:
        regime_score += 0.2
    regime_score = round(min(regime_score, 1.0), 4)

    data_degradation_score = 0.0
    if str(edge_matrix.get("data_quality") or "").upper() in {"DEGRADED", "INVALID"}:
        data_degradation_score += 0.4
    if str(replay_engine.get("data_quality") or "").upper() in {"DEGRADED", "INVALID", "UNKNOWN"}:
        data_degradation_score += 0.2
    if str(paper_outcome.get("data_quality") or "").upper() in {"DEGRADED", "INVALID"}:
        data_degradation_score += 0.2
    data_degradation_score += min(0.2, float(edge_intelligence.get("fake_edge_density") or 0.0))
    data_degradation_score = round(min(data_degradation_score, 1.0), 4)

    global_score = round(max(fake_breakout_score, regime_score, data_degradation_score), 4)
    global_risk_level = _risk_label(global_score)
    assert global_risk_level in RISK_LEVEL

    pressure_score = round(min(1.0, fake_breakout_score + max(0.0, (edge_intelligence.get("fake_edge_density") or 0.0) - 0.2)), 4)
    pressure_level = _pressure_label(pressure_score)
    assert pressure_level in SCENARIO_PRESSURE

    dq_score = replay_engine.get("decision_quality_score")
    if dq_score is None:
        overview_status = "UNKNOWN"
    else:
        dq_score = float(dq_score)
        if dq_score >= 0.8:
            overview_status = "STRONG"
        elif dq_score >= 0.55:
            overview_status = "STABLE"
        elif dq_score >= 0.35:
            overview_status = "WEAKENING"
        else:
            overview_status = "POOR"
    assert overview_status in DECISION_QUALITY_OVERVIEW

    learning_signals = list(replay_engine.get("learning_signals") or [])
    bad_decision_clusters = []
    if overview_status in {"WEAKENING", "POOR"}:
        bad_decision_clusters.append(
            {
                "decision_id": trade_decision.get("decision_id"),
                "risk_grade": trade_decision.get("risk_grade"),
                "learning_signals": learning_signals,
            }
        )

    top_fake_scenarios = []
    if fake_breakout_score > 0:
        top_fake_scenarios.append(
            {
                "active_scenario": active_scenario.get("active_scenario"),
                "flow_confirmation": flow_reaction.get("flow_confirmation"),
                "post_liquidity_reaction": flow_reaction.get("post_liquidity_reaction"),
                "risk_score": fake_breakout_score,
            }
        )

    return {
        "risk_map": {
            "global_risk_level": global_risk_level,
            "regime_risk": {
                "score": regime_score,
                "level": _risk_label(regime_score),
                "market_regime": market_state.get("market_regime"),
                "volatility_state": market_state.get("volatility_state"),
            },
            "fake_breakout_risk": {
                "score": fake_breakout_score,
                "level": _risk_label(fake_breakout_score),
                "scenario": active_scenario.get("active_scenario"),
            },
            "data_degradation_risk": {
                "score": data_degradation_score,
                "level": _risk_label(data_degradation_score),
            },
        },
        "fake_scenario_pressure": {
            "pressure_level": pressure_level,
            "top_fake_scenarios": top_fake_scenarios,
        },
        "regime_risk": {
            "market_regime": market_state.get("market_regime"),
            "trend_state": market_state.get("trend_state"),
            "volatility_state": market_state.get("volatility_state"),
            "risk_level": _risk_label(regime_score),
        },
        "setup_survival": {
            "surviving_edges": len(edge_intelligence.get("growing_edges") or []) + len(edge_intelligence.get("stable_edges") or []),
            "dead_edges": len(edge_intelligence.get("dead_edges") or []),
            "decaying_edges": len(edge_intelligence.get("decaying_edges") or []),
        },
        "decision_quality_overview": {
            "status": overview_status,
            "decision_quality_score": dq_score,
            "bad_decision_clusters": bad_decision_clusters,
        },
        "replay_learning_summary": {
            "replay_status": replay_engine.get("replay_status"),
            "learning_signals": learning_signals,
            "best_alternative_outcome": replay_engine.get("best_alternative_outcome"),
            "worst_alternative_outcome": replay_engine.get("worst_alternative_outcome"),
        },
    }
