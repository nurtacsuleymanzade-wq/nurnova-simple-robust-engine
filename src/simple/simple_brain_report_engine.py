"""S10 Simple Brain Report Engine — NOVA SIMPLE ROBUST ENGINE v1.

Read-only aggregation of S1-S9 state. Creates no new decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S10_SIMPLE_BRAIN_REPORT"
FEEDS_NEXT = {"next_blocks": ["SIMPLE_ENGINE_COMPLETE"]}

_BRAIN_STATUSES = ("READY", "DEGRADED", "INCOMPLETE")
_SYSTEM_HEALTH_MAP = {"READY": "OK", "DEGRADED": "DEGRADED", "INCOMPLETE": "CRITICAL"}

_FAKE_INPUTS: dict[str, Any] = {
    "s1": {
        "official_candle": {
            "open": 105000.0, "high": 105600.0, "low": 104500.0, "close": 105550.0,
        },
        "price_truth": {"mid_price": 105000.0},
    },
    "s2": {
        "evidence": {"evidence_label": "LONG_PRESSURE", "evidence_strength": "MODERATE"},
    },
    "s3": {
        "shape": {"candle_direction": "BULLISH"},
        "candle_intent": {"intent_label": "BUY_PRESSURE_CONFIRMED"},
    },
    "s4": {
        "quality_weight": {
            "quality_weight": 0.9513,
            "quality_label": "HIGH_QUALITY",
            "confidence_policy": "FULL_CONFIDENCE",
        },
        "decision_policy": {"decision_quality_mode": "ALLOW_DECISION"},
    },
    "s5": {
        "nearest_support": 104200.0,
        "nearest_resistance": 105500.0,
        "structure": {"structure_bias": "BULLISH"},
    },
    "s6": {
        "setup_candidate": {
            "setup_type": "LONG_CONTINUATION",
            "setup_direction": "LONG",
            "setup_grade": "A",
            "setup_status": "READY_FOR_PLAN",
        },
        "scenario": {"scenario_type": "CONTINUATION"},
    },
    "s7": {
        "decision_gate": {
            "decision": "ALLOW_PAPER",
            "paper_eligible": True,
            "edge_eligible_if_outcome_closes": True,
            "decision_reason": "Setup READY_FOR_PLAN with GOOD_RR — paper trade allowed.",
        },
        "trade_plan": {
            "trade_direction": "LONG",
            "entry_price": 105000.0,
            "stop_loss": 104200.0,
            "tp1": 105500.0,
            "tp2": 106600.0,
        },
        "risk_reward": {"rr_tp1": 0.625, "rr_tp2": 2.0},
    },
    "s8": {
        "result": {"outcome": "WIN_TP1", "realized_rr": 0.625},
        "lifecycle": {"trade_status": "CLOSED"},
        "edge_eligibility": {"edge_eligible": True},
    },
    "s9": {
        "edge_eligible_count": 3,
        "win_count": 2,
        "loss_count": 1,
        "win_rate": 0.6667,
        "avg_rr_realized": 0.5417,
        "edge_score": 0.3612,
        "data_quality": {"level": "LOW"},
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_input_status(inputs: dict[str, Any]) -> dict[str, Any]:
    block_keys = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]
    block_names = [
        "S1_MARKET_TRUTH", "S2_1S_EVIDENCE", "S3_HYBRID_CANDLE_DNA",
        "S4_QUALITY_WEIGHT", "S5_LIQUIDITY_STRUCTURE", "S6_SETUP_CANDIDATE",
        "S7_TRADE_PLAN_DECISION", "S8_PAPER_OUTCOME", "S9_EDGE_STATS",
    ]
    available: dict[str, bool] = {}
    for key, name in zip(block_keys, block_names):
        available[name] = inputs.get(key) is not None

    blocks_available = sum(1 for v in available.values() if v)
    missing = [name for name, ok in available.items() if not ok]

    return {
        "blocks_available": blocks_available,
        "blocks_total": 9,
        "available": available,
        "missing_blocks": missing,
    }


def _extract_market_snapshot(
    s1: dict | None,
    s2: dict | None,
    s3: dict | None,
) -> dict[str, Any]:
    if s1 is None:
        return {"available": False}
    oc = s1.get("official_candle", {})
    pt = s1.get("price_truth", {})
    ev = (s2 or {}).get("evidence", {})
    intent = (s3 or {}).get("candle_intent", {})
    shape = (s3 or {}).get("shape", {})
    return {
        "available": True,
        "mid_price": pt.get("mid_price"),
        "high": oc.get("high"),
        "low": oc.get("low"),
        "close": oc.get("close"),
        "candle_direction": shape.get("candle_direction"),
        "evidence_label": ev.get("evidence_label"),
        "evidence_strength": ev.get("evidence_strength"),
        "candle_intent": intent.get("intent_label"),
    }


def _extract_quality_snapshot(s4: dict | None) -> dict[str, Any]:
    if s4 is None:
        return {"available": False}
    qw = s4.get("quality_weight", {})
    dp = s4.get("decision_policy", {})
    return {
        "available": True,
        "quality_weight": qw.get("quality_weight"),
        "quality_label": qw.get("quality_label"),
        "confidence_policy": qw.get("confidence_policy"),
        "decision_quality_mode": dp.get("decision_quality_mode"),
    }


def _extract_setup_snapshot(s5: dict | None, s6: dict | None) -> dict[str, Any]:
    if s6 is None:
        return {"available": False}
    sc = s6.get("setup_candidate", {})
    scenario = s6.get("scenario", {})
    return {
        "available": True,
        "setup_type": sc.get("setup_type"),
        "setup_direction": sc.get("setup_direction"),
        "setup_grade": sc.get("setup_grade"),
        "setup_status": sc.get("setup_status"),
        "scenario_type": scenario.get("scenario_type"),
        "nearest_support": (s5 or {}).get("nearest_support"),
        "nearest_resistance": (s5 or {}).get("nearest_resistance"),
        "structure_bias": (s5 or {}).get("structure", {}).get("structure_bias"),
    }


def _extract_decision_snapshot(s7: dict | None) -> dict[str, Any]:
    if s7 is None:
        return {"available": False}
    dg = s7.get("decision_gate", {})
    tp = s7.get("trade_plan", {})
    rr = s7.get("risk_reward", {}) or {}
    return {
        "available": True,
        "decision": dg.get("decision"),
        "decision_reason": dg.get("decision_reason"),
        "paper_eligible": dg.get("paper_eligible"),
        "edge_eligible_if_outcome_closes": dg.get("edge_eligible_if_outcome_closes"),
        "trade_direction": tp.get("trade_direction"),
        "entry_price": tp.get("entry_price"),
        "stop_loss": tp.get("stop_loss"),
        "tp1": tp.get("tp1"),
        "tp2": tp.get("tp2"),
        "rr_tp1": rr.get("rr_tp1"),
        "rr_tp2": rr.get("rr_tp2"),
    }


def _extract_paper_outcome_snapshot(s8: dict | None) -> dict[str, Any]:
    if s8 is None:
        return {"available": False}
    result = s8.get("result", {})
    lifecycle = s8.get("lifecycle", {})
    ee = s8.get("edge_eligibility", {})
    return {
        "available": True,
        "outcome": result.get("outcome"),
        "realized_rr": result.get("realized_rr"),
        "trade_status": lifecycle.get("trade_status"),
        "edge_eligible": ee.get("edge_eligible"),
    }


def _extract_edge_snapshot(s9: dict | None) -> dict[str, Any]:
    if s9 is None:
        return {"available": False}
    return {
        "available": True,
        "edge_eligible_count": s9.get("edge_eligible_count"),
        "win_count": s9.get("win_count"),
        "loss_count": s9.get("loss_count"),
        "win_rate": s9.get("win_rate"),
        "avg_rr_realized": s9.get("avg_rr_realized"),
        "edge_score": s9.get("edge_score"),
        "sample_quality": (s9.get("data_quality") or {}).get("level"),
    }


def _compute_brain_state(
    input_status: dict[str, Any],
    decision_snapshot: dict[str, Any],
) -> tuple[str, str, str]:
    s1_ok = input_status["available"].get("S1_MARKET_TRUTH", False)
    s7_ok = input_status["available"].get("S7_TRADE_PLAN_DECISION", False)

    if not s1_ok or not s7_ok:
        return "INCOMPLETE", "INCOMPLETE", "AWAIT_UPSTREAM_BLOCKS"

    decision = decision_snapshot.get("decision", "UNKNOWN")
    direction = str(decision_snapshot.get("trade_direction") or "UNKNOWN").upper()

    if decision == "ALLOW_PAPER":
        if direction == "LONG":
            return "READY", "PAPER_LONG", "MONITOR_LONG_PAPER_TRADE"
        if direction == "SHORT":
            return "READY", "PAPER_SHORT", "MONITOR_SHORT_PAPER_TRADE"
        return "READY", "PAPER_UNKNOWN", "CHECK_TRADE_DIRECTION"

    return "DEGRADED", "NO_TRADE", "WAIT_FOR_NEXT_SETUP"


def _build_execution_safety() -> dict[str, Any]:
    return {
        "safe_to_open_real_trade": False,
        "private_api_used": False,
        "live_order_sent": False,
    }


def _build_data_quality(input_status: dict[str, Any]) -> dict[str, Any]:
    n = input_status["blocks_available"]
    missing = input_status["missing_blocks"]
    issues = [f"MISSING_{m}" for m in missing]

    if n == 9:
        return {"score": 1.0, "level": "HIGH", "issues": issues}
    if n >= 7:
        return {"score": 0.7, "level": "MEDIUM", "issues": issues}
    if n >= 4:
        return {"score": 0.4, "level": "LOW", "issues": issues}
    return {"score": 0.1, "level": "CRITICAL", "issues": issues}


def _build_reason_codes(
    source_mode: str,
    input_status: dict[str, Any],
    brain_status: str,
    brain_mode: str,
    data_quality: dict[str, Any],
) -> list[str]:
    n = input_status["blocks_available"]
    total = input_status["blocks_total"]
    system_health = _SYSTEM_HEALTH_MAP.get(brain_status, "CRITICAL")
    return [
        f"SOURCE_{source_mode}",
        f"BLOCKS_{n}_OF_{total}",
        f"BRAIN_STATUS_{brain_status}",
        f"BRAIN_MODE_{brain_mode}",
        f"SYSTEM_HEALTH_{system_health}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        f"DATA_QUALITY_{data_quality['level']}",
    ]


def build_brain_report(
    symbol: str,
    inputs: dict[str, Any | None],
    source_mode: str,
    report_path: str = "reports/simple/simple_brain_latest_report.md",
) -> dict[str, Any]:
    input_status = _extract_input_status(inputs)
    market_snapshot = _extract_market_snapshot(
        inputs.get("s1"), inputs.get("s2"), inputs.get("s3")
    )
    quality_snapshot = _extract_quality_snapshot(inputs.get("s4"))
    setup_snapshot = _extract_setup_snapshot(inputs.get("s5"), inputs.get("s6"))
    decision_snapshot = _extract_decision_snapshot(inputs.get("s7"))
    paper_outcome_snapshot = _extract_paper_outcome_snapshot(inputs.get("s8"))
    edge_snapshot = _extract_edge_snapshot(inputs.get("s9"))

    brain_status, brain_mode, primary_next_action = _compute_brain_state(
        input_status, decision_snapshot
    )
    system_health = _SYSTEM_HEALTH_MAP.get(brain_status, "CRITICAL")
    safety = _build_execution_safety()
    data_quality = _build_data_quality(input_status)
    reason_codes = _build_reason_codes(
        source_mode, input_status, brain_status, brain_mode, data_quality
    )

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {"source_mode": source_mode},
        "input_status": input_status,
        "market_snapshot": market_snapshot,
        "quality_snapshot": quality_snapshot,
        "setup_snapshot": setup_snapshot,
        "decision_snapshot": decision_snapshot,
        "paper_outcome_snapshot": paper_outcome_snapshot,
        "edge_snapshot": edge_snapshot,
        "brain_status": brain_status,
        "brain_mode": brain_mode,
        "primary_next_action": primary_next_action,
        "system_health": system_health,
        "report_path": report_path,
        "execution_safety": safety,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_brain_report(symbol, _FAKE_INPUTS, "FAKE_SAMPLE")
