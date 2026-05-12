"""S5 Liquidity + Structure Context — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S5_LIQUIDITY_STRUCTURE_CONTEXT"
FEEDS_NEXT = {"next_blocks": ["S6_SCENARIO_SETUP_CANDIDATE"]}

_FAKE_S1: dict[str, Any] = {
    "available": True,
    "current_price": 105000.0,
    "range_high": 105500.0,
    "range_low": 104200.0,
}

_FAKE_S3: dict[str, Any] = {
    "available": True,
    "candle_direction": "BULLISH",
    "body_pct": 23.08,
    "upper_wick_pct": 38.46,
    "lower_wick_pct": 38.46,
    "shape_label": "BULLISH_SPINNING_TOP",
    "intent_score": 0.621053,
    "intent_label": "BUY_PRESSURE_CONFIRMED",
}

_FAKE_S4: dict[str, Any] = {
    "available": True,
    "quality_weight": 0.9513,
    "quality_label": "HIGH_QUALITY",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_input_status(
    s1: dict[str, Any] | None,
    s3: dict[str, Any] | None,
    s4: dict[str, Any] | None,
) -> dict[str, Any]:
    mt_avail = s1 is not None and bool(s1.get("available", False))
    hc_avail = s3 is not None and bool(s3.get("available", False))
    qw_avail = s4 is not None and bool(s4.get("available", False))
    missing: list[str] = []
    if not mt_avail:
        missing.append("S1_MARKET_TRUTH")
    if not hc_avail:
        missing.append("S3_HYBRID_CANDLE")
    if not qw_avail:
        missing.append("S4_QUALITY_WEIGHT")
    return {
        "market_truth_available": mt_avail,
        "hybrid_candle_available": hc_avail,
        "quality_weight_available": qw_avail,
        "missing_inputs": missing,
    }


def _calc_range_context(s1: dict[str, Any] | None) -> dict[str, Any]:
    if s1 is None or not s1.get("available"):
        return {
            "current_price": None,
            "range_high": None,
            "range_low": None,
            "range_mid": None,
            "price_zone": "UNKNOWN",
        }
    cp = float(s1["current_price"])
    rh = float(s1["range_high"])
    rl = float(s1["range_low"])
    rng = rh - rl
    mid = round((rh + rl) / 2.0, 4)
    if rng <= 0.0:
        price_zone = "UNKNOWN"
    elif cp > rh:
        price_zone = "ABOVE_RANGE"
    elif cp >= rl + rng * 0.75:
        price_zone = "UPPER_RANGE"
    elif cp >= rl + rng * 0.25:
        price_zone = "MID_RANGE"
    elif cp >= rl:
        price_zone = "LOWER_RANGE"
    else:
        price_zone = "BELOW_RANGE"
    return {
        "current_price": cp,
        "range_high": rh,
        "range_low": rl,
        "range_mid": mid,
        "price_zone": price_zone,
    }


def _calc_structure(s3: dict[str, Any] | None) -> dict[str, Any]:
    if s3 is None or not s3.get("available"):
        return {
            "structure_bias": "UNKNOWN",
            "structure_event": "UNKNOWN",
            "structure_score": 0.0,
        }
    direction = str(s3.get("candle_direction", "UNKNOWN")).upper()
    body_pct = float(s3.get("body_pct", 0.0))
    shape_label = str(s3.get("shape_label", "UNKNOWN")).upper()
    intent_score = float(s3.get("intent_score", 0.5))

    if body_pct < 15.0:
        structure_bias = "RANGE"
    elif direction == "BULLISH":
        structure_bias = "BULLISH"
    elif direction == "BEARISH":
        structure_bias = "BEARISH"
    else:
        structure_bias = "UNKNOWN"

    if "SPINNING" in shape_label or "DOJI" in shape_label:
        structure_event = "RANGE_BALANCE"
    elif "MARUBOZU" in shape_label and structure_bias == "BULLISH":
        structure_event = "BULLISH_CONTINUATION"
    elif "MARUBOZU" in shape_label and structure_bias == "BEARISH":
        structure_event = "BEARISH_CONTINUATION"
    elif structure_bias == "BULLISH":
        structure_event = "BULLISH_CONTINUATION"
    elif structure_bias == "BEARISH":
        structure_event = "BEARISH_CONTINUATION"
    elif structure_bias == "RANGE":
        structure_event = "RANGE_BALANCE"
    else:
        structure_event = "UNKNOWN"

    direction_strength = min(1.0, body_pct / 100.0)
    structure_score = round((direction_strength + intent_score) / 2.0, 4)

    return {
        "structure_bias": structure_bias,
        "structure_event": structure_event,
        "structure_score": structure_score,
    }


def _calc_liquidity_levels(s1: dict[str, Any] | None) -> dict[str, Any]:
    _null_level: dict[str, Any] = {
        "price": None,
        "distance_abs": None,
        "distance_pct": None,
        "liquidity_type": "UNKNOWN",
    }
    if s1 is None or not s1.get("available"):
        return {
            "nearest_liquidity_above": dict(_null_level),
            "nearest_liquidity_below": dict(_null_level),
        }
    cp = float(s1["current_price"])
    rh = float(s1["range_high"])
    rl = float(s1["range_low"])
    dist_above = round(rh - cp, 4)
    dist_below = round(cp - rl, 4)
    pct_above = round(dist_above / cp * 100.0, 4) if cp > 0.0 else 0.0
    pct_below = round(dist_below / cp * 100.0, 4) if cp > 0.0 else 0.0
    return {
        "nearest_liquidity_above": {
            "price": rh,
            "distance_abs": dist_above,
            "distance_pct": pct_above,
            "liquidity_type": "RANGE_HIGH",
        },
        "nearest_liquidity_below": {
            "price": rl,
            "distance_abs": dist_below,
            "distance_pct": pct_below,
            "liquidity_type": "RANGE_LOW",
        },
    }


def _calc_liquidity_bias(structure: dict[str, Any]) -> dict[str, Any]:
    bias = structure["structure_bias"]
    struct_score = structure["structure_score"]
    if bias == "BULLISH":
        draw = "ABOVE"
        label = "BUY_SIDE_NEAR"
    elif bias == "BEARISH":
        draw = "BELOW"
        label = "SELL_SIDE_NEAR"
    elif bias == "RANGE":
        draw = "BOTH"
        label = "BALANCED_LIQUIDITY"
    else:
        draw = "UNKNOWN"
        label = "NO_CLEAR_LIQUIDITY"
    return {
        "draw_on_liquidity": draw,
        "liquidity_context_label": label,
        "liquidity_score": round(struct_score, 4),
    }


def _calc_simple_context(
    structure: dict[str, Any],
    quality_weight: float,
) -> dict[str, Any]:
    bias = structure["structure_bias"]
    if bias == "BULLISH":
        base_label = "BULLISH_CONTEXT"
        base_score = 80.0
    elif bias == "BEARISH":
        base_label = "BEARISH_CONTEXT"
        base_score = 80.0
    elif bias == "RANGE":
        base_label = "RANGE_CONTEXT"
        base_score = 50.0
    else:
        base_label = "WEAK_CONTEXT"
        base_score = 30.0
    context_score = round(base_score * quality_weight, 2)
    usable = bias in ("BULLISH", "BEARISH") and context_score >= 50.0
    return {
        "context_label": base_label,
        "context_score": context_score,
        "usable_for_setup_candidate": usable,
    }


def _calc_quality_context(
    s4: dict[str, Any] | None,
    context_score: float,
) -> dict[str, Any]:
    if s4 is None or not s4.get("available"):
        qw = 0.5
        ql = "UNKNOWN"
    else:
        qw = float(s4.get("quality_weight", 0.5))
        ql = str(s4.get("quality_label", "UNKNOWN"))
    return {
        "inherited_quality_weight": qw,
        "quality_label": ql,
        "quality_adjusted_context_score": context_score,
    }


def _build_data_quality(
    input_status: dict[str, Any],
    s4: dict[str, Any] | None,
) -> dict[str, Any]:
    issues = list(input_status["missing_inputs"])
    if s4 is not None and s4.get("available"):
        base = float(s4.get("quality_weight", 0.5))
    else:
        base = 0.5
    if not input_status["market_truth_available"]:
        base = max(0.0, base - 0.40)
    if not input_status["hybrid_candle_available"]:
        base = max(0.0, base - 0.20)
    score = round(max(0.0, min(1.0, base)), 4)
    if score >= 0.8:
        level = "HIGH"
    elif score >= 0.5:
        level = "MEDIUM"
    elif score >= 0.2:
        level = "LOW"
    else:
        level = "CRITICAL"
    return {"score": score, "level": level, "issues": issues}


def _build_reason_codes(
    source_mode: str,
    input_status: dict[str, Any],
    structure: dict[str, Any],
    liq_bias: dict[str, Any],
    ctx: dict[str, Any],
    data_quality: dict[str, Any],
) -> list[str]:
    codes: list[str] = [f"SOURCE_{source_mode}"]
    for missing in input_status["missing_inputs"]:
        codes.append(f"MISSING_{missing}")
    codes.append(f"STRUCTURE_{structure['structure_bias']}")
    codes.append(f"DRAW_{liq_bias['draw_on_liquidity']}")
    ctx_short = ctx["context_label"].replace("_CONTEXT", "")
    codes.append(f"CONTEXT_{ctx_short}")
    codes.append(f"DATA_QUALITY_{data_quality['level']}")
    return codes


def _build_liquidity_notes(
    liq_bias: dict[str, Any],
    liq_levels: dict[str, Any],
    ctx: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    draw = liq_bias["draw_on_liquidity"]
    above_price = liq_levels["nearest_liquidity_above"]["price"]
    below_price = liq_levels["nearest_liquidity_below"]["price"]
    if draw == "ABOVE":
        notes.append(f"Buy-side liquidity pool above current price at {above_price}.")
    elif draw == "BELOW":
        notes.append(f"Sell-side liquidity pool below current price at {below_price}.")
    elif draw == "BOTH":
        notes.append("Range balance — liquidity pools on both sides.")
    else:
        notes.append("Liquidity direction unclear.")
    if ctx["usable_for_setup_candidate"]:
        notes.append("Context strength sufficient for setup candidate in S6.")
    else:
        notes.append("Context not strong enough to qualify for setup candidate.")
    return notes


def build_liquidity_structure(
    symbol: str,
    s1: dict[str, Any] | None,
    s3: dict[str, Any] | None,
    s4: dict[str, Any] | None,
    source_mode: str,
) -> dict[str, Any]:
    quality_weight = (
        float(s4.get("quality_weight", 0.5))
        if s4 is not None and s4.get("available")
        else 0.5
    )
    input_status = _calc_input_status(s1, s3, s4)
    range_ctx = _calc_range_context(s1)
    structure = _calc_structure(s3)
    liq_levels = _calc_liquidity_levels(s1)
    liq_bias = _calc_liquidity_bias(structure)
    ctx = _calc_simple_context(structure, quality_weight)
    quality_ctx = _calc_quality_context(s4, ctx["context_score"])
    data_quality = _build_data_quality(input_status, s4)
    reason_codes = _build_reason_codes(
        source_mode, input_status, structure, liq_bias, ctx, data_quality
    )
    liquidity_notes = _build_liquidity_notes(liq_bias, liq_levels, ctx)

    nearest_resistance = liq_levels["nearest_liquidity_above"]["price"]
    nearest_support = liq_levels["nearest_liquidity_below"]["price"]

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "input_status": input_status,
        "range_context": range_ctx,
        "structure": structure,
        "liquidity_levels": liq_levels,
        "liquidity_bias": liq_bias,
        "simple_context": ctx,
        "quality_context": quality_ctx,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "liquidity_notes": liquidity_notes,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_liquidity_structure(symbol, _FAKE_S1, _FAKE_S3, _FAKE_S4, "FAKE_SAMPLE")
