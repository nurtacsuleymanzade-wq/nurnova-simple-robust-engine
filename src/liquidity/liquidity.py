from collections import deque
from dataclasses import dataclass
from typing import Optional
from ..dna.dna import DNACandle

@dataclass
class LiquidityLevel:
    price: float
    kind: str        # SWING_HIGH / SWING_LOW / EQH / EQL
    touches: int
    swept: bool

@dataclass
class LiquidityMap:
    levels: list[LiquidityLevel]
    nearest_high: Optional[float]   # nearest unswept high above price
    nearest_low: Optional[float]    # nearest unswept low below price
    bias: str                       # LONG (price near low) / SHORT (price near high) / NEUTRAL

    def signal(self) -> str:
        return self.bias


class Liquidity:
    """Single responsibility: identify swing highs/lows and liquidity pools from 1M DNA candles."""

    def __init__(self, history: int = 50):
        self._candles: deque[DNACandle] = deque(maxlen=history)
        self._levels: list[LiquidityLevel] = []

    def ingest(self, candle: DNACandle) -> LiquidityMap:
        self._candles.append(candle)
        self._detect_swings()
        self._check_sweeps(candle)
        return self._build_map(candle.close)

    def _detect_swings(self):
        candles = list(self._candles)
        if len(candles) < 5:
            return

        # Look at candle[-3] as pivot (need left+right confirmation)
        i = len(candles) - 3
        if i < 1:
            return

        pivot = candles[i]
        left = candles[i-1]
        right = candles[i+1]

        # Swing high
        if pivot.high > left.high and pivot.high > right.high:
            if not any(abs(l.price - pivot.high) < pivot.high * 0.0005
                       for l in self._levels if l.kind in ("SWING_HIGH", "EQH")):
                self._levels.append(LiquidityLevel(
                    price=pivot.high, kind="SWING_HIGH", touches=1, swept=False))

        # Swing low
        if pivot.low < left.low and pivot.low < right.low:
            if not any(abs(l.price - pivot.low) < pivot.low * 0.0005
                       for l in self._levels if l.kind in ("SWING_LOW", "EQL")):
                self._levels.append(LiquidityLevel(
                    price=pivot.low, kind="SWING_LOW", touches=1, swept=False))

        # Equal highs/lows (within 0.1%)
        self._detect_equals()

        # Trim old levels
        if len(self._levels) > 40:
            self._levels = self._levels[-40:]

    def _detect_equals(self):
        highs = [l for l in self._levels if l.kind == "SWING_HIGH" and not l.swept]
        lows = [l for l in self._levels if l.kind == "SWING_LOW" and not l.swept]

        for i in range(len(highs) - 1):
            for j in range(i+1, len(highs)):
                if abs(highs[i].price - highs[j].price) / highs[i].price < 0.001:
                    highs[i].kind = "EQH"
                    highs[j].kind = "EQH"

        for i in range(len(lows) - 1):
            for j in range(i+1, len(lows)):
                if abs(lows[i].price - lows[j].price) / lows[i].price < 0.001:
                    lows[i].kind = "EQL"
                    lows[j].kind = "EQL"

    def _check_sweeps(self, candle: DNACandle):
        for level in self._levels:
            if level.swept:
                continue
            if level.kind in ("SWING_HIGH", "EQH") and candle.high > level.price:
                level.swept = True
            if level.kind in ("SWING_LOW", "EQL") and candle.low < level.price:
                level.swept = True

    def _build_map(self, price: float) -> LiquidityMap:
        active = [l for l in self._levels if not l.swept]
        highs_above = sorted([l.price for l in active if l.kind in ("SWING_HIGH", "EQH") and l.price > price])
        lows_below = sorted([l.price for l in active if l.kind in ("SWING_LOW", "EQL") and l.price < price], reverse=True)

        nearest_high = highs_above[0] if highs_above else None
        nearest_low = lows_below[0] if lows_below else None

        # Bias: if closer to low → price likely to sweep high (LONG), vice versa
        bias = "NEUTRAL"
        if nearest_high and nearest_low:
            dist_high = nearest_high - price
            dist_low = price - nearest_low
            if dist_low < dist_high * 0.7:
                bias = "LONG"   # near low, likely sweep upward
            elif dist_high < dist_low * 0.7:
                bias = "SHORT"  # near high, likely sweep downward

        return LiquidityMap(
            levels=active,
            nearest_high=nearest_high,
            nearest_low=nearest_low,
            bias=bias,
        )
