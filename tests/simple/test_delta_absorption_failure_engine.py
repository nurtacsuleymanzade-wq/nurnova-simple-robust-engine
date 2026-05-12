from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.delta_absorption_failure_engine import (
    compute_delta_absorption_failure,
    no_valid_output,
    run_delta_absorption_failure_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_daf():
    path = TMP_BASE / f"daf_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _evidence(delta_score: float, evidence_score: float) -> dict:
    return {
        "symbol": "BTCUSDT",
        "delta_evidence": {"delta": 120.0, "delta_score": delta_score},
        "pressure_evidence": {"pressure_score": delta_score},
        "evidence_score": evidence_score,
        "data_quality": {"level": "OK", "score": 1.0},
    }


def _persistence(avg_30s: float = 0.2, avg_5m: float = 0.4, consistency: float = 0.4) -> dict:
    return {
        "symbol": "BTCUSDT",
        "windows": {
            "last_30s": {"avg_evidence_score": avg_30s},
            "last_5m": {
                "avg_evidence_score": avg_5m,
                "direction_consistency": consistency,
            },
        },
        "data_quality": {"level": "OK", "score": 1.0},
    }


def test_daf_output_fields_present():
    result = compute_delta_absorption_failure(_evidence(6.0, 0.1), _persistence())
    assert result["block_id"] == "DAF_DELTA_ABSORPTION_FAILURE"
    assert "failure_strength" in result
    assert result["aggressive_side_failed"] == "BUYERS"
    assert result["timeframe"] == "1m"


def test_missing_input_returns_no_valid_output():
    result = no_valid_output("TEST_MISSING")
    assert result["input_status"] == "MISSING"
    assert result["delta_divergence"] is False
    assert "TEST_MISSING" in result["reason_codes"]


def test_divergence_threshold_triggers_correctly():
    triggered = compute_delta_absorption_failure(_evidence(5.0, 0.2), _persistence())
    assert triggered["delta_divergence"] is True
    assert triggered["reversal_bias"] == "SHORT"

    not_triggered = compute_delta_absorption_failure(_evidence(2.0, 1.0), _persistence())
    assert not_triggered["delta_divergence"] is False


def test_run_creates_state_and_log(tmp_daf, monkeypatch):
    import src.simple.delta_absorption_failure_engine as eng

    evidence_path = tmp_daf / "latest_flow_evidence.json"
    persistence_path = tmp_daf / "latest_flow_persistence.json"
    evidence_path.write_text(json.dumps(_evidence(6.5, 0.0)), encoding="utf-8")
    persistence_path.write_text(json.dumps(_persistence()), encoding="utf-8")

    monkeypatch.setattr(eng, "FLOW_EVIDENCE_PATH", evidence_path)
    monkeypatch.setattr(eng, "FLOW_PERSISTENCE_PATH", persistence_path)
    monkeypatch.setattr(eng, "DAF_PATH", tmp_daf / "latest_daf.json")
    monkeypatch.setattr(eng, "DAF_LOG_PATH", tmp_daf / "daf_history.jsonl")

    result = run_delta_absorption_failure_engine()
    assert result["delta_divergence"] is True
    assert (tmp_daf / "latest_daf.json").exists()
    assert (tmp_daf / "daf_history.jsonl").exists()
