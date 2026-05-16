import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from ..trade.trade import Trade

EDGE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "state", "edge_matrix.json")

@dataclass
class EdgeEntry:
    condition_key: str
    total: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    win_rate: float = 0.0

    def update(self, trade: Trade):
        self.total += 1
        pnl = trade.pnl_pct or 0.0
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.avg_pnl = self.total_pnl / self.total
        self.win_rate = self.wins / self.total * 100

    def to_dict(self) -> dict:
        return {
            "condition_key": self.condition_key,
            "total": self.total,
            "wins": self.wins,
            "losses": self.losses,
            "total_pnl": round(self.total_pnl, 4),
            "avg_pnl": round(self.avg_pnl, 4),
            "win_rate": round(self.win_rate, 2),
        }


class EdgeMatrix:
    """Single responsibility: learn which conditions produce TP vs SL outcomes."""

    def __init__(self):
        self._matrix: dict[str, EdgeEntry] = {}
        self._load()

    def record(self, trade: Trade):
        """Record a closed trade outcome into the edge matrix."""
        if trade.is_open or not trade.conditions:
            return

        # Build condition key from trade entry conditions
        conds = trade.conditions
        key = (
            f"side={trade.side}|"
            f"ev={conds.get('evidence','?')}|"
            f"dna={conds.get('dna','?')}|"
            f"st={conds.get('structure','?')}|"
            f"liq={conds.get('liquidity','?')}"
        )

        if key not in self._matrix:
            self._matrix[key] = EdgeEntry(condition_key=key)

        self._matrix[key].update(trade)
        self._save()

    def top_edges(self, n: int = 10) -> list[EdgeEntry]:
        """Return top N conditions by win rate (min 3 trades)."""
        qualified = [e for e in self._matrix.values() if e.total >= 3]
        return sorted(qualified, key=lambda e: e.win_rate, reverse=True)[:n]

    def report(self) -> str:
        edges = self.top_edges()
        if not edges:
            return "[EdgeMatrix] No data yet (need 3+ trades per condition)"
        lines = ["[EdgeMatrix] Top edges:"]
        for e in edges:
            lines.append(
                f"  {e.condition_key} | "
                f"total={e.total} win={e.win_rate:.0f}% avg_pnl={e.avg_pnl:+.3f}%"
            )
        return "\n".join(lines)

    def _save(self):
        os.makedirs(os.path.dirname(EDGE_FILE), exist_ok=True)
        data = {k: v.to_dict() for k, v in self._matrix.items()}
        with open(EDGE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        if not os.path.exists(EDGE_FILE):
            return
        try:
            with open(EDGE_FILE) as f:
                data = json.load(f)
            for k, v in data.items():
                e = EdgeEntry(condition_key=k)
                e.total = v["total"]
                e.wins = v["wins"]
                e.losses = v["losses"]
                e.total_pnl = v["total_pnl"]
                e.avg_pnl = v["avg_pnl"]
                e.win_rate = v["win_rate"]
                self._matrix[k] = e
        except Exception as ex:
            print(f"[EdgeMatrix] Load failed: {ex}")
