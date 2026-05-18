import copy

from src.simple.scenario_entry_trigger_engine import compute_scenario_trigger
from src.simple.setup_candidate_engine import build_setup_candidate
from src.simple.trade_plan_engine import compute_trade_plan
from src.simple.decision_gate_engine import compute_decision_gate
from src.simple.paper_lifecycle_tracker import compute_paper_lifecycle
from src.simple.paper_outcome_tracker import build_paper_outcome
from src.simple.research_edge_matrix_engine import _clean_sample


def _setup_ctx():
    return {
        "symbol": "BTCUSDT",
        "setup_context_label": "STRONG_LONG_CONTEXT",
        "setup_context_score": 8.0,
        "direction_bias": "LONG",
        "confidence": 0.9,
        "tradeable": True,
        "data_quality": {"level": "OK", "score": 1.0},
        "identity": {"setup_id": "SETUP_1", "setup_family": "LONG_CONTINUATION"},
    }


def test_scenario_does_not_emit_trade_fields():
    out = compute_scenario_trigger(_setup_ctx(), None, {"symbol": "BTCUSDT", "evidence_score": 8.0}, {"symbol": "BTCUSDT"})
    assert "entry_price" not in out
    assert "stop_loss" not in out
    assert "tp1" not in out
    assert out["trigger_state"] == "SCENARIO_ONLY"
    assert isinstance(out["possible_scenarios"], list)
    assert "active_scenario" in out


def test_setup_does_not_emit_execution_fields():
    out = build_setup_candidate(
        "BTCUSDT",
        {"available": True, "is_official_binance_1m": True},
        {"available": True, "micro_winner": "LONG"},
        {"available": True, "candle_direction": "BULLISH"},
        {"available": True, "quality_weight": 0.9, "quality_label": "HIGH"},
        {"available": True, "structure_bias": "BULLISH", "draw_on_liquidity": "ABOVE", "context_score": 70.0},
        "TEST",
    )
    sc = out["setup_candidate"]
    assert "entry_price" not in sc
    assert "decision" not in sc
    assert "setup_family" in sc
    assert "required_conditions" in sc


def test_trade_plan_requires_signal():
    plan = compute_trade_plan(
        scenario_trigger={"symbol": "BTCUSDT", "scenario_label": "LONG_CONTINUATION", "direction_bias": "LONG", "trigger_strength": 0.9},
        setup_context={"symbol": "BTCUSDT", "confidence": 0.9, "tradeable": True, "data_quality": {"level": "OK", "score": 1.0}},
        flow_state={"latest_bucket": {"last_price": 100.0}},
        evidence={},
        persistence={},
        signal_event=None,
    )
    assert plan["plan_status"] == "NO_PLAN"


def test_decision_enum_is_strict():
    plan = {
        "symbol": "BTCUSDT", "plan_status": "VALID", "side": "LONG", "entry_price": 100.0,
        "stop_loss": 99.0, "tp1": 101.6, "tp2": 102.2, "rr_tp1": 1.6, "rr_tp2": 2.2,
        "reason_codes": ["x"], "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        "data_quality": {"level": "OK", "score": 1.0}, "trade_plan_id": "TP1", "signal_id": "SIG1"
    }
    scen = {"ready_for_entry": True, "trigger_state": "READY_FOR_ENTRY", "trigger_strength": 0.9}
    out = compute_decision_gate(plan, scen, None, None, None, None)
    assert out["decision"] in {"ALLOW_PAPER", "WATCH_ONLY", "BLOCK"}


def test_lifecycle_only_allow_paper_opens():
    gate = {"symbol": "BTCUSDT", "decision": "BLOCK", "allowed_for_paper_lifecycle": False, "selected_side": "LONG", "decision_id": "DEC1"}
    plan = {"trade_plan_id": "TP1", "signal_id": "SIG1"}
    out = compute_paper_lifecycle(gate, plan, None, {"latest_bucket": {"last_price": 100.0}})
    assert out["lifecycle_status"] == "NO_LIFECYCLE"


def test_outcome_closed_only_flag_and_edge_filter():
    s1 = {"available": True, "official_high": 105.0, "official_low": 95.0, "official_close": 101.0, "is_official_binance_1m": True}
    s7 = {
        "available": True, "decision": "ALLOW_PAPER", "paper_eligible": True, "edge_eligible_if_outcome_closes": True,
        "trade_direction": "LONG", "entry_price": 100.0, "stop_loss": 99.0, "tp1": 101.0, "tp2": 102.0, "rr_tp1": 1.0, "rr_tp2": 2.0
    }
    out = build_paper_outcome("BTCUSDT", s1, s7, "TEST")
    assert "closed_only" in out

    sample = {
        "epoch_id": "EPOCH_2026_Q2", "closed_only": False, "outcome_status": "OPEN",
        "model_id": "M", "setup_family": "F", "direction": "LONG", "primary_tf": "1m", "context_tf": "15m", "plan_style": "X",
        "rr1": 1.0, "rr2": 2.0, "mfe": 0.5,
    }
    assert _clean_sample(sample) is False
