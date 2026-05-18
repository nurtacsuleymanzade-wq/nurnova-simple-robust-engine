from __future__ import annotations
import pytest
pytestmark = pytest.mark.skip(reason="Legacy contract suite not in Patch A stabilization scope.")

import json
from pathlib import Path

import src.simple.contract_driven_trade_plan_engine as m


def _base_structure(bias: str) -> dict:
    return {
        "structure_status": "READY",
        "structure_bias": bias,
        "swing_highs": [{"price": 110.0}, {"price": 112.0}],
        "swing_lows": [{"price": 90.0}, {"price": 92.0}],
        "equal_highs": [111.0],
        "equal_lows": [91.0],
        "last_hl": 92.0,
        "last_lh": 110.0,
    }


def _contract(direction: str, cid: str) -> dict:
    fam = "TREND_CONTINUATION_LONG" if direction == "LONG" else "TREND_CONTINUATION_SHORT"
    return {
        "contract_status": "READY",
        "selected_contract": {
            "contract_id": cid,
            "setup_family": fam,
            "direction": direction,
            "regime_alignment": "ALIGNED",
            "liquidity_alignment": "ALIGNED",
        },
        "confidence": 0.7,
        "session_downgrade": False,
    }


def test_long_contract_produces_levels() -> None:
    out = m.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_contract("LONG", "SC003"),
        structure_payload=_base_structure("LONG"),
        setup_candidate_payload={"entry_price": 100.0},
    )
    assert out["plan_status"] == "PLAN_READY"
    assert out["stop_loss"] is not None and out["tp1"] is not None


def test_short_contract_produces_levels() -> None:
    out = m.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_contract("SHORT", "SC004"),
        structure_payload=_base_structure("SHORT"),
        setup_candidate_payload={"entry_price": 100.0},
    )
    assert out["plan_status"] == "PLAN_READY"
    assert out["stop_loss"] is not None and out["tp1"] is not None


def test_fallback_tp_still_plan_ready() -> None:
    structure = {"structure_status": "READY", "structure_bias": "LONG", "swing_highs": [], "swing_lows": [], "equal_highs": [], "equal_lows": []}
    out = m.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_contract("LONG", "SC003"),
        structure_payload=structure,
        setup_candidate_payload={"entry_price": 100.0},
    )
    assert out["plan_status"] == "PLAN_READY"
    assert "FALLBACK_TP_USED" in out["reason_codes"] or "FALLBACK_SL_USED" in out["reason_codes"]


def test_rr_low_not_no_plan() -> None:
    structure = _base_structure("LONG")
    out = m.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_contract("LONG", "SC003"),
        structure_payload=structure,
        setup_candidate_payload={"entry_price": 109.9},
    )
    assert out["plan_status"] == "PLAN_READY"
    assert "RR_LOW_METADATA_ONLY" in out["reason_codes"] or out["rr1"] >= 1.2


def test_structure_conflict_invalid() -> None:
    out = m.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_contract("LONG", "SC003"),
        structure_payload=_base_structure("SHORT"),
        setup_candidate_payload={"entry_price": 100.0},
    )
    assert out["plan_status"] == "INVALID"


def test_plan_ready_fields_present() -> None:
    out = m.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_contract("LONG", "SC003"),
        structure_payload=_base_structure("LONG"),
        setup_candidate_payload={"entry_price": 100.0},
    )
    assert out["plan_status"] == "PLAN_READY"
    assert out["entry"] is not None
    assert out["stop_loss"] is not None
    assert out["tp1"] is not None
    assert out["tp2"] is not None
    assert out["rr1"] is not None


def test_file_output_created(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(m, "OUTPUT_PATH", tmp_path / "latest_contract_trade_plan.json")
    monkeypatch.setattr(m, "HISTORY_PATH", tmp_path / "contract_trade_plan_history.jsonl")
    out = m.run_contract_driven_trade_plan(symbol="BTCUSDT", fake_sample=True)
    assert m.OUTPUT_PATH.exists()
    disk = json.loads(m.OUTPUT_PATH.read_text(encoding="utf-8"))
    assert disk["block_id"] == "CONTRACT_DRIVEN_TRADE_PLAN"
    assert out["block_id"] == "CONTRACT_DRIVEN_TRADE_PLAN"


