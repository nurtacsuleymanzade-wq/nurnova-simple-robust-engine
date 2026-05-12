"""S15 — Flow-to-Setup Context Engine. Combines S13 evidence + S14 persistence into a tradeable context label."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"
EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"
S15_STATE_PATH = STATE_DIR / "s15_setup_context_state.json"
SETUP_CONTEXT_LOG_PATH = DATA_DIR / "setup_context_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s15_setup_context_latest_report.md"

_CONT_WEIGHTS = {"STRONG": 1.0, "MODERATE": 0.75, "WEAK": 0.50, "NONE": 0.25}


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


def _compute_context_score(evidence_score: float, persistence_score: float) -> float:
    raw = 0.6 * evidence_score + 0.4 * persistence_score
    return _clamp(round(raw, 4), -10.0, 10.0)


def _direction_bias(score: float) -> str:
    if score > 1.5:
        return "LONG"
    if score < -1.5:
        return "SHORT"
    return "NEUTRAL"


def _probabilities(score: float) -> tuple[float, float]:
    long_p = _clamp(round((score + 10.0) / 20.0, 4), 0.0, 1.0)
    short_p = round(1.0 - long_p, 4)
    return long_p, short_p


def _context_confidence(
    evidence_confidence: float,
    continuation_quality: str,
    dq_score: float,
) -> float:
    cont_w = _CONT_WEIGHTS.get(continuation_quality, 0.25)
    raw = evidence_confidence * cont_w * dq_score
    return _clamp(round(raw, 4), 0.0, 1.0)


def _setup_context_label(
    evidence_label: str,
    persistence_label: str,
    direction_bias: str,
    score: float,
    confidence: float,
    decay_risk: bool,
    flip_risk: bool,
    input_status: str,
) -> str:
    if input_status in ("MISSING", "INSUFFICIENT"):
        return "INSUFFICIENT_CONTEXT"

    if persistence_label in ("NO_VALID_FLOW", "INSUFFICIENT_HISTORY") and evidence_label in (
        "NO_VALID_FLOW",
        "NEUTRAL_FLOW",
    ):
        return "INSUFFICIENT_CONTEXT"

    if persistence_label == "NO_VALID_FLOW":
        return "NO_TRADE_CONTEXT"

    if persistence_label == "CHOPPY_FLOW":
        return "CHOPPY_CONTEXT"

    if decay_risk or flip_risk:
        return "NO_TRADE_CONTEXT"

    if confidence < 0.30:
        return "NO_TRADE_CONTEXT"

    if (
        evidence_label == "STRONG_LONG_PRESSURE"
        and persistence_label == "SUSTAINED_LONG_PRESSURE"
        and score >= 5.0
        and confidence >= 0.60
    ):
        return "STRONG_LONG_CONTEXT"

    if (
        evidence_label == "STRONG_SHORT_PRESSURE"
        and persistence_label == "SUSTAINED_SHORT_PRESSURE"
        and score <= -5.0
        and confidence >= 0.60
    ):
        return "STRONG_SHORT_CONTEXT"

    if direction_bias == "LONG":
        return "WEAK_LONG_CONTEXT"

    if direction_bias == "SHORT":
        return "WEAK_SHORT_CONTEXT"

    if persistence_label == "INSUFFICIENT_HISTORY":
        return "INSUFFICIENT_CONTEXT"

    return "NEUTRAL_CONTEXT"


def _tradeable(
    label: str,
    direction_bias: str,
    confidence: float,
    persistence_label: str,
    dq_level: str,
) -> bool:
    quality_ok = dq_level in ("OK", "HIGH")
    return (
        quality_ok
        and confidence >= 0.60
        and persistence_label not in ("CHOPPY_FLOW",)
        and direction_bias in ("LONG", "SHORT")
        and label in ("STRONG_LONG_CONTEXT", "STRONG_SHORT_CONTEXT")
    )


def compute_setup_context(
    flow_state: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    persistence: dict[str, Any] | None,
) -> dict[str, Any]:
    ts = _now_utc()

    symbol = "UNKNOWN"
    input_status = "OK"
    reason_codes: list[str] = []

    if evidence is None and persistence is None:
        input_status = "MISSING"
        reason_codes.append("EVIDENCE_MISSING")
        reason_codes.append("PERSISTENCE_MISSING")
    elif evidence is None:
        input_status = "MISSING"
        reason_codes.append("EVIDENCE_MISSING")
    elif persistence is None:
        input_status = "MISSING"
        reason_codes.append("PERSISTENCE_MISSING")

    evidence = evidence or {}
    persistence = persistence or {}

    symbol = evidence.get("symbol") or persistence.get("symbol") or "UNKNOWN"
    source = evidence.get("block_id") or "S13_S14_COMBINED"

    evidence_score = float(evidence.get("evidence_score", 0.0))
    evidence_label = evidence.get("evidence_label", "NEUTRAL_FLOW")
    evidence_confidence = float(evidence.get("confidence", 0.0))
    evidence_dq = evidence.get("data_quality", {})
    evidence_dq_score = float(evidence_dq.get("score", 0.0))
    evidence_dq_level = evidence_dq.get("level", "MISSING")
    pressure_label = evidence.get("pressure_evidence", {}).get("pressure_label", "UNKNOWN")

    persistence_score = float(persistence.get("persistence_score", 0.0))
    persistence_label = persistence.get("persistence_label", "NO_VALID_FLOW")
    continuation_quality = persistence.get("continuation_quality", "NONE")
    decay_risk = bool(persistence.get("decay_risk", False))
    flip_risk = bool(persistence.get("flip_risk", False))
    persistence_dq = persistence.get("data_quality", {})
    persistence_dq_score = float(persistence_dq.get("score", 0.0))
    persistence_dq_level = persistence_dq.get("level", "MISSING")

    combined_dq_score = round((evidence_dq_score + persistence_dq_score) / 2.0, 4) if input_status == "OK" else 0.0
    combined_dq_level = (
        "OK" if combined_dq_score >= 0.85
        else "REDUCED" if combined_dq_score >= 0.6
        else "LOW" if combined_dq_score >= 0.3
        else "MISSING"
    )

    score = _compute_context_score(evidence_score, persistence_score)
    direction = "UNKNOWN" if input_status == "MISSING" else _direction_bias(score)
    long_prob, short_prob = _probabilities(score)
    confidence = _context_confidence(evidence_confidence, continuation_quality, combined_dq_score)

    label = _setup_context_label(
        evidence_label,
        persistence_label,
        direction,
        score,
        confidence,
        decay_risk,
        flip_risk,
        input_status,
    )

    tradeable = _tradeable(label, direction, confidence, persistence_label, combined_dq_level)

    context_reason = _context_reason(label, evidence_label, persistence_label, decay_risk, flip_risk, confidence)

    reason_codes += [
        f"SYMBOL_{symbol}",
        f"EVIDENCE_{evidence_label}",
        f"PERSISTENCE_{persistence_label}",
        f"LABEL_{label}",
        f"DIRECTION_{direction}",
        f"CONTINUATION_{continuation_quality}",
        f"DQ_{combined_dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]
    if decay_risk:
        reason_codes.append("DECAY_RISK_DETECTED")
    if flip_risk:
        reason_codes.append("FLIP_RISK_DETECTED")
    if not tradeable:
        reason_codes.append("NOT_TRADEABLE")

    prob_summary = _confidence_to_probability(confidence, direction, continuation_quality)

    return {
        "timestamp_utc": ts,
        "block_id": "S15_FLOW_TO_SETUP_CONTEXT",
        "symbol": symbol,
        "source": source,
        "input_status": input_status,
        "setup_context_label": label,
        "setup_context_score": score,
        "direction_bias": direction,
        "long_probability": long_prob,
        "short_probability": short_prob,
        "confidence": confidence,
        "probability_summary": prob_summary,
        "tradeable": tradeable,
        "context_reason": context_reason,
        "data_quality": {"level": combined_dq_level, "score": combined_dq_score},
        "reason_codes": reason_codes,
        "feeds_next": {
            "next_blocks": ["S16_SCENARIO_ENTRY_TRIGGER"],
        },
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def _confidence_to_probability(confidence: float, direction: str, continuation_quality: str = "NONE") -> dict[str, Any]:
    base_prob = 50.0 + (max(0.0, min(1.0, confidence)) * 45.0)

    quality_adj = {
        "SUSTAINED": +5.0,
        "BUILDING":  +2.0,
        "MODERATE":  +1.0,
        "WEAK":       0.0,
        "NONE":       0.0,
        "FADING":    -5.0,
    }.get(continuation_quality, 0.0)

    base_prob = max(50.0, min(95.0, base_prob + quality_adj))

    if direction == "LONG":
        long_prob  = round(base_prob, 1)
        short_prob = round(100.0 - base_prob, 1)
    elif direction == "SHORT":
        short_prob = round(base_prob, 1)
        long_prob  = round(100.0 - base_prob, 1)
    else:
        long_prob  = 50.0
        short_prob = 50.0

    if base_prob >= 85:
        signal_class = "A_PLUS"
    elif base_prob >= 75:
        signal_class = "A"
    elif base_prob >= 65:
        signal_class = "B"
    elif base_prob >= 60:
        signal_class = "C"
    else:
        signal_class = "NO_SIGNAL"

    return {
        "long_probability_pct": long_prob,
        "short_probability_pct": short_prob,
        "signal_class": signal_class,
        "signal_eligible": base_prob >= 60.0,
        "confidence_raw": round(confidence, 4),
        "base_probability": round(base_prob, 1),
    }


def _context_reason(
    label: str,
    evidence_label: str,
    persistence_label: str,
    decay_risk: bool,
    flip_risk: bool,
    confidence: float,
) -> str:
    if label == "STRONG_LONG_CONTEXT":
        return "Strong evidence and sustained long persistence with sufficient confidence."
    if label == "STRONG_SHORT_CONTEXT":
        return "Strong evidence and sustained short persistence with sufficient confidence."
    if label == "WEAK_LONG_CONTEXT":
        return f"Long bias detected but not fully sustained: evidence={evidence_label}, persistence={persistence_label}."
    if label == "WEAK_SHORT_CONTEXT":
        return f"Short bias detected but not fully sustained: evidence={evidence_label}, persistence={persistence_label}."
    if label == "CHOPPY_CONTEXT":
        return "Flow persistence is choppy — no reliable directional bias."
    if label == "NO_TRADE_CONTEXT":
        parts = []
        if decay_risk:
            parts.append("decay_risk")
        if flip_risk:
            parts.append("flip_risk")
        if confidence < 0.30:
            parts.append(f"low_confidence={confidence}")
        if persistence_label == "NO_VALID_FLOW":
            parts.append("no_valid_flow")
        return "No trade context: " + (", ".join(parts) if parts else persistence_label)
    if label == "INSUFFICIENT_CONTEXT":
        return "Insufficient input data to determine context."
    return "Neutral flow — no directional edge detected."


def no_valid_context_output(reason: str) -> dict[str, Any]:
    ts = _now_utc()
    return {
        "timestamp_utc": ts,
        "block_id": "S15_FLOW_TO_SETUP_CONTEXT",
        "symbol": "UNKNOWN",
        "source": "NONE",
        "input_status": "MISSING",
        "setup_context_label": "INSUFFICIENT_CONTEXT",
        "setup_context_score": 0.0,
        "direction_bias": "UNKNOWN",
        "long_probability": 0.5,
        "short_probability": 0.5,
        "confidence": 0.0,
        "tradeable": False,
        "context_reason": "Input files missing — cannot determine context.",
        "data_quality": {"level": "MISSING", "score": 0.0},
        "reason_codes": [
            "INSUFFICIENT_CONTEXT",
            reason,
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": {"next_blocks": ["S16_SCENARIO_ENTRY_TRIGGER"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_flow_to_setup_context_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    flow_state = _load_json(FLOW_STATE_PATH)
    evidence = _load_json(EVIDENCE_PATH)
    persistence = _load_json(PERSISTENCE_PATH)

    if evidence is None and persistence is None:
        result = no_valid_context_output("EVIDENCE_AND_PERSISTENCE_MISSING")
    else:
        try:
            result = compute_setup_context(flow_state, evidence, persistence)
        except Exception:
            result = no_valid_context_output("COMPUTE_ERROR")

    SETUP_CONTEXT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s15_state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S15_SETUP_CONTEXT_STATE",
        "last_setup_context_label": result["setup_context_label"],
        "last_direction_bias": result["direction_bias"],
        "last_setup_context_score": result["setup_context_score"],
        "last_confidence": result["confidence"],
        "last_tradeable": result["tradeable"],
        "runs": 1,
    }
    S15_STATE_PATH.write_text(json.dumps(s15_state, indent=2), encoding="utf-8")

    with SETUP_CONTEXT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)

    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S15 Flow-to-Setup Context Engine — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Input Status:** {r['input_status']}",
        f"**Setup Context Label:** {r['setup_context_label']}",
        f"**Setup Context Score:** {r['setup_context_score']}",
        f"**Direction Bias:** {r['direction_bias']}",
        f"**Long Probability:** {r['long_probability']}",
        f"**Short Probability:** {r['short_probability']}",
        f"**Confidence:** {r['confidence']}",
        f"**Tradeable:** {r['tradeable']}",
        f"**Context Reason:** {r['context_reason']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
