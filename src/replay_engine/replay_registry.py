from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


REPLAY_BLOCK_ID = "PHASE_9_WHAT_IF_REPLAY_ENGINE"

REPLAY_SCENARIOS = (
    "EARLY_ENTRY",
    "LATE_ENTRY",
    "RETEST_ENTRY",
    "BREAKOUT_ENTRY",
    "RECLAIM_ENTRY",
    "TIGHTER_STOP",
    "WIDER_STOP",
    "CLOSER_TP",
    "FARTHER_TP",
    "NO_TRADE",
    "WAIT_INSTEAD_OF_ENTRY",
    "BLOCK_INSTEAD_OF_ENTRY",
    "ENTRY_DELAY",
    "EARLY_EXIT",
    "HOLD_LONGER",
    "UNKNOWN",
)

DECISION_QUALITY = (
    "EXCELLENT",
    "GOOD",
    "NEUTRAL",
    "POOR",
    "TERRIBLE",
    "UNKNOWN",
)

REPLAY_STATUS = (
    "REPLAY_SUCCESS",
    "REPLAY_PARTIAL",
    "REPLAY_FAILED",
    "NO_REPLAY_DATA",
    "INVALID",
    "UNKNOWN",
)

DATA_QUALITY = ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN")

DEFAULT_FEEDS_NEXT = [
    "PHASE_10_NOVA_BRAIN_SNAPSHOT",
    "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
]

ELIGIBLE_TRADE_FATES = {
    "TP1_HIT",
    "TP2_HIT",
    "SL_HIT",
    "PARTIAL_WIN",
    "PARTIAL_LOSS",
    "BREAKEVEN",
    "INVALIDATED_AFTER_ENTRY",
}

REQUIRED_FIELDS = [
    "timestamp_utc",
    "block_id",
    "symbol",
    "replay_batch_id",
    "lineage_id",
    "source_outcome_id",
    "source_trade_plan_id",
    "source_setup_candidate_id",
    "source_active_scenario_id",
    "source_flow_reaction_id",
    "source_edge_row_id",
    "replay_status",
    "replay_scenarios",
    "decision_quality",
    "decision_quality_score",
    "counterfactual_summary",
    "best_alternative_outcome",
    "worst_alternative_outcome",
    "learning_signals",
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


def build_replay_batch_id(source_outcome_id: Any, source_trade_plan_id: Any, source_edge_row_id: Any) -> str:
    basis = {
        "source_outcome_id": str(source_outcome_id or ""),
        "source_trade_plan_id": str(source_trade_plan_id or ""),
        "source_edge_row_id": str(source_edge_row_id or ""),
    }
    return f"RPL_{stable_sha256(basis)[:24]}"


def build_scenario_id(source_outcome_id: Any, scenario_type: str, seed: Any) -> str:
    basis = {
        "source_outcome_id": str(source_outcome_id or ""),
        "scenario_type": str(scenario_type or "UNKNOWN"),
        "seed": seed,
    }
    return f"SCN_{stable_sha256(basis)[:24]}"


def build_lineage_id(label: str, *parts: Any) -> str:
    basis = {"label": label, "parts": [str(part or "") for part in parts]}
    return f"LIN_{stable_sha256(basis)[:24]}"
