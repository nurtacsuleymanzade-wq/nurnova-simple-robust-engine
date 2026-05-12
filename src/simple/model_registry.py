from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

AR01_PATH = STATE_DIR / "latest_ar01.json"
DAF_PATH = STATE_DIR / "latest_daf.json"
FCR_PATH = STATE_DIR / "latest_fcr.json"
CQE_PATH = STATE_DIR / "latest_cqe.json"
MODEL_REGISTRY_PATH = STATE_DIR / "latest_model_registry.json"
MODEL_REGISTRY_LOG_PATH = DATA_DIR / "model_registry_history.jsonl"


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


def compute_model_registry(
    ar01: dict[str, Any] | None,
    daf: dict[str, Any] | None,
    fcr: dict[str, Any] | None,
    cqe: dict[str, Any] | None,
) -> dict[str, Any]:
    active_signals: list[dict[str, Any]] = []

    if ar01 and ar01.get("absorption_detected") and ar01.get("reversal_bias") in ("LONG", "SHORT"):
        active_signals.append({
            "model": "AR01",
            "bias": ar01["reversal_bias"],
            "strength": float(ar01.get("reversal_probability", 0.0)),
        })
    if daf and daf.get("delta_divergence") and daf.get("reversal_bias") in ("LONG", "SHORT"):
        active_signals.append({
            "model": "DAF",
            "bias": daf["reversal_bias"],
            "strength": float(daf.get("failure_strength", 0.0)),
        })
    if fcr and fcr.get("continuation_failed"):
        trapped_side = fcr.get("trapped_side")
        bias = "LONG" if trapped_side == "SELLERS" else ("SHORT" if trapped_side == "BUYERS" else "NEUTRAL")
        if bias in ("LONG", "SHORT"):
            active_signals.append({
                "model": "FCR",
                "bias": bias,
                "strength": float(fcr.get("trap_strength", 0.0)),
            })

    long_strength = sum(s["strength"] for s in active_signals if s["bias"] == "LONG")
    short_strength = sum(s["strength"] for s in active_signals if s["bias"] == "SHORT")
    total = long_strength + short_strength

    if total > 0:
        long_pct = round(_clamp(long_strength / total * 100.0, 0.0, 100.0), 1)
        short_pct = round(_clamp(short_strength / total * 100.0, 0.0, 100.0), 1)
    else:
        long_pct = 50.0
        short_pct = 50.0

    consensus = "LONG" if long_pct > 55.0 else ("SHORT" if short_pct > 55.0 else "NEUTRAL")
    available_count = sum(1 for item in (ar01, daf, fcr, cqe) if item is not None)
    dq_score = round(available_count / 4.0, 4)
    dq_level = (
        "OK" if available_count == 4
        else "REDUCED" if available_count >= 2
        else "LOW" if available_count == 1
        else "MISSING"
    )
    input_status = "OK" if available_count == 4 else ("PARTIAL" if available_count > 0 else "MISSING")
    symbol = (
        (cqe or {}).get("symbol")
        or (ar01 or {}).get("symbol")
        or (daf or {}).get("symbol")
        or (fcr or {}).get("symbol")
        or "UNKNOWN"
    )
    candle_quality = cqe.get("candle_quality", "UNKNOWN") if cqe else "UNKNOWN"

    reason_codes = [
        f"ACTIVE_MODELS_{len(active_signals)}",
        f"CONSENSUS_{consensus}",
        f"CANDLE_{candle_quality}",
        f"DQ_{dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_ORDER_EXECUTION",
    ]
    reason_codes += [f"ACTIVE_{signal['model']}_{signal['bias']}" for signal in active_signals]

    return {
        "timestamp_utc": _now_utc(),
        "block_id": "MODEL_REGISTRY",
        "symbol": symbol,
        "source": "PHASE1_MODEL_LAYER",
        "input_status": input_status,
        "active_model_count": len(active_signals),
        "active_signals": active_signals,
        "candle_quality": candle_quality,
        "consensus_direction": consensus,
        "long_probability_pct": long_pct,
        "short_probability_pct": short_pct,
        "reason_codes": reason_codes,
        "data_quality": {"level": dq_level, "score": dq_score},
        "feeds_next": {"next_blocks": ["S16_SCENARIO_ENTRY_TRIGGER", "S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_output(reason: str) -> dict[str, Any]:
    return {
        "timestamp_utc": _now_utc(),
        "block_id": "MODEL_REGISTRY",
        "symbol": "UNKNOWN",
        "source": "PHASE1_MODEL_LAYER",
        "input_status": "MISSING",
        "active_model_count": 0,
        "active_signals": [],
        "candle_quality": "UNKNOWN",
        "consensus_direction": "NEUTRAL",
        "long_probability_pct": 50.0,
        "short_probability_pct": 50.0,
        "reason_codes": [
            "INPUT_MISSING",
            reason,
            "ACTIVE_MODELS_0",
            "CONSENSUS_NEUTRAL",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_ORDER_EXECUTION",
        ],
        "data_quality": {"level": "MISSING", "score": 0.0},
        "feeds_next": {"next_blocks": ["S16_SCENARIO_ENTRY_TRIGGER", "S18_DECISION_GATE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_model_registry() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ar01 = _load_json(AR01_PATH)
    daf = _load_json(DAF_PATH)
    fcr = _load_json(FCR_PATH)
    cqe = _load_json(CQE_PATH)

    if ar01 is None and daf is None and fcr is None and cqe is None:
        result = no_valid_output("ALL_MODEL_INPUTS_MISSING")
    else:
        try:
            result = compute_model_registry(ar01, daf, fcr, cqe)
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    MODEL_REGISTRY_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with MODEL_REGISTRY_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result) + "\n")
    return result
