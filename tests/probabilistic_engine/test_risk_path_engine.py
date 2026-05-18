from __future__ import annotations

from src.probabilistic_engine.risk_path_engine import analyze_risk_paths


def _risk_result() -> dict:
    return analyze_risk_paths(
        market_state={
            "volatility_state": "HIGH",
            "trend_state": "UP",
            "evidence": {
                "liquidity_evidence": {
                    "detected_levels": [
                        {"price": 100.0, "liquidity_type": "untested_high", "strength": "HIGH"}
                    ]
                }
            },
        },
        active_scenario={"active_scenario": "COMPRESSION_BREAKOUT_UP"},
        flow_reaction={"trap_state": "BUYERS_TRAPPED"},
        nova_brain={"risk_map": {"fake_breakout_risk": {"score": 0.42}}},
        future_paths=[
            {"scenario_path": "BULLISH_CONTINUATION_PATH", "estimated_probability": 0.62},
            {"scenario_path": "REVERSAL_PATH", "estimated_probability": 0.3},
            {"scenario_path": "FAKE_BREAKOUT_PATH", "estimated_probability": 0.44},
            {"scenario_path": "LIQUIDITY_SWEEP_PATH", "estimated_probability": 0.36},
        ],
    )


def test_risk_level_is_calculated() -> None:
    result = _risk_result()
    assert any(item["risk_level"] in {"CAUTION", "DANGEROUS", "EXTREME"} for item in result["risk_paths"])

