from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import src.simple.sample_accumulation_edge_review as s30


def _tmp_dir() -> Path:
    base = Path("tmp_pytest_s30")
    base.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base))


def _patch_paths(tmp_dir: Path) -> None:
    s30.STATE_DIR = tmp_dir / "state"
    s30.DATA_DIR = tmp_dir / "data"
    s30.REPORTS_DIR = tmp_dir / "reports"
    s30.OUTCOME_HISTORY_PATH = s30.DATA_DIR / "outcome_monitor_history.jsonl"
    s30.LIFECYCLE_HISTORY_PATH = s30.DATA_DIR / "paper_lifecycle_history.jsonl"
    s30.SETUP_CLASSIFIER_HISTORY_PATH = s30.DATA_DIR / "setup_classifier_v2_history.jsonl"
    s30.DECISION_GATE_HISTORY_PATH = s30.DATA_DIR / "decision_gate_history.jsonl"
    s30.TRADE_PLAN_HISTORY_PATH = s30.DATA_DIR / "trade_plan_history.jsonl"
    s30.SETUP_CONTEXT_HISTORY_PATH = s30.DATA_DIR / "setup_context_history.jsonl"
    s30.SCENARIO_TRIGGER_HISTORY_PATH = s30.DATA_DIR / "scenario_trigger_history.jsonl"
    s30.EDGE_MATRIX_HISTORY_PATH = s30.DATA_DIR / "edge_matrix_v2_history.jsonl"
    s30.LATEST_OUTCOME_PATH = s30.STATE_DIR / "latest_outcome_monitor.json"
    s30.LATEST_LIFECYCLE_PATH = s30.STATE_DIR / "latest_paper_lifecycle.json"
    s30.LATEST_SETUP_CLASSIFIER_PATH = s30.STATE_DIR / "latest_setup_classifier_v2.json"
    s30.LATEST_DECISION_GATE_PATH = s30.STATE_DIR / "latest_decision_gate.json"
    s30.LATEST_TRADE_PLAN_PATH = s30.STATE_DIR / "latest_trade_plan.json"
    s30.LATEST_EDGE_MATRIX_PATH = s30.STATE_DIR / "latest_edge_matrix_v2.json"
    s30.LATEST_SIMPLE_BRAIN_PATH = s30.STATE_DIR / "latest_simple_brain_v2.json"
    s30.LATEST_CHAIN_AUDIT_PATH = s30.STATE_DIR / "latest_full_chain_truth_audit.json"
    s30.LATEST_QUALITY_AUDIT_PATH = s30.STATE_DIR / "latest_live_flow_quality_audit.json"
    s30.LATEST_STATE_PATH = s30.STATE_DIR / "latest_sample_accumulation_edge_review.json"
    s30.S30_STATE_PATH = s30.STATE_DIR / "s30_sample_accumulation_edge_review_state.json"
    s30.HISTORY_PATH = s30.DATA_DIR / "sample_accumulation_edge_review_history.jsonl"
    s30.REPORT_PATH = s30.REPORTS_DIR / "s30_sample_accumulation_edge_review_latest_report.md"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def _outcome(
    idx: int,
    *,
    status: str = "CLOSED",
    result: str = "TP1",
    lifecycle_id: str | None = None,
    side: str = "LONG",
    realized_r: float | None = 1.0,
) -> dict:
    ts = f"2026-05-11T00:00:{idx:02d}Z"
    return {
        "timestamp_utc": ts,
        "block_id": "S21_OUTCOME_MONITOR",
        "symbol": "BTCUSDT",
        "source": "S20_PAPER_LIFECYCLE_TRACKER",
        "input_status": "OK",
        "outcome_status": status,
        "outcome_result": result,
        "lifecycle_id": lifecycle_id or f"lc-{idx}",
        "side": side,
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "tp1": 101.0,
        "tp2": 102.0,
        "final_price": 101.0,
        "realized_r": realized_r,
        "mfe_r": 1.2 if realized_r is not None else 0.0,
        "mae_r": -0.4 if realized_r is not None else 0.0,
        "setup_context_snapshot": {"setup_context_label": "STRONG_LONG_CONTEXT", "confidence": 0.82},
        "scenario_trigger_snapshot": {"scenario_label": "LONG_CONTINUATION"},
        "decision_snapshot": {"decision": "ALLOW_PAPER", "final_grade": "A"},
        "trade_plan_snapshot": {"rr_tp2": 2.0},
        "data_quality": {"score": 1.0, "level": "HIGH"},
        "reason_codes": ["SYMBOL_BTCUSDT"],
        "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
    }


