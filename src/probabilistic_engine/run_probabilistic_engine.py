from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .future_path_engine import build_future_paths
from .probability_cluster_engine import build_probability_clusters
from .probabilistic_validator import validate_probabilistic_payload
from .risk_path_engine import analyze_risk_paths
from .scenario_registry import (
    DEFAULT_FEEDS_NEXT,
    PROBABILISTIC_BLOCK_ID,
    build_lineage_id,
    build_scenario_engine_id,
    utc_now,
)
from .scenario_tree_engine import build_scenario_tree

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/probabilistic_engine"
REPORTS_DIR = ROOT / "reports/probabilistic_engine"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_probabilistic_engine.json"
ENGINE_STATE_PATH = STATE_DIR / "probabilistic_engine_state.json"
EVENTS_PATH = LIVE_DIR / "probabilistic_engine_events.jsonl"
REPORT_PATH = REPORTS_DIR / "probabilistic_engine_latest_report.md"


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
        "nova_brain": ROOT / "state/nova_brain/latest_nova_brain_snapshot.json",
    }
    inputs = {name: _read_json(path) for name, path in mapping.items()}
    files_used = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if path.exists()]
    missing = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if not path.exists()]
    report_count = len(list((ROOT / "reports").glob("**/*latest_report.md")))
    live_count = len(list((ROOT / "data/live").glob("*.jsonl")))
    return inputs, files_used, missing, report_count, live_count


def _data_quality(inputs: dict[str, Any], missing: list[str]) -> str:
    if len(missing) >= 5:
        return "INVALID"
    if len(missing) >= 3:
        return "DEGRADED"
    if len(missing) >= 1:
        return "ACCEPTABLE"
    upstream = str((inputs.get("nova_brain") or {}).get("data_quality") or "UNKNOWN").upper()
    return upstream if upstream in {"OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN"} else "UNKNOWN"


def _market_story_projection(
    dominant_path: dict[str, Any],
    active_scenario: dict[str, Any],
    flow_reaction: dict[str, Any],
) -> dict[str, Any]:
    return {
        "primary_projection": dominant_path.get("expected_behavior"),
        "active_scenario": active_scenario.get("active_scenario"),
        "flow_confirmation": flow_reaction.get("flow_confirmation"),
        "post_liquidity_reaction": flow_reaction.get("post_liquidity_reaction"),
    }


