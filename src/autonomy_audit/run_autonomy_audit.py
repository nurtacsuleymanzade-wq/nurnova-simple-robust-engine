from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .autonomy_governor_engine import evaluate_autonomy_governor
from .autonomy_registry import AUTONOMY_BLOCK_ID, DEFAULT_FEEDS_NEXT, build_autonomy_audit_id, build_lineage_id, utc_now
from .autonomy_validator import validate_autonomy_audit
from .decision_consistency_engine import evaluate_decision_consistency
from .edge_stability_engine import evaluate_edge_stability
from .hallucination_risk_engine import evaluate_hallucination_risk
from .lineage_integrity_engine import evaluate_lineage_integrity
from .template_risk_engine import evaluate_template_risk

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/autonomy_audit"
REPORTS_DIR = ROOT / "reports/autonomy_audit"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_autonomy_audit.json"
ENGINE_STATE_PATH = STATE_DIR / "autonomy_audit_state.json"
EVENTS_PATH = LIVE_DIR / "autonomy_audit_events.jsonl"
REPORT_PATH = REPORTS_DIR / "autonomy_audit_latest_report.md"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_inputs() -> tuple[dict[str, dict[str, Any] | None], list[str], list[str], int, int]:
    mapping = {
        "lineage_audit": ROOT / "state/lineage/latest_lineage_audit.json",
        "lineage_repair": ROOT / "state/lineage/latest_lineage_repair.json",
        "edge_source_mapping": ROOT / "state/lineage/latest_edge_source_outcome_mapping.json",
        "market_state": ROOT / "state/market_state/latest_market_state.json",
        "active_scenario": ROOT / "state/active_scenario/latest_active_scenario.json",
        "flow_reaction": ROOT / "state/flow_reaction/latest_flow_reaction.json",
        "setup_entry": ROOT / "state/setup_entry/latest_setup_entry.json",
        "trade_decision": ROOT / "state/trade_decision/latest_trade_decision.json",
        "paper_outcome": ROOT / "state/paper_outcome/latest_paper_outcome.json",
        "edge_matrix": ROOT / "state/edge_matrix/latest_conditional_edge_matrix.json",
        "replay_engine": ROOT / "state/replay_engine/latest_replay_engine.json",
        "nova_brain": ROOT / "state/nova_brain/latest_nova_brain_snapshot.json",
        "probabilistic_engine": ROOT / "state/probabilistic_engine/latest_probabilistic_engine.json",
        "perspective_merger": ROOT / "state/perspective_merger/latest_perspective_merger.json",
    }
    inputs = {name: _read_json(path) for name, path in mapping.items()}
    files_used = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if path.exists()]
    missing = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if not path.exists()]
    report_count = len(list((ROOT / "reports").glob("**/*latest_report.md")))
    live_count = len(list((ROOT / "data/live").glob("*.jsonl")))
    return inputs, files_used, missing, report_count, live_count


def _data_quality(missing: list[str], lineage_integrity: dict[str, Any], edge_stability: dict[str, Any]) -> str:
    if len(missing) >= 6:
        return "INVALID"
    if len(missing) >= 3 or lineage_integrity.get("status") == "FAIL":
        return "DEGRADED"
    if edge_stability.get("status") == "FAIL" or missing:
        return "ACCEPTABLE"
    return "OK"


