"""Tests for S26A Full Chain Truth Audit."""

from __future__ import annotations

import json
import pathlib
import shutil
import uuid

import pytest

from src.simple.full_chain_truth_audit import (
    BLOCK_ID,
    SAFETY,
    run_full_chain_truth_audit,
)

TMP_BASE = pathlib.Path("tmp_pytest_s26a")

REQUIRED_FIELDS = [
    "timestamp_utc", "block_id", "symbol", "source", "audit_window",
    "system_running_status", "raw_data_audit", "one_second_bucket_audit",
    "candle_dna_audit", "mtf_audit", "market_structure_audit",
    "liquidity_audit", "scenario_audit", "setup_candidate_audit",
    "trade_plan_audit", "decision_gate_audit", "telegram_signal_audit",
    "lifecycle_audit", "outcome_audit", "edge_audit",
    "success_pattern_audit", "failure_pattern_audit",
    "bottleneck_summary", "no_signal_reason", "block_stage",
    "failed_checks", "recommended_next_fix", "final_answer",
    "data_quality", "reason_codes", "feeds_next", "execution_safety",
]


@pytest.fixture()
def tmp_dirs():
    uid = uuid.uuid4().hex
    base = TMP_BASE / uid
    sd = base / "state" / "simple"
    dd = base / "data" / "simple"
    rd = base / "reports" / "simple"
    for d in (sd, dd, rd):
        d.mkdir(parents=True, exist_ok=True)
    yield sd, dd, rd
    shutil.rmtree(base, ignore_errors=True)


