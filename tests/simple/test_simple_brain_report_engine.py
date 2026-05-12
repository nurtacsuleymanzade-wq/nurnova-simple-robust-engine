"""Tests for S10 Simple Brain Report Engine."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.simple_brain_report_engine import (
    build_brain_report,
    run_fake_sample,
    _FAKE_INPUTS,
    FEEDS_NEXT,
)
import src.simple.run_s10_simple_brain as runner


_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "input_status", "market_snapshot", "quality_snapshot",
    "setup_snapshot", "decision_snapshot", "paper_outcome_snapshot",
    "edge_snapshot", "brain_status", "brain_mode", "primary_next_action",
    "system_health", "report_path", "execution_safety",
    "data_quality", "reason_codes", "feeds_next",
]

_REQUIRED_INPUT_STATUS = [
    "blocks_available", "blocks_total", "available", "missing_blocks",
]

_REQUIRED_SAFETY = [
    "safe_to_open_real_trade", "private_api_used", "live_order_sent",
]

_REQUIRED_DATA_QUALITY = ["score", "level", "issues"]


# ── Test: all required contract fields ───────────────────────────────────────

def test_fake_sample_all_required_top_fields():
    br = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_TOP:
        assert f in br, f"Missing top-level field: {f}"
    assert br["block_id"] == "S10_SIMPLE_BRAIN_REPORT"
    assert br["symbol"] == "BTCUSDT"


def test_fake_sample_nested_required_fields():
    br = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_INPUT_STATUS:
        assert f in br["input_status"], f"input_status missing: {f}"
    for f in _REQUIRED_SAFETY:
        assert f in br["execution_safety"], f"execution_safety missing: {f}"
    for f in _REQUIRED_DATA_QUALITY:
        assert f in br["data_quality"], f"data_quality missing: {f}"


# ── Test: reason_codes not empty ─────────────────────────────────────────────

def test_reason_codes_not_empty():
    br = run_fake_sample("BTCUSDT")
    assert isinstance(br["reason_codes"], list)
    assert len(br["reason_codes"]) >= 1
    assert all(isinstance(c, str) for c in br["reason_codes"])


# ── Test: feeds_next includes SIMPLE_ENGINE_COMPLETE ─────────────────────────

def test_feeds_next_includes_complete():
    br = run_fake_sample("BTCUSDT")
    assert "SIMPLE_ENGINE_COMPLETE" in br["feeds_next"]["next_blocks"]


# ── Test: safe_to_open_real_trade always false ────────────────────────────────

def test_safe_to_open_real_trade_always_false():
    for inputs in [
        _FAKE_INPUTS,
        {},
        {"s1": None, "s7": None},
    ]:
        br = build_brain_report("BTCUSDT", inputs, "TEST")
        assert br["execution_safety"]["safe_to_open_real_trade"] is False


# ── Test: private_api_used always false ───────────────────────────────────────

def test_private_api_used_always_false():
    br = run_fake_sample("BTCUSDT")
    assert br["execution_safety"]["private_api_used"] is False


# ── Test: live_order_sent always false ────────────────────────────────────────

def test_live_order_sent_always_false():
    br = run_fake_sample("BTCUSDT")
    assert br["execution_safety"]["live_order_sent"] is False


# ── Test: S10 is read-only — no paper_decision created ───────────────────────

def test_no_paper_decision_in_output():
    br = run_fake_sample("BTCUSDT")
    assert "paper_decision" not in br
    assert "paper_decision" not in br.get("decision_snapshot", {})


def test_no_new_decision_fields():
    br = run_fake_sample("BTCUSDT")
    forbidden = ["paper_decision", "new_decision", "trade_signal"]
    for f in forbidden:
        assert f not in br, f"Forbidden field '{f}' found in output"


# ── Test: brain_status and brain_mode set correctly ──────────────────────────

def test_fake_sample_brain_status_ready():
    br = run_fake_sample("BTCUSDT")
    assert br["brain_status"] == "READY"
    assert br["system_health"] == "OK"


def test_fake_sample_brain_mode_paper_long():
    br = run_fake_sample("BTCUSDT")
    assert br["brain_mode"] == "PAPER_LONG"
    assert br["primary_next_action"] == "MONITOR_LONG_PAPER_TRADE"


def test_paper_short_brain_mode():
    inputs = {**_FAKE_INPUTS, "s7": {
        **_FAKE_INPUTS["s7"],
        "decision_gate": {
            "decision": "ALLOW_PAPER",
            "paper_eligible": True,
            "edge_eligible_if_outcome_closes": True,
            "decision_reason": "Short setup.",
        },
        "trade_plan": {
            "trade_direction": "SHORT",
            "entry_price": 105000.0,
            "stop_loss": 105500.0,
            "tp1": 104500.0,
            "tp2": 103500.0,
        },
    }}
    br = build_brain_report("BTCUSDT", inputs, "TEST")
    assert br["brain_mode"] == "PAPER_SHORT"
    assert br["primary_next_action"] == "MONITOR_SHORT_PAPER_TRADE"


def test_no_trade_decision_produces_degraded():
    inputs = {**_FAKE_INPUTS, "s7": {
        **_FAKE_INPUTS["s7"],
        "decision_gate": {
            "decision": "NO_TRADE",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
            "decision_reason": "Low quality.",
        },
        "trade_plan": {"trade_direction": "NONE"},
    }}
    br = build_brain_report("BTCUSDT", inputs, "TEST")
    assert br["brain_status"] == "DEGRADED"
    assert br["brain_mode"] == "NO_TRADE"
    assert br["system_health"] == "DEGRADED"


# ── Test: missing S1 or S7 → INCOMPLETE ──────────────────────────────────────

def test_missing_s1_produces_incomplete():
    inputs = {k: v for k, v in _FAKE_INPUTS.items() if k != "s1"}
    inputs["s1"] = None
    br = build_brain_report("BTCUSDT", inputs, "TEST")
    assert br["brain_status"] == "INCOMPLETE"
    assert br["system_health"] == "CRITICAL"


def test_missing_s7_produces_incomplete():
    inputs = {k: v for k, v in _FAKE_INPUTS.items() if k != "s7"}
    inputs["s7"] = None
    br = build_brain_report("BTCUSDT", inputs, "TEST")
    assert br["brain_status"] == "INCOMPLETE"


def test_empty_inputs_produces_incomplete():
    br = build_brain_report("BTCUSDT", {}, "TEST")
    assert br["brain_status"] == "INCOMPLETE"
    assert br["input_status"]["blocks_available"] == 0
    assert br["market_snapshot"]["available"] is False
    assert br["decision_snapshot"]["available"] is False


# ── Test: all snapshots present ───────────────────────────────────────────────

def test_all_snapshots_available_in_fake_sample():
    br = run_fake_sample("BTCUSDT")
    for snap in [
        "market_snapshot", "quality_snapshot", "setup_snapshot",
        "decision_snapshot", "paper_outcome_snapshot", "edge_snapshot",
    ]:
        assert br[snap].get("available") is True, f"{snap} not available"


def test_input_status_counts_correctly():
    br = run_fake_sample("BTCUSDT")
    assert br["input_status"]["blocks_available"] == 9
    assert br["input_status"]["blocks_total"] == 9
    assert br["input_status"]["missing_blocks"] == []


# ── Test: snapshot content correct ────────────────────────────────────────────

def test_market_snapshot_has_price():
    br = run_fake_sample("BTCUSDT")
    ms = br["market_snapshot"]
    assert ms["mid_price"] == 105000.0
    assert ms["high"] == 105600.0
    assert ms["candle_direction"] == "BULLISH"
    assert ms["evidence_label"] == "LONG_PRESSURE"


def test_quality_snapshot_has_weight():
    br = run_fake_sample("BTCUSDT")
    qs = br["quality_snapshot"]
    assert qs["quality_weight"] == 0.9513
    assert qs["quality_label"] == "HIGH_QUALITY"


def test_setup_snapshot_has_grade():
    br = run_fake_sample("BTCUSDT")
    ss = br["setup_snapshot"]
    assert ss["setup_grade"] == "A"
    assert ss["setup_direction"] == "LONG"
    assert ss["nearest_support"] == 104200.0


def test_decision_snapshot_has_plan():
    br = run_fake_sample("BTCUSDT")
    ds = br["decision_snapshot"]
    assert ds["decision"] == "ALLOW_PAPER"
    assert ds["trade_direction"] == "LONG"
    assert ds["entry_price"] == 105000.0


def test_paper_outcome_snapshot_has_result():
    br = run_fake_sample("BTCUSDT")
    pos = br["paper_outcome_snapshot"]
    assert pos["outcome"] == "WIN_TP1"
    assert pos["realized_rr"] == 0.625
    assert pos["edge_eligible"] is True


def test_edge_snapshot_has_stats():
    br = run_fake_sample("BTCUSDT")
    es = br["edge_snapshot"]
    assert es["win_rate"] == 0.6667
    assert es["edge_score"] == 0.3612
    assert es["edge_eligible_count"] == 3


# ── Test: data_quality shape ──────────────────────────────────────────────────

def test_data_quality_high_when_all_blocks_available():
    br = run_fake_sample("BTCUSDT")
    assert br["data_quality"]["level"] == "HIGH"
    assert br["data_quality"]["score"] == 1.0
    assert br["data_quality"]["issues"] == []


def test_data_quality_critical_when_no_blocks():
    br = build_brain_report("BTCUSDT", {}, "TEST")
    assert br["data_quality"]["level"] == "CRITICAL"


# ── Test: runner creates all four output files ────────────────────────────────

def test_runner_creates_all_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        report_path = str(tmp / "reports" / "simple_brain_latest_report.md")
        br = build_brain_report("BTCUSDT", _FAKE_INPUTS, "FAKE_SAMPLE", report_path)
        runner._write_outputs(br)

        assert (tmp / "state" / "latest_simple_brain.json").exists()
        assert (tmp / "state" / "s10_simple_brain_state.json").exists()
        assert (tmp / "data" / "simple_brain.jsonl").exists()
        assert (tmp / "reports" / "simple_brain_latest_report.md").exists()

        data = json.loads(
            (tmp / "state" / "latest_simple_brain.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == "S10_SIMPLE_BRAIN_REPORT"
        assert data["reason_codes"]
        assert "SIMPLE_ENGINE_COMPLETE" in data["feeds_next"]["next_blocks"]
        assert data["execution_safety"]["safe_to_open_real_trade"] is False
        assert "paper_decision" not in data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
