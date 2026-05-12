"""S4 Quality Weight Engine — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S4_QUALITY_WEIGHT_ENGINE"
FEEDS_NEXT = {"next_blocks": ["S5_LIQUIDITY_STRUCTURE_CONTEXT"]}

_FAKE_S1: dict[str, Any] = {
    "available": True,
    "data_quality_score": 1.0,
    "consistency_label": "CONSISTENT",
}
_FAKE_S2: dict[str, Any] = {
    "available": True,
    "data_quality_score": 0.85,
}
_FAKE_S3: dict[str, Any] = {
    "available": True,
    "hybrid_quality_weight": 0.925,
}

_W_MARKET = 0.40
_W_EVIDENCE = 0.20
_W_HYBRID = 0.25
_W_COVERAGE = 0.10
_W_CONSISTENCY = 0.05


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_input_status(
    s1: dict[str, Any] | None,
    s2: dict[str, Any] | None,
    s3: dict[str, Any] | None,
) -> dict[str, Any]:
    mt_avail = s1 is not None and bool(s1.get("available", False))
    ev_avail = s2 is not None and bool(s2.get("available", False))
    hc_avail = s3 is not None and bool(s3.get("available", False))
    missing: list[str] = []
    if not mt_avail:
        missing.append("S1_MARKET_TRUTH")
    if not ev_avail:
        missing.append("S2_1S_EVIDENCE")
    if not hc_avail:
        missing.append("S3_HYBRID_CANDLE")
    return {
        "market_truth_available": mt_avail,
        "one_second_evidence_available": ev_avail,
        "hybrid_candle_available": hc_avail,
        "missing_inputs": missing,
    }


def _calc_quality_components(
    s1: dict[str, Any] | None,
    s2: dict[str, Any] | None,
    s3: dict[str, Any] | None,
) -> dict[str, Any]:
    s1_avail = s1 is not None and bool(s1.get("available", False))
    s2_avail = s2 is not None and bool(s2.get("available", False))
    s3_avail = s3 is not None and bool(s3.get("available", False))

    market_truth_score = float(s1.get("data_quality_score", 0.0)) if s1_avail else 0.0
    evidence_score = float(s2.get("data_quality_score", 0.5)) if s2_avail else 0.5
    hybrid_candle_score = float(s3.get("hybrid_quality_weight", 0.5)) if s3_avail else 0.5

    avail_count = sum([s1_avail, s2_avail, s3_avail])
    if avail_count == 3:
        coverage_score = 1.0
    elif avail_count == 2:
        coverage_score = 0.7
    elif avail_count == 1:
        coverage_score = 0.4
    else:
        coverage_score = 0.0

    if s1_avail:
        cl = s1.get("consistency_label", "UNKNOWN")
        if cl == "CONSISTENT":
            consistency_score = 1.0
        elif cl == "MINOR_MISMATCH":
            consistency_score = 0.7
        elif cl == "MAJOR_MISMATCH":
            consistency_score = 0.2
        else:
            consistency_score = 0.5
    else:
        consistency_score = 0.0

    final = (
        market_truth_score * _W_MARKET
        + evidence_score * _W_EVIDENCE
        + hybrid_candle_score * _W_HYBRID
        + coverage_score * _W_COVERAGE
        + consistency_score * _W_CONSISTENCY
    )
    final = round(max(0.0, min(1.0, final)), 4)

    return {
        "market_truth_score": round(market_truth_score, 4),
        "evidence_score": round(evidence_score, 4),
        "hybrid_candle_score": round(hybrid_candle_score, 4),
        "coverage_score": round(coverage_score, 4),
        "consistency_score": round(consistency_score, 4),
        "final_quality_score": final,
    }


def _calc_quality_weight(final_score: float) -> dict[str, Any]:
    if final_score >= 0.85:
        quality_label = "HIGH_QUALITY"
        confidence_policy = "FULL_CONFIDENCE"
    elif final_score >= 0.70:
        quality_label = "ACCEPTABLE"
        confidence_policy = "REDUCED_CONFIDENCE"
    elif final_score >= 0.55:
        quality_label = "USABLE_DEGRADED"
        confidence_policy = "REDUCED_CONFIDENCE"
    elif final_score >= 0.35:
        quality_label = "WEAK_BUT_USABLE"
        confidence_policy = "WATCH_ONLY"
    elif final_score >= 0.10:
        quality_label = "REPAIR_REQUIRED"
        confidence_policy = "REPAIR_MODE"
    else:
        quality_label = "INVALID"
        confidence_policy = "INVALID"
    return {
        "quality_weight": final_score,
        "quality_label": quality_label,
        "confidence_policy": confidence_policy,
    }


def _calc_decision_policy(qw: dict[str, Any]) -> dict[str, Any]:
    cp = qw["confidence_policy"]
    if cp in ("FULL_CONFIDENCE", "REDUCED_CONFIDENCE"):
        return {"decision_quality_mode": "ALLOW_DECISION", "max_allowed_decision": "ALLOW_PAPER"}
    elif cp == "WATCH_ONLY":
        return {"decision_quality_mode": "ALLOW_WATCH_ONLY", "max_allowed_decision": "WATCH"}
    elif cp == "REPAIR_MODE":
        return {"decision_quality_mode": "BLOCK_DECISION", "max_allowed_decision": "BLOCK"}
    else:
        return {"decision_quality_mode": "BLOCK_DECISION", "max_allowed_decision": "INVALID"}


def _calc_repair_policy(
    s1: dict[str, Any] | None,
    final_score: float,
) -> dict[str, Any]:
    s1_avail = s1 is not None and bool(s1.get("available", False))
    if not s1_avail:
        return {"repair_required": True, "repair_action": "REBUILD_S1"}
    if s1.get("consistency_label") == "MAJOR_MISMATCH":
        return {"repair_required": True, "repair_action": "REBUILD_S1"}
    if final_score < 0.10:
        return {"repair_required": True, "repair_action": "REBUILD_CHAIN"}
    return {"repair_required": False, "repair_action": "NONE"}


def _calc_edge_policy(qw: dict[str, Any]) -> dict[str, Any]:
    label = qw["quality_label"]
    if label in ("HIGH_QUALITY", "ACCEPTABLE"):
        return {
            "edge_eligible_if_trade_opens": True,
            "edge_reason": f"Quality {label} meets edge threshold.",
        }
    return {
        "edge_eligible_if_trade_opens": False,
        "edge_reason": f"Quality {label} below edge threshold — trade excluded from edge stats.",
    }


def _build_data_quality(final_score: float, issues: list[str]) -> dict[str, Any]:
    if final_score >= 0.8:
        level = "HIGH"
    elif final_score >= 0.5:
        level = "MEDIUM"
    elif final_score >= 0.2:
        level = "LOW"
    else:
        level = "CRITICAL"
    return {"score": final_score, "level": level, "issues": issues}


def build_quality_weight(
    symbol: str,
    s1: dict[str, Any] | None,
    s2: dict[str, Any] | None,
    s3: dict[str, Any] | None,
    source_mode: str,
) -> dict[str, Any]:
    input_status = _calc_input_status(s1, s2, s3)
    components = _calc_quality_components(s1, s2, s3)
    final_score = components["final_quality_score"]
    qw = _calc_quality_weight(final_score)
    decision_policy = _calc_decision_policy(qw)
    repair_policy = _calc_repair_policy(s1, final_score)
    edge_policy = _calc_edge_policy(qw)

    issues = list(input_status["missing_inputs"])
    data_quality = _build_data_quality(final_score, issues)

    reason_codes: list[str] = [f"SOURCE_{source_mode}"]
    reason_codes.append(f"QUALITY_{qw['quality_label']}")
    reason_codes.append(f"DECISION_{decision_policy['max_allowed_decision']}")
    if edge_policy["edge_eligible_if_trade_opens"]:
        reason_codes.append("EDGE_ELIGIBLE")
    else:
        reason_codes.append("EDGE_NOT_ELIGIBLE")
    reason_codes.append(f"DATA_QUALITY_{data_quality['level']}")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "input_status": input_status,
        "quality_components": components,
        "quality_weight": qw,
        "decision_policy": decision_policy,
        "repair_policy": repair_policy,
        "edge_policy": edge_policy,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_quality_weight(symbol, _FAKE_S1, _FAKE_S2, _FAKE_S3, "FAKE_SAMPLE")
