"""S13 — 1S Flow Evidence Engine. Converts raw 1S flow buckets into directional evidence."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"
EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
S13_STATE_PATH = STATE_DIR / "s13_flow_evidence_state.json"
EVIDENCE_LOG_PATH = DATA_DIR / "flow_evidence.jsonl"
REPORT_PATH = REPORTS_DIR / "s13_flow_evidence_latest_report.md"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _score_delta(delta: float, total_volume: float) -> float:
    if total_volume == 0:
        return 0.0
    ratio = delta / total_volume
    return _clamp(ratio * 10.0, -10.0, 10.0)


def _score_aggression(buy_count: int, sell_count: int) -> float:
    total = buy_count + sell_count
    if total == 0:
        return 0.0
    ratio = (buy_count - sell_count) / total
    return _clamp(ratio * 10.0, -10.0, 10.0)


def _score_pressure(buy_vol: float, sell_vol: float) -> float:
    total = buy_vol + sell_vol
    if total == 0:
        return 0.0
    ratio = (buy_vol - sell_vol) / total
    return _clamp(ratio * 10.0, -10.0, 10.0)


def _pressure_label(pressure_score: float) -> str:
    if pressure_score >= 3.0:
        return "BUY_DOMINANT"
    if pressure_score <= -3.0:
        return "SELL_DOMINANT"
    if abs(pressure_score) < 1.5:
        return "BALANCED"
    return "BALANCED"


def _evidence_label(evidence_score: float) -> str:
    if evidence_score >= 6.0:
        return "STRONG_LONG_PRESSURE"
    if evidence_score >= 2.0:
        return "EARLY_LONG_PRESSURE"
    if evidence_score <= -6.0:
        return "STRONG_SHORT_PRESSURE"
    if evidence_score <= -2.0:
        return "EARLY_SHORT_PRESSURE"
    return "NEUTRAL_FLOW"


def _confidence(delta_score: float, aggression_score: float, pressure_score: float, dq_score: float) -> float:
    avg_abs = (abs(delta_score) + abs(aggression_score) + abs(pressure_score)) / 30.0
    conf = avg_abs * dq_score
    return _clamp(round(conf, 4), 0.0, 1.0)


def compute_flow_evidence(flow_state: dict[str, Any]) -> dict[str, Any]:
    ts = _now_utc()
    bucket = flow_state.get("latest_bucket", {})
    symbol = bucket.get("symbol", "UNKNOWN")
    source = bucket.get("source", "S12_FLOW_STATE")

    buy_vol = float(bucket.get("buy_volume", 0.0))
    sell_vol = float(bucket.get("sell_volume", 0.0))
    delta = float(bucket.get("delta", 0.0))
    total_vol = float(bucket.get("total_volume", 0.0))
    buy_count = int(bucket.get("buy_trade_count", 0))
    sell_count = int(bucket.get("sell_trade_count", 0))
    dq = flow_state.get("quality_state", {})
    dq_score = float(dq.get("score", 1.0))
    dq_level = dq.get("level", "OK")

    delta_score = _score_delta(delta, total_vol)
    aggression_score = _score_aggression(buy_count, sell_count)
    pressure_score = _score_pressure(buy_vol, sell_vol)
    evidence_score = _clamp(
        round((delta_score + aggression_score + pressure_score) / 3.0, 4), -10.0, 10.0
    )
    conf = _confidence(delta_score, aggression_score, pressure_score, dq_score)
    plabel = _pressure_label(pressure_score)
    elabel = _evidence_label(evidence_score)

    reason_codes = [
        "SOURCE_S12_FLOW_STATE",
        f"SYMBOL_{symbol}",
        f"DQ_{dq_level}",
        f"PRESSURE_{plabel}",
        f"EVIDENCE_{elabel}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]

    return {
        "timestamp_utc": ts,
        "block_id": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "symbol": symbol,
        "source": source,
        "input_status": "OK",
        "flow_snapshot": {
            "buy_volume": buy_vol,
            "sell_volume": sell_vol,
            "delta": delta,
            "total_volume": total_vol,
            "buy_trade_count": buy_count,
            "sell_trade_count": sell_count,
            "aggression_label": bucket.get("aggression_label", "UNKNOWN"),
        },
        "delta_evidence": {
            "delta": delta,
            "delta_score": round(delta_score, 4),
        },
        "aggression_evidence": {
            "buy_trade_count": buy_count,
            "sell_trade_count": sell_count,
            "aggression_score": round(aggression_score, 4),
        },
        "pressure_evidence": {
            "buy_volume": buy_vol,
            "sell_volume": sell_vol,
            "pressure_score": round(pressure_score, 4),
            "pressure_label": plabel,
        },
        "evidence_score": evidence_score,
        "evidence_label": elabel,
        "confidence": conf,
        "data_quality": {
            "level": dq_level,
            "score": dq_score,
        },
        "reason_codes": reason_codes,
        "feeds_next": {
            "next_blocks": ["S14_FLOW_PERSISTENCE_ENGINE"],
        },
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_flow_output(reason: str) -> dict[str, Any]:
    ts = _now_utc()
    return {
        "timestamp_utc": ts,
        "block_id": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "symbol": "UNKNOWN",
        "source": "NONE",
        "input_status": "MISSING",
        "flow_snapshot": {},
        "delta_evidence": {"delta": 0.0, "delta_score": 0.0},
        "aggression_evidence": {"buy_trade_count": 0, "sell_trade_count": 0, "aggression_score": 0.0},
        "pressure_evidence": {"buy_volume": 0.0, "sell_volume": 0.0, "pressure_score": 0.0, "pressure_label": "UNKNOWN"},
        "evidence_score": 0.0,
        "evidence_label": "NO_VALID_FLOW",
        "confidence": 0.0,
        "data_quality": {"level": "MISSING", "score": 0.0},
        "reason_codes": ["NO_VALID_FLOW", reason, "SAFE_TO_OPEN_REAL_TRADE_FALSE", "NO_PRIVATE_API"],
        "feeds_next": {"next_blocks": ["S14_FLOW_PERSISTENCE_ENGINE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_flow_evidence_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if not FLOW_STATE_PATH.exists():
        result = no_valid_flow_output("FLOW_STATE_FILE_MISSING")
    else:
        try:
            flow_state = json.loads(FLOW_STATE_PATH.read_text(encoding="utf-8"))
            result = compute_flow_evidence(flow_state)
        except Exception as e:
            result = no_valid_flow_output(f"FLOW_STATE_PARSE_ERROR")

    EVIDENCE_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s13_state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S13_FLOW_EVIDENCE_STATE",
        "last_evidence_label": result["evidence_label"],
        "last_confidence": result["confidence"],
        "last_evidence_score": result["evidence_score"],
        "runs": 1,
    }
    S13_STATE_PATH.write_text(json.dumps(s13_state, indent=2), encoding="utf-8")

    with EVIDENCE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)

    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S13 Flow Evidence Engine — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Input Status:** {r['input_status']}",
        f"**Evidence Label:** {r['evidence_label']}",
        f"**Evidence Score:** {r['evidence_score']}",
        f"**Confidence:** {r['confidence']}",
        f"**Pressure Label:** {r['pressure_evidence'].get('pressure_label', 'N/A')}",
        f"**Delta Score:** {r['delta_evidence']['delta_score']}",
        f"**Aggression Score:** {r['aggression_evidence']['aggression_score']}",
        f"**Pressure Score:** {r['pressure_evidence']['pressure_score']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
