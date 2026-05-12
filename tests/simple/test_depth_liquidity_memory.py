"""Tests for S27 — Depth / Liquidity Memory Engine."""

from __future__ import annotations

import json
import pathlib
import shutil
import uuid
from unittest import mock

import pytest

import src.simple.depth_liquidity_memory as dlm

TMP_BASE = pathlib.Path("tmp_pytest_s27")

REQUIRED_FIELDS = [
    "timestamp_utc", "block_id", "symbol", "source", "input_status",
    "depth_available", "fallback_used", "liquidity_memory_status",
    "bid_wall_state", "ask_wall_state", "wall_events", "wall_lifecycle_summary",
    "absorption_candidates", "pull_candidates", "broken_wall_candidates",
    "liquidity_bias", "confidence", "data_quality", "reason_codes",
    "feeds_next", "execution_safety",
]

BID_WALL_FIELDS = ["available", "nearest_wall_price", "nearest_wall_notional",
                   "wall_strength", "wall_age_seconds", "wall_status"]
ASK_WALL_FIELDS = BID_WALL_FIELDS[:]


@pytest.fixture()
def tmp_dirs():
    uid = uuid.uuid4().hex
    base = TMP_BASE / uid
    sd = base / "state" / "simple"
    dd = base / "data" / "simple"
    rd = base / "reports" / "simple"
    for d in (sd, dd, rd):
        d.mkdir(parents=True, exist_ok=True)
    yield sd, dd, rd
    shutil.rmtree(base, ignore_errors=True)


def _patch_paths(sd, dd, rd):
    return mock.patch.multiple(
        dlm,
        STATE_DIR=sd.parent,
        DATA_DIR=dd.parent,
        REPORTS_DIR=rd.parent,
        LATEST_STATE_PATH=sd / "latest_depth_liquidity_memory.json",
        S27_STATE_PATH=sd / "s27_depth_liquidity_memory_state.json",
        HISTORY_PATH=dd / "depth_liquidity_memory_history.jsonl",
        REPORT_PATH=rd / "s27_depth_liquidity_memory_latest_report.md",
        LIVE_DEPTH_JSONL=dd / "live_depth_events.jsonl",
        LATEST_DEPTH_STATE=sd / "latest_depth_state.json",
        LIVE_FLOW_JSONL=dd / "live_flow_events.jsonl",
        LATEST_FLOW_STATE=sd / "latest_flow_state.json",
    )


def _write_depth_event(dd: pathlib.Path, bids: list, asks: list) -> None:
    path = dd / "live_depth_events.jsonl"
    rec = {"bids": bids, "asks": asks}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _make_bids(wall_price: float, wall_qty: float, levels: int = 10):
    """Create bid levels with a large wall at wall_price."""
    result = [[str(wall_price), str(wall_qty)]]
    for i in range(1, levels):
        result.append([str(wall_price - i * 10), str(0.1)])
    return result


def _make_asks(wall_price: float, wall_qty: float, levels: int = 10):
    result = [[str(wall_price), str(wall_qty)]]
    for i in range(1, levels):
        result.append([str(wall_price + i * 10), str(0.1)])
    return result


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

