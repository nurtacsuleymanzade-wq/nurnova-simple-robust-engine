from __future__ import annotations

from pathlib import Path

from src.lineage.lineage_graph_engine import build_lineage_graph_report
from src.lineage.run_lineage_audit import run_lineage_audit


def _node(
    lineage_id: str,
    node_type: str,
    parent_ids: list[str],
    *,
    outcome_status: str | None = None,
) -> dict:
    return {
        "lineage_id": lineage_id,
        "node_type": node_type,
        "source_block": "TEST_BLOCK",
        "timestamp_utc": "2026-01-01T00:00:00Z",
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


def test_outcome_to_edge_closed_link_status_passes() -> None:
    raw = _node("LIN_RAW", "raw_event", [])
    evidence = _node("LIN_EVID", "evidence", ["LIN_RAW"])
    dna = _node("LIN_DNA", "candle_dna", ["LIN_EVID"])
    fp = _node("LIN_FP", "footprint", ["LIN_DNA"])
    liq = _node("LIN_LIQ", "liquidity", ["LIN_FP"])
    st = _node("LIN_ST", "structure", ["LIN_LIQ"])
    ms = _node("LIN_MS", "market_state", ["LIN_ST"])
    sc = _node("LIN_SC", "scenario", ["LIN_MS"])
    su = _node("LIN_SU", "setup_candidate", ["LIN_SC"])
    sg = _node("LIN_SG", "entry_trigger", ["LIN_SU"])
    tp = _node("LIN_TP", "trade_plan", ["LIN_SG"])
    dc = _node("LIN_DC", "decision", ["LIN_TP"])
    pt = _node("LIN_PT", "paper_trade", ["LIN_DC"])
    out = _node("LIN_OUT", "outcome", ["LIN_PT"], outcome_status="CLOSED")
    edge = _node("LIN_EDGE", "edge_row", ["LIN_OUT"])
    report = build_lineage_graph_report([raw, evidence, dna, fp, liq, st, ms, sc, su, sg, tp, dc, pt, out, edge])
    assert report["outcome_to_edge_link_status"] == "PASS"


def test_audit_runner_missing_files_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    payload = run_lineage_audit(tmp_path)
    assert isinstance(payload, dict)
    assert "missing_source" in payload
    assert (tmp_path / "state/lineage/latest_lineage_audit.json").exists()
    assert (tmp_path / "state/lineage/lineage_graph_state.json").exists()
    assert (tmp_path / "reports/lineage/lineage_audit_latest_report.md").exists()

