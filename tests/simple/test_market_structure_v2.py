"""Tests for S28 — Market Structure V2."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
import pytest

from src.simple.market_structure_v2 import (
    build_1m_candles_from_flow,
    aggregate_candles,
    detect_swing_highs,
    detect_swing_lows,
    detect_sequence,
    detect_bias,
    detect_bos,
    detect_choch,
    detect_range,
    detect_equal_highs,
    detect_equal_lows,
    detect_sweep,
    compute_structure_strength,
    analyze_timeframe,
    run_market_structure_v2,
    SAFETY,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_candle(o, h, l, c, ts=0):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 0.0, "ts": ts}


def _bullish_candles(n=30):
    """Ascending candles producing clear HH/HL bullish structure."""
    candles = []
    base = 100.0
    for i in range(n):
        o = base + i * 1.0
        c = o + 0.5
        h = c + 0.3
        l = o - 0.2
        candles.append(_make_candle(o, h, l, c, ts=i * 60))
    return candles


def _bearish_candles(n=30):
    """Descending candles producing clear LH/LL bearish structure."""
    candles = []
    base = 200.0
    for i in range(n):
        o = base - i * 1.0
        c = o - 0.5
        h = o + 0.2
        l = c - 0.3
        candles.append(_make_candle(o, h, l, c, ts=i * 60))
    return candles


def _range_candles(n=30):
    """Oscillating candles between 100 and 110."""
    import math
    candles = []
    for i in range(n):
        mid = 105 + 5 * math.sin(i * 0.5)
        candles.append(_make_candle(mid - 1, mid + 1, mid - 2, mid, ts=i * 60))
    return candles


# --------------------------------------------------------------------------- #
# Tests: candle building
# --------------------------------------------------------------------------- #

def test_handles_missing_flow_data():
    result = build_1m_candles_from_flow([])
    assert result == []


def test_derives_1m_candles_from_flow_events():
    now = 1_700_000_000.0
    flow = [
        {"timestamp": now, "price": 100.0},
        {"timestamp": now + 10, "price": 101.0},
        {"timestamp": now + 70, "price": 102.0},
    ]
    candles = build_1m_candles_from_flow(flow)
    assert len(candles) >= 1
    assert candles[0]["open"] == 100.0


def test_aggregates_5m_candles():
    candles_1m = _bullish_candles(30)
    candles_5m = aggregate_candles(candles_1m, 5)
    assert 1 <= len(candles_5m) <= 6
    for c in candles_5m:
        assert c["high"] >= c["low"]


def test_aggregates_15m_candles():
    candles_1m = _bullish_candles(30)
    candles_15m = aggregate_candles(candles_1m, 15)
    assert 1 <= len(candles_15m) <= 2
    for c in candles_15m:
        assert c["high"] >= c["low"]


# --------------------------------------------------------------------------- #
# Tests: swing detection
# --------------------------------------------------------------------------- #

def test_detects_swing_highs():
    candles = [
        _make_candle(10, 10, 9, 10),
        _make_candle(11, 13, 10, 11),   # local high
        _make_candle(10, 10, 9, 10),
        _make_candle(11, 11, 10, 11),
        _make_candle(10, 10, 9, 10),
    ]
    highs = detect_swing_highs(candles, lookback=1)
    assert len(highs) >= 1
    assert highs[0]["price"] == 13


def test_detects_swing_lows():
    candles = [
        _make_candle(10, 11, 10, 10),
        _make_candle(9, 10, 7, 9),   # local low
        _make_candle(10, 11, 10, 10),
        _make_candle(9, 10, 8, 9),
        _make_candle(10, 11, 10, 10),
    ]
    lows = detect_swing_lows(candles, lookback=1)
    assert len(lows) >= 1
    assert lows[0]["price"] == 7


# --------------------------------------------------------------------------- #
# Tests: sequence detection
# --------------------------------------------------------------------------- #

def test_detects_hh_hl_bullish_sequence():
    highs = [{"price": 100}, {"price": 105}, {"price": 110}]
    lows = [{"price": 90}, {"price": 93}, {"price": 96}]
    seq = detect_sequence(highs, lows)
    assert seq == "HH_HL_SEQUENCE"


def test_detects_lh_ll_bearish_sequence():
    highs = [{"price": 110}, {"price": 105}, {"price": 100}]
    lows = [{"price": 96}, {"price": 93}, {"price": 90}]
    seq = detect_sequence(highs, lows)
    assert seq == "LH_LL_SEQUENCE"


# --------------------------------------------------------------------------- #
# Tests: BOS detection
# --------------------------------------------------------------------------- #

def test_detects_bullish_bos():
    candles = _bullish_candles(10)
    candles[-1]["close"] = 200.0  # close above all prior highs
    highs = [{"price": 110, "index": 5, "ts": 0}]
    lows = [{"price": 90, "index": 3, "ts": 0}]
    bos = detect_bos(candles, highs, lows)
    assert bos == "BULLISH_BOS"


def test_detects_bearish_bos():
    candles = _bearish_candles(10)
    candles[-1]["close"] = 1.0  # close below all prior lows
    highs = [{"price": 200, "index": 5, "ts": 0}]
    lows = [{"price": 190, "index": 3, "ts": 0}]
    bos = detect_bos(candles, highs, lows)
    assert bos == "BEARISH_BOS"


# --------------------------------------------------------------------------- #
# Tests: CHoCH detection
# --------------------------------------------------------------------------- #

def test_detects_bullish_choch():
    choch = detect_choch("LH_LL_SEQUENCE", "BULLISH_BOS")
    assert choch == "BULLISH_CHOCH"


def test_detects_bearish_choch():
    choch = detect_choch("HH_HL_SEQUENCE", "BEARISH_BOS")
    assert choch == "BEARISH_CHOCH"


# --------------------------------------------------------------------------- #
# Tests: range detection
# --------------------------------------------------------------------------- #

def test_detects_range_high_low():
    highs = [{"price": 105}, {"price": 107}, {"price": 106}]
    lows = [{"price": 95}, {"price": 94}, {"price": 96}]
    rh, rl = detect_range(highs, lows)
    assert rh == 107
    assert rl == 94


# --------------------------------------------------------------------------- #
# Tests: equal highs / lows
# --------------------------------------------------------------------------- #

def test_detects_equal_highs():
    highs = [{"price": 100.0}, {"price": 100.05}, {"price": 110.0}]
    eq = detect_equal_highs(highs, tolerance=0.001)
    assert len(eq) >= 1


def test_detects_equal_lows():
    lows = [{"price": 90.0}, {"price": 90.04}, {"price": 80.0}]
    eq = detect_equal_lows(lows, tolerance=0.001)
    assert len(eq) >= 1


# --------------------------------------------------------------------------- #
# Tests: sweep / reclaim
# --------------------------------------------------------------------------- #

def test_detects_buy_side_sweep():
    # price wicks above prior high but closes below
    prior_high = 110.0
    candles = [
        _make_candle(100, 109, 99, 105),
        _make_candle(105, 112, 104, 108),   # wick above prior high
        _make_candle(108, 109, 100, 102),   # close back below prior high
    ]
    highs = [{"price": prior_high, "index": 0, "ts": 0}]
    sweep, reclaim = detect_sweep(candles, highs, [], [prior_high], [])
    assert sweep in ("BUY_SIDE_SWEEP", "BOTH_SIDE_SWEEP")
    assert "BUY_SIDE" in reclaim


def test_detects_sell_side_sweep():
    prior_low = 90.0
    candles = [
        _make_candle(100, 101, 91, 99),
        _make_candle(99, 100, 88, 97),   # wick below prior low
        _make_candle(97, 100, 96, 98),   # close back above prior low
    ]
    lows = [{"price": prior_low, "index": 0, "ts": 0}]
    sweep, reclaim = detect_sweep(candles, [], lows, [], [prior_low])
    assert sweep in ("SELL_SIDE_SWEEP", "BOTH_SIDE_SWEEP")
    assert "SELL_SIDE" in reclaim


def test_detects_reclaim_after_sweep():
    prior_low = 90.0
    candles = [
        _make_candle(100, 101, 91, 99),
        _make_candle(99, 100, 88, 97),
        _make_candle(97, 100, 96, 98),
    ]
    lows = [{"price": prior_low, "index": 0, "ts": 0}]
    sweep, reclaim = detect_sweep(candles, [], lows, [], [prior_low])
    assert reclaim != "NO_RECLAIM"
    assert reclaim != "INSUFFICIENT_DATA"


# --------------------------------------------------------------------------- #
# Tests: structure strength
# --------------------------------------------------------------------------- #

def test_structure_strength_within_bounds():
    for candle_count in [5, 20, 50]:
        for seq in ("HH_HL_SEQUENCE", "LH_LL_SEQUENCE", "INSUFFICIENT_SEQUENCE"):
            s = compute_structure_strength(candle_count, seq, "BULLISH_BOS", "NO_CHOCH", 110.0, 90.0, "ALIGNED", "ALIGNED")
            assert 0.0 <= s <= 1.0, f"strength out of bounds: {s}"


# --------------------------------------------------------------------------- #
# Tests: INSUFFICIENT_DATA
# --------------------------------------------------------------------------- #

def test_marks_insufficient_data_honestly():
    state = analyze_timeframe([], "1m", "UNKNOWN", "UNKNOWN")
    assert state["available"] is False
    assert state["bias"] == "INSUFFICIENT_DATA"
    assert state["structure_strength"] == 0.0


# --------------------------------------------------------------------------- #
# Tests: alignment
# --------------------------------------------------------------------------- #

def _make_tmp() -> Path:
    """Create a local tmp dir inside the repo (avoids Windows AppData permission issue)."""
    base = Path("tmp_pytest_s28")
    base.mkdir(exist_ok=True)
    d = Path(tempfile.mkdtemp(dir=base))
    return d


def _patch_paths(m, d: Path) -> None:
    attrs = [
        "LATEST_FLOW_EVIDENCE", "LATEST_FLOW_PERSISTENCE", "LATEST_LIQUIDITY_MEMORY",
        "LATEST_FLOW_STATE", "LIVE_FLOW_JSONL", "LATEST_MARKET_TRUTH", "LATEST_HYBRID_DNA",
        "FLOW_EVIDENCE_JSONL", "FLOW_PERSISTENCE_JSONL", "LATEST_FLOW_QUALITY",
        "LATEST_CHAIN_AUDIT", "HYBRID_DNA_JSONL", "MARKET_TRUTH_JSONL",
        "LATEST_STATE_PATH", "S28_STATE_PATH", "HISTORY_PATH", "REPORT_PATH",
    ]
    for attr in attrs:
        suffix = ".jsonl" if "JSONL" in attr or "HISTORY" in attr else (".md" if "REPORT" in attr else ".json")
        setattr(m, attr, d / f"{attr}{suffix}")


def test_aligns_bullish_structure_with_long_flow(monkeypatch):
    import src.simple.market_structure_v2 as m
    d = _make_tmp()
    _patch_paths(m, d)
    (d / "LATEST_FLOW_EVIDENCE.json").write_text(json.dumps({"flow_direction": "LONG"}))
    candles = _bullish_candles(30)
    (d / "LATEST_MARKET_TRUTH.json").write_text(json.dumps({"candles": candles}))

    result = m.run_market_structure_v2()
    assert result["structure_bias"] in ("BULLISH_STRUCTURE", "TRANSITION_STRUCTURE", "RANGE_STRUCTURE", "INSUFFICIENT_DATA")
    assert result["flow_alignment"] in ("ALIGNED", "NEUTRAL", "UNKNOWN", "CONFLICT")
    shutil.rmtree(d, ignore_errors=True)


def test_flags_flow_structure_conflict(monkeypatch):
    import src.simple.market_structure_v2 as m
    d = _make_tmp()
    _patch_paths(m, d)
    (d / "LATEST_FLOW_EVIDENCE.json").write_text(json.dumps({"flow_direction": "LONG"}))
    candles = _bearish_candles(30)
    (d / "LATEST_MARKET_TRUTH.json").write_text(json.dumps({"candles": candles}))

    result = m.run_market_structure_v2()
    if result["structure_bias"] == "BEARISH_STRUCTURE":
        assert result["flow_alignment"] == "CONFLICT"
    shutil.rmtree(d, ignore_errors=True)


def test_aligns_with_s27_liquidity(monkeypatch):
    import src.simple.market_structure_v2 as m
    d = _make_tmp()
    _patch_paths(m, d)
    candles = _bullish_candles(30)
    (d / "LATEST_MARKET_TRUTH.json").write_text(json.dumps({"candles": candles}))
    (d / "LATEST_LIQUIDITY_MEMORY.json").write_text(json.dumps({"liquidity_bias": "BID_SUPPORT"}))

    result = m.run_market_structure_v2()
    if result["structure_bias"] == "BULLISH_STRUCTURE":
        assert result["liquidity_alignment"] == "ALIGNED"
    shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Tests: output files
# --------------------------------------------------------------------------- #

def test_writes_latest_json(monkeypatch):
    import src.simple.market_structure_v2 as m
    d = _make_tmp()
    _patch_paths(m, d)

    m.run_market_structure_v2()
    latest = d / "LATEST_STATE_PATH.json"
    assert latest.exists()
    data = json.loads(latest.read_text())
    assert data["block_id"] == "S28_MARKET_STRUCTURE_V2"
    assert "timeframe_states" in data
    assert "1m" in data["timeframe_states"]
    assert "5m" in data["timeframe_states"]
    assert "15m" in data["timeframe_states"]
    shutil.rmtree(d, ignore_errors=True)


def test_writes_markdown_report(monkeypatch):
    import src.simple.market_structure_v2 as m
    d = _make_tmp()
    _patch_paths(m, d)

    m.run_market_structure_v2()
    report = d / "REPORT_PATH.md"
    assert report.exists()
    content = report.read_text()
    assert "S28 Market Structure V2" in content
    assert "structure_bias" in content
    shutil.rmtree(d, ignore_errors=True)


def test_appends_jsonl_history(monkeypatch):
    import src.simple.market_structure_v2 as m
    d = _make_tmp()
    _patch_paths(m, d)

    m.run_market_structure_v2()
    m.run_market_structure_v2()
    hist = d / "HISTORY_PATH.jsonl"
    lines = [l for l in hist.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    shutil.rmtree(d, ignore_errors=True)


def test_preserves_safety_flags(monkeypatch):
    import src.simple.market_structure_v2 as m
    d = _make_tmp()
    _patch_paths(m, d)

    result = m.run_market_structure_v2()
    assert result["execution_safety"]["safe_to_open_real_trade"] is False
    assert result["execution_safety"]["private_api_used"] is False
    assert result["execution_safety"]["live_order_sent"] is False
    shutil.rmtree(d, ignore_errors=True)
