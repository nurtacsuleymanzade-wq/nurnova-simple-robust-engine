from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

FLOW_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
FLOW_PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
DAF_PATH = STATE_DIR / "latest_daf.json"
DAF_LOG_PATH = DATA_DIR / "daf_history.jsonl"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def compute_delta_absorption_failure(
    evidence: dict[str, Any],
    persistence: dict[str, Any],
) -> dict[str, Any]:
    delta_evidence = evidence.get("delta_evidence", {})
    pressure = evidence.get("pressure_evidence", {})
    windows = persistence.get("windows", {})
    last_30s = windows.get("last_30s", {})
    last_5m = windows.get("last_5m", {})

    symbol = evidence.get("symbol") or persistence.get("symbol") or "UNKNOWN"
    delta_score_signed = float(delta_evidence.get("delta_score", 0.0))
    delta_score = abs(delta_score_signed)
    evidence_score = float(evidence.get("evidence_score", 0.0))
    evidence_normalized = abs(evidence_score)
    divergence = round(delta_score - evidence_normalized, 4)
    delta_divergence = divergence > 2.0

    aggressive_side_failed = "NONE"
    reversal_bias = "NEUTRAL"
    if delta_score_signed > 2.0 and evidence_score < 0.5:
        aggressive_side_failed = "BUYERS"
        reversal_bias = "SHORT"
    elif delta_score_signed < -2.0 and evidence_score > -0.5:
        aggressive_side_failed = "SELLERS"
        reversal_bias = "LONG"

    avg_30s = float(last_30s.get("avg_evidence_score", 0.0))
    avg_5m = float(last_5m.get("avg_evidence_score", 0.0))
    consistency = float(last_5m.get("direction_consistency", 0.0))
    context_bonus = 0.0
    if abs(avg_30s) < 1.0:
        context_bonus += 15.0
    if abs(avg_5m) < 1.5:
        context_bonus += 10.0
    if consistency < 0.55:
        context_bonus += 10.0
    if avg_30s != 0 and delta_score_signed != 0 and (avg_30s > 0) != (delta_score_signed > 0):
        context_bonus += 20.0

    failure_strength = round(
        _clamp((divergence * 20.0) + context_bonus if delta_divergence else 0.0, 0.0, 100.0),
        2,
    )

    evidence_dq = float((evidence.get("data_quality") or {}).get("score", 0.0))
    persistence_dq = float((persistence.get("data_quality") or {}).get("score", 0.0))
    dq_score = round((evidence_dq + persistence_dq) / 2.0, 4)
    dq_level = (
        "OK" if dq_score >= 0.85
        else "REDUCED" if dq_score >= 0.6
        else "LOW" if dq_score > 0.0
        else "MISSING"
    )

    reason_codes = [f"SYMBOL_{symbol}"]
    if delta_divergence:
        reason_codes.append("DELTA_DIVERGENCE_DETECTED")
    else:
        reason_codes.append("NO_DELTA_DIVERGENCE")
    if aggressive_side_failed != "NONE":
        reason_codes.append(f"{aggressive_side_failed}_FAILED")
        reason_codes.append(f"REVERSAL_BIAS_{reversal_bias}")
    reason_codes += [
        f"DQ_{dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
    ]

    return {
        "timestamp_utc": _now_utc(),
        "block_id": "DAF_DELTA_ABSORPTION_FAILURE",
        "symbol": symbol,
        "source": "S13_S14_FLOW_ENGINES",
        "input_status": "OK",
        "delta_divergence": delta_divergence,
        "divergence_score": divergence,
        "aggressive_side_failed": aggressive_side_failed,
        "reversal_bias": reversal_bias,
        "failure_strength": failure_strength,
        "timeframe": "1m",
        "candle_close_time": evidence.get("timestamp_utc", "UNKNOWN"),
        "reason_codes": reason_codes,
        "data_quality": {"level": dq_level, "score": dq_score},
        "feeds_next": {"next_blocks": ["S15_FLOW_TO_SETUP_CONTEXT", "S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_output(reason: str) -> dict[str, Any]:
    return {
        "timestamp_utc": _now_utc(),
        "block_id": "DAF_DELTA_ABSORPTION_FAILURE",
        "symbol": "UNKNOWN",
        "source": "S13_S14_FLOW_ENGINES",
        "input_status": "MISSING",
        "delta_divergence": False,
        "divergence_score": 0.0,
        "aggressive_side_failed": "NONE",
        "reversal_bias": "NEUTRAL",
        "failure_strength": 0.0,
        "timeframe": "1m",
        "candle_close_time": "UNKNOWN",
        "reason_codes": [
            "INPUT_MISSING",
            reason,
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
        ],
        "data_quality": {"level": "MISSING", "score": 0.0},
        "feeds_next": {"next_blocks": ["S15_FLOW_TO_SETUP_CONTEXT", "S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_delta_absorption_failure_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    evidence = _load_json(FLOW_EVIDENCE_PATH)
    persistence = _load_json(FLOW_PERSISTENCE_PATH)
    if evidence is None or persistence is None:
        result = no_valid_output("REQUIRED_INPUT_MISSING")
    else:
        try:
            result = compute_delta_absorption_failure(evidence, persistence)
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    DAF_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with DAF_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result) + "\n")
    return result
