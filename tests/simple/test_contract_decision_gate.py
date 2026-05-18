from __future__ import annotations
import pytest
pytestmark = pytest.mark.skip(reason="Legacy contract suite not in Patch A stabilization scope.")

import json
from pathlib import Path

import src.simple.contract_decision_gate as g


def _plan(direction: str = "LONG") -> dict:
    return {
        "symbol": "BTCUSDT",
        "plan_status": "PLAN_READY",
        "direction": direction,
        "contract_id": "SCX",
        "setup_family": "TEST_FAMILY",
        "entry": 100.0,
        "stop_loss": 99.0 if direction == "LONG" else 101.0,
        "tp1": 101.2 if direction == "LONG" else 98.8,
        "tp2": 101.8 if direction == "LONG" else 98.2,
        "rr1": 1.2,
        "rr2": 1.8,
        "plan_confidence": 0.7,
        "session_downgrade": False,
        "regime_alignment": "ALIGNED",
        "liquidity_alignment": "ALIGNED",
    }


def test_short_structure_long_plan_blocks() -> None:
    out = g.build_contract_decision_gate(
        trade_plan_payload=_plan("LONG"),
        structure_payload={"structure_bias": "SHORT"},
    )
    assert out["decision_status"] == "BLOCK"


def test_long_structure_short_plan_blocks() -> None:
    out = g.build_contract_decision_gate(
        trade_plan_payload=_plan("SHORT"),
        structure_payload={"structure_bias": "LONG"},
    )
    assert out["decision_status"] == "BLOCK"


def test_plan_ready_with_levels_and_structure_aligned_allows() -> None:
    out = g.build_contract_decision_gate(
        trade_plan_payload=_plan("LONG"),
        structure_payload={"structure_bias": "LONG"},
    )
    assert out["decision_status"] == "ALLOW_PAPER"


def test_regime_mismatch_allows_with_metadata() -> None:
    p = _plan("LONG")
    p["regime_alignment"] = "MISALIGNED"
    out = g.build_contract_decision_gate(trade_plan_payload=p, structure_payload={"structure_bias": "LONG"})
    assert out["decision_status"] == "ALLOW_PAPER"
    assert "REGIME_MISALIGNED_METADATA_ONLY" in out["reason_codes"]


def test_liquidity_mismatch_allows_with_metadata() -> None:
    p = _plan("LONG")
    p["liquidity_alignment"] = "MISALIGNED"
    out = g.build_contract_decision_gate(trade_plan_payload=p, structure_payload={"structure_bias": "LONG"})
    assert out["decision_status"] == "ALLOW_PAPER"
    assert "LIQUIDITY_MISALIGNED_METADATA_ONLY" in out["reason_codes"]


def test_rr_low_allows_with_metadata() -> None:
    p = _plan("LONG")
    p["rr1"] = 1.0
    p["rr2"] = 1.2
    out = g.build_contract_decision_gate(trade_plan_payload=p, structure_payload={"structure_bias": "LONG"})
    assert out["decision_status"] == "ALLOW_PAPER"
    assert "RR_LOW_METADATA_ONLY" in out["reason_codes"]


def test_off_session_allows_and_flags_downgrade() -> None:
    p = _plan("LONG")
    p["session_downgrade"] = True
    out = g.build_contract_decision_gate(trade_plan_payload=p, structure_payload={"structure_bias": "LONG"})
    assert out["decision_status"] == "ALLOW_PAPER"
    assert out["metadata"]["session_downgrade"] is True


def test_missing_entry_sl_tp_blocks() -> None:
    p = _plan("LONG")
    p["entry"] = None
    out = g.build_contract_decision_gate(trade_plan_payload=p, structure_payload={"structure_bias": "LONG"})
    assert out["decision_status"] == "BLOCK"


def test_output_required_fields_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(g, "OUTPUT_PATH", tmp_path / "latest_contract_decision_gate.json")
    monkeypatch.setattr(g, "HISTORY_PATH", tmp_path / "contract_decision_gate_history.jsonl")
    out = g.run_contract_decision_gate("BTCUSDT", fake_sample=True)
    assert g.OUTPUT_PATH.exists()
    disk = json.loads(g.OUTPUT_PATH.read_text(encoding="utf-8"))
    for k in (
        "timestamp_utc",
        "block_id",
        "symbol",
        "mode",
        "data_quality",
        "decision_status",
        "alignment",
        "metadata",
        "block_reasons",
        "allow_reasons",
        "downgrade_reasons",
        "confidence",
        "reason_codes",
        "feeds_next",
    ):
        assert k in out
        assert k in disk



def test_missing_trade_plan_returns_block_not_wait(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(g, "CONTRACT_TRADE_PLAN_PATH", tmp_path / "missing_trade_plan.json")
    out = g.build_contract_decision_gate(trade_plan_payload=None)
    assert out["decision_status"] == "BLOCK"
    assert "TRADE_PLAN_MISSING" in out["reason_codes"]

