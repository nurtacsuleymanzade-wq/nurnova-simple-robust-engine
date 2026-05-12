"""S12-B Run Flow Collector — NOVA SIMPLE ROBUST ENGINE v1.

Finite local smoke session. Simulates aggTrade + bookTicker events.
No infinite websocket loop. No live trading. No private API. No orders.

Output:
  data/simple/live_flow_events.jsonl
  state/simple/latest_flow_state.json
"""

from __future__ import annotations

import time
from pathlib import Path

from src.simple.s12_flow_collector import FlowCollector

SYMBOL = "BTCUSDT"
JSONL_PATH = Path("data/simple/live_flow_events.jsonl")
STATE_PATH = Path("state/simple/latest_flow_state.json")

BASE_MS = 1_746_950_400_000  # fixed epoch for deterministic simulation


def _make_agg_trade(i: int, second_offset: int, is_buyer_maker: bool, price: float, qty: float) -> dict:
    ts = BASE_MS + second_offset * 1000 + i * 50
    return {
        "e": "aggTrade",
        "E": ts,
        "s": SYMBOL,
        "a": 100_000 + i,
        "p": str(price),
        "q": str(qty),
        "T": ts,
        "m": is_buyer_maker,
    }


def _make_book_ticker(price: float) -> dict:
    return {
        "e": "bookTicker",
        "s": SYMBOL,
        "b": str(round(price - 0.5, 2)),
        "B": "1.2",
        "a": str(round(price + 0.5, 2)),
        "A": "0.8",
        "u": 999,
    }


def main() -> None:
    collector = FlowCollector(
        symbol=SYMBOL,
        jsonl_path=JSONL_PATH,
        state_path=STATE_PATH,
    )

    # Simulate 3 seconds of events
    price = 65000.0
    trade_idx = 0

    for second in range(3):
        collector.ingest(_make_book_ticker(price + second * 10))

        for j in range(5):
            collector.ingest(_make_agg_trade(trade_idx, second, j % 2 == 0, price + second * 10, 0.01 + j * 0.005))
            trade_idx += 1

        # Force second boundary by injecting a trade in the next second
        if second < 2:
            next_ts = BASE_MS + (second + 1) * 1000
            collector.ingest({
                "e": "aggTrade",
                "E": next_ts,
                "s": SYMBOL,
                "a": 200_000 + second,
                "p": str(price + (second + 1) * 10),
                "q": "0.001",
                "T": next_ts,
                "m": False,
            })
            trade_idx += 1

    # Inject a malformed event to verify tolerance
    collector.ingest({"e": "aggTrade", "s": SYMBOL})

    # Final flush
    collector.flush()

    print(f"JSONL: {JSONL_PATH}")
    print(f"State: {STATE_PATH}")
    print(f"JSONL exists: {JSONL_PATH.exists()}")
    print(f"State exists: {STATE_PATH.exists()}")

    if STATE_PATH.exists():
        import json
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        print(f"Quality level: {state['quality_state']['level']}")
        print(f"Buckets built: {state['event_counters']['buckets_built']}")
        print(f"safe_to_open_real_trade: {state['execution_safety']['safe_to_open_real_trade']}")

    print("\nNUR NOVA SIMPLE S12_B READY")


if __name__ == "__main__":
    main()
