"""Tests for S5 Liquidity + Structure Context Engine."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.liquidity_structure_engine import (
    build_liquidity_structure,
    run_fake_sample,
    _FAKE_S1,
    _FAKE_S3,
    _FAKE_S4,
    FEEDS_NEXT,
)
import src.simple.run_s5_liquidity_structure as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "input_status", "range_context", "structure",
    "liquidity_levels", "liquidity_bias", "simple_context",
    "quality_context", "nearest_support", "nearest_resistance",
    "liquidity_notes", "data_quality", "reason_codes", "feeds_next",
]

_VALID_PRICE_ZONES = {
    "ABOVE_RANGE", "UPPER_RANGE", "MID_RANGE", "LOWER_RANGE", "BELOW_RANGE", "UNKNOWN",
}

_VALID_STRUCTURE_BIAS = {"BULLISH", "BEARISH", "RANGE", "UNKNOWN"}

_VALID_DRAW = {"ABOVE", "BELOW", "BOTH", "NONE", "UNKNOWN"}

_REQUIRED_INPUT_STATUS = [
    "market_truth_available", "hybrid_candle_available",
    "quality_weight_available", "missing_inputs",
]

_REQUIRED_RANGE_CTX = [
    "current_price", "range_high", "range_low", "range_mid", "price_zone",
]

_REQUIRED_STRUCTURE = ["structure_bias", "structure_event", "structure_score"]

_REQUIRED_LIQ_LEVEL = ["price", "distance_abs", "distance_pct", "liquidity_type"]

_REQUIRED_LIQ_BIAS = ["draw_on_liquidity", "liquidity_context_label", "liquidity_score"]

_REQUIRED_CTX = ["context_label", "context_score", "usable_for_setup_candidate"]

_REQUIRED_QUALITY_CTX = [
    "inherited_quality_weight", "quality_label", "quality_adjusted_context_score",
]


def test_fake_sample_contract_fields():
    ls = run_fake_sample("BTCUSDT")
    for field in _REQUIRED_TOP:
        assert field in ls, f"Missing top-level field: {field}"
    assert ls["block_id"] == "S5_LIQUIDITY_STRUCTURE_CONTEXT"
    assert ls["symbol"] == "BTCUSDT"
    for field in _REQUIRED_INPUT_STATUS:
        assert field in ls["input_status"], f"input_status missing: {field}"
    for field in _REQUIRED_RANGE_CTX:
        assert field in ls["range_context"], f"range_context missing: {field}"
    for field in _REQUIRED_STRUCTURE:
        assert field in ls["structure"], f"structure missing: {field}"
    for field in _REQUIRED_LIQ_BIAS:
        assert field in ls["liquidity_bias"], f"liquidity_bias missing: {field}"
    for field in _REQUIRED_CTX:
        assert field in ls["simple_context"], f"simple_context missing: {field}"
    for field in _REQUIRED_QUALITY_CTX:
        assert field in ls["quality_context"], f"quality_context missing: {field}"


def test_reason_codes_not_empty():
    ls = run_fake_sample("BTCUSDT")
    assert ls["reason_codes"], "reason_codes must not be empty"
    assert isinstance(ls["reason_codes"], list)
    assert len(ls["reason_codes"]) >= 1


def test_feeds_next_includes_s6():
    ls = run_fake_sample("BTCUSDT")
    assert "S6_SCENARIO_SETUP_CANDIDATE" in ls["feeds_next"]["next_blocks"]


def test_price_zone_valid():
    ls = run_fake_sample("BTCUSDT")
    assert ls["range_context"]["price_zone"] in _VALID_PRICE_ZONES


def test_structure_bias_valid():
    ls = run_fake_sample("BTCUSDT")
    assert ls["structure"]["structure_bias"] in _VALID_STRUCTURE_BIAS


def test_draw_on_liquidity_valid():
    ls = run_fake_sample("BTCUSDT")
    assert ls["liquidity_bias"]["draw_on_liquidity"] in _VALID_DRAW


def test_liquidity_levels_present():
    ls = run_fake_sample("BTCUSDT")
    ll = ls["liquidity_levels"]
    for key in ("nearest_liquidity_above", "nearest_liquidity_below"):
        assert key in ll, f"liquidity_levels missing: {key}"
        level = ll[key]
        for field in _REQUIRED_LIQ_LEVEL:
            assert field in level, f"{key} missing field: {field}"


def test_liquidity_notes_is_list():
    ls = run_fake_sample("BTCUSDT")
    assert isinstance(ls["liquidity_notes"], list)


def test_context_score_in_range():
    ls = run_fake_sample("BTCUSDT")
    score = ls["simple_context"]["context_score"]
    assert 0.0 <= score <= 100.0, f"context_score {score} out of valid range 0-100"


def test_usable_for_setup_candidate_is_bool():
    ls = run_fake_sample("BTCUSDT")
    assert isinstance(ls["simple_context"]["usable_for_setup_candidate"], bool)


def test_nearest_support_resistance_types():
    ls = run_fake_sample("BTCUSDT")
    ns = ls["nearest_support"]
    nr = ls["nearest_resistance"]
    assert ns is None or isinstance(ns, float)
    assert nr is None or isinstance(nr, float)


def test_feeds_next_always_set():
    ls = build_liquidity_structure("BTCUSDT", None, None, None, "NO_DATA")
    assert ls["feeds_next"]["next_blocks"], "feeds_next must always be set"
    assert len(ls["feeds_next"]["next_blocks"]) >= 1


def test_missing_s1_returns_unknown_zone():
    ls = build_liquidity_structure("BTCUSDT", None, _FAKE_S3, _FAKE_S4, "TEST")
    assert ls["input_status"]["market_truth_available"] is False
    assert ls["range_context"]["price_zone"] == "UNKNOWN"
    assert ls["reason_codes"]
    assert ls["feeds_next"]["next_blocks"]


def test_missing_s3_returns_unknown_structure():
    ls = build_liquidity_structure("BTCUSDT", _FAKE_S1, None, _FAKE_S4, "TEST")
    assert ls["input_status"]["hybrid_candle_available"] is False
    assert ls["structure"]["structure_bias"] == "UNKNOWN"
    assert ls["reason_codes"]
    assert ls["feeds_next"]["next_blocks"]


def test_missing_s4_uses_fallback_quality():
    ls = build_liquidity_structure("BTCUSDT", _FAKE_S1, _FAKE_S3, None, "TEST")
    assert ls["input_status"]["quality_weight_available"] is False
    assert ls["quality_context"]["inherited_quality_weight"] == 0.5
    assert ls["reason_codes"]


def test_bullish_candle_draws_above():
    s3_bullish = dict(_FAKE_S3)
    s3_bullish["candle_direction"] = "BULLISH"
    s3_bullish["body_pct"] = 60.0
    ls = build_liquidity_structure("BTCUSDT", _FAKE_S1, s3_bullish, _FAKE_S4, "TEST")
    assert ls["structure"]["structure_bias"] == "BULLISH"
    assert ls["liquidity_bias"]["draw_on_liquidity"] == "ABOVE"


def test_bearish_candle_draws_below():
    s3_bearish = dict(_FAKE_S3)
    s3_bearish["candle_direction"] = "BEARISH"
    s3_bearish["body_pct"] = 60.0
    s3_bearish["shape_label"] = "BEARISH_MARUBOZU"
    ls = build_liquidity_structure("BTCUSDT", _FAKE_S1, s3_bearish, _FAKE_S4, "TEST")
    assert ls["structure"]["structure_bias"] == "BEARISH"
    assert ls["liquidity_bias"]["draw_on_liquidity"] == "BELOW"


def test_small_body_is_range_bias():
    s3_range = dict(_FAKE_S3)
    s3_range["body_pct"] = 5.0
    ls = build_liquidity_structure("BTCUSDT", _FAKE_S1, s3_range, _FAKE_S4, "TEST")
    assert ls["structure"]["structure_bias"] == "RANGE"
    assert ls["liquidity_bias"]["draw_on_liquidity"] == "BOTH"


def test_runner_creates_all_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        ls = run_fake_sample("BTCUSDT")
        runner._write_outputs(ls)

        assert (tmp / "state" / "latest_liquidity_structure.json").exists()
        assert (tmp / "state" / "s5_liquidity_structure_state.json").exists()
        assert (tmp / "data" / "liquidity_structure.jsonl").exists()
        assert (tmp / "reports" / "s5_liquidity_structure_latest_report.md").exists()

        data = json.loads(
            (tmp / "state" / "latest_liquidity_structure.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == "S5_LIQUIDITY_STRUCTURE_CONTEXT"
        assert data["reason_codes"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
