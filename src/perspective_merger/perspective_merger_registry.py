from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


PERSPECTIVE_MERGER_BLOCK_ID = "PHASE_12_PERSPECTIVE_MERGER"

BIAS_VALUES = (
    "LONG",
    "SHORT",
    "NEUTRAL",
    "NO_TRADE",
    "CONFLICTED",
    "UNKNOWN",
)

ALIGNMENT_STATUSES = (
    "FULL_ALIGNMENT",
    "PARTIAL_ALIGNMENT",
    "CORE_SMC_ALIGNED",
    "CORE_MM_ALIGNED",
    "SMC_MM_ALIGNED",
    "CONFLICTED_ALIGNMENT",
    "NO_ALIGNMENT",
    "INSUFFICIENT_DATA",
    "UNKNOWN",
)

PERSPECTIVE_CONFIDENCE = (
    "HIGH",
    "MEDIUM",
    "LOW",
    "INVALID",
    "UNKNOWN",
)

CONFLICT_TYPES = (
    "CORE_SMC_CONFLICT",
    "CORE_MM_CONFLICT",
    "SMC_MM_CONFLICT",
    "THREE_WAY_CONFLICT",
    "MISSING_SMC",
    "MISSING_MM",
    "MISSING_CORE",
    "LOW_CONFIDENCE_CONFLICT",
    "UNKNOWN",
)

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
    "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
    "PHASE_13_ADAPTIVE_INTELLIGENCE",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "perspective_merger_id",
    "lineage_id",
    "core_bias",
    "smc_bias",
    "mm_bias",
    "core_confidence",
    "smc_confidence",
    "mm_confidence",
    "alignment_status",
    "alignment_score",
    "perspective_agreement",
    "bias_conflicts",
    "conflict_sources",
    "confidence_adjustment",
    "core_summary",
    "smc_summary",
    "mm_summary",
    "merged_context",
    "decision_gate_context_note",
    "nova_brain_context_note",
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


def build_perspective_merger_id(symbol: str, seed: Any) -> str:
    basis = {"symbol": str(symbol or "UNKNOWN"), "seed": seed}
    return f"PMG_{stable_sha256(basis)[:24]}"


def build_lineage_id(label: str, *parts: Any) -> str:
    basis = {"label": label, "parts": [str(part or "") for part in parts]}
    return f"LIN_{stable_sha256(basis)[:24]}"


def normalize_bias(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"LONG", "BULLISH", "BUY"}:
        return "LONG"
    if text in {"SHORT", "BEARISH", "SELL"}:
        return "SHORT"
    if text in {"NEUTRAL", "BALANCED"}:
        return "NEUTRAL"
    if text in {"NO_TRADE", "NONE"}:
        return "NO_TRADE"
    if text in {"CONFLICTED", "MIXED"}:
        return "CONFLICTED"
    return "UNKNOWN"


def confidence_to_score(label: str) -> float | None:
    mapping = {
        "HIGH": 0.8,
        "MEDIUM": 0.6,
        "LOW": 0.35,
        "INVALID": 0.1,
        "UNKNOWN": None,
    }
    return mapping.get(str(label or "UNKNOWN").upper())
