"""S11.4 Pre-VPS Readiness Report — NOVA SIMPLE ROBUST ENGINE v1.

Audits local state to determine readiness for long-running VPS deployment.
Research only. No live trading. safe_to_open_real_trade always false.
"""

from __future__ import annotations

import importlib
import json
import pathlib
from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S11_4_PRE_VPS_READINESS_REPORT"
FEEDS_NEXT: dict[str, list[str]] = {"next_blocks": []}

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
TESTS_DIR = ROOT / "tests" / "simple"

_STATE_BLOCKS: list[tuple[str, str]] = [
    ("S1",  "s1_market_truth_state.json"),
    ("S2",  "s2_1s_evidence_state.json"),
    ("S3",  "s3_hybrid_candle_dna_state.json"),
    ("S4",  "s4_quality_weight_state.json"),
    ("S5",  "s5_liquidity_structure_state.json"),
    ("S6",  "s6_setup_candidate_state.json"),
    ("S7",  "s7_trade_plan_decision_state.json"),
    ("S8",  "s8_paper_outcome_state.json"),
    ("S9",  "s9_edge_stats_state.json"),
    ("S10", "s10_simple_brain_state.json"),
    ("S11", "s11_replay_samples_state.json"),
]

_FAKE_SAMPLE_MODULES: list[str] = [
    "src.simple.market_truth_engine",
    "src.simple.lightweight_1s_evidence_engine",
    "src.simple.hybrid_candle_dna_engine",
    "src.simple.quality_weight_engine",
    "src.simple.liquidity_structure_engine",
    "src.simple.setup_candidate_engine",
    "src.simple.trade_plan_decision_engine",
    "src.simple.paper_outcome_tracker",
    "src.simple.edge_stats_engine",
    "src.simple.simple_brain_report_engine",
    "src.simple.replay_sample_runner",
]

_REQUIRED_TEST_FILES: list[str] = [
    "test_market_truth_engine.py",
    "test_lightweight_1s_evidence_engine.py",
    "test_hybrid_candle_dna_engine.py",
    "test_quality_weight_engine.py",
    "test_liquidity_structure_engine.py",
    "test_setup_candidate_engine.py",
    "test_trade_plan_decision_engine.py",
    "test_paper_outcome_tracker.py",
    "test_edge_stats_engine.py",
    "test_simple_brain_report_engine.py",
    "test_replay_sample_runner.py",
    "test_local_pipeline_runner.py",
    "test_sample_schema_validator.py",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _check_state_blocks() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    for label, fname in _STATE_BLOCKS:
        p = STATE_DIR / fname
        if not p.exists():
            critical.append(f"{label}_STATE_FILE_MISSING:{fname}")
            continue
        data = _load_json(p)
        if data is None:
            critical.append(f"{label}_STATE_FILE_INVALID:{fname}")
        elif not data.get("reason_codes"):
            warnings.append(f"{label}_STATE_REASON_CODES_EMPTY")
    return critical, warnings


def _check_replay_samples() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    p = DATA_DIR / "replay_samples.jsonl"
    if not p.exists():
        critical.append("REPLAY_SAMPLES_FILE_MISSING")
        return critical, warnings
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) == 0:
        critical.append("REPLAY_SAMPLES_FILE_EMPTY")
    elif len(lines) < 10:
        warnings.append(f"REPLAY_SAMPLES_LOW_COUNT:{len(lines)}")
    return critical, warnings


def _check_schema_validation() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    p = STATE_DIR / "latest_schema_validation.json"
    if not p.exists():
        critical.append("SCHEMA_VALIDATION_STATE_MISSING")
        return critical, warnings
    data = _load_json(p)
    if data is None:
        critical.append("SCHEMA_VALIDATION_STATE_INVALID")
        return critical, warnings
    summary = data.get("validation_summary", {})
    error_rows = summary.get("error_rows", -1)
    if error_rows != 0:
        warnings.append(f"SCHEMA_VALIDATION_ERRORS:{error_rows}")
    dq_level = data.get("data_quality", {}).get("level", "")
    if dq_level not in ("HIGH", "MEDIUM"):
        warnings.append(f"SCHEMA_VALIDATION_DATA_QUALITY:{dq_level}")
    return critical, warnings


def _check_edge_stats() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    p = STATE_DIR / "latest_edge_stats.json"
    if not p.exists():
        critical.append("EDGE_STATS_STATE_MISSING")
        return critical, warnings
    data = _load_json(p)
    if data is None:
        critical.append("EDGE_STATS_STATE_INVALID")
        return critical, warnings
    count = data.get("edge_eligible_count", 0)
    if count == 0:
        critical.append("EDGE_STATS_NO_ELIGIBLE_TRADES")
    elif count < 5:
        warnings.append(f"EDGE_STATS_LOW_SAMPLE:{count}")
    return critical, warnings


def _check_simple_brain() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    p = STATE_DIR / "latest_simple_brain.json"
    if not p.exists():
        critical.append("SIMPLE_BRAIN_STATE_MISSING")
        return critical, warnings
    data = _load_json(p)
    if data is None:
        critical.append("SIMPLE_BRAIN_STATE_INVALID")
        return critical, warnings
    status = data.get("brain_status", "")
    if status != "READY":
        warnings.append(f"SIMPLE_BRAIN_NOT_READY:{status}")
    safety = data.get("execution_safety", {})
    if safety.get("safe_to_open_real_trade") is not False:
        critical.append("SIMPLE_BRAIN_SAFE_FLAG_VIOLATED")
    return critical, warnings


