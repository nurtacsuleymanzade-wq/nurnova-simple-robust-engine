"""S9 Edge Stats Engine — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S9_EDGE_STATS"
FEEDS_NEXT = {"next_blocks": ["S10_SIMPLE_BRAIN"]}

_WIN_OUTCOMES = {"WIN_TP1", "WIN_TP2"}
_LOSS_OUTCOMES = {"LOSS"}

# 3 edge-eligible trades + 2 excluded — enough to exercise all stat paths.
# WIN_TP1 rr=0.625, LOSS rr=-1.0, WIN_TP2 rr=2.0 → win_rate=0.6667, avg_rr=0.5417, edge_score=0.3612
_FAKE_RECORDS: list[dict[str, Any]] = [
    {"outcome": "WIN_TP1",    "realized_rr":  0.625, "edge_eligible": True},
    {"outcome": "LOSS",       "realized_rr": -1.0,   "edge_eligible": True},
    {"outcome": "WIN_TP2",    "realized_rr":  2.0,   "edge_eligible": True},
    {"outcome": "AMBIGUOUS",  "realized_rr": None,   "edge_eligible": False},
    {"outcome": "NOT_OPENED", "realized_rr": None,   "edge_eligible": False},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_s8_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse one raw S8 JSONL record into a flat edge-stats record.

    Returns None if the record is malformed or missing required fields.
    """
    try:
        edge_eligible = bool(raw["edge_eligibility"]["edge_eligible"])
        outcome = str(raw["result"]["outcome"])
        rr_raw = raw["result"].get("realized_rr")
        realized_rr = float(rr_raw) if rr_raw is not None else None
        return {"outcome": outcome, "realized_rr": realized_rr, "edge_eligible": edge_eligible}
    except (KeyError, TypeError, ValueError):
        return None


def _compute_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [r for r in records if r.get("edge_eligible")]
    excluded = len(records) - len(eligible)

    edge_eligible_count = len(eligible)
    win_count = sum(1 for r in eligible if r["outcome"] in _WIN_OUTCOMES)
    loss_count = sum(1 for r in eligible if r["outcome"] in _LOSS_OUTCOMES)

    win_rate = round(win_count / edge_eligible_count, 4) if edge_eligible_count > 0 else None

    rr_values = [r["realized_rr"] for r in eligible if r["realized_rr"] is not None]
    avg_rr_realized = round(sum(rr_values) / len(rr_values), 4) if rr_values else None

    if win_rate is not None and avg_rr_realized is not None:
        edge_score = round(win_rate * avg_rr_realized, 4)
    else:
        edge_score = None

    return {
        "total_records_read": len(records),
        "excluded_count": excluded,
        "edge_eligible_count": edge_eligible_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "avg_rr_realized": avg_rr_realized,
        "edge_score": edge_score,
    }


def _build_data_quality(stats: dict[str, Any]) -> dict[str, Any]:
    n = stats["edge_eligible_count"]
    if n == 0:
        return {"score": 0.0, "level": "CRITICAL", "issues": ["NO_EDGE_ELIGIBLE_TRADES"]}
    if n < 10:
        return {"score": 0.3, "level": "LOW", "issues": ["SAMPLE_SIZE_SMALL"]}
    if n < 30:
        return {"score": 0.6, "level": "MEDIUM", "issues": []}
    return {"score": 1.0, "level": "HIGH", "issues": []}


def _build_reason_codes(
    source_mode: str,
    stats: dict[str, Any],
    data_quality: dict[str, Any],
) -> list[str]:
    codes: list[str] = [f"SOURCE_{source_mode}"]
    codes.append(f"EDGE_ELIGIBLE_COUNT_{stats['edge_eligible_count']}")
    codes.append(f"WIN_COUNT_{stats['win_count']}")
    codes.append(f"LOSS_COUNT_{stats['loss_count']}")
    wr = stats["win_rate"]
    codes.append(f"WIN_RATE_{wr}" if wr is not None else "WIN_RATE_NULL")
    es = stats["edge_score"]
    codes.append(f"EDGE_SCORE_{es}" if es is not None else "EDGE_SCORE_NULL")
    codes.append(f"DATA_QUALITY_{data_quality['level']}")
    return codes


def build_edge_stats(
    symbol: str,
    records: list[dict[str, Any]],
    source_mode: str,
) -> dict[str, Any]:
    stats = _compute_stats(records)
    data_quality = _build_data_quality(stats)
    reason_codes = _build_reason_codes(source_mode, stats, data_quality)

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "total_records_read": stats["total_records_read"],
        },
        "sample_info": {
            "total_records_read": stats["total_records_read"],
            "edge_eligible_count": stats["edge_eligible_count"],
            "excluded_count": stats["excluded_count"],
        },
        "edge_eligible_count": stats["edge_eligible_count"],
        "win_count": stats["win_count"],
        "loss_count": stats["loss_count"],
        "win_rate": stats["win_rate"],
        "avg_rr_realized": stats["avg_rr_realized"],
        "edge_score": stats["edge_score"],
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_edge_stats(symbol, _FAKE_RECORDS, "FAKE_SAMPLE")
