from __future__ import annotations

from typing import Any


def build_brain_story(
    *,
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    trade_decision: dict[str, Any] | None,
    system_health: dict[str, Any],
    edge_intelligence: dict[str, Any],
    risk_intelligence: dict[str, Any],
) -> dict[str, Any]:
    market_state = market_state or {}
    active_scenario = active_scenario or {}
    flow_reaction = flow_reaction or {}
    trade_decision = trade_decision or {}

    bias = str(trade_decision.get("side") or active_scenario.get("scenario_bias") or market_state.get("market_regime") or "UNKNOWN").upper()
    scenario = str(active_scenario.get("active_scenario") or "unknown scenario").lower().replace("_", " ")
    flow = str(flow_reaction.get("flow_confirmation") or "unknown flow").lower().replace("_", " ")
    reaction = str(flow_reaction.get("post_liquidity_reaction") or "unknown reaction").lower().replace("_", " ")

    growing_count = len(edge_intelligence.get("growing_edges") or [])
    decaying_count = len(edge_intelligence.get("decaying_edges") or [])
    dead_count = len(edge_intelligence.get("dead_edges") or [])

    primary_story = f"{scenario} under {flow} flow with {reaction} reaction; bias={bias.lower()}"
    if growing_count > decaying_count and growing_count > 0:
        primary_story = f"{primary_story}; edge clusters are strengthening"
    elif decaying_count > 0:
        primary_story = f"{primary_story}; expectancy pressure is weakening"

    secondary_story = None
    if dead_count > 0:
        secondary_story = f"{dead_count} edge clusters are effectively dead"
    elif risk_intelligence["fake_scenario_pressure"]["pressure_level"] in {"DANGEROUS", "EXTREME"}:
        secondary_story = "fake breakout pressure is dominating current scenarios"

    operational_alerts: list[str] = []
    if system_health.get("status") in {"DEGRADED", "CRITICAL"}:
        operational_alerts.append(f"SYSTEM_HEALTH_{system_health.get('status')}")
    if risk_intelligence["risk_map"]["global_risk_level"] in {"HIGH", "EXTREME"}:
        operational_alerts.append(f"GLOBAL_RISK_{risk_intelligence['risk_map']['global_risk_level']}")
    if risk_intelligence["decision_quality_overview"]["status"] in {"WEAKENING", "POOR"}:
        operational_alerts.append(f"DECISION_QUALITY_{risk_intelligence['decision_quality_overview']['status']}")
    if edge_intelligence.get("fake_edge_density", 0.0) >= 0.4:
        operational_alerts.append("FAKE_EDGE_DENSITY_HIGH")
    if not operational_alerts:
        operational_alerts.append("NO_CRITICAL_OPERATIONAL_ALERT")

    brain_summary = [
        f"System health is {system_health.get('status')}.",
        f"Global risk is {risk_intelligence['risk_map']['global_risk_level']}.",
        f"Growing edges={growing_count}, decaying edges={decaying_count}, dead edges={dead_count}.",
        f"Decision quality overview is {risk_intelligence['decision_quality_overview']['status']}.",
    ]
    if secondary_story:
        brain_summary.append(secondary_story)

    return {
        "operational_alerts": operational_alerts,
        "dominant_market_story": {
            "primary_story": primary_story,
            "secondary_story": secondary_story,
            "market_bias": bias,
        },
        "brain_summary": brain_summary,
    }
