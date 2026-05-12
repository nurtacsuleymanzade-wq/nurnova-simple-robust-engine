"""Tests for S12 ws_agg_trade_collector — offline/mock only, no live WS."""

from __future__ import annotations

import pytest

from src.simple.ws_agg_trade_collector import parse_agg_trade, parse_agg_trade_batch

_VALID_BUY_MSG = {
    "e": "aggTrade",
    "E": 1746964801234,
    "s": "BTCUSDT",
    "a": 123456789,
    "p": "104750.00",
    "q": "0.012",
    "T": 1746964801230,
    "m": False,
}

_VALID_SELL_MSG = {
    "e": "aggTrade",
    "E": 1746964802000,
    "s": "BTCUSDT",
    "a": 123456790,
    "p": "104748.00",
    "q": "0.005",
    "T": 1746964801999,
    "m": True,
}


def test_parse_valid_buy_message():
    result = parse_agg_trade(_VALID_BUY_MSG)
    assert result is not None
    assert result["side"] == "BUY"
    assert result["is_buyer_maker"] is False
    assert result["price"] == 104750.0
    assert result["qty"] == 0.012
    assert result["symbol"] == "BTCUSDT"
    assert result["stream"] == "aggTrade"
    assert result["agg_trade_id"] == 123456789


def test_parse_valid_sell_message():
    result = parse_agg_trade(_VALID_SELL_MSG)
    assert result is not None
    assert result["side"] == "SELL"
    assert result["is_buyer_maker"] is True
    assert result["price"] == 104748.0


def test_buyer_maker_true_means_sell_aggression():
    msg = dict(_VALID_BUY_MSG)
    msg["m"] = True
    result = parse_agg_trade(msg)
    assert result is not None
    assert result["side"] == "SELL"


def test_buyer_maker_false_means_buy_aggression():
    msg = dict(_VALID_BUY_MSG)
    msg["m"] = False
    result = parse_agg_trade(msg)
    assert result is not None
    assert result["side"] == "BUY"


def test_wrong_event_type_returns_none():
    msg = dict(_VALID_BUY_MSG)
    msg["e"] = "trade"
    assert parse_agg_trade(msg) is None


def test_missing_price_returns_none():
    msg = {k: v for k, v in _VALID_BUY_MSG.items() if k != "p"}
    assert parse_agg_trade(msg) is None


def test_missing_qty_returns_none():
    msg = {k: v for k, v in _VALID_BUY_MSG.items() if k != "q"}
    assert parse_agg_trade(msg) is None


def test_malformed_price_returns_none():
    msg = dict(_VALID_BUY_MSG)
    msg["p"] = "not_a_number"
    assert parse_agg_trade(msg) is None


def test_empty_dict_returns_none():
    assert parse_agg_trade({}) is None


def test_none_like_dict_returns_none():
    assert parse_agg_trade({"e": "aggTrade"}) is None


def test_required_output_fields():
    result = parse_agg_trade(_VALID_BUY_MSG)
    assert result is not None
    for field in ("timestamp_utc", "stream", "symbol", "agg_trade_id",
                  "price", "qty", "side", "is_buyer_maker",
                  "trade_time_ms", "event_time_ms"):
        assert field in result, f"Missing field: {field}"


def test_batch_filters_malformed():
    messages = [
        _VALID_BUY_MSG,
        {"e": "aggTrade", "p": "bad"},
        _VALID_SELL_MSG,
        {},
    ]
    results = parse_agg_trade_batch(messages)
    assert len(results) == 2
    assert results[0]["side"] == "BUY"
    assert results[1]["side"] == "SELL"


def test_batch_empty_input():
    assert parse_agg_trade_batch([]) == []


def test_batch_all_malformed():
    results = parse_agg_trade_batch([{}, {"e": "other"}, {"p": "bad"}])
    assert results == []
