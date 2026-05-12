"""Tests for S11.3 Research Dataset Exporter."""

from __future__ import annotations

import csv
import io
import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.research_dataset_exporter import (
    BLOCK_ID,
    EXPORT_FIELDS,
    FEEDS_NEXT,
    _FAKE_RECORDS,
    build_research_dataset,
    parse_replay_record,
    rows_to_csv,
    run_fake_sample,
)
import src.simple.run_research_dataset_exporter as runner

_REQUIRED_SUMMARY = [
    "timestamp_utc", "block_id", "symbol", "source",
    "export_stats", "data_quality", "reason_codes", "feeds_next",
]

_REQUIRED_EXPORT_STATS = [
    "total_samples", "trades_opened", "no_trade_count",
    "edge_eligible_count", "win_count", "loss_count",
    "win_rate", "avg_rr_realized",
]

_REQUIRED_ROW_FIELDS = [
    "timestamp_utc", "scenario_type", "setup_type", "setup_status",
    "quality_label", "decision", "paper_outcome", "realized_rr",
    "edge_eligible", "brain_status", "brain_mode",
]


# ── Test 1: summary contract fields ──────────────────────────────────────────

def test_fake_sample_summary_required_fields():
    rows, summary = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_SUMMARY:
        assert f in summary, f"Missing summary field: {f}"
    assert summary["block_id"] == BLOCK_ID
    assert summary["symbol"] == "BTCUSDT"


def test_fake_sample_export_stats_fields():
    rows, summary = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_EXPORT_STATS:
        assert f in summary["export_stats"], f"Missing export_stats field: {f}"


def test_fake_sample_data_quality_fields():
    rows, summary = run_fake_sample("BTCUSDT")
    dq = summary["data_quality"]
    for f in ("score", "level", "issues"):
        assert f in dq, f"Missing data_quality field: {f}"


# ── Test 2: row fields ────────────────────────────────────────────────────────

def test_fake_sample_row_fields():
    rows, _ = run_fake_sample("BTCUSDT")
    assert len(rows) == 3
    for f in _REQUIRED_ROW_FIELDS:
        assert f in rows[0], f"Missing row field: {f}"


def test_export_fields_match_spec():
    assert set(EXPORT_FIELDS) == set(_REQUIRED_ROW_FIELDS)


# ── Test 3: reason_codes not empty ────────────────────────────────────────────

def test_reason_codes_not_empty():
    rows, summary = run_fake_sample("BTCUSDT")
    assert isinstance(summary["reason_codes"], list)
    assert len(summary["reason_codes"]) >= 1
    assert all(isinstance(c, str) for c in summary["reason_codes"])


# ── Test 4: feeds_next present ────────────────────────────────────────────────

def test_feeds_next_present():
    rows, summary = run_fake_sample("BTCUSDT")
    assert "next_blocks" in summary["feeds_next"]
    assert len(summary["feeds_next"]["next_blocks"]) >= 1


# ── Test 5: execution safety ──────────────────────────────────────────────────

def test_execution_safety():
    rows, summary = run_fake_sample("BTCUSDT")
    safety = summary["execution_safety"]
    assert safety["safe_to_open_real_trade"] is False
    assert safety["research_only"] is True
    assert safety["private_api_used"] is False
    assert safety["live_order_sent"] is False


# ── Test 6: quality_label derivation ──────────────────────────────────────────

def test_quality_label_high():
    rows, _ = run_fake_sample("BTCUSDT")
    high = [r for r in rows if r["setup_type"] == "LONG_CONTINUATION"]
    assert high[0]["quality_label"] == "HIGH_QUALITY"


def test_quality_label_medium():
    rows, _ = run_fake_sample("BTCUSDT")
    medium = [r for r in rows if r["setup_type"] == "SHORT_CONTINUATION"]
    assert medium[0]["quality_label"] == "MEDIUM_QUALITY"


def test_quality_label_low():
    rows, _ = run_fake_sample("BTCUSDT")
    no_setup = [r for r in rows if r["setup_type"] == "NO_SETUP"]
    assert no_setup[0]["quality_label"] == "LOW_QUALITY"


# ── Test 7: brain_status derivation ──────────────────────────────────────────

def test_brain_status_ready_for_trade():
    rows, _ = run_fake_sample("BTCUSDT")
    trade = [r for r in rows if r["decision"] != "NO_TRADE"]
    assert all(r["brain_status"] == "READY" for r in trade)


def test_brain_status_idle_no_trade():
    rows, _ = run_fake_sample("BTCUSDT")
    no_trade = [r for r in rows if r["decision"] == "NO_TRADE"]
    assert all(r["brain_status"] == "IDLE" for r in no_trade)


