from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

import src.simple.research_edge_matrix_engine as engine

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_edge():
    d = TMP_BASE / f"edge_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_edge_matrix_groups_include_timeframe_fields(tmp_edge, monkeypatch):
    history = tmp_edge / "research_paper_lifecycle_history.jsonl"
    output = tmp_edge / "latest_research_edge_matrix.json"
    out_history = tmp_edge / "research_edge_matrix_history.jsonl"

    payload = {
        "trades_closed_this_loop": [
            {
                "paper_trade_id": "t1",
                "context_id": "ctx1",
                "model_id": "DAF_SHORT",
                "model_family": "DELTA_ABSORPTION_FAILURE",
                "setup_family": "TRAP_REVERSAL",
                "dominant_setup_family": "TRAP_REVERSAL",
                "primary_tf": "5m",
                "trigger_tf": "1m",
                "context_tf": "15m",
                "structure_tf": "5m",
                "plan_style": "SWEEP_REVERSAL",
                "expected_hold_label": "15m–120m",
                "activation_band": "STRONG_ACTIVE",
                "market_regime": "BALANCE_MODE",
                "candle_category": "TRAP_CANDLE",
                "structure_label": "CHOCH",
                "liquidity_event": "WALL_REACTION",
                "direction": "SHORT",
                "status": "TP1_HIT",
                "outcome_status": "CLOSED",
                "r_result": 1.5,
            }
        ]
    }
    history.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    monkeypatch.setattr(engine, "LIFECYCLE_HISTORY_PATH", history)
    monkeypatch.setattr(engine, "OUTPUT_PATH", output)
    monkeypatch.setattr(engine, "HISTORY_PATH", out_history)

    result = engine.run_research_edge_matrix_engine()

    assert result["groups"]
    group = result["groups"][0]
    assert group["primary_tf"] == "5m"
    assert group["trigger_tf"] == "1m"
    assert group["context_tf"] == "15m"
    assert group["structure_tf"] == "5m"
    assert group["plan_style"] == "SWEEP_REVERSAL"
    assert group["expected_hold_label"] == "15m–120m"
    assert group["edge_status"] == "SAMPLE_BUILDING"
