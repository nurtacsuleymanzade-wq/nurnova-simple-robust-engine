from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

import src.simple.setup_classifier_v2 as s29


def _tmp_dir() -> Path:
    base = Path("tmp_pytest_s29")
    base.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base))


def _patch_paths(tmp_dir: Path) -> None:
    s29.STATE_DIR = tmp_dir / "state"
    s29.DATA_DIR = tmp_dir / "data"
    s29.REPORTS_DIR = tmp_dir / "reports"
    s29.LATEST_STATE_PATH = s29.STATE_DIR / "latest_setup_classifier_v2.json"
    s29.S29_STATE_PATH = s29.STATE_DIR / "s29_setup_classifier_v2_state.json"
    s29.HISTORY_PATH = s29.DATA_DIR / "setup_classifier_v2_history.jsonl"
    s29.REPORT_PATH = s29.REPORTS_DIR / "s29_setup_classifier_v2_latest_report.md"
    s29.INPUT_PATHS = {name: s29.STATE_DIR / f"{name}.json" for name in s29.INPUT_PATHS}


def _write_inputs(tmp_dir: Path, overrides: dict[str, dict] | None = None, missing: set[str] | None = None) -> None:
    overrides = overrides or {}
    missing = missing or set()
    defaults = _base_inputs()
    for name, path in s29.INPUT_PATHS.items():
        if name in missing:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = overrides.get(name, defaults[name])
        path.write_text(json.dumps(payload), encoding="utf-8")


def _base_inputs() -> dict[str, dict]:
    return {
        "flow_state": {"symbol": "BTCUSDT"},
        "flow_evidence": {
            "symbol": "BTCUSDT",
            "evidence_label": "STRONG_LONG_PRESSURE",
            "evidence_score": 4.5,
            "confidence": 0.82,
            "data_quality": {"level": "OK", "score": 0.9},
        },
        "flow_persistence": {
            "symbol": "BTCUSDT",
            "persistence_label": "SUSTAINED_LONG_PRESSURE",
            "persistence_score": 4.2,
            "direction_label": "LONG",
            "continuation_quality": "STRONG",
            "decay_risk": False,
            "flip_risk": False,
        },
        "setup_context": {
            "symbol": "BTCUSDT",
            "direction_bias": "LONG",
            "confidence": 0.84,
        },
        "scenario_trigger": {
            "symbol": "BTCUSDT",
            "scenario_label": "LONG_CONTINUATION",
            "direction_bias": "LONG",
            "trigger_state": "READY_FOR_ENTRY",
            "trigger_strength": 0.84,
            "trigger_confidence": 0.8,
        },
        "trade_plan": {"symbol": "BTCUSDT", "plan_status": "PLAN_READY"},
        "decision_gate": {"symbol": "BTCUSDT", "decision": "ALLOW_PAPER"},
        "quality_audit": {
            "symbol": "BTCUSDT",
            "quality_label": "OK",
            "quality_score": 0.9,
            "data_quality": {"level": "OK", "score": 0.9},
            "stale_data": False,
        },
        "liquidity_memory": {
            "symbol": "BTCUSDT",
            "depth_available": True,
            "fallback_used": False,
            "liquidity_memory_status": "WALLS_DETECTED",
            "liquidity_bias": "BID_SUPPORT",
            "wall_events": [],
            "absorption_candidates": [],
            "broken_wall_candidates": [],
        },
        "market_structure": {
            "symbol": "BTCUSDT",
            "structure_bias": "BULLISH_STRUCTURE",
            "structure_strength": 0.88,
            "liquidity_sweep_status": "NO_SWEEP",
            "choch_status": "NO_CHOCH",
            "bos_status": "BULLISH_BOS",
            "setup_readiness_hint": "STRUCTURE_SUPPORTS_LONG",
        },
        "edge_matrix": {
            "symbol": "BTCUSDT",
            "edge_quality": {"edge_status": "PROMISING_EDGE", "caution_reason": "USABLE_BUT_NOT_ROBUST_SAMPLE"},
            "sample_summary": {"sample_status": "USABLE_SAMPLE", "usable_closed_records": 45},
        },
        "full_chain_truth_audit": {
            "symbol": "BTCUSDT",
            "system_running_status": "OK",
            "data_quality": {"level": {"level": "OK", "score": 0.9}, "score": 0.9},
        },
    }


