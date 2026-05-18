from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


PROBABILISTIC_BLOCK_ID = "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE"

SCENARIO_PATHS = (
    "BULLISH_CONTINUATION_PATH",
    "BEARISH_CONTINUATION_PATH",
    "RANGE_ROTATION_PATH",
    "COMPRESSION_BREAKOUT_UP_PATH",
    "COMPRESSION_BREAKOUT_DOWN_PATH",
    "FAKE_BREAKOUT_PATH",
    "LIQUIDITY_SWEEP_PATH",
    "MEAN_REVERSION_PATH",
    "TREND_EXHAUSTION_PATH",
    "REVERSAL_PATH",
    "HIGH_VOLATILITY_PATH",
    "LOW_VOLATILITY_PATH",
    "UNKNOWN_PATH",
)

PROBABILITY_BANDS = (
    "VERY_LOW",
    "LOW",
    "MEDIUM",
    "HIGH",
    "VERY_HIGH",
    "UNKNOWN",
)

RISK_PATH_LEVELS = (
    "SAFE",
    "CAUTION",
    "DANGEROUS",
    "EXTREME",
    "UNKNOWN",
)

SCENARIO_PRESSURE = (
    "NORMAL",
    "ELEVATED",
    "DANGEROUS",
    "EXTREME",
    "UNKNOWN",
)

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_12_META_LEARNING_LAYER",
    "PHASE_13_ADAPTIVE_INTELLIGENCE",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "scenario_engine_id",
    "lineage_id",
    "future_paths",
    "probability_clusters",
    "scenario_tree",
    "market_path_forecast",
    "risk_paths",
    "survival_probabilities",
    "fake_breakout_probabilities",
    "continuation_probabilities",
    "liquidity_attraction_zones",
    "dominant_path",
    "scenario_pressure_map",
    "market_story_projection",
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


def build_scenario_engine_id(symbol: str, seed: Any) -> str:
    basis = {"symbol": str(symbol or "UNKNOWN"), "seed": seed}
    return f"PRB_{stable_sha256(basis)[:24]}"


def build_path_id(scenario_path: str, seed: Any) -> str:
    basis = {"scenario_path": str(scenario_path or "UNKNOWN_PATH"), "seed": seed}
    return f"PTH_{stable_sha256(basis)[:24]}"


def build_lineage_id(label: str, *parts: Any) -> str:
    basis = {"label": label, "parts": [str(part or "") for part in parts]}
    return f"LIN_{stable_sha256(basis)[:24]}"


def probability_band(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score >= 0.8:
        return "VERY_HIGH"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"
    if score >= 0.2:
        return "LOW"
    return "VERY_LOW"


def risk_level(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score >= 0.8:
        return "EXTREME"
    if score >= 0.55:
        return "DANGEROUS"
    if score >= 0.25:
        return "CAUTION"
    return "SAFE"


def pressure_level(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score >= 0.8:
        return "EXTREME"
    if score >= 0.55:
        return "DANGEROUS"
    if score >= 0.25:
        return "ELEVATED"
    return "NORMAL"
