from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .brain_registry import (
    BRAIN_BLOCK_ID,
    DEFAULT_FEEDS_NEXT,
    build_brain_snapshot_id,
    build_lineage_id,
    utc_now,
)
from .brain_snapshot_validator import validate_brain_snapshot
from .edge_intelligence_engine import analyze_edge_intelligence
from .risk_intelligence_engine import analyze_risk_intelligence
from .story_engine import build_brain_story
from .system_health_engine import evaluate_system_health

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/nova_brain"
REPORTS_DIR = ROOT / "reports/nova_brain"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_nova_brain_snapshot.json"
ENGINE_STATE_PATH = STATE_DIR / "nova_brain_engine_state.json"
EVENTS_PATH = LIVE_DIR / "nova_brain_snapshot_events.jsonl"
REPORT_PATH = REPORTS_DIR / "nova_brain_snapshot_latest_report.md"


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
        "market_state": ROOT / "state/market_state/latest_market_state.json",
        "active_scenario": ROOT / "state/active_scenario/latest_active_scenario.json",
        "flow_reaction": ROOT / "state/flow_reaction/latest_flow_reaction.json",
        "setup_entry": ROOT / "state/setup_entry/latest_setup_entry.json",
        "trade_decision": ROOT / "state/trade_decision/latest_trade_decision.json",
        "paper_outcome": ROOT / "state/paper_outcome/latest_paper_outcome.json",
        "edge_matrix": ROOT / "state/edge_matrix/latest_conditional_edge_matrix.json",
        "replay_engine": ROOT / "state/replay_engine/latest_replay_engine.json",
    }
    inputs = {name: _read_json(path) for name, path in mapping.items()}
    files_used = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if path.exists()]
    missing = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if not path.exists()]
    report_count = len(list((ROOT / "reports").glob("**/*latest_report.md")))
    live_count = len(list((ROOT / "data/live").glob("*.jsonl")))
    return inputs, files_used, missing, report_count, live_count


def _data_quality(system_health: dict[str, Any]) -> str:
    status = str(system_health.get("status") or "UNKNOWN").upper()
    return {
        "HEALTHY": "OK",
        "STRESSED": "ACCEPTABLE",
        "DEGRADED": "DEGRADED",
        "CRITICAL": "INVALID",
    }.get(status, "UNKNOWN")


