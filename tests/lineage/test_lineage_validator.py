from __future__ import annotations

from src.lineage.lineage_validator import validate_lineage_nodes


def _node(
    lineage_id: str,
    node_type: str,
    parent_ids: list[str],
    *,
    ts: str = "2026-01-01T00:00:00Z",
    source_block: str = "TEST_BLOCK",
    outcome_status: str | None = None,
) -> dict:
    return {
        "lineage_id": lineage_id,
        "node_type": node_type,
        "source_block": source_block,
        "timestamp_utc": ts,
        "symbol": "BTCUSDT",
        "parent_lineage_ids": parent_ids,
        "child_lineage_ids": [],
        "context_id": "ctx",
        "data_quality": "OK",
        "reason_codes": [],
        "feeds_next": [],
        "source_file": "tests/source.json",
        "source_record_id": lineage_id,
        "hash_payload": "abc",
        "outcome_status": outcome_status,
    }


def test_missing_required_field_is_detected() -> None:
    raw = _node("LIN_RAW", "raw_event", [])
    raw.pop("source_block")
    result = validate_lineage_nodes([raw])
    assert any(item["lineage_id"] == "LIN_RAW" and item["field"] == "source_block" for item in result["missing_required_fields"])


def test_orphan_outcome_is_detected() -> None:
    orphan_outcome = _node("LIN_OUT", "outcome", [])
    result = validate_lineage_nodes([orphan_outcome])
    assert "LIN_OUT" in result["orphan_outcomes"]


def test_orphan_edge_row_is_detected() -> None:
    edge = _node("LIN_EDGE", "edge_row", ["LIN_OUT"])
    out = _node("LIN_OUT", "outcome", ["LIN_PAPER"], outcome_status="OPEN")
    paper = _node("LIN_PAPER", "paper_trade", ["LIN_DECISION"])
    decision = _node("LIN_DECISION", "decision", ["LIN_PLAN"])
    plan = _node("LIN_PLAN", "trade_plan", ["LIN_SIGNAL"])
    signal = _node("LIN_SIGNAL", "entry_trigger", ["LIN_SETUP"])
    setup = _node("LIN_SETUP", "setup_candidate", ["LIN_SCENARIO"])
    scenario = _node("LIN_SCENARIO", "scenario", ["LIN_MARKET"])
    market = _node("LIN_MARKET", "market_state", ["LIN_STRUCTURE"])
    structure = _node("LIN_STRUCTURE", "structure", ["LIN_LIQ"])
    liquidity = _node("LIN_LIQ", "liquidity", ["LIN_FP"])
    footprint = _node("LIN_FP", "footprint", ["LIN_DNA"])
    dna = _node("LIN_DNA", "candle_dna", ["LIN_EVID"])
    evidence = _node("LIN_EVID", "evidence", ["LIN_RAW"])
    raw = _node("LIN_RAW", "raw_event", [])
    result = validate_lineage_nodes([raw, evidence, dna, footprint, liquidity, structure, market, scenario, setup, signal, plan, decision, paper, out, edge])
    assert "LIN_EDGE" in result["orphan_edge_rows"]


def test_duplicate_lineage_id_is_detected() -> None:
    n1 = _node("LIN_DUP", "raw_event", [])
    n2 = _node("LIN_DUP", "raw_event", [])
    result = validate_lineage_nodes([n1, n2])
    assert "LIN_DUP" in result["duplicate_lineage_ids"]


def test_circular_lineage_is_detected() -> None:
    a = _node("LIN_A", "evidence", ["LIN_B"])
    b = _node("LIN_B", "candle_dna", ["LIN_A"])
    result = validate_lineage_nodes([a, b])
    assert result["circular_links"]


def test_valid_parent_child_chain_passes_core_checks() -> None:
    raw = _node("LIN_RAW", "raw_event", [])
    evidence = _node("LIN_EVID", "evidence", ["LIN_RAW"])
    result = validate_lineage_nodes([raw, evidence])
    assert not result["broken_parent_links"]
    assert not result["duplicate_lineage_ids"]
    assert not result["circular_links"]

