from __future__ import annotations

SETUP_ENTRY_BLOCK_ID = "PHASE_5_SETUP_CANDIDATE_ENTRY_TRIGGER"

SETUP_CANDIDATES = (
    "LONG_CONTINUATION_SETUP",
    "SHORT_CONTINUATION_SETUP",
    "LONG_REVERSAL_SETUP",
    "SHORT_REVERSAL_SETUP",
    "RANGE_LONG_SETUP",
    "RANGE_SHORT_SETUP",
    "COMPRESSION_BREAKOUT_LONG_SETUP",
    "COMPRESSION_BREAKOUT_SHORT_SETUP",
    "BUYERS_TRAPPED_SHORT_SETUP",
    "SELLERS_TRAPPED_LONG_SETUP",
    "POST_SWEEP_RECLAIM_LONG_SETUP",
    "POST_SWEEP_REJECTION_SHORT_SETUP",
    "NO_SETUP",
    "CONFLICTED_SETUP",
    "UNKNOWN",
)

SETUP_DIRECTIONS = (
    "LONG",
    "SHORT",
    "NEUTRAL",
    "NO_TRADE",
    "UNKNOWN",
)

SETUP_QUALITY = (
    "A",
    "B",
    "C",
    "INVALID",
    "UNKNOWN",
)

ENTRY_TRIGGER_STATUSES = (
    "TRIGGER_READY",
    "TRIGGER_NEAR",
    "TRIGGER_WAIT",
    "TRIGGER_INVALID",
    "TRIGGER_CONFLICTED",
    "TRIGGER_UNKNOWN",
)

ENTRY_TRIGGER_QUALITY = (
    "HIGH",
    "MEDIUM",
    "LOW",
    "INVALID",
    "UNKNOWN",
)

DATA_QUALITY = (
    "OK",
    "ACCEPTABLE",
    "DEGRADED",
    "INVALID",
    "UNKNOWN",
)

DEFAULT_FEEDS_NEXT = [
    "PHASE_6_TRADE_PLAN_DECISION_GATE",
    "PHASE_8_CONDITIONAL_EDGE_MATRIX",
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "setup_candidate_id",
    "entry_trigger_id",
    "lineage_id",
    "parent_lineage_ids",
    "market_state_id",
    "active_scenario_id",
    "flow_reaction_id",
    "setup_candidate",
    "setup_direction",
    "setup_quality",
    "setup_confidence",
    "entry_trigger_status",
    "entry_trigger_quality",
    "entry_trigger_confidence",
    "timeframe_context",
    "evidence",
    "scores",
    "setup_reason_codes",
    "entry_trigger_reason_codes",
    "blocking_reason_codes",
    "conflict_reason_codes",
    "missing_evidence",
    "data_quality",
    "feeds_next",
    "reason_codes",
    "warnings",
]