def _setup(idx: int, *, lifecycle_id: str | None = None, setup_class: str = "L2_LONG_CONTINUATION", setup_family: str = "CONTINUATION", setup_grade: str = "A") -> dict:
    return {
        "timestamp_utc": f"2026-05-11T00:00:{idx:02d}Z",
        "block_id": "S29_SETUP_CLASSIFIER_V2",
        "symbol": "BTCUSDT",
        "setup_class": setup_class,
        "setup_family": setup_family,
        "setup_grade": setup_grade,
        "setup_confidence": 0.82,
        "no_trade_reasons": ["RR_NOT_EVALUATED_YET"],
        "quality_component": {"quality_label": "HIGH"},
        "structure_component": {"bias": "BULLISH_STRUCTURE"},
        "liquidity_component": {"bias": "BID_SUPPORT"},
        "lifecycle_id": lifecycle_id or f"lc-{idx}",
    }


def _decision(idx: int, *, lifecycle_id: str | None = None, decision: str = "ALLOW_PAPER") -> dict:
    return {"timestamp_utc": f"2026-05-11T00:00:{idx:02d}Z", "decision": decision, "lifecycle_id": lifecycle_id or f"lc-{idx}"}


def _plan(idx: int, *, lifecycle_id: str | None = None) -> dict:
    return {"timestamp_utc": f"2026-05-11T00:00:{idx:02d}Z", "rr_tp2": 2.0, "lifecycle_id": lifecycle_id or f"lc-{idx}"}


def _context(idx: int, *, lifecycle_id: str | None = None) -> dict:
    return {"timestamp_utc": f"2026-05-11T00:00:{idx:02d}Z", "setup_context_label": "STRONG_LONG_CONTEXT", "lifecycle_id": lifecycle_id or f"lc-{idx}"}


def _scenario(idx: int, *, lifecycle_id: str | None = None) -> dict:
    return {"timestamp_utc": f"2026-05-11T00:00:{idx:02d}Z", "scenario_label": "LONG_CONTINUATION", "lifecycle_id": lifecycle_id or f"lc-{idx}"}


def _lifecycle(idx: int, *, lifecycle_id: str | None = None) -> dict:
    return {"timestamp_utc": f"2026-05-11T00:00:{idx:02d}Z", "lifecycle_id": lifecycle_id or f"lc-{idx}", "lifecycle_status": "CLOSED"}


def _edge_hist() -> list[dict]:
    return [{"timestamp_utc": "2026-05-11T00:00:00Z", "edge_quality": {"edge_status": "NO_EDGE_CLAIM"}}]


