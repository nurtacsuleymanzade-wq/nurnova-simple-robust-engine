from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

FLOW_PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
FCR_PATH = STATE_DIR / "latest_fcr.json"
FCR_LOG_PATH = DATA_DIR / "fcr_history.jsonl"


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


def compute_failed_continuation_reversal(persistence: dict[str, Any]) -> dict[str, Any]:
    persistence_label = persistence.get("persistence_label", "NO_VALID_FLOW")
    continuation_quality = persistence.get("continuation_quality", "NONE")
    decay_risk = bool(persistence.get("decay_risk", False))
    flip_risk = bool(persistence.get("flip_risk", False))
    windows = persistence.get("windows", {})
    last_30s = windows.get("last_30s", {})
    last_5m = windows.get("last_5m", {})

    had_momentum = persistence_label in (
        "BUILDING_LONG_MOMENTUM",
        "BUILDING_SHORT_MOMENTUM",
        "SUSTAINED_LONG_PRESSURE",
        "SUSTAINED_SHORT_PRESSURE",
    )
    momentum_direction = "LONG" if "LONG" in persistence_label else "SHORT"
    last_30s_direction = last_30s.get("dominant_label", "NEUTRAL")
    continuation_failed = (
        had_momentum
        and last_30s_direction != momentum_direction
        and last_30s_direction != "NEUTRAL"
    )
    continuation_failed = continuation_failed or (had_momentum and (decay_risk or flip_risk))

    trapped_side = "NONE"
    reversal_ready = False
    if continuation_failed:
        trapped_side = "BUYERS" if momentum_direction == "LONG" else "SELLERS"
        avg_30s = float(last_30s.get("avg_evidence_score", 0.0))
        reversal_ready = (
            (momentum_direction == "LONG" and avg_30s < -1.0)
            or (momentum_direction == "SHORT" and avg_30s > 1.0)
        )

    quality_weight = {
        "BUILDING": 18.0,
        "SUSTAINED": 24.0,
        "MODERATE": 15.0,
        "WEAK": 10.0,
        "NONE": 5.0,
    }.get(continuation_quality, 5.0)
    trap_strength = round(
        _clamp(
            (
                quality_weight
                + abs(float(last_5m.get("avg_evidence_score", 0.0))) * 6.0
                + abs(float(last_30s.get("avg_evidence_score", 0.0))) * 8.0
                + (18.0 if decay_risk else 0.0)
                + (22.0 if flip_risk else 0.0)
            )
            if continuation_failed
            else 0.0,
            0.0,
            100.0,
        ),
        2,
    )

    symbol = persistence.get("symbol", "UNKNOWN")
    dq = persistence.get("data_quality", {"level": "OK", "score": 1.0})

    reason_codes = [f"SYMBOL_{symbol}"]
    if had_momentum:
        reason_codes.append("MOMENTUM_DETECTED")
    else:
        reason_codes.append("NO_MOMENTUM_CONTEXT")
    if continuation_failed:
        reason_codes.append("CONTINUATION_FAILED")
        reason_codes.append(f"{trapped_side}_TRAPPED")
    if reversal_ready:
        reason_codes.append("REVERSAL_READY")
    reason_codes += [
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
    ]

    return {
        "timestamp_utc": _now_utc(),
        "block_id": "FCR_FAILED_CONTINUATION",
        "symbol": symbol,
        "source": "S14_FLOW_PERSISTENCE_ENGINE",
        "input_status": persistence.get("input_status", "OK"),
        "had_momentum": had_momentum,
        "continuation_failed": continuation_failed,
        "trapped_side": trapped_side,
        "reversal_ready": reversal_ready,
        "trap_strength": trap_strength,
        "timeframe": "1m",
        "candle_close_time": persistence.get("timestamp_utc", "UNKNOWN"),
        "reason_codes": reason_codes,
        "data_quality": dq,
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
        "block_id": "FCR_FAILED_CONTINUATION",
        "symbol": "UNKNOWN",
        "source": "S14_FLOW_PERSISTENCE_ENGINE",
        "input_status": "MISSING",
        "had_momentum": False,
        "continuation_failed": False,
        "trapped_side": "NONE",
        "reversal_ready": False,
        "trap_strength": 0.0,
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


def run_failed_continuation_reversal_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    persistence = _load_json(FLOW_PERSISTENCE_PATH)
    if persistence is None:
        result = no_valid_output("FLOW_PERSISTENCE_MISSING")
    else:
        try:
            result = compute_failed_continuation_reversal(persistence)
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    FCR_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with FCR_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result) + "\n")
    return result
