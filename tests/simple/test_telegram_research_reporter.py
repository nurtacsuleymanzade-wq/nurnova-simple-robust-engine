from __future__ import annotations

from src.simple.telegram_research_reporter import _instant_signal_message, _summary_message


def test_instant_signal_message_includes_timeframes_and_rr():
    message = _instant_signal_message(
        {
            "symbol": "BTCUSDT",
            "direction": "SHORT",
            "setup_family": "TRAP_REVERSAL",
            "model_id": "DAF_SHORT",
            "primary_tf": "5m",
            "trigger_tf": "1m",
            "context_tf": "15m",
            "expected_hold_label": "15m–120m",
            "entry": 80000,
            "stop_loss": 80100,
            "tp1": 79850,
            "tp2": 79750,
            "rr1": 1.5,
            "rr2": 2.5,
            "timeframe_reason": ["5m trap candle", "15m liquidity sweep", "1m trigger confirmation"],
            "activation_score": 0.9,
        },
        {"war_reading": {}},
        {},
        {"ready_for_paper_research": True},
    )
    assert "Primary TF: 5m" in message
    assert "Trigger TF: 1m" in message
    assert "Context TF: 15m" in message
    assert "Expected Hold: 15m–120m" in message
    assert "RR1: 1.5" in message
    assert "RR2: 2.5" in message
    assert "5m trap candle + 15m liquidity sweep + 1m trigger confirmation" in message


def test_summary_message_includes_timeframe_section():
    text, payload = _summary_message(
        {"symbol": "BTCUSDT", "price": 80000},
        {},
        {},
        {},
        {},
        {"dominant_setup_family": "TRAP_REVERSAL"},
        {"summary": {"open": 1, "closed": 3, "tp": 2, "sl": 1, "expired": 0}, "open_trades": [], "recent_closed": [{"r_result": 1.0}, {"r_result": -1.0}]},
        {"edge_status": "SAMPLE_BUILDING", "groups": [{"setup_family": "TRAP_REVERSAL", "primary_tf": "5m", "context_tf": "15m", "expected_hold_label": "15m–120m", "edge_status": "SAMPLE_BUILDING", "sample_size": 3}]},
        {},
        {},
        {},
        {},
    )
    assert "Dominant Setup: TRAP_REVERSAL" in text
    assert "Primary TF: 5m" in text
    assert "Context TF: 15m" in text
    assert "Expected Hold: 15m–120m" in text
    assert "Edge Status: SAMPLE_BUILDING" in text
    assert payload["timeframe"]["primary_tf"] == "5m"
