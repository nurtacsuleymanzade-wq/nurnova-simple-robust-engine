from __future__ import annotations

import json
from pathlib import Path

from src.paper_outcome import run_paper_outcome_engine as engine


def test_no_trade_fast_exit_without_historical_scan(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path
    (root / "state/trade_decision").mkdir(parents=True)
    (root / "state/trade_decision/latest_trade_decision.json").write_text(
        json.dumps(
            {
                "timestamp_utc": "2026-05-18T09:45:24Z",
                "symbol": "BTCUSDT",
                "trade_plan_id": "TP_1",
                "decision_id": "DEC_1",
                "decision_status": "NO_TRADE",
                "side": "NO_TRADE",
                "lineage_id": "LIN_1",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(engine, "ROOT", root)
    monkeypatch.setattr(engine, "STATE_DIR", root / "state/paper_outcome")
    monkeypatch.setattr(engine, "REPORTS_DIR", root / "reports/paper_outcome")
    monkeypatch.setattr(engine, "LIVE_DIR", root / "data/live")
    monkeypatch.setattr(engine, "LATEST_PATH", root / "state/paper_outcome/latest_paper_outcome.json")
    monkeypatch.setattr(engine, "ENGINE_STATE_PATH", root / "state/paper_outcome/paper_outcome_engine_state.json")
    monkeypatch.setattr(engine, "EVENTS_PATH", root / "data/live/paper_outcome_events.jsonl")
    monkeypatch.setattr(engine, "REPORT_PATH", root / "reports/paper_outcome/paper_outcome_latest_report.md")
    monkeypatch.setattr(engine, "TRADE_DECISION_PATH", root / "state/trade_decision/latest_trade_decision.json")
    monkeypatch.setattr(engine, "SETUP_ENTRY_PATH", root / "state/setup_entry/latest_setup_entry.json")
    monkeypatch.setattr(engine, "ACTIVE_SCENARIO_PATH", root / "state/active_scenario/latest_active_scenario.json")
    monkeypatch.setattr(engine, "MARKET_STATE_PATH", root / "state/market_state/latest_market_state.json")
    monkeypatch.setattr(engine, "FLOW_REACTION_PATH", root / "state/flow_reaction/latest_flow_reaction.json")

    def _fail_collect(_: str) -> tuple[list[dict], list[str]]:
        raise AssertionError("historical scan must not run for NO_TRADE")

    monkeypatch.setattr(engine, "_collect_price_path_records", _fail_collect)

    payload = engine.run()

    assert payload["trade_fate"] == "NO_ACTIONABLE_DECISION"
    assert payload["edge_eligible"] is False
    assert "NO_ACTIONABLE_DECISION" in payload["reason_codes"]
    assert "NO_OPEN_PAPER_TRADE" in payload["reason_codes"]
    assert (root / "state/paper_outcome/latest_paper_outcome.json").exists()


def test_read_jsonl_stream_tail_without_full_read(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "large.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for idx in range(1000):
            handle.write(json.dumps({"symbol": "BTCUSDT", "n": idx}) + "\n")

    def _blocked_read_text(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("full read_text() must not be used")

    monkeypatch.setattr(Path, "read_text", _blocked_read_text)
    items = engine._read_jsonl(path, max_lines=50)

    assert len(items) == 50
    assert items[0]["n"] == 950
    assert items[-1]["n"] == 999
