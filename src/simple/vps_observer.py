"""S11.5-B VPS Observer — NOVA SIMPLE ROBUST ENGINE v1.

Infinite loop: fetch live Binance 1M candle → run S1-S10 pipeline → append observation.
Paper-only. No private API. No orders. safe_to_open_real_trade always false.

Usage:
    python -m src.simple.vps_observer
    NOVA_SYMBOL=ETHUSDT python -m src.simple.vps_observer
"""

from __future__ import annotations

import importlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.binance_public_feed import fetch_book_ticker, fetch_latest_closed_1m_candle
from src.simple.vps_health_monitor import write_heartbeat

BLOCK_ID = "S11_5_VPS_OBSERVER"
DEFAULT_SYMBOL = "BTCUSDT"

_DATA_DIR = Path("data/simple")
_OBSERVATIONS_FILE = _DATA_DIR / "live_observations.jsonl"
_RAW_FEED_FILE = _DATA_DIR / "live_feed_raw.jsonl"

_S2_MODULE = "src.simple.lightweight_1s_evidence_engine"
_FAKE_STAGES: list[tuple[str, str]] = [
    ("src.simple.hybrid_candle_dna_engine",       "run_fake_sample"),
    ("src.simple.quality_weight_engine",          "run_fake_sample"),
    ("src.simple.liquidity_structure_engine",     "run_fake_sample"),
    ("src.simple.setup_candidate_engine",         "run_fake_sample"),
    ("src.simple.trade_plan_decision_engine",     "run_fake_sample"),
    ("src.simple.paper_outcome_tracker",          "run_fake_sample"),
    ("src.simple.edge_stats_engine",              "run_fake_sample"),
    ("src.simple.simple_brain_report_engine",     "run_fake_sample"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds_to_next_minute() -> float:
    now = time.time()
    return 60.0 - (now % 60.0)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _run_s1(symbol: str, candle: dict[str, Any] | None, ticker: dict[str, float] | None) -> dict[str, Any]:
    from src.simple.market_truth_engine import build_truth
    source_mode = "LIVE_PUBLIC" if candle is not None else "LIVE_NO_DATA"
    return build_truth(symbol, candle, ticker, source_mode)


def _run_s2(symbol: str) -> dict[str, Any]:
    from src.simple.lightweight_1s_evidence_engine import build_evidence
    return build_evidence(symbol, [], 60, "LIVE_NO_TICKS")


def _run_fake_stages(symbol: str) -> list[dict[str, Any]]:
    results = []
    for module_path, func_name in _FAKE_STAGES:
        try:
            mod = importlib.import_module(module_path)
            results.append(getattr(mod, func_name)(symbol))
        except Exception as exc:
            results.append({
                "block_id": module_path.split(".")[-1].upper(),
                "error": str(exc),
                "data_quality": {"level": "CRITICAL", "score": 0.0, "issues": ["STAGE_EXCEPTION"]},
                "reason_codes": ["STAGE_EXCEPTION"],
            })
    return results


def run_one_cycle(symbol: str, cycle_count: int) -> dict[str, Any]:
    """Fetch live data, run pipeline, return observation record."""
    fetch_ts = _utc_now()
    candle = fetch_latest_closed_1m_candle(symbol)
    ticker = fetch_book_ticker(symbol)

    raw_record = {
        "timestamp_utc": fetch_ts,
        "symbol": symbol,
        "cycle": cycle_count,
        "candle": candle,
        "ticker": ticker,
    }
    _append_jsonl(_RAW_FEED_FILE, raw_record)

    s1 = _run_s1(symbol, candle, ticker)
    s2 = _run_s2(symbol)
    fake_results = _run_fake_stages(symbol)

    stage_labels = ["S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]
    stages_summary = {}
    for label, result in zip(stage_labels, fake_results):
        stages_summary[label] = {
            "block_id": result.get("block_id", label),
            "data_quality_level": result.get("data_quality", {}).get("level", "UNKNOWN"),
            "source_mode": "FAKE_SAMPLE",
        }

    observation = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "cycle": cycle_count,
        "fetch_timestamp_utc": fetch_ts,
        "source": {
            "source_mode": "LIVE_PUBLIC",
            "candle_available": candle is not None,
            "ticker_available": ticker is not None,
        },
        "s1_market_truth": s1,
        "s2_evidence": s2,
        "stages_s3_s10": stages_summary,
        "data_quality": s1.get("data_quality", {"level": "UNKNOWN", "score": 0.0, "issues": []}),
        "reason_codes": [
            "SOURCE_LIVE_PUBLIC",
            f"SYMBOL_{symbol}",
            f"CYCLE_{cycle_count}",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_LIVE_TRADING",
            "NO_PRIVATE_API",
            "OBSERVATION_MODE",
            "S2_LIVE_NO_TICKS_DEGRADED",
            "S3_S10_FAKE_SAMPLE",
        ],
        "feeds_next": {"next_blocks": []},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    _append_jsonl(_OBSERVATIONS_FILE, observation)
    return observation


def main() -> None:
    symbol = os.environ.get("NOVA_SYMBOL", DEFAULT_SYMBOL).upper()
    cycle_count = 0
    consecutive_errors = 0
    last_error: str | None = None

    print(f"[VPS_OBSERVER] Starting — symbol={symbol} safe_to_open_real_trade=False")

    while True:
        cycle_count += 1
        try:
            obs = run_one_cycle(symbol, cycle_count)
            consecutive_errors = 0
            last_error = None
            dq_level = obs.get("data_quality", {}).get("level", "UNKNOWN")
            candle_ok = obs["source"]["candle_available"]
            print(f"[VPS_OBSERVER] cycle={cycle_count} candle={candle_ok} dq={dq_level}")
        except Exception as exc:
            consecutive_errors += 1
            last_error = str(exc)
            print(f"[VPS_OBSERVER] cycle={cycle_count} ERROR consecutive={consecutive_errors} err={last_error}")

        write_heartbeat(
            cycle_count=cycle_count,
            consecutive_errors=consecutive_errors,
            last_error=last_error,
        )

        sleep_s = _seconds_to_next_minute()
        time.sleep(max(1.0, sleep_s))


if __name__ == "__main__":
    main()
