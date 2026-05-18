from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


BRAIN_BLOCK_ID = "PHASE_10_NOVA_BRAIN_SNAPSHOT"

SYSTEM_HEALTH = (
    "HEALTHY",
    "STRESSED",
    "DEGRADED",
    "CRITICAL",
    "UNKNOWN",
)

EDGE_TREND = (
    "GROWING",
    "STABLE",
    "DECAYING",
    "DEAD",
    "UNKNOWN",
)

RISK_LEVEL = (
    "LOW",
    "MEDIUM",
    "HIGH",
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

DECISION_QUALITY_OVERVIEW = (
    "STRONG",
    "STABLE",
    "WEAKENING",
    "POOR",
    "UNKNOWN",
)

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
    "PHASE_12_META_LEARNING_LAYER",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "brain_snapshot_id",
    "lineage_id",
    "system_health",
    "edge_growth",
    "edge_decay",
    "risk_map",
    "fake_scenario_pressure",
    "regime_risk",
    "setup_survival",
    "decision_quality_overview",
    "replay_learning_summary",
    "operational_alerts",
    "dominant_market_story",
    "brain_summary",
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


def build_brain_snapshot_id(symbol: str, seed: Any) -> str:
    basis = {"symbol": str(symbol or "UNKNOWN"), "seed": seed}
    return f"BRN_{stable_sha256(basis)[:24]}"


def build_lineage_id(label: str, *parts: Any) -> str:
    basis = {"label": label, "parts": [str(part or "") for part in parts]}
    return f"LIN_{stable_sha256(basis)[:24]}"