def _run(tmp_dir: Path, overrides: dict[str, dict] | None = None, missing: set[str] | None = None) -> dict:
    _patch_paths(tmp_dir)
    _write_inputs(tmp_dir, overrides=overrides, missing=missing)
    return s29.run_setup_classifier_v2()


def test_handles_missing_inputs_safely():
    d = _tmp_dir()
    result = _run(d, missing={"market_structure", "liquidity_memory"})
    assert result["setup_status"] in ("INSUFFICIENT_DATA", "BLOCKED", "WATCHLIST")
    assert "MISSING_INPUTS" in result["reason_codes"]
    shutil.rmtree(d, ignore_errors=True)


def test_outputs_no_setup_when_flow_neutral():
    d = _tmp_dir()
    result = _run(d, overrides={"flow_evidence": {"symbol": "BTCUSDT", "evidence_label": "NEUTRAL_FLOW", "evidence_score": 0.0, "confidence": 0.2}})
    assert result["setup_status"] == "NO_SETUP"
    assert result["setup_class"] == "NO_SETUP_CLASS"
    shutil.rmtree(d, ignore_errors=True)


def test_outputs_watch_when_flow_weak_but_directional():
    d = _tmp_dir()
    result = _run(d, overrides={"flow_evidence": {"symbol": "BTCUSDT", "evidence_label": "WEAK_LONG_PRESSURE", "evidence_score": 2.0, "confidence": 0.55}})
    assert result["setup_status"] in ("WATCHLIST", "BLOCKED")
    assert result["setup_grade"] in ("WATCH", "NO_SETUP")
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_l2_long_continuation():
    d = _tmp_dir()
    result = _run(d)
    assert result["setup_class"] == "L2_LONG_CONTINUATION"
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_s2_short_continuation():
    d = _tmp_dir()
    result = _run(d, overrides={
        "flow_evidence": {"symbol": "BTCUSDT", "evidence_label": "STRONG_SHORT_PRESSURE", "evidence_score": -4.5, "confidence": 0.82},
        "flow_persistence": {"symbol": "BTCUSDT", "persistence_label": "SUSTAINED_SHORT_PRESSURE", "persistence_score": -4.2, "direction_label": "SHORT", "continuation_quality": "STRONG", "decay_risk": False, "flip_risk": False},
        "setup_context": {"symbol": "BTCUSDT", "direction_bias": "SHORT", "confidence": 0.84},
        "scenario_trigger": {"symbol": "BTCUSDT", "scenario_label": "SHORT_CONTINUATION", "direction_bias": "SHORT", "trigger_state": "READY_FOR_ENTRY", "trigger_strength": 0.84, "trigger_confidence": 0.8},
        "liquidity_memory": {"symbol": "BTCUSDT", "depth_available": True, "fallback_used": False, "liquidity_memory_status": "WALLS_DETECTED", "liquidity_bias": "ASK_RESISTANCE", "wall_events": [], "absorption_candidates": [], "broken_wall_candidates": []},
        "market_structure": {"symbol": "BTCUSDT", "structure_bias": "BEARISH_STRUCTURE", "structure_strength": 0.88, "liquidity_sweep_status": "NO_SWEEP", "choch_status": "NO_CHOCH", "bos_status": "BEARISH_BOS", "setup_readiness_hint": "STRUCTURE_SUPPORTS_SHORT"},
    })
    assert result["setup_class"] == "S2_SHORT_CONTINUATION"
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_l3_long_reversal():
    d = _tmp_dir()
    result = _run(d, overrides={
        "flow_persistence": {"symbol": "BTCUSDT", "persistence_label": "FADING_SHORT_PRESSURE", "persistence_score": -2.8, "direction_label": "SHORT", "continuation_quality": "WEAK", "decay_risk": True, "flip_risk": True},
        "scenario_trigger": {"symbol": "BTCUSDT", "scenario_label": "LONG_REVERSAL", "direction_bias": "LONG", "trigger_state": "READY_FOR_ENTRY", "trigger_strength": 0.76, "trigger_confidence": 0.74},
        "market_structure": {"symbol": "BTCUSDT", "structure_bias": "BULLISH_STRUCTURE", "structure_strength": 0.82, "liquidity_sweep_status": "NO_SWEEP", "choch_status": "BULLISH_CHOCH", "bos_status": "NO_BOS", "setup_readiness_hint": "STRUCTURE_SUPPORTS_LONG"},
    })
    assert result["setup_class"] == "L3_LONG_REVERSAL"
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_s3_short_reversal():
    d = _tmp_dir()
    result = _run(d, overrides={
        "flow_evidence": {"symbol": "BTCUSDT", "evidence_label": "STRONG_SHORT_PRESSURE", "evidence_score": -4.1, "confidence": 0.79},
        "flow_persistence": {"symbol": "BTCUSDT", "persistence_label": "FADING_LONG_PRESSURE", "persistence_score": 2.8, "direction_label": "LONG", "continuation_quality": "WEAK", "decay_risk": True, "flip_risk": True},
        "setup_context": {"symbol": "BTCUSDT", "direction_bias": "SHORT", "confidence": 0.8},
        "scenario_trigger": {"symbol": "BTCUSDT", "scenario_label": "SHORT_REVERSAL", "direction_bias": "SHORT", "trigger_state": "READY_FOR_ENTRY", "trigger_strength": 0.76, "trigger_confidence": 0.74},
        "liquidity_memory": {"symbol": "BTCUSDT", "depth_available": True, "fallback_used": False, "liquidity_memory_status": "WALLS_DETECTED", "liquidity_bias": "ASK_RESISTANCE", "wall_events": [], "absorption_candidates": [], "broken_wall_candidates": []},
        "market_structure": {"symbol": "BTCUSDT", "structure_bias": "BEARISH_STRUCTURE", "structure_strength": 0.82, "liquidity_sweep_status": "NO_SWEEP", "choch_status": "BEARISH_CHOCH", "bos_status": "NO_BOS", "setup_readiness_hint": "STRUCTURE_SUPPORTS_SHORT"},
    })
    assert result["setup_class"] == "S3_SHORT_REVERSAL"
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_l4_long_sweep_reclaim():
    d = _tmp_dir()
    result = _run(d, overrides={"market_structure": {"symbol": "BTCUSDT", "structure_bias": "BULLISH_STRUCTURE", "structure_strength": 0.86, "liquidity_sweep_status": "SELL_SIDE_SWEEP", "choch_status": "BULLISH_CHOCH", "bos_status": "NO_BOS", "setup_readiness_hint": "STRUCTURE_SUPPORTS_LONG"}})
    assert result["setup_class"] == "L4_LONG_SWEEP_RECLAIM"
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_s4_short_sweep_reclaim():
    d = _tmp_dir()
    result = _run(d, overrides={
        "flow_evidence": {"symbol": "BTCUSDT", "evidence_label": "STRONG_SHORT_PRESSURE", "evidence_score": -4.1, "confidence": 0.79},
        "flow_persistence": {"symbol": "BTCUSDT", "persistence_label": "SUSTAINED_SHORT_PRESSURE", "persistence_score": -4.1, "direction_label": "SHORT", "continuation_quality": "STRONG", "decay_risk": False, "flip_risk": False},
        "setup_context": {"symbol": "BTCUSDT", "direction_bias": "SHORT", "confidence": 0.82},
        "scenario_trigger": {"symbol": "BTCUSDT", "scenario_label": "SHORT_REVERSAL", "direction_bias": "SHORT", "trigger_state": "READY_FOR_ENTRY", "trigger_strength": 0.78, "trigger_confidence": 0.74},
        "liquidity_memory": {"symbol": "BTCUSDT", "depth_available": True, "fallback_used": False, "liquidity_memory_status": "WALLS_DETECTED", "liquidity_bias": "ASK_RESISTANCE", "wall_events": [], "absorption_candidates": [], "broken_wall_candidates": []},
        "market_structure": {"symbol": "BTCUSDT", "structure_bias": "BEARISH_STRUCTURE", "structure_strength": 0.86, "liquidity_sweep_status": "BUY_SIDE_SWEEP", "choch_status": "BEARISH_CHOCH", "bos_status": "NO_BOS", "setup_readiness_hint": "STRUCTURE_SUPPORTS_SHORT"},
    })
    assert result["setup_class"] == "S4_SHORT_SWEEP_RECLAIM"
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_l5_rare_a_plus_long_only_with_all_alignments():
    d = _tmp_dir()
    result = _run(d, overrides={"edge_matrix": {"symbol": "BTCUSDT", "edge_quality": {"edge_status": "VALIDATED_EDGE", "caution_reason": ""}, "sample_summary": {"sample_status": "ROBUST_SAMPLE", "usable_closed_records": 150}}, "quality_audit": {"symbol": "BTCUSDT", "quality_label": "HIGH", "quality_score": 1.0, "data_quality": {"level": "HIGH", "score": 1.0}, "stale_data": False}})
    assert result["setup_class"] == "L5_RARE_A_PLUS_LONG"
    assert result["setup_grade"] == "A_PLUS"
    shutil.rmtree(d, ignore_errors=True)


