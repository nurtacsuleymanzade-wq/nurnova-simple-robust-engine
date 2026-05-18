from __future__ import annotations

import json
from typing import Any

import src.simple.contract_decision_gate as gate
import src.simple.contract_driven_trade_plan_engine as plan
import src.simple.local_pipeline_runner as runner
import src.simple.paper_trade_factory as factory


def _structure(direction: str = "LONG") -> dict[str, Any]:
    return {
        "structure_status": "READY",
        "structure_bias": direction,
        "swing_highs": [{"price": 110.0}, {"price": 112.0}],
        "swing_lows": [{"price": 90.0}, {"price": 92.0}],
        "equal_highs": [111.0],
        "equal_lows": [91.0],
        "last_hl": 92.0,
        "last_lh": 110.0,
    }


def _setup_contract(direction: str = "LONG") -> dict[str, Any]:
    return {
        "contract_status": "READY",
        "selected_contract": {
            "contract_id": "SC003",
            "setup_family": "TREND_CONTINUATION_LONG",
            "direction": direction,
            "regime_alignment": "ALIGNED",
            "liquidity_alignment": "ALIGNED",
        },
        "confidence": 0.7,
        "session_downgrade": False,
    }


def _signal_event() -> dict[str, Any]:
    return {
        "latest_event": {
            "setup_id": "SETUP_EPOCH",
            "signal_id": "SIG_EPOCH",
            "event_id": "EVT_EPOCH",
            "symbol": "BTCUSDT",
            "direction": "LONG",
        }
    }


def test_epoch_v2_signal_event_drives_contract_plan_without_legacy_root_signal(tmp_path, monkeypatch) -> None:
    epoch_signal_path = tmp_path / "state" / "simple" / "epoch_v2" / "latest_signal_event.json"
    epoch_signal_path.parent.mkdir(parents=True)
    epoch_signal_path.write_text(json.dumps(_signal_event()), encoding="utf-8")
    legacy_root_signal = tmp_path / "state" / "simple" / "latest_signal_event.json"

    monkeypatch.setattr(plan, "SIGNAL_EVENT_PATH", epoch_signal_path)

    out = plan.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_setup_contract(),
        structure_payload=_structure(),
        setup_candidate_payload={"entry_price": 100.0},
    )

    assert not legacy_root_signal.exists()
    assert out["plan_status"] == "PLAN_READY"
    assert out["paper_executable"] is True
    assert "SIGNAL_EVENT_CANONICAL_EPOCH_V2" in out["reason_codes"]


def test_contract_driven_plan_outputs_paper_executable_geometry() -> None:
    out = plan.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_setup_contract(),
        structure_payload=_structure(),
        setup_candidate_payload={"entry_price": 100.0},
        signal_event_payload=_signal_event(),
    )

    assert out["plan_status"] == "PLAN_READY"
    assert out["side"] == "LONG"
    assert out["entry_price"] == 100.0
    assert out["stop_loss"] < out["entry_price"] < out["tp1"] <= out["tp2"]
    assert out["rr1"] >= 1.2
    assert out["rr2"] >= 1.5
    assert out["geometry_quality"] == "PAPER_EXECUTABLE"
    assert out["paper_executable"] is True
    assert out["real_trade_allowed"] is False
    assert out["execution_safety"]["safe_to_open_real_trade"] is False
    assert out["execution_safety"]["private_api_used"] is False


def test_decision_gate_separates_paper_permission_from_real_execution() -> None:
    trade_plan = plan.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_setup_contract(),
        structure_payload=_structure(),
        setup_candidate_payload={"entry_price": 100.0},
        signal_event_payload=_signal_event(),
    )

    out = gate.build_contract_decision_gate(
        "BTCUSDT",
        trade_plan_payload=trade_plan,
        setup_contract_payload=_setup_contract(),
        structure_payload={"structure_bias": "LONG"},
        quality_weight_payload={"data_quality": {"level": "HIGH", "score": 1.0}},
    )

    assert out["paper_decision"] == "ALLOW_PAPER"
    assert out["paper_permission"] is True
    assert out["paper_execution_permission"] is True
    assert out["real_execution_permission"] is False
    assert out["real_trade_allowed"] is False
    assert out["execution_permission"] == "BLOCK_OPEN"
    assert out["execution_safety"]["safe_to_open_real_trade"] is False
    assert out["execution_safety"]["private_api_used"] is False