def _seed(tmp_dir: Path, outcomes: list[dict], setups: list[dict] | None = None, decisions: list[dict] | None = None, plans: list[dict] | None = None, contexts: list[dict] | None = None, scenarios: list[dict] | None = None, lifecycles: list[dict] | None = None) -> None:
    _patch_paths(tmp_dir)
    _write_jsonl(s30.OUTCOME_HISTORY_PATH, outcomes)
    _write_jsonl(s30.LIFECYCLE_HISTORY_PATH, lifecycles or [_lifecycle(i + 1, lifecycle_id=o.get("lifecycle_id")) for i, o in enumerate(outcomes)])
    _write_jsonl(s30.SETUP_CLASSIFIER_HISTORY_PATH, setups or [_setup(i + 1, lifecycle_id=o.get("lifecycle_id")) for i, o in enumerate(outcomes)])
    _write_jsonl(s30.DECISION_GATE_HISTORY_PATH, decisions or [_decision(i + 1, lifecycle_id=o.get("lifecycle_id")) for i, o in enumerate(outcomes)])
    _write_jsonl(s30.TRADE_PLAN_HISTORY_PATH, plans or [_plan(i + 1, lifecycle_id=o.get("lifecycle_id")) for i, o in enumerate(outcomes)])
    _write_jsonl(s30.SETUP_CONTEXT_HISTORY_PATH, contexts or [_context(i + 1, lifecycle_id=o.get("lifecycle_id")) for i, o in enumerate(outcomes)])
    _write_jsonl(s30.SCENARIO_TRIGGER_HISTORY_PATH, scenarios or [_scenario(i + 1, lifecycle_id=o.get("lifecycle_id")) for i, o in enumerate(outcomes)])
    _write_jsonl(s30.EDGE_MATRIX_HISTORY_PATH, _edge_hist())
    s30.LATEST_OUTCOME_PATH.parent.mkdir(parents=True, exist_ok=True)
    s30.LATEST_OUTCOME_PATH.write_text(json.dumps(outcomes[-1] if outcomes else _outcome(1, status="NO_OUTCOME", result="NO_LIFECYCLE", realized_r=None, lifecycle_id=None)), encoding="utf-8")
    s30.LATEST_LIFECYCLE_PATH.write_text(json.dumps((lifecycles or [_lifecycle(1)])[0]), encoding="utf-8")
    s30.LATEST_SETUP_CLASSIFIER_PATH.write_text(json.dumps((setups or [_setup(1)])[0]), encoding="utf-8")
    s30.LATEST_DECISION_GATE_PATH.write_text(json.dumps((decisions or [_decision(1)])[0]), encoding="utf-8")
    s30.LATEST_TRADE_PLAN_PATH.write_text(json.dumps((plans or [_plan(1)])[0]), encoding="utf-8")
    s30.LATEST_EDGE_MATRIX_PATH.write_text(json.dumps({"symbol": "BTCUSDT"}), encoding="utf-8")
    s30.LATEST_SIMPLE_BRAIN_PATH.write_text(json.dumps({"brain_status": "RESEARCH_READY"}), encoding="utf-8")
    s30.LATEST_CHAIN_AUDIT_PATH.write_text(json.dumps({"telegram_signal_audit": {"SENT": 0}}), encoding="utf-8")
    s30.LATEST_QUALITY_AUDIT_PATH.write_text(json.dumps({"quality_label": "OK"}), encoding="utf-8")


def _run(tmp_dir: Path) -> dict:
    return s30.run_sample_accumulation_edge_review()


def test_handles_missing_histories_safely():
    d = _tmp_dir()
    _patch_paths(d)
    result = _run(d)
    assert result["input_status"] in ("MISSING", "PARTIAL")
    shutil.rmtree(d, ignore_errors=True)


def test_handles_no_outcomes():
    d = _tmp_dir()
    _seed(d, [])
    result = _run(d)
    assert result["sample_summary"]["total_outcome_records"] >= 0
    shutil.rmtree(d, ignore_errors=True)


def test_excludes_still_open_from_win_loss():
    d = _tmp_dir()
    _seed(d, [_outcome(1, status="OPEN", result="STILL_OPEN", realized_r=None)])
    result = _run(d)
    assert result["overall_outcome_stats"]["win_count"] == 0
    assert result["overall_outcome_stats"]["loss_count"] == 0
    shutil.rmtree(d, ignore_errors=True)


def test_excludes_no_lifecycle_from_win_loss():
    d = _tmp_dir()
    _seed(d, [_outcome(1, status="NO_OUTCOME", result="NO_LIFECYCLE", lifecycle_id=None, realized_r=None)])
    result = _run(d)
    assert result["overall_outcome_stats"]["win_count"] == 0
    assert result["overall_outcome_stats"]["loss_count"] == 0
    shutil.rmtree(d, ignore_errors=True)


