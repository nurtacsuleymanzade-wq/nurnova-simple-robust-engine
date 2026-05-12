"""S3 Hybrid Candle DNA Engine — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S3_HYBRID_CANDLE_DNA"
FEEDS_NEXT = {"next_blocks": ["S4_QUALITY_WEIGHT_ENGINE"]}

_FAKE_CANDLE: dict[str, Any] = {
    "open": 104700.0,
    "high": 105500.0,
    "low": 104200.0,
    "close": 105000.0,
    "volume": 12.543,
}

_FAKE_EVIDENCE: dict[str, Any] = {
    "evidence_label": "LONG_PRESSURE",
    "evidence_score": 6.2105,
    "evidence_strength": "MODERATE",
    "micro_winner": "LONG",
    "delta_ratio": 0.621053,
    "confidence_adjusted": True,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_shape(candle: dict[str, Any]) -> dict[str, Any]:
    o = float(candle["open"])
    h = float(candle["high"])
    l = float(candle["low"])
    c = float(candle["close"])

    range_size = round(h - l, 8)

    if range_size == 0.0:
        return {
            "candle_direction": "DOJI",
            "body_size": 0.0,
            "upper_wick_size": 0.0,
            "lower_wick_size": 0.0,
            "range_size": 0.0,
            "body_pct": 0.0,
            "upper_wick_pct": 0.0,
            "lower_wick_pct": 0.0,
            "shape_label": "DOJI",
            "dna_open": o,
            "dna_high": h,
            "dna_low": l,
            "dna_close": c,
            "body_ratio": 0.0,
            "wick_upper_ratio": 0.0,
            "wick_lower_ratio": 0.0,
            "candle_type": "DOJI",
        }

    body_size = round(abs(c - o), 8)
    upper_wick = round(h - max(o, c), 8)
    lower_wick = round(min(o, c) - l, 8)

    body_ratio = round(body_size / range_size, 6)
    wick_upper_ratio = round(upper_wick / range_size, 6)
    wick_lower_ratio = round(1.0 - body_ratio - wick_upper_ratio, 6)

    body_pct = round(body_ratio * 100.0, 2)
    upper_wick_pct = round(wick_upper_ratio * 100.0, 2)
    lower_wick_pct = round(wick_lower_ratio * 100.0, 2)

    if c > o:
        direction = "BULLISH"
    elif c < o:
        direction = "BEARISH"
    else:
        direction = "DOJI"

    if body_pct < 5.0:
        shape_label = "DOJI"
    elif body_pct >= 60.0:
        shape_label = f"{direction}_MARUBOZU"
    elif lower_wick_pct > 2 * upper_wick_pct and body_pct < 40.0:
        shape_label = f"{direction}_HAMMER"
    elif upper_wick_pct > 2 * lower_wick_pct and body_pct < 40.0:
        shape_label = f"{direction}_SHOOTING_STAR"
    else:
        shape_label = f"{direction}_SPINNING_TOP"

    return {
        "candle_direction": direction,
        "body_size": body_size,
        "upper_wick_size": upper_wick,
        "lower_wick_size": lower_wick,
        "range_size": range_size,
        "body_pct": body_pct,
        "upper_wick_pct": upper_wick_pct,
        "lower_wick_pct": lower_wick_pct,
        "shape_label": shape_label,
        "dna_open": o,
        "dna_high": h,
        "dna_low": l,
        "dna_close": c,
        "body_ratio": body_ratio,
        "wick_upper_ratio": wick_upper_ratio,
        "wick_lower_ratio": wick_lower_ratio,
        "candle_type": shape_label,
    }


def _calc_candle_intent(
    shape: dict[str, Any],
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if evidence is None:
        return {
            "intent_label": "UNKNOWN",
            "intent_score": 0.0,
            "intent_strength": "NONE",
        }

    direction = shape["candle_direction"]
    ev_label = evidence.get("evidence_label", "UNKNOWN")
    delta_ratio = float(evidence.get("delta_ratio", 0.0))
    intent_score = round(delta_ratio, 6)

    if direction == "BULLISH" and ev_label == "LONG_PRESSURE":
        intent_label = "BUY_PRESSURE_CONFIRMED"
    elif direction == "BULLISH" and ev_label == "SHORT_PRESSURE":
        intent_label = "BUY_PRESSURE_REJECTED"
        intent_score = round(-abs(delta_ratio), 6)
    elif direction == "BEARISH" and ev_label == "SHORT_PRESSURE":
        intent_label = "SELL_PRESSURE_CONFIRMED"
        intent_score = round(-abs(delta_ratio), 6)
    elif direction == "BEARISH" and ev_label == "LONG_PRESSURE":
        intent_label = "SELL_PRESSURE_REJECTED"
    elif ev_label == "BALANCED" or direction == "DOJI":
        intent_label = "BALANCED"
        intent_score = 0.0
    else:
        intent_label = "UNKNOWN"
        intent_score = 0.0

    abs_score = abs(intent_score)
    if abs_score >= 0.7:
        intent_strength = "STRONG"
    elif abs_score >= 0.4:
        intent_strength = "MODERATE"
    elif abs_score > 0.0:
        intent_strength = "WEAK"
    else:
        intent_strength = "NONE"

    return {
        "intent_label": intent_label,
        "intent_score": intent_score,
        "intent_strength": intent_strength,
    }


def _calc_flow_vs_price(
    shape: dict[str, Any],
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if evidence is None:
        return {"alignment": "UNKNOWN", "explanation": "No 1S evidence available."}

    direction = shape["candle_direction"]
    micro_winner = evidence.get("micro_winner", "UNKNOWN")

    if direction == "DOJI" or micro_winner == "BALANCED":
        return {
            "alignment": "NEUTRAL",
            "explanation": f"Candle is {direction} and micro winner is {micro_winner}.",
        }

    if (direction == "BULLISH" and micro_winner == "LONG") or (
        direction == "BEARISH" and micro_winner == "SHORT"
    ):
        return {
            "alignment": "ALIGNED",
            "explanation": f"Price closed {direction.lower()} and micro flow confirms {micro_winner.lower()} pressure.",
        }

    if (direction == "BULLISH" and micro_winner == "SHORT") or (
        direction == "BEARISH" and micro_winner == "LONG"
    ):
        return {
            "alignment": "DIVERGENT",
            "explanation": f"Price closed {direction.lower()} but micro flow shows {micro_winner.lower()} pressure — divergence.",
        }

    return {"alignment": "UNKNOWN", "explanation": "Alignment could not be determined."}


def _calc_coverage(candle_avail: bool, evidence_avail: bool) -> dict[str, Any]:
    if candle_avail and evidence_avail:
        coverage_pct = 100.0
    elif candle_avail or evidence_avail:
        coverage_pct = 50.0
    else:
        coverage_pct = 0.0
    return {
        "official_candle_available": candle_avail,
        "one_second_evidence_available": evidence_avail,
        "coverage_pct": coverage_pct,
    }


def _calc_quality(s1_score: float, s2_score: float | None) -> dict[str, Any]:
    if s2_score is not None:
        hybrid_weight = round((s1_score + s2_score) / 2.0, 4)
    else:
        hybrid_weight = round(s1_score * 0.7, 4)

    if hybrid_weight >= 0.9:
        label = "GOOD"
    elif hybrid_weight >= 0.7:
        label = "PARTIAL"
    elif hybrid_weight >= 0.5:
        label = "WEAK"
    else:
        label = "DEGRADED"

    return {
        "hybrid_quality_weight": hybrid_weight,
        "hybrid_quality_label": label,
        "usable_for_next_block": True,
    }


def _build_data_quality(
    coverage: dict[str, Any],
    quality: dict[str, Any],
    issues: list[str],
) -> dict[str, Any]:
    score = quality["hybrid_quality_weight"]
    if score >= 0.8:
        level = "HIGH"
    elif score >= 0.5:
        level = "MEDIUM"
    elif score >= 0.2:
        level = "LOW"
    else:
        level = "CRITICAL"
    return {"score": score, "level": level, "issues": issues}


def build_dna(
    symbol: str,
    candle: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    source_mode: str,
    s1_dq_score: float = 1.0,
    s2_dq_score: float | None = None,
) -> dict[str, Any]:
    candle_avail = candle is not None
    evidence_avail = evidence is not None

    issues: list[str] = []
    if not candle_avail:
        issues.append("NO_OFFICIAL_CANDLE")
    if not evidence_avail:
        issues.append("NO_1S_EVIDENCE")

    if candle_avail:
        shape = _calc_shape(candle)
        official_candle_out = {
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle.get("volume"),
        }
    else:
        shape = {
            "candle_direction": "UNKNOWN",
            "body_size": None, "upper_wick_size": None, "lower_wick_size": None,
            "range_size": None, "body_pct": None, "upper_wick_pct": None, "lower_wick_pct": None,
            "shape_label": "UNKNOWN",
            "dna_open": None, "dna_high": None, "dna_low": None, "dna_close": None,
            "body_ratio": None, "wick_upper_ratio": None, "wick_lower_ratio": None,
            "candle_type": "UNKNOWN",
        }
        official_candle_out = {
            "open": None, "high": None, "low": None, "close": None, "volume": None,
        }

    micro_evidence_out = None
    if evidence_avail:
        micro_evidence_out = {
            "evidence_label": evidence.get("evidence_label", "UNKNOWN"),
            "evidence_score": evidence.get("evidence_score", 0.0),
            "evidence_strength": evidence.get("evidence_strength", "NONE"),
            "micro_winner": evidence.get("micro_winner", "UNKNOWN"),
            "delta_ratio": evidence.get("delta_ratio", 0.0),
            "confidence_adjusted": evidence.get("confidence_adjusted", False),
        }

    candle_intent = _calc_candle_intent(shape, evidence)
    flow_vs_price = _calc_flow_vs_price(shape, evidence)
    coverage = _calc_coverage(candle_avail, evidence_avail)
    quality = _calc_quality(s1_dq_score, s2_dq_score)
    data_quality = _build_data_quality(coverage, quality, issues)

    reason_codes: list[str] = [f"SOURCE_{source_mode}"]
    if not candle_avail:
        reason_codes.append("NO_OFFICIAL_CANDLE")
    else:
        reason_codes.append(f"CANDLE_{shape['candle_direction']}")
    if not evidence_avail:
        reason_codes.append("NO_1S_EVIDENCE")
    reason_codes.append(f"INTENT_{candle_intent['intent_label']}")
    reason_codes.append(f"ALIGNMENT_{flow_vs_price['alignment']}")
    reason_codes.append(f"DATA_QUALITY_{data_quality['level']}")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "official_candle": official_candle_out,
        "micro_evidence": micro_evidence_out,
        "shape": shape,
        "candle_intent": candle_intent,
        "flow_vs_price": flow_vs_price,
        "coverage": coverage,
        "quality": quality,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_dna(
        symbol, _FAKE_CANDLE, _FAKE_EVIDENCE, "FAKE_SAMPLE",
        s1_dq_score=1.0, s2_dq_score=0.85,
    )
