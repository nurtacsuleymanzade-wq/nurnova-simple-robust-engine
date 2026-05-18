from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .counterfactual_engine import build_counterfactual_summary
from .decision_quality_engine import evaluate_decision_quality
from .replay_registry import (
    DEFAULT_FEEDS_NEXT,
    REPLAY_BLOCK_ID,
    build_lineage_id,
    build_replay_batch_id,
    utc_now,
)
from .replay_scenario_engine import filter_replay_eligible_outcomes, generate_replay_scenarios
from .replay_validator import validate_replay_output

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/replay_engine"
REPORTS_DIR = ROOT / "reports/replay_engine"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_replay_engine.json"
ENGINE_STATE_PATH = STATE_DIR / "replay_engine_state.json"
EVENTS_PATH = LIVE_DIR / "replay_engine_events.jsonl"
REPORT_PATH = REPORTS_DIR / "replay_engine_latest_report.md"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path, max_lines: int = 500) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _collect_inputs() -> tuple[list[dict[str, Any]], dict[str, Any], list[str], list[str]]:
    files_used: list[str] = []
    missing: list[str] = []

    outcome_paths = [
        ROOT / "state/paper_outcome/latest_paper_outcome.json",
        ROOT / "data/live/paper_outcome_events.jsonl",
    ]
    edge_paths = [
        ROOT / "state/edge_matrix/latest_conditional_edge_matrix.json",
        ROOT / "data/live/conditional_edge_matrix_events.jsonl",
    ]
    context_paths = {
        "trade_decision": ROOT / "state/trade_decision/latest_trade_decision.json",
        "setup_entry": ROOT / "state/setup_entry/latest_setup_entry.json",
        "active_scenario": ROOT / "state/active_scenario/latest_active_scenario.json",
        "flow_reaction": ROOT / "state/flow_reaction/latest_flow_reaction.json",
        "edge_matrix": ROOT / "state/edge_matrix/latest_conditional_edge_matrix.json",
    }

    records: list[dict[str, Any]] = []
    for path in outcome_paths:
        if path.suffix.lower() == ".json":
            payload = _read_json(path)
            if payload is not None:
                records.append(payload)
                files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
            elif not path.exists():
                missing.append(str(path.relative_to(ROOT)).replace("\\", "/"))
        else:
            items = _read_jsonl(path)
            if items:
                records.extend(items)
                files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
            elif not path.exists():
                missing.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    for path in edge_paths:
        if path.exists():
            files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
        else:
            missing.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    latest_context = {name: _read_json(path) for name, path in context_paths.items()}
    for name, path in context_paths.items():
        if path.exists():
            files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
        else:
            missing.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get("outcome_id") or record.get("paper_trade_id") or json.dumps(record, sort_keys=True, ensure_ascii=False))
        deduped[key] = record

    return list(deduped.values()), latest_context, sorted(set(files_used)), sorted(set(missing))


def _resolve_edge_row_id(source_outcome_id: str, edge_matrix: dict[str, Any] | None) -> str | None:
    for row in (edge_matrix or {}).get("conditional_edge_rows") or []:
        if source_outcome_id in (row.get("source_outcome_ids") or []):
            return row.get("edge_row_id")
    return None


def _extract_source_ids(source_outcome: dict[str, Any], latest_context: dict[str, Any]) -> dict[str, Any]:
    evidence = source_outcome.get("evidence") if isinstance(source_outcome.get("evidence"), dict) else {}
    trade_evidence = evidence.get("trade_decision_evidence") if isinstance(evidence.get("trade_decision_evidence"), dict) else {}
    active_scenario_id = trade_evidence.get("active_scenario_id") or (latest_context.get("active_scenario") or {}).get("active_scenario_id")
    flow_reaction_id = trade_evidence.get("flow_reaction_id") or (latest_context.get("flow_reaction") or {}).get("flow_reaction_id")
    edge_row_id = _resolve_edge_row_id(str(source_outcome.get("outcome_id") or ""), latest_context.get("edge_matrix"))
    return {
        "source_trade_plan_id": source_outcome.get("trade_plan_id") or trade_evidence.get("trade_plan_id"),
        "source_setup_candidate_id": source_outcome.get("setup_candidate_id") or trade_evidence.get("setup_entry_id"),
        "source_active_scenario_id": active_scenario_id,
        "source_flow_reaction_id": flow_reaction_id,
        "source_edge_row_id": edge_row_id,
    }


