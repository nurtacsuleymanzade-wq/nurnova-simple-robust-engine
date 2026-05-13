from __future__ import annotations

import contextlib
import importlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

from src.simple.research_runtime import initialize_runtime_context, stamp_payload, write_json

BLOCK_ID = "S11_1_LOCAL_PIPELINE_RUNNER"
FEEDS_NEXT: dict[str, list[str]] = {"next_blocks": []}

_REQUIRED_CONTRACT_FIELDS = frozenset(
    {"timestamp_utc", "block_id", "symbol", "source", "data_quality", "reason_codes", "feeds_next"}
)

_ACTIVE_CHAIN_STAGES: list[tuple[str, str, str]] = [
    ("src.simple.run_s1_market_truth", "LIVE", "S1_OFFICIAL_MARKET_TRUTH"),
    ("src.simple.run_s2_1s_evidence", "LIVE_S2", "S2_LIGHTWEIGHT_1S_EVIDENCE"),
    ("src.simple.run_s3_hybrid_candle_dna", "LIVE_S3", "S3_HYBRID_CANDLE_DNA"),
    ("src.simple.quality_weight_engine", "LIVE_S4", "S4_QUALITY_WEIGHT_ENGINE"),
    ("src.simple.liquidity_structure_engine", "LIVE_S5", "S5_LIQUIDITY_STRUCTURE_CONTEXT"),
    ("src.simple.setup_candidate_engine", "LIVE_S6", "S6_SCENARIO_SETUP_CANDIDATE"),
    ("src.simple.run_s27_depth_liquidity_memory", "NOARG_MAIN", "S27_DEPTH_LIQUIDITY_MEMORY"),
    ("src.simple.run_s27b_wall_lifecycle", "NOARG_MAIN", "S27B_WALL_LIFECYCLE"),
    ("src.simple.flow_evidence_engine", "NOARG", "S13_FLOW_EVIDENCE"),
    ("src.simple.flow_persistence_engine", "NOARG", "S14_FLOW_PERSISTENCE"),
    ("src.simple.observation_factory", "NOARG", "OBSERVATION_FACTORY"),
    ("src.simple.mtf_candle_dna_factory", "NOARG", "MTF_CANDLE_DNA_FACTORY"),
    ("src.simple.atr_engine", "NOARG", "ATR_ENGINE"),
    ("src.simple.market_structure_engine", "NOARG", "MARKET_STRUCTURE_ENGINE"),
    ("src.simple.liquidity_map_engine", "NOARG", "LIQUIDITY_MAP_ENGINE"),
    ("src.simple.interpretation_engine", "NOARG", "INTERPRETATION_ENGINE"),
    ("src.simple.three_scenario_engine", "NOARG", "THREE_SCENARIO_ENGINE"),
    ("src.simple.business_zone_engine", "NOARG", "BUSINESS_ZONE_ENGINE"),
    ("src.simple.market_regime_classifier", "NOARG", "MARKET_REGIME_CLASSIFIER"),
    ("src.simple.intent_engine", "NOARG", "INTENT_ENGINE"),
    ("src.simple.positioning_context_engine", "NOARG", "POSITIONING_CONTEXT_ENGINE"),
    ("src.simple.momentum_continuation_engine", "NOARG", "MOMENTUM_CONTINUATION_ENGINE"),
    ("src.simple.double_distribution_reversal_engine", "NOARG", "DOUBLE_DISTRIBUTION_REVERSAL_ENGINE"),
    ("src.simple.trap_trader_engine", "NOARG", "TRAP_TRADER_ENGINE"),
    ("src.simple.unified_context_engine", "NOARG", "UNIFIED_CONTEXT_ENGINE"),
    ("src.simple.model_definition_registry", "NOARG", "MODEL_DEFINITION_REGISTRY"),
    ("src.simple.model_hunter_engine", "NOARG", "MODEL_HUNTER_ENGINE"),
    ("src.simple.model_semantic_validator", "NOARG", "MODEL_SEMANTIC_VALIDATOR"),
    ("src.simple.model_cluster_engine", "NOARG", "MODEL_CLUSTER_ENGINE"),
    ("src.simple.model_cooldown_engine", "NOARG", "MODEL_COOLDOWN_ENGINE"),
    ("src.simple.setup_family_activation_engine", "NOARG", "SETUP_FAMILY_ACTIVATION_ENGINE"),
    ("src.simple.timeframe_resolver", "NOARG", "TIMEFRAME_RESOLVER"),
    ("src.simple.paper_trade_factory", "NOARG", "PAPER_TRADE_FACTORY"),
    ("src.simple.research_paper_lifecycle_engine", "NOARG", "RESEARCH_PAPER_LIFECYCLE_ENGINE"),
    ("src.simple.outcome_accounting_engine", "NOARG", "OUTCOME_ACCOUNTING_ENGINE"),
    ("src.simple.research_edge_matrix_engine", "NOARG", "RESEARCH_EDGE_MATRIX_ENGINE"),
    ("src.simple.telegram_research_reporter", "SUMMARY_REPORT", "TELEGRAM_RESEARCH_REPORTER"),
    ("src.simple.model_feedback_diagnostic", "NOARG", "MODEL_FEEDBACK_DIAGNOSTIC"),
    ("src.simple.model_promotion_engine", "NOARG", "MODEL_PROMOTION_ENGINE"),
    ("src.simple.live_eligibility_gate", "NOARG", "LIVE_ELIGIBILITY_GATE_DIAGNOSTIC"),
    ("src.simple.system_auditor_engine", "NOARG", "SYSTEM_AUDITOR_ENGINE"),
    ("src.simple.system_query_state_builder", "NOARG", "SYSTEM_QUERY_STATE_BUILDER"),
]

