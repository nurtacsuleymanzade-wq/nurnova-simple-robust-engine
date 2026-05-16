from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, write_json

BLOCK_ID = "REGIME_CLASSIFIER"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple/epoch_v2")
OUTPUT_PATH = STATE_DIR / "latest_regime_classifier.json"
HISTORY_PATH = DATA_DIR / "regime_classifier_history.jsonl"

MARKET_STRUCTURE_V2_PATH = STATE_DIR / "latest_market_structure_v2.json"
LIQUIDITY_STRUCTURE_PATH = STATE_DIR / "latest_liquidity_structure.json"
HYBRID_CANDLE_DNA_PATH = STATE_DIR / "latest_hybrid_candle_dna.json"
EVIDENCE_1S_PATH = STATE_DIR / "latest_1s_evidence.json"
QUALITY_WEIGHT_PATH = STATE_DIR / "latest_quality_weight.json"

FEEDS_NEXT = [
    "SETUP_CONTRACT_ENGINE",
    "TRADE_PLAN_ENGINE",
    "DECISION_GATE",
    "EDGE_MATRIX",
]

_ALLOWED_PRIMARY = {"TREND", "RANGE", "COMPRESSION", "EXPANSION", "REVERSAL", "ROTATION", "UNKNOWN"}
_ALLOWED_BIAS = {"LONG", "SHORT", "NEUTRAL"}
_ALLOWED_VOL = {"LOW", "NORMAL", "HIGH", "EXPANDING", "COMPRESSING", "UNKNOWN"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _volatility_state(evidence: dict[str, Any] | None, quality: dict[str, Any] | None) -> tuple[str, float, list[str]]:
    reasons: list[str] = []
    evidence_score = _safe_float((evidence or {}).get("volatility_score"), default=-1.0)
    quality_score = _safe_float((quality or {}).get("quality_score"), default=-1.0)
    if evidence_score < 0 and quality_score < 0:
        reasons.append("VOLATILITY_SIGNAL_MISSING")
        return "UNKNOWN", 0.0, reasons
    base = evidence_score if evidence_score >= 0 else 0.5
    if quality_score >= 0:
        base = (base + quality_score) / 2.0
    base = _clamp(base)
    if base >= 0.78:
        return "HIGH", base, reasons
    if base <= 0.22:
        return "LOW", base, reasons
    return "NORMAL", base, reasons


def _build_allowed(primary_regime: str, directional_bias: str) -> tuple[list[str], list[str], list[str]]:
    allowed: list[str] = []
    blocked: list[str] = []
    reasons: list[str] = []
    if primary_regime == "TREND" and directional_bias == "LONG":
        allowed = ["TREND_CONTINUATION_LONG", "PULLBACK_CONTINUATION_LONG"]
    elif primary_regime == "TREND" and directional_bias == "SHORT":
        allowed = ["TREND_CONTINUATION_SHORT", "PULLBACK_CONTINUATION_SHORT"]
    elif primary_regime == "RANGE":
        allowed = [
            "RANGE_ROTATION_LONG",
            "RANGE_ROTATION_SHORT",
            "LIQUIDITY_SWEEP_REVERSAL_LONG",
            "LIQUIDITY_SWEEP_REVERSAL_SHORT",
        ]
    elif primary_regime == "COMPRESSION":
        allowed = ["BREAKOUT_EXPANSION_LONG", "BREAKOUT_EXPANSION_SHORT"]
        reasons.append("COMPRESSION_BREAKOUT_CANDIDATE_ONLY_NO_ENTRY_PERMISSION")
    elif primary_regime == "EXPANSION":
        allowed = [
            "TREND_CONTINUATION_LONG",
            "TREND_CONTINUATION_SHORT",
            "PULLBACK_CONTINUATION_LONG",
            "PULLBACK_CONTINUATION_SHORT",
        ]
        reasons.append("LATE_ENTRY_RISK_EXPANSION")
    elif primary_regime == "REVERSAL":
        allowed = [
            "ABSORPTION_REVERSAL_LONG",
            "ABSORPTION_REVERSAL_SHORT",
            "SWEEP_REVERSAL_LONG",
            "SWEEP_REVERSAL_SHORT",
        ]
    elif primary_regime == "ROTATION":
        allowed = ["RANGE_ROTATION_LONG", "RANGE_ROTATION_SHORT"]
    else:
        blocked = []
    return allowed, blocked, reasons


def _infer_regime(structure: dict[str, Any], liquidity: dict[str, Any] | None, volatility_state: str) -> tuple[str, float, float, float, float, float, str, list[str]]:
    reasons: list[str] = []
    structure_status = str(structure.get("structure_status", "NOT_READY")).upper()
    bias = str(structure.get("structure_bias", "NEUTRAL")).upper()
    trend_dir = str(structure.get("trend_direction", "NEUTRAL")).upper()
    regime_hint = str(structure.get("regime_hint", "UNKNOWN")).upper()
    bos = str(structure.get("bos", "NONE")).upper()

    trend_strength = 0.0
    range_strength = 0.0
    compression_score = 0.0
    expansion_score = 0.0
    reversal_risk = 0.0
    primary_regime = "UNKNOWN"
    directional_bias = bias if bias in _ALLOWED_BIAS else "NEUTRAL"

    if structure_status != "READY":
        reasons.append("STRUCTURE_NOT_READY")
        return primary_regime, trend_strength, range_strength, compression_score, expansion_score, reversal_risk, "NEUTRAL", reasons

    conf = _clamp(_safe_float(structure.get("confidence"), default=0.0))
    trend_strength = conf if regime_hint.startswith("TREND") else conf * 0.4
    range_strength = conf if regime_hint == "RANGE" else (0.35 if directional_bias == "NEUTRAL" else 0.15)

    if volatility_state == "LOW":
        compression_score = 0.72
    elif volatility_state == "HIGH":
        expansion_score = 0.7
    elif volatility_state == "UNKNOWN":
        reasons.append("VOLATILITY_UNKNOWN")

    if "BULLISH_BOS" in bos or "BEARISH_BOS" in bos:
        expansion_score = max(expansion_score, 0.62)
    if str(structure.get("choch", "")).upper() not in ("", "NONE", "NULL"):
        reversal_risk = max(reversal_risk, 0.68)
    if str((liquidity or {}).get("liquidity_sweep_status", "")).upper() not in ("", "NONE", "NULL"):
        reversal_risk = max(reversal_risk, 0.62)

    if reversal_risk >= 0.66:
        primary_regime = "REVERSAL"
    elif compression_score >= 0.7:
        primary_regime = "COMPRESSION"
    elif expansion_score >= 0.68 and trend_strength >= 0.45:
        primary_regime = "EXPANSION"
    elif trend_strength >= 0.55 and directional_bias in ("LONG", "SHORT"):
        primary_regime = "TREND"
    elif range_strength >= 0.35 and directional_bias == "NEUTRAL":
        primary_regime = "RANGE"
    else:
        primary_regime = "UNKNOWN"

    if trend_dir in ("LONG", "SHORT") and directional_bias in ("LONG", "SHORT") and trend_dir != directional_bias:
        directional_bias = "NEUTRAL"
        reasons.append("REGIME_STRUCTURE_DIRECTION_CONFLICT")

    return primary_regime, trend_strength, range_strength, compression_score, expansion_score, reversal_risk, directional_bias, reasons


def build_regime_classifier(
    symbol: str = "BTCUSDT",
    structure_payload: dict[str, Any] | None = None,
    liquidity_payload: dict[str, Any] | None = None,
    hybrid_payload: dict[str, Any] | None = None,
    evidence_payload: dict[str, Any] | None = None,
    quality_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    structure = structure_payload if structure_payload is not None else _load_json(MARKET_STRUCTURE_V2_PATH)
    liquidity = liquidity_payload if liquidity_payload is not None else _load_json(LIQUIDITY_STRUCTURE_PATH)
    hybrid = hybrid_payload if hybrid_payload is not None else _load_json(HYBRID_CANDLE_DNA_PATH)
    evidence = evidence_payload if evidence_payload is not None else _load_json(EVIDENCE_1S_PATH)
    quality = quality_payload if quality_payload is not None else _load_json(QUALITY_WEIGHT_PATH)

    reason_codes: list[str] = []
    if structure is None:
        reason_codes.append("STRUCTURE_SOURCE_MISSING")
        return {
            "timestamp_utc": _utc_now(),
            "block_id": BLOCK_ID,
            "symbol": symbol,
            "data_quality": "INVALID",
            "regime_status": "NOT_READY",
            "primary_regime": "UNKNOWN",
            "directional_bias": "NEUTRAL",
            "volatility_state": "UNKNOWN",
            "trend_strength": 0.0,
            "range_strength": 0.0,
            "compression_score": 0.0,
            "expansion_score": 0.0,
            "reversal_risk": 0.0,
            "allowed_setup_families": [],
            "blocked_setup_families": ["ALL_SETUPS_STRUCTURE_MISSING"],
            "confidence": 0.0,
            "reason_codes": reason_codes,
            "metadata_only": True,
            "source": {"market_structure_v2": str(MARKET_STRUCTURE_V2_PATH)},
            "feeds_next": FEEDS_NEXT,
        }

    vol_state, vol_score, vol_reasons = _volatility_state(evidence, quality)
    reason_codes.extend(vol_reasons)
    primary, trend_strength, range_strength, compression_score, expansion_score, reversal_risk, bias, infer_reasons = _infer_regime(
        structure, liquidity, vol_state
    )
    reason_codes.extend(infer_reasons)

    if primary not in _ALLOWED_PRIMARY:
        primary = "UNKNOWN"
    if bias not in _ALLOWED_BIAS:
        bias = "NEUTRAL"
    if vol_state not in _ALLOWED_VOL:
        vol_state = "UNKNOWN"

    allowed, blocked, allow_reasons = _build_allowed(primary, bias)
    reason_codes.extend(allow_reasons)

    structure_status = str(structure.get("structure_status", "NOT_READY")).upper()
    if structure_status != "READY":
        regime_status = "NOT_READY"
        primary = "UNKNOWN"
        bias = "NEUTRAL"
    elif primary == "UNKNOWN":
        regime_status = "NOT_READY"
    else:
        regime_status = "READY"

    confidence = _clamp(
        trend_strength * 0.35
        + range_strength * 0.2
        + compression_score * 0.1
        + expansion_score * 0.15
        + (1.0 - reversal_risk) * 0.2
    )
    if bias == "NEUTRAL" and str(structure.get("structure_bias", "NEUTRAL")).upper() in ("LONG", "SHORT"):
        confidence = min(confidence, 0.45)
        reason_codes.append("REGIME_STRUCTURE_DIRECTION_CONFLICT")
    if primary == "UNKNOWN":
        confidence = min(confidence, 0.35)
    if vol_state == "UNKNOWN":
        confidence = min(confidence, 0.5)
    if not (hybrid and isinstance(hybrid, dict)):
        reason_codes.append("HYBRID_DNA_MISSING_OPTIONAL")

    data_quality = "OK"
    if regime_status == "NOT_READY":
        data_quality = "DEGRADED"
    if structure_status not in ("READY", "NOT_READY"):
        data_quality = "INVALID"
        regime_status = "INVALID"
        primary = "UNKNOWN"
        bias = "NEUTRAL"
        confidence = 0.0
        reason_codes.append("STRUCTURE_STATUS_INVALID")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "data_quality": data_quality,
        "regime_status": regime_status,
        "primary_regime": primary,
        "directional_bias": bias,
        "volatility_state": vol_state,
        "trend_strength": round(_clamp(trend_strength), 3),
        "range_strength": round(_clamp(range_strength), 3),
        "compression_score": round(_clamp(compression_score), 3),
        "expansion_score": round(_clamp(expansion_score), 3),
        "reversal_risk": round(_clamp(reversal_risk), 3),
        "allowed_setup_families": allowed,
        "blocked_setup_families": blocked,
        "confidence": round(_clamp(confidence), 3),
        "reason_codes": sorted(set(reason_codes)),
        "metadata_only": True,
        "source": {"market_structure_v2": str(MARKET_STRUCTURE_V2_PATH)},
        "feeds_next": FEEDS_NEXT,
        "volatility_score": round(_clamp(vol_score), 3),
    }


def _fake_trend_up_structure(symbol: str) -> dict[str, Any]:
    return {
        "timestamp_utc": _utc_now(),
        "block_id": "MARKET_STRUCTURE_V2",
        "symbol": symbol,
        "data_quality": "OK",
        "structure_status": "READY",
        "regime_hint": "TREND_UP",
        "trend_direction": "LONG",
        "structure_bias": "LONG",
        "confidence": 0.81,
        "bos": "BULLISH_BOS",
        "choch": None,
    }


def run_regime_classifier_engine(symbol: str = "BTCUSDT", fake_sample: bool = False) -> dict[str, Any]:
    context = current_runtime_context(symbol)
    payload = build_regime_classifier(
        symbol=symbol,
        structure_payload=_fake_trend_up_structure(symbol) if fake_sample else None,
    )
    payload["context_id"] = context.get("context_id")
    payload["loop_id"] = context.get("loop_id")
    write_json(OUTPUT_PATH, payload)
    _append_jsonl(HISTORY_PATH, payload)
    return payload
