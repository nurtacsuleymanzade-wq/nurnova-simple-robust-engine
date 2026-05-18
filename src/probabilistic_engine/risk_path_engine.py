from __future__ import annotations

from typing import Any

from .scenario_registry import RISK_PATH_LEVELS, SCENARIO_PRESSURE, pressure_level, risk_level


def _clamp(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def _find_probability(future_paths: list[dict[str, Any]], scenario_path: str) -> float:
    for item in future_paths:
        if str(item.get("scenario_path") or "") == scenario_path:
            try:
                return float(item.get("estimated_probability") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def analyze_risk_paths(
    *,
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    nova_brain: dict[str, Any] | None,
    future_paths: list[dict[str, Any]],
) -> dict[str, Any]:
    market_state = market_state or {}
    active_scenario = active_scenario or {}
    flow_reaction = flow_reaction or {}
    nova_brain = nova_brain or {}

    fake_breakout_probability = _find_probability(future_paths, "FAKE_BREAKOUT_PATH")
    liquidity_sweep_probability = _find_probability(future_paths, "LIQUIDITY_SWEEP_PATH")
    continuation_probability = max(
        _find_probability(future_paths, "BULLISH_CONTINUATION_PATH"),
        _find_probability(future_paths, "BEARISH_CONTINUATION_PATH"),
    )
    reversal_probability = _find_probability(future_paths, "REVERSAL_PATH")

    volatility_state = str(market_state.get("volatility_state") or "UNKNOWN").upper()
    trend_state = str(market_state.get("trend_state") or "UNKNOWN").upper()
    trap_state = str(flow_reaction.get("trap_state") or "").upper()
    pressure_input = float(((nova_brain.get("risk_map") or {}).get("fake_breakout_risk") or {}).get("score") or 0.0)

    trend_exhaustion_score = _clamp(reversal_probability + (0.15 if trend_state in {"UP", "DOWN", "BULLISH", "BEARISH"} else 0.05))
    volatility_collapse_score = _clamp((0.35 if volatility_state == "HIGH" else 0.1) + pressure_input)
    liquidity_trap_score = _clamp(liquidity_sweep_probability + (0.2 if trap_state not in {"", "NONE", "UNKNOWN"} else 0.05))
    fake_breakout_score = _clamp(max(fake_breakout_probability, pressure_input))

    risk_paths = [
        {
            "risk_type": "FAKE_BREAKOUT_RISK",
            "score": fake_breakout_score,
            "risk_level": risk_level(fake_breakout_score),
            "reason_codes": ["FAKE_BREAKOUT_PROBABILITY_TRACKED"],
        },
        {
            "risk_type": "TREND_EXHAUSTION_RISK",
            "score": trend_exhaustion_score,
            "risk_level": risk_level(trend_exhaustion_score),
            "reason_codes": ["REVERSAL_PATH_PRESSURE_TRACKED"],
        },
        {
            "risk_type": "VOLATILITY_COLLAPSE_RISK",
            "score": volatility_collapse_score,
            "risk_level": risk_level(volatility_collapse_score),
            "reason_codes": ["VOLATILITY_STATE_TRACKED"],
        },
        {
            "risk_type": "LIQUIDITY_TRAP_RISK",
            "score": liquidity_trap_score,
            "risk_level": risk_level(liquidity_trap_score),
            "reason_codes": ["LIQUIDITY_SWEEP_PRESSURE_TRACKED"],
        },
    ]
    for item in risk_paths:
        assert item["risk_level"] in RISK_PATH_LEVELS

    overall_pressure_score = _clamp(max(item["score"] for item in risk_paths)) if risk_paths else 0.0
    scenario_pressure_map = {
        "pressure_level": pressure_level(overall_pressure_score),
        "pressure_score": overall_pressure_score,
        "fake_breakout_score": fake_breakout_score,
        "trend_exhaustion_score": trend_exhaustion_score,
        "volatility_collapse_score": volatility_collapse_score,
        "liquidity_trap_score": liquidity_trap_score,
        "active_scenario": active_scenario.get("active_scenario"),
    }
    assert scenario_pressure_map["pressure_level"] in SCENARIO_PRESSURE

    liquidity_evidence = ((market_state.get("evidence") or {}).get("liquidity_evidence") or {})
    detected_levels = liquidity_evidence.get("detected_levels") or []
    liquidity_attraction_zones = []
    for item in detected_levels[:3]:
        liquidity_attraction_zones.append(
            {
                "price": item.get("price"),
                "liquidity_type": item.get("liquidity_type"),
                "strength": item.get("strength"),
            }
        )

    return {
        "risk_paths": risk_paths,
        "scenario_pressure_map": scenario_pressure_map,
        "survival_probabilities": {
            "continuation": round(continuation_probability, 4),
            "reversal": round(reversal_probability, 4),
        },
        "fake_breakout_probabilities": {
            "active_scenario": active_scenario.get("active_scenario"),
            "probability": round(fake_breakout_probability, 4),
        },
        "continuation_probabilities": {
            "primary": round(continuation_probability, 4),
        },
        "liquidity_attraction_zones": liquidity_attraction_zones,
    }
