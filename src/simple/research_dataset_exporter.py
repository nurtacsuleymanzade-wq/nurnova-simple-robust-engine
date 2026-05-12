"""S11.3 Research Dataset Exporter — NOVA SIMPLE ROBUST ENGINE v1.

Exports replay research samples into structured CSV and JSON summary.
Research only. No live trading, no private API.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S11_3_RESEARCH_DATASET_EXPORTER"
FEEDS_NEXT = {"next_blocks": ["QUANT_RESEARCH_PIPELINE"]}

EXPORT_FIELDS = [
    "timestamp_utc",
    "scenario_type",
    "setup_type",
    "setup_status",
    "quality_label",
    "decision",
    "paper_outcome",
    "realized_rr",
    "edge_eligible",
    "brain_status",
    "brain_mode",
]

_SCENARIO_TYPE_MAP = {
    "LONG_CONTINUATION": "CONTINUATION",
    "SHORT_CONTINUATION": "CONTINUATION",
    "LONG_REVERSAL": "REVERSAL",
    "SHORT_REVERSAL": "REVERSAL",
    "LONG_BREAKOUT": "BREAKOUT",
    "SHORT_BREAKDOWN": "BREAKDOWN",
    "NO_SETUP": "NO_SETUP",
}

_FAKE_RECORDS: list[dict[str, Any]] = [
    {
        "sample_id": 0, "seed": 42, "symbol": "BTCUSDT",
        "scenario": {
            "candle_direction": "BULLISH", "evidence_label": "LONG_PRESSURE",
            "quality_weight": 0.85, "structure_bias": "bullish",
            "setup_type": "LONG_CONTINUATION", "setup_direction": "LONG", "setup_grade": "A",
        },
        "decision": {
            "paper_decision": "LONG", "entry_price": 105000.0, "stop_loss": 104200.0,
            "tp1": 105600.0, "tp2": 106600.0, "rr_tp1": 0.75, "rr_tp2": 2.0,
        },
        "outcome": {"outcome": "WIN_TP1", "realized_rr": 0.75, "edge_eligible": True},
    },
    {
        "sample_id": 1, "seed": 42, "symbol": "BTCUSDT",
        "scenario": {
            "candle_direction": "BEARISH", "evidence_label": "SHORT_PRESSURE",
            "quality_weight": 0.72, "structure_bias": "bearish",
            "setup_type": "SHORT_CONTINUATION", "setup_direction": "SHORT", "setup_grade": "B",
        },
        "decision": {
            "paper_decision": "SHORT", "entry_price": 105000.0, "stop_loss": 105800.0,
            "tp1": 104400.0, "tp2": 103400.0, "rr_tp1": 0.75, "rr_tp2": 2.0,
        },
        "outcome": {"outcome": "LOSS", "realized_rr": -1.0, "edge_eligible": True},
    },
    {
        "sample_id": 2, "seed": 42, "symbol": "BTCUSDT",
        "scenario": {
            "candle_direction": "DOJI", "evidence_label": "NEUTRAL",
            "quality_weight": 0.45, "structure_bias": "bearish",
            "setup_type": "NO_SETUP", "setup_direction": "NONE", "setup_grade": "NONE",
        },
        "decision": {
            "paper_decision": "NO_TRADE", "entry_price": None, "stop_loss": None,
            "tp1": None, "tp2": None, "rr_tp1": None, "rr_tp2": None,
        },
        "outcome": {"outcome": "NO_TRADE", "realized_rr": None, "edge_eligible": False},
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quality_label(quality_weight: float) -> str:
    if quality_weight >= 0.8:
        return "HIGH_QUALITY"
    if quality_weight >= 0.5:
        return "MEDIUM_QUALITY"
    return "LOW_QUALITY"


def _setup_status(setup_type: str) -> str:
    return "READY_FOR_PLAN" if setup_type != "NO_SETUP" else "NO_SETUP"


def _brain_status(setup_type: str) -> str:
    return "READY" if setup_type != "NO_SETUP" else "IDLE"


def _brain_mode(paper_decision: str) -> str:
    if paper_decision in ("LONG", "SHORT"):
        return f"PAPER_{paper_decision}"
    return "PAPER_IDLE"


def _scenario_type(setup_type: str) -> str:
    return _SCENARIO_TYPE_MAP.get(setup_type, "UNKNOWN")


def parse_replay_record(raw: dict[str, Any], export_ts: str) -> dict[str, Any] | None:
    """Parse one replay_samples.jsonl record into a flat research row.

    Returns None if the record is malformed or missing required fields.
    """
    try:
        scenario = raw["scenario"]
        decision = raw["decision"]
        outcome = raw["outcome"]

        setup_type = str(scenario["setup_type"])
        paper_decision = str(decision["paper_decision"])
        rr_raw = outcome.get("realized_rr")

        return {
            "timestamp_utc": export_ts,
            "scenario_type": _scenario_type(setup_type),
            "setup_type": setup_type,
            "setup_status": _setup_status(setup_type),
            "quality_label": _quality_label(float(scenario["quality_weight"])),
            "decision": paper_decision,
            "paper_outcome": str(outcome["outcome"]),
            "realized_rr": float(rr_raw) if rr_raw is not None else None,
            "edge_eligible": bool(outcome["edge_eligible"]),
            "brain_status": _brain_status(setup_type),
            "brain_mode": _brain_mode(paper_decision),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _compute_export_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [r for r in rows if r["decision"] != "NO_TRADE"]
    eligible = [r for r in rows if r["edge_eligible"]]
    wins = [r for r in eligible if r["paper_outcome"] in {"WIN_TP1", "WIN_TP2"}]
    losses = [r for r in eligible if r["paper_outcome"] == "LOSS"]

    edge_count = len(eligible)
    win_count = len(wins)
    win_rate = round(win_count / edge_count, 4) if edge_count > 0 else None
    rr_vals = [r["realized_rr"] for r in eligible if r["realized_rr"] is not None]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 4) if rr_vals else None

    return {
        "total_samples": len(rows),
        "trades_opened": len(trades),
        "no_trade_count": len(rows) - len(trades),
        "edge_eligible_count": edge_count,
        "win_count": win_count,
        "loss_count": len(losses),
        "win_rate": win_rate,
        "avg_rr_realized": avg_rr,
    }


def _build_data_quality(stats: dict[str, Any]) -> dict[str, Any]:
    n = stats["edge_eligible_count"]
    if n == 0:
        return {"score": 0.0, "level": "CRITICAL", "issues": ["NO_EDGE_ELIGIBLE_SAMPLES"]}
    if n < 10:
        return {"score": 0.3, "level": "LOW", "issues": ["SAMPLE_SIZE_SMALL"]}
    if n < 30:
        return {"score": 0.6, "level": "MEDIUM", "issues": []}
    return {"score": 1.0, "level": "HIGH", "issues": []}


def _build_reason_codes(stats: dict[str, Any], dq: dict[str, Any]) -> list[str]:
    codes: list[str] = [
        "SOURCE_REPLAY_SAMPLES",
        f"TOTAL_SAMPLES_{stats['total_samples']}",
        f"TRADES_OPENED_{stats['trades_opened']}",
        f"EDGE_ELIGIBLE_{stats['edge_eligible_count']}",
        f"WIN_COUNT_{stats['win_count']}",
        f"LOSS_COUNT_{stats['loss_count']}",
    ]
    wr = stats["win_rate"]
    codes.append(f"WIN_RATE_{wr}" if wr is not None else "WIN_RATE_NULL")
    codes.append(f"DATA_QUALITY_{dq['level']}")
    codes.append("RESEARCH_ONLY")
    codes.append("SAFE_TO_OPEN_REAL_TRADE_FALSE")
    return codes


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize rows to CSV string with EXPORT_FIELDS columns."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def build_research_dataset(
    symbol: str,
    raw_records: list[dict[str, Any]],
    source_mode: str = "REPLAY_SAMPLES",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse raw replay records into export rows and a summary.

    Returns (rows, summary). Summary follows the standard JSON contract.
    """
    export_ts = _utc_now()
    rows: list[dict[str, Any]] = []
    skipped = 0
    for raw in raw_records:
        row = parse_replay_record(raw, export_ts)
        if row is not None:
            rows.append(row)
        else:
            skipped += 1

    stats = _compute_export_stats(rows)
    dq = _build_data_quality(stats)
    reason_codes = _build_reason_codes(stats, dq)

    summary = {
        "timestamp_utc": export_ts,
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "source_file": "data/simple/replay_samples.jsonl",
            "records_read": len(raw_records),
            "rows_exported": len(rows),
            "rows_skipped": skipped,
        },
        "export_stats": stats,
        "data_quality": dq,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
            "research_only": True,
        },
    }
    return rows, summary


def run_fake_sample(symbol: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fake-sample entry point — deterministic, no live data."""
    return build_research_dataset(symbol, _FAKE_RECORDS, "FAKE_SAMPLE")
