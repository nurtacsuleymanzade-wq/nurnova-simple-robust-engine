from __future__ import annotations

from src.market_state.market_state_classifier import classify_market_state


def _base_records() -> dict[str, dict]:
    return {
        "candle_dna": {"timestamp_utc": "2026-05-18T00:00:00Z", "symbol": "BTCUSDT", "candle_type": "NORMAL"},
        "structure": {"timestamp_utc": "2026-05-18T00:00:01Z", "trend_state": "UPTREND", "structure_label": "HH"},
        "liquidity": {"timestamp_utc": "2026-05-18T00:00:02Z", "draw_on_liquidity": "ABOVE"},
        "flow": {"timestamp_utc": "2026-05-18T00:00:03Z", "cvd_state": "BUY_PRESSURE"},
        "context": {"timestamp_utc": "2026-05-18T00:00:04Z", "auction_state": "ACCEPTANCE", "volatility_state": "NORMAL"},
    }


def _run(records: dict[str, dict]) -> dict:
    return classify_market_state(
        symbol="BTCUSDT",
        evidence_records=records,
        source_files_used=["state/simple/latest_market_structure_v2.json"],
        missing_sources=[],
        parent_lineage_ids=["LIN_PARENT"],
    )


def test_uptrend_classification_pass() -> None:
    payload = _run(_base_records())
    assert payload["market_regime"] == "UPTREND"


def test_downtrend_classification_pass() -> None:
    records = _base_records()
    records["structure"] = {"timestamp_utc": "2026-05-18T00:00:01Z", "trend_state": "DOWNTREND", "structure_label": "LL"}
    records["liquidity"] = {"timestamp_utc": "2026-05-18T00:00:02Z", "draw_on_liquidity": "BELOW"}
    records["flow"] = {"timestamp_utc": "2026-05-18T00:00:03Z", "cvd_state": "SELL_PRESSURE"}
    payload = _run(records)
    assert payload["market_regime"] == "DOWNTREND"


def test_range_classification_pass() -> None:
    records = _base_records()
    records["structure"] = {"timestamp_utc": "2026-05-18T00:00:01Z", "trend_state": "RANGE", "structure_label": "RANGE_BOUND"}
    records["liquidity"] = {"timestamp_utc": "2026-05-18T00:00:02Z", "draw_on_liquidity": "BOTH"}
    records["flow"] = {"timestamp_utc": "2026-05-18T00:00:03Z", "dominant_label": "BALANCED"}
    records["context"] = {"timestamp_utc": "2026-05-18T00:00:04Z", "volatility_state": "LOW", "auction_state": "BALANCE"}
    payload = _run(records)
    assert payload["market_regime"] == "RANGE"


def test_compression_classification_pass() -> None:
    records = _base_records()
    records["structure"] = {"timestamp_utc": "2026-05-18T00:00:01Z", "structure_label": "RANGE_BOUND"}
    records["flow"] = {"timestamp_utc": "2026-05-18T00:00:03Z", "dominant_label": "BALANCED"}
    records["context"] = {"timestamp_utc": "2026-05-18T00:00:04Z", "volatility_state": "COMPRESSING", "auction_state": "BALANCE"}
    payload = _run(records)
    assert payload["market_regime"] == "COMPRESSION"


def test_expansion_classification_pass() -> None:
    records = _base_records()
    records["context"] = {"timestamp_utc": "2026-05-18T00:00:04Z", "volatility_state": "EXPANDING", "auction_state": "DISCOVERY"}
    records["flow"] = {"timestamp_utc": "2026-05-18T00:00:03Z", "cvd_state": "BUY_PRESSURE"}
    payload = _run(records)
    assert payload["market_regime"] == "EXPANSION"


def test_liquidity_hunt_classification_pass() -> None:
    records = _base_records()
    records["liquidity"] = {
        "timestamp_utc": "2026-05-18T00:00:02Z",
        "liquidity_event": "SWEEP",
        "draw_on_liquidity": "BOTH",
    }
    records["flow"] = {"timestamp_utc": "2026-05-18T00:00:03Z", "dominant_label": "BALANCED"}
    payload = _run(records)
    assert payload["market_regime"] == "LIQUIDITY_HUNT"


def test_post_sweep_reaction_classification_pass() -> None:
    records = _base_records()
    records["liquidity"] = {
        "timestamp_utc": "2026-05-18T00:00:02Z",
        "liquidity_event": "SWEEP",
        "reaction_state": "RECLAIM",
    }
    payload = _run(records)
    assert payload["market_regime"] == "POST_SWEEP_REACTION"


def test_reversal_risk_classification_pass() -> None:
    records = _base_records()
    records["context"] = {"timestamp_utc": "2026-05-18T00:00:04Z", "maturity": "LATE_STAGE", "volatility_state": "HIGH"}
    records["flow"] = {"timestamp_utc": "2026-05-18T00:00:03Z", "dominant_label": "DIVERGENT"}
    payload = _run(records)
    assert payload["market_regime"] == "REVERSAL_RISK"


def test_missing_input_files_no_crash_unknown() -> None:
    payload = classify_market_state(
        symbol="BTCUSDT",
        evidence_records={},
        source_files_used=[],
        missing_sources=["state/latest_candle_dna.json"],
        parent_lineage_ids=[],
    )
    assert payload["market_regime"] == "UNKNOWN"
    assert "INSUFFICIENT_EVIDENCE" in payload["reason_codes"]