def _report(payload: dict[str, Any]) -> str:
    def _rows(items: list[Any]) -> list[str]:
        return [f"- {item}" for item in items] if items else ["- NONE"]

    lines = [
        f"# Nova Brain Snapshot Report - {payload.get('timestamp_utc')}",
        "",
        "## Nova Brain Status",
        f"- brain_snapshot_id: {payload.get('brain_snapshot_id')}",
        f"- lineage_id: {payload.get('lineage_id')}",
        "",
        "## System Health",
        f"```json\n{json.dumps(payload.get('system_health', {}), indent=2)}\n```",
        "",
        "## Growing Edges",
        *_rows(payload.get("edge_growth", {}).get("growing_edges", [])),
        "",
        "## Decaying Edges",
        *_rows(payload.get("edge_growth", {}).get("decaying_edges", [])),
        "",
        "## Risk Map",
        f"```json\n{json.dumps(payload.get('risk_map', {}), indent=2)}\n```",
        "",
        "## Fake Scenario Pressure",
        f"```json\n{json.dumps(payload.get('fake_scenario_pressure', {}), indent=2)}\n```",
        "",
        "## Decision Quality Overview",
        f"```json\n{json.dumps(payload.get('decision_quality_overview', {}), indent=2)}\n```",
        "",
        "## Replay Learning Summary",
        f"```json\n{json.dumps(payload.get('replay_learning_summary', {}), indent=2)}\n```",
        "",
        "## Operational Alerts",
        *_rows(payload.get("operational_alerts", [])),
        "",
        "## Dominant Market Story",
        f"```json\n{json.dumps(payload.get('dominant_market_story', {}), indent=2)}\n```",
        "",
        "## Brain Summary",
        *_rows(payload.get("brain_summary", [])),
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
    if payload.get("system_health", {}).get("status") in {"DEGRADED", "CRITICAL"}:
        lines.append("- Stabilize upstream states before trusting operational intelligence.")
    else:
        lines.append("- Review alerts and dominant story before moving to PHASE 11 or PHASE 12.")
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    timestamp_utc = utc_now()
    inputs, files_used, missing, report_count, live_count = _load_inputs()
    system_health = evaluate_system_health(inputs, report_files_count=report_count, live_files_count=live_count)
    edge_intelligence = analyze_edge_intelligence(inputs.get("edge_matrix"))
    risk_intelligence = analyze_risk_intelligence(
        market_state=inputs.get("market_state"),
        active_scenario=inputs.get("active_scenario"),
        flow_reaction=inputs.get("flow_reaction"),
        trade_decision=inputs.get("trade_decision"),
        paper_outcome=inputs.get("paper_outcome"),
        edge_matrix=inputs.get("edge_matrix"),
        replay_engine=inputs.get("replay_engine"),
        edge_intelligence=edge_intelligence,
    )
    story = build_brain_story(
        market_state=inputs.get("market_state"),
        active_scenario=inputs.get("active_scenario"),
        flow_reaction=inputs.get("flow_reaction"),
        trade_decision=inputs.get("trade_decision"),
        system_health=system_health,
        edge_intelligence=edge_intelligence,
        risk_intelligence=risk_intelligence,
    )

    symbol = str((inputs.get("trade_decision") or {}).get("symbol") or "BTCUSDT")
    seed = {
        "system_health_status": system_health.get("status"),
        "growing_edges": len(edge_intelligence.get("growing_edges") or []),
        "global_risk_level": risk_intelligence["risk_map"]["global_risk_level"],
        "decision_quality_status": risk_intelligence["decision_quality_overview"]["status"],
    }
    brain_snapshot_id = build_brain_snapshot_id(symbol, seed)
    lineage_id = build_lineage_id(
        "nova_brain",
        symbol,
        brain_snapshot_id,
        (inputs.get("edge_matrix") or {}).get("edge_matrix_id"),
        (inputs.get("replay_engine") or {}).get("replay_batch_id"),
    )

    reason_codes: list[str] = []
    if missing:
        reason_codes.append("UNKNOWN_SYSTEM_STATE")
    reason_codes.append(f"SYSTEM_HEALTH_{system_health['status']}")
    reason_codes.append(f"GLOBAL_RISK_{risk_intelligence['risk_map']['global_risk_level']}")
    reason_codes.append(f"DECISION_QUALITY_{risk_intelligence['decision_quality_overview']['status']}")

    payload = {
        "timestamp_utc": timestamp_utc,
        "block_id": BRAIN_BLOCK_ID,
        "symbol": symbol,
        "brain_snapshot_id": brain_snapshot_id,
        "lineage_id": lineage_id,
        "system_health": system_health,
        "edge_growth": {
            "growing_edges": edge_intelligence.get("growing_edges", []),
            "stable_edges": edge_intelligence.get("stable_edges", []),
            "decaying_edges": edge_intelligence.get("decaying_edges", []),
            "dead_edges": edge_intelligence.get("dead_edges", []),
        },
        "edge_decay": {
            "fake_edge_density": edge_intelligence.get("fake_edge_density"),
            "strong_clusters": edge_intelligence.get("strong_clusters", []),
        },
        "risk_map": risk_intelligence["risk_map"],
        "fake_scenario_pressure": risk_intelligence["fake_scenario_pressure"],
        "regime_risk": risk_intelligence["regime_risk"],
        "setup_survival": risk_intelligence["setup_survival"],
        "decision_quality_overview": risk_intelligence["decision_quality_overview"],
        "replay_learning_summary": risk_intelligence["replay_learning_summary"],
        "operational_alerts": story["operational_alerts"],
        "dominant_market_story": story["dominant_market_story"],
        "brain_summary": story["brain_summary"],
        "data_quality": _data_quality(system_health),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "warnings": [],
    }

    validation = validate_brain_snapshot(payload)
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
                "last_brain_snapshot_id": brain_snapshot_id,
                "last_lineage_id": lineage_id,
                "system_health_status": system_health["status"],
                "global_risk_level": risk_intelligence["risk_map"]["global_risk_level"],
                "decision_quality_status": risk_intelligence["decision_quality_overview"]["status"],
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
