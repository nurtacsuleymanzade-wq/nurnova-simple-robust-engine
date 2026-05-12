"""Tests for S7 Trade Plan + Decision Gate Engine."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.trade_plan_decision_engine import (
    build_trade_plan_decision,
    run_fake_sample,
    _calc_decision_gate,
    _calc_risk_reward,
    _FAKE_S1,
    _FAKE_S4,
    _FAKE_S5,
    _FAKE_S6,
    FEEDS_NEXT,
)
import src.simple.run_s7_trade_plan_decision as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "input_status", "setup_reference", "trade_plan",
    "risk_reward", "decision_gate", "quality_context",
    "execution_safety", "data_quality", "reason_codes", "feeds_next",
]

_REQUIRED_INPUT_STATUS = [
    "market_truth_available", "quality_weight_available",
    "liquidity_structure_available", "setup_candidate_available",
    "missing_inputs",
]

_REQUIRED_SETUP_REF = [
    "setup_type", "setup_direction", "setup_grade",
    "setup_status", "quality_adjusted_setup_score",
]

_REQUIRED_TRADE_PLAN = [
    "trade_direction", "entry_price", "stop_loss",
    "tp1", "tp2", "invalidation_price", "plan_status",
]

_REQUIRED_RISK_REWARD = [
    "risk_abs", "reward_tp1_abs", "reward_tp2_abs",
    "rr_tp1", "rr_tp2", "rr_label",
]

_REQUIRED_DECISION_GATE = [
    "decision", "decision_reason", "paper_eligible",
    "edge_eligible_if_outcome_closes",
]

_REQUIRED_QUALITY_CTX = [
    "inherited_quality_weight", "inherited_quality_label",
    "quality_adjusted_decision_score",
]

_REQUIRED_SAFETY = [
    "safe_to_open_real_trade", "private_api_used", "live_order_sent",
]


def test_fake_sample_all_required_top_fields():
    td = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_TOP:
        assert f in td, f"Missing top-level field: {f}"
    assert td["block_id"] == "S7_TRADE_PLAN_DECISION_GATE"
    assert td["symbol"] == "BTCUSDT"


def test_fake_sample_nested_fields():
    td = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_INPUT_STATUS:
        assert f in td["input_status"], f"input_status missing: {f}"
    for f in _REQUIRED_SETUP_REF:
        assert f in td["setup_reference"], f"setup_reference missing: {f}"
    for f in _REQUIRED_TRADE_PLAN:
        assert f in td["trade_plan"], f"trade_plan missing: {f}"
    for f in _REQUIRED_RISK_REWARD:
        assert f in td["risk_reward"], f"risk_reward missing: {f}"
    for f in _REQUIRED_DECISION_GATE:
        assert f in td["decision_gate"], f"decision_gate missing: {f}"
    for f in _REQUIRED_QUALITY_CTX:
        assert f in td["quality_context"], f"quality_context missing: {f}"
    for f in _REQUIRED_SAFETY:
        assert f in td["execution_safety"], f"execution_safety missing: {f}"


def test_reason_codes_not_empty():
    td = run_fake_sample("BTCUSDT")
    assert isinstance(td["reason_codes"], list)
    assert len(td["reason_codes"]) >= 1
    assert all(isinstance(c, str) for c in td["reason_codes"])


def test_feeds_next_includes_s8():
    td = run_fake_sample("BTCUSDT")
    assert "S8_PAPER_OUTCOME_TRACKER" in td["feeds_next"]["next_blocks"]


def test_safe_to_open_real_trade_always_false():
    # Fake sample path
    td = run_fake_sample("BTCUSDT")
    assert td["execution_safety"]["safe_to_open_real_trade"] is False

    # Missing S1 path
    td2 = build_trade_plan_decision("BTCUSDT", None, _FAKE_S4, _FAKE_S5, _FAKE_S6, "TEST")
    assert td2["execution_safety"]["safe_to_open_real_trade"] is False

    # Missing S6 path
    td3 = build_trade_plan_decision("BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, None, "TEST")
    assert td3["execution_safety"]["safe_to_open_real_trade"] is False

    # NO_SETUP path
    s6_no = dict(_FAKE_S6)
    s6_no["setup_status"] = "NO_SETUP"
    td4 = build_trade_plan_decision("BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, s6_no, "TEST")
    assert td4["execution_safety"]["safe_to_open_real_trade"] is False


def test_private_api_used_always_false():
    for td in [
        run_fake_sample("BTCUSDT"),
        build_trade_plan_decision("BTCUSDT", None, _FAKE_S4, _FAKE_S5, _FAKE_S6, "TEST"),
        build_trade_plan_decision("BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, None, "TEST"),
    ]:
        assert td["execution_safety"]["private_api_used"] is False


def test_live_order_sent_always_false():
    for td in [
        run_fake_sample("BTCUSDT"),
        build_trade_plan_decision("BTCUSDT", None, _FAKE_S4, _FAKE_S5, _FAKE_S6, "TEST"),
    ]:
        assert td["execution_safety"]["live_order_sent"] is False


def test_long_plan_price_ordering_valid():
    td = run_fake_sample("BTCUSDT")
    tp = td["trade_plan"]
    assert tp["plan_status"] == "PLAN_READY"
    assert tp["stop_loss"] < tp["entry_price"]
    assert tp["entry_price"] < tp["tp1"]
    assert tp["tp1"] <= tp["tp2"]


def test_short_plan_price_ordering_valid():
    s6_short = dict(_FAKE_S6)
    s6_short["setup_type"] = "SHORT_CONTINUATION"
    s6_short["setup_direction"] = "SHORT"
    # Use same S5: resistance=105500 (stop), support=104200 (tp1)
    # entry=105000, stop=105500>entry, tp1=104200<entry ✓
    td = build_trade_plan_decision(
        "BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, s6_short, "TEST"
    )
    tp = td["trade_plan"]
    assert tp["plan_status"] == "PLAN_READY"
    assert tp["stop_loss"] > tp["entry_price"]
    assert tp["entry_price"] > tp["tp1"]
    assert tp["tp1"] >= tp["tp2"]


def test_invalid_long_stop_above_entry_blocks():
    s5_bad = dict(_FAKE_S5)
    s5_bad["nearest_support"] = 106000.0   # support above entry=105000 → INVALID for LONG
    s5_bad["nearest_resistance"] = 107000.0
    td = build_trade_plan_decision(
        "BTCUSDT", _FAKE_S1, _FAKE_S4, s5_bad, _FAKE_S6, "TEST"
    )
    assert td["trade_plan"]["plan_status"] == "INVALID"
    assert td["decision_gate"]["decision"] == "BLOCK"
    assert td["execution_safety"]["safe_to_open_real_trade"] is False


def test_no_setup_produces_block():
    s6_no = dict(_FAKE_S6)
    s6_no["setup_status"] = "NO_SETUP"
    td = build_trade_plan_decision(
        "BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, s6_no, "TEST"
    )
    assert td["decision_gate"]["decision"] == "BLOCK"
    assert td["decision_gate"]["paper_eligible"] is False
    assert td["trade_plan"]["plan_status"] == "NO_PLAN"


def test_watch_setup_produces_watch():
    s6_watch = dict(_FAKE_S6)
    s6_watch["setup_status"] = "WATCH_SETUP"
    td = build_trade_plan_decision(
        "BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, s6_watch, "TEST"
    )
    assert td["decision_gate"]["decision"] == "WATCH"
    assert td["decision_gate"]["paper_eligible"] is False


def test_ready_for_plan_acceptable_rr_allows_paper():
    td = run_fake_sample("BTCUSDT")
    assert td["decision_gate"]["decision"] == "ALLOW_PAPER"
    assert td["decision_gate"]["paper_eligible"] is True
    assert td["risk_reward"]["rr_label"] in ("GOOD_RR", "ACCEPTABLE_RR")


def test_missing_s6_produces_block_or_invalid_no_crash():
    td = build_trade_plan_decision(
        "BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, None, "TEST"
    )
    assert td["decision_gate"]["decision"] in ("BLOCK", "INVALID")
    assert td["decision_gate"]["paper_eligible"] is False
    assert td["execution_safety"]["safe_to_open_real_trade"] is False
    assert td["reason_codes"]


def test_missing_s1_produces_invalid():
    td = build_trade_plan_decision(
        "BTCUSDT", None, _FAKE_S4, _FAKE_S5, _FAKE_S6, "TEST"
    )
    assert td["decision_gate"]["decision"] == "INVALID"
    assert td["trade_plan"]["entry_price"] is None


def test_poor_rr_blocks_decision():
    s6_ready = dict(_FAKE_S6)
    s6_ready["setup_status"] = "READY_FOR_PLAN"
    plan_ok = {
        "plan_status": "PLAN_READY",
        "trade_direction": "LONG",
        "entry_price": 105000.0,
        "stop_loss": 100000.0,
        "tp1": 105100.0,
        "tp2": 105200.0,
        "invalidation_price": 100000.0,
    }
    poor_rr = {
        "risk_abs": 5000.0,
        "reward_tp1_abs": 100.0,
        "reward_tp2_abs": 200.0,
        "rr_tp1": 0.02,
        "rr_tp2": 0.04,
        "rr_label": "POOR_RR",
    }
    gate = _calc_decision_gate(_FAKE_S1, s6_ready, plan_ok, poor_rr, 0.9513)
    assert gate["decision"] == "BLOCK"
    assert gate["paper_eligible"] is False


def test_invalid_setup_produces_invalid():
    s6_inv = dict(_FAKE_S6)
    s6_inv["setup_status"] = "INVALID"
    td = build_trade_plan_decision(
        "BTCUSDT", _FAKE_S1, _FAKE_S4, _FAKE_S5, s6_inv, "TEST"
    )
    assert td["decision_gate"]["decision"] == "INVALID"


def test_risk_reward_invalid_plan_returns_null_rr():
    null_plan = {
        "plan_status": "INVALID",
        "entry_price": None,
        "stop_loss": None,
        "tp1": None,
        "tp2": None,
        "trade_direction": "UNKNOWN",
        "invalidation_price": None,
    }
    rr = _calc_risk_reward(null_plan)
    assert rr["rr_label"] == "INVALID_RR"
    assert rr["rr_tp2"] is None


def test_data_quality_object_shape():
    td = run_fake_sample("BTCUSDT")
    dq = td["data_quality"]
    assert "score" in dq and "level" in dq and "issues" in dq
    assert dq["level"] in ("HIGH", "MEDIUM", "LOW", "CRITICAL")
    assert 0.0 <= dq["score"] <= 1.0


def test_setup_reference_mirrors_s6():
    td = run_fake_sample("BTCUSDT")
    sr = td["setup_reference"]
    assert sr["setup_type"] == _FAKE_S6["setup_type"]
    assert sr["setup_direction"] == _FAKE_S6["setup_direction"]
    assert sr["setup_status"] == _FAKE_S6["setup_status"]


def test_runner_creates_all_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        td = run_fake_sample("BTCUSDT")
        runner._write_outputs(td)

        assert (tmp / "state" / "latest_decision.json").exists()
        assert (tmp / "state" / "s7_trade_plan_decision_state.json").exists()
        assert (tmp / "data" / "trade_plan_decision.jsonl").exists()
        assert (tmp / "reports" / "s7_trade_plan_decision_latest_report.md").exists()

        data = json.loads(
            (tmp / "state" / "latest_decision.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == "S7_TRADE_PLAN_DECISION_GATE"
        assert data["reason_codes"]
        assert "S8_PAPER_OUTCOME_TRACKER" in data["feeds_next"]["next_blocks"]
        assert data["execution_safety"]["safe_to_open_real_trade"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
