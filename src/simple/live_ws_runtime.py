"""S12-C Live WS Runtime — NOVA SIMPLE ROBUST ENGINE v1.

DUZELTME v3: depth20@100ms stream eklendi.
Streams:
  btcusdt@aggTrade     → buy/sell flow
  btcusdt@bookTicker   → anlık bid/ask
  btcusdt@kline_1m     → 1 dakikalık resmi mum
  btcusdt@depth20@100ms → order book derinliği, duvarlar, sweep riski

No private API. No orders. safe_to_open_real_trade always false.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import websockets
import websockets.exceptions

from src.simple.s12_flow_collector import FlowCollector
from src.simple.ws_runtime_health_monitor import WsRuntimeHealthMonitor

BINANCE_STREAM_URL = (
    "wss://stream.binance.com:9443/stream"
    "?streams="
    "btcusdt@aggTrade"
    "/btcusdt@bookTicker"
    "/btcusdt@kline_1m"
    "/btcusdt@depth20@100ms"
)

_HEARTBEAT_INTERVAL_S = 3.0
_RECONNECT_DELAY_S    = 2.0


class LiveWsRuntime:
    def __init__(
        self,
        collector:       FlowCollector,
        health_monitor:  WsRuntimeHealthMonitor,
        health_path:     str | Path,
        ws_connector:    Callable | None = None,
        reconnect_delay: float = _RECONNECT_DELAY_S,
        stream_url:      str   = BINANCE_STREAM_URL,
    ) -> None:
        self._collector     = collector
        self._health        = health_monitor
        self._health_path   = Path(health_path)
        self._ws_connector  = ws_connector
        self._reconnect_delay = reconnect_delay
        self._stream_url    = stream_url
        self._running       = False

    def stop(self) -> None:
        self._running = False

    async def run(self, max_seconds: float | None = None) -> None:
        self._running = True
        start = time.monotonic()
        connector = self._ws_connector or websockets.connect

        while self._running:
            if max_seconds is not None and (time.monotonic() - start) >= max_seconds:
                break
            try:
                async with connector(self._stream_url) as ws:
                    self._health.on_connected()
                    await self._recv_loop(ws, start, max_seconds)
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError,
            ):
                if not self._running:
                    break
                self._health.on_disconnected()
                await asyncio.sleep(self._reconnect_delay)
                self._health.on_reconnecting()
            except asyncio.CancelledError:
                break

    async def _recv_loop(self, ws: Any, start: float, max_seconds: float | None) -> None:
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        try:
            async for raw_msg in ws:
                if not self._running:
                    break
                if max_seconds is not None and (time.monotonic() - start) >= max_seconds:
                    break
                self._handle_message(raw_msg)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    def _handle_message(self, raw_msg: str | bytes) -> None:
        try:
            outer = json.loads(raw_msg)
            # Combined stream: {"stream": "...", "data": {...}}
            stream_name = outer.get("stream", "")
            data = outer.get("data", outer)

            # depth20 event'i FlowCollector'a gönder
            # event type yok, stream adından anlıyoruz
            if "depth20" in stream_name:
                data["_stream"] = "depth20"

            self._collector.ingest(data)
            self._health.on_message()
            self._write_health()
        except (json.JSONDecodeError, Exception):
            self._collector.ingest({})
            self._health.on_message()

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
            self._health.on_heartbeat()
            self._write_health()

    def _write_health(self) -> None:
        try:
            h    = self._health.get_health()
            dir_ = self._health_path.parent
            dir_.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(h, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self._health_path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        except Exception:
            pass
