from __future__ import annotations

import inspect
import json
import pathlib
import shutil
import tempfile

from src.lineage.run_edge_source_outcome_mapping_audit import run_edge_source_outcome_mapping_audit
from src.simple import edge_matrix_v2 as em


def _rec(*, status: str, result: str, lifecycle_id: str | None = "lc-001", outcome_id: str | None = None) -> dict:
    payload = {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "block_id": "S21_OUTCOME_MONITOR",
        "symbol": "BTCUSDT",
        "outcome_status": status,
        "outcome_result": result,
        "lifecycle_id": lifecycle_id,
        "side": "LONG",
        "realized_r": 1.0 if result in {"TP1", "TP2"} else -1.0 if result == "SL" else None,
    }
    if outcome_id is not None:
        payload["outcome_id"] = outcome_id
    return payload


def _setup_paths(tmp: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(em, "STATE_DIR", tmp / "state")
    monkeypatch.setattr(em, "DATA_DIR", tmp / "data")
    monkeypatch.setattr(em, "REPORTS_DIR", tmp / "reports")
    monkeypatch.setattr(em, "OUTCOME_HISTORY_PATH", tmp / "data" / "outcome_monitor_history.jsonl")
    monkeypatch.setattr(em, "LATEST_OUTCOME_PATH", tmp / "state" / "latest_outcome_monitor.json")
    monkeypatch.setattr(em, "LATEST_MATRIX_PATH", tmp / "state" / "latest_edge_matrix_v2.json")
    monkeypatch.setattr(em, "S22_STATE_PATH", tmp / "state" / "s22_edge_matrix_v2_state.json")
    monkeypatch.setattr(em, "MATRIX_HISTORY_PATH", tmp / "data" / "edge_matrix_v2_history.jsonl")
    monkeypatch.setattr(em, "REPORT_PATH", tmp / "reports" / "s22_edge_matrix_v2_latest_report.md")
    (tmp / "state").mkdir(parents=True, exist_ok=True)
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    (tmp / "reports").mkdir(parents=True, exist_ok=True)


def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_closed_outcome_produces_edge_row_with_source_mapping(monkeypatch) -> None:
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        _setup_paths(tmp, monkeypatch)
        _write_jsonl(em.OUTCOME_HISTORY_PATH, [_rec(status="CLOSED", result="TP2", lifecycle_id="lc-closed")])
        result = em.run_edge_matrix_v2()
        assert result["edge_data_status"] == "EDGE_DATA_AVAILABLE"
        lines = em.MATRIX_HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
        row = json.loads(lines[-1])
        assert row["edge_source_type"] == "CLOSED_OUTCOME"
        assert row["source_outcome_id"].startswith("OUT_")
        assert row["parent_outcome_id"] == "lc-closed"
        assert row["parent_lineage_ids"] == [row["outcome_lineage_id"]]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_open_or_timeout_outcomes_do_not_produce_main_edge_rows(monkeypatch) -> None:
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        _setup_paths(tmp, monkeypatch)
        _write_jsonl(
            em.OUTCOME_HISTORY_PATH,
            [
                _rec(status="OPEN", result="STILL_OPEN", lifecycle_id="lc-open"),
                _rec(status="CLOSED", result="TIMEOUT", lifecycle_id="lc-timeout"),
            ],
        )
        result = em.run_edge_matrix_v2()
        assert result["edge_data_status"] == "NO_EDGE_DATA"
        assert "NO_CLOSED_OUTCOMES_FOR_EDGE" in result["reason_codes"]
        if em.MATRIX_HISTORY_PATH.exists():
            assert em.MATRIX_HISTORY_PATH.read_text(encoding="utf-8").strip() == ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_outcome_id_missing_uses_deterministic_id(monkeypatch) -> None:
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        _setup_paths(tmp, monkeypatch)
        rec = _rec(status="CLOSED", result="TP1", lifecycle_id="lc-det", outcome_id=None)
        _write_jsonl(em.OUTCOME_HISTORY_PATH, [rec])
        em.run_edge_matrix_v2()
        em.run_edge_matrix_v2()
        lines = [json.loads(x) for x in em.MATRIX_HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()]
        assert len(lines) == 2
        assert lines[0]["source_outcome_id"] == lines[1]["source_outcome_id"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_closed_outcome_produces_no_edge_data_state(monkeypatch) -> None:
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        _setup_paths(tmp, monkeypatch)
        _write_jsonl(em.OUTCOME_HISTORY_PATH, [_rec(status="NO_OUTCOME", result="NO_LIFECYCLE", lifecycle_id=None)])
        result = em.run_edge_matrix_v2()
        assert result["edge_data_status"] == "NO_EDGE_DATA"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_deterministic_id_helpers_do_not_use_hash_uuid_or_runtime_now() -> None:
    source_id_fn = inspect.getsource(em._deterministic_source_outcome_id)
    lineage_id_fn = inspect.getsource(em._deterministic_outcome_lineage_id)
    joined = f"{source_id_fn}\n{lineage_id_fn}".lower()
    assert "hash(" not in joined
    assert "uuid" not in joined
    assert "datetime.now(" not in joined


def test_mapping_audit_reports_no_edge_data_when_no_closed(tmp_path: pathlib.Path) -> None:
    (tmp_path / "data/simple").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state/simple").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state/lineage").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports/lineage").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/simple/outcome_monitor_history.jsonl").write_text(
        json.dumps(_rec(status="OPEN", result="STILL_OPEN", lifecycle_id="lc-open")) + "\n",
        encoding="utf-8",
    )
    payload = run_edge_source_outcome_mapping_audit(tmp_path)
    assert payload["closed_outcomes_found"] == 0
    assert payload["outcome_to_edge_link_status"] == "FAIL"
    assert (tmp_path / "state/lineage/latest_edge_source_outcome_mapping.json").exists()
    assert (tmp_path / "reports/lineage/edge_source_outcome_mapping_report.md").exists()

