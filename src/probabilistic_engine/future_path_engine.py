from __future__ import annotations

from typing import Any

from .scenario_registry import PROBABILITY_BANDS, RISK_PATH_LEVELS, SCENARIO_PATHS, build_path_id, probability_band, risk_level


def _clamp(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def _cluster_probability(clusters: list[dict[str, Any]], cluster_type: str) -> float:
    for cluster in clusters:
        if str(cluster.get("cluster_type") or "") == cluster_type:
            try:
                return float(cluster.get("estimated_probability") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _map_active_scenario_to_path(active_scenario: str) -> str:
    scenario = str(active_scenario or "").upper()
    if "RANGE_ROTATION" in scenario:
        return "RANGE_ROTATION_PATH"
    if scenario == "COMPRESSION_BREAKOUT_UP":
        return "COMPRESSION_BREAKOUT_UP_PATH"
    if scenario == "COMPRESSION_BREAKOUT_DOWN":
        return "COMPRESSION_BREAKOUT_DOWN_PATH"
    if "BULLISH_CONTINUATION" in scenario:
        return "BULLISH_CONTINUATION_PATH"
    if "BEARISH_CONTINUATION" in scenario:
        return "BEARISH_CONTINUATION_PATH"
    if "REVERSAL" in scenario:
        return "REVERSAL_PATH"
    if "LIQUIDITY" in scenario or "SWEEP" in scenario:
        return "LIQUIDITY_SWEEP_PATH"
    return "UNKNOWN_PATH"


def _expected_behavior(path: str, bias: str) -> str:
    mapping = {
        "BULLISH_CONTINUATION_PATH": "trend continuation holds with buyers preserving control",
        "BEARISH_CONTINUATION_PATH": "downtrend continuation holds with sellers preserving control",
        "RANGE_ROTATION_PATH": "range rotation seeks the opposite side of balance",
        "COMPRESSION_BREAKOUT_UP_PATH": "compression resolves upward if liquidity lifts cleanly",
        "COMPRESSION_BREAKOUT_DOWN_PATH": "compression resolves downward if liquidity breaks cleanly",
        "FAKE_BREAKOUT_PATH": "breakout attempt fades and returns into prior range",
        "LIQUIDITY_SWEEP_PATH": "liquidity sweep occurs before reclaim or rejection response",
        "MEAN_REVERSION_PATH": "price rotates back toward value after imbalance fails",
        "TREND_EXHAUSTION_PATH": "trend stalls and loses follow-through",
        "REVERSAL_PATH": "current directional pressure flips into a reversal regime",
        "HIGH_VOLATILITY_PATH": "wide unstable movement with elevated failure risk",
        "LOW_VOLATILITY_PATH": "contained movement with slower path development",
        "UNKNOWN_PATH": f"path remains unresolved for {bias or 'unknown'} bias",
    }
    return mapping.get(path, "path behavior unresolved")


def trade_side(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("dominant_market_story"), dict):
        return payload["dominant_market_story"].get("market_bias")
    return payload.get("side")


def build_future_paths(
    *,
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    edge_matrix: dict[str, Any] | None,
    replay_engine: dict[str, Any] | None,
    nova_brain: dict[str, Any] | None,
    probability_clusters: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    market_state = market_state or {}
    active_scenario = active_scenario or {}
    flow_reaction = flow_reaction or {}
    edge_matrix = edge_matrix or {}
    replay_engine = replay_engine or {}
    nova_brain = nova_brain or {}

    scenario = str(active_scenario.get("active_scenario") or "")
    bias = str(active_scenario.get("scenario_bias") or trade_side(replay_engine) or trade_side(nova_brain) or "UNKNOWN").upper()
    dominant_scenario_path = _map_active_scenario_to_path(scenario)
    volatility_state = str(market_state.get("volatility_state") or "UNKNOWN").upper()
    global_risk_level = str((nova_brain.get("risk_map") or {}).get("global_risk_level") or "UNKNOWN").upper()
    top_positive_edges = len(edge_matrix.get("top_positive_edges") or [])

    continuation_cluster = _cluster_probability(probability_clusters, "CONTINUATION_CLUSTER")
    reversal_cluster = _cluster_probability(probability_clusters, "REVERSAL_CLUSTER")
    fake_breakout_cluster = _cluster_probability(probability_clusters, "FAKE_BREAKOUT_CLUSTER")
    liquidity_sweep_cluster = _cluster_probability(probability_clusters, "LIQUIDITY_SWEEP_CLUSTER")

    continuation_survival = _clamp(continuation_cluster + min(0.15, top_positive_edges * 0.03) - (0.1 if str(flow_reaction.get("flow_confirmation") or "").upper() == "NOT_CONFIRMED" else 0.0))
    fake_breakout_probability = _clamp(fake_breakout_cluster + (0.1 if global_risk_level in {"HIGH", "EXTREME"} else 0.0))
    liquidity_probability = _clamp(liquidity_sweep_cluster + (0.05 if volatility_state == "HIGH" else 0.0))
    reversal_probability = _clamp(reversal_cluster + (0.05 if scenario.upper().startswith("RANGE_ROTATION") else 0.0))

    path_specs = {
        dominant_scenario_path: max(
            0.2,
            float(active_scenario.get("scenario_confidence") or 0.0),
            continuation_survival if dominant_scenario_path in {"BULLISH_CONTINUATION_PATH", "BEARISH_CONTINUATION_PATH"} else 0.0,
            reversal_probability if dominant_scenario_path in {"RANGE_ROTATION_PATH", "REVERSAL_PATH", "MEAN_REVERSION_PATH"} else 0.0,
            fake_breakout_probability if dominant_scenario_path == "FAKE_BREAKOUT_PATH" else 0.0,
            liquidity_probability if dominant_scenario_path == "LIQUIDITY_SWEEP_PATH" else 0.0,
        ),
        "BULLISH_CONTINUATION_PATH" if bias == "LONG" else "BEARISH_CONTINUATION_PATH": continuation_survival,
        "REVERSAL_PATH": reversal_probability,
        "FAKE_BREAKOUT_PATH": fake_breakout_probability,
        "LIQUIDITY_SWEEP_PATH": liquidity_probability,
        "HIGH_VOLATILITY_PATH" if volatility_state == "HIGH" else "LOW_VOLATILITY_PATH": _clamp(0.55 if volatility_state == "HIGH" else 0.35),
    }

    future_paths: list[dict[str, Any]] = []
    for path_name, probability in path_specs.items():
        risk_score = _clamp(max(fake_breakout_probability, 0.25 if path_name == "HIGH_VOLATILITY_PATH" else 0.0, 0.15 if "REVERSAL" in path_name else 0.0))
        row = {
            "path_id": build_path_id(
                path_name,
                {
                    "scenario": scenario,
                    "bias": bias,
                    "probability": round(probability, 4),
                    "volatility_state": volatility_state,
                },
            ),
            "scenario_path": path_name,
            "probability_band": probability_band(probability),
            "estimated_probability": round(probability, 4),
            "continuation_survival_probability": round(continuation_survival, 4),
            "fake_breakout_probability": round(fake_breakout_probability, 4),
            "risk_level": risk_level(risk_score),
            "expected_behavior": _expected_behavior(path_name, bias),
            "reason_codes": [],
        }
        if path_name == dominant_scenario_path:
            row["reason_codes"].append("DOMINANT_SCENARIO_ALIGNED")
        if path_name == "FAKE_BREAKOUT_PATH" and fake_breakout_probability > 0.3:
            row["reason_codes"].append("FAKE_BREAKOUT_RISK_ELEVATED")
        if path_name == "LIQUIDITY_SWEEP_PATH" and liquidity_probability > 0.2:
            row["reason_codes"].append("LIQUIDITY_ATTRACTION_ACTIVE")
        assert row["scenario_path"] in SCENARIO_PATHS
        assert row["probability_band"] in PROBABILITY_BANDS
        assert row["risk_level"] in RISK_PATH_LEVELS
        future_paths.append(row)

    future_paths.sort(key=lambda item: (float(item.get("estimated_probability") or 0.0), item["scenario_path"]), reverse=True)
    dominant_path = future_paths[0] if future_paths else {
        "scenario_path": "UNKNOWN_PATH",
        "probability_band": "UNKNOWN",
        "estimated_probability": None,
    }
    return future_paths, dominant_path
