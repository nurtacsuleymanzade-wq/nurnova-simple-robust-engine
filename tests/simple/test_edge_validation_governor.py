from __future__ import annotations

import json
from pathlib import Path

import src.simple.contract_decision_gate as gate
import src.simple.edge_validation_governor as gov


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _lifecycle_payload(
    *,
    closed: list[dict] | None = None,
    invalid: list[dict] | None = None,
    open_trades: list[dict] | None = None,
) -> dict:
    return {
        "timestamp_utc": "2026-05-18T22:00:00Z",
        "block_id": "RESEARCH_PAPER_LIFECYCLE_ENGINE",
        "open_trades": open_trades or [],
        "recent_closed": closed or [],
        "recent_invalid": invalid or [],
        "trades_closed_this_loop": [],
        "summary": {"open": len(open_trades or []), "closed": len(closed or []), "invalid": len(invalid or [])},
    }


def _trade(i: int, *, result: str, r_result: float, contract_id: str = "SC003", setup_family: str = "TREND_CONTINUATION_LONG") -> dict:
    close_reason = {"WIN": "TP1_HIT", "LOSS": "SL_HIT", "TIMEOUT": "EXPIRED"}[result]
    return {
        "paper_trade_id": f"T{i}",
        "contract_id": contract_id,
        "setup_family": setup_family,
        "model_id": "MODEL_X",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "status": close_reason,
        "close_reason": close_reason,
        "outcome_status": "CLOSED",
        "r_result": r_result,
        "opened_at_utc": f"2026-05-18T20:{i%60:02d}:00Z",
        "closed_at_utc": f"2026-05-18T21:{i%60:02d}:00Z",
        "event_id": f"EVT_{i}",
        "primary_regime": "TREND",
        "structure_bias": "LONG",
        "valid_for_edge": True,
        "epoch_id": gov.ACTIVE_EPOCH_ID,
        "entry": 100.0,
        "stop_loss": 99.0,
        "tp1": 101.5,
        "rr1": 1.5,
        "rr2": 2.0,
        "primary_tf": "5m",
        "trigger_tf": "1m",
        "context_tf": "15m",
    }


def _factory_open(i: int, *, contract_id: str = "SC003", setup_family: str = "TREND_CONTINUATION_LONG", event_id: str | None = None) -> dict:
    return {
        "paper_trade_id": f"O{i}",
        "contract_id": contract_id,
        "setup_family": setup_family,
        "model_id": "MODEL_X",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "status": "OPEN",
        "event_id": event_id or f"EVT_OPEN_{i}",
        "opened_at_utc": f"2026-05-18T22:{i%60:02d}:00Z",
    }


def _configure_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gov, "OUTPUT_PATH", tmp_path / "state" / "simple" / "latest_edge_validation_governor.json")
    monkeypatch.setattr(gov, "HISTORY_PATH", tmp_path / "data" / "simple" / "epoch_v2" / "edge_validation_governor_history.jsonl")
    monkeypatch.setattr(gov, "REPORT_PATH", tmp_path / "reports" / "simple" / "edge_validation_governor_latest_report.md")
    monkeypatch.setattr(gov, "RESEARCH_LIFECYCLE_HISTORY_PATH", tmp_path / "data" / "simple" / "epoch_v2" / "research_paper_lifecycle_history.jsonl")
    monkeypatch.setattr(gov, "OUTCOME_ACCOUNTING_HISTORY_PATH", tmp_path / "data" / "simple" / "epoch_v2" / "outcome_accounting_history.jsonl")
    monkeypatch.setattr(gov, "CONTRACT_EDGE_MATRIX_HISTORY_PATH", tmp_path / "data" / "simple" / "epoch_v2" / "contract_edge_matrix_history.jsonl")
    monkeypatch.setattr(gov, "PAPER_FACTORY_HISTORY_PATH", tmp_path / "data" / "simple" / "epoch_v2" / "paper_trade_factory_history.jsonl")
    monkeypatch.setattr(gov, "LATEST_CONTRACT_TRADE_PLAN_PATH", tmp_path / "state" / "simple" / "latest_contract_trade_plan.json")
    monkeypatch.setattr(gov, "LATEST_CONTRACT_DECISION_GATE_PATH", tmp_path / "state" / "simple" / "latest_contract_decision_gate.json")
    monkeypatch.setattr(gov, "LATEST_PAPER_TRADE_FACTORY_PATH", tmp_path / "state" / "simple" / "epoch_v2" / "latest_paper_trade_factory.json")


