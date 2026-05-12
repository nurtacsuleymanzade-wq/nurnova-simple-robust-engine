"""Tests for S9 Edge Stats Engine."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.edge_stats_engine import (
    build_edge_stats,
    run_fake_sample,
    parse_s8_record,
    _compute_stats,
    _FAKE_RECORDS,
    FEEDS_NEXT,
)
import src.simple.run_s9_edge_stats as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "sample_info",
    "edge_eligible_count", "win_count", "loss_count",
    "win_rate", "avg_rr_realized", "edge_score",
    "data_quality", "reason_codes", "feeds_next",
]

_REQUIRED_SAMPLE_INFO = ["total_records_read", "edge_eligible_count", "excluded_count"]
_REQUIRED_DATA_QUALITY = ["score", "level", "issues"]


# ── Test 1: fake sample creates all required contract fields ──────────────────

def test_fake_sample_all_required_top_fields():
    es = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_TOP:
        assert f in es, f"Missing top-level field: {f}"
    assert es["block_id"] == "S9_EDGE_STATS"
    assert es["symbol"] == "BTCUSDT"


def test_fake_sample_nested_fields():
    es = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_SAMPLE_INFO:
        assert f in es["sample_info"], f"sample_info missing: {f}"
    for f in _REQUIRED_DATA_QUALITY:
        assert f in es["data_quality"], f"data_quality missing: {f}"


# ── Test 2: reason_codes are not empty ───────────────────────────────────────

def test_reason_codes_not_empty():
    es = run_fake_sample("BTCUSDT")
    assert isinstance(es["reason_codes"], list)
    assert len(es["reason_codes"]) >= 1
    assert all(isinstance(c, str) for c in es["reason_codes"])


# ── Test 3: feeds_next includes S10_SIMPLE_BRAIN ─────────────────────────────

def test_feeds_next_includes_s10():
    es = run_fake_sample("BTCUSDT")
    assert "S10_SIMPLE_BRAIN" in es["feeds_next"]["next_blocks"]


# ── Test 4: only edge_eligible=true trades counted ───────────────────────────

def test_only_edge_eligible_counted():
    # _FAKE_RECORDS has 3 eligible + 2 excluded
    es = run_fake_sample("BTCUSDT")
    assert es["edge_eligible_count"] == 3
    assert es["sample_info"]["excluded_count"] == 2
    assert es["sample_info"]["total_records_read"] == 5


def test_non_eligible_records_excluded():
    records = [
        {"outcome": "AMBIGUOUS",  "realized_rr": None,  "edge_eligible": False},
        {"outcome": "NOT_OPENED", "realized_rr": None,  "edge_eligible": False},
        {"outcome": "INVALID",    "realized_rr": None,  "edge_eligible": False},
        {"outcome": "OPEN",       "realized_rr": None,  "edge_eligible": False},
    ]
    es = build_edge_stats("BTCUSDT", records, "TEST")
    assert es["edge_eligible_count"] == 0
    assert es["win_count"] == 0
    assert es["loss_count"] == 0


# ── Test 5: win_rate = win_count / edge_eligible_count (or null if 0) ─────────

def test_win_rate_correct():
    es = run_fake_sample("BTCUSDT")
    expected = round(2 / 3, 4)
    assert es["win_rate"] == expected


def test_win_rate_null_when_no_eligible():
    es = build_edge_stats("BTCUSDT", [], "TEST")
    assert es["win_rate"] is None


def test_win_rate_zero_when_all_losses():
    records = [
        {"outcome": "LOSS", "realized_rr": -1.0, "edge_eligible": True},
        {"outcome": "LOSS", "realized_rr": -1.0, "edge_eligible": True},
    ]
    es = build_edge_stats("BTCUSDT", records, "TEST")
    assert es["win_rate"] == 0.0
    assert es["win_count"] == 0
    assert es["loss_count"] == 2


# ── Test 6: avg_rr_realized correct ──────────────────────────────────────────

def test_avg_rr_realized_correct():
    # (0.625 + -1.0 + 2.0) / 3 = 1.625 / 3
    es = run_fake_sample("BTCUSDT")
    expected = round((0.625 + (-1.0) + 2.0) / 3, 4)
    assert es["avg_rr_realized"] == expected


def test_avg_rr_realized_null_when_no_eligible():
    es = build_edge_stats("BTCUSDT", [], "TEST")
    assert es["avg_rr_realized"] is None


# ── Test 7: edge_score computation or null ────────────────────────────────────

def test_edge_score_not_null_when_data_available():
    es = run_fake_sample("BTCUSDT")
    assert es["edge_score"] is not None
    expected = round(es["win_rate"] * es["avg_rr_realized"], 4)
    assert es["edge_score"] == expected


def test_edge_score_null_when_no_eligible():
    es = build_edge_stats("BTCUSDT", [], "TEST")
    assert es["edge_score"] is None


# ── Test 8: no eligible trades → null stats ───────────────────────────────────

def test_no_eligible_trades_produces_null_stats():
    es = build_edge_stats("BTCUSDT", [], "TEST")
    assert es["edge_eligible_count"] == 0
    assert es["win_count"] == 0
    assert es["loss_count"] == 0
    assert es["win_rate"] is None
    assert es["avg_rr_realized"] is None
    assert es["edge_score"] is None
    assert es["data_quality"]["level"] == "CRITICAL"


# ── Test 9: excluded outcomes not counted ─────────────────────────────────────

def test_ambiguous_not_counted_as_win_or_loss():
    records = [
        {"outcome": "WIN_TP1",   "realized_rr": 1.0,  "edge_eligible": True},
        {"outcome": "AMBIGUOUS", "realized_rr": None,  "edge_eligible": False},
    ]
    es = build_edge_stats("BTCUSDT", records, "TEST")
    assert es["edge_eligible_count"] == 1
    assert es["win_count"] == 1
    assert es["loss_count"] == 0


# ── Test 10: win_count and loss_count correct ─────────────────────────────────

def test_win_count_and_loss_count():
    records = [
        {"outcome": "WIN_TP1", "realized_rr": 0.5,  "edge_eligible": True},
        {"outcome": "WIN_TP2", "realized_rr": 2.0,  "edge_eligible": True},
        {"outcome": "LOSS",    "realized_rr": -1.0, "edge_eligible": True},
        {"outcome": "LOSS",    "realized_rr": -1.0, "edge_eligible": True},
    ]
    es = build_edge_stats("BTCUSDT", records, "TEST")
    assert es["win_count"] == 2
    assert es["loss_count"] == 2
    assert es["edge_eligible_count"] == 4
    assert es["win_rate"] == 0.5


# ── Test 11: runner creates all output files ──────────────────────────────────

def test_runner_creates_all_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        es = run_fake_sample("BTCUSDT")
        runner._write_outputs(es)

        assert (tmp / "state" / "latest_edge_stats.json").exists()
        assert (tmp / "state" / "s9_edge_stats_state.json").exists()
        assert (tmp / "reports" / "s9_edge_stats_latest_report.md").exists()

        data = json.loads(
            (tmp / "state" / "latest_edge_stats.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == "S9_EDGE_STATS"
        assert data["reason_codes"]
        assert "S10_SIMPLE_BRAIN" in data["feeds_next"]["next_blocks"]
        assert "edge_eligible_count" in data
        assert "win_rate" in data
        assert "avg_rr_realized" in data
        assert "edge_score" in data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── parse_s8_record unit tests ────────────────────────────────────────────────

def test_parse_s8_record_eligible():
    raw = {
        "result": {"outcome": "WIN_TP1", "realized_rr": 0.625},
        "edge_eligibility": {"edge_eligible": True},
    }
    parsed = parse_s8_record(raw)
    assert parsed is not None
    assert parsed["outcome"] == "WIN_TP1"
    assert parsed["realized_rr"] == 0.625
    assert parsed["edge_eligible"] is True


def test_parse_s8_record_not_eligible():
    raw = {
        "result": {"outcome": "AMBIGUOUS", "realized_rr": None},
        "edge_eligibility": {"edge_eligible": False},
    }
    parsed = parse_s8_record(raw)
    assert parsed is not None
    assert parsed["edge_eligible"] is False


def test_parse_s8_record_malformed_returns_none():
    assert parse_s8_record({}) is None
    assert parse_s8_record({"result": {}}) is None


# ── data_quality level tests ──────────────────────────────────────────────────

def test_data_quality_critical_when_no_eligible():
    es = build_edge_stats("BTCUSDT", [], "TEST")
    assert es["data_quality"]["level"] == "CRITICAL"
    assert es["data_quality"]["score"] == 0.0


def test_data_quality_low_when_small_sample():
    records = [{"outcome": "WIN_TP1", "realized_rr": 1.0, "edge_eligible": True}]
    es = build_edge_stats("BTCUSDT", records, "TEST")
    assert es["data_quality"]["level"] == "LOW"


def test_data_quality_medium_when_moderate_sample():
    records = [
        {"outcome": "WIN_TP1", "realized_rr": 1.0, "edge_eligible": True}
    ] * 15
    es = build_edge_stats("BTCUSDT", records, "TEST")
    assert es["data_quality"]["level"] == "MEDIUM"


def test_data_quality_high_when_large_sample():
    records = [
        {"outcome": "WIN_TP1", "realized_rr": 1.0, "edge_eligible": True}
    ] * 30
    es = build_edge_stats("BTCUSDT", records, "TEST")
    assert es["data_quality"]["level"] == "HIGH"