def _report(payload: dict[str, Any]) -> str:
    def _rows(items: list[Any]) -> list[str]:
        return [f"- {item}" for item in items] if items else ["- NONE"]

    lines = [
        f"# Autonomy Audit Report - {payload.get('timestamp_utc')}",
        "",
        "## Autonomy Audit Status",
        f"- autonomy_audit_id: {payload.get('autonomy_audit_id')}",
        f"- lineage_id: {payload.get('lineage_id')}",
        "",
        "## Autonomy Score",
        f"- {payload.get('autonomy_score')}",
        "",
        "## Safe For Autonomy",
        f"- {payload.get('safe_for_autonomy')}",
        "",
        "## Human Override Requirement",
        f"- {payload.get('human_override_required')}",
        "",
        "## Global Risk Level",
        f"- {payload.get('global_risk_level')}",
        "",
        "## Lineage Integrity",
        f"```json\n{json.dumps(payload.get('lineage_integrity', {}), indent=2)}\n```",
        "",
        "## Edge Stability",
        f"```json\n{json.dumps(payload.get('edge_stability', {}), indent=2)}\n```",
        "",
        "## Replay Validation",
        f"```json\n{json.dumps(payload.get('replay_validation', {}), indent=2)}\n```",
        "",
        "## Template Risk",
        f"```json\n{json.dumps(payload.get('template_risk', {}), indent=2)}\n```",
        "",
        "## Hallucination Risk",
        f"```json\n{json.dumps(payload.get('hallucination_risk', {}), indent=2)}\n```",
        "",
        "## Decision Consistency",
        f"```json\n{json.dumps(payload.get('decision_quality', {}), indent=2)}\n```",
        "",
        "## Critical Failures",
        *_rows(payload.get("critical_failures", [])),
        "",
        "## Autonomy Blockers",
        *_rows(payload.get("autonomy_blockers", [])),
        "",
        "## Safety Constraints",
        *_rows(payload.get("safety_constraints", [])),
        "",
        "## Recommended Human Controls",
        *_rows(payload.get("recommended_human_controls", [])),
        "",
        "## Brain Governor Summary",
        f"```json\n{json.dumps(payload.get('brain_governor_summary', {}), indent=2)}\n```",
        "",
        "## Data Quality",
        f"- {payload.get('data_quality')}",
        "",
        "## Reason Codes",
        *_rows(payload.get("reason_codes", [])),
        "",
        "## Warnings",
        *_rows(payload.get("warnings", [])),
        "",
        "## Feeds Next",
        *_rows(payload.get("feeds_next", [])),
        "",
        "## Next Action",
    ]
    if str(payload.get("autonomy_status") or "UNKNOWN").upper() == "NOT_READY":
        lines.append("- Keep the system paper-only and clear lineage, edge, and replay blockers first.")
    else:
        lines.append("- Maintain paper-only supervision until higher readiness is empirically proven.")
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    timestamp_utc = utc_now()
    inputs, files_used, missing, report_count, live_count = _load_inputs()

    lineage_integrity = evaluate_lineage_integrity(
        inputs.get("lineage_audit"),
        inputs.get("lineage_repair"),
        inputs.get("edge_source_mapping"),
    )
    edge_results = evaluate_edge_stability(inputs.get("edge_matrix"), inputs.get("nova_brain"))
    edge_stability = edge_results["edge_stability"]
    edge_decay_pressure = edge_results["edge_decay_pressure"]
    template_risk = evaluate_template_risk(inputs.get("trade_decision"), inputs.get("setup_entry"))
    hallucination_risk = evaluate_hallucination_risk(
        trade_decision=inputs.get("trade_decision"),
        paper_outcome=inputs.get("paper_outcome"),
        edge_matrix=inputs.get("edge_matrix"),
        replay_engine=inputs.get("replay_engine"),
        nova_brain=inputs.get("nova_brain"),
        probabilistic_engine=inputs.get("probabilistic_engine"),
        perspective_merger=inputs.get("perspective_merger"),
    )
    consistency = evaluate_decision_consistency(
        lineage_audit=inputs.get("lineage_audit"),
        trade_decision=inputs.get("trade_decision"),
        replay_engine=inputs.get("replay_engine"),
        nova_brain=inputs.get("nova_brain"),
        probabilistic_engine=inputs.get("probabilistic_engine"),
        perspective_merger=inputs.get("perspective_merger"),
        edge_matrix=inputs.get("edge_matrix"),
    )
    governor = evaluate_autonomy_governor(
        lineage_integrity=lineage_integrity,
        edge_stability=edge_stability,
        replay_validation=consistency["replay_validation"],
        template_risk=template_risk,
        hallucination_risk=hallucination_risk,
        decision_consistency=consistency,
        edge_decay_pressure=edge_decay_pressure,
        trade_decision=inputs.get("trade_decision"),
        paper_outcome=inputs.get("paper_outcome"),
        perspective_merger=inputs.get("perspective_merger"),
    )

    symbol = str((inputs.get("trade_decision") or {}).get("symbol") or "BTCUSDT")
    seed = {
        "autonomy_status": governor["autonomy_status"],
        "autonomy_score": governor["autonomy_score"],
        "global_risk_level": governor["global_risk_level"],
        "lineage_score": lineage_integrity.get("score"),
        "edge_score": edge_stability.get("score"),
    }
    autonomy_audit_id = build_autonomy_audit_id(symbol, seed)
    lineage_id = build_lineage_id(
        "autonomy_audit",
        symbol,
        autonomy_audit_id,
        (inputs.get("lineage_audit") or {}).get("generated_at_utc"),
        (inputs.get("trade_decision") or {}).get("decision_id"),
        (inputs.get("probabilistic_engine") or {}).get("scenario_engine_id"),
        (inputs.get("perspective_merger") or {}).get("perspective_merger_id"),
    )

    data_quality = _data_quality(missing, lineage_integrity, edge_stability)
    reason_codes: list[str] = []
    if missing:
        reason_codes.append("UNKNOWN_AUTONOMY_STATE")
    reason_codes.extend(lineage_integrity.get("reason_codes") or [])
    reason_codes.extend(edge_stability.get("reason_codes") or [])
    reason_codes.extend(template_risk.get("reason_codes") or [])
    reason_codes.extend(hallucination_risk.get("reason_codes") or [])
    reason_codes.extend(consistency.get("reason_codes") or [])
    reason_codes.extend(governor.get("critical_failures") or [])

    payload = {
        "timestamp_utc": timestamp_utc,
        "block_id": AUTONOMY_BLOCK_ID,
        "symbol": symbol,
        "autonomy_audit_id": autonomy_audit_id,
        "lineage_id": lineage_id,
        "autonomy_status": governor["autonomy_status"],
        "autonomy_score": governor["autonomy_score"],
        "safe_for_autonomy": governor["safe_for_autonomy"],
        "human_override_required": governor["human_override_required"],
        "global_risk_level": governor["global_risk_level"],
        "lineage_integrity": lineage_integrity,
        "edge_stability": edge_stability,
        "replay_validation": consistency["replay_validation"],
        "template_risk": template_risk,
        "hallucination_risk": hallucination_risk,
        "fake_confidence_risk": consistency["fake_confidence_risk"],
        "data_spine_health": consistency["data_spine_health"],
        "decision_quality": consistency["decision_quality"],
        "probabilistic_consistency": consistency["probabilistic_consistency"],
        "perspective_alignment_consistency": consistency["perspective_alignment_consistency"],
        "system_health": consistency["system_health"],
        "edge_decay_pressure": edge_decay_pressure,
        "operational_stability": governor["operational_stability"],
        "critical_failures": governor["critical_failures"],
        "autonomy_blockers": governor["autonomy_blockers"],
        "autonomy_strengths": governor["autonomy_strengths"],
        "safety_constraints": governor["safety_constraints"],
        "recommended_human_controls": governor["recommended_human_controls"],
        "autonomy_notes": governor["autonomy_notes"],
        "brain_governor_summary": governor["brain_governor_summary"],
        "data_quality": data_quality,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "warnings": [],
    }

    validation = validate_autonomy_audit(payload)
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
                "last_autonomy_audit_id": autonomy_audit_id,
                "last_lineage_id": lineage_id,
                "autonomy_status": governor["autonomy_status"],
                "autonomy_score": governor["autonomy_score"],
                "safe_for_autonomy": governor["safe_for_autonomy"],
                "global_risk_level": governor["global_risk_level"],
                "validation_passed": validation["is_valid"],
                "validation_errors": validation["errors"],
                "files_used": files_used,
                "missing_sources": missing,
                "report_files_count": report_count,
                "live_files_count": live_count,
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
