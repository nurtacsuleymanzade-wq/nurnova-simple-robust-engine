from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from ..dna.dna import DNACandle

TIMEFRAMES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1D": 1440,
}

@dataclass
class TFState:
    tf: str
    candles: deque = field(default_factory=lambda: deque(maxlen=50))
    trend: str = "NEUTRAL"   # BULL / BEAR / NEUTRAL
    last_hh: float = 0.0
    last_ll: float = float("inf")

    def update(self, candle: DNACandle):
        self.candles.append(candle)
        self._compute_trend()

    def _compute_trend(self):
        if len(self.candles) < 3:
            return
        highs = [c.high for c in self.candles]
        lows = [c.low for c in self.candles]
        # Simple HH/HL or LL/LH detection on last 10 candles
        recent = list(self.candles)[-10:]
        if len(recent) < 3:
            return
        pivot_highs = []
        pivot_lows = []
        for i in range(1, len(recent) - 1):
            if recent[i].high > recent[i-1].high and recent[i].high > recent[i+1].high:
                pivot_highs.append(recent[i].high)
            if recent[i].low < recent[i-1].low and recent[i].low < recent[i+1].low:
                pivot_lows.append(recent[i].low)

        if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
            if pivot_highs[-1] > pivot_highs[-2] and pivot_lows[-1] > pivot_lows[-2]:
                self.trend = "BULL"
            elif pivot_highs[-1] < pivot_highs[-2] and pivot_lows[-1] < pivot_lows[-2]:
                self.trend = "BEAR"
            else:
                self.trend = "NEUTRAL"
        elif len(recent) >= 5:
            # Fallback: EMA-style slope
            closes = [c.close for c in recent]
            mid = len(closes) // 2
            first_half = sum(closes[:mid]) / mid
            second_half = sum(closes[mid:]) / (len(closes) - mid)
            if second_half > first_half * 1.0005:
                self.trend = "BULL"
            elif second_half < first_half * 0.9995:
                self.trend = "BEAR"
            else:
                self.trend = "NEUTRAL"


@dataclass
class StructureState:
    trends: dict[str, str]      # tf → BULL/BEAR/NEUTRAL
    dominant: str               # 15m trend (primary decision tf)
    confluence: str             # overall direction if 3+ TFs agree


class Structure:
    """Single responsibility: maintain MTF structure state from 1M DNA candles."""

    def __init__(self):
        self._states: dict[str, TFState] = {tf: TFState(tf=tf) for tf in TIMEFRAMES}
        self._1m_bucket: dict[str, Optional[dict]] = {tf: None for tf in TIMEFRAMES if tf != "1m"}

    def ingest(self, candle: DNACandle) -> StructureState:
        """Feed a completed 1M candle, update all timeframe states."""
        minute = candle.ts // 60

        # 1m always updates
        self._states["1m"].update(candle)

        # Higher TFs aggregate from 1M
        for tf, mins in TIMEFRAMES.items():
            if tf == "1m":
                continue
            bucket_id = minute // mins
            b = self._1m_bucket.get(tf)
            if b is None or b["bucket"] != bucket_id:
                if b is not None:
                    # emit completed higher-TF candle
                    htf_candle = self._make_candle(b)
                    self._states[tf].update(htf_candle)
                self._1m_bucket[tf] = {
                    "bucket": bucket_id,
                    "open": candle.open, "high": candle.high, "low": candle.low,
                    "close": candle.close, "volume": candle.volume,
                    "buy_vol": candle.buy_vol, "sell_vol": candle.sell_vol,
                    "ts": candle.ts,
                }
            else:
                b["high"] = max(b["high"], candle.high)
                b["low"] = min(b["low"], candle.low)
                b["close"] = candle.close
                b["volume"] += candle.volume
                b["buy_vol"] += candle.buy_vol
                b["sell_vol"] += candle.sell_vol

        return self.state()

    def _make_candle(self, b: dict) -> DNACandle:
        from ..dna.dna import DNACandle
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        rng = h - l if h != l else 1e-8
        vol = b["volume"] if b["volume"] > 0 else 1e-8
        return DNACandle(
            ts=b["ts"], open=o, high=h, low=l, close=c,
            volume=b["volume"], buy_vol=b["buy_vol"], sell_vol=b["sell_vol"],
            body_ratio=abs(c-o)/rng, upper_wick=(h-max(o,c))/rng,
            lower_wick=(min(o,c)-l)/rng,
            delta_ratio=(b["buy_vol"]-b["sell_vol"])/vol,
            momentum=(c-(h+l)/2)/rng,
            volatility=rng/o if o > 0 else 0,
        )

    def state(self) -> StructureState:
        trends = {tf: s.trend for tf, s in self._states.items()}
        dominant = trends.get("15m", "NEUTRAL")

        votes = list(trends.values())
        bull_count = votes.count("BULL")
        bear_count = votes.count("BEAR")
        if bull_count >= 3:
            confluence = "BULL"
        elif bear_count >= 3:
            confluence = "BEAR"
        else:
            confluence = "NEUTRAL"

        return StructureState(trends=trends, dominant=dominant, confluence=confluence)
