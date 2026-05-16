#!/usr/bin/env python3
"""Entry point: run the BTC/USDT paper trading pipeline."""

import asyncio
import signal
import sys
from pipeline import Pipeline


async def main():
    pipeline = Pipeline()

    def handle_exit(sig, frame):
        print("\n[Run] Shutting down...")
        stats = pipeline.trades.stats()
        print(
            f"[Final] Trades={stats['total']} "
            f"WinRate={stats['win_rate']:.1f}% "
            f"TotalPnL={stats['total_pnl']:+.3f}%"
        )
        print(pipeline.edge.report())
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    try:
        await pipeline.run()
    except KeyboardInterrupt:
        handle_exit(None, None)


if __name__ == "__main__":
    asyncio.run(main())
