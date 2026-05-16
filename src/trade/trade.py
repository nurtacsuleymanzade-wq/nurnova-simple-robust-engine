import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
from ..decision.decision import DecisionResult

# Risk parameters
TP_RATIO = 2.0      # TP = 2x SL distance
SL_ATR_MULT = 1.5   # SL = 1.5 * recent ATR
DEFAULT_SL_PCT = 0.003   # 0.3% fallback SL

@dataclass
class Trade:
    id: str
    side: str           # LONG / SHORT
    entry_price: float
    sl: float
    tp: float
    qty: float          # normalized: 1.0 unit
    open_ts: float
    close_ts: Optional[float] = None
    close_price: Optional[float] = None
    outcome: Optional[str] = None   # TP / SL / MANUAL
    pnl_pct: Optional[float] = None
    decision: Optional[DecisionResult] = None
    conditions: dict = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.outcome is None

    def check(self, price: float) -> Optional[str]:
        """Returns outcome if trade should close, else None."""
        if not self.is_open:
            return None
        if self.side == "LONG":
            if price >= self.tp:
                return "TP"
            if price <= self.sl:
                return "SL"
        else:
            if price <= self.tp:
                return "TP"
            if price >= self.sl:
                return "SL"
        return None

    def close(self, price: float, outcome: str):
        self.close_price = price
        self.close_ts = time.time()
        self.outcome = outcome
        if self.side == "LONG":
            self.pnl_pct = (price - self.entry_price) / self.entry_price * 100
        else:
            self.pnl_pct = (self.entry_price - price) / self.entry_price * 100

    def summary(self) -> str:
        status = f"{self.outcome} {self.pnl_pct:+.3f}%" if not self.is_open else "OPEN"
        return (
            f"[{self.id[:8]}] {self.side} @ {self.entry_price:.2f} "
            f"SL={self.sl:.2f} TP={self.tp:.2f} → {status}"
        )


class TradeManager:
    """Single responsibility: open, manage, close paper trades with TP/SL lifecycle."""

    def __init__(self):
        self._open: list[Trade] = []
        self._closed: list[Trade] = []
        self._total = 0

    def open(self, decision: DecisionResult, atr: float = 0.0) -> Optional[Trade]:
        """Open a paper trade from a decision. Returns None if position already open."""
        if self._open:
            return None  # one position at a time

        sl_dist = max(atr * SL_ATR_MULT, decision.price * DEFAULT_SL_PCT)
        if decision.action == "LONG":
            sl = decision.price - sl_dist
            tp = decision.price + sl_dist * TP_RATIO
        else:
            sl = decision.price + sl_dist
            tp = decision.price - sl_dist * TP_RATIO

        trade = Trade(
            id=str(uuid.uuid4()),
            side=decision.action,
            entry_price=decision.price,
            sl=sl,
            tp=tp,
            qty=1.0,
            open_ts=decision.ts,
            decision=decision,
            conditions={
                "evidence": decision.evidence_signal,
                "dna": decision.dna_signal,
                "structure": decision.structure_signal,
                "liquidity": decision.liquidity_signal,
            },
        )
        self._open.append(trade)
        self._total += 1
        print(f"[Trade] OPEN  {trade.summary()}")
        return trade

    def tick(self, price: float) -> list[Trade]:
        """Check open trades against current price. Returns list of closed trades."""
        closed = []
        still_open = []
        for trade in self._open:
            outcome = trade.check(price)
            if outcome:
                trade.close(price, outcome)
                self._closed.append(trade)
                closed.append(trade)
                print(f"[Trade] CLOSE {trade.summary()}")
            else:
                still_open.append(trade)
        self._open = still_open
        return closed

    def stats(self) -> dict:
        if not self._closed:
            return {"total": 0, "win_rate": 0, "avg_pnl": 0, "open": len(self._open)}
        wins = [t for t in self._closed if t.pnl_pct and t.pnl_pct > 0]
        pnls = [t.pnl_pct for t in self._closed if t.pnl_pct is not None]
        return {
            "total": len(self._closed),
            "open": len(self._open),
            "win_rate": len(wins) / len(self._closed) * 100,
            "avg_pnl": sum(pnls) / len(pnls) if pnls else 0,
            "total_pnl": sum(pnls),
        }

    @property
    def closed_trades(self) -> list[Trade]:
        return list(self._closed)

    @property
    def open_trades(self) -> list[Trade]:
        return list(self._open)