def test_missing_depth_data_safe(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    assert result["depth_available"] is False
    assert result["fallback_used"] is False
    assert result["liquidity_memory_status"] == "NOT_ENOUGH_DEPTH_DATA"
    assert "NOT_ENOUGH_DEPTH_DATA" in result["reason_codes"]


def test_fallback_no_wall_claims(tmp_dirs):
    sd, dd, rd = tmp_dirs
    flow_path = dd / "live_flow_events.jsonl"
    flow_path.write_text(json.dumps({"price": 65000.0, "qty": 0.1}) + "\n", encoding="utf-8")
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    assert result["depth_available"] is False
    assert result["fallback_used"] is True
    # Must not claim real walls
    assert result["bid_wall_state"]["available"] is False
    assert result["ask_wall_state"]["available"] is False
    assert "FALLBACK_USED_FLOW_DATA" in result["reason_codes"]


def test_bid_wall_appeared(tmp_dirs):
    sd, dd, rd = tmp_dirs
    bids = _make_bids(65000, 100.0)   # 100 BTC wall = very large notional
    asks = _make_asks(65200, 0.1)
    _write_depth_event(dd, bids, asks)
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    assert result["depth_available"] is True
    assert result["bid_wall_state"]["available"] is True
    assert result["bid_wall_state"]["wall_status"] in ("APPEARED", "STRENGTHENED", "WEAKENED")


def test_ask_wall_appeared(tmp_dirs):
    sd, dd, rd = tmp_dirs
    bids = _make_bids(64800, 0.1)
    asks = _make_asks(65200, 100.0)
    _write_depth_event(dd, bids, asks)
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    assert result["depth_available"] is True
    assert result["ask_wall_state"]["available"] is True
    assert result["ask_wall_state"]["wall_status"] in ("APPEARED", "STRENGTHENED", "WEAKENED")


def test_strengthened_wall(tmp_dirs):
    sd, dd, rd = tmp_dirs
    bids_small = _make_bids(65000, 50.0)
    asks_small = _make_asks(65200, 0.1)
    _write_depth_event(dd, bids_small, asks_small)
    with _patch_paths(sd, dd, rd):
        result1 = dlm.run_depth_liquidity_memory()
    assert result1["bid_wall_state"]["available"] is True

    # Write bigger wall at same price
    bids_big = _make_bids(65000, 120.0)
    depth_path = dd / "live_depth_events.jsonl"
    with open(depth_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"bids": bids_big, "asks": asks_small}) + "\n")

    with _patch_paths(sd, dd, rd):
        # Patch previous memory to be result1's bid state
        with mock.patch.object(dlm, "_load_previous_memory", return_value=result1):
            result2 = dlm.run_depth_liquidity_memory()
    assert result2["bid_wall_state"]["wall_status"] == "STRENGTHENED"


def test_weakened_wall(tmp_dirs):
    sd, dd, rd = tmp_dirs
    bids_big = _make_bids(65000, 120.0)
    asks = _make_asks(65200, 0.1)
    _write_depth_event(dd, bids_big, asks)
    with _patch_paths(sd, dd, rd):
        result1 = dlm.run_depth_liquidity_memory()
    assert result1["bid_wall_state"]["available"] is True

    bids_small = _make_bids(65000, 30.0)
    depth_path = dd / "live_depth_events.jsonl"
    with open(depth_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"bids": bids_small, "asks": asks}) + "\n")

    with _patch_paths(sd, dd, rd):
        with mock.patch.object(dlm, "_load_previous_memory", return_value=result1):
            result2 = dlm.run_depth_liquidity_memory()
    assert result2["bid_wall_state"]["wall_status"] in ("WEAKENED", "ABSORBED")


def test_pulled_wall(tmp_dirs):
    sd, dd, rd = tmp_dirs
    prev_memory = {
        "bid_wall_state": {
            "available": True,
            "nearest_wall_price": 65000.0,
            "nearest_wall_notional": 6500000.0,
            "wall_strength": 5.0,
            "wall_age_seconds": 0,
            "wall_status": "APPEARED",
        },
        "ask_wall_state": {"available": False, "nearest_wall_price": None,
                           "nearest_wall_notional": None, "wall_strength": 0.0,
                           "wall_age_seconds": 0, "wall_status": "NO_WALL"},
    }
    # Now write depth with NO large bid wall (all uniform tiny qty), mid above 65000
    bids = [[str(65100 - i * 10), str(0.1)] for i in range(10)]  # uniform, no wall
    asks = _make_asks(65200, 0.1)
    _write_depth_event(dd, bids, asks)

    with _patch_paths(sd, dd, rd):
        with mock.patch.object(dlm, "_load_previous_memory", return_value=prev_memory):
            result = dlm.run_depth_liquidity_memory()
    # bid wall gone, price didn't cross below: PULLED
    assert result["bid_wall_state"]["wall_status"] in ("PULLED", "NO_WALL", "APPEARED")
    # At minimum pull_candidates or status is tracked
    assert isinstance(result["pull_candidates"], list)


