from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

import src.simple.timeframe_resolver as resolver

TMP_BASE = Path("tmp_pytest")


@pytest.fixture()
def tmp_tf():
    d = TMP_BASE / f"tf_{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_timeframe_resolver_builds_output(tmp_tf, monkeypatch):
    mtf = tmp_tf / "mtf.json"
    structure = tmp_tf / "structure.json"
    liquidity = tmp_tf / "liquidity.json"
    interpretation = tmp_tf / "interpretation.json"
    scenarios = tmp_tf / "scenarios.json"
    setup = tmp_tf / "setup.json"
    unified = tmp_tf / "unified.json"
    output = tmp_tf / "latest_timeframe_resolution.json"
    history = tmp_tf / "timeframe_resolution_history.jsonl"

    _write(mtf, {"symbol": "BTCUSDT", "1m": {"candle_category": {"primary": "TRAP_CANDLE"}}, "5m": {"liquidity_event": "LIQUIDITY_SWEEP_DOWN"}, "15m": {"liquidity_event": "LIQUIDITY_SWEEP_DOWN"}, "1h": {"liquidity_event": "WALL_REACTION"}})
    _write(structure, {"1m": {"structure_label": "EQH", "trend_state": "RANGE"}, "5m": {"structure_label": "CHOCH", "trend_state": "SHORT", "choch_detected": True}, "15m": {"structure_label": "EQH", "trend_state": "RANGE"}, "1h": {"structure_label": "RANGE", "trend_state": "RANGE"}})
    _write(liquidity, {"near_liquidity": [{"reason_codes": ["TF_5m", "TF_15m"]}]})
    _write(interpretation, {"1m": {"raw_context": {"liquidity_event": "WALL_REACTION"}}, "5m": {"raw_context": {"liquidity_event": "LIQUIDITY_SWEEP_DOWN"}}, "15m": {"raw_context": {"liquidity_event": "LIQUIDITY_SWEEP_DOWN"}}, "1h": {"raw_context": {"liquidity_event": "WALL_REACTION"}}})
    _write(scenarios, {"bearish_scenario": {"condition": "sweep rejection", "quality": "HIGH"}})
    _write(setup, {"symbol": "BTCUSDT", "dominant_setup_family": "TRAP_REVERSAL", "direction": "SHORT", "activation_score": 0.9, "source_models": [{"model_id": "TRAP_BUYERS_SHORT"}]})
    _write(unified, {"symbol": "BTCUSDT", "dominant_setup_family": "TRAP_REVERSAL", "setup_direction": "SHORT"})

    monkeypatch.setattr(resolver, "MTF_DNA_PATH", mtf)
    monkeypatch.setattr(resolver, "MARKET_STRUCTURE_PATH", structure)
    monkeypatch.setattr(resolver, "LIQUIDITY_MAP_PATH", liquidity)
    monkeypatch.setattr(resolver, "INTERPRETATION_PATH", interpretation)
    monkeypatch.setattr(resolver, "THREE_SCENARIOS_PATH", scenarios)
    monkeypatch.setattr(resolver, "SETUP_ACTIVATION_PATH", setup)
    monkeypatch.setattr(resolver, "UNIFIED_CONTEXT_PATH", unified)
    monkeypatch.setattr(resolver, "OUTPUT_PATH", output)
    monkeypatch.setattr(resolver, "HISTORY_PATH", history)

    result = resolver.run_timeframe_resolver()

    assert result["primary_tf"] == "5m"
    assert result["trigger_tf"] in {"1m", "5m"}
    assert result["context_tf"] == "15m"
    assert result["structure_tf"] in {"5m", "15m"}
    assert result["expected_hold_label"]
    assert result["timeframe_confidence"] > 0
    assert output.exists()
    assert result["execution_safety"]["live_order_sent"] is False
    assert result["execution_safety"]["private_api_used"] is False


def test_timeframe_resolver_handles_missing_inputs(tmp_tf, monkeypatch):
    output = tmp_tf / "latest_timeframe_resolution.json"
    history = tmp_tf / "timeframe_resolution_history.jsonl"

    monkeypatch.setattr(resolver, "MTF_DNA_PATH", tmp_tf / "missing_mtf.json")
    monkeypatch.setattr(resolver, "MARKET_STRUCTURE_PATH", tmp_tf / "missing_structure.json")
    monkeypatch.setattr(resolver, "LIQUIDITY_MAP_PATH", tmp_tf / "missing_liquidity.json")
    monkeypatch.setattr(resolver, "INTERPRETATION_PATH", tmp_tf / "missing_interpretation.json")
    monkeypatch.setattr(resolver, "THREE_SCENARIOS_PATH", tmp_tf / "missing_scenarios.json")
    monkeypatch.setattr(resolver, "SETUP_ACTIVATION_PATH", tmp_tf / "missing_setup.json")
    monkeypatch.setattr(resolver, "UNIFIED_CONTEXT_PATH", tmp_tf / "missing_unified.json")
    monkeypatch.setattr(resolver, "OUTPUT_PATH", output)
    monkeypatch.setattr(resolver, "HISTORY_PATH", history)

    result = resolver.run_timeframe_resolver()

    assert result["primary_tf"] == "5m"
    assert result["context_tf"] == "15m"
    assert result["data_quality"]["missing_inputs"]
    assert output.exists()
