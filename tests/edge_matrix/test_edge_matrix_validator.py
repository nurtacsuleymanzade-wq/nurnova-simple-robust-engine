from __future__ import annotations

from src.edge_matrix.edge_matrix_validator import validate_conditional_edge_matrix


def _valid_payload() -> dict:
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "block_id": "PHASE_8_CONDITIONAL_EDGE_MATRIX",
        "symbol": "BTCUSDT",
        "edge_matrix_id": "EDM_123",
        "lineage_id": "LIN_123",
        "source_outcome_count": 1,
        "edge_eligible_outcome_count": 1,
        "excluded_outcome_count": 0,
        "excluded_breakdown": {},
        "conditional_edge_rows": [
            {
                "edge_row_id": "EDR_123",
                "group_key": {"pattern": "RANGE_LONG_SETUP"},
                "sample_size": 10,
                "win_count": 6,
                "loss_count": 4,
                "breakeven_count": 0,
                "partial_win_count": 0,
                "partial_loss_count": 0,
                "winrate": 0.6,
                "lossrate": 0.4,
                "avg_r": 0.5,
                "median_r": 0.5,
                "expectancy_r": 0.5,
                "profit_factor": 1.5,
                "max_win_r": 2.0,
                "max_loss_r": -1.0,
                "best_outcome": "TP2_HIT",
                "worst_outcome": "SL_HIT",
                "failure_reason_top": "STOP_LOSS_TOUCHED",
                "success_reason_top": "TAKE_PROFIT_2_TOUCHED",
                "confidence_band": "LOW",
                "edge_status": "WATCHLIST_EDGE",
                "source_outcome_ids": ["OUT_1"],
                "source_paper_trade_ids": ["PPR_1"],
                "source_trade_fates": ["TP2_HIT"],
                "reason_codes": [],
            }
        ],
        "top_positive_edges": [],
        "top_negative_edges": [],
        "failure_patterns": [],
        "high_probability_clusters": [],
        "data_quality": "OK",
        "reason_codes": ["EDGE_MATRIX_COMPUTED"],
        "feeds_next": [
            "PHASE_10_NOVA_BRAIN_SNAPSHOT",
            "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
        ],
        "warnings": [],
    }


def test_invalid_enum_is_detected() -> None:
    payload = _valid_payload()
    payload["conditional_edge_rows"][0]["edge_status"] = "NOT_VALID"
    result = validate_conditional_edge_matrix(payload)
    assert not result["is_valid"]
    assert "INVALID_EDGE_STATUS_ENUM" in result["errors"]


def test_timeout_source_is_detected() -> None:
    payload = _valid_payload()
    payload["conditional_edge_rows"][0]["source_outcome_ids"] = ["OUT_TIMEOUT_1"]
    result = validate_conditional_edge_matrix(payload)
    assert not result["is_valid"]
    assert "FORBIDDEN_TIMEOUT_OR_NO_ENTRY_SOURCE_PRESENT" in result["errors"]


def test_output_required_fields_pass() -> None:
    payload = _valid_payload()
    result = validate_conditional_edge_matrix(payload)
    assert result["is_valid"]


def test_feeds_next_are_correct() -> None:
    payload = _valid_payload()
    assert payload["feeds_next"] == [
        "PHASE_10_NOVA_BRAIN_SNAPSHOT",
        "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
    ]