def _write_common_state(tmp_path: Path) -> None:
    (tmp_path / "state" / "simple").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "simple" / "epoch_v2").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "simple" / "latest_contract_trade_plan.json").write_text(
        json.dumps({"contract_id": "SC003", "setup_family": "TREND_CONTINUATION_LONG", "direction": "LONG"}), encoding="utf-8"
    )
    (tmp_path / "state" / "simple" / "latest_contract_decision_gate.json").write_text(json.dumps({}), encoding="utf-8")
    (tmp_path / "state" / "simple" / "epoch_v2" / "latest_paper_trade_factory.json").write_text(
        json.dumps({"data_quality": {"level": "HIGH"}}), encoding="utf-8"
    )
    _write_jsonl(tmp_path / "data" / "simple" / "epoch_v2" / "outcome_accounting_history.jsonl", [{"summary": {"invalid": 0, "clean_sample_count": 50}}])
    _write_jsonl(tmp_path / "data" / "simple" / "epoch_v2" / "contract_edge_matrix_history.jsonl", [{"sample_summary": {"contract_sample_count": 10}}])


def test_insufficient_sample_becomes_watchlist(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)
    _write_common_state(tmp_path)
    _write_jsonl(
        gov.RESEARCH_LIFECYCLE_HISTORY_PATH,
        [_lifecycle_payload(closed=[_trade(1, result="WIN", r_result=1.0), _trade(2, result="LOSS", r_result=-1.0)])],
    )
    _write_jsonl(gov.PAPER_FACTORY_HISTORY_PATH, [{"newest_opened_this_loop": [_factory_open(1)]}])
    out = gov.run_edge_validation_governor()
    assert out["current_edge_decision"]["edge_status"] == "EDGE_WATCHLIST"
    assert out["real_execution_permission"] is False
    assert out["safe_to_open_real_trade"] is False


def test_positive_expectancy_enough_samples_becomes_validated(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)
    _write_common_state(tmp_path)
    closed = [_trade(i, result="WIN", r_result=1.3) for i in range(1, 31)]
    closed += [_trade(100 + i, result="LOSS", r_result=-0.5) for i in range(1, 6)]
    _write_jsonl(gov.RESEARCH_LIFECYCLE_HISTORY_PATH, [_lifecycle_payload(closed=closed)])
    _write_jsonl(gov.PAPER_FACTORY_HISTORY_PATH, [{"newest_opened_this_loop": [_factory_open(1), _factory_open(2)]}])
    out = gov.run_edge_validation_governor()
    assert out["current_edge_decision"]["edge_status"] == "EDGE_VALIDATED_PAPER"
    assert out["paper_autonomy_permission"] is True
    assert out["real_trade_allowed"] is False


def test_negative_expectancy_becomes_rejected(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)
    _write_common_state(tmp_path)
    closed = [_trade(i, result="LOSS", r_result=-1.0) for i in range(1, 15)]
    _write_jsonl(gov.RESEARCH_LIFECYCLE_HISTORY_PATH, [_lifecycle_payload(closed=closed)])
    _write_jsonl(gov.PAPER_FACTORY_HISTORY_PATH, [{"newest_opened_this_loop": [_factory_open(1)]}])
    out = gov.run_edge_validation_governor()
    assert out["current_edge_decision"]["edge_status"] == "EDGE_REJECTED"
    assert out["current_edge_decision"]["paper_autonomy_permission"] is False


