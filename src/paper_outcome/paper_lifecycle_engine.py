from __future__ import annotations

from typing import Any

from .paper_outcome_registry import (
    DATA_QUALITY,
    DEFAULT_FEEDS_NEXT,
    PAPER_OUTCOME_BLOCK_ID,
    build_paper_trade_id,
)


def _clean_reason_codes(reason_codes: list[str]) -> list[str]:
    return list(dict.fromkeys(code for code in reason_codes if code))


def build_paper_lifecycle(
    trade_decision: dict[str, Any] | None,
    *,
    timestamp_utc: str,
) -> dict[str, Any]:
    decision = trade_decision or {}
    symbol = str(decision.get("symbol") or "BTCUSDT")
    side = str(decision.get("side") or "UNKNOWN").upper()
    decision_status = str(decision.get("decision_status") or "UNKNOWN").upper()
    trade_plan_id = decision.get("trade_plan_id")
    decision_id = decision.get("decision_id")
    entry_price = decision.get("entry_price")
    stop_loss = decision.get("stop_loss")
    take_profit_1 = decision.get("take_profit_1")
    take_profit_2 = decision.get("take_profit_2")
    invalidation_level = decision.get("invalidation_level")

    paper_trade_id = build_paper_trade_id(
        symbol=symbol,
        trade_plan_id=trade_plan_id,
        decision_id=decision_id,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        side=side,
    )

    reason_codes: list[str] = []
    warnings: list[str] = []

    if trade_decision is None:
        reason_codes.append("TRADE_DECISION_MISSING")

    if not trade_plan_id:
        reason_codes.append("MISSING_TRADE_PLAN_ID")
    if not decision_id:
        reason_codes.append("MISSING_DECISION_ID")

    if decision_status != "ALLOW_PAPER":
        reason_codes.append(f"DECISION_STATUS_{decision_status}")
        reason_codes.append("PAPER_TRADE_NOT_STARTED")
        return {
            "timestamp_utc": timestamp_utc,
            "block_id": PAPER_OUTCOME_BLOCK_ID,
            "symbol": symbol,
            "paper_trade_id": paper_trade_id,
            "trade_plan_id": trade_plan_id,
            "decision_id": decision_id,
            "setup_candidate_id": decision.get("setup_candidate_id"),
            "entry_trigger_id": decision.get("entry_trigger_id"),
            "side": side if side in ("LONG", "SHORT", "NO_TRADE") else "UNKNOWN",
            "lifecycle_state": "UNKNOWN",
            "trade_fate": "UNKNOWN",
            "is_closed_outcome": False,
            "edge_eligible": False,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "invalidation_level": invalidation_level,
            "entry_touched": False,
            "tp1_touched": False,
            "tp2_touched": False,
            "sl_touched": False,
            "invalidation_touched": False,
            "opened_at": None,
            "closed_at": None,
            "close_reason": "DECISION_NOT_ALLOW_PAPER",
            "r_multiple": None,
            "outcome_quality": "LOW",
            "evidence": {
                "trade_decision_evidence": {},
                "price_path_evidence": {},
                "entry_evidence": {},
                "tp_evidence": {},
                "sl_evidence": {},
                "invalidation_evidence": {},
            },
            "data_quality": "ACCEPTABLE",
            "feeds_next": list(DEFAULT_FEEDS_NEXT),
            "reason_codes": _clean_reason_codes(reason_codes),
            "warnings": warnings,
            "_decision_timestamp_utc": decision.get("timestamp_utc"),
            "_decision_status": decision_status,
            "_decision_lineage_id": decision.get("lineage_id"),
            "_allow_paper": False,
            "_core_prices_present": False,
        }

    missing_core = []
    for key, value in (
        ("ENTRY_PRICE", entry_price),
        ("STOP_LOSS", stop_loss),
        ("TAKE_PROFIT_1", take_profit_1),
        ("INVALIDATION_LEVEL", invalidation_level),
    ):
        if value is None:
            missing_core.append(key)
            reason_codes.append(f"ALLOW_PAPER_MISSING_{key}")

    if side not in ("LONG", "SHORT"):
        reason_codes.append("ALLOW_PAPER_INVALID_SIDE")
        missing_core.append("SIDE")

    if missing_core:
        return {
            "timestamp_utc": timestamp_utc,
            "block_id": PAPER_OUTCOME_BLOCK_ID,
            "symbol": symbol,
            "paper_trade_id": paper_trade_id,
            "trade_plan_id": trade_plan_id,
            "decision_id": decision_id,
            "setup_candidate_id": decision.get("setup_candidate_id"),
            "entry_trigger_id": decision.get("entry_trigger_id"),
            "side": side if side in ("LONG", "SHORT", "NO_TRADE") else "UNKNOWN",
            "lifecycle_state": "UNKNOWN",
            "trade_fate": "UNKNOWN",
            "is_closed_outcome": False,
            "edge_eligible": False,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "invalidation_level": invalidation_level,
            "entry_touched": False,
            "tp1_touched": False,
            "tp2_touched": False,
            "sl_touched": False,
            "invalidation_touched": False,
            "opened_at": None,
            "closed_at": None,
            "close_reason": "ALLOW_PAPER_INPUT_INCOMPLETE",
            "r_multiple": None,
            "outcome_quality": "INVALID",
            "evidence": {
                "trade_decision_evidence": {},
                "price_path_evidence": {},
                "entry_evidence": {},
                "tp_evidence": {},
                "sl_evidence": {},
                "invalidation_evidence": {},
            },
            "data_quality": "INVALID",
            "feeds_next": list(DEFAULT_FEEDS_NEXT),
            "reason_codes": _clean_reason_codes(reason_codes),
            "warnings": warnings,
            "_decision_timestamp_utc": decision.get("timestamp_utc"),
            "_decision_status": decision_status,
            "_decision_lineage_id": decision.get("lineage_id"),
            "_allow_paper": False,
            "_core_prices_present": False,
        }

    reason_codes.append("ALLOW_PAPER_LIFECYCLE_CREATED")
    if take_profit_2 is None:
        warnings.append("take_profit_2 missing; TP1 is treated as terminal target")

    return {
        "timestamp_utc": timestamp_utc,
        "block_id": PAPER_OUTCOME_BLOCK_ID,
        "symbol": symbol,
        "paper_trade_id": paper_trade_id,
        "trade_plan_id": trade_plan_id,
        "decision_id": decision_id,
        "setup_candidate_id": decision.get("setup_candidate_id"),
        "entry_trigger_id": decision.get("entry_trigger_id"),
        "side": side,
        "lifecycle_state": "WAITING_ENTRY",
        "trade_fate": "NO_ENTRY_TOUCH",
        "is_closed_outcome": False,
        "edge_eligible": False,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "invalidation_level": invalidation_level,
        "entry_touched": False,
        "tp1_touched": False,
        "tp2_touched": False,
        "sl_touched": False,
        "invalidation_touched": False,
        "opened_at": None,
        "closed_at": None,
        "close_reason": None,
        "r_multiple": None,
        "outcome_quality": "MEDIUM",
        "evidence": {
            "trade_decision_evidence": {},
            "price_path_evidence": {},
            "entry_evidence": {},
            "tp_evidence": {},
            "sl_evidence": {},
            "invalidation_evidence": {},
        },
        "data_quality": "OK",
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "reason_codes": _clean_reason_codes(reason_codes),
        "warnings": warnings,
        "_decision_timestamp_utc": decision.get("timestamp_utc"),
        "_decision_status": decision_status,
        "_decision_lineage_id": decision.get("lineage_id"),
        "_allow_paper": True,
        "_core_prices_present": True,
    }
