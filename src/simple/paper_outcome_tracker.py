"""S8 Paper Outcome Tracker — NOVA SIMPLE ROBUST ENGINE v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S8_PAPER_OUTCOME_TRACKER"
FEEDS_NEXT = {"next_blocks": ["S9_EDGE_STATS"]}

# high=105600 > tp1=105500 → tp1_hit=True; high=105600 < tp2=106600 → tp2_hit=False;
# low=104500 > stop=104200 → stop_hit=False → WIN_TP1, edge_eligible=True
_FAKE_S1: dict[str, Any] = {
    "available": True,
    "official_high": 105600.0,
    "official_low": 104500.0,
    "official_close": 105550.0,
    "is_official_binance_1m": True,
}

_FAKE_S7: dict[str, Any] = {
    "available": True,
    "decision": "ALLOW_PAPER",
    "paper_eligible": True,
    "edge_eligible_if_outcome_closes": True,
    "trade_direction": "LONG",
    "entry_price": 105000.0,
    "stop_loss": 104200.0,
    "tp1": 105500.0,
    "tp2": 106600.0,
    "rr_tp1": 0.625,
    "rr_tp2": 2.0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_input_status(
    s1: dict[str, Any] | None,
    s7: dict[str, Any] | None,
) -> dict[str, Any]:
    mt = s1 is not None and bool(s1.get("available", False))
    dec = s7 is not None and bool(s7.get("available", False))
    missing: list[str] = []
    if not mt:
        missing.append("S1_MARKET_TRUTH")
    if not dec:
        missing.append("S7_DECISION")
    return {
        "market_truth_available": mt,
        "decision_available": dec,
        "missing_inputs": missing,
    }


def _calc_outcome_check(s1: dict[str, Any] | None) -> dict[str, Any]:
    if s1 is None or not s1.get("available"):
        return {
            "official_high": None,
            "official_low": None,
            "official_close": None,
            "check_method": "OFFICIAL_CANDLE_HIGH_LOW",
        }
    return {
        "official_high": s1.get("official_high"),
        "official_low": s1.get("official_low"),
        "official_close": s1.get("official_close"),
        "check_method": "OFFICIAL_CANDLE_HIGH_LOW",
    }


def _calc_decision_reference(s7: dict[str, Any] | None) -> dict[str, Any]:
    if s7 is None or not s7.get("available"):
        return {
            "decision": "UNKNOWN",
            "paper_eligible": False,
            "edge_eligible_if_outcome_closes": False,
            "trade_direction": "UNKNOWN",
            "entry_price": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "rr_tp1": None,
            "rr_tp2": None,
        }
    return {
        "decision": str(s7.get("decision", "UNKNOWN")),
        "paper_eligible": bool(s7.get("paper_eligible", False)),
        "edge_eligible_if_outcome_closes": bool(s7.get("edge_eligible_if_outcome_closes", False)),
        "trade_direction": str(s7.get("trade_direction", "UNKNOWN")),
        "entry_price": s7.get("entry_price"),
        "stop_loss": s7.get("stop_loss"),
        "tp1": s7.get("tp1"),
        "tp2": s7.get("tp2"),
        "rr_tp1": s7.get("rr_tp1"),
        "rr_tp2": s7.get("rr_tp2"),
    }


def _calc_outcome(
    s1: dict[str, Any] | None,
    s7: dict[str, Any] | None,
) -> dict[str, Any]:
    """Internal outcome calc; returns edge_eligible inside dict for splitting."""
    _invalid = {
        "outcome": "INVALID",
        "outcome_reason": "Missing required inputs.",
        "tp1_hit": False,
        "tp2_hit": False,
        "stop_hit": False,
        "ambiguous_hit": False,
        "realized_rr": None,
        "edge_eligible": False,
    }

    if s7 is None or not s7.get("available"):
        return _invalid

    decision = str(s7.get("decision", "UNKNOWN"))
    paper_eligible = bool(s7.get("paper_eligible", False))

    if decision != "ALLOW_PAPER" or not paper_eligible:
        return {
            "outcome": "NOT_OPENED",
            "outcome_reason": f"S7 decision={decision}, paper_eligible={paper_eligible} — trade not opened.",
            "tp1_hit": False,
            "tp2_hit": False,
            "stop_hit": False,
            "ambiguous_hit": False,
            "realized_rr": None,
            "edge_eligible": False,
        }

    direction = str(s7.get("trade_direction", "UNKNOWN")).upper()
    entry = s7.get("entry_price")
    stop = s7.get("stop_loss")
    tp1 = s7.get("tp1")
    tp2 = s7.get("tp2")
    rr_tp1 = s7.get("rr_tp1")
    rr_tp2 = s7.get("rr_tp2")

    if entry is None or stop is None or tp1 is None or tp2 is None:
        return {**_invalid, "outcome_reason": "Trade plan fields missing (entry/stop/tp)."}

    if direction not in ("LONG", "SHORT"):
        return {**_invalid, "outcome_reason": f"Unknown trade direction: {direction}."}

    if s1 is None or not s1.get("available"):
        return {**_invalid, "outcome_reason": "S1 official candle unavailable — cannot check outcome."}

    high = s1.get("official_high")
    low = s1.get("official_low")
    if high is None or low is None:
        return {**_invalid, "outcome_reason": "official_high or official_low missing from S1."}

    high = float(high)
    low = float(low)
    edge_from_s7 = bool(s7.get("edge_eligible_if_outcome_closes", False))

    if direction == "LONG":
        tp2_hit = high >= float(tp2)
        tp1_hit = high >= float(tp1)
        stop_hit = low <= float(stop)
    else:  # SHORT
        tp2_hit = low <= float(tp2)
        tp1_hit = low <= float(tp1)
        stop_hit = high >= float(stop)

    ambiguous = (tp1_hit or tp2_hit) and stop_hit

    if ambiguous:
        return {
            "outcome": "AMBIGUOUS",
            "outcome_reason": "Both TP and stop touched in the same candle — outcome ambiguous.",
            "tp1_hit": tp1_hit,
            "tp2_hit": tp2_hit,
            "stop_hit": stop_hit,
            "ambiguous_hit": True,
            "realized_rr": None,
            "edge_eligible": False,
        }

    if tp2_hit:
        return {
            "outcome": "WIN_TP2",
            "outcome_reason": "Official candle hit TP2.",
            "tp1_hit": True,
            "tp2_hit": True,
            "stop_hit": False,
            "ambiguous_hit": False,
            "realized_rr": round(float(rr_tp2), 4) if rr_tp2 is not None else None,
            "edge_eligible": edge_from_s7,
        }

    if tp1_hit:
        return {
            "outcome": "WIN_TP1",
            "outcome_reason": "Official candle hit TP1.",
            "tp1_hit": True,
            "tp2_hit": False,
            "stop_hit": False,
            "ambiguous_hit": False,
            "realized_rr": round(float(rr_tp1), 4) if rr_tp1 is not None else None,
            "edge_eligible": edge_from_s7,
        }

    if stop_hit:
        return {
            "outcome": "LOSS",
            "outcome_reason": "Official candle hit stop loss.",
            "tp1_hit": False,
            "tp2_hit": False,
            "stop_hit": True,
            "ambiguous_hit": False,
            "realized_rr": -1.0,
            "edge_eligible": edge_from_s7,
        }

    return {
        "outcome": "OPEN",
        "outcome_reason": "Neither TP nor stop touched — trade still open.",
        "tp1_hit": False,
        "tp2_hit": False,
        "stop_hit": False,
        "ambiguous_hit": False,
        "realized_rr": None,
        "edge_eligible": False,
    }


def _build_lifecycle(internal_outcome: dict[str, Any]) -> dict[str, Any]:
    o = internal_outcome.get("outcome", "INVALID")
    trade_opened = o not in ("NOT_OPENED", "INVALID")
    if o in ("WIN_TP1", "WIN_TP2", "LOSS", "AMBIGUOUS"):
        trade_status = "CLOSED"
    elif o == "OPEN":
        trade_status = "OPEN"
    elif o == "NOT_OPENED":
        trade_status = "NOT_OPENED"
    else:
        trade_status = "INVALID"
    return {"trade_opened": trade_opened, "trade_status": trade_status}


def _build_edge_eligibility(internal_outcome: dict[str, Any]) -> dict[str, Any]:
    edge_eligible = bool(internal_outcome.get("edge_eligible", False))
    return {"edge_eligible": edge_eligible, "feeds_edge_stats": edge_eligible}


def _build_execution_safety() -> dict[str, Any]:
    return {
        "safe_to_open_real_trade": False,
        "private_api_used": False,
        "live_order_sent": False,
    }


def _build_data_quality(
    input_status: dict[str, Any],
    s1: dict[str, Any] | None,
) -> dict[str, Any]:
    issues = list(input_status["missing_inputs"])
    base = 1.0
    if not input_status["market_truth_available"]:
        issues.append("S1_MISSING")
        base = max(0.0, base - 0.50)
    if not input_status["decision_available"]:
        issues.append("S7_MISSING")
        base = max(0.0, base - 0.50)
    if s1 is not None and s1.get("available") and not s1.get("is_official_binance_1m", True):
        issues.append("NOT_OFFICIAL_BINANCE_1M")
        base = max(0.0, base - 0.30)
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
    internal_outcome: dict[str, Any],
    data_quality: dict[str, Any],
) -> list[str]:
    codes: list[str] = [f"SOURCE_{source_mode}"]
    for m in input_status["missing_inputs"]:
        codes.append(f"MISSING_{m}")
    codes.append(f"OUTCOME_{internal_outcome['outcome']}")
    codes.append(f"EDGE_ELIGIBLE_{str(internal_outcome['edge_eligible']).upper()}")
    codes.append("CHECK_METHOD_OFFICIAL_CANDLE_HIGH_LOW")
    codes.append("SAFE_TO_OPEN_REAL_TRADE_FALSE")
    codes.append(f"DATA_QUALITY_{data_quality['level']}")
    return codes


def build_paper_outcome(
    symbol: str,
    s1: dict[str, Any] | None,
    s7: dict[str, Any] | None,
    source_mode: str,
) -> dict[str, Any]:
    input_status = _calc_input_status(s1, s7)
    outcome_check = _calc_outcome_check(s1)
    decision_reference = _calc_decision_reference(s7)
    internal_outcome = _calc_outcome(s1, s7)

    result = {k: v for k, v in internal_outcome.items() if k != "edge_eligible"}
    lifecycle = _build_lifecycle(internal_outcome)
    edge_eligibility = _build_edge_eligibility(internal_outcome)
    safety = _build_execution_safety()
    data_quality = _build_data_quality(input_status, s1)
    reason_codes = _build_reason_codes(source_mode, input_status, internal_outcome, data_quality)

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": source_mode,
            "reason_codes": [f"SOURCE_{source_mode}"],
        },
        "input_status": input_status,
        "decision_reference": decision_reference,
        "outcome_check": outcome_check,
        "lifecycle": lifecycle,
        "result": result,
        "edge_eligibility": edge_eligibility,
        "execution_safety": safety,
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
    }


def run_fake_sample(symbol: str) -> dict[str, Any]:
    return build_paper_outcome(symbol, _FAKE_S1, _FAKE_S7, "FAKE_SAMPLE")
