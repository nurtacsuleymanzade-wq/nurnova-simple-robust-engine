from __future__ import annotations

from typing import Any

import src.simple.paper_trade_factory as f


def _run_factory(monkeypatch, *, decision_status: str = "ALLOW_PAPER", plan_status: str = "PLAN_READY", entry: float | None = 100.0, open_trades: list[dict[str, Any]] | None = None, direction: str = "LONG") -> dict[str, Any]:
    captured: dict[str, Any] = {}

    decision_payload = {
        "decision_status": decision_status,
        "direction": direction,
        "contract_id": "SC003",
        "setup_family": "TREND_CONTINUATION_LONG",
        "metadata": {"structure_bias": "LONG", "liquidity_bias": "BUY"},
    }
    plan_payload = {
        "symbol": "BTCUSDT",
        "plan_status": plan_status,
        "contract_id": "SC003",
        "setup_family": "TREND_CONTINUATION_LONG",
        "direction": direction,
        "entry": entry,
        "stop_loss": 99.0,
        "tp1": 101.2,
        "tp2": 101.8,
        "rr1": 1.2,
        "rr2": 1.8,
    }

    payloads: dict[str, dict[str, Any]] = {
        str(f.CONTRACT_DECISION_PATH): decision_payload,
        str(f.CONTRACT_TRADE_PLAN_PATH): plan_payload,
        str(f.SETUP_CONTRACT_PATH): {"liquidity_bias": "BUY"},
        str(f.REGIME_CLASSIFIER_PATH): {"primary_regime": "TREND"},
        str(f.MARKET_STRUCTURE_V2_PATH): {"structure_bias": "LONG"},
        str(f.OBSERVATION_PATH): {"symbol": "BTCUSDT", "market_snapshot": {"price": 100.0}},
        str(f.DNA_PATH): {"1m": {"close": 100.0}},
    }

    monkeypatch.setattr(f, "load_json", lambda path: payloads.get(str(path), {}))
    monkeypatch.setattr(f, "safe_read_json", lambda *args, **kwargs: ({"open_trades": list(open_trades or [])}, "OK"))
    monkeypatch.setattr(f, "_select_candidates", lambda *args, **kwargs: ([], "NO_MODEL_INPUT", []))
    monkeypatch.setattr(f, "load_model_survival_registry", lambda: {})
    monkeypatch.setattr(f, "split_active_quarantined", lambda items, _block: (items, []))
    monkeypatch.setattr(f, "update_model_survival_report", lambda **kwargs: {"registry_status": "OK"})
    monkeypatch.setattr(f, "write_json", lambda path, payload: captured.setdefault("output", payload))
    monkeypatch.setattr(f, "append_epoch_jsonl", lambda name, payload: None)

    return f.run_paper_trade_factory()


def test_allow_paper_plan_ready_opens_contract_trade(monkeypatch) -> None:
    out = _run_factory(monkeypatch)
    opened = out["newest_opened_this_loop"]
    assert len(opened) == 1
    trade = opened[0]
    assert trade["paper_source"] == "CONTRACT_DECISION_GATE"
    assert trade["contract_id"] == "SC003"
    assert trade["setup_family"] == "TREND_CONTINUATION_LONG"
    assert trade["rr1"] == 1.2
    assert trade["rr2"] == 1.8


def test_blocked_decision_does_not_open_trade(monkeypatch) -> None:
    out = _run_factory(monkeypatch, decision_status="BLOCK")
    assert out["newest_opened_this_loop"] == []
    assert "CONTRACT_DECISION_NOT_ALLOWING" in out["reason_codes"]


def test_no_plan_does_not_open_trade(monkeypatch) -> None:
    out = _run_factory(monkeypatch, plan_status="NO_PLAN")
    assert out["newest_opened_this_loop"] == []
    assert "CONTRACT_PLAN_INCOMPLETE" in out["reason_codes"]


def test_missing_entry_does_not_open_trade(monkeypatch) -> None:
    out = _run_factory(monkeypatch, entry=None)
    assert out["newest_opened_this_loop"] == []
    assert "CONTRACT_PLAN_INCOMPLETE" in out["reason_codes"]


def test_duplicate_contract_max_2(monkeypatch) -> None:
    existing = [
        {"status": "OPEN", "contract_id": "SC003", "direction": "LONG", "entry": 100.0},
        {"status": "OPEN", "contract_id": "SC003", "direction": "LONG", "entry": 100.01},
    ]
    out = _run_factory(monkeypatch, open_trades=existing)
    assert out["newest_opened_this_loop"] == []
    assert "CONTRACT_DUPLICATE_BLOCKED" in out["reason_codes"]


def test_same_direction_max_3(monkeypatch) -> None:
    existing = [
        {"status": "OPEN", "contract_id": "SC001", "direction": "LONG", "entry": 99.0},
        {"status": "OPEN", "contract_id": "SC002", "direction": "LONG", "entry": 100.0},
        {"status": "OPEN", "contract_id": "SC004", "direction": "LONG", "entry": 101.0},
    ]
    out = _run_factory(monkeypatch, open_trades=existing)
    assert out["newest_opened_this_loop"] == []
    assert "DIRECTION_OPEN_LIMIT_BLOCKED" in out["reason_codes"]


def test_trade_object_keeps_contract_fields(monkeypatch) -> None:
    out = _run_factory(monkeypatch)
    trade = out["newest_opened_this_loop"][0]
    assert trade["contract_id"] == "SC003"
    assert trade["setup_family"] == "TREND_CONTINUATION_LONG"
    assert trade["rr1"] == 1.2
    assert trade["rr2"] == 1.8
