"""
Pipeline: BTC/USDT trading system orchestrator.

Flow: Feed → Evidence → DNA → Structure → Liquidity → Decision → Trade → Edge
"""

import asyncio
import time
from collections import deque
from typing import Optional

from src.feed.feed import Feed
from src.evidence.evidence import Evidence
from src.dna.dna import DNA, DNACandle
from src.structure.structure import Structure
from src.liquidity.liquidity import Liquidity
from src.decision.decision import Decision
from src.trade.trade import TradeManager
from src.edge.edge import EdgeMatrix

DECISION_INTERVAL = 5   # evaluate decision every N seconds
REPORT_INTERVAL = 60    # print stats every N seconds


class Pipeline:
    def __init__(self):
        self.feed = Feed()
        self.evidence = Evidence(history=300)
        self.dna = DNA(history=100)
        self.structure = Structure()
        self.liquidity = Liquidity(history=50)
        self.decision = Decision()
        self.trades = TradeManager()
        self.edge = EdgeMatrix()

        self._last_decision_ts = 0.0
        self._last_report_ts = 0.0
        self._last_price = 0.0
        self._atr_samples: deque[float] = deque(maxlen=14)
        self._running = False

    async def run(self):
        self._running = True
        await self.feed.start()
        print("[Pipeline] Started — streaming BTC/USDT from Binance")

        asyncio.create_task(self._decision_loop())
        asyncio.create_task(self._report_loop())

        async for trade_data in self.feed.stream():
            self._last_price = trade_data.price

            # 1. Evidence: aggregate 1s candles
            ev_candle = self.evidence.ingest(trade_data)
            if ev_candle is None:
                continue

            # 2. DNA: build 1M candles
            dna_candle = self.dna.ingest(ev_candle)
            if dna_candle is None:
                continue

            # Track ATR
            self._atr_samples.append(dna_candle.high - dna_candle.low)

            # 3. Structure: update MTF
            self.structure.ingest(dna_candle)

            # 4. Liquidity: update map
            self.liquidity.ingest(dna_candle)

            # 5. Trade lifecycle: check open trades
            closed = self.trades.tick(self._last_price)
            for t in closed:
                self.edge.record(t)

    async def _decision_loop(self):
        """Evaluate trading decision every DECISION_INTERVAL seconds."""
        while self._running:
            await asyncio.sleep(DECISION_INTERVAL)
            if self._last_price == 0:
                continue

            try:
                ev_signal = self.evidence.momentum_signal(n=3)
                dna_signal = self.dna.signal()
                structure_state = self.structure.state()
                liquidity_map = self.liquidity._build_map(self._last_price)

                result = self.decision.evaluate(
                    price=self._last_price,
                    evidence_signal=ev_signal,
                    dna_signal=dna_signal,
                    structure=structure_state,
                    liquidity=liquidity_map,
                )

                print(
                    f"[Decision] {result.action:8s} score={result.score}/3 "
                    f"price={result.price:.2f} | {result.reason}"
                )

                if result.is_trade():
                    atr = sum(self._atr_samples) / len(self._atr_samples) if self._atr_samples else 0
                    self.trades.open(result, atr=atr)

            except Exception as e:
                print(f"[Decision] Error: {e}")

    async def _report_loop(self):
        """Print stats every REPORT_INTERVAL seconds."""
        while self._running:
            await asyncio.sleep(REPORT_INTERVAL)
            stats = self.trades.stats()
            print(
                f"\n[Stats] Trades={stats['total']} Open={stats['open']} "
                f"WinRate={stats['win_rate']:.1f}% "
                f"AvgPnL={stats['avg_pnl']:+.3f}% "
                f"TotalPnL={stats['total_pnl']:+.3f}%"
            )
            print(self.edge.report())
            print()

    async def stop(self):
        self._running = False
        await self.feed.stop()