def _check_local_pipeline() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    p = STATE_DIR / "latest_local_pipeline_run.json"
    if not p.exists():
        critical.append("LOCAL_PIPELINE_STATE_MISSING")
        return critical, warnings
    data = _load_json(p)
    if data is None:
        critical.append("LOCAL_PIPELINE_STATE_INVALID")
        return critical, warnings
    status = data.get("execution_summary", {}).get("pipeline_status", "")
    if status != "COMPLETE":
        warnings.append(f"LOCAL_PIPELINE_NOT_COMPLETE:{status}")
    safety = data.get("execution_safety", {})
    if safety.get("safe_to_open_real_trade") is not False:
        critical.append("LOCAL_PIPELINE_SAFE_FLAG_VIOLATED")
    return critical, warnings


def _check_fake_sample_support() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    for mod_path in _FAKE_SAMPLE_MODULES:
        short = mod_path.split(".")[-1]
        try:
            mod = importlib.import_module(mod_path)
            if not hasattr(mod, "run_fake_sample"):
                critical.append(f"FAKE_SAMPLE_MISSING_IN:{short}")
        except Exception:
            critical.append(f"MODULE_IMPORT_FAILED:{short}")
    return critical, warnings


def _check_test_suite() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    for fname in _REQUIRED_TEST_FILES:
        if not (TESTS_DIR / fname).exists():
            warnings.append(f"TEST_FILE_MISSING:{fname}")
    return critical, warnings


def _check_live_trading_safety() -> tuple[list[str], list[str]]:
    critical: list[str] = []
    warnings: list[str] = []
    if not STATE_DIR.exists():
        return critical, warnings
    for p in STATE_DIR.glob("*.json"):
        data = _load_json(p)
        if data is None:
            continue
        safety = data.get("execution_safety", {})
        if safety.get("safe_to_open_real_trade") is True:
            critical.append(f"LIVE_TRADING_FLAG_SET_IN:{p.name}")
        if safety.get("live_order_sent") is True:
            critical.append(f"LIVE_ORDER_SENT_IN:{p.name}")
        if safety.get("private_api_used") is True:
            critical.append(f"PRIVATE_API_USED_IN:{p.name}")
    return critical, warnings


_AUDIT_CHECKS: list[tuple[str, Any]] = [
    ("S1_S11_STATE_FILES",   _check_state_blocks),
    ("REPLAY_SAMPLES",       _check_replay_samples),
    ("SCHEMA_VALIDATION",    _check_schema_validation),
    ("EDGE_STATS",           _check_edge_stats),
    ("SIMPLE_BRAIN",         _check_simple_brain),
    ("LOCAL_PIPELINE",       _check_local_pipeline),
    ("FAKE_SAMPLE_SUPPORT",  _check_fake_sample_support),
    ("TEST_SUITE",           _check_test_suite),
    ("LIVE_TRADING_SAFETY",  _check_live_trading_safety),
]


def run_readiness_audit(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Run all audit checks and return a standard JSON-contract readiness report."""
    all_critical: list[str] = []
    all_warnings: list[str] = []
    check_results: list[dict[str, Any]] = []

    for check_name, check_fn in _AUDIT_CHECKS:
        critical, warnings = check_fn()
        all_critical.extend(critical)
        all_warnings.extend(warnings)
        check_results.append({
            "check": check_name,
            "passed": len(critical) == 0,
            "critical_items": critical,
            "warnings": warnings,
        })

    n_passed = sum(1 for r in check_results if r["passed"])
    readiness_score = round(n_passed / len(check_results), 4)

    vps_ready = (readiness_score >= 0.8 and len(all_critical) == 0)

    if vps_ready:
        recommended_next_step = "DEPLOY_TO_VPS_OBSERVATION_MODE"
    elif all_critical:
        recommended_next_step = f"RESOLVE_CRITICAL_ITEMS_FIRST:{all_critical[0]}"
    else:
        recommended_next_step = "ADDRESS_WARNINGS_THEN_RERUN_AUDIT"

    if readiness_score >= 0.9:
        dq_level = "HIGH"
    elif readiness_score >= 0.7:
        dq_level = "MEDIUM"
    elif readiness_score >= 0.5:
        dq_level = "LOW"
    else:
        dq_level = "CRITICAL"

    reason_codes = [
        "SOURCE_LOCAL_AUDIT",
        f"SYMBOL_{symbol}",
        f"READINESS_SCORE_{readiness_score}",
        f"CHECKS_PASSED_{n_passed}_OF_{len(check_results)}",
        f"CRITICAL_ITEMS_{len(all_critical)}",
        f"WARNINGS_{len(all_warnings)}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "RESEARCH_ONLY",
        "VPS_READY_TRUE" if vps_ready else "VPS_READY_FALSE",
    ]

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {"source_mode": "LOCAL_AUDIT"},
        "readiness_score": readiness_score,
        "vps_ready": vps_ready,
        "critical_missing_items": all_critical,
        "warnings": all_warnings,
        "recommended_next_step": recommended_next_step,
        "check_results": check_results,
        "data_quality": {
            "score": readiness_score,
            "level": dq_level,
            "issues": all_critical[:5],
        },
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
            "research_only": True,
        },
    }
