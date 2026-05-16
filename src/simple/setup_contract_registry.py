from __future__ import annotations

from typing import Any


def _contract(
    contract_id: str,
    setup_family: str,
    direction: str,
    allowed_regimes: list[str],
    blocked_regimes: list[str],
    required_structure_bias: str,
    required_liquidity_context: list[str],
) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "setup_family": setup_family,
        "direction": direction,
        "allowed_regimes": allowed_regimes,
        "blocked_regimes": blocked_regimes,
        "required_structure_bias": required_structure_bias,
        "required_liquidity_context": required_liquidity_context,
        "entry_model": f"{setup_family}_ENTRY_V1",
        "sl_model": f"{setup_family}_SL_V1",
        "tp_model": f"{setup_family}_TP_V1",
        "rr_policy": {"min_rr1": 1.2, "min_rr2": 1.5},
        "duplicate_policy": {"max_open_same_contract": 2, "max_open_same_direction": 3},
        "session_policy": {
            "allowed_sessions": ["LONDON", "NEW_YORK"],
            "off_session_policy": "DOWNGRADE",
        },
        "invalidation_model": f"{setup_family}_INVALIDATION_V1",
        "continuation_model": f"{setup_family}_CONTINUATION_V1",
        "failure_model": f"{setup_family}_FAILURE_V1",
        "reason_codes": [],
    }


def load_setup_contract_registry() -> list[dict[str, Any]]:
    return [
        _contract(
            "SC001",
            "LIQUIDITY_SWEEP_REVERSAL_LONG",
            "LONG",
            ["RANGE", "REVERSAL", "ROTATION"],
            [],
            "LONG",
            ["SWEEP", "STOP_RUN", "ANY"],
        ),
        _contract(
            "SC002",
            "LIQUIDITY_SWEEP_REVERSAL_SHORT",
            "SHORT",
            ["RANGE", "REVERSAL", "ROTATION"],
            [],
            "SHORT",
            ["SWEEP", "STOP_RUN", "ANY"],
        ),
        _contract("SC003", "TREND_CONTINUATION_LONG", "LONG", ["TREND", "EXPANSION"], [], "LONG", ["ANY"]),
        _contract("SC004", "TREND_CONTINUATION_SHORT", "SHORT", ["TREND", "EXPANSION"], [], "SHORT", ["ANY"]),
        _contract("SC005", "ABSORPTION_REVERSAL_LONG", "LONG", ["REVERSAL", "RANGE"], [], "LONG", ["ABSORPTION", "ANY"]),
        _contract("SC006", "ABSORPTION_REVERSAL_SHORT", "SHORT", ["REVERSAL", "RANGE"], [], "SHORT", ["ABSORPTION", "ANY"]),
        _contract("SC007", "RANGE_ROTATION_LONG", "LONG", ["RANGE", "ROTATION"], [], "NEUTRAL", ["ANY"]),
        _contract("SC008", "RANGE_ROTATION_SHORT", "SHORT", ["RANGE", "ROTATION"], [], "NEUTRAL", ["ANY"]),
        _contract("SC009", "BREAKOUT_EXPANSION_LONG", "LONG", ["COMPRESSION", "EXPANSION"], [], "LONG", ["ANY"]),
        _contract("SC010", "BREAKOUT_EXPANSION_SHORT", "SHORT", ["COMPRESSION", "EXPANSION"], [], "SHORT", ["ANY"]),
    ]