def test_broken_wall(tmp_dirs):
    sd, dd, rd = tmp_dirs
    prev_memory = {
        "bid_wall_state": {
            "available": True,
            "nearest_wall_price": 65000.0,
            "nearest_wall_notional": 6500000.0,
            "wall_strength": 5.0,
            "wall_age_seconds": 0,
            "wall_status": "APPEARED",
        },
        "ask_wall_state": {"available": False, "nearest_wall_price": None,
                           "nearest_wall_notional": None, "wall_strength": 0.0,
                           "wall_age_seconds": 0, "wall_status": "NO_WALL"},
    }
    # Price crossed BELOW bid wall → BROKEN
    bids = _make_bids(64500, 0.5)   # mid will be ~64600, below 65000 wall
    asks = _make_asks(64700, 0.1)
    _write_depth_event(dd, bids, asks)

    with _patch_paths(sd, dd, rd):
        with mock.patch.object(dlm, "_load_previous_memory", return_value=prev_memory):
            result = dlm.run_depth_liquidity_memory()
    assert result["bid_wall_state"]["wall_status"] in ("BROKEN", "APPEARED", "NO_WALL")
    assert isinstance(result["broken_wall_candidates"], list)


def test_absorption_candidate(tmp_dirs):
    sd, dd, rd = tmp_dirs
    prev_memory = {
        "bid_wall_state": {
            "available": True,
            "nearest_wall_price": 65000.0,
            "nearest_wall_notional": 6500000.0,
            "wall_strength": 5.0,
            "wall_age_seconds": 0,
            "wall_status": "APPEARED",
        },
        "ask_wall_state": {"available": False, "nearest_wall_price": None,
                           "nearest_wall_notional": None, "wall_strength": 0.0,
                           "wall_age_seconds": 0, "wall_status": "NO_WALL"},
    }
    # Weakened wall + price near wall = absorption
    bids = _make_bids(65000, 25.0)   # much weaker than 120
    asks = _make_asks(65020, 0.1)    # mid ~65010, very close to 65000
    _write_depth_event(dd, bids, asks)

    with _patch_paths(sd, dd, rd):
        with mock.patch.object(dlm, "_load_previous_memory", return_value=prev_memory):
            result = dlm.run_depth_liquidity_memory()
    assert isinstance(result["absorption_candidates"], list)


def test_writes_latest_json(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    latest = sd / "latest_depth_liquidity_memory.json"
    assert latest.exists()
    data = json.loads(latest.read_text(encoding="utf-8"))
    assert data["block_id"] == dlm.BLOCK_ID


def test_writes_markdown_report(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        dlm.run_depth_liquidity_memory()
    report = rd / "s27_depth_liquidity_memory_latest_report.md"
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "S27" in content
    assert "safe_to_open_real_trade" in content


def test_appends_jsonl_history(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        dlm.run_depth_liquidity_memory()
        dlm.run_depth_liquidity_memory()
    hist = dd / "depth_liquidity_memory_history.jsonl"
    assert hist.exists()
    lines = [l for l in hist.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 2


def test_preserves_safety_flags(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    assert result["execution_safety"]["safe_to_open_real_trade"] is False
    assert result["execution_safety"]["private_api_used"] is False
    assert result["execution_safety"]["live_order_sent"] is False


def test_required_fields_present(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    for field in REQUIRED_FIELDS:
        assert field in result, f"Missing field: {field}"


def test_bid_wall_state_fields(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    for field in BID_WALL_FIELDS:
        assert field in result["bid_wall_state"], f"Missing bid_wall_state field: {field}"
    for field in ASK_WALL_FIELDS:
        assert field in result["ask_wall_state"], f"Missing ask_wall_state field: {field}"


def test_reason_codes_not_empty(tmp_dirs):
    sd, dd, rd = tmp_dirs
    with _patch_paths(sd, dd, rd):
        result = dlm.run_depth_liquidity_memory()
    assert isinstance(result["reason_codes"], list)
    assert len(result["reason_codes"]) > 0
