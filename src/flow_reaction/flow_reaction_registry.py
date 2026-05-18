from __future__ import annotations

FLOW_REACTION_BLOCK_ID = "PHASE_4_FLOW_CONFIRMATION_POST_LIQUIDITY_REACTION"

FLOW_CONFIRMATIONS = (
    "CONFIRMED_LONG",
    "CONFIRMED_SHORT",
    "NOT_CONFIRMED",
    "CONFLICTED",
    "UNKNOWN",
)

POST_LIQUIDITY_REACTIONS = (
    "CONTINUATION_AFTER_SWEEP",
    "REVERSAL_AFTER_SWEEP",
    "REJECTION_AFTER_SWEEP",
    "RECLAIM_AFTER_SWEEP",
    "ABSORPTION_DETECTED",
    "BUYERS_TRAPPED",
    "SELLERS_TRAPPED",
    "FAILED_BREAKOUT",
    "REAL_BREAKOUT",
    "NO_LIQUIDITY_EVENT",
    "INSUFFICIENT_EVIDENCE",
    "UNKNOWN",
)

ABSORPTION_STATES = (
    "BUY_ABSORPTION",
    "SELL_ABSORPTION",
    "BOTH",
    "NONE",
    "UNKNOWN",
)

TRAP_STATES = (
    "BUYERS_TRAPPED",
    "SELLERS_TRAPPED",
    "NONE",
    "UNKNOWN",
)

REACTION_BIASES = (
    "LONG",
    "SHORT",
    "NEUTRAL",
    "NO_TRADE",
    "UNKNOWN",
)

REACTION_QUALITY = (
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
    "PHASE_5_SETUP_CANDIDATE_ENTRY_TRIGGER",
    "PHASE_8_CONDITIONAL_EDGE_MATRIX",
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "flow_reaction_id",
    "lineage_id",
    "parent_lineage_ids",
    "market_state_id",
    "active_scenario_id",
    "flow_confirmation",
    "post_liquidity_reaction",
    "absorption_state",
    "trap_state",
    "reaction_bias",
    "reaction_confidence",
    "reaction_quality",
    "evidence",
    "scores",
    "confirmation_reason_codes",
    "rejection_reason_codes",
    "trap_reason_codes",
    "absorption_reason_codes",
    "conflict_reason_codes",
    "data_quality",
    "feeds_next",
    "reason_codes",
    "warnings",
]
