import math
from collections import deque
from dataclasses import dataclass
from typing import Optional
from ..evidence.evidence import EvidenceCandle

@dataclass
class DNACandle:
    ts: int          # minute-epoch bucket
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_vol: float
    sell_vol: float
    # DNA features
    body_ratio: float      # |close-open| / (high-low)
    upper_wick: float      # upper wick ratio
    lower_wick: float      # lower wick ratio
    delta_ratio: float     # (buy_vol-sell_vol) / volume
    momentum: float        # close vs mid
    volatility: float      # (high-low) / open

    @property
    def signal(self) -> str:
        if self.delta_ratio > 0.1 and self.close > self.open:
            return "BULL"
        if self.delta_ratio < -0.1 and self.close < self.open:
            return "BEAR"
        return "NEUTRAL"

    def as_dict(self) -> dict:
        return {
            "ts": self.ts,
            "open": self.open, "high": self.high, "low": self.low, "close": self.close,
            "volume": self.volume, "buy_vol": self.buy_vol, "sell_vol": self.sell_vol,
            "body_ratio": self.body_ratio, "upper_wick": self.upper_wick,
            "lower_wick": self.lower_wick, "delta_ratio": self.delta_ratio,
            "momentum": self.momentum, "volatility": self.volatility,
            "signal": self.signal,
        }


class DNA:
    """Single responsibility: build 1M candles with DNA features from 1s evidence."""

    def __init__(self, history: int = 100):
        self._bucket: Optional[dict] = None
        self._candles: deque[DNACandle] = deque(maxlen=history)

    def ingest(self, ev: EvidenceCandle) -> Optional[DNACandle]:
        minute_ts = (ev.ts // 60) * 60
        if self._bucket is None:
            self._bucket = self._new_bucket(minute_ts, ev)
            return None

        if minute_ts == self._bucket["ts"]:
            b = self._bucket
            b["high"] = max(b["high"], ev.high)
            b["low"] = min(b["low"], ev.low)
            b["close"] = ev.close
            b["volume"] += ev.volume
            b["buy_vol"] += ev.buy_vol
            b["sell_vol"] += ev.sell_vol
            return None

        candle = self._emit()
        self._bucket = self._new_bucket(minute_ts, ev)
        return candle

    def _new_bucket(self, ts: int, ev: EvidenceCandle) -> dict:
        return {
            "ts": ts,
            "open": ev.open, "high": ev.high, "low": ev.low, "close": ev.close,
            "volume": ev.volume, "buy_vol": ev.buy_vol, "sell_vol": ev.sell_vol,
        }

    def _emit(self) -> DNACandle:
        b = self._bucket
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        rng = h - l if h != l else 1e-8
        vol = b["volume"] if b["volume"] > 0 else 1e-8

        body = abs(c - o) / rng
        upper = (h - max(o, c)) / rng
        lower = (min(o, c) - l) / rng
        delta_r = (b["buy_vol"] - b["sell_vol"]) / vol
        momentum = (c - (h + l) / 2) / rng
        volatility = rng / o if o > 0 else 0

        candle = DNACandle(
            ts=b["ts"], open=o, high=h, low=l, close=c,
            volume=b["volume"], buy_vol=b["buy_vol"], sell_vol=b["sell_vol"],
            body_ratio=body, upper_wick=upper, lower_wick=lower,
            delta_ratio=delta_r, momentum=momentum, volatility=volatility,
        )
        self._candles.append(candle)
        return candle

    def last(self) -> Optional[DNACandle]:
        return self._candles[-1] if self._candles else None

    def last_n(self, n: int) -> list[DNACandle]:
        return list(self._candles)[-n:]

    def signal(self) -> str:
        c = self.last()
        return c.signal if c else "NEUTRAL"