def test_classifies_s5_rare_a_plus_short_only_with_all_alignments():
    d = _tmp_dir()
    result = _run(d, overrides={
        "flow_evidence": {"symbol": "BTCUSDT", "evidence_label": "STRONG_SHORT_PRESSURE", "evidence_score": -5.0, "confidence": 0.9, "data_quality": {"level": "HIGH", "score": 1.0}},
        "flow_persistence": {"symbol": "BTCUSDT", "persistence_label": "SUSTAINED_SHORT_PRESSURE", "persistence_score": -4.8, "direction_label": "SHORT", "continuation_quality": "STRONG", "decay_risk": False, "flip_risk": False},
        "setup_context": {"symbol": "BTCUSDT", "direction_bias": "SHORT", "confidence": 0.9},
        "scenario_trigger": {"symbol": "BTCUSDT", "scenario_label": "SHORT_CONTINUATION", "direction_bias": "SHORT", "trigger_state": "READY_FOR_ENTRY", "trigger_strength": 0.92, "trigger_confidence": 0.86},
        "liquidity_memory": {"symbol": "BTCUSDT", "depth_available": True, "fallback_used": False, "liquidity_memory_status": "WALLS_DETECTED", "liquidity_bias": "ASK_RESISTANCE", "wall_events": [], "absorption_candidates": [], "broken_wall_candidates": []},
        "market_structure": {"symbol": "BTCUSDT", "structure_bias": "BEARISH_STRUCTURE", "structure_strength": 0.95, "liquidity_sweep_status": "NO_SWEEP", "choch_status": "NO_CHOCH", "bos_status": "BEARISH_BOS", "setup_readiness_hint": "STRUCTURE_SUPPORTS_SHORT"},
        "edge_matrix": {"symbol": "BTCUSDT", "edge_quality": {"edge_status": "VALIDATED_EDGE", "caution_reason": ""}, "sample_summary": {"sample_status": "ROBUST_SAMPLE", "usable_closed_records": 150}},
        "quality_audit": {"symbol": "BTCUSDT", "quality_label": "HIGH", "quality_score": 1.0, "data_quality": {"level": "HIGH", "score": 1.0}, "stale_data": False},
    })
    assert result["setup_class"] == "S5_RARE_A_PLUS_SHORT"
    assert result["setup_grade"] == "A_PLUS"
    shutil.rmtree(d, ignore_errors=True)


