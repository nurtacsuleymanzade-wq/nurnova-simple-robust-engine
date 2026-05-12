"""Tests for S12 flow_gap_quality_checker."""

from __future__ import annotations

import pytest

from src.simple.flow_gap_quality_checker import check_bucket_quality


def test_all_good_returns_ok():
    q = check_bucket_quality(
        trade_count=10,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
    )
    assert q["level"] == "OK"
    assert q["score"] == 1.0
    assert q["issues"] == []
    assert "DQ_OK" in q["reason_codes"]


def test_agg_trade_ws_disconnected_is_invalid():
    q = check_bucket_quality(
        trade_count=5,
        ws_agg_trade_connected=False,
        ws_book_ticker_connected=True,
    )
    assert q["level"] == "INVALID"
    assert q["score"] == 0.0
    assert "WS_AGG_TRADE_DISCONNECTED" in q["issues"]


def test_book_ticker_ws_disconnected_is_degraded():
    q = check_bucket_quality(
        trade_count=5,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=False,
    )
    assert q["level"] == "DEGRADED"
    assert q["score"] == 0.5
    assert "WS_BOOK_TICKER_DISCONNECTED" in q["issues"]


def test_zero_trades_with_ws_connected_is_degraded():
    q = check_bucket_quality(
        trade_count=0,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
    )
    assert q["level"] == "DEGRADED"
    assert q["score"] == 0.6
    assert "ZERO_TRADES_BUCKET" in q["issues"]


def test_stale_timestamp_is_invalid():
    q = check_bucket_quality(
        trade_count=3,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
        age_seconds=6.0,
    )
    assert q["level"] == "INVALID"
    assert q["score"] == 0.0
    assert "STALE_TIMESTAMP" in q["issues"]


def test_sustained_gap_is_invalid():
    q = check_bucket_quality(
        trade_count=0,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
        consecutive_empty_seconds=5,
    )
    assert q["level"] == "INVALID"
    assert q["score"] == 0.0
    assert "SUSTAINED_GAP" in q["issues"]


def test_malformed_messages_degrade_score():
    q = check_bucket_quality(
        trade_count=10,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
        malformed_count=2,
    )
    assert q["level"] == "DEGRADED"
    assert q["score"] == 0.7
    assert "MALFORMED_MESSAGES" in q["issues"]


def test_score_boundary_zero_point_six():
    q = check_bucket_quality(
        trade_count=0,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
    )
    assert q["score"] == 0.6


def test_score_boundary_zero_point_five():
    q = check_bucket_quality(
        trade_count=10,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=False,
    )
    assert q["score"] == 0.5


def test_score_boundary_zero_point_seven():
    q = check_bucket_quality(
        trade_count=10,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
        malformed_count=1,
    )
    assert q["score"] == 0.7


def test_worst_case_both_disconnected():
    q = check_bucket_quality(
        trade_count=0,
        ws_agg_trade_connected=False,
        ws_book_ticker_connected=False,
    )
    assert q["level"] == "INVALID"
    assert q["score"] == 0.0
    assert "WS_AGG_TRADE_DISCONNECTED" in q["issues"]


def test_reason_codes_not_empty():
    q = check_bucket_quality(
        trade_count=5,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
    )
    assert isinstance(q["reason_codes"], list)
    assert len(q["reason_codes"]) >= 1


def test_stale_threshold_not_exceeded():
    q = check_bucket_quality(
        trade_count=3,
        ws_agg_trade_connected=True,
        ws_book_ticker_connected=True,
        age_seconds=4.9,
    )
    assert "STALE_TIMESTAMP" not in q["issues"]
    assert q["level"] == "OK"
