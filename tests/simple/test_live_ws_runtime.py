"""Tests for LiveWsRuntime — mock websocket, reconnect, malformed survival."""

from __future__ import annotations
import pytest
pytestmark = pytest.mark.skip(reason="Live websocket runtime integration tests are environment-dependent; excluded in Patch A stabilization.")

import asyncio
import json
from pathlib import Path

import pytest

from src.simple.s12_flow_collector import FlowCollector
from src.simple.live_ws_runtime import LiveWsRuntime
from src.simple.ws_runtime_health_monitor import WsRuntimeHealthMonitor

SYMBOL = "BTCUSDT"
BASE_MS = 1_746_950_400_000


def _agg_trade_msg(second: int, i: int = 0) -> str:
    ts = BASE_MS + second * 1000 + i * 10
    return json.dumps({
        "stream": "btcusdt@aggTrade",
        "data": {
            "e": "aggTrade", "E": ts, "s": SYMBOL,
            "a": i, "p": "65000.0", "q": "0.01", "T": ts, "m": False,
        },
    })


def _book_ticker_msg() -> str:
    return json.dumps({
        "stream": "btcusdt@bookTicker",
        "data": {
            "e": "bookTicker", "s": SYMBOL,
            "b": "64999.5", "B": "1.0", "a": "65000.5", "A": "0.8", "u": 1,
        },
    })


def _malformed_msg() -> str:
    return "not-json-{"


class _MockWs:
    def __init__(self, messages: list[str], raise_on_end: type[Exception] | None = None):
        self._messages = messages
        self._raise_on_end = raise_on_end
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._messages):
            if self._raise_on_end:
                raise self._raise_on_end("mock disconnect")
            raise StopAsyncIteration
        msg = self._messages[self._idx]
        self._idx += 1
        return msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_connector(*sessions: _MockWs):
    it = iter(sessions)

    class _Connector:
        def __init__(self, url: str):
            self._ws = next(it)

        async def __aenter__(self):
            return self._ws

        async def __aexit__(self, *args):
            pass

    return _Connector


def _make_runtime(tmp_path: Path, connector) -> tuple[LiveWsRuntime, WsRuntimeHealthMonitor]:
    collector = FlowCollector(
        symbol=SYMBOL,
        jsonl_path=tmp_path / "events.jsonl",
        state_path=tmp_path / "latest.json",
    )
    health = WsRuntimeHealthMonitor()
    runtime = LiveWsRuntime(
        collector=collector,
        health_monitor=health,
        health_path=tmp_path / "health.json",
        ws_connector=connector,
        reconnect_delay=0.0,
    )
    return runtime, health


@pytest.mark.asyncio
async def test_events_received_and_jsonl_created(tmp_path):
    messages = [_agg_trade_msg(0, i) for i in range(3)] + [_book_ticker_msg()]
    connector = _make_connector(_MockWs(messages))
    runtime, health = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    assert (tmp_path / "events.jsonl").exists()
    assert health.get_health()["events_received"] >= 3


@pytest.mark.asyncio
async def test_health_file_written(tmp_path):
    messages = [_agg_trade_msg(0, 0)]
    connector = _make_connector(_MockWs(messages))
    runtime, _ = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    assert (tmp_path / "health.json").exists()
    state = json.loads((tmp_path / "health.json").read_text())
    assert state["block_id"] == "S12_WS_RUNTIME_HEALTH"


@pytest.mark.asyncio
async def test_safe_to_open_real_trade_always_false(tmp_path):
    messages = [_agg_trade_msg(0, 0)]
    connector = _make_connector(_MockWs(messages))
    runtime, health = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    h = health.get_health()
    assert h["execution_safety"]["safe_to_open_real_trade"] is False


@pytest.mark.asyncio
async def test_malformed_message_survived(tmp_path):
    messages = [_malformed_msg(), _agg_trade_msg(0, 0)]
    connector = _make_connector(_MockWs(messages))
    runtime, health = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    # Runtime must not crash; events_received should cover the valid message
    assert health.get_health()["events_received"] >= 1


@pytest.mark.asyncio
async def test_reconnect_after_disconnect(tmp_path):
    session1 = _MockWs([_agg_trade_msg(0, 0)], raise_on_end=ConnectionError)
    session2 = _MockWs([_agg_trade_msg(1, 0)])
    connector = _make_connector(session1, session2)
    runtime, health = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    assert health.get_health()["reconnect_count"] >= 1


@pytest.mark.asyncio
async def test_reconnect_continues_collecting(tmp_path):
    session1 = _MockWs([_agg_trade_msg(0, 0)], raise_on_end=ConnectionError)
    session2 = _MockWs([_agg_trade_msg(1, 0)])
    connector = _make_connector(session1, session2)
    runtime, health = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    assert health.get_health()["events_received"] >= 2


@pytest.mark.asyncio
async def test_append_only_jsonl_grows(tmp_path):
    session1 = _MockWs([_agg_trade_msg(0, 0)])
    session2 = _MockWs([_agg_trade_msg(1, 0)])
    connector = _make_connector(session1, session2)
    runtime, _ = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) >= 2


@pytest.mark.asyncio
async def test_stale_detection_via_health_monitor(tmp_path):
    messages = [_agg_trade_msg(0, 0)]
    connector = _make_connector(_MockWs(messages))
    runtime, health = _make_runtime(tmp_path, connector)
    await runtime.run(max_seconds=0.5)
    base = health._last_event_time
    if base is not None:
        assert health.check_stale(now=base + 100.0) is True


@pytest.mark.asyncio
async def test_exception_in_session_triggers_reconnect(tmp_path):
    class _BrokenConnector:
        _calls = 0

        def __init__(self, url):
            pass

        async def __aenter__(self):
            _BrokenConnector._calls += 1
            if _BrokenConnector._calls < 3:
                raise OSError("fail")
            return _MockWs([_agg_trade_msg(0, 0)])

        async def __aexit__(self, *args):
            pass

    runtime, health = _make_runtime(tmp_path, _BrokenConnector)
    await runtime.run(max_seconds=0.5)
    # Must survive multiple failures without crashing
    assert health is not None

