"""S12-C Run Live WS Runtime — NOVA SIMPLE ROBUST ENGINE v1.

Starts real Binance public websocket session for BTCUSDT flow collection.
Runs indefinitely until Ctrl+C. No private API. No orders. No live trading.

Output files (append-only / atomic overwrite):
  data/simple/live_flow_events.jsonl
  state/simple/latest_flow_state.json
  state/simple/live_ws_runtime_health.json
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from pathlib import Path

from src.simple.s12_flow_collector import FlowCollector
from src.simple.live_ws_runtime import LiveWsRuntime
from src.simple.ws_runtime_health_monitor import WsRuntimeHealthMonitor

SYMBOL = "BTCUSDT"
JSONL_PATH = Path("data/simple/live_flow_events.jsonl")
STATE_PATH = Path("state/simple/latest_flow_state.json")
HEALTH_PATH = Path("state/simple/live_ws_runtime_health.json")


async def main() -> None:
    collector = FlowCollector(
        symbol=SYMBOL,
        jsonl_path=JSONL_PATH,
        state_path=STATE_PATH,
    )
    health = WsRuntimeHealthMonitor()
    runtime = LiveWsRuntime(
        collector=collector,
        health_monitor=health,
        health_path=HEALTH_PATH,
    )

    loop = asyncio.get_running_loop()

    def _shutdown(*_):
        print("\n[S12-C] Stopping — safe_to_open_real_trade=false")
        runtime.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except (NotImplementedError, OSError):
            signal.signal(sig, _shutdown)

    print(f"[S12-C] Starting BTCUSDT flow collection")
    print(f"[S12-C] JSONL  -> {JSONL_PATH}")
    print(f"[S12-C] State  -> {STATE_PATH}")
    print(f"[S12-C] Health -> {HEALTH_PATH}")
    print("[S12-C] Press Ctrl+C to stop\n")

    report_task = asyncio.create_task(_status_reporter(health, STATE_PATH, HEALTH_PATH))
    try:
        await runtime.run()
    finally:
        report_task.cancel()
        try:
            await report_task
        except asyncio.CancelledError:
            pass
        collector.flush()
        _print_final(health, STATE_PATH)


async def _status_reporter(
    health: WsRuntimeHealthMonitor,
    state_path: Path,
    health_path: Path,
) -> None:
    while True:
        await asyncio.sleep(5)
        h = health.get_health()
        print(
            f"[S12-C] status={h['runtime_status']} "
            f"events={h['events_received']} "
            f"reconnects={h['reconnect_count']} "
            f"stale={h['stale_seconds']}s"
        )


def _print_final(health: WsRuntimeHealthMonitor, state_path: Path) -> None:
    h = health.get_health()
    print(f"\n[S12-C] Final status  : {h['runtime_status']}")
    print(f"[S12-C] Events recv'd : {h['events_received']}")
    print(f"[S12-C] Reconnects    : {h['reconnect_count']}")
    print(f"[S12-C] JSONL exists  : {JSONL_PATH.exists()}")
    print(f"[S12-C] State exists  : {STATE_PATH.exists()}")
    print(f"[S12-C] Health exists : {HEALTH_PATH.exists()}")
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            print(f"[S12-C] Quality level : {state['quality_state']['level']}")
            print(f"[S12-C] Buckets built : {state['event_counters']['buckets_built']}")
        except Exception:
            pass
    print(f"[S12-C] safe_to_open_real_trade : {h['execution_safety']['safe_to_open_real_trade']}")


if __name__ == "__main__":
    asyncio.run(main())
