import time
from dataclasses import dataclass
from ..structure.structure import StructureState
from ..liquidity.liquidity import LiquidityMap

@dataclass
class DecisionResult:
    ts: float
    action: str          # LONG / SHORT / WAIT / NO_TRADE
    score: int           # 0-3 signals aligned
    evidence_signal: str
    dna_signal: str
    structure_signal: str
    liquidity_signal: str
    reason: str
    price: float

    def is_trade(self) -> bool:
        return self.action in ("LONG", "SHORT")


class Decision:
    """Single responsibility: combine 3 signals into LONG/SHORT/WAIT/NO_TRADE."""

    def evaluate(
        self,
        price: float,
        evidence_signal: str,   # BULL/BEAR/NEUTRAL from Evidence
        dna_signal: str,         # BULL/BEAR/NEUTRAL from DNA
        structure: StructureState,
        liquidity: LiquidityMap,
    ) -> DecisionResult:

        structure_signal = structure.dominant  # 15m trend

        # Normalize to LONG/SHORT/NEUTRAL
        ev = self._normalize(evidence_signal)
        dna = self._normalize(dna_signal)
        st = self._normalize(structure_signal)
        liq = liquidity.signal()  # LONG/SHORT/NEUTRAL

        # Count alignment
        signals = [ev, dna, st]
        long_count = signals.count("LONG")
        short_count = signals.count("SHORT")

        # Determine action
        if long_count == 3:
            action = "LONG"
            score = 3
        elif short_count == 3:
            action = "SHORT"
            score = 3
        elif long_count == 2:
            action = "WAIT"
            score = 2
        elif short_count == 2:
            action = "WAIT"
            score = 2
        else:
            action = "NO_TRADE"
            score = max(long_count, short_count)

        # Liquidity confirmation gate: if liquidity disagrees with 3/3, downgrade
        if score == 3 and liq not in ("NEUTRAL", action):
            action = "WAIT"
            score = 2

        reason = (
            f"EV={ev} DNA={dna} ST={st} LIQ={liq} "
            f"=> long={long_count} short={short_count} score={score}"
        )

        return DecisionResult(
            ts=time.time(),
            action=action,
            score=score,
            evidence_signal=ev,
            dna_signal=dna,
            structure_signal=st,
            liquidity_signal=liq,
            reason=reason,
            price=price,
        )

    @staticmethod
    def _normalize(s: str) -> str:
        if s in ("BULL", "LONG"):
            return "LONG"
        if s in ("BEAR", "SHORT"):
            return "SHORT"
        return "NEUTRAL"