def test_downgrades_when_quality_is_degraded():
    d = _tmp_dir()
    result = _run(d, overrides={"quality_audit": {"symbol": "BTCUSDT", "quality_label": "DEGRADED", "quality_score": 0.45, "data_quality": {"level": "DEGRADED", "score": 0.45}, "stale_data": False}})
    assert result["setup_grade"] in ("B", "WATCH", "NO_SETUP")
    shutil.rmtree(d, ignore_errors=True)


def test_blocks_when_data_is_stale_or_no_data():
    d = _tmp_dir()
    result = _run(d, overrides={"quality_audit": {"symbol": "BTCUSDT", "quality_label": "STALE", "quality_score": 0.1, "data_quality": {"level": "STALE", "score": 0.1}, "stale_data": True}})
    assert result["setup_status"] == "INSUFFICIENT_DATA"
    shutil.rmtree(d, ignore_errors=True)


def test_blocks_or_downgrades_structure_conflict():
    d = _tmp_dir()
    result = _run(d, overrides={"market_structure": {"symbol": "BTCUSDT", "structure_bias": "BEARISH_STRUCTURE", "structure_strength": 0.9, "liquidity_sweep_status": "NO_SWEEP", "choch_status": "NO_CHOCH", "bos_status": "BEARISH_BOS", "setup_readiness_hint": "STRUCTURE_SUPPORTS_SHORT"}})
    assert result["tradeability"] in ("BLOCKED_BY_STRUCTURE", "WATCH_ONLY", "NO_TRADE")
    shutil.rmtree(d, ignore_errors=True)


