from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


AUTONOMY_BLOCK_ID = "PHASE_13_AUTONOMOUS_INTELLIGENCE_READINESS"

AUTONOMY_STATUS = (
    "NOT_READY",
    "EARLY_EXPERIMENTAL",
    "PAPER_ONLY_READY",
    "SUPERVISED_READY",
    "LIMITED_AUTONOMY_READY",
    "FULL_AUTONOMY_UNSAFE",
    "UNKNOWN",
)

HUMAN_OVERRIDE = (
    "REQUIRED",
    "STRONGLY_RECOMMENDED",
    "OPTIONAL",
    "NOT_REQUIRED",
    "UNKNOWN",
)

RISK_LEVEL = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "EXTREME",
    "UNKNOWN",
)

SAFETY_STATUS = (
    "PASS",
    "PARTIAL",
    "FAIL",
    "UNKNOWN",
)

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_14_META_GOVERNOR",
    "PHASE_15_EVOLUTION_LAYER",
]

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "autonomy_audit_id",
    "lineage_id",
    "autonomy_status",
    "autonomy_score",
    "safe_for_autonomy",
    "human_override_required",
    "global_risk_level",
    "lineage_integrity",
    "edge_stability",
    "replay_validation",
    "template_risk",
    "hallucination_risk",
    "fake_confidence_risk",
    "data_spine_health",
    "decision_quality",
    "probabilistic_consistency",
    "perspective_alignment_consistency",
    "system_health",
    "edge_decay_pressure",
    "operational_stability",
    "critical_failures",
    "autonomy_blockers",
    "autonomy_strengths",
    "safety_constraints",
    "recommended_human_controls",
    "autonomy_notes",
    "brain_governor_summary",
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


def build_autonomy_audit_id(symbol: str, seed: Any) -> str:
    basis = {"symbol": str(symbol or "UNKNOWN"), "seed": seed}
    return f"AUD_{stable_sha256(basis)[:24]}"


def build_lineage_id(label: str, *parts: Any) -> str:
    basis = {"label": label, "parts": [str(part or "") for part in parts]}
    return f"LIN_{stable_sha256(basis)[:24]}"


def clamp(value: float) -> float:
    return round(min(max(float(value), 0.0), 1.0), 4)


def safety_status_from_positive_score(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 0.75:
        return "PASS"
    if score >= 0.45:
        return "PARTIAL"
    return "FAIL"


def safety_status_from_risk_score(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score <= 0.25:
        return "PASS"
    if score <= 0.55:
        return "PARTIAL"
    return "FAIL"


def risk_level_from_score(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 0.8:
        return "EXTREME"
    if score >= 0.55:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"
