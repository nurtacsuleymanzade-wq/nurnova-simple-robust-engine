"""Tests for S11.4 Pre-VPS Readiness Report."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

import pytest

from src.simple.pre_vps_readiness_report import (
    BLOCK_ID,
    FEEDS_NEXT,
    _AUDIT_CHECKS,
    _check_live_trading_safety,
    _check_fake_sample_support,
    _check_state_blocks,
    run_readiness_audit,
)
import src.simple.run_pre_vps_readiness_report as runner_module

_REQUIRED_TOP = [
    "timestamp_utc", "block_id", "symbol", "source",
    "readiness_score", "vps_ready", "critical_missing_items",
    "warnings", "recommended_next_step", "check_results",
    "data_quality", "reason_codes", "feeds_next", "execution_safety",
]
_REQUIRED_DATA_QUALITY = ["score", "level", "issues"]
_REQUIRED_SAFETY = ["safe_to_open_real_trade", "private_api_used", "live_order_sent", "research_only"]
_REQUIRED_CHECK_RESULT = ["check", "passed", "critical_items", "warnings"]


# ── Contract: top-level fields ────────────────────────────────────────────────

def test_all_required_top_fields():
    result = run_readiness_audit("BTCUSDT")
    for f in _REQUIRED_TOP:
        assert f in result, f"Missing top-level field: {f}"


def test_block_id_matches_constant():
    result = run_readiness_audit("BTCUSDT")
    assert result["block_id"] == BLOCK_ID


def test_symbol_propagated():
    result = run_readiness_audit("ETHUSDT")
    assert result["symbol"] == "ETHUSDT"


def test_source_mode_is_local_audit():
    result = run_readiness_audit("BTCUSDT")
    assert result["source"]["source_mode"] == "LOCAL_AUDIT"


def test_data_quality_fields():
    result = run_readiness_audit("BTCUSDT")
    dq = result["data_quality"]
    for f in _REQUIRED_DATA_QUALITY:
        assert f in dq, f"data_quality missing: {f}"


def test_execution_safety_fields():
    result = run_readiness_audit("BTCUSDT")
    for f in _REQUIRED_SAFETY:
        assert f in result["execution_safety"], f"execution_safety missing: {f}"


# ── Contract: required final fields ──────────────────────────────────────────

def test_vps_ready_is_bool():
    result = run_readiness_audit("BTCUSDT")
    assert isinstance(result["vps_ready"], bool)


def test_readiness_score_in_range():
    result = run_readiness_audit("BTCUSDT")
    score = result["readiness_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_critical_missing_items_is_list():
    result = run_readiness_audit("BTCUSDT")
    assert isinstance(result["critical_missing_items"], list)
    for item in result["critical_missing_items"]:
        assert isinstance(item, str)


def test_warnings_is_list():
    result = run_readiness_audit("BTCUSDT")
    assert isinstance(result["warnings"], list)
    for w in result["warnings"]:
        assert isinstance(w, str)


def test_recommended_next_step_is_nonempty_string():
    result = run_readiness_audit("BTCUSDT")
    rns = result["recommended_next_step"]
    assert isinstance(rns, str)
    assert len(rns) > 0


# ── Contract: safety invariants ───────────────────────────────────────────────

def test_safe_to_open_real_trade_always_false():
    result = run_readiness_audit("BTCUSDT")
    assert result["execution_safety"]["safe_to_open_real_trade"] is False


def test_private_api_always_false():
    result = run_readiness_audit("BTCUSDT")
    assert result["execution_safety"]["private_api_used"] is False


def test_live_order_always_false():
    result = run_readiness_audit("BTCUSDT")
    assert result["execution_safety"]["live_order_sent"] is False


def test_research_only_always_true():
    result = run_readiness_audit("BTCUSDT")
    assert result["execution_safety"]["research_only"] is True


# ── Contract: reason_codes ────────────────────────────────────────────────────

def test_reason_codes_not_empty():
    result = run_readiness_audit("BTCUSDT")
    codes = result["reason_codes"]
    assert isinstance(codes, list)
    assert len(codes) >= 1
    assert all(isinstance(c, str) for c in codes)


def test_reason_codes_include_safe_flag():
    result = run_readiness_audit("BTCUSDT")
    assert any("SAFE_TO_OPEN_REAL_TRADE_FALSE" in c for c in result["reason_codes"])


def test_reason_codes_include_readiness_score():
    result = run_readiness_audit("BTCUSDT")
    assert any("READINESS_SCORE_" in c for c in result["reason_codes"])


def test_reason_codes_include_vps_ready_status():
    result = run_readiness_audit("BTCUSDT")
    codes = result["reason_codes"]
    assert any("VPS_READY_TRUE" in c or "VPS_READY_FALSE" in c for c in codes)


# ── Contract: feeds_next ──────────────────────────────────────────────────────

def test_feeds_next_has_next_blocks():
    result = run_readiness_audit("BTCUSDT")
    assert "next_blocks" in result["feeds_next"]
    assert isinstance(result["feeds_next"]["next_blocks"], list)


def test_feeds_next_constant_is_dict():
    assert isinstance(FEEDS_NEXT, dict)
    assert "next_blocks" in FEEDS_NEXT


# ── Check results structure ───────────────────────────────────────────────────

def test_check_results_is_list():
    result = run_readiness_audit("BTCUSDT")
    assert isinstance(result["check_results"], list)
    assert len(result["check_results"]) == len(_AUDIT_CHECKS)


def test_each_check_result_has_required_fields():
    result = run_readiness_audit("BTCUSDT")
    for cr in result["check_results"]:
        for f in _REQUIRED_CHECK_RESULT:
            assert f in cr, f"check_result missing: {f}"


def test_check_result_passed_is_bool():
    result = run_readiness_audit("BTCUSDT")
    for cr in result["check_results"]:
        assert isinstance(cr["passed"], bool)


def test_check_result_critical_items_is_list():
    result = run_readiness_audit("BTCUSDT")
    for cr in result["check_results"]:
        assert isinstance(cr["critical_items"], list)


def test_check_result_warnings_is_list():
    result = run_readiness_audit("BTCUSDT")
    for cr in result["check_results"]:
        assert isinstance(cr["warnings"], list)


def test_check_passed_iff_no_critical_items():
    result = run_readiness_audit("BTCUSDT")
    for cr in result["check_results"]:
        if cr["passed"]:
            assert len(cr["critical_items"]) == 0
        else:
            assert len(cr["critical_items"]) > 0


# ── Readiness score consistency ───────────────────────────────────────────────

def test_readiness_score_matches_passed_checks():
    result = run_readiness_audit("BTCUSDT")
    n_checks = len(result["check_results"])
    n_passed = sum(1 for cr in result["check_results"] if cr["passed"])
    expected = round(n_passed / n_checks, 4)
    assert result["readiness_score"] == expected


def test_vps_ready_requires_no_critical_items():
    result = run_readiness_audit("BTCUSDT")
    if result["vps_ready"]:
        assert len(result["critical_missing_items"]) == 0


def test_vps_ready_requires_high_score():
    result = run_readiness_audit("BTCUSDT")
    if result["vps_ready"]:
        assert result["readiness_score"] >= 0.8


def test_critical_items_matches_check_results():
    result = run_readiness_audit("BTCUSDT")
    all_critical_from_checks: list[str] = []
    for cr in result["check_results"]:
        all_critical_from_checks.extend(cr["critical_items"])
    assert result["critical_missing_items"] == all_critical_from_checks


def test_warnings_matches_check_results():
    result = run_readiness_audit("BTCUSDT")
    all_warnings_from_checks: list[str] = []
    for cr in result["check_results"]:
        all_warnings_from_checks.extend(cr["warnings"])
    assert result["warnings"] == all_warnings_from_checks


# ── Data quality level consistency ────────────────────────────────────────────

def test_data_quality_score_matches_readiness_score():
    result = run_readiness_audit("BTCUSDT")
    assert result["data_quality"]["score"] == result["readiness_score"]


def test_data_quality_level_is_valid():
    result = run_readiness_audit("BTCUSDT")
    assert result["data_quality"]["level"] in ("HIGH", "MEDIUM", "LOW", "CRITICAL")


# ── Helper: _check_live_trading_safety ───────────────────────────────────────

def test_live_trading_safety_no_violations_on_clean_state():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        (tmp / "good.json").write_text(
            json.dumps({
                "execution_safety": {
                    "safe_to_open_real_trade": False,
                    "live_order_sent": False,
                    "private_api_used": False,
                }
            }),
            encoding="utf-8",
        )
        import src.simple.pre_vps_readiness_report as engine
        orig = engine.STATE_DIR
        engine.STATE_DIR = tmp
        try:
            critical, _ = _check_live_trading_safety()
            assert critical == []
        finally:
            engine.STATE_DIR = orig
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_live_trading_safety_flags_real_trade_true():
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        (tmp / "bad.json").write_text(
            json.dumps({
                "execution_safety": {
                    "safe_to_open_real_trade": True,
                    "live_order_sent": False,
                    "private_api_used": False,
                }
            }),
            encoding="utf-8",
        )
        import src.simple.pre_vps_readiness_report as engine
        orig = engine.STATE_DIR
        engine.STATE_DIR = tmp
        try:
            critical, _ = _check_live_trading_safety()
            assert any("LIVE_TRADING_FLAG_SET_IN" in c for c in critical)
        finally:
            engine.STATE_DIR = orig
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Helper: _check_fake_sample_support ───────────────────────────────────────

def test_fake_sample_support_all_modules_importable():
    critical, warnings = _check_fake_sample_support()
    assert critical == [], f"Module import failures: {critical}"


# ── Helper: _check_state_blocks ──────────────────────────────────────────────

def test_state_blocks_missing_dir_returns_critical(monkeypatch):
    import src.simple.pre_vps_readiness_report as engine
    orig = engine.STATE_DIR
    engine.STATE_DIR = pathlib.Path("/nonexistent/dir/xyz")
    try:
        critical, _ = _check_state_blocks()
        assert len(critical) > 0
    finally:
        engine.STATE_DIR = orig


# ── Runner: file outputs ──────────────────────────────────────────────────────

def test_runner_creates_output_files(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner_module, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner_module, "REPORTS_DIR", tmp / "reports")

        result = run_readiness_audit("BTCUSDT")
        runner_module._write_outputs(result)

        assert (tmp / "state" / "latest_pre_vps_readiness.json").exists()
        assert (tmp / "reports" / "pre_vps_readiness_latest_report.md").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_state_json_valid_contract(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner_module, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner_module, "REPORTS_DIR", tmp / "reports")

        result = run_readiness_audit("BTCUSDT")
        runner_module._write_outputs(result)

        data = json.loads(
            (tmp / "state" / "latest_pre_vps_readiness.json").read_text(encoding="utf-8")
        )
        assert data["block_id"] == BLOCK_ID
        assert data["reason_codes"]
        assert data["execution_safety"]["safe_to_open_real_trade"] is False
        assert "vps_ready" in data
        assert "readiness_score" in data
        assert "critical_missing_items" in data
        assert "warnings" in data
        assert "recommended_next_step" in data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_report_contains_key_sections(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner_module, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner_module, "REPORTS_DIR", tmp / "reports")

        result = run_readiness_audit("BTCUSDT")
        runner_module._write_outputs(result)

        text = (tmp / "reports" / "pre_vps_readiness_latest_report.md").read_text(encoding="utf-8")
        assert "S11.4 Pre-VPS Readiness Report" in text
        assert "Check Results" in text
        assert "Critical Missing Items" in text
        assert "Warnings" in text
        assert "Execution Safety" in text
        assert "Reason Codes" in text
        assert "safe_to_open_real_trade: False" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_report_shows_vps_ready_status(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp(dir=pathlib.Path(__file__).parent))
    try:
        monkeypatch.setattr(runner_module, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(runner_module, "REPORTS_DIR", tmp / "reports")

        result = run_readiness_audit("BTCUSDT")
        runner_module._write_outputs(result)

        text = (tmp / "reports" / "pre_vps_readiness_latest_report.md").read_text(encoding="utf-8")
        assert "VPS Ready:" in text
        assert "Readiness Score:" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
