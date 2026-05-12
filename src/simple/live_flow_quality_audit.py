"""S26B — Live Flow Quality Audit Engine.

Read-only. Measures live data flow quality: event rate, bucket freshness,
staleness, JSONL growth, observer health.

No fake data. No real trades. safe_to_open_real_trade always False.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S26B_LIVE_FLOW_QUALITY_AUDIT"
SYMBOL = "BTCUSDT"
AUDIT_WINDOW_SECONDS = 300  # 5 minutes

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

LATEST_STATE_PATH = STATE_DIR / "latest_live_flow_quality_audit.json"
S26B_STATE_PATH = STATE_DIR / "s26b_live_flow_quality_audit_state.json"
HISTORY_PATH = DATA_DIR / "live_flow_quality_audit_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s26b_live_flow_quality_audit_latest_report.md"

LIVE_FLOW_JSONL = DATA_DIR / "live_flow_events.jsonl"
OBSERVER_HISTORY_JSONL = DATA_DIR / "production_observer_history.jsonl"
LATEST_FLOW_STATE = STATE_DIR / "latest_flow_state.json"
LATEST_OBSERVER_STATE = STATE_DIR / "latest_production_observer.json"
LATEST_BRAIN_STATE = STATE_DIR / "latest_simple_brain_v2.json"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

STALE_THRESHOLD_SECONDS = 120
LOW_EPM_THRESHOLD = 1.0
LOW_BUCKET_THRESHOLD = 3


# --------------------------------------------------------------------------- #
# I/O helpers
# --------------------------------------------------------------------------- #

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_jsonl_tail(path: Path, max_records: int = 5000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return records
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return records[-max_records:]


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _parse_ts(ts_str: str) -> float | None:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(ts_str, fmt)
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------- #
# Core audit logic
# --------------------------------------------------------------------------- #

def _audit_flow_events(
    events: list[dict[str, Any]],
    now_ts: float,
    audit_window: int,
) -> dict[str, Any]:
    """Analyse flow events within audit window."""
    cutoff = now_ts - audit_window
    windowed = []
    for ev in events:
        ts_str = ev.get("timestamp_utc") or ev.get("ts") or ev.get("time")
        if not ts_str:
            continue
        ts = _parse_ts(str(ts_str))
        if ts is not None and ts >= cutoff:
            windowed.append((ts, ev))

    event_count = len(windowed)
    events_per_minute = (event_count / audit_window) * 60.0 if audit_window > 0 else 0.0

    # Bucket count: unique 1-second timestamps
    bucket_ts_set: set[int] = set()
    for ts, _ in windowed:
        bucket_ts_set.add(int(ts))
    bucket_count = len(bucket_ts_set)
    buckets_per_minute = (bucket_count / audit_window) * 60.0 if audit_window > 0 else 0.0

    # Expected buckets if 1/s data
    expected_buckets = min(audit_window, bucket_count + 1) if bucket_count > 0 else audit_window
    missing_bucket_estimate = max(0, audit_window - bucket_count)

    empty_or_low_flow = event_count == 0 or events_per_minute < LOW_EPM_THRESHOLD

    latest_event_timestamp: str | None = None
    latest_event_age_seconds: float | None = None
    if windowed:
        latest_ts = max(ts for ts, _ in windowed)
        latest_event_age_seconds = now_ts - latest_ts
        latest_event_timestamp = datetime.utcfromtimestamp(latest_ts).strftime("%Y-%m-%dT%H:%M:%SZ")

    stale_data = (
        latest_event_age_seconds is None
        or latest_event_age_seconds > STALE_THRESHOLD_SECONDS
    )

    return {
        "event_count": event_count,
        "bucket_count": bucket_count,
        "latest_event_timestamp": latest_event_timestamp,
        "latest_event_age_seconds": round(latest_event_age_seconds, 1) if latest_event_age_seconds is not None else None,
        "events_per_minute": round(events_per_minute, 2),
        "buckets_per_minute": round(buckets_per_minute, 2),
        "missing_bucket_estimate": missing_bucket_estimate,
        "empty_or_low_flow": empty_or_low_flow,
        "stale_data": stale_data,
    }


def _check_jsonl_growth(path: Path) -> tuple[int, bool]:
    """Return (size_bytes, growth_detected). Growth detected if file exists and non-empty."""
    if not path.exists():
        return 0, False
    size = path.stat().st_size
    # Simple heuristic: if size > 0 and mtime within last 10 minutes, growth detected
    mtime = path.stat().st_mtime
    age = time.time() - mtime
    growth_detected = size > 0 and age < 600
    return size, growth_detected


def _determine_quality(
    event_count: int,
    events_per_minute: float,
    bucket_count: int,
    stale_data: bool,
    empty_or_low_flow: bool,
    jsonl_size_bytes: int,
    has_stale_events: bool = False,
) -> tuple[str, float, str, list[str]]:
    """Returns (quality_label, quality_score, bottleneck, reason_codes)."""
    reason_codes: list[str] = []
    bottleneck = "NONE"

    if jsonl_size_bytes == 0 or (event_count == 0 and not has_stale_events):
        return "NO_DATA", 0.0, "NO_EVENTS_IN_JSONL", ["NO_DATA"]

    if stale_data:
        reason_codes.append("STALE_DATA")
        bottleneck = "STALE_FEED"
        return "STALE", 0.1, bottleneck, reason_codes

    if empty_or_low_flow:
        reason_codes.append("LOW_EPM")
        bottleneck = "LOW_EVENT_RATE"

    if bucket_count < LOW_BUCKET_THRESHOLD:
        reason_codes.append("LOW_BUCKET_COUNT")
        if bottleneck == "NONE":
            bottleneck = "LOW_BUCKET_COUNT"

    if reason_codes:
        score = min(0.4 + (events_per_minute / 10.0) * 0.2, 0.59)
        return "DEGRADED", round(score, 2), bottleneck, reason_codes

    # OK / HIGH
    score = min(0.6 + (events_per_minute / 60.0) * 0.4, 1.0)
    label = "HIGH" if score >= 0.85 else "OK"
    reason_codes.append("FLOW_OK")
    return label, round(score, 2), bottleneck, reason_codes


# --------------------------------------------------------------------------- #
# Report generation
# --------------------------------------------------------------------------- #

def _write_report(record: dict[str, Any]) -> None:
    lines = [
        "# S26B Live Flow Quality Audit",
        "",
        f"**timestamp_utc**: {record['timestamp_utc']}",
        f"**symbol**: {record['symbol']}",
        f"**audit_window**: {record['audit_window']}s",
        "",
        "## Flow Metrics",
        f"- events_per_minute: {record['events_per_minute']}",
        f"- buckets_per_minute: {record['buckets_per_minute']}",
        f"- event_count: {record['event_count']}",
        f"- bucket_count: {record['bucket_count']}",
        f"- latest_event_age_seconds: {record['latest_event_age_seconds']}",
        f"- missing_bucket_estimate: {record['missing_bucket_estimate']}",
        f"- jsonl_size_bytes: {record['jsonl_size_bytes']}",
        f"- jsonl_growth_detected: {record['jsonl_growth_detected']}",
        "",
        "## Quality Assessment",
        f"- **quality_label**: {record['quality_label']}",
        f"- **quality_score**: {record['quality_score']}",
        f"- stale_data: {record['stale_data']}",
        f"- empty_or_low_flow: {record['empty_or_low_flow']}",
        f"- bottleneck: {record['bottleneck']}",
        f"- reason_codes: {record['reason_codes']}",
        "",
        "## Diagnosis",
        f"**final_answer**: {record['final_answer']}",
        f"**recommended_next_fix**: {record['recommended_next_fix']}",
        "",
        "## Safety",
        f"- safe_to_open_real_trade: {record['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {record['execution_safety']['private_api_used']}",
        f"- live_order_sent: {record['execution_safety']['live_order_sent']}",
    ]
    _atomic_write(REPORT_PATH, "\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def run_live_flow_quality_audit(
    _state_dir: Path | None = None,
    _data_dir: Path | None = None,
    _reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Run S26B audit. Returns result dict."""
    # Allow test path overrides
    state_dir = _state_dir or STATE_DIR
    data_dir = _data_dir or DATA_DIR
    reports_dir = _reports_dir or REPORTS_DIR

    live_flow_path = data_dir / "live_flow_events.jsonl"
    latest_state_path = state_dir / "latest_live_flow_quality_audit.json"
    s26b_state_path = state_dir / "s26b_live_flow_quality_audit_state.json"
    history_path = data_dir / "live_flow_quality_audit_history.jsonl"
    report_path = reports_dir / "s26b_live_flow_quality_audit_latest_report.md"

    now_ts = _utc_now_ts()
    audit_window = AUDIT_WINDOW_SECONDS

    events = _load_jsonl_tail(live_flow_path)
    jsonl_size_bytes, jsonl_growth_detected = _check_jsonl_growth(live_flow_path)

    # Detect staleness using all events, not just those in the audit window
    flow_audit = _audit_flow_events(events, now_ts, audit_window)
    if jsonl_size_bytes > 0 and flow_audit["event_count"] == 0:
        # Events exist but none in window — check if there are any events at all
        all_tss = []
        for ev in events:
            ts_str = ev.get("timestamp_utc") or ev.get("ts") or ev.get("time")
            if ts_str:
                ts = _parse_ts(str(ts_str))
                if ts is not None:
                    all_tss.append(ts)
        if all_tss:
            latest_ts = max(all_tss)
            age = now_ts - latest_ts
            latest_ts_str = datetime.utcfromtimestamp(latest_ts).strftime("%Y-%m-%dT%H:%M:%SZ")
            flow_audit["stale_data"] = True
            flow_audit["latest_event_timestamp"] = latest_ts_str
            flow_audit["latest_event_age_seconds"] = round(age, 1)
            # Override quality to STALE rather than NO_DATA
            flow_audit["_has_stale_events"] = True

    has_stale_events = flow_audit.pop("_has_stale_events", False)
    quality_label, quality_score, bottleneck, reason_codes = _determine_quality(
        flow_audit["event_count"],
        flow_audit["events_per_minute"],
        flow_audit["bucket_count"],
        flow_audit["stale_data"],
        flow_audit["empty_or_low_flow"],
        jsonl_size_bytes,
        has_stale_events=has_stale_events,
    )

    # final_answer and recommended_next_fix
    if quality_label == "NO_DATA":
        final_answer = "No live flow events found. Feed not running or JSONL missing."
        recommended_next_fix = "Start live_ws_runtime / raw_flow_event_logger to populate live_flow_events.jsonl"
    elif quality_label == "STALE":
        final_answer = f"Data is stale. Latest event age: {flow_audit['latest_event_age_seconds']}s"
        recommended_next_fix = "Restart WebSocket feed. Check network/binance connection."
    elif quality_label == "DEGRADED":
        final_answer = f"Flow is degraded. EPM={flow_audit['events_per_minute']}, buckets={flow_audit['bucket_count']}"
        recommended_next_fix = "Check raw_flow_event_logger throttling. Verify WS agg trade feed."
    elif quality_label == "OK":
        final_answer = f"Flow OK. EPM={flow_audit['events_per_minute']}, buckets={flow_audit['bucket_count']}"
        recommended_next_fix = "Monitor. Increase audit window if bucket coverage seems low."
    else:  # HIGH
        final_answer = f"Flow HIGH quality. EPM={flow_audit['events_per_minute']}"
        recommended_next_fix = "No action needed. Continue monitoring."

    record: dict[str, Any] = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": SYMBOL,
        "audit_window": audit_window,
        "event_count": flow_audit["event_count"],
        "bucket_count": flow_audit["bucket_count"],
        "latest_event_timestamp": flow_audit["latest_event_timestamp"],
        "latest_event_age_seconds": flow_audit["latest_event_age_seconds"],
        "events_per_minute": flow_audit["events_per_minute"],
        "buckets_per_minute": flow_audit["buckets_per_minute"],
        "missing_bucket_estimate": flow_audit["missing_bucket_estimate"],
        "jsonl_size_bytes": jsonl_size_bytes,
        "jsonl_growth_detected": jsonl_growth_detected,
        "stale_data": flow_audit["stale_data"],
        "empty_or_low_flow": flow_audit["empty_or_low_flow"],
        "quality_label": quality_label,
        "quality_score": quality_score,
        "bottleneck": bottleneck,
        "final_answer": final_answer,
        "recommended_next_fix": recommended_next_fix,
        "data_quality": {"level": quality_label, "score": quality_score},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["S24_VPS_SYSTEMD_24_7_PRODUCTION_OBSERVER"]},
        "execution_safety": {**SAFETY},
    }

    # Write outputs
    _atomic_write(latest_state_path, json.dumps(record, indent=2, ensure_ascii=False))
    _atomic_write(s26b_state_path, json.dumps(record, indent=2, ensure_ascii=False))
    _append_jsonl(history_path, record)

    # Write markdown report
    lines = [
        "# S26B Live Flow Quality Audit",
        "",
        f"**timestamp_utc**: {record['timestamp_utc']}",
        f"**symbol**: {record['symbol']}",
        f"**audit_window**: {record['audit_window']}s",
        "",
        "## Flow Metrics",
        f"- events_per_minute: {record['events_per_minute']}",
        f"- buckets_per_minute: {record['buckets_per_minute']}",
        f"- event_count: {record['event_count']}",
        f"- bucket_count: {record['bucket_count']}",
        f"- latest_event_age_seconds: {record['latest_event_age_seconds']}",
        f"- missing_bucket_estimate: {record['missing_bucket_estimate']}",
        f"- jsonl_size_bytes: {record['jsonl_size_bytes']}",
        f"- jsonl_growth_detected: {record['jsonl_growth_detected']}",
        "",
        "## Quality Assessment",
        f"- **quality_label**: {record['quality_label']}",
        f"- **quality_score**: {record['quality_score']}",
        f"- stale_data: {record['stale_data']}",
        f"- empty_or_low_flow: {record['empty_or_low_flow']}",
        f"- bottleneck: {record['bottleneck']}",
        f"- reason_codes: {record['reason_codes']}",
        "",
        "## Diagnosis",
        f"**final_answer**: {record['final_answer']}",
        f"**recommended_next_fix**: {record['recommended_next_fix']}",
        "",
        "## Safety",
        f"- safe_to_open_real_trade: {record['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {record['execution_safety']['private_api_used']}",
        f"- live_order_sent: {record['execution_safety']['live_order_sent']}",
    ]
    _atomic_write(report_path, "\n".join(lines) + "\n")

    return record
