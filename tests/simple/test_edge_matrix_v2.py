"""Tests for S22 Edge Matrix v2."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

from src.simple import edge_matrix_v2 as em
from src.simple.edge_matrix_v2 import (
    ALLOWED_EDGE_STATUS,
    ALLOWED_SAMPLE_STATUS,
    build_edge_matrix,
    run_edge_matrix_v2,
)


def _rec(
    *,
    status="CLOSED",
    result="TP1",
    side="LONG",
    realized_r=2.0,
    mfe=2.0,
    mae=-0.5,
    setup_label="LONG_PRESSURE",
    scenario_label="BREAKOUT_ATTEMPT",
    decision="ALLOW_PAPER",
    final_grade="A",
    symbol="BTCUSDT",
):
    return {
        "timestamp_utc": "2026-05-11T00:00:00Z",
        "block_id": "S21_OUTCOME_MONITOR",
        "symbol": symbol,
        "outcome_status": status,
        "outcome_result": result,
        "side": side,
        "realized_r": realized_r,
        "mfe_r": mfe,
        "mae_r": mae,
        "setup_context_snapshot": {"setup_context_label": setup_label},
        "scenario_trigger_snapshot": {"scenario_label": scenario_label},
        "decision_snapshot": {"decision": decision, "final_grade": final_grade},
        "trade_plan_snapshot": {},
        "data_quality": {"score": 1.0, "level": "HIGH", "issues": []},
        "reason_codes": ["SYMBOL_BTCUSDT"],
        "feeds_next": {"next_blocks": ["S22_EDGE_MATRIX_V2"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def _build(records):
    return build_edge_matrix(records, symbol="BTCUSDT", source="S21_OUTCOME_MONITOR", input_status="OK")


# --- Wins / losses counting ---

def test_closed_tp1_counts_as_win():
    r = _build([_rec(status="CLOSED", result="TP1", realized_r=1.2)])
    assert r["overall_stats"]["tp1_count"] == 1
    assert r["overall_stats"]["win_count"] == 1
    assert r["overall_stats"]["loss_count"] == 0


def test_closed_tp2_counts_as_win():
    r = _build([_rec(status="CLOSED", result="TP2", realized_r=4.0)])
    assert r["overall_stats"]["tp2_count"] == 1
    assert r["overall_stats"]["win_count"] == 1


def test_closed_sl_counts_as_loss():
    r = _build([_rec(status="CLOSED", result="SL", realized_r=-1.0)])
    assert r["overall_stats"]["sl_count"] == 1
    assert r["overall_stats"]["loss_count"] == 1
    assert r["overall_stats"]["win_count"] == 0


def test_open_outcomes_excluded_from_expectancy():
    records = [
        _rec(status="OPEN", result="STILL_OPEN", realized_r=None),
        _rec(status="CLOSED", result="TP2", realized_r=4.0),
    ]
    r = _build(records)
    assert r["overall_stats"]["expectancy_r"] == 4.0
    assert r["sample_summary"]["open_records"] == 1
    assert r["sample_summary"]["closed_records"] == 1


def test_no_lifecycle_excluded_from_expectancy():
    records = [
        _rec(status="NO_OUTCOME", result="NO_LIFECYCLE", realized_r=None),
        _rec(status="CLOSED", result="SL", realized_r=-1.0),
    ]
    r = _build(records)
    assert r["sample_summary"]["no_lifecycle_records"] == 1
    assert r["overall_stats"]["expectancy_r"] == -1.0


def test_invalidated_not_counted_as_win_or_loss():
    r = _build([_rec(status="CLOSED", result="INVALIDATED", realized_r=0.0)])
    assert r["overall_stats"]["invalidated_count"] == 1
    assert r["overall_stats"]["win_count"] == 0
    assert r["overall_stats"]["loss_count"] == 0


# --- Sample status / edge status rules ---

def test_insufficient_sample_blocks_edge_claim():
    r = _build([])
    assert r["sample_summary"]["sample_status"] == "INSUFFICIENT_SAMPLE"
    assert r["edge_quality"]["edge_status"] == "NO_EDGE_CLAIM"


def test_early_sample_is_research_only():
    records = [_rec(status="CLOSED", result="TP1", realized_r=1.0) for _ in range(5)]
    r = _build(records)
    assert r["sample_summary"]["sample_status"] == "EARLY_SAMPLE"
    assert r["edge_quality"]["edge_status"] in {"NO_EDGE_CLAIM", "RESEARCH_ONLY"}


def test_usable_sample_does_not_claim_validated_edge():
    # 30 wins → usable but not robust
    records = [_rec(status="CLOSED", result="TP1", realized_r=1.0) for _ in range(30)]
    r = _build(records)
    assert r["sample_summary"]["sample_status"] == "USABLE_SAMPLE"
    assert r["edge_quality"]["edge_status"] != "VALIDATED_EDGE"


def test_robust_sample_can_claim_validated_edge():
    records = (
        [_rec(status="CLOSED", result="TP2", realized_r=4.0) for _ in range(70)]
        + [_rec(status="CLOSED", result="SL", realized_r=-1.0) for _ in range(30)]
    )
    r = _build(records)
    assert r["sample_summary"]["sample_status"] == "ROBUST_SAMPLE"
    assert r["edge_quality"]["edge_status"] == "VALIDATED_EDGE"


# --- Grouping ---

def test_grouping_by_side():
    records = [
        _rec(side="LONG", status="CLOSED", result="TP1", realized_r=1.0),
        _rec(side="SHORT", status="CLOSED", result="SL", realized_r=-1.0),
        _rec(side=None, status="CLOSED", result="TP2", realized_r=2.0),  # UNKNOWN bucket
    ]
    r = _build(records)
    assert "LONG" in r["by_side"]
    assert "SHORT" in r["by_side"]
    assert "UNKNOWN" in r["by_side"]


def test_grouping_by_grade():
    records = [
        _rec(final_grade="A", status="CLOSED", result="TP1", realized_r=1.0),
        _rec(final_grade="B", status="CLOSED", result="SL", realized_r=-1.0),
    ]
    r = _build(records)
    assert "A" in r["by_grade"]
    assert "B" in r["by_grade"]


def test_grouping_by_setup_context_label():
    records = [
        _rec(setup_label="LONG_PRESSURE", status="CLOSED", result="TP1", realized_r=1.0),
        _rec(setup_label="SHORT_PRESSURE", status="CLOSED", result="SL", realized_r=-1.0),
    ]
    r = _build(records)
    assert "LONG_PRESSURE" in r["by_setup_context"]
    assert "SHORT_PRESSURE" in r["by_setup_context"]


def test_grouping_by_scenario_label():
    records = [
        _rec(scenario_label="BREAKOUT_ATTEMPT", status="CLOSED", result="TP1", realized_r=1.0),
        _rec(scenario_label="REVERSAL", status="CLOSED", result="SL", realized_r=-1.0),
    ]
    r = _build(records)
    assert "BREAKOUT_ATTEMPT" in r["by_scenario_label"]
    assert "REVERSAL" in r["by_scenario_label"]


def test_grouping_missing_fields_does_not_crash():
    minimal = {
        "outcome_status": "CLOSED",
        "outcome_result": "TP1",
        "realized_r": 1.0,
    }
    r = build_edge_matrix([minimal], "BTCUSDT", "S21_OUTCOME_MONITOR", "OK")
    assert "UNKNOWN" in r["by_side"]
    assert "UNKNOWN" in r["by_setup_context"]
    assert "UNKNOWN" in r["by_scenario_label"]
    assert "UNKNOWN" in r["by_decision"]
    assert "UNKNOWN" in r["by_grade"]


# --- Expectancy calculation ---

def test_expectancy_r_calculation():
    records = [
        _rec(status="CLOSED", result="TP2", realized_r=4.0),
        _rec(status="CLOSED", result="TP1", realized_r=1.0),
        _rec(status="CLOSED", result="SL", realized_r=-1.0),
    ]
    r = _build(records)
    # expectancy = avg of wins/losses realized_r
    assert r["overall_stats"]["expectancy_r"] == round((4.0 + 1.0 - 1.0) / 3.0, 4)
    assert r["overall_stats"]["win_rate"] == round(2 / 3, 4)
    assert r["overall_stats"]["avg_realized_r"] == round((4.0 + 1.0 - 1.0) / 3.0, 4)


# --- Edge status rules ---

def test_edge_status_in_allowed_set_always():
    for rs in (
        [],
        [_rec()],
        [_rec(status="OPEN", result="STILL_OPEN", realized_r=None)],
        [_rec(status="CLOSED", result="TP2", realized_r=4.0) for _ in range(120)],
    ):
        r = _build(rs)
        assert r["edge_quality"]["edge_status"] in ALLOWED_EDGE_STATUS
        assert r["sample_summary"]["sample_status"] in ALLOWED_SAMPLE_STATUS


def test_below_30_blocks_validated_or_promising():
    records = [_rec(status="CLOSED", result="TP2", realized_r=4.0) for _ in range(29)]
    r = _build(records)
    assert r["edge_quality"]["edge_status"] in {"NO_EDGE_CLAIM", "RESEARCH_ONLY"}


# --- Reason codes / safety / required fields ---

def test_reason_codes_not_empty():
    for rs in ([], [_rec()], [_rec(status="OPEN", result="STILL_OPEN", realized_r=None)]):
        r = _build(rs)
        assert isinstance(r["reason_codes"], list)
        assert len(r["reason_codes"]) > 0
        assert any("SAFE_TO_OPEN_REAL_TRADE_FALSE" in c for c in r["reason_codes"])


def test_safety_flags_always_false():
    for rs in (
        [],
        [_rec(status="CLOSED", result="TP2", realized_r=4.0)],
        [_rec(status="CLOSED", result="SL", realized_r=-1.0)],
    ):
        r = _build(rs)
        es = r["execution_safety"]
        assert es["safe_to_open_real_trade"] is False
        assert es["private_api_used"] is False
        assert es["live_order_sent"] is False


_REQUIRED = [
    "timestamp_utc", "block_id", "symbol", "source", "input_status",
    "sample_summary", "overall_stats", "by_side", "by_grade",
    "by_setup_context", "by_scenario_label", "by_decision",
    "edge_quality", "best_observed_conditions", "worst_observed_conditions",
    "limitations", "data_quality", "reason_codes", "feeds_next",
    "execution_safety",
]


def test_required_fields_present_and_feeds_next():
    r = _build([_rec()])
    for f in _REQUIRED:
        assert f in r, f"missing field: {f}"
    assert r["block_id"] == "S22_EDGE_MATRIX_V2"
    assert "S23_SIMPLE_BRAIN_V2" in r["feeds_next"]["next_blocks"]


# --- Append-only persistence ---

def test_runner_creates_outputs_and_appends(monkeypatch):
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        monkeypatch.setattr(em, "STATE_DIR", tmp / "state")
        monkeypatch.setattr(em, "DATA_DIR", tmp / "data")
        monkeypatch.setattr(em, "REPORTS_DIR", tmp / "reports")
        monkeypatch.setattr(em, "OUTCOME_HISTORY_PATH", tmp / "data" / "outcome_monitor_history.jsonl")
        monkeypatch.setattr(em, "LATEST_OUTCOME_PATH", tmp / "state" / "latest_outcome_monitor.json")
        monkeypatch.setattr(em, "LATEST_MATRIX_PATH", tmp / "state" / "latest_edge_matrix_v2.json")
        monkeypatch.setattr(em, "S22_STATE_PATH", tmp / "state" / "s22_edge_matrix_v2_state.json")
        monkeypatch.setattr(em, "MATRIX_HISTORY_PATH", tmp / "data" / "edge_matrix_v2_history.jsonl")
        monkeypatch.setattr(em, "REPORT_PATH", tmp / "reports" / "s22_edge_matrix_v2_latest_report.md")

        (tmp / "state").mkdir(parents=True, exist_ok=True)
        (tmp / "data").mkdir(parents=True, exist_ok=True)
        records = [
            _rec(status="CLOSED", result="TP2", realized_r=4.0),
            _rec(status="CLOSED", result="SL", realized_r=-1.0),
            _rec(status="OPEN", result="STILL_OPEN", realized_r=None),
        ]
        with (tmp / "data" / "outcome_monitor_history.jsonl").open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
        (tmp / "state" / "latest_outcome_monitor.json").write_text(json.dumps(records[0]))

        r1 = run_edge_matrix_v2()
        r2 = run_edge_matrix_v2()

        assert (tmp / "state" / "latest_edge_matrix_v2.json").exists()
        assert (tmp / "state" / "s22_edge_matrix_v2_state.json").exists()
        assert (tmp / "data" / "edge_matrix_v2_history.jsonl").exists()
        assert (tmp / "reports" / "s22_edge_matrix_v2_latest_report.md").exists()

        lines = (tmp / "data" / "edge_matrix_v2_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # append-only

        assert r1["sample_summary"]["total_records"] == 3
        assert r1["overall_stats"]["win_count"] == 1
        assert r2["overall_stats"]["loss_count"] == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
