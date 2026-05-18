from __future__ import annotations

from src.perspective_merger.bias_extractor import extract_perspective_biases


def test_core_bias_is_extracted() -> None:
    result = extract_perspective_biases(
        {
            "trade_decision": {"side": "LONG"},
            "setup_entry": {"setup_direction": "LONG"},
            "active_scenario": {"scenario_bias": "LONG"},
            "probabilistic_engine": {"dominant_path": {"scenario_path": "BULLISH_CONTINUATION_PATH"}},
            "nova_brain": {"dominant_market_story": {"market_bias": "LONG"}},
        }
    )
    assert result["core_bias"] == "LONG"


def test_missing_smc_does_not_crash() -> None:
    result = extract_perspective_biases({"trade_decision": {"side": "LONG"}})
    assert result["smc_bias"] == "UNKNOWN"
    assert "MISSING_SMC_PERSPECTIVE" in result["reason_codes"]


def test_missing_mm_does_not_crash() -> None:
    result = extract_perspective_biases({"trade_decision": {"side": "LONG"}})
    assert result["mm_bias"] == "UNKNOWN"
    assert "MISSING_MM_PERSPECTIVE" in result["reason_codes"]
