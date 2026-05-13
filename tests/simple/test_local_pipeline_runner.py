"""Tests for S11.1 Local Pipeline Runner."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.local_pipeline_runner import (
    BLOCK_ID,
    FEEDS_NEXT,
    _STAGES,
    _check_critical,
    _classify_status,
    run_pipeline,
)
import src.simple.run_local_full_pipeline as runner_module

_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "execution_summary", "block_results", "data_quality",
    "reason_codes", "feeds_next", "execution_safety",
]
_REQUIRED_EXEC_SUMMARY = [
    "blocks_total", "blocks_passed", "blocks_failed",
    "pipeline_status", "stop_reason",
]
_REQUIRED_BLOCK_RESULT = ["block_id", "status", "runtime_ms", "error"]
_REQUIRED_SAFETY = ["safe_to_open_real_trade", "private_api_used", "live_order_sent"]


# ── Contract: top-level fields ────────────────────────────────────────────────

def test_all_required_top_fields():
    result = run_pipeline("BTCUSDT")
    for f in _REQUIRED_TOP:
        assert f in result, f"Missing top-level field: {f}"


def test_block_id_matches_constant():
    result = run_pipeline("BTCUSDT")
    assert result["block_id"] == BLOCK_ID


def test_symbol_propagated():
    result = run_pipeline("ETHUSDT")
    assert result["symbol"] == "ETHUSDT"


def test_execution_summary_fields():
    result = run_pipeline("BTCUSDT")
    for f in _REQUIRED_EXEC_SUMMARY:
        assert f in result["execution_summary"], f"execution_summary missing: {f}"


def test_each_block_result_has_required_fields():
    result = run_pipeline("BTCUSDT")
    for br in result["block_results"]:
        for f in _REQUIRED_BLOCK_RESULT:
            assert f in br, f"block_result missing: {f}"


def test_data_quality_fields():
    result = run_pipeline("BTCUSDT")
    dq = result["data_quality"]
    assert "score" in dq
    assert "level" in dq
    assert "issues" in dq


def test_execution_safety_fields():
    result = run_pipeline("BTCUSDT")
    for f in _REQUIRED_SAFETY:
        assert f in result["execution_safety"], f"execution_safety missing: {f}"


# ── Contract: invariants ──────────────────────────────────────────────────────

def test_safe_to_open_real_trade_always_false():
    result = run_pipeline("BTCUSDT")
    assert result["execution_safety"]["safe_to_open_real_trade"] is False


def test_private_api_always_false():
    result = run_pipeline("BTCUSDT")
    assert result["execution_safety"]["private_api_used"] is False


def test_live_order_always_false():
    result = run_pipeline("BTCUSDT")
    assert result["execution_safety"]["live_order_sent"] is False


def test_reason_codes_not_empty():
    result = run_pipeline("BTCUSDT")
    codes = result["reason_codes"]
    assert isinstance(codes, list)
    assert len(codes) >= 1
    assert all(isinstance(c, str) for c in codes)


def test_feeds_next_is_dict_with_next_blocks():
    result = run_pipeline("BTCUSDT")
    assert "next_blocks" in result["feeds_next"]
    assert isinstance(result["feeds_next"]["next_blocks"], list)


# ── Execution summary correctness ─────────────────────────────────────────────

def test_blocks_total_matches_stage_count():
    result = run_pipeline("BTCUSDT")
    assert result["execution_summary"]["blocks_total"] == len(_STAGES) + 2


def test_passed_plus_failed_equals_blocks_run():
    result = run_pipeline("BTCUSDT")
    es = result["execution_summary"]
    assert es["blocks_passed"] + es["blocks_failed"] == len(result["block_results"])


def test_complete_pipeline_has_zero_failures():
    result = run_pipeline("BTCUSDT")
    if result["execution_summary"]["pipeline_status"] == "COMPLETE":
        assert result["execution_summary"]["blocks_failed"] == 0


def test_complete_pipeline_stop_reason_is_none():
    result = run_pipeline("BTCUSDT")
    if result["execution_summary"]["pipeline_status"] == "COMPLETE":
        assert result["execution_summary"]["stop_reason"] is None


def test_complete_pipeline_all_blocks_have_results():
    result = run_pipeline("BTCUSDT")
    if result["execution_summary"]["pipeline_status"] == "COMPLETE":
        assert len(result["block_results"]) == len(_STAGES) + 2


def test_block_statuses_are_valid_values():
    result = run_pipeline("BTCUSDT")
    valid = {"PASSED", "DEGRADED", "CRITICAL", "FAILED"}
    for br in result["block_results"]:
        assert br["status"] in valid, f"Unexpected status: {br['status']}"


def test_runtime_ms_is_non_negative():
    result = run_pipeline("BTCUSDT")
    for br in result["block_results"]:
        assert br["runtime_ms"] >= 0


# ── Source mode ───────────────────────────────────────────────────────────────

def test_fake_sample_source_mode():
    result = run_pipeline("BTCUSDT", source_mode="FAKE_SAMPLE")
    assert result["source"]["source_mode"] == "FAKE_SAMPLE"


def test_reason_codes_include_pipeline_status():
    result = run_pipeline("BTCUSDT")
    status = result["execution_summary"]["pipeline_status"]
    assert any(status in c for c in result["reason_codes"])


# ── Helper: _check_critical ───────────────────────────────────────────────────

def test_check_critical_valid_output_returns_none():
    output = {
        "timestamp_utc": "2025-01-01T00:00:00Z",
        "block_id": "S1_TEST",
        "symbol": "BTCUSDT",
        "source": {"source_mode": "FAKE_SAMPLE"},
        "data_quality": {"score": 1.0, "level": "HIGH", "issues": []},
        "reason_codes": ["SOME_CODE"],
        "feeds_next": {"next_blocks": []},
    }
    assert _check_critical(output) is None


def test_check_critical_missing_field():
    output = {
        "block_id": "S1_TEST",
        "symbol": "BTCUSDT",
        "source": {},
        "data_quality": {},
        "reason_codes": ["X"],
        "feeds_next": {},
    }
    result = _check_critical(output)
    assert result is not None
    assert "TIMESTAMP" in result or "MISSING" in result


def test_check_critical_empty_reason_codes():
    output = {
        "timestamp_utc": "2025-01-01T00:00:00Z",
        "block_id": "S1_TEST",
        "symbol": "BTCUSDT",
        "source": {},
        "data_quality": {},
        "reason_codes": [],
        "feeds_next": {},
    }
    assert _check_critical(output) == "REASON_CODES_EMPTY"


# ── Helper: _classify_status ──────────────────────────────────────────────────

def test_classify_status_high_quality_is_passed():
    output = {"data_quality": {"level": "HIGH", "score": 1.0, "issues": []}}
    assert _classify_status(output) == "PASSED"


def test_classify_status_medium_quality_is_passed():
    output = {"data_quality": {"level": "MEDIUM", "score": 0.6, "issues": []}}
    assert _classify_status(output) == "PASSED"


def test_classify_status_low_quality_is_degraded():
    output = {"data_quality": {"level": "LOW", "score": 0.3, "issues": []}}
    assert _classify_status(output) == "DEGRADED"


def test_classify_status_critical_quality_is_degraded():
    output = {"data_quality": {"level": "CRITICAL", "score": 0.0, "issues": []}}
    assert _classify_status(output) == "DEGRADED"


# ── Stop on critical corruption ───────────────────────────────────────────────

def test_bad_module_stops_pipeline(monkeypatch):
    import src.simple.local_pipeline_runner as lpr
    original_stages = lpr._STAGES

    bad_stages = [("src.simple.NONEXISTENT_MODULE_XYZ", "run_fake_sample", "S_BAD")]
    monkeypatch.setattr(lpr, "_STAGES", bad_stages)

    result = lpr.run_pipeline("BTCUSDT")
    assert result["execution_summary"]["pipeline_status"] == "STOPPED_CRITICAL"
    assert result["execution_summary"]["blocks_failed"] >= 1
    assert result["execution_summary"]["blocks_passed"] == 0


def test_pipeline_continues_on_degraded_output(monkeypatch):
    import src.simple.local_pipeline_runner as lpr

    def _fake_degraded(symbol):
        return {
            "timestamp_utc": "2025-01-01T00:00:00Z",
            "block_id": "S_DEGRADED",
            "symbol": symbol,
            "source": {"source_mode": "FAKE_SAMPLE"},
            "data_quality": {"score": 0.0, "level": "CRITICAL", "issues": ["SOME_ISSUE"]},
            "reason_codes": ["DEGRADED_CODE"],
            "feeds_next": {"next_blocks": []},
        }

    original = lpr._run_stage

    call_count = 0

    def _patched_run_stage(module_path, func_name, symbol):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _fake_degraded(symbol), 1.0, None
        return original(module_path, func_name, symbol)

    monkeypatch.setattr(lpr, "_run_stage", _patched_run_stage)

    result = lpr.run_pipeline("BTCUSDT")
    assert call_count >= 2, "Pipeline should continue after first degraded block"
    assert result["block_results"][0]["status"] == "DEGRADED"


# ── Runner: file outputs ──────────────────────────────────────────────────────

def test_runner_creates_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner_module, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner_module, "REPORTS_DIR", tmp / "reports")

        summary = run_pipeline("BTCUSDT")
        runner_module._write_outputs(summary)

        assert (tmp / "state" / "latest_local_pipeline_run.json").exists()
        assert (tmp / "reports" / "local_pipeline_latest_report.md").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_state_json_valid_contract(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner_module, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner_module, "REPORTS_DIR", tmp / "reports")

        summary = run_pipeline("BTCUSDT")
        runner_module._write_outputs(summary)

        data = json.loads(
            (tmp / "state" / "latest_local_pipeline_run.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == BLOCK_ID
        assert data["reason_codes"]
        assert data["execution_safety"]["safe_to_open_real_trade"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_report_contains_key_sections(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner_module, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner_module, "REPORTS_DIR", tmp / "reports")

        summary = run_pipeline("BTCUSDT")
        runner_module._write_outputs(summary)

        text = (tmp / "reports" / "local_pipeline_latest_report.md").read_text(encoding="utf-8")
        assert "S11.1 Local Full Pipeline" in text
        assert "Execution Summary" in text
        assert "Block Results" in text
        assert "Execution Safety" in text
        assert "Reason Codes" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