_LEGACY_BRIDGE_STAGES: list[tuple[str, str, str]] = [
    ("src.simple.flow_to_setup_context_engine", "NOARG", "S15_FLOW_TO_SETUP_CONTEXT"),
    ("src.simple.absorption_reversal_engine", "NOARG", "AR01_ABSORPTION_REVERSAL"),
    ("src.simple.delta_absorption_failure_engine", "NOARG", "DAF_DELTA_ABSORPTION_FAILURE"),
    ("src.simple.failed_continuation_reversal_engine", "NOARG", "FCR_FAILED_CONTINUATION"),
    ("src.simple.candle_quality_engine", "NOARG", "CQE_CANDLE_QUALITY"),
    ("src.simple.model_registry", "NOARG", "MODEL_REGISTRY"),
    ("src.simple.scenario_entry_trigger_engine", "NOARG", "S16_SCENARIO_ENTRY_TRIGGER"),
    ("src.simple.trade_plan_engine", "NOARG", "S17_TRADE_PLAN"),
    ("src.simple.decision_gate_engine", "NOARG", "S18_DECISION_GATE"),
    ("src.simple.paper_lifecycle_tracker", "NOARG", "S20_PAPER_LIFECYCLE"),
    ("src.simple.outcome_monitor", "NOARG", "S21_OUTCOME_MONITOR"),
    ("src.simple.edge_matrix_v2", "NOARG", "S22_EDGE_MATRIX"),
    ("src.simple.simple_brain_report_engine", "run_fake_sample", "S10_SIMPLE_BRAIN_REPORT"),
]

_STAGES = list(_ACTIVE_CHAIN_STAGES)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_critical(output: dict[str, Any]) -> str | None:
    for field in _REQUIRED_CONTRACT_FIELDS:
        if field not in output:
            return f"MISSING_FIELD_{field.upper()}"
    if not output.get("reason_codes"):
        return "REASON_CODES_EMPTY"
    return None


