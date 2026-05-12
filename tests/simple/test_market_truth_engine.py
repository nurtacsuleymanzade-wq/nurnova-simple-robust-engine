"""Tests for S1 Official Market Truth Engine."""

from __future__ import annotations

import json
import pathlib

import pytest

from src.simple.market_truth_engine import build_truth, run_fake_sample, FEEDS_NEXT
import src.simple.run_s1_market_truth as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "market_truth", "official_candle", "price_truth",
    "consistency", "data_quality", "reason_codes", "feeds_next",
]


def test_fake_sample_contract_fields():
    truth = run_fake_sample("BTCUSDT")
    for field in _REQUIRED_TOP:
        assert field in truth, f"Missing top-level field: {field}"
    assert truth["block_id"] == "S1_OFFICIAL_MARKET_TRUTH"
    assert truth["symbol"] == "BTCUSDT"
    assert "source_mode" in truth["source"]
    for key in ("current_price", "official_close", "official_high", "official_low", "official_open", "official_volume", "official_candle_closed"):
        assert key in truth["market_truth"], f"market_truth missing: {key}"
    for key in ("open_time_utc", "close_time_utc", "open", "high", "low", "close", "volume"):
        assert key in truth["official_candle"], f"official_candle missing: {key}"
    for key in ("best_bid", "best_ask", "mid_price", "spread", "spread_pct"):
        assert key in truth["price_truth"], f"price_truth missing: {key}"
    for key in ("close_vs_mid_diff", "close_vs_mid_diff_pct", "consistency_label"):
        assert key in truth["consistency"], f"consistency missing: {key}"


def test_reason_codes_not_empty():
    truth = run_fake_sample("BTCUSDT")
    assert truth["reason_codes"], "reason_codes must not be empty"
    assert isinstance(truth["reason_codes"], list)
    assert len(truth["reason_codes"]) >= 1


def test_feeds_next_includes_s2():
    truth = run_fake_sample("BTCUSDT")
    next_blocks = truth["feeds_next"]["next_blocks"]
    assert "S2_LIGHTWEIGHT_1S_EVIDENCE" in next_blocks


def test_spread_pct_calculated_correctly():
    truth = run_fake_sample("BTCUSDT")
    pt = truth["price_truth"]
    bid, ask = pt["best_bid"], pt["best_ask"]
    mid = (bid + ask) / 2.0
    expected = round((ask - bid) / mid * 100, 6)
    assert abs(pt["spread_pct"] - expected) < 1e-4


def test_consistency_label_consistent():
    # close=105000, mid=(104990+105010)/2=105000 → diff=0 → CONSISTENT
    truth = run_fake_sample("BTCUSDT")
    assert truth["consistency"]["consistency_label"] == "CONSISTENT"


def test_consistency_label_major_mismatch():
    candle = {
        "open": 104700.0, "high": 105500.0, "low": 104200.0,
        "close": 105000.0, "volume": 12.0,
        "open_time_ms": 1746835200000, "close_time_ms": 1746835259999,
    }
    ticker = {"best_bid": 103000.0, "best_ask": 103100.0}
    truth = build_truth("BTCUSDT", candle, ticker, "PUBLIC_REST")
    assert truth["consistency"]["consistency_label"] == "MAJOR_MISMATCH"


def test_missing_price_produces_invalid_no_crash():
    truth = build_truth("BTCUSDT", None, None, "NO_DATA")
    assert truth["data_quality"]["level"] == "INVALID"
    assert truth["reason_codes"]  # not empty
    assert truth["market_truth"]["current_price"] is None


def test_runner_creates_all_output_files(monkeypatch):
    import shutil
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        truth = run_fake_sample("BTCUSDT")
        runner._write_outputs(truth)

        assert (tmp / "state" / "latest_market_truth.json").exists()
        assert (tmp / "state" / "s1_market_truth_state.json").exists()
        assert (tmp / "data" / "market_truth.jsonl").exists()
        assert (tmp / "reports" / "s1_market_truth_latest_report.md").exists()

        data = json.loads((tmp / "state" / "latest_market_truth.json").read_text())
        assert data["block_id"] == "S1_OFFICIAL_MARKET_TRUTH"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
