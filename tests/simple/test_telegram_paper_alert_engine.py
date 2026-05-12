"""Tests for S19 Telegram Paper Alert Engine."""

import json
import shutil
import uuid
from pathlib import Path

import pytest

from src.simple.telegram_paper_alert_engine import (
    compute_telegram_paper_alert,
    no_valid_output,
    run_telegram_paper_alert_engine,
)

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_s19():
    d = TMP_BASE / f"s19_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _gate(decision: str = "ALLOW_PAPER", side: str = "LONG") -> dict:
    return {
        "timestamp_utc": "2026-05-11T12:00:00Z",
        "block_id": "S18_DECISION_GATE",
        "symbol": "BTCUSDT",
        "input_status": "OK",
        "decision": decision,
        "decision_status": "PASSED" if decision == "ALLOW_PAPER" else (
            "WATCH_ONLY" if decision == "WATCH" else "BLOCKED"
        ),
        "selected_side": side,
        "selected_entry": 80000.0,
        "selected_stop_loss": 79600.0,
        "selected_tp1": 80480.0,
        "selected_tp2": 80800.0,
        "selected_rr_tp1": 1.2,
        "selected_rr_tp2": 2.0,
        "final_grade": "A" if decision == "ALLOW_PAPER" else "BLOCKED",
        "data_quality": {"level": "OK", "score": 1.0},
        "block_reasons": [] if decision != "BLOCK" else ["SAMPLE_BLOCK"],
        "warning_reasons": [] if decision != "WATCH" else ["SAMPLE_WARN"],
    }


def _plan() -> dict:
    return {
        "symbol": "BTCUSDT",
        "reason_codes": ["FLOW_CONFIRMED", "TREND_OK"],
    }


def test_dry_run_for_allow_paper():
    r = compute_telegram_paper_alert(_gate("ALLOW_PAPER"), _plan(), None, None, mode="DRY_RUN")
    assert r["alert_status"] == "DRY_RUN_READY"
    assert r["telegram_mode"] == "DRY_RUN"
    assert r["dry_run"] is True
    assert r["sent"] is False


def test_skip_when_watch():
    r = compute_telegram_paper_alert(_gate("WATCH"), _plan(), None, None, mode="DRY_RUN")
    assert r["alert_status"] == "SKIPPED"
    assert r["sent"] is False


def test_block_when_block():
    r = compute_telegram_paper_alert(_gate("BLOCK"), _plan(), None, None, mode="DRY_RUN")
    assert r["alert_status"] == "BLOCKED"
    assert r["sent"] is False


def test_send_mode_missing_env_safe(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    r = compute_telegram_paper_alert(_gate("ALLOW_PAPER"), _plan(), None, None, mode="SEND")
    assert r["alert_status"] in ("INVALID", "BLOCKED")
    assert r["sent"] is False
    assert "TELEGRAM_ENV_MISSING" in r["reason_codes"]


def test_message_contains_paper_only():
    r = compute_telegram_paper_alert(_gate("ALLOW_PAPER"), _plan(), None, None, mode="DRY_RUN")
    assert "PAPER ONLY" in r["message_text"]
    assert "REAL TRADE DISABLED" in r["message_text"]


def test_message_contains_safe_to_open_real_trade_false():
    r = compute_telegram_paper_alert(_gate("ALLOW_PAPER"), _plan(), None, None, mode="DRY_RUN")
    assert "safe_to_open_real_trade=false" in r["message_text"]


def test_sent_false_in_dry_run():
    for d in ("ALLOW_PAPER", "WATCH", "BLOCK"):
        r = compute_telegram_paper_alert(_gate(d), _plan(), None, None, mode="DRY_RUN")
        assert r["sent"] is False
        assert r["dry_run"] is True


def test_safety_flags_always_false():
    cases = [_gate("ALLOW_PAPER"), _gate("WATCH"), _gate("BLOCK"), None]
    for g in cases:
        r = compute_telegram_paper_alert(g, _plan(), None, None, mode="DRY_RUN")
        s = r["execution_safety"]
        assert s["safe_to_open_real_trade"] is False
        assert s["private_api_used"] is False
        assert s["live_order_sent"] is False
    m = no_valid_output("X")["execution_safety"]
    assert m["safe_to_open_real_trade"] is False
    assert m["private_api_used"] is False
    assert m["live_order_sent"] is False


def test_reason_codes_not_empty():
    for d in ("ALLOW_PAPER", "WATCH", "BLOCK"):
        r = compute_telegram_paper_alert(_gate(d), _plan(), None, None, mode="DRY_RUN")
        assert len(r["reason_codes"]) > 0
    assert len(no_valid_output("X")["reason_codes"]) > 0


def test_feeds_next_includes_s20():
    r = compute_telegram_paper_alert(_gate("ALLOW_PAPER"), _plan(), None, None, mode="DRY_RUN")
    assert "S20_PAPER_LIFECYCLE_TRACKER" in r["feeds_next"]["next_blocks"]
    assert "S20_PAPER_LIFECYCLE_TRACKER" in no_valid_output("X")["feeds_next"]["next_blocks"]


def test_required_output_fields():
    r = compute_telegram_paper_alert(_gate("ALLOW_PAPER"), _plan(), None, None, mode="DRY_RUN")
    required = {
        "timestamp_utc", "block_id", "symbol", "source", "input_status",
        "alert_status", "telegram_mode", "message_text", "sent", "dry_run",
        "decision", "side", "entry_price", "stop_loss", "tp1", "tp2",
        "rr_tp1", "rr_tp2", "final_grade", "reason_summary", "safety_summary",
        "data_quality", "reason_codes", "feeds_next", "execution_safety",
    }
    assert required <= set(r.keys())


def test_missing_decision_gate_invalid():
    r = compute_telegram_paper_alert(None, None, None, None, mode="DRY_RUN")
    assert r["alert_status"] == "INVALID"
    assert r["sent"] is False


def test_append_only_persistence_and_outputs(tmp_s19, monkeypatch):
    import src.simple.telegram_paper_alert_engine as eng

    gate_p = tmp_s19 / "gate.json"
    plan_p = tmp_s19 / "plan.json"
    gate_p.write_text(json.dumps(_gate("ALLOW_PAPER")), encoding="utf-8")
    plan_p.write_text(json.dumps(_plan()), encoding="utf-8")

    log_path = tmp_s19 / "telegram_paper_alert_history.jsonl"

    monkeypatch.setattr(eng, "DECISION_GATE_PATH", gate_p)
    monkeypatch.setattr(eng, "TRADE_PLAN_PATH", plan_p)
    monkeypatch.setattr(eng, "SCENARIO_TRIGGER_PATH", tmp_s19 / "no_trig.json")
    monkeypatch.setattr(eng, "SETUP_CONTEXT_PATH", tmp_s19 / "no_ctx.json")
    monkeypatch.setattr(eng, "ALERT_PATH", tmp_s19 / "latest_telegram_paper_alert.json")
    monkeypatch.setattr(eng, "S19_STATE_PATH", tmp_s19 / "s19_state.json")
    monkeypatch.setattr(eng, "ALERT_LOG_PATH", log_path)
    monkeypatch.setattr(eng, "REPORT_PATH", tmp_s19 / "report.md")

    run_telegram_paper_alert_engine(mode="DRY_RUN")
    run_telegram_paper_alert_engine(mode="DRY_RUN")
    run_telegram_paper_alert_engine(mode="DRY_RUN")

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert (tmp_s19 / "latest_telegram_paper_alert.json").exists()
    assert (tmp_s19 / "s19_state.json").exists()
    assert (tmp_s19 / "report.md").exists()
