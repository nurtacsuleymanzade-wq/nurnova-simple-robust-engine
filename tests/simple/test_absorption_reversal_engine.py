from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.absorption_reversal_engine import (
    compute_absorption_reversal,
    no_valid_output,
    run_absorption_reversal_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_ar01():
    path = TMP_BASE / f"ar01_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _evidence(pressure_score: float, evidence_score: float) -> dict:
    return {
        "timestamp_utc": "2026-05-13T12:00:00Z",
        "block_id": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "symbol": "BTCUSDT",
        "input_status": "OK",
        "pressure_evidence": {
            "buy_volume": 12.0,
            "sell_volume": 2.0,
            "pressure_score": pressure_score,
        },
        "aggression_evidence": {"aggression_score": 6.0},
        "delta_evidence": {"delta_score": 5.0},
        "evidence_score": evidence_score,
        "evidence_label": "NEUTRAL_FLOW",
        "data_quality": {"level": "OK", "score": 1.0},
    }


def test_absorption_output_fields_present():
    result = compute_absorption_reversal(_evidence(7.5, -0.2))
    assert result["block_id"] == "AR01_ABSORPTION_REVERSAL"
    assert result["absorption_detected"] is True
    assert result["reversal_bias"] == "SHORT"
    assert "absorption_strength" in result


def test_missing_input_returns_no_valid_output():
    result = no_valid_output("TEST_MISSING")
    assert result["input_status"] == "MISSING"
    assert result["absorption_detected"] is False
    assert "TEST_MISSING" in result["reason_codes"]


def test_absorption_threshold_triggers_correctly():
    buyers_absorbed = compute_absorption_reversal(_evidence(4.0, 0.9))
    assert buyers_absorbed["absorption_detected"] is True
    assert buyers_absorbed["aggressor_side"] == "BUYERS"
    assert buyers_absorbed["reversal_bias"] == "SHORT"

    no_absorption = compute_absorption_reversal(_evidence(1.5, 5.0))
    assert no_absorption["absorption_detected"] is False
    assert no_absorption["aggressor_side"] == "NEUTRAL"


def test_run_creates_state_and_log(tmp_ar01, monkeypatch):
    import src.simple.absorption_reversal_engine as eng

    evidence_path = tmp_ar01 / "latest_flow_evidence.json"
    evidence_path.write_text(json.dumps(_evidence(6.0, 0.0)), encoding="utf-8")

    monkeypatch.setattr(eng, "FLOW_EVIDENCE_PATH", evidence_path)
    monkeypatch.setattr(eng, "AR01_PATH", tmp_ar01 / "latest_ar01.json")
    monkeypatch.setattr(eng, "AR01_LOG_PATH", tmp_ar01 / "ar01_history.jsonl")

    result = run_absorption_reversal_engine()
    assert result["absorption_detected"] is True
    assert (tmp_ar01 / "latest_ar01.json").exists()
    assert (tmp_ar01 / "ar01_history.jsonl").exists()