def _classify_status(output: dict[str, Any]) -> str:
    level = output.get("data_quality", {}).get("level", "")
    if level in ("LOW", "CRITICAL", "INVALID"):
        return "DEGRADED"
    return "PASSED"


def _run_live_s1(symbol: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        old_argv = sys.argv
        sys.argv = ["run_s1_market_truth", "--symbol", symbol]
        try:
            from src.simple.run_s1_market_truth import main as s1_main

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                s1_main()
            output = json.loads(buf.getvalue())
        finally:
            sys.argv = old_argv
        return output, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_stage(module_path: str, func_name: str, symbol: str) -> tuple[dict[str, Any] | None, float, str | None]:
    if func_name == "LIVE":
        return _run_live_s1(symbol)
    t0 = time.monotonic()
    try:
        mod = importlib.import_module(module_path)
        fn = getattr(mod, func_name)
        result: dict[str, Any] = fn(symbol)
        return result, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_noarg_main_stage(module_path: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        mod = importlib.import_module(module_path)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main()
        raw = buf.getvalue().strip()
        output = json.loads(raw) if raw else None
        return output, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_noarg_stage(module_path: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        mod = importlib.import_module(module_path)
        run_candidates = []
        imported_candidates = []
        for name in dir(mod):
            fn = getattr(mod, name)
            if not (name.startswith("run_") and callable(fn)):
                continue
            if getattr(fn, "__module__", None) == module_path:
                run_candidates.append((name, fn))
            else:
                imported_candidates.append((name, fn))
        run_fn = None
        for name, fn in sorted(run_candidates):
            if name.endswith("_engine"):
                run_fn = fn
                break
        if run_fn is None and run_candidates:
            run_fn = sorted(run_candidates)[0][1]
        if run_fn is None and imported_candidates:
            run_fn = sorted(imported_candidates)[0][1]
        if run_fn is None:
            raise ValueError(f"No run_ function found in {module_path}")
        result: dict[str, Any] = run_fn()
        return result, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_summary_report_stage(module_path: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        mod = importlib.import_module(module_path)
        result: dict[str, Any] = mod.run_summary_report()
        return result, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _persist_stage_output(module_path: str, output: dict[str, Any], symbol: str, context: dict[str, Any]) -> dict[str, Any]:
    stamped = stamp_payload(output, str(output.get("block_id") or module_path.rsplit(".", 1)[-1].upper()), symbol, context)
    try:
        mod = importlib.import_module(module_path)
        output_path = getattr(mod, "OUTPUT_PATH", None)
        if output_path is not None:
            write_json(output_path, stamped)
    except Exception:
        pass
    return stamped


def run_pipeline(symbol: str, source_mode: str = "LIVE") -> dict[str, Any]:
    block_results: list[dict[str, Any]] = []
    blocks_passed = 0
    blocks_failed = 0
    pipeline_status = "COMPLETE"
    stop_reason: str | None = None
    context = initialize_runtime_context(symbol)
    context_id = context.get("context_id", "CTX_UNKNOWN")
    sync_status = "UNKNOWN"

    block_results.append({
        "block_id": "RUNTIME_CONTEXT",
        "status": "PASSED",
        "runtime_ms": 0.0,
        "context_id": context_id,
        "sync_status": "STARTED",
        "error": None,
    })
    blocks_passed += 1

    for module_path, func_name, fallback_label in _STAGES:
        if func_name == "LIVE":
            output, runtime_ms, exc_str = _run_live_s1(symbol)
        elif func_name == "LIVE_S2":
            output, runtime_ms, exc_str = _run_live_s2(symbol)
        elif func_name == "LIVE_S3":
            output, runtime_ms, exc_str = _run_live_s3(symbol)
        elif func_name == "LIVE_S4":
            output, runtime_ms, exc_str = _run_live_s4_direct(symbol)
        elif func_name == "LIVE_S5":
            output, runtime_ms, exc_str = _run_live_s5_direct(symbol)
        elif func_name == "LIVE_S6":
            output, runtime_ms, exc_str = _run_live_s6_direct(symbol)
        elif func_name == "NOARG_MAIN":
            output, runtime_ms, exc_str = _run_noarg_main_stage(module_path)
        elif func_name == "NOARG":
            output, runtime_ms, exc_str = _run_noarg_stage(module_path)
        elif func_name == "SUMMARY_REPORT":
            output, runtime_ms, exc_str = _run_summary_report_stage(module_path)
        else:
            output, runtime_ms, exc_str = _run_stage(module_path, func_name, symbol)

        if exc_str is not None:
            block_results.append({
                "block_id": fallback_label,
                "status": "CRITICAL",
                "runtime_ms": runtime_ms,
                "error": exc_str[:200],
            })
            blocks_failed += 1
            if any(fallback_label.startswith(cb) for cb in {"S1_", "S2_", "S3_", "S4_", "S5_", "S6_"}):
                pipeline_status = "STOPPED_CRITICAL"
                stop_reason = f"EXCEPTION_IN_{fallback_label}"
                break
            continue

        if output is None:
            block_results.append({
                "block_id": fallback_label,
                "status": "DEGRADED",
                "runtime_ms": runtime_ms,
                "error": "NO_OUTPUT",
            })
            blocks_failed += 1
            continue

        output = _persist_stage_output(module_path, output, symbol, context)
        violation = _check_critical(output)
        if violation:
            block_results.append({
                "block_id": output.get("block_id", fallback_label),
                "status": "DEGRADED",
                "runtime_ms": runtime_ms,
                "error": violation,
            })
            blocks_failed += 1
            continue

        block_results.append({
            "block_id": output.get("block_id", fallback_label),
            "status": _classify_status(output),
            "runtime_ms": runtime_ms,
            "error": None,
        })
        blocks_passed += 1

    try:
        from src.simple.context_sync_engine import run_context_sync

        t0_sync = time.monotonic()
        sync_result = run_context_sync(symbol=symbol, mode="post")
        sync_ms = round((time.monotonic() - t0_sync) * 1000, 1)
        sync_status = sync_result.get("sync_status", "UNKNOWN")
        sync_block_status = "PASSED" if sync_status == "SYNC_OK" else "DEGRADED" if sync_status == "SYNC_DEGRADED" else "CRITICAL"
        block_results.append({
            "block_id": "S0_CONTEXT_SYNC_POST_VALIDATION",
            "status": sync_block_status,
            "runtime_ms": sync_ms,
            "context_id": context_id,
            "sync_status": sync_status,
            "error": sync_result.get("failed_reason"),
        })
        if sync_block_status == "PASSED":
            blocks_passed += 1
        else:
            blocks_failed += 1
    except Exception as exc:
        sync_status = "ERROR"
        block_results.append({
            "block_id": "S0_CONTEXT_SYNC_POST_VALIDATION",
            "status": "CRITICAL",
            "runtime_ms": 0.0,
            "context_id": context_id,
            "sync_status": sync_status,
            "error": str(exc)[:200],
        })
        blocks_failed += 1

    reason_codes = [
        f"SOURCE_{source_mode}",
        f"SYMBOL_{symbol}",
        f"PIPELINE_{pipeline_status}",
        f"SYNC_{sync_status}",
        f"CONTEXT_{context_id}",
        f"BLOCKS_PASSED_{blocks_passed}",
        f"BLOCKS_FAILED_{blocks_failed}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_LIVE_TRADING",
        "NO_PRIVATE_API",
    ]
    if stop_reason:
        reason_codes.append(f"STOP_{stop_reason[:100]}")

    if pipeline_status == "COMPLETE" and blocks_failed == 0:
        dq: dict[str, Any] = {"score": 1.0, "level": "HIGH", "issues": []}
    elif blocks_passed > blocks_failed:
        dq = {"score": 0.6, "level": "MEDIUM", "issues": [f"BLOCKS_FAILED_{blocks_failed}"]}
    else:
        dq = {"score": 0.0, "level": "CRITICAL", "issues": [f"PIPELINE_{pipeline_status}"]}

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {"source_mode": source_mode},
        "context_id": context_id,
        "loop_id": context.get("loop_id"),
        "sync_status": sync_status,
        "execution_summary": {
            "blocks_total": len(_STAGES) + 2,
            "blocks_passed": blocks_passed,
            "blocks_failed": blocks_failed,
            "pipeline_status": pipeline_status,
            "stop_reason": stop_reason,
        },
        "block_results": block_results,
        "data_quality": dq,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def _run_live_s2(symbol: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        old_argv = sys.argv
        sys.argv = ["run_s2_1s_evidence", "--symbol", symbol]
        try:
            from src.simple.run_s2_1s_evidence import main as s2_main

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                s2_main()
            output = json.loads(buf.getvalue())
        finally:
            sys.argv = old_argv
        return output, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_live_s3(symbol: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        old_argv = sys.argv
        sys.argv = ["run_s3_hybrid_candle_dna", "--symbol", symbol]
        try:
            from src.simple.run_s3_hybrid_candle_dna import main as s3_main

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                s3_main()
            output = json.loads(buf.getvalue())
        finally:
            sys.argv = old_argv
        return output, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_live_s4_direct(symbol: str) -> tuple[dict[str, Any] | None, float, str | None]:
    import json as _json
    import pathlib

    t0 = time.monotonic()
    try:
        state_dir = pathlib.Path("state/simple")
        try:
            s1_raw = _json.loads((state_dir / "latest_market_truth.json").read_text())
            s1 = {
                "available": True,
                "data_quality_score": s1_raw.get("data_quality", {}).get("score", 0.5),
                "consistency_label": s1_raw.get("consistency", {}).get("consistency_label", "UNKNOWN"),
            }
        except Exception:
            s1 = None
        try:
            s2_raw = _json.loads((state_dir / "latest_1s_evidence.json").read_text())
            s2 = {"available": True, "data_quality_score": s2_raw.get("data_quality", {}).get("score", 0.5)}
        except Exception:
            s2 = None
        try:
            s3_raw = _json.loads((state_dir / "latest_hybrid_candle_dna.json").read_text())
            s3 = {"available": True, "hybrid_quality_weight": s3_raw.get("quality", {}).get("hybrid_quality_weight", 0.5)}
        except Exception:
            s3 = None
        from src.simple.quality_weight_engine import build_quality_weight
        from src.simple.run_s4_quality_weight import _write_outputs as s4_write

        result = build_quality_weight(symbol, s1, s2, s3, "FLOW_STATE_LIVE")
        s4_write(result)
        return result, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_live_s5_direct(symbol: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        from src.simple.liquidity_structure_engine import build_liquidity_structure
        from src.simple.run_s5_liquidity_structure import _load_inputs, _write_outputs as s5_write

        s1, s3, s4 = _load_inputs()
        result = build_liquidity_structure(symbol, s1, s3, s4, "FLOW_STATE_LIVE")
        s5_write(result)
        return result, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)


def _run_live_s6_direct(symbol: str) -> tuple[dict[str, Any] | None, float, str | None]:
    t0 = time.monotonic()
    try:
        from src.simple.run_s6_setup_candidate import _load_inputs, _write_outputs as s6_write
        from src.simple.setup_candidate_engine import build_setup_candidate

        s1, s2, s3, s4, s5 = _load_inputs()
        result = build_setup_candidate(symbol, s1, s2, s3, s4, s5, "FLOW_STATE_LIVE")
        s6_write(result)
        return result, round((time.monotonic() - t0) * 1000, 1), None
    except Exception as exc:
        return None, round((time.monotonic() - t0) * 1000, 1), str(exc)
