from __future__ import annotations

import json

from src.simple import telegram_followup_notifier as tfn


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _lifecycle(status: str = "ACTIVE", events: list[dict] | None = None) -> dict:
    return {
        "timestamp_utc": "2026-05-11T00:00:10Z",
        "block_id": "S20_PAPER_LIFECYCLE_TRACKER",
        "symbol": "BTCUSDT",
        "lifecycle_id": "lc-1",
        "lifecycle_status": status,
        "side": "LONG",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "tp1": 105.0,
        "tp2": 110.0,
        "current_price": 101.0,
        "entry_touched": True,
        "tp1_hit": status in {"TP1_HIT", "TP2_HIT", "CLOSED"},
        "tp2_hit": status in {"TP2_HIT", "CLOSED"},
        "stop_hit": status == "SL_HIT",
        "invalidated": status == "INVALIDATED",
        "unrealized_r": 0.2,
        "realized_r": None,
        "lifecycle_events": events or [],
        "execution_safety": dict(tfn.SAFETY),
    }


def _outcome(status: str = "OPEN", result: str = "STILL_OPEN", final_price: float | None = None, realized_r: float | None = None) -> dict:
    return {
        "timestamp_utc": "2026-05-11T00:00:10Z",
        "block_id": "S21_OUTCOME_MONITOR",
        "symbol": "BTCUSDT",
        "outcome_status": status,
        "outcome_result": result,
        "final_price": final_price,
        "realized_r": realized_r,
        "execution_safety": dict(tfn.SAFETY),
    }


def _plan() -> dict:
    return {"symbol": "BTCUSDT", "plan_status": "READY"}


def _gate() -> dict:
    return {"symbol": "BTCUSDT"}


def _configure_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(tfn, "STATE_DIR", tmp_path / "state" / "simple")
    monkeypatch.setattr(tfn, "DATA_DIR", tmp_path / "data" / "simple")
    monkeypatch.setattr(tfn, "REPORTS_DIR", tmp_path / "reports" / "simple")
    monkeypatch.setattr(tfn, "LIFECYCLE_PATH", tfn.STATE_DIR / "latest_paper_lifecycle.json")
    monkeypatch.setattr(tfn, "OUTCOME_PATH", tfn.STATE_DIR / "latest_outcome_monitor.json")
    monkeypatch.setattr(tfn, "TRADE_PLAN_PATH", tfn.STATE_DIR / "latest_trade_plan.json")
    monkeypatch.setattr(tfn, "DECISION_GATE_PATH", tfn.STATE_DIR / "latest_decision_gate.json")
    monkeypatch.setattr(tfn, "LATEST_PATH", tfn.STATE_DIR / "latest_telegram_followup.json")
    monkeypatch.setattr(tfn, "S25_STATE_PATH", tfn.STATE_DIR / "s25_telegram_followup_state.json")
    monkeypatch.setattr(tfn, "HISTORY_PATH", tfn.DATA_DIR / "telegram_followup_history.jsonl")
    monkeypatch.setattr(tfn, "REPORT_PATH", tfn.REPORTS_DIR / "s25_telegram_followup_latest_report.md")


