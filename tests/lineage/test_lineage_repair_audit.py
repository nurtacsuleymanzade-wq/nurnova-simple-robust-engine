from __future__ import annotations

import json
from pathlib import Path

from src.lineage.run_lineage_repair_audit import run_lineage_repair_audit


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def test_repair_audit_required_fields_and_outputs(tmp_path: Path) -> None:
    (tmp_path / "state/lineage").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/simple").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state/simple").mkdir(parents=True, exist_ok=True)

    # before audit snapshot
    (tmp_path / "state/lineage/latest_lineage_audit.json").write_text(
        json.dumps({"lineage_health_status": "FAIL"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # orphan outcome (no matching paper parent)
    _append_jsonl(
        tmp_path / "data/simple/outcome_monitor_history.jsonl",
        {
            "timestamp_utc": "2026-05-18T00:00:00Z",
            "symbol": "BTCUSDT",
            "outcome_id": "OUT_ORPHAN",
            "outcome_status": "CLOSED",
            "lineage_id": "LIN_OUT_DUP",
        },
    )
    # duplicate lineage id with conflicting payload
    _append_jsonl(
        tmp_path / "data/simple/outcome_monitor_history.jsonl",
        {
            "timestamp_utc": "2026-05-18T00:00:01Z",
            "symbol": "BTCUSDT",
            "outcome_id": "OUT_DUP_2",
            "outcome_status": "CLOSED",
            "lineage_id": "LIN_OUT_DUP",
            "extra": "different_payload",
        },
    )

    # one valid edge -> closed, one invalid edge -> open/missing
    _append_jsonl(
        tmp_path / "data/simple/edge_matrix_v2_history.jsonl",
        {"timestamp_utc": "2026-05-18T00:00:02Z", "symbol": "BTCUSDT", "source_outcome_id": "OUT_ORPHAN", "lineage_id": "LIN_EDGE_1"},
    )
    _append_jsonl(
        tmp_path / "data/simple/edge_matrix_v2_history.jsonl",
        {"timestamp_utc": "2026-05-18T00:00:03Z", "symbol": "BTCUSDT", "source_outcome_id": "OUT_MISSING", "lineage_id": "LIN_EDGE_2"},
    )

    payload = run_lineage_repair_audit(tmp_path)

    required = {
        "timestamp_utc",
        "block_id",
        "lineage_health_before",
        "lineage_health_after_estimate",
        "closed_outcome_count",
        "edge_rows_total",
        "edge_rows_linked_to_closed_outcome",
        "edge_rows_invalid_without_closed_outcome",
        "orphan_outcomes_total",
        "orphan_outcomes_repairable",
        "orphan_outcomes_unrepairable",
        "duplicate_lineage_ids_total",
        "non_deterministic_id_risks_total",
        "outcome_to_edge_link_status",
        "next_action",
        "reason_codes",
    }
    assert required.issubset(set(payload.keys()))
    assert payload["edge_rows_total"] == 2
    assert payload["edge_rows_invalid_without_closed_outcome"] >= 1
    assert payload["orphan_outcomes_total"] >= 1
    assert payload["duplicate_lineage_ids_total"] >= 1

    assert (tmp_path / "state/lineage/latest_lineage_repair.json").exists()
    assert (tmp_path / "data/live/lineage_repair_events.jsonl").exists()
    assert (tmp_path / "reports/lineage/lineage_repair_latest_report.md").exists()

