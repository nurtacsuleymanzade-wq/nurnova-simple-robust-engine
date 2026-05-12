"""Tests for S26B Live Flow Quality Audit."""

from __future__ import annotations

import json
import pathlib
import shutil
import time
import uuid
from datetime import datetime, timezone

import pytest

from src.simple.live_flow_quality_audit import (
    BLOCK_ID,
    SAFETY,
    run_live_flow_quality_audit,
)

TMP_BASE = pathlib.Path("tmp_pytest_s26b")

REQUIRED_FIELDS = [
    "timestamp_utc", "block_id", "symbol", "audit_window",
    "event_count", "bucket_count", "latest_event_timestamp",
    "latest_event_age_seconds", "events_per_minute", "buckets_per_minute",
    "jsonl_size_bytes", "jsonl_growth_detected", "stale_data",
    "empty_or_low_flow", "quality_label", "quality_score",
    "bottleneck", "final_answer", "recommended_next_fix",
    "data_quality", "reason_codes", "feeds_next", "execution_safety",
]


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


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_flow_events(dd: pathlib.Path, events: list[dict]) -> None:
    path = dd / "live_flow_events.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _fresh_event() -> dict:
    return {"timestamp_utc": _now_utc(), "price": 65000.0, "qty": 0.01}


def _old_event(age_seconds: int = 300) -> dict:
    ts = datetime.utcfromtimestamp(time.time() - age_seconds).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp_utc": ts, "price": 65000.0, "qty": 0.01}


# --------------------------------------------------------------------------- #

class TestMissingJSONL:
    def test_handles_missing_jsonl_safely(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        # No live_flow_events.jsonl written
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["quality_label"] == "NO_DATA"
        assert result["event_count"] == 0

    def test_detects_no_data(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_flow_events(dd, [])
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["quality_label"] == "NO_DATA"
        assert result["quality_score"] == 0.0

    def test_no_data_reason_codes(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert "NO_DATA" in result["reason_codes"]


class TestStaleData:
    def test_detects_stale_data(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_flow_events(dd, [_old_event(age_seconds=300)])
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["quality_label"] == "STALE"
        assert result["stale_data"] is True

    def test_stale_reason_codes(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_flow_events(dd, [_old_event(age_seconds=300)])
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert "STALE_DATA" in result["reason_codes"]


class TestLowFlow:
    def test_detects_low_flow(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        # Only 1 fresh event in 5 min window => very low EPM
        _write_flow_events(dd, [_fresh_event()])
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["quality_label"] in ("DEGRADED", "OK")
        # EPM should be very low
        assert result["events_per_minute"] < 2.0

    def test_low_flow_empty_or_low_flag(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        _write_flow_events(dd, [_fresh_event()])
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["empty_or_low_flow"] is True


class TestOKFlow:
    def test_detects_ok_flow(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        # 200 events spread over last 3 minutes => good EPM
        events = []
        for i in range(200):
            age = i * 0.9  # spread events
            ts = datetime.utcfromtimestamp(time.time() - age).strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append({"timestamp_utc": ts, "price": 65000.0, "qty": 0.01})
        _write_flow_events(dd, events)
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["quality_label"] in ("OK", "HIGH")
        assert result["stale_data"] is False

    def test_ok_flow_reason_codes(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        events = []
        for i in range(200):
            age = i * 0.9
            ts = datetime.utcfromtimestamp(time.time() - age).strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append({"timestamp_utc": ts, "price": 65000.0, "qty": 0.01})
        _write_flow_events(dd, events)
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert "FLOW_OK" in result["reason_codes"]


class TestMetricCalculations:
    def test_calculates_events_per_minute(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        # 60 events in last 60 seconds => ~60 EPM
        events = []
        for i in range(60):
            ts = datetime.utcfromtimestamp(time.time() - i).strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append({"timestamp_utc": ts, "price": 65000.0, "qty": 0.01})
        _write_flow_events(dd, events)
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        # Within 5 min window: 60 events / 300 * 60 = 12 EPM
        assert result["events_per_minute"] > 0

    def test_calculates_bucket_count(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        # 10 events at different seconds
        events = []
        for i in range(10):
            ts = datetime.utcfromtimestamp(time.time() - i * 2).strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append({"timestamp_utc": ts, "price": 65000.0, "qty": 0.01})
        _write_flow_events(dd, events)
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["bucket_count"] >= 1


class TestOutputFiles:
    def test_writes_latest_json(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert (sd / "latest_live_flow_quality_audit.json").exists()

    def test_writes_s26b_state_json(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert (sd / "s26b_live_flow_quality_audit_state.json").exists()

    def test_writes_markdown_report(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        report = rd / "s26b_live_flow_quality_audit_latest_report.md"
        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "S26B" in content

    def test_appends_jsonl_history(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        history = dd / "live_flow_quality_audit_history.jsonl"
        assert history.exists()
        lines = [l for l in history.read_text().splitlines() if l.strip()]
        assert len(lines) >= 2


class TestRequiredFields:
    def test_all_required_fields_present(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        for field in REQUIRED_FIELDS:
            assert field in result, f"Missing field: {field}"


class TestSafetyFlags:
    def test_preserves_safety_flags(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        safety = result["execution_safety"]
        assert safety["safe_to_open_real_trade"] is False
        assert safety["private_api_used"] is False
        assert safety["live_order_sent"] is False

    def test_block_id_correct(self, tmp_dirs):
        sd, dd, rd = tmp_dirs
        result = run_live_flow_quality_audit(_state_dir=sd, _data_dir=dd, _reports_dir=rd)
        assert result["block_id"] == BLOCK_ID


class TestS24Integration:
    def test_s24_integration_includes_s26b(self):
        from src.simple.production_observer import _MODULE_CHAIN
        labels = [label for _, _, label in _MODULE_CHAIN]
        assert "S26B_LIVE_FLOW_QUALITY_AUDIT" in labels

    def test_s26b_after_s26a(self):
        from src.simple.production_observer import _MODULE_CHAIN
        labels = [label for _, _, label in _MODULE_CHAIN]
        assert labels.index("S26A_FULL_CHAIN_TRUTH_AUDIT") < labels.index("S26B_LIVE_FLOW_QUALITY_AUDIT")