# ── Test 8: brain_mode derivation ────────────────────────────────────────────

def test_brain_mode_paper_long():
    rows, _ = run_fake_sample("BTCUSDT")
    long_rows = [r for r in rows if r["decision"] == "LONG"]
    assert all(r["brain_mode"] == "PAPER_LONG" for r in long_rows)


def test_brain_mode_paper_short():
    rows, _ = run_fake_sample("BTCUSDT")
    short_rows = [r for r in rows if r["decision"] == "SHORT"]
    assert all(r["brain_mode"] == "PAPER_SHORT" for r in short_rows)


def test_brain_mode_paper_idle():
    rows, _ = run_fake_sample("BTCUSDT")
    idle_rows = [r for r in rows if r["decision"] == "NO_TRADE"]
    assert all(r["brain_mode"] == "PAPER_IDLE" for r in idle_rows)


# ── Test 9: setup_status derivation ──────────────────────────────────────────

def test_setup_status_ready_for_plan():
    rows, _ = run_fake_sample("BTCUSDT")
    setup_rows = [r for r in rows if r["setup_type"] != "NO_SETUP"]
    assert all(r["setup_status"] == "READY_FOR_PLAN" for r in setup_rows)


def test_setup_status_no_setup():
    rows, _ = run_fake_sample("BTCUSDT")
    no_setup = [r for r in rows if r["setup_type"] == "NO_SETUP"]
    assert all(r["setup_status"] == "NO_SETUP" for r in no_setup)


# ── Test 10: scenario_type derivation ────────────────────────────────────────

def test_scenario_type_continuation():
    rows, _ = run_fake_sample("BTCUSDT")
    for r in rows:
        if r["setup_type"] in ("LONG_CONTINUATION", "SHORT_CONTINUATION"):
            assert r["scenario_type"] == "CONTINUATION"


def test_scenario_type_no_setup():
    rows, _ = run_fake_sample("BTCUSDT")
    for r in rows:
        if r["setup_type"] == "NO_SETUP":
            assert r["scenario_type"] == "NO_SETUP"


# ── Test 11: CSV structure ────────────────────────────────────────────────────

def test_csv_has_all_fields():
    rows, _ = run_fake_sample("BTCUSDT")
    csv_text = rows_to_csv(rows)
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        for f in EXPORT_FIELDS:
            assert f in row, f"CSV missing field: {f}"


def test_csv_row_count():
    rows, _ = run_fake_sample("BTCUSDT")
    csv_text = rows_to_csv(rows)
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(reader) == len(rows)


# ── Test 12: parse_replay_record ─────────────────────────────────────────────

def test_parse_replay_record_valid():
    raw = _FAKE_RECORDS[0]
    row = parse_replay_record(raw, "2026-01-01T00:00:00Z")
    assert row is not None
    assert row["decision"] == "LONG"
    assert row["paper_outcome"] == "WIN_TP1"
    assert row["edge_eligible"] is True
    assert row["realized_rr"] == 0.75


def test_parse_replay_record_no_trade():
    raw = _FAKE_RECORDS[2]
    row = parse_replay_record(raw, "2026-01-01T00:00:00Z")
    assert row is not None
    assert row["decision"] == "NO_TRADE"
    assert row["realized_rr"] is None
    assert row["edge_eligible"] is False


def test_parse_replay_record_malformed_returns_none():
    assert parse_replay_record({}, "2026-01-01T00:00:00Z") is None
    assert parse_replay_record({"scenario": {}}, "2026-01-01T00:00:00Z") is None


# ── Test 13: empty records ────────────────────────────────────────────────────

def test_build_empty_records():
    rows, summary = build_research_dataset("BTCUSDT", [])
    assert rows == []
    assert summary["export_stats"]["total_samples"] == 0
    assert summary["data_quality"]["level"] == "CRITICAL"
    assert summary["reason_codes"]


# ── Test 14: runner creates output files ──────────────────────────────────────

def test_runner_creates_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "EXPORTS_DIR", tmp / "exports")

        rows, summary = run_fake_sample("BTCUSDT")
        runner._write_outputs(rows, summary)

        assert (tmp / "exports" / "research_dataset.csv").exists()
        assert (tmp / "exports" / "research_dataset_summary.json").exists()

        data = json.loads(
            (tmp / "exports" / "research_dataset_summary.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == BLOCK_ID
        assert data["reason_codes"]
        assert "next_blocks" in data["feeds_next"]

        csv_text = (tmp / "exports" / "research_dataset.csv").read_text(encoding="utf-8")
        reader = list(csv.DictReader(io.StringIO(csv_text)))
        assert len(reader) == 3
        for f in EXPORT_FIELDS:
            assert f in reader[0], f"CSV missing field: {f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
