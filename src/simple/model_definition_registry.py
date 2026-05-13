"""Full ENOVA model definition registry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MODEL_DEFINITION_REGISTRY"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_model_definitions.json"
HISTORY_PATH = DATA_DIR / "model_definitions_history.jsonl"

QUALITY_RULES = {
    "LOW": "score >= 0.30",
    "MEDIUM": "score >= 0.50",
    "HIGH": "score >= 0.70",
    "A_PLUS": "score >= 0.85",
}

DEFAULT_REQUIRED_INPUTS = [
    "latest_observation_factory",
    "latest_mtf_candle_dna",
    "latest_market_structure",
    "latest_liquidity_map",
    "latest_interpretation",
    "latest_three_scenarios",
    "latest_business_zone",
    "latest_market_regime",
    "latest_intent_analysis",
    "latest_positioning_context",
    "latest_unified_context",
    "latest_atr_state",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _timeframe_behavior(direction: str, family: str) -> dict[str, str]:
    bias_text = "upside" if direction == "LONG" else "downside" if direction == "SHORT" else "neutral"
    return {
        "1s": f"Micro aggression and defense confirm {bias_text} initiation.",
        "1m": f"Primary research trigger for {family.lower()} context.",
        "5m": f"Short-term structure and confirmation layer for {bias_text} continuation or failure.",
        "15m": f"Context filter for whether the model is leaving, rotating within, or returning to value.",
        "1h": "Higher-timeframe context only; not required for paper trade activation.",
    }


def _make_model(
    model_id: str,
    model_family: str,
    direction: str,
    core: list[str],
    confirmation: list[str],
    optional: list[str],
    invalidation: list[str],
    opens_paper_trade: bool = True,
) -> dict[str, Any]:
    purpose = f"Research model for {model_family.lower().replace('_', ' ')} behavior."
    if model_family == "NO_TRADE":
        purpose = "Research logging model for conditions that should not open paper trades."
    market_logic = (
        f"{model_id} tracks repeatable {model_family.lower().replace('_', ' ')} behavior and logs condition alignment "
        "without sending live orders."
    )
    return {
        "model_id": model_id,
        "model_family": model_family,
        "direction": direction,
        "purpose": purpose,
        "market_logic": market_logic,
        "required_inputs": list(DEFAULT_REQUIRED_INPUTS),
        "condition_groups": {
            "core": core,
            "confirmation": confirmation,
            "optional": optional,
            "invalidation": invalidation,
        },
        "condition_weights": {
            "core": 0.50,
            "confirmation": 0.30,
            "optional": 0.20,
            "invalidation_penalty": 0.25,
        },
        "entry_logic": "Enter at current observed price for paper research when the model instance is emitted.",
        "stop_logic": "Use paper trade factory ATR-based or fallback risk distance only.",
        "target_logic": "Use paper trade factory fixed R targets and optional liquidity reference.",
        "timeframe_behavior": _timeframe_behavior(direction, model_family),
        "quality_rules": dict(QUALITY_RULES),
        "is_research_model": True,
        "opens_paper_trade": opens_paper_trade,
    }


MODEL_SPECS: list[dict[str, Any]] = [
    {"id": "LSR_LONG", "family": "LIQUIDITY_SWEEP_REVERSAL", "direction": "LONG", "core": ["COND_LIQUIDITY_SWEEP_DOWN", "COND_SELLERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE"], "confirmation": ["COND_BUYERS_DEFENDING", "COND_TRAPPED_SELLERS", "COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH", "COND_BULLISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_STRUCTURE_BEARISH"]},
    {"id": "LSR_SHORT", "family": "LIQUIDITY_SWEEP_REVERSAL", "direction": "SHORT", "core": ["COND_LIQUIDITY_SWEEP_UP", "COND_BUYERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE"], "confirmation": ["COND_SELLERS_DEFENDING", "COND_TRAPPED_BUYERS", "COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH", "COND_BEARISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_STRUCTURE_BULLISH"]},
    {"id": "AR01_LONG", "family": "ABSORPTION_REVERSAL", "direction": "LONG", "core": ["COND_SELLERS_ATTACKING", "COND_BUYERS_DEFENDING", "COND_PRICE_FAILED_TO_ADVANCE"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH", "COND_ABSORPTION_INTENT"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "AR01_SHORT", "family": "ABSORPTION_REVERSAL", "direction": "SHORT", "core": ["COND_BUYERS_ATTACKING", "COND_SELLERS_DEFENDING", "COND_PRICE_FAILED_TO_ADVANCE"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH", "COND_ABSORPTION_INTENT"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "AR02_LONG", "family": "EXHAUSTION_REVERSAL", "direction": "LONG", "core": ["COND_SELLERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_FAKE_BEARISH"], "confirmation": ["COND_BUYERS_DEFENDING", "COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "AR02_SHORT", "family": "EXHAUSTION_REVERSAL", "direction": "SHORT", "core": ["COND_BUYERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_FAKE_BULLISH"], "confirmation": ["COND_SELLERS_DEFENDING", "COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "FCR_LONG", "family": "FAILED_CONTINUATION_REVERSAL", "direction": "LONG", "core": ["COND_REAL_BEARISH", "COND_PRICE_FAILED_TO_ADVANCE", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_CHOCH_OR_MSS", "COND_BULLISH_SCENARIO_AVAILABLE"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_STRUCTURE_BEARISH"]},
    {"id": "FCR_SHORT", "family": "FAILED_CONTINUATION_REVERSAL", "direction": "SHORT", "core": ["COND_REAL_BULLISH", "COND_PRICE_FAILED_TO_ADVANCE", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_CHOCH_OR_MSS", "COND_BEARISH_SCENARIO_AVAILABLE"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_STRUCTURE_BULLISH"]},
    {"id": "DAF_LONG", "family": "DELTA_ABSORPTION_FAILURE", "direction": "LONG", "core": ["COND_NEGATIVE_DELTA", "COND_PRICE_FAILED_TO_ADVANCE", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "optional": ["COND_TRAPPED_SELLERS"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "DAF_SHORT", "family": "DELTA_ABSORPTION_FAILURE", "direction": "SHORT", "core": ["COND_POSITIVE_DELTA", "COND_PRICE_FAILED_TO_ADVANCE", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "optional": ["COND_TRAPPED_BUYERS"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "PLR_LONG", "family": "POST_LIQUIDITY_REACTION", "direction": "LONG", "core": ["COND_LIQUIDITY_SWEEP_DOWN", "COND_BUYERS_DEFENDING", "COND_BULLISH_SCENARIO_AVAILABLE"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE", "COND_REGIME_TRANSITION"], "optional": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "PLR_SHORT", "family": "POST_LIQUIDITY_REACTION", "direction": "SHORT", "core": ["COND_LIQUIDITY_SWEEP_UP", "COND_SELLERS_DEFENDING", "COND_BEARISH_SCENARIO_AVAILABLE"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW", "COND_REGIME_TRANSITION"], "optional": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "TRAP_BUYERS_SHORT", "family": "TRAP_REVERSAL", "direction": "SHORT", "core": ["COND_TRAPPED_BUYERS", "COND_FAKE_BULLISH", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_LIQUIDITY_SWEEP_UP", "COND_BEARISH_SCENARIO_AVAILABLE"], "optional": ["COND_ABOVE_VALUE"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "TRAP_SELLERS_LONG", "family": "TRAP_REVERSAL", "direction": "LONG", "core": ["COND_TRAPPED_SELLERS", "COND_FAKE_BEARISH", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_LIQUIDITY_SWEEP_DOWN", "COND_BULLISH_SCENARIO_AVAILABLE"], "optional": ["COND_BELOW_VALUE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "IB01_LONG", "family": "INITIATIVE_BREAKOUT", "direction": "LONG", "core": ["COND_REGIME_MOMENTUM", "COND_BUYERS_ATTACKING", "COND_STRUCTURE_BULLISH"], "confirmation": ["COND_ACCEPTANCE", "COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_ATR_EXPANDING"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "IB01_SHORT", "family": "INITIATIVE_BREAKOUT", "direction": "SHORT", "core": ["COND_REGIME_MOMENTUM", "COND_SELLERS_ATTACKING", "COND_STRUCTURE_BEARISH"], "confirmation": ["COND_ACCEPTANCE", "COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_ATR_EXPANDING"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "ACCEPTANCE_BREAKOUT_LONG", "family": "ACCEPTANCE_BREAKOUT", "direction": "LONG", "core": ["COND_ABOVE_VALUE", "COND_ACCEPTANCE", "COND_BUYERS_ATTACKING"], "confirmation": ["COND_STRUCTURE_BULLISH", "COND_BULLISH_SCENARIO_AVAILABLE"], "optional": ["COND_ATR_AVAILABLE"], "invalidation": ["COND_REJECTION"]},
    {"id": "ACCEPTANCE_BREAKOUT_SHORT", "family": "ACCEPTANCE_BREAKOUT", "direction": "SHORT", "core": ["COND_BELOW_VALUE", "COND_ACCEPTANCE", "COND_SELLERS_ATTACKING"], "confirmation": ["COND_STRUCTURE_BEARISH", "COND_BEARISH_SCENARIO_AVAILABLE"], "optional": ["COND_ATR_AVAILABLE"], "invalidation": ["COND_REJECTION"]},
    {"id": "FAILED_BREAKOUT_TRAP_LONG", "family": "FAILED_BREAKOUT_TRAP", "direction": "LONG", "core": ["COND_BELOW_VALUE", "COND_REJECTION", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_FAKE_BEARISH", "COND_TRAPPED_SELLERS"], "optional": ["COND_BULLISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "FAILED_BREAKOUT_TRAP_SHORT", "family": "FAILED_BREAKOUT_TRAP", "direction": "SHORT", "core": ["COND_ABOVE_VALUE", "COND_REJECTION", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_FAKE_BULLISH", "COND_TRAPPED_BUYERS"], "optional": ["COND_BEARISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "FAILED_AUCTION_RETURN_LONG", "family": "FAILED_AUCTION_RETURN", "direction": "LONG", "core": ["COND_BELOW_VALUE", "COND_REJECTION", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_INSIDE_VALUE", "COND_BULLISH_SCENARIO_AVAILABLE"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_ACCEPTANCE"]},
    {"id": "FAILED_AUCTION_RETURN_SHORT", "family": "FAILED_AUCTION_RETURN", "direction": "SHORT", "core": ["COND_ABOVE_VALUE", "COND_REJECTION", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_INSIDE_VALUE", "COND_BEARISH_SCENARIO_AVAILABLE"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_ACCEPTANCE"]},
    {"id": "DOUBLE_DISTRIBUTION_REVERSAL_LONG", "family": "DOUBLE_DISTRIBUTION_REVERSAL", "direction": "LONG", "core": ["COND_DOUBLE_DISTRIBUTION_DAY", "COND_SELLERS_ATTACKING", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH", "COND_INSIDE_VALUE"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "DOUBLE_DISTRIBUTION_REVERSAL_SHORT", "family": "DOUBLE_DISTRIBUTION_REVERSAL", "direction": "SHORT", "core": ["COND_DOUBLE_DISTRIBUTION_DAY", "COND_BUYERS_ATTACKING", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH", "COND_INSIDE_VALUE"], "optional": ["COND_REGIME_TRANSITION"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "VALUE_ROTATION_LONG", "family": "VALUE_ROTATION", "direction": "LONG", "core": ["COND_REGIME_BALANCE", "COND_INSIDE_VALUE", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_NEUTRAL_RANGE_SCENARIO"], "invalidation": ["COND_ACCEPTANCE"]},
    {"id": "VALUE_ROTATION_SHORT", "family": "VALUE_ROTATION", "direction": "SHORT", "core": ["COND_REGIME_BALANCE", "COND_INSIDE_VALUE", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_NEUTRAL_RANGE_SCENARIO"], "invalidation": ["COND_ACCEPTANCE"]},
    {"id": "BUSINESS_ZONE_ROTATION_LONG", "family": "BUSINESS_ZONE_ROTATION", "direction": "LONG", "core": ["COND_BUSINESS_ZONE_AVAILABLE", "COND_BELOW_VALUE", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_REGIME_BALANCE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "BUSINESS_ZONE_ROTATION_SHORT", "family": "BUSINESS_ZONE_ROTATION", "direction": "SHORT", "core": ["COND_BUSINESS_ZONE_AVAILABLE", "COND_ABOVE_VALUE", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_REGIME_BALANCE"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "STOP_RUN_ABSORPTION_LONG", "family": "STOP_RUN_ABSORPTION", "direction": "LONG", "core": ["COND_LIQUIDITY_SWEEP_DOWN", "COND_SELLERS_ATTACKING", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "optional": ["COND_TRAPPED_SELLERS"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "STOP_RUN_ABSORPTION_SHORT", "family": "STOP_RUN_ABSORPTION", "direction": "SHORT", "core": ["COND_LIQUIDITY_SWEEP_UP", "COND_BUYERS_ATTACKING", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "optional": ["COND_TRAPPED_BUYERS"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "LIQUIDITY_CASCADE_LONG", "family": "LIQUIDITY_CASCADE", "direction": "LONG", "core": ["COND_BUYERS_ATTACKING", "COND_NEAR_LIQUIDITY_ABOVE", "COND_REGIME_MOMENTUM"], "confirmation": ["COND_STRUCTURE_BULLISH"], "optional": ["COND_ATR_EXPANDING"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "LIQUIDITY_CASCADE_SHORT", "family": "LIQUIDITY_CASCADE", "direction": "SHORT", "core": ["COND_SELLERS_ATTACKING", "COND_NEAR_LIQUIDITY_BELOW", "COND_REGIME_MOMENTUM"], "confirmation": ["COND_STRUCTURE_BEARISH"], "optional": ["COND_ATR_EXPANDING"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "LIQUIDITY_VACUUM_ROTATION_LONG", "family": "LIQUIDITY_VACUUM_ROTATION", "direction": "LONG", "core": ["COND_NEAR_LIQUIDITY_ABOVE", "COND_BUYERS_ATTACKING"], "confirmation": ["COND_REGIME_TRANSITION"], "optional": ["COND_STRUCTURE_BULLISH"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "LIQUIDITY_VACUUM_ROTATION_SHORT", "family": "LIQUIDITY_VACUUM_ROTATION", "direction": "SHORT", "core": ["COND_NEAR_LIQUIDITY_BELOW", "COND_SELLERS_ATTACKING"], "confirmation": ["COND_REGIME_TRANSITION"], "optional": ["COND_STRUCTURE_BEARISH"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "SWEEP_RISK_AVOIDANCE_LONG", "family": "SWEEP_RISK_AVOIDANCE", "direction": "LONG", "core": ["COND_SWEEP_RISK_IMMINENT", "COND_LIQUIDITY_SWEEP_DOWN", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_BULLISH_SCENARIO_AVAILABLE"], "optional": ["COND_TRAPPED_SELLERS"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "SWEEP_RISK_AVOIDANCE_SHORT", "family": "SWEEP_RISK_AVOIDANCE", "direction": "SHORT", "core": ["COND_SWEEP_RISK_IMMINENT", "COND_LIQUIDITY_SWEEP_UP", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_BEARISH_SCENARIO_AVAILABLE"], "optional": ["COND_TRAPPED_BUYERS"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "WLT_LONG", "family": "WALL_LIFECYCLE_TRAP", "direction": "LONG", "core": ["COND_RESTING_WALL_ABOVE", "COND_SPOOF_SELL", "COND_BUYERS_ATTACKING"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_MANIPULATION_INTENT"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "WLT_SHORT", "family": "WALL_LIFECYCLE_TRAP", "direction": "SHORT", "core": ["COND_RESTING_WALL_BELOW", "COND_SPOOF_BUY", "COND_SELLERS_ATTACKING"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_MANIPULATION_INTENT"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "BID_WALL_ABSORPTION_LONG", "family": "WALL_ABSORPTION", "direction": "LONG", "core": ["COND_RESTING_WALL_BELOW", "COND_SELLERS_ATTACKING", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_ICEBERG_BUY"], "optional": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "ASK_WALL_ABSORPTION_SHORT", "family": "WALL_ABSORPTION", "direction": "SHORT", "core": ["COND_RESTING_WALL_ABOVE", "COND_BUYERS_ATTACKING", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_ICEBERG_SELL"], "optional": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "LIQUIDITY_PULL_BREAKOUT_LONG", "family": "LIQUIDITY_PULL_BREAKOUT", "direction": "LONG", "core": ["COND_RESTING_WALL_ABOVE", "COND_SPOOF_SELL", "COND_BUYERS_ATTACKING"], "confirmation": ["COND_STRUCTURE_BULLISH"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "LIQUIDITY_PULL_BREAKOUT_SHORT", "family": "LIQUIDITY_PULL_BREAKOUT", "direction": "SHORT", "core": ["COND_RESTING_WALL_BELOW", "COND_SPOOF_BUY", "COND_SELLERS_ATTACKING"], "confirmation": ["COND_STRUCTURE_BEARISH"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "ICEBERG_SUPPORT_LONG", "family": "ICEBERG_ABSORPTION", "direction": "LONG", "core": ["COND_ICEBERG_BUY", "COND_SELLERS_ATTACKING", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "ICEBERG_RESISTANCE_SHORT", "family": "ICEBERG_ABSORPTION", "direction": "SHORT", "core": ["COND_ICEBERG_SELL", "COND_BUYERS_ATTACKING", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "SPOOF_TRAP_LONG", "family": "SPOOF_TRAP", "direction": "LONG", "core": ["COND_SPOOF_SELL", "COND_BUYERS_ATTACKING", "COND_MANIPULATION_INTENT"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_STRUCTURE_BULLISH"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "SPOOF_TRAP_SHORT", "family": "SPOOF_TRAP", "direction": "SHORT", "core": ["COND_SPOOF_BUY", "COND_SELLERS_ATTACKING", "COND_MANIPULATION_INTENT"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_STRUCTURE_BEARISH"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "TREND_IGNITION_LONG", "family": "TREND_IGNITION", "direction": "LONG", "core": ["COND_REGIME_MOMENTUM", "COND_BUYERS_ATTACKING", "COND_STRUCTURE_BULLISH"], "confirmation": ["COND_ACCEPTANCE", "COND_ATR_EXPANDING"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "TREND_IGNITION_SHORT", "family": "TREND_IGNITION", "direction": "SHORT", "core": ["COND_REGIME_MOMENTUM", "COND_SELLERS_ATTACKING", "COND_STRUCTURE_BEARISH"], "confirmation": ["COND_ACCEPTANCE", "COND_ATR_EXPANDING"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "TREND_CONTINUATION_LONG", "family": "TREND_CONTINUATION", "direction": "LONG", "core": ["COND_REAL_BULLISH", "COND_BUYERS_ATTACKING", "COND_STRUCTURE_BULLISH"], "confirmation": ["COND_REGIME_MOMENTUM"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "TREND_CONTINUATION_SHORT", "family": "TREND_CONTINUATION", "direction": "SHORT", "core": ["COND_REAL_BEARISH", "COND_SELLERS_ATTACKING", "COND_STRUCTURE_BEARISH"], "confirmation": ["COND_REGIME_MOMENTUM"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "ABSORPTION_CONTINUATION_LONG", "family": "ABSORPTION_CONTINUATION", "direction": "LONG", "core": ["COND_REAL_BULLISH", "COND_SELLERS_ATTACKING", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_STRUCTURE_BULLISH"], "optional": ["COND_REGIME_MOMENTUM"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "ABSORPTION_CONTINUATION_SHORT", "family": "ABSORPTION_CONTINUATION", "direction": "SHORT", "core": ["COND_REAL_BEARISH", "COND_BUYERS_ATTACKING", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_STRUCTURE_BEARISH"], "optional": ["COND_REGIME_MOMENTUM"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "VOLATILITY_EXPANSION_CONTINUATION_LONG", "family": "VOLATILITY_EXPANSION_CONTINUATION", "direction": "LONG", "core": ["COND_ATR_EXPANDING", "COND_BUYERS_ATTACKING", "COND_STRUCTURE_BULLISH"], "confirmation": ["COND_BULLISH_SCENARIO_AVAILABLE"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "VOLATILITY_EXPANSION_CONTINUATION_SHORT", "family": "VOLATILITY_EXPANSION_CONTINUATION", "direction": "SHORT", "core": ["COND_ATR_EXPANDING", "COND_SELLERS_ATTACKING", "COND_STRUCTURE_BEARISH"], "confirmation": ["COND_BEARISH_SCENARIO_AVAILABLE"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "MOMENTUM_CONTINUATION_LONG", "family": "MOMENTUM_CONTINUATION", "direction": "LONG", "core": ["COND_REGIME_MOMENTUM", "COND_REAL_BULLISH", "COND_BUYERS_ATTACKING"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_STRUCTURE_BULLISH"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "MOMENTUM_CONTINUATION_SHORT", "family": "MOMENTUM_CONTINUATION", "direction": "SHORT", "core": ["COND_REGIME_MOMENTUM", "COND_REAL_BEARISH", "COND_SELLERS_ATTACKING"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_STRUCTURE_BEARISH"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "VOLATILITY_COLLAPSE_REVERSION_LONG", "family": "VOLATILITY_COLLAPSE_REVERSION", "direction": "LONG", "core": ["COND_ATR_AVAILABLE", "COND_SELLERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE"], "confirmation": ["COND_BUYERS_DEFENDING"], "optional": ["COND_REGIME_BALANCE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "VOLATILITY_COLLAPSE_REVERSION_SHORT", "family": "VOLATILITY_COLLAPSE_REVERSION", "direction": "SHORT", "core": ["COND_ATR_AVAILABLE", "COND_BUYERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE"], "confirmation": ["COND_SELLERS_DEFENDING"], "optional": ["COND_REGIME_BALANCE"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "SCENARIO_COMPRESSION_BREAK_LONG", "family": "SCENARIO_COMPRESSION_BREAK", "direction": "LONG", "core": ["COND_NEUTRAL_RANGE_SCENARIO", "COND_BULLISH_SCENARIO_AVAILABLE", "COND_BUYERS_ATTACKING"], "confirmation": ["COND_STRUCTURE_BULLISH"], "optional": ["COND_ATR_EXPANDING"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "SCENARIO_COMPRESSION_BREAK_SHORT", "family": "SCENARIO_COMPRESSION_BREAK", "direction": "SHORT", "core": ["COND_NEUTRAL_RANGE_SCENARIO", "COND_BEARISH_SCENARIO_AVAILABLE", "COND_SELLERS_ATTACKING"], "confirmation": ["COND_STRUCTURE_BEARISH"], "optional": ["COND_ATR_EXPANDING"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "STRUCTURE_FLOW_ALIGNMENT_LONG", "family": "STRUCTURE_FLOW_ALIGNMENT", "direction": "LONG", "core": ["COND_STRUCTURE_BULLISH", "COND_BUYERS_ATTACKING", "COND_POSITIVE_DELTA"], "confirmation": ["COND_BULLISH_SCENARIO_AVAILABLE"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "STRUCTURE_FLOW_ALIGNMENT_SHORT", "family": "STRUCTURE_FLOW_ALIGNMENT", "direction": "SHORT", "core": ["COND_STRUCTURE_BEARISH", "COND_SELLERS_ATTACKING", "COND_NEGATIVE_DELTA"], "confirmation": ["COND_BEARISH_SCENARIO_AVAILABLE"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "MTF_ALIGNMENT_LONG", "family": "MTF_ALIGNMENT", "direction": "LONG", "core": ["COND_REAL_BULLISH", "COND_STRUCTURE_BULLISH", "COND_BULLISH_SCENARIO_AVAILABLE"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_REGIME_MOMENTUM"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "MTF_ALIGNMENT_SHORT", "family": "MTF_ALIGNMENT", "direction": "SHORT", "core": ["COND_REAL_BEARISH", "COND_STRUCTURE_BEARISH", "COND_BEARISH_SCENARIO_AVAILABLE"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_REGIME_MOMENTUM"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "PREMIUM_DISCOUNT_REVERSAL_LONG", "family": "PREMIUM_DISCOUNT_REVERSAL", "direction": "LONG", "core": ["COND_BELOW_VALUE", "COND_SELLERS_ATTACKING", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "optional": ["COND_BULLISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "PREMIUM_DISCOUNT_REVERSAL_SHORT", "family": "PREMIUM_DISCOUNT_REVERSAL", "direction": "SHORT", "core": ["COND_ABOVE_VALUE", "COND_BUYERS_ATTACKING", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "optional": ["COND_BEARISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "CQE_REAL_BULLISH_CONTINUATION", "family": "CANDLE_QUALITY", "direction": "LONG", "core": ["COND_REAL_BULLISH", "COND_POSITIVE_DELTA", "COND_BUYERS_ATTACKING"], "confirmation": ["COND_NEAR_LIQUIDITY_ABOVE"], "optional": ["COND_STRUCTURE_BULLISH"], "invalidation": ["COND_FAKE_BULLISH"]},
    {"id": "CQE_REAL_BEARISH_CONTINUATION", "family": "CANDLE_QUALITY", "direction": "SHORT", "core": ["COND_REAL_BEARISH", "COND_NEGATIVE_DELTA", "COND_SELLERS_ATTACKING"], "confirmation": ["COND_NEAR_LIQUIDITY_BELOW"], "optional": ["COND_STRUCTURE_BEARISH"], "invalidation": ["COND_FAKE_BEARISH"]},
    {"id": "CQE_FAKE_BULLISH_REVERSAL", "family": "CANDLE_QUALITY_REVERSAL", "direction": "SHORT", "core": ["COND_FAKE_BULLISH", "COND_SELLERS_DEFENDING", "COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "confirmation": ["COND_TRAPPED_BUYERS"], "optional": ["COND_BEARISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "CQE_FAKE_BEARISH_REVERSAL", "family": "CANDLE_QUALITY_REVERSAL", "direction": "LONG", "core": ["COND_FAKE_BEARISH", "COND_BUYERS_DEFENDING", "COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "confirmation": ["COND_TRAPPED_SELLERS"], "optional": ["COND_BULLISH_SCENARIO_AVAILABLE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "EFFORT_RESULT_LONG", "family": "EFFORT_VS_RESULT", "direction": "LONG", "core": ["COND_SELLERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_BUYERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BULLISH"], "optional": ["COND_NEAR_LIQUIDITY_ABOVE"], "invalidation": ["COND_REAL_BEARISH"]},
    {"id": "EFFORT_RESULT_SHORT", "family": "EFFORT_VS_RESULT", "direction": "SHORT", "core": ["COND_BUYERS_ATTACKING", "COND_PRICE_FAILED_TO_ADVANCE", "COND_SELLERS_DEFENDING"], "confirmation": ["COND_DELTA_PRICE_DIVERGENCE_BEARISH"], "optional": ["COND_NEAR_LIQUIDITY_BELOW"], "invalidation": ["COND_REAL_BULLISH"]},
    {"id": "NO_TRADE_CHOP", "family": "NO_TRADE", "direction": "NEUTRAL", "core": ["COND_CHOP_BALANCED", "COND_STRUCTURE_RANGE"], "confirmation": ["COND_NEUTRAL_RANGE_SCENARIO"], "optional": ["COND_ATR_AVAILABLE"], "invalidation": [], "opens": False},
    {"id": "NO_TRADE_DATA_INVALID", "family": "NO_TRADE", "direction": "NEUTRAL", "core": ["COND_DATA_INVALID"], "confirmation": [], "optional": [], "invalidation": [], "opens": False},
    {"id": "NO_TRADE_SWEEP_RISK", "family": "NO_TRADE", "direction": "NEUTRAL", "core": ["COND_SWEEP_RISK_IMMINENT"], "confirmation": [], "optional": ["COND_LIQUIDITY_SWEEP_DOWN", "COND_LIQUIDITY_SWEEP_UP"], "invalidation": [], "opens": False},
]


def build_model_definitions() -> list[dict[str, Any]]:
    models = [
        _make_model(
            model_id=spec["id"],
            model_family=spec["family"],
            direction=spec["direction"],
            core=spec["core"],
            confirmation=spec["confirmation"],
            optional=spec["optional"],
            invalidation=spec["invalidation"],
            opens_paper_trade=spec.get("opens", True),
        )
        for spec in MODEL_SPECS
    ]
    return models


def run_model_definition_registry() -> dict[str, Any]:
    models = build_model_definitions()
    output = {
        "timestamp_utc": _utc_now(),
        "symbol": "BTCUSDT",
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "STATIC_MODEL_DEFINITION_LIBRARY",
        },
        "model_count": len(models),
        "model_ids": [model["model_id"] for model in models],
        "models": models,
        "reason_codes": [
            f"MODEL_COUNT_{len(models)}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "PAPER_ONLY_RESEARCH",
        ],
        "data_quality": {
            "level": "HIGH",
            "missing_inputs": [],
        },
        "feeds_next": [
            "MODEL_HUNTER_ENGINE",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_model_definition_registry(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