def test_blocks_or_downgrades_liquidity_conflict():
    d = _tmp_dir()
    result = _run(d, overrides={"liquidity_memory": {"symbol": "BTCUSDT", "depth_available": True, "fallback_used": False, "liquidity_memory_status": "WALLS_DETECTED", "liquidity_bias": "ASK_RESISTANCE", "wall_events": [], "absorption_candidates": [], "broken_wall_candidates": []}})
    assert result["tradeability"] in ("BLOCKED_BY_LIQUIDITY", "WATCH_ONLY", "NO_TRADE")
    shutil.rmtree(d, ignore_errors=True)


def test_marks_edge_not_validated_when_sample_too_small():
    d = _tmp_dir()
    result = _run(d, overrides={"edge_matrix": {"symbol": "BTCUSDT", "edge_quality": {"edge_status": "NO_EDGE_CLAIM", "caution_reason": "NO_CLOSED_RESOLVED_SAMPLES"}, "sample_summary": {"sample_status": "INSUFFICIENT_SAMPLE", "usable_closed_records": 0}}})
    assert "EDGE_NOT_VALIDATED" in result["reason_codes"]
    shutil.rmtree(d, ignore_errors=True)


def test_component_scores_within_bounds():
    d = _tmp_dir()
    result = _run(d)
    for key in ("flow_component", "persistence_component", "quality_component", "structure_component", "liquidity_component", "scenario_component"):
        assert 0.0 <= result[key]["score"] <= 1.0
    shutil.rmtree(d, ignore_errors=True)


def test_setup_score_within_bounds():
    d = _tmp_dir()
    result = _run(d)
    assert 0.0 <= result["setup_score"] <= 1.0
    assert 0.0 <= result["setup_confidence"] <= 1.0
    shutil.rmtree(d, ignore_errors=True)


def test_reason_codes_not_empty():
    d = _tmp_dir()
    result = _run(d)
    assert result["reason_codes"]
    shutil.rmtree(d, ignore_errors=True)


def test_writes_latest_json():
    d = _tmp_dir()
    _run(d)
    assert s29.LATEST_STATE_PATH.exists()
    shutil.rmtree(d, ignore_errors=True)


def test_writes_markdown_report():
    d = _tmp_dir()
    _run(d)
    assert s29.REPORT_PATH.exists()
    assert "S29 Setup Classifier V2" in s29.REPORT_PATH.read_text(encoding="utf-8")
    shutil.rmtree(d, ignore_errors=True)


def test_appends_jsonl_history():
    d = _tmp_dir()
    _run(d)
    _run(d)
    lines = [line for line in s29.HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    shutil.rmtree(d, ignore_errors=True)


def test_preserves_safety_flags():
    d = _tmp_dir()
    result = _run(d)
    assert result["execution_safety"]["safe_to_open_real_trade"] is False
    assert result["execution_safety"]["private_api_used"] is False
    assert result["execution_safety"]["live_order_sent"] is False
    shutil.rmtree(d, ignore_errors=True)


def test_s24_integration_includes_s29():
    from src.simple.production_observer import _MODULE_CHAIN

    labels = [label for _, _, label in _MODULE_CHAIN]
    assert "S29_SETUP_CLASSIFIER_V2" in labels
    assert labels.index("S28_MARKET_STRUCTURE_V2") < labels.index("S29_SETUP_CLASSIFIER_V2") < labels.index("S22_EDGE_MATRIX_V2")
