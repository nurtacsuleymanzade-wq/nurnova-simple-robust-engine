from __future__ import annotations

from src.lineage.lineage_builder import build_lineage_id, build_lineage_node, build_payload_hash


def test_deterministic_id_is_stable_for_same_input() -> None:
    payload_hash = build_payload_hash({"k": "v", "n": 1})
    kwargs = {
        "symbol": "BTCUSDT",
        "node_type": "trade_plan",
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "source_block": "S17_TRADE_PLAN_ENGINE",
        "source_file": "state/simple/latest_trade_plan.json",
        "source_record_id": "plan_001",
        "parent_lineage_ids": ["LIN_PARENT"],
        "hash_payload": payload_hash,
    }
    assert build_lineage_id(**kwargs) == build_lineage_id(**kwargs)


def test_parent_missing_marks_invalid_lineage() -> None:
    node = build_lineage_node(
        node_type="outcome",
        source_block="S21_OUTCOME_MONITOR",
        source_file="state/simple/latest_outcome_monitor.json",
        source_record={"timestamp_utc": "2026-01-01T00:00:01Z", "symbol": "BTCUSDT"},
        parent_lineage_ids=[],
        source_record_id="outcome_001",
    )
    assert node["lineage_status"] == "INVALID_LINEAGE"
    assert "INVALID_LINEAGE_PARENT_MISSING" in node["reason_codes"]

