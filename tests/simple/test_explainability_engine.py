"""Tests for S26 Explainability Engine."""

from __future__ import annotations

import json
import pathlib
import shutil
import uuid

import pytest

from src.simple.explainability_engine import (
    BLOCK_ID,
    SAFETY,
    run_explainability_engine,
)

TMP_BASE = pathlib.Path("tmp_pytest_s26")


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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_json(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _base_flow_state(quality_state: str = "OK") -> dict:
    return {"quality_state": quality_state, "flow_label": "BULLISH_FLOW", "confidence": 0.75}


def _base_flow_evidence(flow_label: str = "BULLISH_FLOW", confidence: float = 0.75) -> dict:
    return {"flow_label": flow_label, "confidence": confidence}


def _base_flow_persistence() -> dict:
    return {"persistence_score": 0.8}


def _base_setup_context(valid: bool = True) -> dict:
    return {"setup_valid": valid, "direction": "LONG"}


def _base_scenario_trigger(state: str = "READY_FOR_ENTRY") -> dict:
    return {"trigger_state": state, "ready_for_entry": True}


def _base_trade_plan(status: str = "PLAN_READY") -> dict:
    return {"plan_status": status, "rr_tp1": 1.2, "rr_tp2": 1.8, "plan_reason_codes": ["VALID"]}


def _base_decision_gate(decision: str = "ALLOW_PAPER") -> dict:
    return {
        "decision": decision,
        "allowed_for_paper_alert": decision == "ALLOW_PAPER",
        "block_reasons": [] if decision != "BLOCK" else ["RR_TOO_LOW"],
        "data_quality": {"level": "OK", "score": 0.9},
    }


def _base_telegram_alert(status: str = "SENT", bot_token: bool = True, chat_id: bool = True) -> dict:
    return {
        "alert_status": status,
        "telegram_sent": status == "SENT",
        "bot_token_set": bot_token,
        "chat_id_set": chat_id,
    }


def _base_paper_lifecycle(status: str = "ACTIVE") -> dict:
    return {"lifecycle_status": status, "active_trade": status == "ACTIVE"}


def _base_telegram_followup(status: str = "SENT") -> dict:
    return {"followup_status": status, "event_type": "TP1_HIT"}


def _base_edge_matrix(status: str = "EDGE_CLAIM") -> dict:
    return {"edge_status": status, "win_rate": 0.6}


def _base_simple_brain() -> dict:
    return {
        "brain_status": "READY",
        "data_quality": {"level": "OK", "score": 0.9},
    }


def _write_all_inputs(sd: pathlib.Path, **overrides) -> None:
    defaults = {
        "latest_flow_state.json": _base_flow_state(),
        "latest_flow_evidence.json": _base_flow_evidence(),
        "latest_flow_persistence.json": _base_flow_persistence(),
        "latest_setup_context.json": _base_setup_context(),
        "latest_scenario_trigger.json": _base_scenario_trigger(),
        "latest_trade_plan.json": _base_trade_plan(),
        "latest_decision_gate.json": _base_decision_gate(),
        "latest_telegram_paper_alert.json": _base_telegram_alert(),
        "latest_paper_lifecycle.json": _base_paper_lifecycle(),
        "latest_outcome_monitor.json": {"outcome": "PENDING"},
        "latest_telegram_followup.json": _base_telegram_followup(),
        "latest_edge_matrix_v2.json": _base_edge_matrix(),
        "latest_simple_brain_v2.json": _base_simple_brain(),
    }
    defaults.update(overrides)
    for fname, data in defaults.items():
        _write_json(sd / fname, data)


# --------------------------------------------------------------------------- #
# Contract tests
# --------------------------------------------------------------------------- #

class TestRequiredFields:
    REQUIRED = [
        "timestamp_utc", "block_id", "symbol", "source", "input_status",
        "final_answer", "no_signal_reason", "block_stage", "block_chain",
        "failed_checks", "weak_signals", "closest_to_signal",
        "telegram_diagnosis", "lifecycle_diagnosis", "data_quality_diagnosis",
        "decision_diagnosis", "edge_diagnosis", "system_health_diagnosis",
        "recommended_next_fix", "confidence_to_next_signal",
        "data_quality", "reason_codes", "feeds_next", "execution_safety",
    ]

    def test_all_required_fields_present(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd)
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        for field in self.REQUIRED:
            assert field in result, f"Missing required field: {field}"

    def test_block_id(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["block_id"] == BLOCK_ID

    def test_reason_codes_not_empty(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert len(result["reason_codes"]) > 0


# --------------------------------------------------------------------------- #
# Safety invariants
# --------------------------------------------------------------------------- #

class TestSafetyInvariants:
    def test_safety_constants_are_false(self):
        assert SAFETY["safe_to_open_real_trade"] is False
        assert SAFETY["private_api_used"] is False
        assert SAFETY["live_order_sent"] is False

    def test_execution_safety_always_false(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        es = result["execution_safety"]
        assert es["safe_to_open_real_trade"] is False
        assert es["private_api_used"] is False
        assert es["live_order_sent"] is False

    def test_safety_not_mutated_by_inputs(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        # Write inputs with safe_to_open_real_trade=True to test injection resistance
        _write_all_inputs(sd, **{
            "latest_decision_gate.json": {
                **_base_decision_gate(),
                "execution_safety": {"safe_to_open_real_trade": True},
            }
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["execution_safety"]["safe_to_open_real_trade"] is False


# --------------------------------------------------------------------------- #
# no_signal_reason scenarios
# --------------------------------------------------------------------------- #

class TestNoSignalReasons:
    def test_explains_decision_block(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_decision_gate.json": _base_decision_gate("BLOCK"),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] == "DECISION_BLOCKED"
        assert result["block_stage"] == "S18_DECISION_GATE"
        assert any("decision=BLOCK" in fc for fc in result["failed_checks"])

    def test_explains_weak_flow_neutral(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_flow_evidence.json": _base_flow_evidence("NEUTRAL_FLOW", 0.5),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] in ("WEAK_FLOW", "LOW_CONFIDENCE")
        assert any("NEUTRAL_FLOW" in w for w in result["weak_signals"])

    def test_explains_low_confidence(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_flow_evidence.json": _base_flow_evidence("BULLISH_FLOW", 0.4),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] in ("WEAK_FLOW", "LOW_CONFIDENCE")
        assert any("flow_confidence" in w for w in result["weak_signals"])

    def test_explains_degraded_data(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_flow_state.json": _base_flow_state("DEGRADED"),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] in ("DEGRADED_DATA", "WEAK_FLOW")

    def test_explains_telegram_blocked_missing_env(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_telegram_paper_alert.json": _base_telegram_alert("BLOCKED", False, False),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] == "TELEGRAM_BLOCKED"
        assert result["block_stage"] == "S19_TELEGRAM_ALERT"
        assert "TELEGRAM_BOT_TOKEN_NOT_SET" in result["failed_checks"]
        assert "TELEGRAM_CHAT_ID_NOT_SET" in result["failed_checks"]

    def test_explains_telegram_dry_run(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_telegram_paper_alert.json": _base_telegram_alert("DRY_RUN", True, True),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] == "TELEGRAM_BLOCKED"
        assert "TELEGRAM_DRY_RUN_MODE" in result["failed_checks"]

    def test_explains_no_lifecycle(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_paper_lifecycle.json": _base_paper_lifecycle("NO_TRADE"),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] == "NO_LIFECYCLE"
        assert result["block_stage"] == "S20_PAPER_LIFECYCLE"

    def test_explains_no_lifecycle_followup(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_telegram_followup.json": {"followup_status": "NO_LIFECYCLE"},
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] in ("NO_LIFECYCLE",)
        assert any("NO_LIFECYCLE" in fc for fc in result["failed_checks"])

    def test_explains_no_edge_claim(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_edge_matrix_v2.json": _base_edge_matrix("NO_EDGE_CLAIM"),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] == "NO_EDGE_CLAIM"
        assert result["block_stage"] == "S22_EDGE_MATRIX_V2"

    def test_explains_plan_not_ready(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_trade_plan.json": _base_trade_plan("NOT_READY"),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] == "PLAN_NOT_READY"
        assert result["block_stage"] == "S17_TRADE_PLAN"

    def test_explains_no_trade_setup(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd, **{
            "latest_setup_context.json": _base_setup_context(valid=False),
        })
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["no_signal_reason"] == "NO_TRADE_SETUP"
        assert result["block_stage"] == "S15_SETUP_CONTEXT"


# --------------------------------------------------------------------------- #
# File output tests
# --------------------------------------------------------------------------- #

class TestFileOutputs:
    def test_writes_latest_json(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd)
        run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert (sd / "latest_explainability_report.json").exists()
        data = json.loads((sd / "latest_explainability_report.json").read_text(encoding="utf-8"))
        assert data["block_id"] == BLOCK_ID

    def test_writes_s26_state_json(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd)
        run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert (sd / "s26_explainability_state.json").exists()

    def test_appends_jsonl_history(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd)
        run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        hist = (dd / "explainability_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(hist) == 2
        for line in hist:
            rec = json.loads(line)
            assert rec["block_id"] == BLOCK_ID

    def test_writes_markdown_report(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_all_inputs(sd)
        run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        md = (rd / "s26_explainability_latest_report.md").read_text(encoding="utf-8")
        assert "S26 Explainability" in md
        assert "Why no Telegram signal?" in md
        assert "Where did the chain stop?" in md
        assert "closest missing condition" in md
        assert "fixed next" in md
        assert "system running" in md
        assert "Telegram configured" in md
        assert "safe_to_open_real_trade" in md
        assert "False" in md

    def test_no_state_files_does_not_crash(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        # No input files written at all
        result = run_explainability_engine(state_dir=sd, data_dir=dd, reports_dir=rd)
        assert result["block_id"] == BLOCK_ID
        assert result["execution_safety"]["safe_to_open_real_trade"] is False


# --------------------------------------------------------------------------- #
# S24 integration
# --------------------------------------------------------------------------- #

class TestS24Integration:
    def test_s24_module_chain_includes_s26(self):
        from src.simple.production_observer import _MODULE_CHAIN
        labels = [label for _, _, label in _MODULE_CHAIN]
        assert "S26_EXPLAINABILITY" in labels

    def test_s26_placed_after_s25_before_end(self):
        from src.simple.production_observer import _MODULE_CHAIN
        labels = [label for _, _, label in _MODULE_CHAIN]
        assert "S25_TELEGRAM_FOLLOWUP" in labels
        assert labels.index("S25_TELEGRAM_FOLLOWUP") < labels.index("S26_EXPLAINABILITY")
