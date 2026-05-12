"""Tests for WsRuntimeHealthMonitor — state transitions, stale, safety flags."""

from __future__ import annotations

import pytest

from src.simple.ws_runtime_health_monitor import WsRuntimeHealthMonitor


def test_initial_state_disconnected():
    h = WsRuntimeHealthMonitor()
    assert h.get_health()["runtime_status"] == "DISCONNECTED"
    assert h.get_health()["websocket_connected"] is False


def test_on_connected_sets_ok():
    h = WsRuntimeHealthMonitor()
    h.on_connected()
    health = h.get_health()
    assert health["runtime_status"] == "OK"
    assert health["websocket_connected"] is True


def test_on_disconnected_increments_reconnect():
    h = WsRuntimeHealthMonitor()
    h.on_connected()
    h.on_disconnected()
    health = h.get_health()
    assert health["reconnect_count"] == 1
    assert health["websocket_connected"] is False
    assert health["runtime_status"] == "DISCONNECTED"


def test_multiple_reconnects_counted():
    h = WsRuntimeHealthMonitor()
    for _ in range(3):
        h.on_connected()
        h.on_disconnected()
    assert h.get_health()["reconnect_count"] == 3


def test_on_reconnecting_sets_recovering():
    h = WsRuntimeHealthMonitor()
    h.on_reconnecting()
    assert h.get_health()["runtime_status"] == "RECOVERING"


def test_on_message_increments_events():
    h = WsRuntimeHealthMonitor()
    h.on_connected()
    h.on_message()
    h.on_message()
    assert h.get_health()["events_received"] == 2


def test_on_malformed_sets_degraded():
    h = WsRuntimeHealthMonitor()
    h.on_connected()
    h.on_malformed()
    health = h.get_health()
    assert health["runtime_status"] == "DEGRADED"
    assert health["malformed_events"] == 1


def test_stale_detection_with_injected_time():
    h = WsRuntimeHealthMonitor(stale_threshold_seconds=5.0)
    h.on_connected()
    h.on_message()
    # Simulate 10 seconds of staleness
    base = h._last_event_time
    assert h.check_stale(now=base + 3.0) is False
    assert h.check_stale(now=base + 6.0) is True
    assert h.get_health(now=base + 6.0)["runtime_status"] == "DEGRADED"


def test_no_stale_before_first_message():
    h = WsRuntimeHealthMonitor()
    assert h.check_stale() is False
    assert h.get_stale_seconds() == 0.0


def test_safe_to_open_real_trade_always_false():
    h = WsRuntimeHealthMonitor()
    assert h.get_health()["execution_safety"]["safe_to_open_real_trade"] is False
    h.on_connected()
    assert h.get_health()["execution_safety"]["safe_to_open_real_trade"] is False


def test_private_api_used_always_false():
    h = WsRuntimeHealthMonitor()
    assert h.get_health()["execution_safety"]["private_api_used"] is False


def test_health_contains_required_fields():
    h = WsRuntimeHealthMonitor()
    health = h.get_health()
    for field in ("timestamp_utc", "block_id", "websocket_connected",
                  "reconnect_count", "stale_seconds", "events_received",
                  "malformed_events", "runtime_status", "execution_safety"):
        assert field in health


def test_block_id_correct():
    h = WsRuntimeHealthMonitor()
    assert h.get_health()["block_id"] == "S12_WS_RUNTIME_HEALTH"
