from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.failed_continuation_reversal_engine import (
    compute_failed_continuation_reversal,
    no_valid_output,
    run_failed_continuation_reversal_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_fcr():
    path = TMP_BASE / f"fcr_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _persistence(
    label: str = "SUSTAINED_LONG_PRESSURE",
    last_30_label: str = "SHORT",
    avg_30s: float = -2.0,
    decay_risk: bool = False,
    flip_risk: bool = False,
) -> dict:
    return {
        "symbol": "BTCUSDT",
        "input_status": "OK",
        "persistence_label": label,
        "continuation_quality": "SUSTAINED",
        "decay_risk": decay_risk,
        "flip_risk": flip_risk,
        "windows": {
            "last_30s": {
                "avg_evidence_score": avg_30s,
                "dominant_label": last_30_label,
            },
            "last_5m": {
                "avg_evidence_score": 4.0,
                "dominant_label": "LONG",
                "direction_consistency": 0.8,
            },
        },
        "direction_label": "LONG",
        "data_quality": {"level": "OK", "score": 1.0},
    }


def test_fcr_output_fields_present():
    result = compute_failed_continuation_reversal(_persistence())
    assert result["block_id"] == "FCR_FAILED_CONTINUATION"
    assert result["had_momentum"] is True
    assert "trap_strength" in result


def test_missing_input_returns_no_valid_output():
    result = no_valid_output("TEST_MISSING")
    assert result["input_status"] == "MISSING"
    assert result["continuation_failed"] is False
    assert "TEST_MISSING" in result["reason_codes"]


def test_continuation_failure_threshold_triggers_correctly():
    reversed_flow = compute_failed_continuation_reversal(_persistence())
    assert reversed_flow["continuation_failed"] is True
    assert reversed_flow["trapped_side"] == "BUYERS"
    assert reversed_flow["reversal_ready"] is True

    clean_flow = compute_failed_continuation_reversal(
        _persistence(last_30_label="LONG", avg_30s=2.0, decay_risk=False, flip_risk=False)
    )
    assert clean_flow["continuation_failed"] is False


def test_run_creates_state_and_log(tmp_fcr, monkeypatch):
    import src.simple.failed_continuation_reversal_engine as eng

    persistence_path = tmp_fcr / "latest_flow_persistence.json"
    persistence_path.write_text(json.dumps(_persistence(decay_risk=True)), encoding="utf-8")

    monkeypatch.setattr(eng, "FLOW_PERSISTENCE_PATH", persistence_path)
    monkeypatch.setattr(eng, "FCR_PATH", tmp_fcr / "latest_fcr.json")
    monkeypatch.setattr(eng, "FCR_LOG_PATH", tmp_fcr / "fcr_history.jsonl")

    result = run_failed_continuation_reversal_engine()
    assert result["continuation_failed"] is True
    assert (tmp_fcr / "latest_fcr.json").exists()
    assert (tmp_fcr / "fcr_history.jsonl").exists()
