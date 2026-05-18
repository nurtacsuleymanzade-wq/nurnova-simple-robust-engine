from __future__ import annotations

from src.replay_engine.replay_validator import validate_replay_output


def _valid_payload() -> dict:
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "block_id": "PHASE_9_WHAT_IF_REPLAY_ENGINE",
        "symbol": "BTCUSDT",
        "replay_batch_id": "RPL_123",
        "lineage_id": "LIN_123",
        "source_outcome_id": "OUT_1",
        "source_trade_plan_id": "TPN_1",
        "source_setup_candidate_id": "SETUP_1",
        "source_active_scenario_id": "ASC_1",
        "source_flow_reaction_id": "FR_1",
        "source_edge_row_id": "EDR_1",
        "replay_status": "REPLAY_SUCCESS",
        "replay_scenarios": [
            {
                "scenario_id": "SCN_1",
                "scenario_type": "EARLY_ENTRY",
                "alternative_outcome": {"trade_fate": "TP2_HIT"},
                "alternative_r_multiple": 1.7,
                "better_than_original": True,
                "worse_than_original": False,
                "reason_codes": [],
            }
        ],
        "decision_quality": "GOOD",
        "decision_quality_score": 0.7,
        "counterfactual_summary": {},
        "best_alternative_outcome": {},
        "worst_alternative_outcome": {},
        "learning_signals": [],
        "data_quality": "OK",
        "reason_codes": ["REPLAY_ENGINE_COMPUTED"],
        "feeds_next": [
            "PHASE_10_NOVA_BRAIN_SNAPSHOT",
            "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
        ],
        "warnings": [],
        "source_is_closed_outcome": True,
        "source_edge_eligible": True,
    }


def test_invalid_enum_is_detected() -> None:
    payload = _valid_payload()
    payload["replay_scenarios"][0]["scenario_type"] = "NOT_VALID"
    result = validate_replay_output(payload)
    assert not result["is_valid"]
    assert "INVALID_SCENARIO_TYPE_ENUM" in result["errors"]


def test_output_required_fields_pass() -> None:
    result = validate_replay_output(_valid_payload())
    assert result["is_valid"]


def test_feeds_next_are_correct() -> None:
    payload = _valid_payload()
    assert payload["feeds_next"] == [
        "PHASE_10_NOVA_BRAIN_SNAPSHOT",
        "PHASE_11_PROBABILISTIC_SCENARIO_ENGINE",
    ]
