"""Tests for S12 flow_bucket_builder."""

from __future__ import annotations

import pytest

from src.simple.flow_bucket_builder import build_bucket, BLOCK_ID, FEEDS_NEXT

_SYMBOL = "BTCUSDT"
_BUCKET_SECOND = "2026-05-11T12:00:01"

_BOOK_TICKER = {
    "best_bid": 104748.0,
    "best_ask": 104750.0,
    "spread": 2.0,
    "mid_price": 104749.0,
}

_BUY_TRADE = {"price": 104750.0, "qty": 0.1, "side": "BUY"}
_SELL_TRADE = {"price": 104748.0, "qty": 0.05, "side": "SELL"}

_REQUIRED_FIELDS = [
    "timestamp_utc", "block_id", "symbol", "bucket_second",
    "trade_count", "buy_volume", "sell_volume", "total_volume",
    "delta", "delta_ratio", "buy_trade_count", "sell_trade_count",
    "last_price", "best_bid", "best_ask", "spread",
    "aggression_label", "data_quality", "reason_codes",
    "feeds_next", "execution_safety",
]


def _build(**kwargs):
    defaults = dict(
        symbol=_SYMBOL,
        bucket_second=_BUCKET_SECOND,
        trades=[],
        last_book_ticker=_BOOK_TICKER,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
    )
    defaults.update(kwargs)
    return build_bucket(**defaults)


def test_all_required_fields_present():
    bucket = _build(trades=[_BUY_TRADE])
    for field in _REQUIRED_FIELDS:
        assert field in bucket, f"Missing required field: {field}"


def test_block_id_correct():
    bucket = _build()
    assert bucket["block_id"] == BLOCK_ID


def test_feeds_next_points_to_s13():
    bucket = _build()
    assert "S13_1S_FLOW_EVIDENCE" in bucket["feeds_next"]["next_blocks"]


def test_safety_flags():
    bucket = _build()
    safety = bucket["execution_safety"]
    assert safety["safe_to_open_real_trade"] is False
    assert safety["private_api_used"] is False
    assert safety["live_order_sent"] is False


def test_reason_codes_not_empty():
    bucket = _build(trades=[_BUY_TRADE])
    assert isinstance(bucket["reason_codes"], list)
    assert len(bucket["reason_codes"]) >= 1


def test_empty_trades_zero_volumes():
    bucket = _build(trades=[])
    assert bucket["trade_count"] == 0
    assert bucket["buy_volume"] == 0.0
    assert bucket["sell_volume"] == 0.0
    assert bucket["total_volume"] == 0.0
    assert bucket["delta"] == 0.0
    assert bucket["delta_ratio"] == 0.0


def test_empty_trades_quality_degraded():
    bucket = _build(trades=[])
    assert bucket["data_quality"]["level"] == "DEGRADED"
    assert "ZERO_TRADES_BUCKET" in bucket["data_quality"]["issues"]


def test_single_buy_delta_ratio_one():
    bucket = _build(trades=[_BUY_TRADE])
    assert bucket["delta_ratio"] == 1.0
    assert bucket["buy_volume"] == 0.1
    assert bucket["sell_volume"] == 0.0
    assert bucket["buy_trade_count"] == 1
    assert bucket["sell_trade_count"] == 0


def test_single_sell_delta_ratio_minus_one():
    bucket = _build(trades=[_SELL_TRADE])
    assert bucket["delta_ratio"] == -1.0
    assert bucket["sell_volume"] == 0.05
    assert bucket["buy_volume"] == 0.0


def test_mixed_trades_volumes_correct():
    trades = [_BUY_TRADE, _SELL_TRADE]
    bucket = _build(trades=trades)
    assert bucket["buy_volume"] == pytest.approx(0.1)
    assert bucket["sell_volume"] == pytest.approx(0.05)
    assert bucket["total_volume"] == pytest.approx(0.15)
    assert bucket["delta"] == pytest.approx(0.05)
    assert bucket["trade_count"] == 2
    assert bucket["buy_trade_count"] == 1
    assert bucket["sell_trade_count"] == 1


def test_delta_ratio_range():
    trades = [_BUY_TRADE, _SELL_TRADE]
    bucket = _build(trades=trades)
    assert -1.0 <= bucket["delta_ratio"] <= 1.0


def test_book_ticker_fields_populated():
    bucket = _build(trades=[_BUY_TRADE])
    assert bucket["best_bid"] == 104748.0
    assert bucket["best_ask"] == 104750.0
    assert bucket["spread"] == 2.0
    assert bucket["mid_price"] == 104749.0


def test_no_book_ticker_fields_none():
    bucket = _build(trades=[_BUY_TRADE], last_book_ticker=None)
    assert bucket["best_bid"] is None
    assert bucket["best_ask"] is None
    assert bucket["spread"] is None


def test_no_book_ticker_quality_degraded():
    bucket = _build(
        trades=[_BUY_TRADE],
        last_book_ticker=None,
        ws_book_ticker_connected=False,
    )
    assert bucket["data_quality"]["level"] in ("DEGRADED", "INVALID")


def test_ws_disconnected_quality_invalid():
    bucket = _build(
        trades=[],
        ws_agg_trade_connected=False,
    )
    assert bucket["data_quality"]["level"] == "INVALID"
    assert bucket["data_quality"]["score"] == 0.0


def test_aggression_strong_buy():
    big_buy = {"price": 104750.0, "qty": 1.0, "side": "BUY"}
    bucket = _build(trades=[big_buy])
    assert bucket["aggression_label"] == "STRONG_BUY"


def test_aggression_strong_sell():
    big_sell = {"price": 104748.0, "qty": 1.0, "side": "SELL"}
    bucket = _build(trades=[big_sell])
    assert bucket["aggression_label"] == "STRONG_SELL"


def test_aggression_neutral_balanced():
    trades = [
        {"price": 104750.0, "qty": 0.1, "side": "BUY"},
        {"price": 104748.0, "qty": 0.1, "side": "SELL"},
    ]
    bucket = _build(trades=trades)
    assert bucket["aggression_label"] == "NEUTRAL"


def test_gap_detected_false_normal():
    bucket = _build(trades=[_BUY_TRADE])
    assert bucket["gap_detected"] is False


def test_gap_detected_true_when_disconnected():
    bucket = _build(trades=[], ws_agg_trade_connected=False)
    assert bucket["gap_detected"] is True


def test_last_price_set_to_final_trade():
    trades = [_BUY_TRADE, _SELL_TRADE]
    bucket = _build(trades=trades)
    assert bucket["last_price"] == 104748.0


def test_last_price_none_when_no_trades():
    bucket = _build(trades=[])
    assert bucket["last_price"] is None


def test_symbol_and_bucket_second_in_output():
    bucket = _build()
    assert bucket["symbol"] == _SYMBOL
    assert bucket["bucket_second"] == _BUCKET_SECOND


def test_data_quality_ok_with_trades():
    bucket = _build(trades=[_BUY_TRADE])
    assert bucket["data_quality"]["level"] == "OK"
    assert bucket["data_quality"]["score"] == 1.0
