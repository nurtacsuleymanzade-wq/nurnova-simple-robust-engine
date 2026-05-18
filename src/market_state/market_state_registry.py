from __future__ import annotations

MARKET_STATE_BLOCK_ID = "PHASE_2_MARKET_STATE_ENGINE"

MARKET_REGIMES = (
    "UPTREND",
    "DOWNTREND",
    "RANGE",
    "COMPRESSION",
    "EXPANSION",
    "REVERSAL_RISK",
    "LIQUIDITY_HUNT",
    "POST_SWEEP_REACTION",
    "UNKNOWN",
)

TREND_STATES = (
    "BULLISH",
    "BEARISH",
    "NEUTRAL",
    "MIXED",
    "UNKNOWN",
)

VOLATILITY_STATES = (
    "LOW",
    "NORMAL",
    "HIGH",
    "EXPANDING",
    "COMPRESSING",
    "UNKNOWN",
)

STRUCTURE_STATES = (
    "HH_HL",
    "LH_LL",
    "RANGE_BOUND",
    "BROKEN_STRUCTURE",
    "UNKNOWN",
)

LIQUIDITY_PRESSURE_STATES = (
    "ABOVE",
    "BELOW",
    "BOTH",
    "NONE",
    "UNKNOWN",
)

AUCTION_STATES = (
    "ACCEPTANCE",
    "REJECTION",
    "DISCOVERY",
    "BALANCE",
    "UNKNOWN",
)

FLOW_STATES = (
    "BUY_PRESSURE",
    "SELL_PRESSURE",
    "BALANCED",
    "DIVERGENT",
    "UNKNOWN",
)

MATURITY_STATES = (
    "EARLY",
    "MID",
    "LATE",
    "EXHAUSTED",
    "UNKNOWN",
)

RISK_STATES = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "NO_TRADE",
    "UNKNOWN",
)

DATA_QUALITY_STATES = (
    "OK",
    "ACCEPTABLE",
    "DEGRADED",
    "INVALID",
    "UNKNOWN",
)

DEFAULT_FEEDS_NEXT = [
    "PHASE_3_ACTIVE_SCENARIO_ENGINE",
    "PHASE_8_CONDITIONAL_EDGE_MATRIX",
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "market_state_id",
    "lineage_id",
    "parent_lineage_ids",
    "market_regime",
    "trend_state",
    "volatility_state",
    "structure_state",
    "liquidity_pressure_state",
    "auction_state",
    "flow_state",
    "maturity_state",
    "risk_state",
    "confidence",
    "confidence_components",
    "evidence",
    "reason_codes",
    "warnings",
    "data_quality",
    "feeds_next",
]