def _write_json(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _flow_event(ts: str = "2026-05-11T12:00:00Z") -> dict:
    return {"timestamp_utc": ts, "price": 65000.0, "qty": 0.01}


def _flow_state(quality: str = "OK") -> dict:
    return {"quality_state": quality, "flow_label": "BULLISH_FLOW", "confidence": 0.8}


def _flow_evidence(flow_label: str = "BULLISH_FLOW", confidence: float = 0.8) -> dict:
    return {"flow_label": flow_label, "confidence": confidence, "quality_label": "OK"}


def _setup_ctx(valid: bool = True, direction: str = "LONG", confidence: float = 0.8) -> dict:
    return {"setup_valid": valid, "direction": direction, "confidence": confidence, "setup_label": "STRONG_LONG"}


def _trade_plan(status: str = "PLAN_READY", direction: str = "LONG", rr: float = 2.5) -> dict:
    return {"plan_status": status, "direction": direction, "rr_tp1": rr}


def _decision(decision: str = "ALLOW_PAPER", block_reasons: list | None = None) -> dict:
    return {"decision": decision, "block_reasons": block_reasons or [], "allowed_for_paper_alert": decision == "ALLOW_PAPER"}


def _tg_alert(status: str = "SENT", bot: bool = True, chat: bool = True) -> dict:
    return {"alert_status": status, "telegram_sent": status == "SENT", "bot_token_set": bot, "chat_id_set": chat}


def _lifecycle(status: str = "TP1_HIT") -> dict:
    return {"lifecycle_status": status, "active_trade": True}


def _outcome(outcome: str = "TP1_HIT", realized_r: float = 2.0) -> dict:
    return {"outcome": outcome, "realized_r": realized_r}


# --------------------------------------------------------------------------- #
# Core contract tests
# --------------------------------------------------------------------------- #

def test_handles_all_missing_files(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert isinstance(result, dict)
    for field in REQUIRED_FIELDS:
        assert field in result, f"Missing required field: {field}"


def test_safety_flags_always_false(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["execution_safety"]["safe_to_open_real_trade"] is False
    assert result["execution_safety"]["private_api_used"] is False
    assert result["execution_safety"]["live_order_sent"] is False


def test_block_id_correct(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["block_id"] == BLOCK_ID


def test_reason_codes_not_empty(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert isinstance(result["reason_codes"], list)
    assert len(result["reason_codes"]) >= 3


# --------------------------------------------------------------------------- #
# Raw data audit
# --------------------------------------------------------------------------- #

def test_detects_data_flowing_from_live_flow_events(tmp_dirs):
    sd, dd, rd = tmp_dirs
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(dd / "live_flow_events.jsonl", [_flow_event(ts) for _ in range(50)])
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["raw_data_audit"]["live_flow_event_count"] == 50
    assert result["raw_data_audit"]["data_flowing"] is True


def test_no_data_when_empty_events(tmp_dirs):
    sd, dd, rd = tmp_dirs
    _write_jsonl(dd / "live_flow_events.jsonl", [])
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["raw_data_audit"]["live_flow_event_count"] == 0
    assert result["raw_data_audit"]["data_flowing"] is False
    assert result["raw_data_audit"]["empty_or_stale_reason"] is not None


# --------------------------------------------------------------------------- #
# 1-second bucket audit
# --------------------------------------------------------------------------- #

def test_one_second_evidence_produced_when_state_exists(tmp_dirs):
    sd, dd, rd = tmp_dirs
    _write_json(sd / "latest_flow_evidence.json", _flow_evidence())
    _write_jsonl(dd / "flow_evidence_history.jsonl", [_flow_evidence() for _ in range(10)])
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["one_second_bucket_audit"]["one_second_evidence_produced"] is True
    assert result["one_second_bucket_audit"]["bucket_count"] == 10


def test_one_second_not_produced_when_missing(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["one_second_bucket_audit"]["one_second_evidence_produced"] is False


# --------------------------------------------------------------------------- #
# MTF audit reports NOT_IMPLEMENTED
# --------------------------------------------------------------------------- #

def test_mtf_not_implemented_when_no_files(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["mtf_audit"]["mtf_implemented"] is False
    assert result["mtf_audit"]["5m_state"] == "NOT_IMPLEMENTED_OR_NOT_PRODUCED"
    assert result["mtf_audit"]["15m_state"] == "NOT_IMPLEMENTED_OR_NOT_PRODUCED"
    assert result["mtf_audit"]["30m_state"] == "NOT_IMPLEMENTED_OR_NOT_PRODUCED"


# --------------------------------------------------------------------------- #
# Market structure and liquidity report NOT_IMPLEMENTED
# --------------------------------------------------------------------------- #

def test_market_structure_not_implemented_when_no_persistence(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["market_structure_audit"]["structure_available"] is False
    assert result["market_structure_audit"]["structure_label"] in ("NOT_IMPLEMENTED_OR_NOT_PRODUCED", None, "NOT_IMPLEMENTED_OR_NOT_PRODUCED")


def test_liquidity_not_implemented_when_no_data(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["liquidity_audit"]["liquidity_available"] is False


# --------------------------------------------------------------------------- #
# Setup candidate audit
# --------------------------------------------------------------------------- #

def test_counts_setup_context_records(tmp_dirs):
    sd, dd, rd = tmp_dirs
    records = [_setup_ctx(valid=True), _setup_ctx(valid=False), _setup_ctx(valid=True)]
    _write_jsonl(dd / "setup_context_history.jsonl", records)
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["setup_candidate_audit"]["setup_context_count"] == 3
    assert result["setup_candidate_audit"]["tradeable_count"] == 2
    assert result["setup_candidate_audit"]["no_trade_count"] == 1


# --------------------------------------------------------------------------- #
# Trade plan audit
# --------------------------------------------------------------------------- #

def test_counts_trade_plans(tmp_dirs):
    sd, dd, rd = tmp_dirs
    records = [
        _trade_plan("PLAN_READY"), _trade_plan("PLAN_READY"),
        _trade_plan("NO_PLAN"), _trade_plan("WATCH_ONLY"),
    ]
    _write_jsonl(dd / "trade_plan_history.jsonl", records)
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["trade_plan_audit"]["plan_count"] == 4
    assert result["trade_plan_audit"]["PLAN_READY"] == 2
    assert result["trade_plan_audit"]["NO_PLAN"] == 1
    assert result["trade_plan_audit"]["WATCH_ONLY"] == 1


# --------------------------------------------------------------------------- #
# Decision gate audit
# --------------------------------------------------------------------------- #

def test_counts_decision_gate_outcomes(tmp_dirs):
    sd, dd, rd = tmp_dirs
    records = [
        _decision("ALLOW_PAPER"), _decision("ALLOW_PAPER"),
        _decision("BLOCK", ["LOW_CONFIDENCE"]), _decision("BLOCK", ["LOW_RR"]),
        _decision("WATCH"),
    ]
    _write_jsonl(dd / "decision_gate_history.jsonl", records)
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    g = result["decision_gate_audit"]
    assert g["decision_record_count"] == 5
    assert g["ALLOW_PAPER"] == 2
    assert g["BLOCK"] == 2
    assert g["WATCH"] == 1


def test_detects_low_confidence_block(tmp_dirs):
    sd, dd, rd = tmp_dirs
    records = [_decision("BLOCK", ["LOW_CONFIDENCE"]) for _ in range(5)]
    _write_jsonl(dd / "decision_gate_history.jsonl", records)
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    block_reasons = [r["reason"] for r in result["decision_gate_audit"]["main_block_reasons"]]
    assert "LOW_CONFIDENCE" in block_reasons


# --------------------------------------------------------------------------- #
# Telegram audit
# --------------------------------------------------------------------------- #

def test_counts_telegram_attempts(tmp_dirs):
    sd, dd, rd = tmp_dirs
    records = [_tg_alert("SENT"), _tg_alert("SENT"), _tg_alert("BLOCKED"), _tg_alert("DRY_RUN")]
    _write_jsonl(dd / "telegram_paper_alert_history.jsonl", records)
    _write_json(sd / "latest_telegram_paper_alert.json", _tg_alert("SENT"))
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    tg = result["telegram_signal_audit"]
    assert tg["telegram_alert_attempts"] == 4
    assert tg["SENT"] == 2
    assert tg["SKIPPED_BLOCKED_INVALID"] == 2


# --------------------------------------------------------------------------- #
# Lifecycle audit
# --------------------------------------------------------------------------- #

def test_counts_lifecycle_outcomes(tmp_dirs):
    sd, dd, rd = tmp_dirs
    records = [
        _lifecycle("TP1_HIT"), _lifecycle("TP2_HIT"),
        _lifecycle("SL_HIT"), _lifecycle("INVALIDATED"), _lifecycle("OPEN"),
    ]
    _write_jsonl(dd / "paper_lifecycle_history.jsonl", records)
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    lc = result["lifecycle_audit"]
    assert lc["lifecycle_record_count"] == 5
    assert lc["TP1_HIT"] == 1
    assert lc["TP2_HIT"] == 1
    assert lc["SL_HIT"] == 1
    assert lc["INVALIDATED"] == 1
    assert lc["OPEN"] == 1


def test_no_lifecycle_reason_when_empty(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["lifecycle_audit"]["no_lifecycle_reason"] is not None


# --------------------------------------------------------------------------- #
# Bottleneck
# --------------------------------------------------------------------------- #

def test_produces_bottleneck_summary(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert isinstance(result["bottleneck_summary"], str)
    assert len(result["bottleneck_summary"]) > 0


def test_bottleneck_is_s12_when_no_data(tmp_dirs):
    sd, dd, rd = tmp_dirs
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert "S12" in result["bottleneck_summary"]


def test_bottleneck_advances_when_chain_progresses(tmp_dirs):
    sd, dd, rd = tmp_dirs
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(dd / "live_flow_events.jsonl", [_flow_event(ts) for _ in range(10)])
    _write_json(sd / "latest_flow_state.json", _flow_state())
    _write_json(sd / "latest_flow_evidence.json", _flow_evidence())
    _write_jsonl(dd / "flow_evidence_history.jsonl", [_flow_evidence() for _ in range(5)])
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert "S12" not in result["bottleneck_summary"]


# --------------------------------------------------------------------------- #
# Output files
# --------------------------------------------------------------------------- #

def test_writes_latest_json(tmp_dirs):
    sd, dd, rd = tmp_dirs
    run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert (sd / "latest_full_chain_truth_audit.json").exists()
    assert (sd / "s26a_full_chain_truth_audit_state.json").exists()


def test_writes_markdown_report(tmp_dirs):
    sd, dd, rd = tmp_dirs
    run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    report = rd / "s26a_full_chain_truth_audit_latest_report.md"
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "S26A Full Chain Truth Audit" in content
    assert "Bottleneck" in content
    assert "Final Answer" in content


def test_appends_jsonl_history(tmp_dirs):
    sd, dd, rd = tmp_dirs
    run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    hist = dd / "full_chain_truth_audit_history.jsonl"
    assert hist.exists()
    lines = [l for l in hist.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2


# --------------------------------------------------------------------------- #
# Safety invariants preserved
# --------------------------------------------------------------------------- #

def test_safety_invariants_with_full_happy_path(tmp_dirs):
    sd, dd, rd = tmp_dirs
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(dd / "live_flow_events.jsonl", [_flow_event(ts) for _ in range(20)])
    _write_json(sd / "latest_flow_state.json", _flow_state())
    _write_json(sd / "latest_flow_evidence.json", _flow_evidence())
    _write_json(sd / "latest_setup_context.json", _setup_ctx())
    _write_json(sd / "latest_trade_plan.json", _trade_plan())
    _write_json(sd / "latest_decision_gate.json", _decision("ALLOW_PAPER"))
    _write_json(sd / "latest_telegram_paper_alert.json", _tg_alert("SENT"))
    result = run_full_chain_truth_audit(state_dir=sd, data_dir=dd, reports_dir=rd)
    assert result["execution_safety"]["safe_to_open_real_trade"] is False
    assert result["execution_safety"]["private_api_used"] is False
    assert result["execution_safety"]["live_order_sent"] is False


# --------------------------------------------------------------------------- #
# S24 integration — S26A must be in module chain
# --------------------------------------------------------------------------- #

def test_s24_module_chain_includes_s26a():
    from src.simple.production_observer import _MODULE_CHAIN
    labels = [label for _, _, label in _MODULE_CHAIN]
    assert "S26A_FULL_CHAIN_TRUTH_AUDIT" in labels, (
        "S26A_FULL_CHAIN_TRUTH_AUDIT not found in S24 _MODULE_CHAIN"
    )
