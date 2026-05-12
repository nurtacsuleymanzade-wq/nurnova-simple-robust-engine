from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.model_registry import (
    compute_model_registry,
    no_valid_output,
    run_model_registry,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_registry():
    path = TMP_BASE / f"mreg_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _ar01() -> dict:
    return {"symbol": "BTCUSDT", "absorption_detected": True, "reversal_bias": "SHORT", "reversal_probability": 70.0}


def _daf() -> dict:
    return {"symbol": "BTCUSDT", "delta_divergence": True, "reversal_bias": "SHORT", "failure_strength": 65.0}


def _fcr() -> dict:
    return {"symbol": "BTCUSDT", "continuation_failed": True, "trapped_side": "SELLERS", "trap_strength": 55.0}


def _cqe() -> dict:
    return {"symbol": "BTCUSDT", "candle_quality": "FAKE_MOVE"}


def _market_truth() -> dict:
    return {"official_candle": {"close_time_utc": "2026-05-11T12:00:00Z"}}


def test_registry_output_fields_present():
    result = compute_model_registry(_ar01(), _daf(), _fcr(), _cqe(), _market_truth())
    assert result["block_id"] == "MODEL_REGISTRY"
    assert result["active_model_count"] == 3
    assert result["consensus_direction"] in ("LONG", "SHORT", "NEUTRAL")
    assert result["timeframe"] == "1m"
    assert result["candle_close_time"] == "2026-05-11T12:00:00Z"
    assert "trigger_reason" in result["active_signals"][0]


def test_missing_input_returns_no_valid_output():
    result = no_valid_output("TEST_MISSING")
    assert result["input_status"] == "MISSING"
    assert result["active_model_count"] == 0
    assert "TEST_MISSING" in result["reason_codes"]


def test_consensus_threshold_computes_correctly():
    short_consensus = compute_model_registry(_ar01(), _daf(), None, _cqe(), _market_truth())
    assert short_consensus["consensus_direction"] == "SHORT"
    assert short_consensus["short_probability_pct"] > 55.0

    balanced_fcr = {"symbol": "BTCUSDT", "continuation_failed": True, "trapped_side": "SELLERS", "trap_strength": 70.0}
    neutral_consensus = compute_model_registry(_ar01(), None, balanced_fcr, _cqe(), _market_truth())
    assert neutral_consensus["consensus_direction"] == "NEUTRAL"


def test_run_creates_state_and_log(tmp_registry, monkeypatch):
    import src.simple.model_registry as eng

    (tmp_registry / "latest_ar01.json").write_text(json.dumps(_ar01()), encoding="utf-8")
    (tmp_registry / "latest_daf.json").write_text(json.dumps(_daf()), encoding="utf-8")
    (tmp_registry / "latest_fcr.json").write_text(json.dumps(_fcr()), encoding="utf-8")
    (tmp_registry / "latest_cqe.json").write_text(json.dumps(_cqe()), encoding="utf-8")
    (tmp_registry / "latest_market_truth.json").write_text(json.dumps(_market_truth()), encoding="utf-8")

    monkeypatch.setattr(eng, "AR01_PATH", tmp_registry / "latest_ar01.json")
    monkeypatch.setattr(eng, "DAF_PATH", tmp_registry / "latest_daf.json")
    monkeypatch.setattr(eng, "FCR_PATH", tmp_registry / "latest_fcr.json")
    monkeypatch.setattr(eng, "CQE_PATH", tmp_registry / "latest_cqe.json")
    monkeypatch.setattr(eng, "MARKET_TRUTH_PATH", tmp_registry / "latest_market_truth.json")
    monkeypatch.setattr(eng, "MODEL_REGISTRY_PATH", tmp_registry / "latest_model_registry.json")
    monkeypatch.setattr(eng, "MODEL_REGISTRY_LOG_PATH", tmp_registry / "model_registry_history.jsonl")

    result = run_model_registry()
    assert result["active_model_count"] == 3
    assert result["timeframe"] == "1m"
    assert (tmp_registry / "latest_model_registry.json").exists()
    assert (tmp_registry / "model_registry_history.jsonl").exists()
