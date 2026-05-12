"""S2 Lightweight 1S Evidence Engine — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S2_LIGHTWEIGHT_1S_EVIDENCE"
FEEDS_NEXT = {"next_blocks": ["S3_HYBRID_CANDLE_DNA"]}

_FAKE_TICKS: list[dict[str, Any]] = [
    {"price": 104710.0, "side": "BUY",  "qty": 0.05},
    {"price": 104720.0, "side": "BUY",  "qty": 0.12},
    {"price": 104715.0, "side": "SELL", "qty": 0.03},
    {"price": 104730.0, "side": "BUY",  "qty": 0.08},
    {"price": 104725.0, "side": "SELL", "qty": 0.04},
    {"price": 104740.0, "side": "BUY",  "qty": 0.15},
    {"price": 104735.0, "side": "SELL", "qty": 0.02},
    {"price": 104750.0, "side": "BUY",  "qty": 0.20},
    {"price": 104745.0, "side": "SELL", "qty": 0.06},
    {"price": 104760.0, "side": "BUY",  "qty": 0.10},
    {"price": 104755.0, "side": "SELL", "qty": 0.03},
    {"price": 104770.0, "side": "BUY",  "qty": 0.07},
]
_FAKE_MISSING_SECONDS = 5


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_trade_flow(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    buy_vol = 0.0
    sell_vol = 0.0
    for t in ticks:
        qty = float(t.get("qty", 0.0))
        if t.get("side") == "BUY":
            buy_vol += qty
        else:
            sell_vol += qty
    total = buy_vol + sell_vol
    delta = buy_vol - sell_vol
    delta_ratio = round(delta / total, 6) if total != 0.0 else 0.0
    return {
        "buy_volume": round(buy_vol, 8),
        "sell_volume": round(sell_vol, 8),
        "total_volume": round(total, 8),
        "delta": round(delta, 8),
        "delta_ratio": delta_ratio,
        "trade_count": len(ticks),
    }


def _calc_evidence(
    trade_flow: dict[str, Any],
    missing_seconds: int,
) -> dict[str, Any]:
    total_vol = trade_flow["total_volume"]
    buy_vol = trade_flow["buy_volume"]
    sell_vol = trade_flow["sell_volume"]
    tick_count = trade_flow["trade_count"]

    if total_vol == 0.0 or tick_count == 0:
        return {
            "evidence_score": 0.0,
            "evidence_label": "UNKNOWN",
            "evidence_strength": "NONE",
            "micro_winner": "UNKNOWN",
            "tick_count": tick_count,
            "buy_pressure": 0.0,
            "sell_pressure": 0.0,
            "missing_seconds": missing_seconds,
            "confidence_adjusted": missing_seconds > 0,
        }

    buy_pressure = round(buy_vol / total_vol, 6)
    sell_pressure = round(sell_vol / total_vol, 6)
    raw_score = trade_flow["delta_ratio"] * 10.0
    evidence_score = round(max(-10.0, min(10.0, raw_score)), 4)

    if evidence_score > 2.0:
        evidence_label = "LONG_PRESSURE"
        micro_winner = "LONG"
    elif evidence_score < -2.0:
        evidence_label = "SHORT_PRESSURE"
        micro_winner = "SHORT"
    else:
        evidence_label = "BALANCED"
        micro_winner = "BALANCED"

    abs_score = abs(evidence_score)
    if abs_score >= 7.0:
        evidence_strength = "STRONG"
    elif abs_score >= 4.0:
        evidence_strength = "MODERATE"
    elif abs_score > 0.0:
        evidence_strength = "WEAK"
    else:
        evidence_strength = "NONE"

    return {
        "evidence_score": evidence_score,
        "evidence_label": evidence_label,
        "evidence_strength": evidence_strength,
        "micro_winner": micro_winner,
        "tick_count": tick_count,
        "buy_pressure": buy_pressure,
        "sell_pressure": sell_pressure,
        "missing_seconds": missing_seconds,
        "confidence_adjusted": missing_seconds > 0,
    }


def _calc_quality(
    ticks: list[dict[str, Any]],
    missing_seconds: int,
    total_seconds: int = 60,
) -> dict[str, Any]:
    covered = max(0, total_seconds - missing_seconds)
    coverage_pct = round(covered / total_seconds * 100.0, 2) if total_seconds > 0 else 0.0

    if not ticks:
        label = "EMPTY"
    elif coverage_pct >= 90.0:
        label = "GOOD"
    elif coverage_pct >= 60.0:
        label = "PARTIAL"
    else:
        label = "WEAK"

    return {
        "sample_coverage_pct": coverage_pct,
        "sample_quality_label": label,
        "usable_for_next_block": True,
    }


def _build_data_quality(missing_seconds: int, tick_count: int) -> dict[str, Any]:
    issues: list[str] = []
    if tick_count == 0:
        issues.append("NO_TICKS")
    if missing_seconds > 0:
        issues.append(f"MISSING_{missing_seconds}_SECONDS")

    if tick_count == 0:
        score = 0.0
    elif missing_seconds == 0:
        score = 1.0
    elif missing_seconds < 10:
        score = 0.85
    elif missing_seconds < 30:
        score = 0.65
    else:
        score = 0.4

    if score >= 0.8:
        level = "HIGH"
    elif score >= 0.5:
        level = "MEDIUM"
    elif score >= 0.2:
        level = "LOW"
    else:
        level = "CRITICAL"

    return {"score": round(score, 4), "level": level, "issues": issues}


def build_evidence(
    symbol: str,
    ticks: list[dict[str, Any]],
    missing_seconds: int,
    source_mode: str,
) -> dict[str, Any]:
    trade_flow = _calc_trade_flow(ticks)
    evidence = _calc_evidence(trade_flow, missing_seconds)
    quality = _calc_quality(ticks, missing_seconds)
    data_quality = _build_data_quality(missing_seconds, trade_flow["trade_count"])

    reason_codes: list[str] = [f"SOURCE_{source_mode}"]
    if missing_seconds > 0:
        reason_codes.append("CONFIDENCE_ADJUSTED_MISSING_SECONDS")
    if trade_flow["trade_count"] == 0:
        reason_codes.append("NO_TICK_DATA")
    reason_codes.append(f"EVIDENCE_{evidence['evidence_label']}")
    reason_codes.append(f"DATA_QUALITY_{data_quality['level']}")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "market_context": {
            "s1_close": None,
            "s1_high": None,
            "s1_low": None,
        },
        "trade_flow": trade_flow,
        "evidence": evidence,
        "quality": quality,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_evidence(symbol, _FAKE_TICKS, _FAKE_MISSING_SECONDS, "FAKE_SAMPLE")
