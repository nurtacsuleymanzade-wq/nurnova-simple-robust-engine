from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.candle_quality_engine import (
    compute_candle_quality,
    no_valid_output,
    run_candle_quality_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_cqe():
    path = TMP_BASE / f"cqe_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _market_truth(open_price: float, high: float, low: float, close: float) -> dict:
    return {
        "symbol": "BTCUSDT",
        "official_candle": {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 100.0,
        },
        "data_quality": {"level": "OK", "score": 1.0},
    }


def _evidence(delta_score: float) -> dict:
    return {
        "symbol": "BTCUSDT",
        "evidence_score": delta_score,
        "delta_evidence": {"delta_score": delta_score},
        "pressure_evidence": {"pressure_score": delta_score},
        "data_quality": {"level": "OK", "score": 1.0},
    }


def _persistence(avg_60s: float = 2.0) -> dict:
    return {
        "symbol": "BTCUSDT",
        "windows": {"last_60s": {"avg_evidence_score": avg_60s}},
        "data_quality": {"level": "OK", "score": 1.0},
    }


def test_cqe_output_fields_present():
    result = compute_candle_quality(
        _market_truth(100.0, 112.0, 99.0, 111.0),
        _evidence(5.0),
        _persistence(),
    )
    assert result["block_id"] == "CQE_CANDLE_QUALITY"
    assert result["candle_quality"] == "STRONG_BULLISH"
    assert result["delta_aligned"] is True
    assert result["timeframe"] == "1m"


def test_missing_input_returns_no_valid_output():
    result = no_valid_output("TEST_MISSING")
    assert result["input_status"] == "MISSING"
    assert result["candle_quality"] == "UNKNOWN"
    assert "TEST_MISSING" in result["reason_codes"]


def test_fake_move_threshold_triggers_correctly():
    fake = compute_candle_quality(
        _market_truth(100.0, 120.0, 99.0, 101.0),
        _evidence(-4.0),
        _persistence(avg_60s=-2.0),
    )
    assert fake["fake_move_probability"] >= 60.0
    assert fake["candle_quality"] == "FAKE_MOVE"


def test_run_creates_state_and_log(tmp_cqe, monkeypatch):
    import src.simple.candle_quality_engine as eng

    market_path = tmp_cqe / "latest_market_truth.json"
    evidence_path = tmp_cqe / "latest_flow_evidence.json"
    persistence_path = tmp_cqe / "latest_flow_persistence.json"
    market_path.write_text(json.dumps(_market_truth(100.0, 112.0, 99.0, 111.0)), encoding="utf-8")
    evidence_path.write_text(json.dumps(_evidence(5.0)), encoding="utf-8")
    persistence_path.write_text(json.dumps(_persistence()), encoding="utf-8")

    monkeypatch.setattr(eng, "MARKET_TRUTH_PATH", market_path)
    monkeypatch.setattr(eng, "FLOW_EVIDENCE_PATH", evidence_path)
    monkeypatch.setattr(eng, "FLOW_PERSISTENCE_PATH", persistence_path)
    monkeypatch.setattr(eng, "CQE_PATH", tmp_cqe / "latest_cqe.json")
    monkeypatch.setattr(eng, "CQE_LOG_PATH", tmp_cqe / "cqe_history.jsonl")

    result = run_candle_quality_engine()
    assert result["candle_quality"] == "STRONG_BULLISH"
    assert (tmp_cqe / "latest_cqe.json").exists()
    assert (tmp_cqe / "cqe_history.jsonl").exists()