def _report(payload: dict[str, Any]) -> str:
    def _rows(items: list[Any]) -> list[str]:
        return [f"- {item}" for item in items] if items else ["- NONE"]

    lines = [
        f"# Probabilistic Engine Report - {payload.get('timestamp_utc')}",
        "",
        "## Probabilistic Engine Status",
        f"- scenario_engine_id: {payload.get('scenario_engine_id')}",
        f"- lineage_id: {payload.get('lineage_id')}",
        "",
        "## Dominant Future Paths",
        f"```json\n{json.dumps(payload.get('dominant_path', {}), indent=2)}\n```",
        "",
        "## Probability Clusters",
        f"```json\n{json.dumps(payload.get('probability_clusters', []), indent=2)}\n```",
        "",
        "## Scenario Tree",
        f"```json\n{json.dumps(payload.get('scenario_tree', {}), indent=2)}\n```",
        "",
        "## Risk Paths",
        f"```json\n{json.dumps(payload.get('risk_paths', []), indent=2)}\n```",
        "",
        "## Continuation Survival",
        f"```json\n{json.dumps(payload.get('survival_probabilities', {}), indent=2)}\n```",
        "",
        "## Fake Breakout Probabilities",
        f"```json\n{json.dumps(payload.get('fake_breakout_probabilities', {}), indent=2)}\n```",
        "",
        "## Liquidity Attraction Zones",
        f"```json\n{json.dumps(payload.get('liquidity_attraction_zones', []), indent=2)}\n```",
        "",
        "## Market Story Projection",
        f"```json\n{json.dumps(payload.get('market_story_projection', {}), indent=2)}\n```",
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
    if "UNKNOWN_PROBABILITY_STATE" in (payload.get("reason_codes") or []):
        lines.append("- Stabilize upstream context before relying on scenario probabilities.")
    else:
        lines.append("- Compare dominant path and pressure map before moving to PHASE 12 or PHASE 13.")
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    timestamp_utc = utc_now()
    inputs, files_used, missing, report_count, live_count = _load_inputs()
    probability_clusters = build_probability_clusters(
        edge_matrix=inputs.get("edge_matrix"),
        replay_engine=inputs.get("replay_engine"),
        market_state=inputs.get("market_state"),
        active_scenario=inputs.get("active_scenario"),
        flow_reaction=inputs.get("flow_reaction"),
        nova_brain=inputs.get("nova_brain"),
    )
    future_paths, dominant_path = build_future_paths(
        market_state=inputs.get("market_state"),
        active_scenario=inputs.get("active_scenario"),
        flow_reaction=inputs.get("flow_reaction"),
        edge_matrix=inputs.get("edge_matrix"),
        replay_engine=inputs.get("replay_engine"),
        nova_brain=inputs.get("nova_brain"),
        probability_clusters=probability_clusters,
    )
    scenario_tree = build_scenario_tree(future_paths, dominant_path)
    risk_paths = analyze_risk_paths(
        market_state=inputs.get("market_state"),
        active_scenario=inputs.get("active_scenario"),
        flow_reaction=inputs.get("flow_reaction"),
        nova_brain=inputs.get("nova_brain"),
        future_paths=future_paths,
    )

    symbol = str((inputs.get("trade_decision") or {}).get("symbol") or (inputs.get("market_state") or {}).get("symbol") or "BTCUSDT")
    data_quality = _data_quality(inputs, missing)
    seed = {
        "dominant_path": dominant_path.get("scenario_path"),
        "dominant_probability": dominant_path.get("estimated_probability"),
        "pressure_level": risk_paths["scenario_pressure_map"].get("pressure_level"),
        "report_count": report_count,
        "live_count": live_count,
    }
    scenario_engine_id = build_scenario_engine_id(symbol, seed)
    lineage_id = build_lineage_id(
        "probabilistic_engine",
        symbol,
        scenario_engine_id,
        (inputs.get("nova_brain") or {}).get("brain_snapshot_id"),
        (inputs.get("edge_matrix") or {}).get("edge_matrix_id"),
        (inputs.get("replay_engine") or {}).get("replay_batch_id"),
    )

    reason_codes: list[str] = []
    if missing:
        reason_codes.append("UNKNOWN_PROBABILITY_STATE")
    if not probability_clusters:
        reason_codes.append("NO_CLUSTER_DATA")
    reason_codes.append(f"DOMINANT_PATH_{dominant_path.get('scenario_path', 'UNKNOWN_PATH')}")
    reason_codes.append(f"PRESSURE_{risk_paths['scenario_pressure_map'].get('pressure_level', 'UNKNOWN')}")

    payload = {
        "timestamp_utc": timestamp_utc,
        "block_id": PROBABILISTIC_BLOCK_ID,
        "symbol": symbol,
        "scenario_engine_id": scenario_engine_id,
        "lineage_id": lineage_id,
        "future_paths": future_paths,
        "probability_clusters": probability_clusters,
        "scenario_tree": scenario_tree,
        "market_path_forecast": {
            "dominant_path": dominant_path.get("scenario_path"),
            "estimated_probability": dominant_path.get("estimated_probability"),
            "branch_count": scenario_tree.get("branch_count"),
        },
        "risk_paths": risk_paths["risk_paths"],
        "survival_probabilities": risk_paths["survival_probabilities"],
        "fake_breakout_probabilities": risk_paths["fake_breakout_probabilities"],
        "continuation_probabilities": risk_paths["continuation_probabilities"],
        "liquidity_attraction_zones": risk_paths["liquidity_attraction_zones"],
        "dominant_path": dominant_path,
        "scenario_pressure_map": risk_paths["scenario_pressure_map"],
        "market_story_projection": _market_story_projection(dominant_path, inputs.get("active_scenario") or {}, inputs.get("flow_reaction") or {}),
        "data_quality": data_quality,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "warnings": [],
    }

    validation = validate_probabilistic_payload(payload)
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
                "last_scenario_engine_id": scenario_engine_id,
                "last_lineage_id": lineage_id,
                "dominant_path": dominant_path.get("scenario_path"),
                "dominant_probability": dominant_path.get("estimated_probability"),
                "pressure_level": risk_paths["scenario_pressure_map"].get("pressure_level"),
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
