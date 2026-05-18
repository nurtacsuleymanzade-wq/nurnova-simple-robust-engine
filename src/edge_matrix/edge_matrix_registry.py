from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


EDGE_MATRIX_BLOCK_ID = "PHASE_8_CONDITIONAL_EDGE_MATRIX"

EDGE_STATUSES = (
    "NO_DATA",
    "INSUFFICIENT_SAMPLE",
    "NEGATIVE_EDGE",
    "NEUTRAL_EDGE",
    "WATCHLIST_EDGE",
    "TRADEABLE_EDGE_CANDIDATE",
    "STRONG_EDGE_CANDIDATE",
    "DEGRADED_BY_DATA_QUALITY",
    "INVALID",
)

GROUPING_FIELDS = (
    "pattern",
    "market_regime",
    "trend_state",
    "volatility_state",
    "liquidity_state",
    "active_scenario",
    "flow_confirmation",
    "post_liquidity_reaction",
    "trap_state",
    "absorption_state",
    "setup_candidate",
    "setup_direction",
    "entry_trigger_status",
    "side",
    "entry_model",
    "risk_grade",
    "plan_quality",
)

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
    "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
]

ELIGIBLE_TRADE_FATES = {
    "TP1_HIT",
    "TP2_HIT",
    "SL_HIT",
    "PARTIAL_WIN",
    "PARTIAL_LOSS",
    "BREAKEVEN",
    "INVALIDATED_AFTER_ENTRY",
}

EXCLUDED_TOKENS = {
    "TIMEOUT",
    "DIAGNOSTIC_TIMEOUT",
    "NO_ENTRY_TOUCH",
    "EXPIRED_NO_ENTRY",
    "OPEN",
    "ACTIVE",
    "PENDING",
    "UNKNOWN",
}

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "edge_matrix_id",
    "lineage_id",
    "source_outcome_count",
    "edge_eligible_outcome_count",
    "excluded_outcome_count",
    "excluded_breakdown",
    "conditional_edge_rows",
    "top_positive_edges",
    "top_negative_edges",
    "failure_patterns",
    "high_probability_clusters",
    "data_quality",
    "reason_codes",
    "feeds_next",
    "warnings",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest().upper()


def build_edge_matrix_id(symbol: str, source_outcome_ids: list[str]) -> str:
    basis = {
        "symbol": str(symbol or "UNKNOWN"),
        "source_outcome_ids": sorted(str(item) for item in source_outcome_ids if str(item)),
    }
    return f"EDM_{stable_sha256(basis)[:24]}"


def build_edge_row_id(group_key: dict[str, Any], source_outcome_ids: list[str]) -> str:
    basis = {
        "group_key": group_key,
        "source_outcome_ids": sorted(str(item) for item in source_outcome_ids if str(item)),
    }
    return f"EDR_{stable_sha256(basis)[:24]}"


def build_lineage_id(label: str, *parts: Any) -> str:
    basis = {"label": label, "parts": [str(part or "") for part in parts]}
    return f"LIN_{stable_sha256(basis)[:24]}"
