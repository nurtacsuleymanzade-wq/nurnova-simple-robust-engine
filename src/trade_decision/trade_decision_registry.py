from __future__ import annotations

TRADE_DECISION_BLOCK_ID = "PHASE_6_TRADE_PLAN_DECISION_GATE"

SIDES = ("LONG", "SHORT", "NO_TRADE", "UNKNOWN")

ENTRY_MODELS = (
    "RETEST",
    "BREAKOUT",
    "RECLAIM",
    "REJECTION",
    "CONTINUATION",
    "NO_ENTRY",
    "UNKNOWN",
)

RISK_GRADES = ("LOW", "MEDIUM", "HIGH", "NO_TRADE", "UNKNOWN")

DECISION_STATUSES = ("ALLOW_PAPER", "WAIT", "BLOCK", "NO_TRADE", "UNKNOWN")

PLAN_QUALITY = ("A", "B", "C", "INVALID", "UNKNOWN")

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_7_PAPER_LIFECYCLE_OUTCOME_TRUTH",
    "PHASE_8_CONDITIONAL_EDGE_MATRIX",
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "trade_plan_id",
    "decision_id",
    "lineage_id",
    "parent_lineage_ids",
    "setup_candidate_id",
    "entry_trigger_id",
    "market_state_id",
    "active_scenario_id",
    "flow_reaction_id",
    "side",
    "entry_model",
    "entry_price",
    "stop_loss",
    "take_profit_1",
    "take_profit_2",
    "invalidation_level",
    "rr_to_tp1",
    "rr_to_tp2",
    "risk_grade",
    "decision_status",
    "decision_confidence",
    "plan_quality",
    "position_policy",
    "entry_reason_codes",
    "sl_reason_codes",
    "tp_reason_codes",
    "invalidation_reason_codes",
    "blocking_reason_codes",
    "risk_reason_codes",
    "evidence",
    "scores",
    "data_quality",
    "feeds_next",
    "reason_codes",
    "warnings",
]

# Minimum RR thresholds — TP price comes from liquidity destination, not from these values.
RR_MIN_SCALP = 1.2
RR_MIN_NORMAL = 1.5
RR_MIN_A_QUALITY = 1.8

# template_risk_score threshold above which BLOCK is triggered
TEMPLATE_RISK_BLOCK_THRESHOLD = 0.5
