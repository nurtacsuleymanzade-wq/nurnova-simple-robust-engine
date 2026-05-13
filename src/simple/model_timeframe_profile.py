"""Canonical timeframe profiles for paper-research model families."""

from __future__ import annotations

from typing import Any

_PROFILES: dict[str, dict[str, Any]] = {
    "MOMENTUM_CONTINUATION": {
        "preferred_primary_tf": ["1m", "5m"],
        "allowed_trigger_tf": ["1m", "5m"],
        "context_tf": ["15m"],
        "expected_hold_minutes": {"min": 5, "max": 90},
        "plan_style": "FAST_CONTINUATION",
    },
    "TRAP_REVERSAL": {
        "preferred_primary_tf": ["5m"],
        "allowed_trigger_tf": ["1m", "5m"],
        "context_tf": ["15m"],
        "expected_hold_minutes": {"min": 15, "max": 120},
        "plan_style": "SWEEP_REVERSAL",
    },
    "LIQUIDITY_SWEEP_REVERSAL": {
        "preferred_primary_tf": ["5m", "15m"],
        "allowed_trigger_tf": ["5m", "15m"],
        "context_tf": ["15m", "1h"],
        "expected_hold_minutes": {"min": 30, "max": 240},
        "plan_style": "LIQUIDITY_RECLAIM",
    },
    "DOUBLE_DISTRIBUTION_REVERSAL": {
        "preferred_primary_tf": ["15m"],
        "allowed_trigger_tf": ["5m", "15m"],
        "context_tf": ["1h"],
        "expected_hold_minutes": {"min": 60, "max": 360},
        "plan_style": "VALUE_ROTATION",
    },
    "ABSORPTION_REVERSAL": {
        "preferred_primary_tf": ["5m", "15m"],
        "allowed_trigger_tf": ["1m", "5m", "15m"],
        "context_tf": ["15m"],
        "expected_hold_minutes": {"min": 15, "max": 180},
        "plan_style": "ABSORPTION_REACTION",
    },
    "ACCEPTANCE_BREAKOUT": {
        "preferred_primary_tf": ["5m", "15m"],
        "allowed_trigger_tf": ["5m", "15m"],
        "context_tf": ["15m", "1h"],
        "expected_hold_minutes": {"min": 30, "max": 240},
        "plan_style": "ACCEPTANCE_CONTINUATION",
    },
    "DEFAULT": {
        "preferred_primary_tf": ["5m"],
        "allowed_trigger_tf": ["1m"],
        "context_tf": ["15m"],
        "expected_hold_minutes": {"min": 15, "max": 90},
        "plan_style": "DEFAULT_INTRADAY",
    },
}


def _normalize_family(setup_family: Any, model_id: Any) -> str:
    text = " ".join(str(value or "") for value in (setup_family, model_id)).upper()
    if "ACCEPTANCE_BREAKOUT" in text:
        return "ACCEPTANCE_BREAKOUT"
    if "MOMENTUM_CONTINUATION" in text or "CONTINUATION" in text:
        return "MOMENTUM_CONTINUATION"
    if "LIQUIDITY_SWEEP_REVERSAL" in text or "LSR_" in text:
        return "LIQUIDITY_SWEEP_REVERSAL"
    if "DOUBLE_DISTRIBUTION_REVERSAL" in text or "VALUE_ROTATION" in text:
        return "DOUBLE_DISTRIBUTION_REVERSAL"
    if "ABSORPTION_REVERSAL" in text or "ABSORPTION" in text or "AR01" in text or "DAF" in text:
        return "ABSORPTION_REVERSAL"
    if "TRAP_REVERSAL" in text or "TRAP" in text or "FCR" in text:
        return "TRAP_REVERSAL"
    return "DEFAULT"


def get_timeframe_profile(setup_family: Any, model_id: Any = None) -> dict[str, Any]:
    family = _normalize_family(setup_family, model_id)
    profile = dict(_PROFILES.get(family, _PROFILES["DEFAULT"]))
    profile["resolved_setup_family"] = family
    profile["preferred_primary_tf"] = list(profile.get("preferred_primary_tf") or [])
    profile["allowed_trigger_tf"] = list(profile.get("allowed_trigger_tf") or [])
    profile["context_tf"] = list(profile.get("context_tf") or [])
    hold = dict(profile.get("expected_hold_minutes") or {})
    profile["expected_hold_minutes"] = {
        "min": int(hold.get("min") or 15),
        "max": int(hold.get("max") or 90),
    }
    return profile