def test_paper_trade_factory_opens_from_contract_permission(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    trade_plan = plan.build_contract_driven_trade_plan(
        "BTCUSDT",
        setup_contract_payload=_setup_contract(),
        structure_payload=_structure(),
        setup_candidate_payload={"entry_price": 100.0},
        signal_event_payload=_signal_event(),
    )
    decision = gate.build_contract_decision_gate(
        "BTCUSDT",
        trade_plan_payload=trade_plan,
        setup_contract_payload=_setup_contract(),
        structure_payload={"structure_bias": "LONG"},
        quality_weight_payload={"data_quality": {"level": "HIGH", "score": 1.0}},
    )

    payloads: dict[str, dict[str, Any]] = {
        str(factory.CONTRACT_DECISION_PATH): decision,
        str(factory.CONTRACT_TRADE_PLAN_PATH): trade_plan,
        str(factory.SETUP_CONTRACT_PATH): {"liquidity_bias": "BUY"},
        str(factory.REGIME_CLASSIFIER_PATH): {"primary_regime": "TREND"},
        str(factory.MARKET_STRUCTURE_V2_PATH): {"structure_bias": "LONG"},
        str(factory.OBSERVATION_PATH): {"symbol": "BTCUSDT", "market_snapshot": {"price": 100.0}},
        str(factory.DNA_PATH): {"1m": {"close": 100.0}},
    }

    monkeypatch.setattr(factory, "load_json", lambda path: payloads.get(str(path), {}))
    monkeypatch.setattr(factory, "safe_read_json", lambda *args, **kwargs: ({"open_trades": []}, "OK"))
    monkeypatch.setattr(factory, "_select_candidates", lambda *args, **kwargs: ([], "NO_MODEL_INPUT", []))
    monkeypatch.setattr(factory, "load_model_survival_registry", lambda: {})
    monkeypatch.setattr(factory, "split_active_quarantined", lambda items, _block: (items, []))
    monkeypatch.setattr(factory, "update_model_survival_report", lambda **kwargs: {"registry_status": "OK"})
    monkeypatch.setattr(factory, "write_json", lambda path, payload: captured.setdefault("output", payload))
    monkeypatch.setattr(factory, "append_epoch_jsonl", lambda name, payload: None)
    monkeypatch.setattr(factory, "seen_ids", lambda *args, **kwargs: set())
    monkeypatch.setattr(factory, "append_event", lambda *args, **kwargs: None)

    out = factory.run_paper_trade_factory()
    opened = out["newest_opened_this_loop"]

    assert len(opened) > 0
    assert "PAPER_OPENED_FROM_CONTRACT_DRIVEN_CHAIN" in out["reason_codes"]
    assert "PAPER_OPENED_FROM_CONTRACT_DRIVEN_CHAIN" in opened[0]["reason_codes"]
    assert out["execution_safety"]["safe_to_open_real_trade"] is False
    assert out["execution_safety"]["private_api_used"] is False
    assert opened[0]["execution_safety"]["safe_to_open_real_trade"] is False
    assert opened[0]["execution_safety"]["private_api_used"] is False
    assert captured["output"]["summary"]["contract_bridge_trade_opened"] is True


def test_legacy_s17_is_not_active_runtime_opener() -> None:
    active_labels = {label for _module, _func, label in runner._STAGES}

    assert "S17_TRADE_PLAN" not in active_labels
    assert "S18_DECISION_GATE" not in active_labels
    assert "S20_PAPER_LIFECYCLE" not in active_labels
    assert any(label == "S17_TRADE_PLAN" for _module, _func, label in runner._DISABLED_LEGACY_ACTIVE_OPENER_STAGES)

