"""S14 — Flow Persistence Engine. Detects whether 1S flow evidence is sustained, fading, flipping, or noisy."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

EVIDENCE_LOG_PATH = DATA_DIR / "flow_evidence.jsonl"
LATEST_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
S14_STATE_PATH = STATE_DIR / "s14_flow_persistence_state.json"
PERSISTENCE_LOG_PATH = DATA_DIR / "flow_persistence.jsonl"
REPORT_PATH = REPORTS_DIR / "s14_flow_persistence_latest_report.md"

WINDOW_SECONDS = {
    "last_30s": 30,
    "last_60s": 60,
    "last_3m":  180,
    "last_5m":  300,
    "last_10m": 600,
    "last_15m": 900,
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts_str: str) -> datetime:
    return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _load_evidence_history(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if "timestamp_utc" in entry and "evidence_score" in entry:
                entries.append(entry)
        except Exception:
            continue
    return entries


def _compute_window(entries: list[dict[str, Any]], ref_time: datetime, window_secs: int) -> dict[str, Any]:
    windowed = []
    for e in entries:
        try:
            age = (ref_time - _parse_ts(e["timestamp_utc"])).total_seconds()
            if 0 <= age <= window_secs:
                windowed.append(e)
        except Exception:
            continue

    n = len(windowed)
    if n == 0:
        return {
            "sample_count": 0,
            "avg_evidence_score": 0.0,
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "dominant_label": "NEUTRAL",
            "direction_consistency": 0.0,
            "confidence_avg": 0.0,
        }

    scores = [float(e["evidence_score"]) for e in windowed]
    confidences = [float(e.get("confidence", 0.0)) for e in windowed]
    avg_score = sum(scores) / n
    pos = sum(1 for s in scores if s > 1.0)
    neg = sum(1 for s in scores if s < -1.0)
    neu = n - pos - neg

    if pos > neg and pos > neu:
        dominant = "LONG"
        dominant_count = pos
    elif neg > pos and neg > neu:
        dominant = "SHORT"
        dominant_count = neg
    else:
        dominant = "NEUTRAL"
        dominant_count = neu

    consistency = dominant_count / n if n > 0 else 0.0
    conf_avg = sum(confidences) / n

    return {
        "sample_count": n,
        "avg_evidence_score": round(avg_score, 4),
        "positive_count": pos,
        "negative_count": neg,
        "neutral_count": neu,
        "dominant_label": dominant,
        "direction_consistency": round(consistency, 4),
        "confidence_avg": round(conf_avg, 4),
    }


def _persistence_label(windows: dict[str, dict]) -> str:
    w30 = windows["last_30s"]
    w60 = windows["last_60s"]
    w3m = windows["last_3m"]
    w5m = windows["last_5m"]
    w10m = windows["last_10m"]
    w15m = windows["last_15m"]

    all_zero = all(windows[k]["sample_count"] == 0 for k in windows)
    if all_zero:
        return "NO_VALID_FLOW"

    if w5m["sample_count"] < 5:
        return "INSUFFICIENT_HISTORY"

    s30  = w30["avg_evidence_score"]
    s5m  = w5m["avg_evidence_score"]
    s15m = w15m["avg_evidence_score"]

    long5m  = s5m > 2.0  and w5m["direction_consistency"] > 0.6
    short5m = s5m < -2.0 and w5m["direction_consistency"] > 0.6
    long15m  = w15m["sample_count"] > 10 and s15m > 1.5
    short15m = w15m["sample_count"] > 10 and s15m < -1.5

    if long5m and long15m:
        return "SUSTAINED_LONG_PRESSURE"
    if short5m and short15m:
        return "SUSTAINED_SHORT_PRESSURE"

    if s30 > 3.0 and long5m:
        return "BUILDING_LONG_MOMENTUM"
    if s30 < -3.0 and short5m:
        return "BUILDING_SHORT_MOMENTUM"

    if long15m and not long5m:
        return "FADING_LONG_PRESSURE"
    if short15m and not short5m:
        return "FADING_SHORT_PRESSURE"

    return "CHOPPY_FLOW"


def _direction_label(persistence_score: float) -> str:
    if persistence_score > 1.0:
        return "LONG"
    if persistence_score < -1.0:
        return "SHORT"
    return "NEUTRAL"


def _continuation_quality(windows: dict[str, dict], label: str) -> str:
    if label in ("INSUFFICIENT_HISTORY", "NO_VALID_FLOW", "CHOPPY_FLOW"):
        return "NONE"
    if label in ("FADING_LONG_PRESSURE", "FADING_SHORT_PRESSURE"):
        return "FADING"
    if label in ("SUSTAINED_LONG_PRESSURE", "SUSTAINED_SHORT_PRESSURE"):
        c15m = windows["last_15m"]["direction_consistency"]
        n15m = windows["last_15m"]["sample_count"]
        if n15m >= 10 and c15m >= 0.70:
            return "SUSTAINED"
        if c15m >= 0.55:
            return "MODERATE"
        return "WEAK"
    if label in ("BUILDING_LONG_MOMENTUM", "BUILDING_SHORT_MOMENTUM"):
        return "BUILDING"
    return "NONE"


def _decay_risk(windows: dict[str, dict], label: str) -> bool:
    if label in ("FADING_LONG_PRESSURE", "FADING_SHORT_PRESSURE"):
        return True
    w30 = windows["last_30s"]
    w15m = windows["last_15m"]
    if w30["sample_count"] < 1 or w15m["sample_count"] < 1:
        return False
    return abs(w30["avg_evidence_score"]) < abs(w15m["avg_evidence_score"]) - 2.0


def _flip_risk(windows: dict[str, dict]) -> bool:
    d30 = windows["last_30s"]["dominant_label"]
    d15m = windows["last_15m"]["dominant_label"]
    if d30 == "NEUTRAL" or d15m == "NEUTRAL":
        return False
    return d30 != d15m


def _data_quality(entries_30s: int, total_entries: int) -> dict[str, Any]:
    if total_entries == 0:
        return {"level": "MISSING", "score": 0.0}
    if entries_30s >= 25:
        return {"level": "OK", "score": 1.0}
    if entries_30s >= 10:
        return {"level": "REDUCED", "score": 0.7}
    if entries_30s >= 3:
        return {"level": "LOW", "score": 0.4}
    return {"level": "INSUFFICIENT", "score": 0.1}


def compute_flow_persistence(
    history: list[dict[str, Any]],
    current: dict[str, Any],
    ref_time: datetime | None = None,
) -> dict[str, Any]:
    ts = _now_utc()
    symbol = current.get("symbol", "UNKNOWN")
    source = current.get("block_id", "S13_1S_FLOW_EVIDENCE_ENGINE")
    input_status = current.get("input_status", "OK")

    if ref_time is None:
        if history:
            try:
                ref_time = _parse_ts(history[-1]["timestamp_utc"])
            except Exception:
                ref_time = datetime.now(timezone.utc)
        else:
            ref_time = datetime.now(timezone.utc)

    windows = {
        name: _compute_window(history, ref_time, secs)
        for name, secs in WINDOW_SECONDS.items()
    }

    total_entries = len(history)
    entries_30s = windows["last_30s"]["sample_count"]
    dq = _data_quality(entries_30s, total_entries)

    plabel = _persistence_label(windows)

    w30  = windows["last_30s"]
    w5m  = windows["last_5m"]
    w15m = windows["last_15m"]
    counts = [w["sample_count"] for w in [w30, w5m, w15m] if w["sample_count"] > 0]
    if counts:
        persistence_score = _clamp(
            round((w30["avg_evidence_score"] * 0.1 + w5m["avg_evidence_score"] * 0.3 + w15m["avg_evidence_score"] * 0.6), 4),
            -10.0,
            10.0,
        )
    else:
        persistence_score = 0.0

    dlabel = _direction_label(persistence_score)
    cquality = _continuation_quality(windows, plabel)
    d_risk = _decay_risk(windows, plabel)
    f_risk = _flip_risk(windows)

    reason_codes = [
        f"SYMBOL_{symbol}",
        f"SOURCE_{source}",
        f"PERSISTENCE_{plabel}",
        f"DIRECTION_{dlabel}",
        f"CONTINUATION_{cquality}",
        f"DQ_{dq['level']}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]
    if d_risk:
        reason_codes.append("DECAY_RISK_DETECTED")
    if f_risk:
        reason_codes.append("FLIP_RISK_DETECTED")

    return {
        "timestamp_utc": ts,
        "block_id": "S14_FLOW_PERSISTENCE_ENGINE",
        "symbol": symbol,
        "source": source,
        "input_status": input_status,
        "windows": windows,
        "persistence_score": persistence_score,
        "persistence_label": plabel,
        "direction_label": dlabel,
        "continuation_quality": cquality,
        "decay_risk": d_risk,
        "flip_risk": f_risk,
        "data_quality": dq,
        "reason_codes": reason_codes,
        "feeds_next": {
            "next_blocks": ["S15_FLOW_TO_SETUP_CONTEXT"],
        },
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_flow_output(reason: str) -> dict[str, Any]:
    ts = _now_utc()
    empty_window = {
        "sample_count": 0,
        "avg_evidence_score": 0.0,
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "dominant_label": "NEUTRAL",
        "direction_consistency": 0.0,
        "confidence_avg": 0.0,
    }
    return {
        "timestamp_utc": ts,
        "block_id": "S14_FLOW_PERSISTENCE_ENGINE",
        "symbol": "UNKNOWN",
        "source": "NONE",
        "input_status": "MISSING",
        "windows": {k: dict(empty_window) for k in WINDOW_SECONDS},
        "persistence_score": 0.0,
        "persistence_label": "NO_VALID_FLOW",
        "direction_label": "UNKNOWN",
        "continuation_quality": "NONE",
        "decay_risk": False,
        "flip_risk": False,
        "data_quality": {"level": "MISSING", "score": 0.0},
        "reason_codes": ["NO_VALID_FLOW", reason, "SAFE_TO_OPEN_REAL_TRADE_FALSE", "NO_PRIVATE_API"],
        "feeds_next": {"next_blocks": ["S15_FLOW_TO_SETUP_CONTEXT"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_flow_persistence_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if not LATEST_EVIDENCE_PATH.exists():
        result = no_valid_flow_output("LATEST_EVIDENCE_FILE_MISSING")
    else:
        try:
            current = json.loads(LATEST_EVIDENCE_PATH.read_text(encoding="utf-8"))
            history = _load_evidence_history(EVIDENCE_LOG_PATH)
            result = compute_flow_persistence(history, current)
        except Exception:
            result = no_valid_flow_output("EVIDENCE_PARSE_ERROR")

    PERSISTENCE_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s14_state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S14_FLOW_PERSISTENCE_STATE",
        "last_persistence_label": result["persistence_label"],
        "last_direction_label": result["direction_label"],
        "last_persistence_score": result["persistence_score"],
        "last_continuation_quality": result["continuation_quality"],
        "runs": 1,
    }
    S14_STATE_PATH.write_text(json.dumps(s14_state, indent=2), encoding="utf-8")

    with PERSISTENCE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)

    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S14 Flow Persistence Engine — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Input Status:** {r['input_status']}",
        f"**Persistence Label:** {r['persistence_label']}",
        f"**Direction Label:** {r['direction_label']}",
        f"**Persistence Score:** {r['persistence_score']}",
        f"**Continuation Quality:** {r['continuation_quality']}",
        f"**Decay Risk:** {r['decay_risk']}",
        f"**Flip Risk:** {r['flip_risk']}",
        "",
        "## Windows",
        "| Window | Samples | Avg Score | Dominant | Consistency |",
        "|--------|---------|-----------|----------|-------------|",
    ]
    for wname, wdata in r["windows"].items():
        lines.append(
            f"| {wname} | {wdata['sample_count']} | {wdata['avg_evidence_score']} | {wdata['dominant_label']} | {wdata['direction_consistency']} |"
        )
    lines += [
        "",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
