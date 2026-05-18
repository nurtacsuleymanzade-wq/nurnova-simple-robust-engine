from __future__ import annotations

from src.probabilistic_engine.probabilistic_validator import validate_probabilistic_payload


def _valid_payload() -> dict:
    return {
        "timestamp_utc": "2026-05-18T08:00:00Z",
        "block_id": "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
        "symbol": "BTCUSDT",
        "scenario_engine_id": "PRB_1",
        "lineage_id": "LIN_1",
        "future_paths": [
            {
                "path_id": "PTH_1",
                "scenario_path": "BULLISH_CONTINUATION_PATH",
                "probability_band": "HIGH",
                "estimated_probability": 0.7,
                "continuation_survival_probability": 0.65,
                "fake_breakout_probability": 0.2,
                "risk_level": "CAUTION",
                "expected_behavior": "continuation",
                "reason_codes": [],
            }
        ],
        "probability_clusters": [],
        "scenario_tree": {},
        "market_path_forecast": {},
        "risk_paths": [],
        "survival_probabilities": {},
        "fake_breakout_probabilities": {},
        "continuation_probabilities": {},
        "liquidity_attraction_zones": [],
        "dominant_path": {},
        "scenario_pressure_map": {},
        "market_story_projection": {},
        "data_quality": "OK",
        "reason_codes": [],
        "feeds_next": [
            "PHASE_12_META_LEARNING_LAYER",
            "PHASE_13_ADAPTIVE_INTELLIGENCE",
        ],
        "warnings": [],
    }


def test_invalid_enum_is_caught() -> None:
    payload = _valid_payload()
    payload["future_paths"][0]["scenario_path"] = "BAD_PATH"
    result = validate_probabilistic_payload(payload)
    assert "INVALID_SCENARIO_PATH_ENUM" in result["errors"]


def test_output_required_fields_pass() -> None:
    result = validate_probabilistic_payload(_valid_payload())
    assert result["is_valid"] is True


def test_feeds_next_is_correct() -> None:
    assert _valid_payload()["feeds_next"] == [
        "PHASE_12_META_LEARNING_LAYER",
        "PHASE_13_ADAPTIVE_INTELLIGENCE",
    ]