def test_counts_tp1_tp2_as_wins():
    d = _tmp_dir()
    _seed(d, [_outcome(1, result="TP1", realized_r=1.0), _outcome(2, result="TP2", realized_r=2.0)])
    result = _run(d)
    assert result["overall_outcome_stats"]["win_count"] == 2
    shutil.rmtree(d, ignore_errors=True)


def test_counts_sl_as_loss():
    d = _tmp_dir()
    _seed(d, [_outcome(1, result="SL", realized_r=-1.0)])
    result = _run(d)
    assert result["overall_outcome_stats"]["loss_count"] == 1
    shutil.rmtree(d, ignore_errors=True)


def test_handles_invalidated_separately():
    d = _tmp_dir()
    _seed(d, [_outcome(1, result="INVALIDATED", realized_r=0.0)])
    result = _run(d)
    assert result["sample_summary"]["invalidated_count"] == 1
    shutil.rmtree(d, ignore_errors=True)


def test_computes_win_rate():
    d = _tmp_dir()
    _seed(d, [_outcome(1, result="TP1", realized_r=1.0), _outcome(2, result="SL", realized_r=-1.0)])
    result = _run(d)
    assert result["overall_outcome_stats"]["win_rate"] == 0.5
    shutil.rmtree(d, ignore_errors=True)


def test_computes_expectancy_r():
    d = _tmp_dir()
    _seed(d, [_outcome(1, result="TP2", realized_r=2.0), _outcome(2, result="SL", realized_r=-1.0)])
    result = _run(d)
    assert result["overall_outcome_stats"]["expectancy_r"] == 0.5
    shutil.rmtree(d, ignore_errors=True)


def test_computes_milestone_below_100():
    d = _tmp_dir()
    _seed(d, [_outcome(i + 1, result="TP1", realized_r=1.0) for i in range(10)])
    result = _run(d)
    assert result["milestone_status"]["current_milestone"] == "BELOW_100"
    shutil.rmtree(d, ignore_errors=True)


def test_computes_milestone_reached_100():
    d = _tmp_dir()
    _seed(d, [_outcome(i + 1, result="TP1", realized_r=1.0) for i in range(100)])
    result = _run(d)
    assert result["milestone_status"]["current_milestone"] == "REACHED_100"
    shutil.rmtree(d, ignore_errors=True)


def test_computes_milestone_reached_500():
    d = _tmp_dir()
    _seed(d, [_outcome(i + 1, result="TP1", realized_r=1.0) for i in range(500)])
    result = _run(d)
    assert result["milestone_status"]["current_milestone"] == "REACHED_500"
    shutil.rmtree(d, ignore_errors=True)


def test_computes_milestone_reached_1000():
    d = _tmp_dir()
    _seed(d, [_outcome(i + 1, result="TP1", realized_r=1.0) for i in range(1000)])
    result = _run(d)
    assert result["milestone_status"]["current_milestone"] == "REACHED_1000"
    shutil.rmtree(d, ignore_errors=True)


def test_blocks_edge_claim_under_100_samples():
    d = _tmp_dir()
    _seed(d, [_outcome(i + 1, result="TP1", realized_r=1.0) for i in range(99)])
    result = _run(d)
    assert result["edge_claim_policy"]["edge_claim_allowed"] is False
    shutil.rmtree(d, ignore_errors=True)


def test_allows_only_early_candidate_over_100_with_positive_expectancy():
    d = _tmp_dir()
    _seed(d, [_outcome(i + 1, result="TP1", realized_r=1.0) for i in range(120)])
    result = _run(d)
    assert result["edge_claim_policy"]["edge_status"] == "EARLY_EDGE_CANDIDATE"
    shutil.rmtree(d, ignore_errors=True)


def test_allows_promising_edge_over_500_with_positive_expectancy():
    d = _tmp_dir()
    _seed(d, [_outcome(i + 1, result="TP1", realized_r=1.0) for i in range(520)])
    result = _run(d)
    assert result["edge_claim_policy"]["edge_status"] == "PROMISING_EDGE"
    shutil.rmtree(d, ignore_errors=True)