def _report(payload: dict[str, Any]) -> str:
    def _scenario_lines(items: list[dict[str, Any]]) -> list[str]:
        if not items:
            return ["- NONE"]
        return [
            f"- {item.get('scenario_type')}: alt_r={item.get('alternative_r_multiple')} better={item.get('better_than_original')} worse={item.get('worse_than_original')}"
            for item in items
        ]

    lines = [
        f"# Replay Engine Report - {payload.get('timestamp_utc')}",
        "",
        "## Replay Engine Status",
        f"- replay_status: {payload.get('replay_status')}",
        f"- replay_batch_id: {payload.get('replay_batch_id')}",
        f"- lineage_id: {payload.get('lineage_id')}",
        "",
        "## Replay Eligible Outcomes",
        f"- source_outcome_id: {payload.get('source_outcome_id')}",
        "",
        "## Replay Scenarios",
        *_scenario_lines(payload.get("replay_scenarios", [])),
        "",
        "## Decision Quality",
        f"- {payload.get('decision_quality')}",
        "",
        "## Decision Quality Score",
        f"- {payload.get('decision_quality_score')}",
        "",
        "## Best Alternative Outcome",
        f"```json\n{json.dumps(payload.get('best_alternative_outcome', {}), indent=2)}\n```",
        "",
        "## Worst Alternative Outcome",
        f"```json\n{json.dumps(payload.get('worst_alternative_outcome', {}), indent=2)}\n```",
        "",
        "## Counterfactual Summary",
        f"```json\n{json.dumps(payload.get('counterfactual_summary', {}), indent=2)}\n```",
        "",
        "## Learning Signals",
        *([f"- {item}" for item in payload.get("learning_signals", [])] or ["- NONE"]),
        "",
        "## Data Quality",
        f"- {payload.get('data_quality')}",
        "",
        "## Reason Codes",
        *([f"- {item}" for item in payload.get("reason_codes", [])] or ["- NONE"]),
        "",
        "## Warnings",
        *([f"- {item}" for item in payload.get("warnings", [])] or ["- NONE"]),
        "",
        "## Feeds Next",
        *([f"- {item}" for item in payload.get("feeds_next", [])] or ["- NONE"]),
        "",
        "## Next Action",
    ]
    if payload.get("replay_status") == "NO_REPLAY_DATA":
        lines.append("- No replayable closed eligible outcomes yet; wait for PHASE 7 truth samples.")
    else:
        lines.append("- Review learning signals before trusting the current decision policy in PHASE 10 or PHASE 11.")
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    timestamp_utc = utc_now()
    records, latest_context, files_used, missing_sources = _collect_inputs()
    filtered = filter_replay_eligible_outcomes(records)
    source_outcome = filtered["eligible_records"][0] if filtered["eligible_records"] else {}

    source_ids = _extract_source_ids(source_outcome, latest_context) if source_outcome else {
        "source_trade_plan_id": None,
        "source_setup_candidate_id": None,
        "source_active_scenario_id": None,
        "source_flow_reaction_id": None,
        "source_edge_row_id": None,
    }

    replay_batch_id = build_replay_batch_id(
        source_outcome.get("outcome_id") if source_outcome else "NO_SOURCE_OUTCOME",
        source_ids.get("source_trade_plan_id"),
        source_ids.get("source_edge_row_id"),
    )
    lineage_id = build_lineage_id(
        "replay",
        replay_batch_id,
        source_outcome.get("outcome_id") if source_outcome else "NO_SOURCE_OUTCOME",
        source_ids.get("source_edge_row_id"),
    )

    replay_scenarios = generate_replay_scenarios(source_outcome) if source_outcome else []
    counterfactual = build_counterfactual_summary(source_outcome, replay_scenarios) if source_outcome else {
        "replay_status": "NO_REPLAY_DATA",
        "counterfactual_summary": {"scenario_count": 0},
        "best_alternative_outcome": {},
        "worst_alternative_outcome": {},
        "learning_signals": ["NO_REPLAY_DATA"],
    }
    decision_quality = evaluate_decision_quality(
        source_outcome,
        replay_scenarios,
        edge_context=latest_context.get("edge_matrix"),
        trade_decision=latest_context.get("trade_decision"),
    ) if source_outcome else {"decision_quality": "UNKNOWN", "decision_quality_score": None}

    replay_status = counterfactual["replay_status"] if source_outcome else "NO_REPLAY_DATA"
    data_quality = "OK" if source_outcome else ("DEGRADED" if missing_sources else "UNKNOWN")
    if source_outcome and any(scenario.get("alternative_r_multiple") is None for scenario in replay_scenarios):
        data_quality = "ACCEPTABLE"

    reason_codes = list(filtered.get("reason_codes") or [])
    if missing_sources:
        reason_codes.append("NO_REPLAY_DATA_SOURCE_MISSING")
    if not source_outcome:
        reason_codes.append("NO_REPLAY_DATA")

    payload = {
        "timestamp_utc": timestamp_utc,
        "block_id": REPLAY_BLOCK_ID,
        "symbol": str(source_outcome.get("symbol") or (latest_context.get("trade_decision") or {}).get("symbol") or "BTCUSDT"),
        "replay_batch_id": replay_batch_id,
        "lineage_id": lineage_id,
        "source_outcome_id": source_outcome.get("outcome_id") if source_outcome else "NO_SOURCE_OUTCOME",
        "source_trade_plan_id": source_ids.get("source_trade_plan_id"),
        "source_setup_candidate_id": source_ids.get("source_setup_candidate_id"),
        "source_active_scenario_id": source_ids.get("source_active_scenario_id"),
        "source_flow_reaction_id": source_ids.get("source_flow_reaction_id"),
        "source_edge_row_id": source_ids.get("source_edge_row_id"),
        "replay_status": replay_status,
        "replay_scenarios": replay_scenarios,
        "decision_quality": decision_quality["decision_quality"],
        "decision_quality_score": decision_quality["decision_quality_score"],
        "counterfactual_summary": counterfactual["counterfactual_summary"],
        "best_alternative_outcome": counterfactual["best_alternative_outcome"],
        "worst_alternative_outcome": counterfactual["worst_alternative_outcome"],
        "learning_signals": counterfactual["learning_signals"],
        "data_quality": data_quality,
        "reason_codes": list(dict.fromkeys(reason_codes or ["REPLAY_ENGINE_COMPUTED"])),
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "warnings": [],
        "source_is_closed_outcome": source_outcome.get("is_closed_outcome") if source_outcome else False,
        "source_edge_eligible": source_outcome.get("edge_eligible") if source_outcome else False,
    }

    validation = validate_replay_output(payload)
    if not validation["is_valid"]:
        payload["warnings"] = list(dict.fromkeys(validation["errors"]))

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    LATEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    ENGINE_STATE_PATH.write_text(
        json.dumps(
            {
                "timestamp_utc": timestamp_utc,
                "last_replay_batch_id": replay_batch_id,
                "last_lineage_id": lineage_id,
                "eligible_outcome_count": len(filtered["eligible_records"]),
                "excluded_outcome_count": filtered["excluded_count"],
                "replay_status": replay_status,
                "decision_quality": payload["decision_quality"],
                "decision_quality_score": payload["decision_quality_score"],
                "validation_passed": validation["is_valid"],
                "validation_errors": validation["errors"],
                "files_used": files_used,
                "missing_sources": missing_sources,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    REPORT_PATH.write_text(_report(payload), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
