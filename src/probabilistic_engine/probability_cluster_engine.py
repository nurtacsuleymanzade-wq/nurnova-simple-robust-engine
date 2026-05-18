from __future__ import annotations

from typing import Any

from .scenario_registry import PROBABILITY_BANDS, probability_band


def _clamp(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def _score_continuation(
    market_state: dict[str, Any],
    active_scenario: dict[str, Any],
    flow_reaction: dict[str, Any],
    edge_matrix: dict[str, Any],
) -> float:
    scenario = str(active_scenario.get("active_scenario") or "").upper()
    bias = str(active_scenario.get("scenario_bias") or "").upper()
    trend = str(market_state.get("trend_state") or "").upper()
    flow_confirmation = str(flow_reaction.get("flow_confirmation") or "").upper()
    score = 0.1
    if "CONTINUATION" in scenario:
        score += 0.35
    if scenario in {"COMPRESSION_BREAKOUT_UP", "COMPRESSION_BREAKOUT_DOWN"}:
        score += 0.2
    if bias == "LONG" and trend in {"UP", "BULLISH", "LONG"}:
        score += 0.15
    if bias == "SHORT" and trend in {"DOWN", "BEARISH", "SHORT"}:
        score += 0.15
    if flow_confirmation == "CONFIRMED":
        score += 0.2
    elif flow_confirmation == "NOT_CONFIRMED":
        score -= 0.05
    positive_edges = len(edge_matrix.get("top_positive_edges") or [])
    score += min(0.15, positive_edges * 0.03)
    return _clamp(score)


def _score_reversal(
    market_state: dict[str, Any],
    active_scenario: dict[str, Any],
    replay_engine: dict[str, Any],
) -> float:
    scenario = str(active_scenario.get("active_scenario") or "").upper()
    market_regime = str(market_state.get("market_regime") or "").upper()
    learning_signals = {str(item).upper() for item in replay_engine.get("learning_signals") or []}
    score = 0.08
    if "REVERSAL" in scenario or "RANGE_ROTATION" in scenario:
        score += 0.35
    if market_regime in {"RANGE", "RANGING", "BALANCE", "UNKNOWN"}:
        score += 0.15
    if "NO_TRADE_WOULD_HAVE_BEEN_BETTER" in learning_signals:
        score += 0.15
    if str(replay_engine.get("decision_quality") or "").upper() in {"POOR", "TERRIBLE"}:
        score += 0.1
    return _clamp(score)


def _score_fake_breakout(
    active_scenario: dict[str, Any],
    flow_reaction: dict[str, Any],
    nova_brain: dict[str, Any],
) -> float:
    scenario = str(active_scenario.get("active_scenario") or "").upper()
    flow_confirmation = str(flow_reaction.get("flow_confirmation") or "").upper()
    liquidity_reaction = str(flow_reaction.get("post_liquidity_reaction") or "").upper()
    pressure = str((nova_brain.get("fake_scenario_pressure") or {}).get("pressure_level") or "").upper()
    score = 0.05
    if "BREAKOUT" in scenario or "COMPRESSION" in scenario:
        score += 0.25
    if flow_confirmation == "NOT_CONFIRMED":
        score += 0.2
    if any(token in liquidity_reaction for token in ("FAILED", "REJECTION", "NO_LIQUIDITY_EVENT")):
        score += 0.2
    if pressure in {"ELEVATED", "DANGEROUS", "EXTREME"}:
        score += 0.15
    return _clamp(score)


def _score_liquidity_sweep(
    market_state: dict[str, Any],
    flow_reaction: dict[str, Any],
    active_scenario: dict[str, Any],
) -> float:
    scenario = str(active_scenario.get("active_scenario") or "").upper()
    trap_state = str(flow_reaction.get("trap_state") or "").upper()
    absorption_state = str(flow_reaction.get("absorption_state") or "").upper()
    liquidity = str(market_state.get("liquidity_pressure_state") or "").upper()
    score = 0.05
    if "LIQUIDITY" in scenario or "SWEEP" in scenario:
        score += 0.3
    if trap_state not in {"", "NONE", "UNKNOWN"}:
        score += 0.2
    if absorption_state not in {"", "NONE", "UNKNOWN"}:
        score += 0.15
    if liquidity in {"BOTH", "UP", "DOWN"}:
        score += 0.1
    return _clamp(score)


def build_probability_clusters(
    *,
    edge_matrix: dict[str, Any] | None,
    replay_engine: dict[str, Any] | None,
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    nova_brain: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    edge_matrix = edge_matrix or {}
    replay_engine = replay_engine or {}
    market_state = market_state or {}
    active_scenario = active_scenario or {}
    flow_reaction = flow_reaction or {}
    nova_brain = nova_brain or {}

    if not any([edge_matrix, replay_engine, market_state, active_scenario, flow_reaction, nova_brain]):
        return [
            {
                "cluster_type": "UNKNOWN_CLUSTER",
                "probability_band": "UNKNOWN",
                "estimated_probability": None,
                "supporting_signals": [],
                "reason_codes": ["UNKNOWN_PROBABILITY_STATE"],
            }
        ]

    cluster_rows = [
        {
            "cluster_type": "CONTINUATION_CLUSTER",
            "estimated_probability": _score_continuation(market_state, active_scenario, flow_reaction, edge_matrix),
            "supporting_signals": [
                active_scenario.get("active_scenario"),
                market_state.get("trend_state"),
                flow_reaction.get("flow_confirmation"),
            ],
            "reason_codes": [],
        },
        {
            "cluster_type": "REVERSAL_CLUSTER",
            "estimated_probability": _score_reversal(market_state, active_scenario, replay_engine),
            "supporting_signals": [
                active_scenario.get("active_scenario"),
                market_state.get("market_regime"),
                replay_engine.get("decision_quality"),
            ],
            "reason_codes": [],
        },
        {
            "cluster_type": "FAKE_BREAKOUT_CLUSTER",
            "estimated_probability": _score_fake_breakout(active_scenario, flow_reaction, nova_brain),
            "supporting_signals": [
                active_scenario.get("active_scenario"),
                flow_reaction.get("flow_confirmation"),
                flow_reaction.get("post_liquidity_reaction"),
            ],
            "reason_codes": [],
        },
        {
            "cluster_type": "LIQUIDITY_SWEEP_CLUSTER",
            "estimated_probability": _score_liquidity_sweep(market_state, flow_reaction, active_scenario),
            "supporting_signals": [
                active_scenario.get("active_scenario"),
                flow_reaction.get("trap_state"),
                flow_reaction.get("absorption_state"),
            ],
            "reason_codes": [],
        },
    ]

    for row in cluster_rows:
        row["probability_band"] = probability_band(row["estimated_probability"])
        assert row["probability_band"] in PROBABILITY_BANDS
        row["supporting_signals"] = [item for item in row["supporting_signals"] if item not in (None, "")]
        if row["estimated_probability"] == 0:
            row["reason_codes"].append("NO_SUPPORTING_EVIDENCE")
    return cluster_rows
