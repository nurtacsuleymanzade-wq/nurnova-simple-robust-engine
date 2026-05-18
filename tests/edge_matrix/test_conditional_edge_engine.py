from __future__ import annotations

from src.edge_matrix.conditional_edge_engine import build_conditional_edge_rows


def _context() -> dict:
    return {
        "setup_entry": {
            "setup_candidate_id": "SETUP_1",
            "setup_candidate": "RANGE_LONG_SETUP",
            "setup_direction": "LONG",
            "entry_trigger_status": "TRIGGER_READY",
        },
        "trade_decision": {
            "decision_id": "DEC_1",
            "symbol": "BTCUSDT",
            "entry_model": "RETEST",
            "risk_grade": "LOW",
            "plan_quality": "A",
        },
        "active_scenario": {
            "active_scenario_id": "ASC_1",
            "active_scenario": "RANGE_ROTATION_UP",
        },
        "market_state": {
            "market_state_id": "MS_1",
            "market_regime": "TRENDING",
            "trend_state": "UPTREND",
            "volatility_state": "HIGH",
            "liquidity_state": "ABOVE",
        },
        "flow_reaction": {
            "flow_reaction_id": "FR_1",
            "flow_confirmation": "CONFIRMED",
            "post_liquidity_reaction": "RECLAIM",
            "trap_state": "NONE",
            "absorption_state": "NONE",
        },
    }


def _outcome(*, fate: str = "TP2_HIT", closed: bool = True, eligible: bool = True) -> dict:
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "symbol": "BTCUSDT",
        "outcome_id": f"OUT_{fate}",
        "paper_trade_id": f"PPR_{fate}",
        "decision_id": "DEC_1",
        "setup_candidate_id": "SETUP_1",
        "trade_fate": fate,
        "is_closed_outcome": closed,
        "edge_eligible": eligible,
        "side": "LONG",
        "r_multiple": 1.5,
        "data_quality": "OK",
        "evidence": {
            "trade_decision_evidence": {
                "active_scenario_id": "ASC_1",
                "market_state_id": "MS_1",
                "flow_reaction_id": "FR_1",
                "side": "LONG",
            }
        },
        "reason_codes": ["OUTCOME_SAMPLE"],
        "close_reason": "TAKE_PROFIT_2_TOUCHED",
    }


def test_closed_edge_eligible_outcome_is_edge_input() -> None:
    result = build_conditional_edge_rows([_outcome()], latest_context=_context())
    assert len(result["eligible_records"]) == 1
    assert result["excluded_outcome_count"] == 0


def test_timeout_is_not_edge_input() -> None:
    result = build_conditional_edge_rows([_outcome(fate="DIAGNOSTIC_TIMEOUT")], latest_context=_context())
    assert len(result["eligible_records"]) == 0
    assert result["excluded_breakdown"]["EXCLUDED_TRADE_FATE_DIAGNOSTIC_TIMEOUT"] == 1


def test_no_entry_touch_is_not_edge_input() -> None:
    result = build_conditional_edge_rows([_outcome(fate="NO_ENTRY_TOUCH", eligible=False)], latest_context=_context())
    assert len(result["eligible_records"]) == 0


def test_open_pending_is_not_edge_input() -> None:
    result = build_conditional_edge_rows([_outcome(fate="TP1_HIT", closed=False)], latest_context=_context())
    assert len(result["eligible_records"]) == 0
    assert result["excluded_breakdown"]["NOT_CLOSED_OUTCOME"] == 1


def test_group_key_is_built_correctly() -> None:
    result = build_conditional_edge_rows([_outcome()], latest_context=_context())
    row = result["conditional_rows"][0]
    assert row["group_key"]["pattern"] == "RANGE_LONG_SETUP"
    assert row["group_key"]["market_regime"] == "TRENDING"
    assert row["group_key"]["active_scenario"] == "RANGE_ROTATION_UP"