def _write_inputs(tmp_path, lifecycle: dict | None, outcome: dict | None, plan: dict | None = None, gate: dict | None = None):
    state_dir = tmp_path / "state" / "simple"
    state_dir.mkdir(parents=True, exist_ok=True)
    if lifecycle is not None:
        (state_dir / "latest_paper_lifecycle.json").write_text(json.dumps(lifecycle), encoding="utf-8")
    if outcome is not None:
        (state_dir / "latest_outcome_monitor.json").write_text(json.dumps(outcome), encoding="utf-8")
    if plan is not None:
        (state_dir / "latest_trade_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    if gate is not None:
        (state_dir / "latest_decision_gate.json").write_text(json.dumps(gate), encoding="utf-8")


def test_sends_entry_touched_once(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    _write_inputs(
        tmp_path,
        _lifecycle(events=[{"timestamp_utc": "2026-05-11T00:00:10Z", "event": "ENTRY_TOUCHED", "detail": "price=100.0"}]),
        _outcome(),
        _plan(),
        _gate(),
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(tfn.request, "urlopen", lambda *args, **kwargs: _FakeResponse({"ok": True}))

    result = tfn.run_telegram_followup_notifier()

    assert result["followup_status"] == "SENT"
    assert result["event_type"] == "ENTRY_TOUCHED"
    assert result["telegram_sent"] is True


def test_does_not_duplicate_same_event(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    lifecycle = _lifecycle(events=[{"timestamp_utc": "2026-05-11T00:00:10Z", "event": "ENTRY_TOUCHED", "detail": "price=100.0"}])
    _write_inputs(tmp_path, lifecycle, _outcome(), _plan(), _gate())
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = {"count": 0}

    def _urlopen(*args, **kwargs):
        calls["count"] += 1
        return _FakeResponse({"ok": True})

    monkeypatch.setattr(tfn.request, "urlopen", _urlopen)

    first = tfn.run_telegram_followup_notifier()
    second = tfn.run_telegram_followup_notifier()

    assert first["followup_status"] == "SENT"
    assert second["followup_status"] == "NO_NEW_EVENT"
    assert calls["count"] == 1


def test_sends_tp1_once(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    _write_inputs(
        tmp_path,
        _lifecycle(status="TP1_HIT", events=[{"timestamp_utc": "2026-05-11T00:01:00Z", "event": "TP1_HIT", "detail": "price=105.0"}]),
        _outcome(status="OPEN", result="TP1", final_price=105.0, realized_r=1.0),
        _plan(),
        _gate(),
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(tfn.request, "urlopen", lambda *args, **kwargs: _FakeResponse({"ok": True}))

    result = tfn.run_telegram_followup_notifier()

    assert result["followup_status"] == "SENT"
    assert result["event_type"] == "TP1_HIT"


def test_sends_tp2_once(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    _write_inputs(
        tmp_path,
        _lifecycle(status="TP2_HIT", events=[{"timestamp_utc": "2026-05-11T00:02:00Z", "event": "TP2_HIT", "detail": "price=110.0"}]),
        _outcome(status="CLOSED", result="TP2", final_price=110.0, realized_r=2.0),
        _plan(),
        _gate(),
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(tfn.request, "urlopen", lambda *args, **kwargs: _FakeResponse({"ok": True}))

    result = tfn.run_telegram_followup_notifier()

    assert result["followup_status"] == "SENT"
    assert result["event_type"] == "TP2_HIT"


def test_sends_sl_once(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    _write_inputs(
        tmp_path,
        _lifecycle(status="SL_HIT", events=[{"timestamp_utc": "2026-05-11T00:03:00Z", "event": "SL_HIT", "detail": "price=95.0"}]),
        _outcome(status="CLOSED", result="SL", final_price=95.0, realized_r=-1.0),
        _plan(),
        _gate(),
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(tfn.request, "urlopen", lambda *args, **kwargs: _FakeResponse({"ok": True}))

    result = tfn.run_telegram_followup_notifier()

    assert result["followup_status"] == "SENT"
    assert result["event_type"] == "SL_HIT"


def test_missing_env_blocks_safely(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    _write_inputs(
        tmp_path,
        _lifecycle(events=[{"timestamp_utc": "2026-05-11T00:00:10Z", "event": "ENTRY_TOUCHED", "detail": "price=100.0"}]),
        _outcome(),
        _plan(),
        _gate(),
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    result = tfn.run_telegram_followup_notifier()

    assert result["followup_status"] == "BLOCKED_MISSING_ENV"
    assert result["telegram_sent"] is False


def test_no_lifecycle_returns_no_lifecycle(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    _write_inputs(tmp_path, None, None, _plan(), _gate())

    result = tfn.run_telegram_followup_notifier()

    assert result["followup_status"] == "NO_LIFECYCLE"


def test_safety_flags_always_false(tmp_path, monkeypatch):
    _configure_paths(monkeypatch, tmp_path)
    _write_inputs(
        tmp_path,
        _lifecycle(status="TP1_HIT", events=[{"timestamp_utc": "2026-05-11T00:01:00Z", "event": "TP1_HIT", "detail": "price=105.0"}]),
        _outcome(status="OPEN", result="TP1", final_price=105.0, realized_r=1.0),
        _plan(),
        _gate(),
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(tfn.request, "urlopen", lambda *args, **kwargs: _FakeResponse({"ok": True}))

    result = tfn.run_telegram_followup_notifier()

    assert result["safe_to_open_real_trade"] is False
    assert result["private_api_used"] is False
    assert result["live_order_sent"] is False
    assert result["execution_safety"]["safe_to_open_real_trade"] is False
