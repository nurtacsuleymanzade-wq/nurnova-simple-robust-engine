"""Tests for S11 Replay Sample Runner."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.replay_sample_runner import (
    BLOCK_ID,
    FEEDS_NEXT,
    DEFAULT_SEED,
    run_batch,
    run_fake_sample,
    _generate_scenario,
    _compute_batch_stats,
)
import src.simple.run_s11_replay_samples as runner

import random

_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "run_config", "batch_stats", "data_quality",
    "reason_codes", "feeds_next", "execution_safety",
]
_REQUIRED_BATCH_STATS = [
    "total_samples", "trades_opened", "no_trade_count",
    "edge_eligible_count", "win_count", "loss_count",
    "ambiguous_count", "win_rate", "avg_rr_realized", "edge_score",
]
_REQUIRED_DATA_QUALITY = ["score", "level", "issues"]
_REQUIRED_RUN_CONFIG = ["seed", "samples_requested", "samples_generated"]
_REQUIRED_EXECUTION_SAFETY = [
    "safe_to_open_real_trade", "private_api_used", "live_order_sent", "research_only",
]
_REQUIRED_SAMPLE = ["sample_id", "seed", "symbol", "scenario", "decision", "outcome"]
_REQUIRED_SCENARIO = [
    "candle_direction", "evidence_label", "quality_weight",
    "structure_bias", "setup_type", "setup_direction", "setup_grade",
]
_REQUIRED_DECISION = [
    "paper_decision", "entry_price", "stop_loss", "tp1", "tp2", "rr_tp1", "rr_tp2",
]
_REQUIRED_OUTCOME = ["outcome", "realized_rr", "edge_eligible"]


# ── Contract: top-level fields ────────────────────────────────────────────────

def test_fake_sample_all_required_top_fields():
    summary = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_TOP:
        assert f in summary, f"Missing top-level field: {f}"
    assert summary["block_id"] == BLOCK_ID
    assert summary["symbol"] == "BTCUSDT"


def test_batch_stats_fields():
    summary = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_BATCH_STATS:
        assert f in summary["batch_stats"], f"batch_stats missing: {f}"


def test_run_config_fields():
    summary = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_RUN_CONFIG:
        assert f in summary["run_config"], f"run_config missing: {f}"


def test_data_quality_fields():
    summary = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_DATA_QUALITY:
        assert f in summary["data_quality"], f"data_quality missing: {f}"


def test_execution_safety_fields():
    summary = run_fake_sample("BTCUSDT")
    for f in _REQUIRED_EXECUTION_SAFETY:
        assert f in summary["execution_safety"], f"execution_safety missing: {f}"


# ── Contract: reason_codes not empty ─────────────────────────────────────────

def test_reason_codes_not_empty():
    summary = run_fake_sample("BTCUSDT")
    assert isinstance(summary["reason_codes"], list)
    assert len(summary["reason_codes"]) >= 1
    assert all(isinstance(c, str) for c in summary["reason_codes"])


# ── Contract: feeds_next includes S11_1_LOCAL_PIPELINE_RUNNER ────────────────

def test_feeds_next_includes_required_block():
    summary = run_fake_sample("BTCUSDT")
    assert "S11_1_LOCAL_PIPELINE_RUNNER" in summary["feeds_next"]["next_blocks"]


def test_feeds_next_constant_correct():
    assert "S11_1_LOCAL_PIPELINE_RUNNER" in FEEDS_NEXT["next_blocks"]


# ── Contract: execution safety ────────────────────────────────────────────────

def test_safe_to_open_real_trade_always_false():
    summary = run_fake_sample("BTCUSDT")
    assert summary["execution_safety"]["safe_to_open_real_trade"] is False


def test_private_api_not_used():
    summary = run_fake_sample("BTCUSDT")
    assert summary["execution_safety"]["private_api_used"] is False


def test_live_order_not_sent():
    summary = run_fake_sample("BTCUSDT")
    assert summary["execution_safety"]["live_order_sent"] is False


def test_research_only_flag():
    summary = run_fake_sample("BTCUSDT")
    assert summary["execution_safety"]["research_only"] is True


# ── Deterministic seed ────────────────────────────────────────────────────────

def test_same_seed_produces_same_samples():
    samples_a, summary_a = run_batch("BTCUSDT", 20, seed=42)
    samples_b, summary_b = run_batch("BTCUSDT", 20, seed=42)
    assert samples_a == samples_b
    assert summary_a["batch_stats"] == summary_b["batch_stats"]


def test_different_seeds_produce_different_samples():
    samples_a, _ = run_batch("BTCUSDT", 20, seed=42)
    samples_b, _ = run_batch("BTCUSDT", 20, seed=99)
    assert samples_a != samples_b


def test_default_seed_is_deterministic():
    s1 = run_fake_sample("BTCUSDT")
    s2 = run_fake_sample("BTCUSDT")
    assert s1["batch_stats"] == s2["batch_stats"]


# ── Sample count ──────────────────────────────────────────────────────────────

def test_samples_count_matches_requested():
    samples, summary = run_batch("BTCUSDT", 50)
    assert len(samples) == 50
    assert summary["run_config"]["samples_generated"] == 50
    assert summary["batch_stats"]["total_samples"] == 50


def test_samples_count_small():
    samples, summary = run_batch("BTCUSDT", 5)
    assert len(samples) == 5
    assert summary["batch_stats"]["total_samples"] == 5


# ── Sample structure ──────────────────────────────────────────────────────────

def test_each_sample_has_required_fields():
    samples, _ = run_batch("BTCUSDT", 10)
    for s in samples:
        for f in _REQUIRED_SAMPLE:
            assert f in s, f"Sample missing field: {f}"
        for f in _REQUIRED_SCENARIO:
            assert f in s["scenario"], f"Scenario missing field: {f}"
        for f in _REQUIRED_DECISION:
            assert f in s["decision"], f"Decision missing field: {f}"
        for f in _REQUIRED_OUTCOME:
            assert f in s["outcome"], f"Outcome missing field: {f}"


def test_sample_ids_are_sequential():
    samples, _ = run_batch("BTCUSDT", 10)
    for i, s in enumerate(samples):
        assert s["sample_id"] == i


def test_sample_symbols_match():
    samples, _ = run_batch("ETHUSDT", 5)
    for s in samples:
        assert s["symbol"] == "ETHUSDT"


# ── Batch stats correctness ───────────────────────────────────────────────────

def test_batch_stats_totals_consistent():
    samples, summary = run_batch("BTCUSDT", 50)
    bs = summary["batch_stats"]
    assert bs["trades_opened"] + bs["no_trade_count"] == bs["total_samples"]
    assert bs["edge_eligible_count"] + bs["ambiguous_count"] <= bs["trades_opened"]
    assert bs["win_count"] + bs["loss_count"] <= bs["edge_eligible_count"]


def test_win_rate_null_when_no_eligible():
    # Generate a minimal fake set with no eligible trades
    samples_data = [
        {
            "sample_id": 0, "seed": 0, "symbol": "BTCUSDT",
            "scenario": {}, "decision": {"paper_decision": "NO_TRADE"},
            "outcome": {"outcome": "NO_TRADE", "realized_rr": None, "edge_eligible": False},
        }
    ]
    stats = _compute_batch_stats(samples_data)
    assert stats["win_rate"] is None
    assert stats["avg_rr_realized"] is None
    assert stats["edge_score"] is None


def test_win_rate_computed_correctly():
    samples, summary = run_batch("BTCUSDT", 50)
    bs = summary["batch_stats"]
    if bs["edge_eligible_count"] > 0:
        expected = round(bs["win_count"] / bs["edge_eligible_count"], 4)
        assert bs["win_rate"] == expected


def test_edge_score_computed_correctly():
    samples, summary = run_batch("BTCUSDT", 50)
    bs = summary["batch_stats"]
    if bs["win_rate"] is not None and bs["avg_rr_realized"] is not None:
        expected = round(bs["win_rate"] * bs["avg_rr_realized"], 4)
        assert bs["edge_score"] == expected


# ── No-trade samples have no entry/outcome ────────────────────────────────────

def test_no_trade_samples_have_null_prices():
    samples, _ = run_batch("BTCUSDT", 100, seed=1)
    no_trade = [s for s in samples if s["decision"]["paper_decision"] == "NO_TRADE"]
    for s in no_trade:
        assert s["decision"]["entry_price"] is None
        assert s["outcome"]["outcome"] == "NO_TRADE"
        assert s["outcome"]["edge_eligible"] is False


# ── Source mode ───────────────────────────────────────────────────────────────

def test_fake_sample_source_mode():
    summary = run_fake_sample("BTCUSDT")
    assert summary["source"]["source_mode"] == "FAKE_SAMPLE"


def test_reason_codes_include_source_fake_sample():
    summary = run_fake_sample("BTCUSDT")
    assert any("SOURCE_FAKE_SAMPLE" in c for c in summary["reason_codes"])


# ── Runner: output files ──────────────────────────────────────────────────────

def test_runner_creates_all_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        samples, summary = run_batch("BTCUSDT", 10)
        runner._write_outputs(summary, samples)

        assert (tmp / "state" / "latest_replay_summary.json").exists()
        assert (tmp / "state" / "s11_replay_samples_state.json").exists()
        assert (tmp / "data" / "replay_samples.jsonl").exists()
        assert (tmp / "reports" / "s11_replay_samples_latest_report.md").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_state_json_valid_contract(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        samples, summary = run_batch("BTCUSDT", 10)
        runner._write_outputs(summary, samples)

        data = json.loads(
            (tmp / "state" / "latest_replay_summary.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == BLOCK_ID
        assert data["reason_codes"]
        assert "S11_1_LOCAL_PIPELINE_RUNNER" in data["feeds_next"]["next_blocks"]
        assert data["execution_safety"]["safe_to_open_real_trade"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_jsonl_has_correct_line_count(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        samples, summary = run_batch("BTCUSDT", 10)
        runner._write_outputs(summary, samples)

        lines = [
            l for l in
            (tmp / "data" / "replay_samples.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        assert len(lines) == 10
        for line in lines:
            record = json.loads(line)
            assert "sample_id" in record
            assert "outcome" in record
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_report_contains_key_sections(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(runner, "REPORTS_DIR", tmp / "reports")

        samples, summary = run_batch("BTCUSDT", 10)
        runner._write_outputs(summary, samples)

        text = (tmp / "reports" / "s11_replay_samples_latest_report.md").read_text(encoding="utf-8")
        assert "S11 Replay Sample Runner" in text
        assert "Batch Stats" in text
        assert "Execution Safety" in text
        assert "Feeds Next" in text
        assert "S11_1_LOCAL_PIPELINE_RUNNER" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
