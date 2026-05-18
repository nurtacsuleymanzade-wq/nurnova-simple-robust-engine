from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


PAPER_OUTCOME_BLOCK_ID = "PHASE_7_PAPER_LIFECYCLE_OUTCOME_TRUTH"

LIFECYCLE_STATES = (
    "CREATED",
    "WAITING_ENTRY",
    "ENTRY_FILLED",
    "CLOSED",
    "INVALIDATED",
    "EXPIRED",
    "UNKNOWN",
)

TRADE_FATES = (
    "NO_ACTIONABLE_DECISION",
    "NO_OPEN_PAPER_TRADE",
    "NO_ENTRY_TOUCH",
    "ENTRY_FILLED",
    "TP1_HIT",
    "TP2_HIT",
    "SL_HIT",
    "INVALIDATED_BEFORE_ENTRY",
    "INVALIDATED_AFTER_ENTRY",
    "PARTIAL_WIN",
    "PARTIAL_LOSS",
    "BREAKEVEN",
    "EXPIRED_NO_ENTRY",
    "DIAGNOSTIC_TIMEOUT",
    "UNKNOWN",
)

OUTCOME_QUALITY = (
    "HIGH",
    "MEDIUM",
    "LOW",
    "INVALID",
    "UNKNOWN",
)

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

SIDES = ("LONG", "SHORT", "NO_TRADE", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_8_CONDITIONAL_EDGE_MATRIX",
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
]

CLOSED_EDGE_ELIGIBLE_FATES = {
    "TP1_HIT",
    "TP2_HIT",
    "SL_HIT",
    "PARTIAL_WIN",
    "PARTIAL_LOSS",
    "BREAKEVEN",
    "INVALIDATED_AFTER_ENTRY",
}

NON_EDGE_FATES = {
    "NO_ACTIONABLE_DECISION",
    "NO_OPEN_PAPER_TRADE",
    "NO_ENTRY_TOUCH",
    "EXPIRED_NO_ENTRY",
    "DIAGNOSTIC_TIMEOUT",
    "INVALIDATED_BEFORE_ENTRY",
    "UNKNOWN",
}

FORBIDDEN_OUTPUT_FIELDS = {
    "real_trade_allowed",
    "safe_to_open_real_trade",
    "private_api_used",
    "live_order_sent",
    "execution_safety",
    "position_policy",
}

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "paper_trade_id",
    "outcome_id",
    "lineage_id",
    "parent_lineage_ids",
    "trade_plan_id",
    "decision_id",
    "setup_candidate_id",
    "entry_trigger_id",
    "side",
    "lifecycle_state",
    "trade_fate",
    "is_closed_outcome",
    "edge_eligible",
    "entry_price",
    "stop_loss",
    "take_profit_1",
    "take_profit_2",
    "invalidation_level",
    "entry_touched",
    "tp1_touched",
    "tp2_touched",
    "sl_touched",
    "invalidation_touched",
    "opened_at",
    "closed_at",
    "close_reason",
    "r_multiple",
    "outcome_quality",
    "evidence",
    "data_quality",
    "feeds_next",
    "reason_codes",
    "warnings",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest().upper()


def build_paper_trade_id(
    *,
    symbol: str,
    trade_plan_id: Any,
    decision_id: Any,
    entry_price: Any,
    stop_loss: Any,
    take_profit_1: Any,
    side: Any,
) -> str:
    basis = {
        "symbol": str(symbol or "UNKNOWN"),
        "trade_plan_id": str(trade_plan_id or ""),
        "decision_id": str(decision_id or ""),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "side": str(side or "UNKNOWN"),
    }
    return f"PPR_{stable_sha256(basis)[:24]}"


def build_outcome_id(
    *,
    paper_trade_id: Any,
    trade_fate: Any,
    closed_at: Any,
    evidence_seed: Any,
) -> str:
    basis = {
        "paper_trade_id": str(paper_trade_id or ""),
        "trade_fate": str(trade_fate or "UNKNOWN"),
        "closed_at": str(closed_at or ""),
        "evidence_seed": evidence_seed,
    }
    return f"OUT_{stable_sha256(basis)[:24]}"


def build_lineage_id(label: str, *parts: Any) -> str:
    basis = {"label": label, "parts": [str(part or "") for part in parts]}
    return f"LIN_{stable_sha256(basis)[:24]}"
