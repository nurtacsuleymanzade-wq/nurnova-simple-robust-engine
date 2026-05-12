"""Tests for S11.5 VPS Observer, Binance Public Feed, and Health Monitor."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.simple.binance_public_feed import fetch_latest_closed_1m_candle, fetch_book_ticker
from src.simple.vps_health_monitor import write_heartbeat, read_heartbeat, _status_from_errors
from src.simple.vps_observer import run_one_cycle, _append_jsonl, _seconds_to_next_minute

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_KLINES_RESPONSE = [
    [
        1746835200000, "104700.0", "105500.0", "104200.0", "105000.0",
        "12.543", 1746835259999, "1314990.01", 100, "8.0", "839200.0", "0",
    ],
    [
        1746835260000, "105000.0", "105100.0", "104900.0", "105050.0",
        "5.0", 1746835319999, "524750.0", 50, "3.0", "314550.0", "0",
    ],
]

_FAKE_BOOK_TICKER = {"symbol": "BTCUSDT", "bidPrice": "104990.0", "askPrice": "105010.0"}

_FAKE_CANDLE = {
    "open_time_ms": 1746835200000,
    "open": 104700.0,
    "high": 105500.0,
    "low": 104200.0,
    "close": 105000.0,
    "volume": 12.543,
    "close_time_ms": 1746835259999,
}

_FAKE_TICKER = {"best_bid": 104990.0, "best_ask": 105010.0}


def _mock_urlopen(response_data):
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(response_data).encode()
    return mock_resp


def _tmp() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


# ---------------------------------------------------------------------------
# binance_public_feed
# ---------------------------------------------------------------------------

class TestBinancePublicFeed:
    def test_fetch_candle_returns_expected_fields(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(_FAKE_KLINES_RESPONSE)):
            candle = fetch_latest_closed_1m_candle("BTCUSDT")
        assert candle is not None
        for field in ("open_time_ms", "open", "high", "low", "close", "volume", "close_time_ms"):
            assert field in candle, f"Missing field: {field}"
        assert candle["open"] == 104700.0
        assert candle["high"] == 105500.0
        assert candle["close"] == 105000.0

    def test_fetch_candle_returns_none_on_network_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            candle = fetch_latest_closed_1m_candle("BTCUSDT")
        assert candle is None

    def test_fetch_book_ticker_returns_expected_fields(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(_FAKE_BOOK_TICKER)):
            ticker = fetch_book_ticker("BTCUSDT")
        assert ticker is not None
        assert "best_bid" in ticker
        assert "best_ask" in ticker
        assert ticker["best_bid"] == 104990.0
        assert ticker["best_ask"] == 105010.0

    def test_fetch_book_ticker_returns_none_on_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            ticker = fetch_book_ticker("BTCUSDT")
        assert ticker is None


# ---------------------------------------------------------------------------
# vps_health_monitor
# ---------------------------------------------------------------------------

class TestVpsHealthMonitor:
    def test_write_and_read_heartbeat(self):
        d = _tmp()
        try:
            import src.simple.vps_health_monitor as hm
            orig_state, orig_hb = hm._STATE_DIR, hm._HEARTBEAT_FILE
            hm._STATE_DIR = d
            hm._HEARTBEAT_FILE = d / "vps_heartbeat.json"
            write_heartbeat(cycle_count=5, consecutive_errors=0, last_error=None)
            hm._STATE_DIR = orig_state
            hm._HEARTBEAT_FILE = orig_hb
            hb = json.loads((d / "vps_heartbeat.json").read_text())
            assert isinstance(hb, dict)
            assert hb["cycle_count"] == 5
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_write_heartbeat_safety_invariants(self):
        d = _tmp()
        try:
            import src.simple.vps_health_monitor as hm
            orig_state, orig_hb = hm._STATE_DIR, hm._HEARTBEAT_FILE
            hm._STATE_DIR = d
            hm._HEARTBEAT_FILE = d / "vps_heartbeat.json"
            write_heartbeat(cycle_count=1, consecutive_errors=0, last_error=None)
            hm._STATE_DIR = orig_state
            hm._HEARTBEAT_FILE = orig_hb
            hb = json.loads((d / "vps_heartbeat.json").read_text())
            assert hb["safe_to_open_real_trade"] is False
            assert hb["private_api_used"] is False
            assert hb["live_order_sent"] is False
            assert hb["SAFETY_INVARIANTS_VERIFIED"] is True
            assert hb["observation_mode"] is True
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_status_thresholds(self):
        assert _status_from_errors(0) == "OK"
        assert _status_from_errors(1) == "RECOVERING"
        assert _status_from_errors(3) == "WARNING"
        assert _status_from_errors(10) == "DEGRADED"
        assert _status_from_errors(20) == "DEGRADED"

    def test_write_heartbeat_never_raises_on_bad_path(self):
        import src.simple.vps_health_monitor as hm
        orig_state, orig_hb = hm._STATE_DIR, hm._HEARTBEAT_FILE
        hm._STATE_DIR = pathlib.Path("/nonexistent/path/abc")
        hm._HEARTBEAT_FILE = pathlib.Path("/nonexistent/path/abc/hb.json")
        write_heartbeat(cycle_count=1, consecutive_errors=0, last_error=None)
        hm._STATE_DIR = orig_state
        hm._HEARTBEAT_FILE = orig_hb


# ---------------------------------------------------------------------------
# vps_observer
# ---------------------------------------------------------------------------

class TestVpsObserver:
    def test_append_jsonl_creates_file(self):
        d = _tmp()
        try:
            target = d / "sub" / "out.jsonl"
            _append_jsonl(target, {"key": "val"})
            assert target.exists()
            lines = target.read_text().splitlines()
            assert len(lines) == 1
            assert json.loads(lines[0])["key"] == "val"
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_append_jsonl_is_append_only(self):
        d = _tmp()
        try:
            target = d / "out.jsonl"
            _append_jsonl(target, {"n": 1})
            _append_jsonl(target, {"n": 2})
            lines = target.read_text().splitlines()
            assert len(lines) == 2
            assert json.loads(lines[0])["n"] == 1
            assert json.loads(lines[1])["n"] == 2
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_seconds_to_next_minute_in_range(self):
        s = _seconds_to_next_minute()
        assert 0.0 <= s <= 60.0

    def _patch_observer_paths(self, obs, d):
        obs._DATA_DIR = d
        obs._OBSERVATIONS_FILE = d / "live_observations.jsonl"
        obs._RAW_FEED_FILE = d / "live_feed_raw.jsonl"

    def test_run_one_cycle_contract_fields(self):
        d = _tmp()
        try:
            import src.simple.vps_observer as obs
            orig_data, orig_obs, orig_raw = obs._DATA_DIR, obs._OBSERVATIONS_FILE, obs._RAW_FEED_FILE
            self._patch_observer_paths(obs, d)

            with patch("src.simple.vps_observer.fetch_latest_closed_1m_candle", return_value=_FAKE_CANDLE), \
                 patch("src.simple.vps_observer.fetch_book_ticker", return_value=_FAKE_TICKER), \
                 patch("src.simple.vps_observer.write_heartbeat"):
                result = run_one_cycle("BTCUSDT", cycle_count=1)

            obs._DATA_DIR, obs._OBSERVATIONS_FILE, obs._RAW_FEED_FILE = orig_data, orig_obs, orig_raw

            for field in ("timestamp_utc", "block_id", "symbol", "cycle", "source",
                          "s1_market_truth", "s2_evidence", "data_quality",
                          "reason_codes", "feeds_next", "execution_safety"):
                assert field in result, f"Missing field: {field}"

            assert result["execution_safety"]["safe_to_open_real_trade"] is False
            assert result["execution_safety"]["private_api_used"] is False
            assert result["execution_safety"]["live_order_sent"] is False
            assert result["reason_codes"], "reason_codes must not be empty"
            assert "SAFE_TO_OPEN_REAL_TRADE_FALSE" in result["reason_codes"]
            assert "OBSERVATION_MODE" in result["reason_codes"]
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_run_one_cycle_with_no_candle(self):
        d = _tmp()
        try:
            import src.simple.vps_observer as obs
            orig_data, orig_obs, orig_raw = obs._DATA_DIR, obs._OBSERVATIONS_FILE, obs._RAW_FEED_FILE
            self._patch_observer_paths(obs, d)

            with patch("src.simple.vps_observer.fetch_latest_closed_1m_candle", return_value=None), \
                 patch("src.simple.vps_observer.fetch_book_ticker", return_value=None), \
                 patch("src.simple.vps_observer.write_heartbeat"):
                result = run_one_cycle("BTCUSDT", cycle_count=2)

            obs._DATA_DIR, obs._OBSERVATIONS_FILE, obs._RAW_FEED_FILE = orig_data, orig_obs, orig_raw

            assert result["source"]["candle_available"] is False
            assert result["execution_safety"]["safe_to_open_real_trade"] is False
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_run_one_cycle_appends_to_jsonl(self):
        d = _tmp()
        try:
            import src.simple.vps_observer as obs
            orig_data, orig_obs, orig_raw = obs._DATA_DIR, obs._OBSERVATIONS_FILE, obs._RAW_FEED_FILE
            self._patch_observer_paths(obs, d)

            with patch("src.simple.vps_observer.fetch_latest_closed_1m_candle", return_value=None), \
                 patch("src.simple.vps_observer.fetch_book_ticker", return_value=None), \
                 patch("src.simple.vps_observer.write_heartbeat"):
                run_one_cycle("BTCUSDT", cycle_count=1)
                run_one_cycle("BTCUSDT", cycle_count=2)

            obs_file = d / "live_observations.jsonl"
            obs._DATA_DIR, obs._OBSERVATIONS_FILE, obs._RAW_FEED_FILE = orig_data, orig_obs, orig_raw

            lines = obs_file.read_text().splitlines()
            assert len(lines) == 2
            assert json.loads(lines[0])["cycle"] == 1
            assert json.loads(lines[1])["cycle"] == 2
        finally:
            shutil.rmtree(d, ignore_errors=True)
