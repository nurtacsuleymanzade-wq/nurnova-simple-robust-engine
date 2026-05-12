"""Tests for S24 Production Observer."""

from __future__ import annotations

import json
import pathlib
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from src.simple.production_observer import (
    BLOCK_ID,
    FEEDS_NEXT,
    SAFETY,
    run_one_cycle,
    run_observer_loop,
    _utc_now,
    _append_jsonl,
    _write_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _fake_brain_result() -> dict:
    return {
        "brain_status": "READY",
        "brain_mode": "OBSERVER_MODE",
        "data_quality": {"level": "OK", "score": 0.9},
        "primary_reading": {"decision": "WATCH"},
        "alert_summary": {"alert_status": "DRY_RUN"},
        "edge_summary": {"edge_status": "VALID"},
        "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
    }


def _module_results_map(brain_result: dict | None = None) -> dict:
    """Map label -> result for mock chain."""
    base = {
        "S12_FLOW_STATE": {"ok": True},
        "S13_FLOW_EVIDENCE": {"ok": True},
        "S14_FLOW_PERSISTENCE": {"ok": True},
        "S15_SETUP_CONTEXT": {"ok": True},
        "S16_SCENARIO_ENTRY": {"ok": True},
        "S17_TRADE_PLAN": {"ok": True},
        "S18_DECISION_GATE": {"ok": True},
        "S19_TELEGRAM_ALERT": {"ok": True},
        "S20_PAPER_LIFECYCLE": {"ok": True},
        "S21_OUTCOME_MONITOR": {"ok": True},
        "S25_TELEGRAM_FOLLOWUP": {"ok": True},
        "S22_EDGE_MATRIX_V2": {"ok": True},
        "S23_SIMPLE_BRAIN_V2": brain_result or _fake_brain_result(),
    }
    return base


def test_s24_integration_includes_s25():
    from src.simple.production_observer import _MODULE_CHAIN

    labels = [label for _, _, label in _MODULE_CHAIN]
    assert "S25_TELEGRAM_FOLLOWUP" in labels
    assert labels.index("S21_OUTCOME_MONITOR") < labels.index("S25_TELEGRAM_FOLLOWUP") < labels.index("S22_EDGE_MATRIX_V2")


# ---------------------------------------------------------------------------
# run_one_cycle — basic contract
# ---------------------------------------------------------------------------

class TestRunOneCycle:
    def _patched_cycle(self, module_results: dict | None = None, failing: list[str] | None = None):
        """Run run_one_cycle with all modules mocked."""
        results = module_results or _module_results_map()
        failing = failing or []

        def fake_run_module(module_path, func_name, label, dry_run_alerts):
            if label in failing:
                return label, None, f"Simulated failure for {label}"
            result = results.get(label, {"ok": True})
            return label, result, None

        with patch("src.simple.production_observer._run_module", side_effect=fake_run_module):
            return run_one_cycle(cycle_count=1, dry_run_alerts=True)

    def test_returns_dict_with_required_fields(self):
        record = self._patched_cycle()
        required = [
            "timestamp_utc", "block_id", "symbol", "observer_status", "loop_status",
            "cycle_count", "last_cycle_started_utc", "last_cycle_finished_utc",
            "last_cycle_duration_seconds", "modules_run", "modules_failed",
            "latest_brain_status", "latest_brain_mode", "latest_decision",
            "latest_alert_status", "latest_edge_status", "systemd_ready",
            "restart_safe", "disk_safety", "data_quality", "reason_codes",
            "execution_safety", "feeds_next",
        ]
        for field in required:
            assert field in record, f"Missing field: {field}"

    def test_block_id(self):
        record = self._patched_cycle()
        assert record["block_id"] == BLOCK_ID

    def test_safety_flags_always_false(self):
        record = self._patched_cycle()
        es = record["execution_safety"]
        assert es["safe_to_open_real_trade"] is False
        assert es["private_api_used"] is False
        assert es["live_order_sent"] is False

    def test_systemd_ready_true(self):
        record = self._patched_cycle()
        assert record["systemd_ready"] is True
        assert record["restart_safe"] is True

    def test_feeds_next(self):
        record = self._patched_cycle()
        assert "SIMPLE_ROBUST_ENGINE_V1_COMPLETE" in record["feeds_next"]["next_blocks"]

    def test_observer_status_ok_all_modules_pass(self):
        record = self._patched_cycle()
        assert record["observer_status"] == "OK"
        assert len(record["modules_failed"]) == 0

    def test_missing_module_handled_safely(self):
        """A missing/failing module must not crash the cycle."""
        record = self._patched_cycle(failing=["S13_FLOW_EVIDENCE"])
        assert record["observer_status"] in ("DEGRADED", "CRITICAL")
        failed_labels = [f["module"] for f in record["modules_failed"]]
        assert "S13_FLOW_EVIDENCE" in failed_labels

    def test_multiple_failures_recorded(self):
        failing = ["S13_FLOW_EVIDENCE", "S15_SETUP_CONTEXT", "S22_EDGE_MATRIX_V2"]
        record = self._patched_cycle(failing=failing)
        failed_labels = [f["module"] for f in record["modules_failed"]]
        for lbl in failing:
            assert lbl in failed_labels

    def test_reason_codes_non_empty(self):
        record = self._patched_cycle()
        assert len(record["reason_codes"]) > 0

    def test_brain_status_extracted(self):
        record = self._patched_cycle()
        assert record["latest_brain_status"] == "READY"
        assert record["latest_brain_mode"] == "OBSERVER_MODE"

    def test_cycle_count_stored(self):
        def fake_run_module(module_path, func_name, label, dry_run_alerts):
            if label == "S23_SIMPLE_BRAIN_V2":
                return label, _fake_brain_result(), None
            return label, {"ok": True}, None

        with patch("src.simple.production_observer._run_module", side_effect=fake_run_module):
            r = run_one_cycle(cycle_count=42, dry_run_alerts=True)
        assert r["cycle_count"] == 42


# ---------------------------------------------------------------------------
# Finite cycles test (integration-style with file I/O)
# ---------------------------------------------------------------------------

class TestFiniteCycles:
    def test_finite_cycles_create_heartbeat_and_history(self, tmp_path, monkeypatch):
        """run_observer_loop with max_cycles=2 must create heartbeat and history."""
        import src.simple.production_observer as obs_mod

        state_dir = tmp_path / "state" / "simple"
        data_dir = tmp_path / "data" / "simple"
        logs_dir = tmp_path / "logs" / "simple"
        reports_dir = tmp_path / "reports" / "simple"
        state_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        logs_dir.mkdir(parents=True)
        reports_dir.mkdir(parents=True)

        monkeypatch.setattr(obs_mod, "LATEST_STATE_PATH", state_dir / "latest_production_observer.json")
        monkeypatch.setattr(obs_mod, "S24_STATE_PATH", state_dir / "s24_production_observer_state.json")
        monkeypatch.setattr(obs_mod, "HISTORY_PATH", data_dir / "production_observer_history.jsonl")
        monkeypatch.setattr(obs_mod, "LOG_PATH", logs_dir / "production_observer.log")
        monkeypatch.setattr(obs_mod, "REPORT_PATH", reports_dir / "s24_production_observer_latest_report.md")

        def fake_run_module(module_path, func_name, label, dry_run_alerts):
            if label == "S23_SIMPLE_BRAIN_V2":
                return label, _fake_brain_result(), None
            return label, {"ok": True}, None

        with patch("src.simple.production_observer._run_module", side_effect=fake_run_module):
            run_observer_loop(interval_seconds=0, dry_run_alerts=True, max_cycles=2)

        latest = obs_mod.LATEST_STATE_PATH
        history = obs_mod.HISTORY_PATH
        report = obs_mod.REPORT_PATH

        assert latest.exists(), "Heartbeat/latest state file must exist"
        assert history.exists(), "History JSONL must exist"
        assert report.exists(), "Report file must exist"

        # History must have 2 lines (append-only)
        lines = [l for l in history.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
        assert len(lines) == 2, f"Expected 2 history entries, got {len(lines)}"

        # Each line must be valid JSON with required fields
        for line in lines:
            rec = json.loads(line)
            assert rec["block_id"] == BLOCK_ID
            assert rec["execution_safety"]["safe_to_open_real_trade"] is False

    def test_history_append_only(self, tmp_path, monkeypatch):
        """Each cycle appends a new line; prior lines must not change."""
        import src.simple.production_observer as obs_mod

        state_dir = tmp_path / "state" / "simple"
        data_dir = tmp_path / "data" / "simple"
        logs_dir = tmp_path / "logs" / "simple"
        reports_dir = tmp_path / "reports" / "simple"
        for d in (state_dir, data_dir, logs_dir, reports_dir):
            d.mkdir(parents=True)

        monkeypatch.setattr(obs_mod, "LATEST_STATE_PATH", state_dir / "latest_production_observer.json")
        monkeypatch.setattr(obs_mod, "S24_STATE_PATH", state_dir / "s24_production_observer_state.json")
        monkeypatch.setattr(obs_mod, "HISTORY_PATH", data_dir / "production_observer_history.jsonl")
        monkeypatch.setattr(obs_mod, "LOG_PATH", logs_dir / "production_observer.log")
        monkeypatch.setattr(obs_mod, "REPORT_PATH", reports_dir / "s24_production_observer_latest_report.md")

        def fake_run_module(module_path, func_name, label, dry_run_alerts):
            return label, {"ok": True}, None

        with patch("src.simple.production_observer._run_module", side_effect=fake_run_module):
            run_observer_loop(interval_seconds=0, dry_run_alerts=True, max_cycles=3)

        lines = obs_mod.HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        cycle_nums = [json.loads(l)["cycle_count"] for l in lines]
        assert cycle_nums == [1, 2, 3]


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    def test_safety_dict_constants(self):
        assert SAFETY["safe_to_open_real_trade"] is False
        assert SAFETY["private_api_used"] is False
        assert SAFETY["live_order_sent"] is False

    def test_no_private_api_in_module_chain(self):
        from src.simple.production_observer import _MODULE_CHAIN
        for module_path, func_name, label in _MODULE_CHAIN:
            assert "private" not in module_path.lower()
            assert "private" not in func_name.lower()
            assert "order" not in func_name.lower() or "paper" in func_name.lower()

    def test_run_one_cycle_safety_never_true(self):
        def fake_run_module(module_path, func_name, label, dry_run_alerts):
            return label, {"safe_to_open_real_trade": True}, None  # attempt to inject True

        with patch("src.simple.production_observer._run_module", side_effect=fake_run_module):
            record = run_one_cycle(cycle_count=1)

        assert record["execution_safety"]["safe_to_open_real_trade"] is False


# ---------------------------------------------------------------------------
# Systemd scripts content checks
# ---------------------------------------------------------------------------

class TestSystemdScripts:
    _SCRIPTS_DIR = pathlib.Path(__file__).parents[2] / "scripts"

    def test_install_script_exists(self):
        assert (self._SCRIPTS_DIR / "simple_install_systemd.sh").exists()

    def test_uninstall_script_exists(self):
        assert (self._SCRIPTS_DIR / "simple_uninstall_systemd.sh").exists()

    def test_status_script_exists(self):
        assert (self._SCRIPTS_DIR / "simple_status.sh").exists()

    def test_install_contains_service_name(self):
        content = (self._SCRIPTS_DIR / "simple_install_systemd.sh").read_text(encoding="utf-8")
        assert "nurnova-simple-observer" in content

    def test_install_contains_correct_run_command(self):
        content = (self._SCRIPTS_DIR / "simple_install_systemd.sh").read_text(encoding="utf-8")
        assert "run_s24_production_observer" in content
        assert "--dry-run-alerts" in content

    def test_install_restart_always(self):
        content = (self._SCRIPTS_DIR / "simple_install_systemd.sh").read_text(encoding="utf-8")
        assert "Restart=always" in content

    def test_uninstall_contains_stop_disable_remove(self):
        content = (self._SCRIPTS_DIR / "simple_uninstall_systemd.sh").read_text(encoding="utf-8")
        assert "stop" in content
        assert "disable" in content
        assert "rm -f" in content or "remove" in content.lower()

    def test_status_script_contains_diagnostics(self):
        content = (self._SCRIPTS_DIR / "simple_status.sh").read_text(encoding="utf-8")
        assert "systemctl status" in content
        assert "latest_production_observer" in content
        assert "journalctl" in content
        assert "du " in content or "disk" in content.lower()
        assert "ps aux" in content or "process" in content.lower()
