from __future__ import annotations

ACTIVE_SCENARIO_BLOCK_ID = "PHASE_3_ACTIVE_SCENARIO_ENGINE"

ACTIVE_SCENARIOS = (
    "BULLISH_CONTINUATION",
    "BEARISH_CONTINUATION",
    "BULLISH_REVERSAL",
    "BEARISH_REVERSAL",
    "RANGE_ROTATION_UP",
    "RANGE_ROTATION_DOWN",
    "COMPRESSION_BREAKOUT_UP",
    "COMPRESSION_BREAKOUT_DOWN",
    "LIQUIDITY_SWEEP_REVERSAL_LONG",
    "LIQUIDITY_SWEEP_REVERSAL_SHORT",
    "LIQUIDITY_GRAB_CONTINUATION_LONG",
    "LIQUIDITY_GRAB_CONTINUATION_SHORT",
    "BUYERS_TRAPPED_CONTINUATION_SHORT",
    "SELLERS_TRAPPED_CONTINUATION_LONG",
    "POST_SWEEP_RECLAIM_LONG",
    "POST_SWEEP_REJECTION_SHORT",
    "NO_ACTIVE_SCENARIO",
    "CONFLICTED_SCENARIO",
    "UNKNOWN",
)

SCENARIO_BIASES = (
    "LONG",
    "SHORT",
    "NEUTRAL",
    "NO_TRADE",
    "UNKNOWN",
)

SCENARIO_QUALITY = (
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
    "PHASE_4_FLOW_CONFIRMATION_POST_LIQUIDITY_REACTION",
    "PHASE_5_SETUP_CANDIDATE_ENTRY_TRIGGER",
    "PHASE_8_CONDITIONAL_EDGE_MATRIX",
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "active_scenario_id",
    "lineage_id",
    "parent_lineage_ids",
    "market_state_id",
    "active_scenario",
    "scenario_bias",
    "scenario_confidence",
    "scenario_quality",
    "selection_reason_codes",
    "rejection_reason_codes",
    "conflict_reason_codes",
    "scenario_candidates",
    "selected_candidate",
    "evidence",
    "candidate_scores",
    "data_quality",
    "feeds_next",
    "reason_codes",
    "warnings",
]

