from __future__ import annotations

import json
from pathlib import Path

import src.simple.setup_contract_engine as e
import src.simple.setup_contract_registry as r


def test_registry_loads_required_contracts() -> None:
    registry = r.load_setup_contract_registry()
    families = {item["setup_family"] for item in registry}
    assert len(registry) >= 10
    assert "TREND_CONTINUATION_LONG" in families
    assert "BREAKOUT_EXPANSION_SHORT" in families


def test_fake_trend_long_has_trend_continuation_long_eligible(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(e, "OUTPUT_PATH", tmp_path / "latest_setup_contract.json")
    monkeypatch.setattr(e, "HISTORY_PATH", tmp_path / "setup_contract_history.jsonl")
    out = e.run_setup_contract_engine(symbol="BTCUSDT", fake_sample=True)
    families = {x["setup_family"] for x in out["eligible_contracts"]}
    assert "TREND_CONTINUATION_LONG" in families


def test_short_structure_blocks_long_contracts() -> None:
    structure = {"structure_status": "READY", "structure_bias": "SHORT"}
    regime = {"regime_status": "READY", "primary_regime": "TREND", "directional_bias": "SHORT"}
    out = e.build_setup_contract_state("BTCUSDT", structure_payload=structure, regime_payload=regime)
    blocked = {x["setup_family"] for x in out["blocked_contracts"]}
    assert "TREND_CONTINUATION_LONG" in blocked


def test_neutral_structure_allows_both_directions() -> None:
    structure = {"structure_status": "READY", "structure_bias": "NEUTRAL"}
    regime = {"regime_status": "READY", "primary_regime": "RANGE", "directional_bias": "NEUTRAL"}
    out = e.build_setup_contract_state("BTCUSDT", structure_payload=structure, regime_payload=regime)
    dirs = {x["direction"] for x in out["eligible_contracts"]}
    assert "LONG" in dirs and "SHORT" in dirs


def test_missing_regime_not_blocking_but_metadata_reason() -> None:
    structure = {"structure_status": "READY", "structure_bias": "LONG"}
    out = e.build_setup_contract_state(
        "BTCUSDT",
        structure_payload=structure,
        regime_payload={"regime_status": "NOT_READY", "primary_regime": "UNKNOWN", "directional_bias": "NEUTRAL"},
    )
    assert out["contract_status"] == "READY"
    assert "REGIME_NOT_READY_METADATA_ONLY" in out["reason_codes"]


def test_selected_contract_has_required_fields() -> None:
    structure = {"structure_status": "READY", "structure_bias": "LONG"}
    regime = {"regime_status": "READY", "primary_regime": "TREND", "directional_bias": "LONG"}
    out = e.build_setup_contract_state("BTCUSDT", structure_payload=structure, regime_payload=regime)
    assert out["selected_contract"] is not None
    for key in ("contract_id", "setup_family", "direction", "score"):
        assert key in out["selected_contract"]


def test_duplicate_and_session_policies_are_correct() -> None:
    registry = r.load_setup_contract_registry()
    for item in registry:
        assert item["duplicate_policy"]["max_open_same_contract"] == 2
        assert item["duplicate_policy"]["max_open_same_direction"] == 3
        assert item["session_policy"]["off_session_policy"] == "DOWNGRADE"
        assert "OVERLAP" not in item["session_policy"]["allowed_sessions"]
        assert set(item["session_policy"]["allowed_sessions"]) == {"LONDON", "NEW_YORK"}


def test_output_written(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(e, "OUTPUT_PATH", tmp_path / "latest_setup_contract.json")
    monkeypatch.setattr(e, "HISTORY_PATH", tmp_path / "setup_contract_history.jsonl")
    out = e.run_setup_contract_engine(symbol="BTCUSDT", fake_sample=True)
    assert e.OUTPUT_PATH.exists()
    disk = json.loads(e.OUTPUT_PATH.read_text(encoding="utf-8"))
    assert disk["block_id"] == "SETUP_CONTRACT_ENGINE"
    assert out["block_id"] == "SETUP_CONTRACT_ENGINE"
