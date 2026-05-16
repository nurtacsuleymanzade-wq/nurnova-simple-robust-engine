import asyncio
import json
import time
import websockets
from dataclasses import dataclass
from typing import AsyncIterator

BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@trade"

@dataclass
class RawTrade:
    ts: float        # epoch seconds
    price: float
    qty: float
    side: str        # BUY or SELL

class Feed:
    """Single responsibility: stream raw BTC/USDT trades from Binance WebSocket."""

    def __init__(self):
        self._queue: asyncio.Queue[RawTrade] = asyncio.Queue(maxsize=10000)
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._connect())

    async def stop(self):
        self._running = False

    async def _connect(self):
        while self._running:
            try:
                async with websockets.connect(BINANCE_WS, ping_interval=20) as ws:
                    print("[Feed] Connected to Binance WebSocket")
                    async for raw in ws:
                        if not self._running:
                            break
                        msg = json.loads(raw)
                        trade = RawTrade(
                            ts=msg["T"] / 1000.0,
                            price=float(msg["p"]),
                            qty=float(msg["q"]),
                            side="SELL" if msg["m"] else "BUY",
                        )
                        try:
                            self._queue.put_nowait(trade)
                        except asyncio.QueueFull:
                            self._queue.get_nowait()  # drop oldest
                            self._queue.put_nowait(trade)
            except Exception as e:
                print(f"[Feed] Error: {e} — reconnecting in 3s")
                await asyncio.sleep(3)

    async def stream(self) -> AsyncIterator[RawTrade]:
        while self._running:
            try:
                trade = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield trade
            except asyncio.TimeoutError:
                continue
