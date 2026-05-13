from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import run_loop


def test_filter_duplicate_processes_excludes_current_children_and_helpers(monkeypatch):
    monkeypatch.setattr(run_loop.os, "getpid", lambda: 100)
    monkeypatch.setattr(run_loop, "_pid_alive", lambda pid: True)

    processes = [
        {"pid": 100, "parent_pid": 90, "cmdline": "python run_loop.py"},
        {"pid": 101, "parent_pid": 100, "cmdline": "python run_loop.py --child"},
        {"pid": 102, "parent_pid": 1, "cmdline": "bash -lc ps aux | grep run_loop.py"},
        {"pid": 103, "parent_pid": 1, "cmdline": "python run_loop.py"},
        {"pid": 104, "parent_pid": 103, "cmdline": "python run_loop.py --report"},
    ]

    duplicates = run_loop._filter_duplicate_processes(processes)

    assert duplicates == [
        {
            "pid": 103,
            "parent_pid": 1,
            "cmdline": "python run_loop.py",
            "source": "process_scan",
        }
    ]


def test_classify_duplicate_processes_ignores_self_lock_and_helper_children(monkeypatch):
    monkeypatch.setattr(run_loop.os, "getpid", lambda: 1180286)
    monkeypatch.setattr(run_loop, "_pid_alive", lambda pid: True)

    processes = [
        {"pid": 1180286, "parent_pid": 1, "cmdline": ".venv/bin/python run_loop.py"},
        {"pid": 1180300, "parent_pid": 1180286, "cmdline": ".venv/bin/python run_loop.py --report"},
        {"pid": 1180400, "parent_pid": 1, "cmdline": "python run_loop.py"},
    ]

    duplicates, metadata = run_loop._classify_duplicate_processes(
        processes,
        runtime_lock_pid=1180286,
    )

    assert duplicates == [
        {
            "pid": 1180400,
            "parent_pid": 1,
            "cmdline": "python run_loop.py",
            "source": "process_scan",
        }
    ]
    assert metadata["current_pid"] == 1180286
    assert metadata["runtime_lock_pid"] == 1180286
    assert metadata["scanned_pids"] == [1180286, 1180300, 1180400]
    assert metadata["ignored_self_pid"] == 1180286
    assert metadata["ignored_lock_pid"] == 1180286
    assert metadata["ignored_child_pids"] == [1180300]
    assert metadata["true_duplicate_pids"] == [1180400]
    assert metadata["duplicate_loop_detected"] is True


def test_classify_duplicate_processes_self_only_is_not_duplicate(monkeypatch):
    monkeypatch.setattr(run_loop.os, "getpid", lambda: 1180286)
    monkeypatch.setattr(run_loop, "_pid_alive", lambda pid: True)

    duplicates, metadata = run_loop._classify_duplicate_processes(
        [{"pid": 1180286, "parent_pid": 1, "cmdline": ".venv/bin/python run_loop.py"}],
        runtime_lock_pid=1180286,
    )

    assert duplicates == []
    assert metadata["ignored_self_pid"] == 1180286
    assert metadata["ignored_lock_pid"] == 1180286
    assert metadata["true_duplicate_pids"] == []
    assert metadata["duplicate_loop_detected"] is False


def test_acquire_runtime_lock_replaces_stale_dead_lock(monkeypatch, tmp_path):
    state_dir = tmp_path / "state" / "simple"
    lock_path = state_dir / "runtime_loop.lock"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": 99999,
                "started_at_utc": (
                    datetime.now(timezone.utc) - timedelta(minutes=10)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "heartbeat_utc": (
                    datetime.now(timezone.utc) - timedelta(minutes=10)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "cmdline": "python run_loop.py",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(run_loop, "STATE_DIR", state_dir)
    monkeypatch.setattr(run_loop, "LOCK_PATH", lock_path)
    monkeypatch.setattr(run_loop.os, "getpid", lambda: 1234)
    monkeypatch.setattr(run_loop.os, "getppid", lambda: 1)
    monkeypatch.setattr(run_loop, "_scan_run_loop_processes", lambda: ([{"pid": 1234, "parent_pid": 1, "cmdline": "python run_loop.py"}], []))
    monkeypatch.setattr(run_loop, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(run_loop, "_write_runtime_topology_report", lambda **kwargs: None)

    acquired, topology = run_loop._acquire_runtime_lock()

    assert acquired is True
    assert topology["duplicate_loop_detected"] is False
    assert topology["duplicate_loop_fixed"] is True
    assert topology["topology_snapshot"]["current_pid"] == 1234
    assert topology["topology_snapshot"]["runtime_lock_pid"] == 1234
    assert topology["topology_snapshot"]["ignored_self_pid"] == 1234
    assert topology["topology_snapshot"]["ignored_lock_pid"] == 1234
    assert topology["topology_snapshot"]["true_duplicate_pids"] == []
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock_payload["pid"] == 1234
    assert lock_payload["heartbeat_utc"]


def test_run_once_records_pipeline_failure(monkeypatch, tmp_path, capsys):
    failure_path = tmp_path / "latest_pipeline_failure.json"
    monkeypatch.setattr(run_loop, "LATEST_PIPELINE_FAILURE_PATH", failure_path)
    monkeypatch.setattr(
        run_loop.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=7,
            stdout="stdout details",
            stderr="Traceback: pipeline exploded",
        ),
    )

    result = run_loop.run_once()
    output = capsys.readouterr().out
    payload = json.loads(failure_path.read_text(encoding="utf-8"))

    assert result["error"] == "PIPELINE_SUBPROCESS_FAILED"
    assert result["returncode"] == 7
    assert "PIPELINE_SUBPROCESS_FAILED" in output
    assert "return_code=7" in output
    assert "Traceback: pipeline exploded" in output
    assert payload["return_code"] == 7
    assert payload["last_stdout"] == "stdout details"
    assert payload["last_stderr"] == "Traceback: pipeline exploded"
    assert payload["execution_safety"]["live_order_sent"] is False
