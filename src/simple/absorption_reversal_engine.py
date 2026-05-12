from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

FLOW_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
AR01_PATH = STATE_DIR / "latest_ar01.json"
AR01_LOG_PATH = DATA_DIR / "ar01_history.jsonl"


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


def compute_absorption_reversal(evidence: dict[str, Any]) -> dict[str, Any]:
    pressure = evidence.get("pressure_evidence", {})
    aggression = evidence.get("aggression_evidence", {})
    delta_evidence = evidence.get("delta_evidence", {})

    symbol = evidence.get("symbol", "UNKNOWN")
    pressure_score = float(pressure.get("pressure_score", 0.0))
    aggression_score = float(aggression.get("aggression_score", 0.0))
    delta_score = float(delta_evidence.get("delta_score", 0.0))
    evidence_score = float(evidence.get("evidence_score", 0.0))

    if pressure_score > 2.0:
        aggressor_side = "BUYERS"
    elif pressure_score < -2.0:
        aggressor_side = "SELLERS"
    else:
        aggressor_side = "NEUTRAL"

    absorption_detected = False
    absorbed_side = "NONE"
    reversal_bias = "NEUTRAL"
    if aggressor_side == "BUYERS" and evidence_score < 1.0:
        absorption_detected = True
        absorbed_side = "SELLERS"
        reversal_bias = "SHORT"
    elif aggressor_side == "SELLERS" and evidence_score > -1.0:
        absorption_detected = True
        absorbed_side = "BUYERS"
        reversal_bias = "LONG"

    trap_probability = round(_clamp(abs(pressure_score) * 10.0, 0.0, 100.0), 2)
    reversal_probability = round(trap_probability * 0.85 if absorption_detected else 0.0, 2)

    mismatch = 0.0
    if aggressor_side == "BUYERS":
        mismatch = max(0.0, 1.0 - evidence_score)
    elif aggressor_side == "SELLERS":
        mismatch = max(0.0, evidence_score + 1.0)
    absorption_strength = round(
        _clamp(
            (abs(pressure_score) * 8.0)
            + (abs(aggression_score) * 3.0)
            + (abs(delta_score) * 3.0)
            + (mismatch * 12.0 if absorption_detected else 0.0),
            0.0,
            100.0,
        ),
        2,
    )

    reason_codes = [f"SYMBOL_{symbol}"]
    if absorption_detected:
        reason_codes.append("ABSORPTION_DETECTED")
        reason_codes.append(f"AGGRESSOR_{aggressor_side}")
        reason_codes.append(f"REVERSAL_BIAS_{reversal_bias}")
    else:
        reason_codes.append("NO_ABSORPTION_SIGNAL")
    if trap_probability >= 70.0:
        reason_codes.append("TRAP_RISK_HIGH")
    elif trap_probability >= 40.0:
        reason_codes.append("TRAP_RISK_MEDIUM")
    else:
        reason_codes.append("TRAP_RISK_LOW")
    reason_codes += [
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
    ]

    return {
        "timestamp_utc": _now_utc(),
        "block_id": "AR01_ABSORPTION_REVERSAL",
        "symbol": symbol,
        "source": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "input_status": evidence.get("input_status", "OK"),
        "absorption_detected": absorption_detected,
        "aggressor_side": aggressor_side,
        "absorbed_side": absorbed_side,
        "trap_probability": trap_probability,
        "reversal_probability": reversal_probability,
        "absorption_strength": absorption_strength,
        "reversal_bias": reversal_bias,
        "reason_codes": reason_codes,
        "data_quality": evidence.get("data_quality", {"level": "OK", "score": 1.0}),
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
        "block_id": "AR01_ABSORPTION_REVERSAL",
        "symbol": "UNKNOWN",
        "source": "S13_1S_FLOW_EVIDENCE_ENGINE",
        "input_status": "MISSING",
        "absorption_detected": False,
        "aggressor_side": "NEUTRAL",
        "absorbed_side": "NONE",
        "trap_probability": 0.0,
        "reversal_probability": 0.0,
        "absorption_strength": 0.0,
        "reversal_bias": "NEUTRAL",
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


def run_absorption_reversal_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    evidence = _load_json(FLOW_EVIDENCE_PATH)
    if evidence is None:
        result = no_valid_output("FLOW_EVIDENCE_MISSING")
    else:
        try:
            result = compute_absorption_reversal(evidence)
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    AR01_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with AR01_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result) + "\n")
    return result