def test_high_loss_streak_becomes_probation_or_disabled(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)
    _write_common_state(tmp_path)
    closed = [_trade(i, result="LOSS", r_result=-1.0) for i in range(1, 7)]
    closed += [_trade(20 + i, result="WIN", r_result=0.8) for i in range(1, 10)]
    _write_jsonl(gov.RESEARCH_LIFECYCLE_HISTORY_PATH, [_lifecycle_payload(closed=closed)])
    _write_jsonl(gov.PAPER_FACTORY_HISTORY_PATH, [{"newest_opened_this_loop": [_factory_open(1)]}])
    out = gov.run_edge_validation_governor()
    assert out["current_edge_decision"]["edge_status"] in {"EDGE_PROBATION", "EDGE_DISABLED"}


def test_real_trade_flags_always_false(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)
    _write_common_state(tmp_path)
    _write_jsonl(gov.RESEARCH_LIFECYCLE_HISTORY_PATH, [_lifecycle_payload(closed=[_trade(1, result="WIN", r_result=1.0)])])
    _write_jsonl(gov.PAPER_FACTORY_HISTORY_PATH, [{"newest_opened_this_loop": [_factory_open(1)]}])
    out = gov.run_edge_validation_governor()
    assert out["real_execution_permission"] is False
    assert out["safe_to_open_real_trade"] is False
    assert out["private_api_used"] is False
    assert out["live_order_sent"] is False


def test_decision_gate_rejected_edge_blocks_paper() -> None:
    out = gate.build_contract_decision_gate(
        symbol="BTCUSDT",
        trade_plan_payload={
            "symbol": "BTCUSDT",
            "plan_status": "PLAN_READY",
            "paper_executable": True,
            "direction": "LONG",
            "entry": 100.0,
            "stop_loss": 99.0,
            "tp1": 101.5,
            "tp2": 102.0,
            "rr1": 1.5,
            "rr2": 2.0,
            "setup_id": "SETUP1",
            "signal_id": "SIG1",
            "plan_id": "PLAN1",
            "contract_id": "SC003",
            "setup_family": "TREND_CONTINUATION_LONG",
        },
        structure_payload={"structure_bias": "LONG"},
        edge_validation_payload={"current_edge_decision": {"edge_status": "EDGE_REJECTED", "edge_block": True, "paper_autonomy_permission": False}},
    )
    assert out["paper_permission"] is False
    assert out["paper_decision"] == "BLOCK"


def test_decision_gate_validated_edge_can_allow_paper() -> None:
    out = gate.build_contract_decision_gate(
        symbol="BTCUSDT",
        trade_plan_payload={
            "symbol": "BTCUSDT",
            "plan_status": "PLAN_READY",
            "paper_executable": True,
            "direction": "LONG",
            "entry": 100.0,
            "stop_loss": 99.0,
            "tp1": 101.5,
            "tp2": 102.0,
            "rr1": 1.5,
            "rr2": 2.0,
            "setup_id": "SETUP1",
            "signal_id": "SIG1",
            "plan_id": "PLAN1",
            "contract_id": "SC003",
            "setup_family": "TREND_CONTINUATION_LONG",
        },
        structure_payload={"structure_bias": "LONG"},
        edge_validation_payload={"current_edge_decision": {"edge_status": "EDGE_VALIDATED_PAPER", "edge_block": False, "paper_autonomy_permission": True}},
    )
    assert out["paper_permission"] is True
    assert out["real_execution_permission"] is False


def test_decision_gate_ignores_mismatched_edge_entity() -> None:
    out = gate.build_contract_decision_gate(
        symbol="BTCUSDT",
        trade_plan_payload={
            "symbol": "BTCUSDT",
            "plan_status": "PLAN_READY",
            "paper_executable": True,
            "direction": "LONG",
            "entry": 100.0,
            "stop_loss": 99.0,
            "tp1": 101.5,
            "tp2": 102.0,
            "rr1": 1.5,
            "rr2": 2.0,
            "setup_id": "SETUP1",
            "signal_id": "SIG1",
            "plan_id": "PLAN1",
            "contract_id": "SC003",
            "setup_family": "TREND_CONTINUATION_LONG",
        },
        structure_payload={"structure_bias": "LONG"},
        edge_validation_payload={"current_edge_decision": {"entity_type": "CONTRACT", "entity_id": "SC001", "edge_status": "EDGE_DISABLED", "edge_block": True}},
    )
    assert out["paper_permission"] is True
    assert out["paper_decision"] == "ALLOW_PAPER"
