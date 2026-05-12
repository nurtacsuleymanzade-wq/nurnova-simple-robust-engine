"""Tests for S8 Paper Outcome Tracker."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.paper_outcome_tracker import (
    build_paper_outcome,
    run_fake_sample,
    _calc_outcome,
    _FAKE_S1,
    _FAKE_S7,
    FEEDS_NEXT,
)
import src.simple.run_s8_paper_outcome as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "input_status", "decision_reference", "outcome_check",
    "lifecycle", "result", "edge_eligibility",
    "execution_safety", "data_quality",
    "reason_codes", "feeds_next",
]

_REQUIRED_INPUT_STATUS = [
    "market_truth_available", "decision_available", "missing_inputs",
]

_REQUIRED_DECISION_REF = [
    "decision", "paper_eligible", "edge_eligible_if_outcome_closes",
    "trade_direction", "entry_price", "stop_loss", "tp1", "tp2",
    "rr_tp1", "rr_tp2",
]

_REQUIRED_OUTCOME_CHECK = [
    "official_high", "official_low", "official_close", "check_method",
]

_REQUIRED_LIFECYCLE = [
    "trade_opened", "trade_status",
]

_REQUIRED_RESULT = [
    "outcome", "outcome_reason", "tp1_hit", "tp2_hit",
    "stop_hit", "ambiguous_hit", "realized_rr",
]

_REQUIRED_EDGE_ELIGIBILITY = [
    "edge_eligible", "feeds_edge_stats",
]

_REQUIRED_SAFETY = [
    "safe_to_open_real_trade", "private_api_used", "live_order_sent",
]

_FORBIDDEN_FIELDS = [
    "winrate", "expectancy", "edge_score", "edge_matrix",
    "win_count", "loss_count",
]


# --- Test 1: fake sample creates all required contract fields ---

def test_fake_sample_all_required_top_fields():
    po = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_TOP:
        assert f in po, f"Missing top-level field: {f}"
    assert po["block_id"] == "S8_PAPER_OUTCOME_TRACKER"
    assert po["symbol"] == "BTCUSDT"


def test_fake_sample_nested_fields():
    po = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_INPUT_STATUS:
        assert f in po["input_status"], f"input_status missing: {f}"
    for f in _REQUIRED_DECISION_REF:
        assert f in po["decision_reference"], f"decision_reference missing: {f}"
    for f in _REQUIRED_OUTCOME_CHECK:
        assert f in po["outcome_check"], f"outcome_check missing: {f}"
    for f in _REQUIRED_LIFECYCLE:
        assert f in po["lifecycle"], f"lifecycle missing: {f}"
    for f in _REQUIRED_RESULT:
        assert f in po["result"], f"result missing: {f}"
    for f in _REQUIRED_EDGE_ELIGIBILITY:
        assert f in po["edge_eligibility"], f"edge_eligibility missing: {f}"
    for f in _REQUIRED_SAFETY:
        assert f in po["execution_safety"], f"execution_safety missing: {f}"


# --- Test 2: reason_codes are not empty ---

def test_reason_codes_not_empty():
    po = run_fake_sample("BTCUSDT")
    assert isinstance(po["reason_codes"], list)
    assert len(po["reason_codes"]) >= 1
    assert all(isinstance(c, str) for c in po["reason_codes"])


# --- Test 3: feeds_next includes S9_EDGE_STATS ---

def test_feeds_next_includes_s9():
    po = run_fake_sample("BTCUSDT")
    assert "S9_EDGE_STATS" in po["feeds_next"]["next_blocks"]


# --- Test 4: check_method is OFFICIAL_CANDLE_HIGH_LOW ---

def test_check_method_always_official_candle_high_low():
    for po in [
        run_fake_sample("BTCUSDT"),
        build_paper_outcome("BTCUSDT", None, _FAKE_S7, "TEST"),
        build_paper_outcome("BTCUSDT", _FAKE_S1, None, "TEST"),
    ]:
        assert po["outcome_check"]["check_method"] == "OFFICIAL_CANDLE_HIGH_LOW"


# --- Test 5: safe_to_open_real_trade is false in every branch ---

def test_safe_to_open_real_trade_always_false():
    for po in [
        run_fake_sample("BTCUSDT"),
        build_paper_outcome("BTCUSDT", None, _FAKE_S7, "TEST"),
        build_paper_outcome("BTCUSDT", _FAKE_S1, None, "TEST"),
        build_paper_outcome("BTCUSDT", _FAKE_S1, _FAKE_S7, "TEST"),
    ]:
        assert po["execution_safety"]["safe_to_open_real_trade"] is False


# --- Test 6: private_api_used is false ---

def test_private_api_used_always_false():
    for po in [
        run_fake_sample("BTCUSDT"),
        build_paper_outcome("BTCUSDT", None, _FAKE_S7, "TEST"),
    ]:
        assert po["execution_safety"]["private_api_used"] is False


# --- Test 7: live_order_sent is false ---

def test_live_order_sent_always_false():
    for po in [
        run_fake_sample("BTCUSDT"),
        build_paper_outcome("BTCUSDT", _FAKE_S1, _FAKE_S7, "TEST"),
    ]:
        assert po["execution_safety"]["live_order_sent"] is False


# --- Test 8: non-ALLOW_PAPER decision produces NOT_OPENED ---

def test_not_opened_when_decision_block():
    s7_blocked = {**_FAKE_S7, "decision": "BLOCK", "paper_eligible": False}
    po = build_paper_outcome("BTCUSDT", _FAKE_S1, s7_blocked, "TEST")
    assert po["result"]["outcome"] == "NOT_OPENED"
    assert po["edge_eligibility"]["edge_eligible"] is False


def test_not_opened_when_paper_eligible_false():
    s7_watch = {**_FAKE_S7, "decision": "ALLOW_PAPER", "paper_eligible": False}
    oc = _calc_outcome(_FAKE_S1, s7_watch)
    assert oc["outcome"] == "NOT_OPENED"


# --- Test 9: LONG TP1/TP2/STOP detection works ---

def test_fake_sample_produces_win_tp1():
    # high=105600 >= tp1=105500 → tp1_hit; high < tp2=106600; low=104500 > stop=104200
    po = run_fake_sample("BTCUSDT")
    r = po["result"]
    assert r["outcome"] == "WIN_TP1"
    assert r["tp1_hit"] is True
    assert r["tp2_hit"] is False
    assert r["stop_hit"] is False
    assert r["ambiguous_hit"] is False
    assert r["realized_rr"] == 0.625
    assert "edge_eligible" not in r
    assert po["edge_eligibility"]["edge_eligible"] is True


def test_long_win_tp2():
    s1 = {**_FAKE_S1, "official_high": 107000.0, "official_low": 104500.0}
    oc = _calc_outcome(s1, _FAKE_S7)
    assert oc["outcome"] == "WIN_TP2"
    assert oc["tp1_hit"] is True
    assert oc["tp2_hit"] is True
    assert oc["stop_hit"] is False
    assert oc["edge_eligible"] is True
    assert oc["realized_rr"] == 2.0


def test_long_loss():
    s1 = {**_FAKE_S1, "official_high": 105100.0, "official_low": 104000.0}
    oc = _calc_outcome(s1, _FAKE_S7)
    assert oc["outcome"] == "LOSS"
    assert oc["stop_hit"] is True
    assert oc["tp1_hit"] is False
    assert oc["realized_rr"] == -1.0
    assert oc["edge_eligible"] is True


def test_long_open():
    s1 = {**_FAKE_S1, "official_high": 105200.0, "official_low": 104500.0}
    oc = _calc_outcome(s1, _FAKE_S7)
    assert oc["outcome"] == "OPEN"
    assert oc["tp1_hit"] is False
    assert oc["stop_hit"] is False
    assert oc["realized_rr"] is None
    assert oc["edge_eligible"] is False


# --- Test 10: SHORT TP1/TP2/STOP detection works ---

def test_short_win_tp1():
    s7_short = {
        **_FAKE_S7,
        "trade_direction": "SHORT",
        "entry_price": 105000.0,
        "stop_loss": 105500.0,
        "tp1": 104200.0,
        "tp2": 103400.0,
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
    }
    # low=104000 <= tp1=104200 → tp1_hit; low=104000 > tp2=103400 → not tp2; high=105200 < stop=105500 → not stop
    s1 = {**_FAKE_S1, "official_high": 105200.0, "official_low": 104000.0}
    oc = _calc_outcome(s1, s7_short)
    assert oc["outcome"] == "WIN_TP1"
    assert oc["tp1_hit"] is True
    assert oc["tp2_hit"] is False
    assert oc["stop_hit"] is False
    assert oc["edge_eligible"] is True


def test_short_win_tp2():
    s7_short = {
        **_FAKE_S7,
        "trade_direction": "SHORT",
        "entry_price": 105000.0,
        "stop_loss": 105500.0,
        "tp1": 104200.0,
        "tp2": 103400.0,
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
    }
    s1 = {**_FAKE_S1, "official_high": 105200.0, "official_low": 103000.0}
    oc = _calc_outcome(s1, s7_short)
    assert oc["outcome"] == "WIN_TP2"
    assert oc["tp1_hit"] is True
    assert oc["tp2_hit"] is True
    assert oc["stop_hit"] is False
    assert oc["edge_eligible"] is True


def test_short_loss():
    s7_short = {
        **_FAKE_S7,
        "trade_direction": "SHORT",
        "entry_price": 105000.0,
        "stop_loss": 105500.0,
        "tp1": 104200.0,
        "tp2": 103400.0,
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
    }
    s1 = {**_FAKE_S1, "official_high": 105600.0, "official_low": 104500.0}
    oc = _calc_outcome(s1, s7_short)
    assert oc["outcome"] == "LOSS"
    assert oc["stop_hit"] is True
    assert oc["tp1_hit"] is False


# --- Test 11: ambiguous TP+SL same candle produces AMBIGUOUS and edge_eligible=false ---

def test_long_ambiguous_blocks_edge():
    # high >= tp1 AND low <= stop in same candle → AMBIGUOUS
    s1 = {**_FAKE_S1, "official_high": 105600.0, "official_low": 104100.0}
    oc = _calc_outcome(s1, _FAKE_S7)
    assert oc["outcome"] == "AMBIGUOUS"
    assert oc["ambiguous_hit"] is True
    assert oc["edge_eligible"] is False
    assert oc["realized_rr"] is None


def test_short_ambiguous():
    s7_short = {
        **_FAKE_S7,
        "trade_direction": "SHORT",
        "entry_price": 105000.0,
        "stop_loss": 105500.0,
        "tp1": 104200.0,
        "tp2": 103400.0,
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
    }
    # low <= tp1 AND high >= stop → AMBIGUOUS
    s1 = {**_FAKE_S1, "official_high": 105600.0, "official_low": 104000.0}
    oc = _calc_outcome(s1, s7_short)
    assert oc["outcome"] == "AMBIGUOUS"
    assert oc["ambiguous_hit"] is True
    assert oc["edge_eligible"] is False


def test_ambiguous_edge_eligibility_section():
    s1 = {**_FAKE_S1, "official_high": 105600.0, "official_low": 104100.0}
    po = build_paper_outcome("BTCUSDT", s1, _FAKE_S7, "TEST")
    assert po["result"]["outcome"] == "AMBIGUOUS"
    assert po["edge_eligibility"]["edge_eligible"] is False


# --- Test 12: missing S1 or missing official high/low produces INVALID ---

def test_missing_s7_produces_invalid():
    po = build_paper_outcome("BTCUSDT", _FAKE_S1, None, "TEST")
    assert po["result"]["outcome"] == "INVALID"
    assert po["input_status"]["decision_available"] is False


def test_missing_s1_produces_invalid():
    po = build_paper_outcome("BTCUSDT", None, _FAKE_S7, "TEST")
    assert po["result"]["outcome"] == "INVALID"
    assert po["input_status"]["market_truth_available"] is False


def test_missing_official_high_produces_invalid():
    s1_no_high = {"available": True, "official_low": 104500.0, "official_close": 105000.0}
    po = build_paper_outcome("BTCUSDT", s1_no_high, _FAKE_S7, "TEST")
    assert po["result"]["outcome"] == "INVALID"


def test_missing_official_low_produces_invalid():
    s1_no_low = {"available": True, "official_high": 105600.0, "official_close": 105000.0}
    po = build_paper_outcome("BTCUSDT", s1_no_low, _FAKE_S7, "TEST")
    assert po["result"]["outcome"] == "INVALID"


# --- Test 13: S8 does not output winrate/expectancy/edge stats fields ---

def test_no_winrate_expectancy_edge_stats_fields():
    po = run_fake_sample("BTCUSDT")
    for f in _FORBIDDEN_FIELDS:
        assert f not in po, f"Forbidden top-level field found: {f}"
        assert f not in po.get("result", {}), f"Forbidden field in result: {f}"
        assert f not in po.get("edge_eligibility", {}), f"Forbidden field in edge_eligibility: {f}"


# --- Test 14: runner creates all four output files ---

def test_runner_creates_all_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        po = run_fake_sample("BTCUSDT")
        runner._write_outputs(po)

        assert (tmp / "state" / "latest_outcome.json").exists()
        assert (tmp / "state" / "s8_paper_outcome_state.json").exists()
        assert (tmp / "data" / "paper_outcome.jsonl").exists()
        assert (tmp / "reports" / "s8_paper_outcome_latest_report.md").exists()

        data = json.loads(
            (tmp / "state" / "latest_outcome.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == "S8_PAPER_OUTCOME_TRACKER"
        assert data["reason_codes"]
        assert "S9_EDGE_STATS" in data["feeds_next"]["next_blocks"]
        assert data["execution_safety"]["safe_to_open_real_trade"] is False
        assert data["outcome_check"]["check_method"] == "OFFICIAL_CANDLE_HIGH_LOW"
        assert "decision_reference" in data
        assert "lifecycle" in data
        assert "result" in data
        assert "edge_eligibility" in data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- Additional quality/shape tests ---

def test_data_quality_object_shape():
    po = run_fake_sample("BTCUSDT")
    dq = po["data_quality"]
    assert "score" in dq and "level" in dq and "issues" in dq
    assert dq["level"] in ("HIGH", "MEDIUM", "LOW", "CRITICAL")
    assert 0.0 <= dq["score"] <= 1.0


def test_lifecycle_shape():
    po = run_fake_sample("BTCUSDT")
    lc = po["lifecycle"]
    assert lc["trade_opened"] is True
    assert lc["trade_status"] == "CLOSED"


def test_lifecycle_not_opened():
    s7_blocked = {**_FAKE_S7, "decision": "BLOCK", "paper_eligible": False}
    po = build_paper_outcome("BTCUSDT", _FAKE_S1, s7_blocked, "TEST")
    lc = po["lifecycle"]
    assert lc["trade_opened"] is False
    assert lc["trade_status"] == "NOT_OPENED"
