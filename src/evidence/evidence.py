import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from ..feed.feed import RawTrade

@dataclass
class EvidenceCandle:
    ts: int          # second-epoch bucket
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_vol: float
    sell_vol: float
    trade_count: int

    @property
    def delta(self) -> float:
        return self.buy_vol - self.sell_vol

    @property
    def signal(self) -> str:
        """Momentum direction from this 1s candle."""
        if self.delta > 0 and self.close >= self.open:
            return "BULL"
        if self.delta < 0 and self.close <= self.open:
            return "BEAR"
        return "NEUTRAL"


class Evidence:
    """Single responsibility: aggregate raw trades into 1s OHLCV candles."""

    def __init__(self, history: int = 300):
        self._bucket: Optional[dict] = None
        self._candles: deque[EvidenceCandle] = deque(maxlen=history)

    def ingest(self, trade: RawTrade) -> Optional[EvidenceCandle]:
        """Feed a trade. Returns completed candle when second boundary crossed."""
        ts = int(trade.ts)
        if self._bucket is None:
            self._bucket = self._new_bucket(ts, trade)
            return None

        if ts == self._bucket["ts"]:
            b = self._bucket
            b["high"] = max(b["high"], trade.price)
            b["low"] = min(b["low"], trade.price)
            b["close"] = trade.price
            b["volume"] += trade.qty
            if trade.side == "BUY":
                b["buy_vol"] += trade.qty
            else:
                b["sell_vol"] += trade.qty
            b["count"] += 1
            return None

        # New second — emit completed candle
        candle = self._emit()
        self._bucket = self._new_bucket(ts, trade)
        return candle

    def _new_bucket(self, ts: int, trade: RawTrade) -> dict:
        return {
            "ts": ts,
            "open": trade.price,
            "high": trade.price,
            "low": trade.price,
            "close": trade.price,
            "volume": trade.qty,
            "buy_vol": trade.qty if trade.side == "BUY" else 0.0,
            "sell_vol": trade.qty if trade.side == "SELL" else 0.0,
            "count": 1,
        }

    def _emit(self) -> EvidenceCandle:
        b = self._bucket
        c = EvidenceCandle(
            ts=b["ts"],
            open=b["open"],
            high=b["high"],
            low=b["low"],
            close=b["close"],
            volume=b["volume"],
            buy_vol=b["buy_vol"],
            sell_vol=b["sell_vol"],
            trade_count=b["count"],
        )
        self._candles.append(c)
        return c

    def last_n(self, n: int = 3) -> list[EvidenceCandle]:
        return list(self._candles)[-n:]

    def momentum_signal(self, n: int = 3) -> str:
        """Bull/Bear/Neutral from last n 1s candles."""
        candles = self.last_n(n)
        if len(candles) < n:
            return "NEUTRAL"
        bull = sum(1 for c in candles if c.signal == "BULL")
        bear = sum(1 for c in candles if c.signal == "BEAR")
        if bull >= 2:
            return "BULL"
        if bear >= 2:
            return "BEAR"
        return "NEUTRAL"