def test_allows_validated_edge_over_1000_with_positive_expectancy():
    d = _tmp_dir()
    outcomes = [_outcome(i + 1, result="TP1", realized_r=1.0, lifecycle_id=f"a-{i}") for i in range(600)] + [_outcome(700 + i, result="TP2", realized_r=2.0, lifecycle_id=f"b-{i}") for i in range(500)]
    setups = [_setup(i + 1, lifecycle_id=o["lifecycle_id"], setup_class="L2_LONG_CONTINUATION") for i, o in enumerate(outcomes[:600])] + [_setup(700 + i, lifecycle_id=o["lifecycle_id"], setup_class="L4_LONG_SWEEP_RECLAIM", setup_family="SWEEP_RECLAIM") for i, o in enumerate(outcomes[600:])]
    _seed(d, outcomes, setups=setups)
    result = _run(d)
    assert result["edge_claim_policy"]["edge_status"] == "VALIDATED_EDGE"
    shutil.rmtree(d, ignore_errors=True)


def test_groups_by_setup_class():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    result = _run(d)
    assert "L2_LONG_CONTINUATION" in result["by_setup_class"]
    shutil.rmtree(d, ignore_errors=True)


def test_groups_by_setup_grade():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    result = _run(d)
    assert "A" in result["by_setup_grade"]
    shutil.rmtree(d, ignore_errors=True)


def test_groups_by_setup_family():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    result = _run(d)
    assert "CONTINUATION" in result["by_setup_family"]
    shutil.rmtree(d, ignore_errors=True)


def test_groups_missing_fields_as_unknown():
    d = _tmp_dir()
    _seed(d, [_outcome(1)], setups=[{"timestamp_utc": "2026-05-11T00:00:01Z", "lifecycle_id": "lc-1"}])
    result = _run(d)
    assert "UNKNOWN" in result["by_setup_class"]
    shutil.rmtree(d, ignore_errors=True)


def test_reports_insufficient_group_sample():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    result = _run(d)
    assert result["by_setup_class"]["L2_LONG_CONTINUATION"]["quality"] == "INSUFFICIENT_GROUP_SAMPLE"
    shutil.rmtree(d, ignore_errors=True)


def test_reports_sample_gaps():
    d = _tmp_dir()
    _seed(d, [_outcome(1, status="NO_OUTCOME", result="NO_LIFECYCLE", lifecycle_id=None, realized_r=None)])
    result = _run(d)
    assert result["sample_gaps"]
    shutil.rmtree(d, ignore_errors=True)


def test_writes_latest_json():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    _run(d)
    assert s30.LATEST_STATE_PATH.exists()
    shutil.rmtree(d, ignore_errors=True)


def test_writes_markdown_report():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    _run(d)
    assert s30.REPORT_PATH.exists()
    shutil.rmtree(d, ignore_errors=True)


def test_appends_jsonl_history():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    _run(d)
    _run(d)
    lines = [line for line in s30.HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    shutil.rmtree(d, ignore_errors=True)


def test_preserves_safety_flags():
    d = _tmp_dir()
    _seed(d, [_outcome(1)])
    result = _run(d)
    assert result["execution_safety"]["safe_to_open_real_trade"] is False
    assert result["execution_safety"]["private_api_used"] is False
    assert result["execution_safety"]["live_order_sent"] is False
    shutil.rmtree(d, ignore_errors=True)


def test_s24_integration_includes_s30():
    from src.simple.production_observer import _MODULE_CHAIN

    labels = [label for _, _, label in _MODULE_CHAIN]
    assert "S30_SAMPLE_ACCUMULATION_EDGE_REVIEW" in labels
    assert labels.index("S22_EDGE_MATRIX_V2") < labels.index("S30_SAMPLE_ACCUMULATION_EDGE_REVIEW") < labels.index("S23_SIMPLE_BRAIN_V2")
