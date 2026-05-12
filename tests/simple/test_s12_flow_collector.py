"""Tests for s12_flow_collector — bucket persistence, quality, safety flags."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.simple.s12_flow_collector import FlowCollector

BASE_MS = 1_746_950_400_000
SYMBOL = "BTCUSDT"


def _collector(tmp_path: Path) -> FlowCollector:
    return FlowCollector(
        symbol=SYMBOL,
        jsonl_path=tmp_path / "events.jsonl",
        state_path=tmp_path / "latest.json",
    )


def _agg_trade(second_offset: int, i: int = 0, is_buyer_maker: bool = False) -> dict:
    ts = BASE_MS + second_offset * 1000 + i * 10
    return {"e": "aggTrade", "E": ts, "s": SYMBOL, "a": i, "p": "65000.0", "q": "0.01", "T": ts, "m": is_buyer_maker}


def _book_ticker(price: float = 65000.0) -> dict:
    return {"e": "bookTicker", "s": SYMBOL, "b": str(price - 0.5), "B": "1.0", "a": str(price + 0.5), "A": "0.8", "u": 1}


def test_jsonl_created_after_flush(tmp_path):
    c = _collector(tmp_path)
    c.ingest(_agg_trade(0, 0))
    c.flush()
    assert (tmp_path / "events.jsonl").exists()


def test_state_created_after_flush(tmp_path):
    c = _collector(tmp_path)
    c.ingest(_agg_trade(0, 0))
    c.flush()
    assert (tmp_path / "latest.json").exists()


def test_bucket_built_on_second_boundary(tmp_path):
    c = _collector(tmp_path)
    c.ingest(_agg_trade(0, 0))
    c.ingest(_agg_trade(1, 1))  # triggers flush of second 0
    state = json.loads((tmp_path / "latest.json").read_text())
    assert state["event_counters"]["buckets_built"] >= 1


def test_malformed_event_tolerated(tmp_path):
    c = _collector(tmp_path)
    c.ingest({"e": "aggTrade", "s": SYMBOL})  # missing required fields
    c.ingest(_agg_trade(0, 0))
    c.flush()
    lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines() if l.strip()]
    malformed = [l for l in lines if l.get("malformed")]
    assert len(malformed) >= 1


def test_safe_to_open_real_trade_always_false(tmp_path):
    c = _collector(tmp_path)
    c.ingest(_agg_trade(0, 0))
    c.flush()
    state = json.loads((tmp_path / "latest.json").read_text())
    assert state["execution_safety"]["safe_to_open_real_trade"] is False


def test_quality_label_in_state(tmp_path):
    c = _collector(tmp_path)
    c.ingest(_book_ticker())
    c.ingest(_agg_trade(0, 0))
    c.flush()
    state = json.loads((tmp_path / "latest.json").read_text())
    assert state["quality_state"]["level"] in ("OK", "DEGRADED", "INVALID")


def test_buy_sell_volumes_in_bucket(tmp_path):
    c = _collector(tmp_path)
    c.ingest(_agg_trade(0, 0, is_buyer_maker=False))  # BUY
    c.ingest(_agg_trade(0, 1, is_buyer_maker=True))   # SELL
    c.flush()
    state = json.loads((tmp_path / "latest.json").read_text())
    bucket = state["latest_bucket"]
    assert bucket["buy_volume"] > 0
    assert bucket["sell_volume"] > 0


def test_counters_increment(tmp_path):
    c = _collector(tmp_path)
    c.ingest(_agg_trade(0, 0))
    c.ingest(_agg_trade(0, 1))
    c.ingest(_book_ticker())
    c.flush()
    state = json.loads((tmp_path / "latest.json").read_text())
    assert state["event_counters"]["agg_trade_events"] >= 2
    assert state["event_counters"]["book_ticker_events"] >= 1
