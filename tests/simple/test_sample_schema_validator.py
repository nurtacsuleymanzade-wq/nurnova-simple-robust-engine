"""Tests for S11.2 Sample Schema Validator."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.sample_schema_validator import (
    BLOCK_ID,
    FEEDS_NEXT,
    validate_file,
    _validate_row,
    _build_data_quality,
    _validate_timestamp,
    _is_numeric,
)
import src.simple.run_sample_schema_validator as runner

_HERE = pathlib.Path(__file__).parent

_VALID_ROW: dict = {
    "sample_id": 0, "seed": 42, "symbol": "BTCUSDT",
    "scenario": {
        "candle_direction": "BULLISH", "evidence_label": "LONG_PRESSURE",
        "quality_weight": 0.75, "structure_bias": "bullish",
        "setup_type": "LONG_BREAKOUT", "setup_direction": "LONG", "setup_grade": "A",
    },
    "decision": {
        "paper_decision": "LONG", "entry_price": 107000.0, "stop_loss": 106000.0,
        "tp1": 107700.0, "tp2": 109000.0, "rr_tp1": 0.7, "rr_tp2": 2.0,
    },
    "outcome": {"outcome": "WIN_TP1", "realized_rr": 0.7, "edge_eligible": True},
}

_NO_TRADE_ROW: dict = {
    "sample_id": 1, "seed": 42, "symbol": "BTCUSDT",
    "scenario": {
        "candle_direction": "DOJI", "evidence_label": "NEUTRAL",
        "quality_weight": 0.4, "structure_bias": "neutral",
        "setup_type": "NO_SETUP", "setup_direction": "NONE", "setup_grade": "NONE",
    },
    "decision": {
        "paper_decision": "NO_TRADE", "entry_price": None, "stop_loss": None,
        "tp1": None, "tp2": None, "rr_tp1": None, "rr_tp2": None,
    },
    "outcome": {"outcome": "NO_TRADE", "realized_rr": None, "edge_eligible": False},
}


def _write_jsonl(tmp_dir: pathlib.Path, rows: list) -> pathlib.Path:
    p = tmp_dir / "test.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return p


# ── _validate_timestamp ───────────────────────────────────────────────────────

def test_timestamp_valid():
    assert _validate_timestamp("2026-05-11T12:00:00Z") is True


def test_timestamp_invalid_format():
    assert _validate_timestamp("2026/05/11 12:00:00") is False


def test_timestamp_empty():
    assert _validate_timestamp("") is False


def test_timestamp_none():
    assert _validate_timestamp(None) is False


# ── _is_numeric ───────────────────────────────────────────────────────────────

def test_is_numeric_int():
    assert _is_numeric(42) is True


def test_is_numeric_float():
    assert _is_numeric(3.14) is True


def test_is_numeric_bool_is_not_numeric():
    assert _is_numeric(True) is False


def test_is_numeric_string():
    assert _is_numeric("1.0") is False


def test_is_numeric_none():
    assert _is_numeric(None) is False


# ── _validate_row: valid rows produce no errors ───────────────────────────────

def test_valid_trade_row_no_errors():
    assert _validate_row(_VALID_ROW, 0) == []


def test_valid_no_trade_row_no_errors():
    assert _validate_row(_NO_TRADE_ROW, 1) == []


# ── _validate_row: missing required top-level fields ─────────────────────────

@pytest.mark.parametrize("field", ["sample_id", "seed", "symbol", "scenario", "decision", "outcome"])
def test_missing_top_level_field(field):
    row = {k: v for k, v in _VALID_ROW.items() if k != field}
    errors = _validate_row(row, 0)
    assert any(field in e for e in errors)


# ── _validate_row: null critical fields ──────────────────────────────────────

@pytest.mark.parametrize("field", ["sample_id", "seed", "symbol"])
def test_null_critical_top_field(field):
    row = {**_VALID_ROW, field: None}
    errors = _validate_row(row, 0)
    assert any(field in e for e in errors)


def test_null_paper_decision():
    row = {**_VALID_ROW, "decision": {**_VALID_ROW["decision"], "paper_decision": None}}
    errors = _validate_row(row, 0)
    assert any("paper_decision" in e for e in errors)


def test_null_outcome_field():
    row = {**_VALID_ROW, "outcome": {**_VALID_ROW["outcome"], "outcome": None}}
    errors = _validate_row(row, 0)
    assert any("outcome" in e for e in errors)


def test_null_edge_eligible():
    row = {**_VALID_ROW, "outcome": {**_VALID_ROW["outcome"], "edge_eligible": None}}
    errors = _validate_row(row, 0)
    assert any("edge_eligible" in e for e in errors)


# ── _validate_row: scenario enum validation ───────────────────────────────────

def test_invalid_candle_direction():
    row = {**_VALID_ROW, "scenario": {**_VALID_ROW["scenario"], "candle_direction": "SIDEWAYS"}}
    errors = _validate_row(row, 0)
    assert any("candle_direction" in e for e in errors)


def test_invalid_evidence_label():
    row = {**_VALID_ROW, "scenario": {**_VALID_ROW["scenario"], "evidence_label": "UNKNOWN"}}
    errors = _validate_row(row, 0)
    assert any("evidence_label" in e for e in errors)


def test_invalid_structure_bias():
    row = {**_VALID_ROW, "scenario": {**_VALID_ROW["scenario"], "structure_bias": "STRONG"}}
    errors = _validate_row(row, 0)
    assert any("structure_bias" in e for e in errors)


def test_invalid_setup_type():
    row = {**_VALID_ROW, "scenario": {**_VALID_ROW["scenario"], "setup_type": "FAKE_SETUP"}}
    errors = _validate_row(row, 0)
    assert any("setup_type" in e for e in errors)


def test_invalid_setup_direction():
    row = {**_VALID_ROW, "scenario": {**_VALID_ROW["scenario"], "setup_direction": "SIDEWAYS"}}
    errors = _validate_row(row, 0)
    assert any("setup_direction" in e for e in errors)


def test_invalid_setup_grade():
    row = {**_VALID_ROW, "scenario": {**_VALID_ROW["scenario"], "setup_grade": "D"}}
    errors = _validate_row(row, 0)
    assert any("setup_grade" in e for e in errors)


# ── _validate_row: decision validation ───────────────────────────────────────

def test_invalid_paper_decision():
    row = {**_VALID_ROW, "decision": {**_VALID_ROW["decision"], "paper_decision": "HOLD"}}
    errors = _validate_row(row, 0)
    assert any("paper_decision" in e for e in errors)


def test_rr_tp1_not_numeric():
    row = {**_VALID_ROW, "decision": {**_VALID_ROW["decision"], "rr_tp1": "high"}}
    errors = _validate_row(row, 0)
    assert any("rr_tp1" in e for e in errors)


def test_rr_tp2_not_numeric():
    row = {**_VALID_ROW, "decision": {**_VALID_ROW["decision"], "rr_tp2": "low"}}
    errors = _validate_row(row, 0)
    assert any("rr_tp2" in e for e in errors)


def test_rr_null_is_valid():
    row = {**_VALID_ROW, "decision": {**_VALID_ROW["decision"], "rr_tp1": None, "rr_tp2": None}}
    errors = _validate_row(row, 0)
    assert not any("rr_tp" in e for e in errors)


# ── _validate_row: outcome validation ────────────────────────────────────────

def test_invalid_outcome_value():
    row = {**_VALID_ROW, "outcome": {**_VALID_ROW["outcome"], "outcome": "MAYBE_WIN"}}
    errors = _validate_row(row, 0)
    assert any("outcome" in e for e in errors)


def test_edge_eligible_not_bool():
    row = {**_VALID_ROW, "outcome": {**_VALID_ROW["outcome"], "edge_eligible": 1}}
    errors = _validate_row(row, 0)
    assert any("edge_eligible" in e for e in errors)


def test_realized_rr_not_numeric():
    row = {**_VALID_ROW, "outcome": {**_VALID_ROW["outcome"], "realized_rr": "good"}}
    errors = _validate_row(row, 0)
    assert any("realized_rr" in e for e in errors)


def test_realized_rr_null_is_valid():
    row = {**_VALID_ROW, "outcome": {**_VALID_ROW["outcome"], "realized_rr": None}}
    errors = _validate_row(row, 0)
    assert not any("realized_rr" in e for e in errors)


# ── _validate_row: timestamp format (optional field) ─────────────────────────

def test_valid_timestamp_in_row():
    row = {**_VALID_ROW, "timestamp_utc": "2026-05-11T10:00:00Z"}
    assert _validate_row(row, 0) == []


def test_invalid_timestamp_in_row():
    row = {**_VALID_ROW, "timestamp_utc": "not-a-timestamp"}
    errors = _validate_row(row, 0)
    assert any("timestamp_utc" in e for e in errors)


# ── _build_data_quality ───────────────────────────────────────────────────────

def test_data_quality_no_rows():
    dq = _build_data_quality(0, 0, 0)
    assert dq["level"] == "CRITICAL"


def test_data_quality_malformed_rows():
    dq = _build_data_quality(10, 0, 1)
    assert dq["level"] == "CRITICAL"


def test_data_quality_high_error_rate():
    dq = _build_data_quality(10, 5, 0)
    assert dq["level"] == "CRITICAL"


def test_data_quality_some_errors():
    dq = _build_data_quality(100, 1, 0)
    assert dq["level"] == "MEDIUM"


def test_data_quality_no_errors():
    dq = _build_data_quality(50, 0, 0)
    assert dq["level"] == "HIGH"
    assert dq["score"] == 1.0


# ── validate_file: full file integration ─────────────────────────────────────

def test_validate_file_all_valid_rows():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = _write_jsonl(tmp, [_VALID_ROW, _NO_TRADE_ROW])
        result = validate_file(p)
        assert result["validation_summary"]["total_rows"] == 2
        assert result["validation_summary"]["valid_rows"] == 2
        assert result["validation_summary"]["error_rows"] == 0
        assert result["validation_summary"]["malformed_rows"] == 0
        assert result["data_quality"]["level"] == "HIGH"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_malformed_json():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = tmp / "bad.jsonl"
        p.write_text('{"good": 1}\nnot valid json\n', encoding="utf-8")
        result = validate_file(p)
        assert result["validation_summary"]["malformed_rows"] == 1
        assert result["data_quality"]["level"] == "CRITICAL"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_error_row():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        bad_row = {**_VALID_ROW, "scenario": {**_VALID_ROW["scenario"], "candle_direction": "INVALID"}}
        p = _write_jsonl(tmp, [bad_row])
        result = validate_file(p)
        assert result["validation_summary"]["error_rows"] == 1
        assert len(result["errors"]) >= 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_empty_file():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = tmp / "empty.jsonl"
        p.write_text("", encoding="utf-8")
        result = validate_file(p)
        assert result["validation_summary"]["total_rows"] == 0
        assert result["data_quality"]["level"] == "CRITICAL"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_skips_blank_lines():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = tmp / "blanks.jsonl"
        p.write_text(
            json.dumps(_VALID_ROW) + "\n\n" + json.dumps(_NO_TRADE_ROW) + "\n",
            encoding="utf-8",
        )
        result = validate_file(p)
        assert result["validation_summary"]["total_rows"] == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── validate_file: JSON contract fields ──────────────────────────────────────

_REQUIRED_CONTRACT_FIELDS = [
    "timestamp_utc", "block_id", "symbol", "source",
    "validation_summary", "errors", "data_quality",
    "reason_codes", "feeds_next", "execution_safety",
]


def test_validate_file_all_contract_fields():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = _write_jsonl(tmp, [_VALID_ROW])
        result = validate_file(p)
        for f in _REQUIRED_CONTRACT_FIELDS:
            assert f in result, f"Missing contract field: {f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_block_id():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = _write_jsonl(tmp, [_VALID_ROW])
        result = validate_file(p)
        assert result["block_id"] == BLOCK_ID
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_reason_codes_not_empty():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = _write_jsonl(tmp, [_VALID_ROW])
        result = validate_file(p)
        assert isinstance(result["reason_codes"], list)
        assert len(result["reason_codes"]) >= 1
        assert all(isinstance(c, str) for c in result["reason_codes"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_execution_safety():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = _write_jsonl(tmp, [_VALID_ROW])
        result = validate_file(p)
        es = result["execution_safety"]
        assert es["safe_to_open_real_trade"] is False
        assert es["private_api_used"] is False
        assert es["live_order_sent"] is False
        assert es["research_only"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validate_file_feeds_next():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        p = _write_jsonl(tmp, [_VALID_ROW])
        result = validate_file(p)
        assert "S11_REPLAY_SAMPLE_RUNNER" in result["feeds_next"]["next_blocks"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Runner: output files ──────────────────────────────────────────────────────

def test_runner_creates_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        data_file = _write_jsonl(tmp, [_VALID_ROW, _NO_TRADE_ROW])
        monkeypatch.setattr(runner, "DATA_FILE", data_file)
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        result = validate_file(data_file)
        runner._write_outputs(result)

        assert (tmp / "state" / "latest_schema_validation.json").exists()
        assert (tmp / "reports" / "schema_validation_latest_report.md").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_state_json_valid(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        data_file = _write_jsonl(tmp, [_VALID_ROW])
        monkeypatch.setattr(runner, "DATA_FILE", data_file)
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        result = validate_file(data_file)
        runner._write_outputs(result)

        data = json.loads(
            (tmp / "state" / "latest_schema_validation.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == BLOCK_ID
        assert data["reason_codes"]
        assert data["execution_safety"]["safe_to_open_real_trade"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_report_contains_key_sections(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=_HERE))
    try:
        data_file = _write_jsonl(tmp, [_VALID_ROW])
        monkeypatch.setattr(runner, "DATA_FILE", data_file)
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        result = validate_file(data_file)
        runner._write_outputs(result)

        text = (tmp / "reports" / "schema_validation_latest_report.md").read_text(encoding="utf-8")
        assert "S11.2 Sample Schema Validator" in text
        assert "Validation Summary" in text
        assert "Execution Safety" in text
        assert "Feeds Next" in text
        assert "S11_REPLAY_SAMPLE_RUNNER" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
