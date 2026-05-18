from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .lineage_builder import build_lineage_node
from .lineage_graph_engine import build_lineage_graph_report
from .lineage_registry import LINEAGE_REGISTRY, NODE_TYPES


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_jsonl(path: Path, max_lines: int = 300) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                out.append(payload)
        except Exception:
            continue
    return out


def _path_candidates(root: Path) -> tuple[list[Path], list[Path]]:
    explicit = [
        root / "state/latest_setup_candidate.json",
        root / "state/latest_trade_plan.json",
        root / "state/latest_decision_gate.json",
        root / "state/latest_outcome.json",
        root / "state/latest_edge_matrix.json",
    ]
    existing: list[Path] = []
    missing: list[Path] = []
    for path in explicit:
        if path.exists():
            existing.append(path)
        else:
            missing.append(path)

    for pattern in ("data/live/*.jsonl", "data/simple/*.jsonl", "state/simple/*.json", "state/simple/epoch_v2/*.json"):
        for path in sorted(root.glob(pattern)):
            existing.append(path)
    return existing, missing


def _infer_node_type(path: Path, record: dict[str, Any]) -> str:
    text = f"{path.as_posix().lower()}|{str(record.get('block_id') or '').lower()}"
    if "raw" in text and "flow" in text:
        return "raw_event"
    if "1s_evidence" in text or "flow_evidence" in text:
        return "evidence"
    if "candle_dna" in text:
        return "candle_dna"
    if "observation" in text or "footprint" in text:
        return "footprint"
    if "liquidity" in text:
        return "liquidity"
    if "market_structure" in text or "structure_quality" in text:
        return "structure"
    if "market_regime" in text or "regime_classifier" in text:
        return "market_state"
    if "scenario" in text:
        return "scenario"
    if "setup_candidate" in text or "setup_classifier" in text or "setup_contract" in text:
        return "setup_candidate"
    if "signal_event" in text or "signal_grade" in text:
        return "entry_trigger"
    if "trade_plan" in text:
        return "trade_plan"
    if "decision" in text:
        return "decision"
    if "paper_lifecycle" in text or "paper_trade" in text:
        return "paper_trade"
    if "outcome" in text:
        return "outcome"
    if "edge" in text:
        return "edge_row"
    if "replay" in text or "true_outcome" in text:
        return "replay"
    if "brain" in text:
        return "brain_snapshot"
    return "raw_event"


def _fallback_block(node_type: str) -> str:
    return str((LINEAGE_REGISTRY.get(node_type) or {}).get("block_id") or "UNKNOWN_BLOCK")


def _source_record_id_candidates(record: dict[str, Any], node_type: str) -> list[str]:
    field_map = {
        "raw_event": ["raw_event_id", "event_id"],
        "evidence": ["evidence_id", "event_id", "bucket_second"],
        "candle_dna": ["candle_dna_id", "event_id"],
        "footprint": ["footprint_id", "event_id"],
        "liquidity": ["liquidity_state_id", "event_id"],
        "structure": ["structure_state_id", "event_id"],
        "market_state": ["market_state_id", "event_id"],
        "scenario": ["scenario_id", "active_scenario_id", "event_id"],
        "setup_candidate": ["setup_candidate_id", "setup_id", "event_id"],
        "entry_trigger": ["entry_trigger_id", "signal_id", "event_id"],
        "trade_plan": ["trade_plan_id", "plan_id", "event_id"],
        "decision": ["decision_id", "event_id"],
        "paper_trade": ["paper_trade_id", "lifecycle_id", "event_id"],
        "outcome": ["outcome_id", "paper_trade_id", "lifecycle_id", "event_id"],
        "edge_row": ["edge_row_id", "edge_event_id", "event_id"],
        "replay": ["replay_id", "event_id"],
        "brain_snapshot": ["brain_snapshot_id", "event_id"],
    }
    values: list[str] = []
    for key in field_map.get(node_type, []):
        value = record.get(key)
        if value not in (None, ""):
            values.append(str(value))
    return values


def _extract_parent_refs(record: dict[str, Any], expected_parent_types: list[str]) -> dict[str, list[str]]:
    by_type: dict[str, list[str]] = {}
    if isinstance(record.get("parent_lineage_ids"), list):
        by_type["_lineage"] = [str(x) for x in record["parent_lineage_ids"] if str(x)]
        return by_type

    parent_fields = {
        "raw_event": ["raw_event_id"],
        "evidence": ["evidence_id"],
        "candle_dna": ["candle_dna_id"],
        "footprint": ["footprint_id", "observation_id"],
        "liquidity": ["liquidity_state_id"],
        "structure": ["structure_state_id"],
        "market_state": ["market_state_id", "regime_id"],
        "scenario": ["scenario_id", "active_scenario_id"],
        "setup_candidate": ["setup_candidate_id", "setup_id"],
        "entry_trigger": ["entry_trigger_id", "signal_id"],
        "trade_plan": ["trade_plan_id", "plan_id"],
        "decision": ["decision_id"],
        "paper_trade": ["paper_trade_id", "lifecycle_id"],
        "outcome": ["outcome_id"],
        "edge_row": ["edge_row_id", "edge_event_id"],
        "replay": ["replay_id"],
        "brain_snapshot": ["brain_snapshot_id"],
    }
    generic = {
        "setup_id": "setup_candidate",
        "setup_candidate_id": "setup_candidate",
        "signal_id": "entry_trigger",
        "trade_plan_id": "trade_plan",
        "plan_id": "trade_plan",
        "decision_id": "decision",
        "source_decision_id": "decision",
        "paper_trade_id": "paper_trade",
        "source_paper_trade_id": "paper_trade",
        "lifecycle_id": "paper_trade",
        "outcome_id": "outcome",
        "source_outcome_id": "outcome",
        "parent_outcome_id": "outcome",
        "edge_event_id": "edge_row",
    }
    for ptype in expected_parent_types:
        refs: list[str] = []
        for field in parent_fields.get(ptype, []):
            value = record.get(field)
            if value not in (None, ""):
                refs.append(str(value))
        if refs:
            by_type[ptype] = refs
    for field, ptype in generic.items():
        if ptype not in expected_parent_types:
            continue
        value = record.get(field)
        if value not in (None, ""):
            by_type.setdefault(ptype, []).append(str(value))
    return by_type


def _extract_outcome_status(record: dict[str, Any], node_type: str) -> str | None:
    if node_type != "outcome":
        return None
    value = record.get("outcome_status")
    if value is None and isinstance(record.get("result"), dict):
        value = record["result"].get("outcome")
    return str(value) if value is not None else None


def run_lineage_audit(root: Path | None = None) -> dict[str, Any]:
    root_path = root or Path(__file__).resolve().parents[2]
    state_lineage_dir = root_path / "state/lineage"
    reports_lineage_dir = root_path / "reports/lineage"
    live_data_dir = root_path / "data/live"
    state_lineage_dir.mkdir(parents=True, exist_ok=True)
    reports_lineage_dir.mkdir(parents=True, exist_ok=True)
    live_data_dir.mkdir(parents=True, exist_ok=True)

    source_files, missing_sources = _path_candidates(root_path)

    records_by_path: dict[Path, list[dict[str, Any]]] = {}
    for path in source_files:
        if path.suffix.lower() == ".json":
            payload = _read_json(path)
            if payload is None:
                continue
            records_by_path[path] = [payload]
        elif path.suffix.lower() == ".jsonl":
            records_by_path[path] = _read_jsonl(path)

    nodes: list[dict[str, Any]] = []
    source_index: dict[str, dict[str, str]] = {node_type: {} for node_type in NODE_TYPES}
    outcome_status_by_lineage: dict[str, str] = {}

    for path in sorted(records_by_path.keys(), key=lambda p: str(p).lower()):
        for record in records_by_path[path]:
            node_type = _infer_node_type(path, record)
            source_block = str(record.get("block_id") or _fallback_block(node_type))
            expected_parent_types = list((LINEAGE_REGISTRY.get(node_type) or {}).get("expected_parent_types") or [])
            parent_ref_map = _extract_parent_refs(record, expected_parent_types)

            parent_lineage_ids: list[str] = []
            if "_lineage" in parent_ref_map:
                parent_lineage_ids.extend(parent_ref_map["_lineage"])
            else:
                for ptype, refs in parent_ref_map.items():
                    for ref in refs:
                        lineage_id = source_index.get(ptype, {}).get(ref)
                        if lineage_id:
                            parent_lineage_ids.append(lineage_id)

            source_id_candidates = _source_record_id_candidates(record, node_type)
            chosen_source_id = source_id_candidates[0] if source_id_candidates else None

            # Outcome -> Edge only through CLOSED outcomes
            if node_type == "edge_row":
                closed_parent_ids = []
                for pid in parent_lineage_ids:
                    if str(outcome_status_by_lineage.get(pid, "")).upper() == "CLOSED":
                        closed_parent_ids.append(pid)
                parent_lineage_ids = closed_parent_ids

            node = build_lineage_node(
                node_type=node_type,
                source_block=source_block,
                source_file=str(path.relative_to(root_path)).replace("\\", "/"),
                source_record=record,
                parent_lineage_ids=parent_lineage_ids,
                source_record_id=chosen_source_id,
            )
            nodes.append(node)

            if node_type == "outcome":
                outcome_status_by_lineage[node["lineage_id"]] = str(_extract_outcome_status(record, node_type) or "")

            for sid in source_id_candidates:
                source_index[node_type][sid] = node["lineage_id"]
            if node.get("source_record_id"):
                source_index[node_type][str(node["source_record_id"])] = node["lineage_id"]

    graph = build_lineage_graph_report(nodes)
    non_deterministic_id_risks: list[str] = []
    for node in nodes:
        if not node.get("timestamp_utc") or node.get("timestamp_utc") == "1970-01-01T00:00:00Z":
            non_deterministic_id_risks.append(str(node.get("lineage_id")))

    next_action = "PATCH_PARENT_LINEAGE_LINKS"
    if graph["lineage_health_status"] == "PASS":
        next_action = "MONITOR_ONLY"
    elif graph["outcome_to_edge_link_status"] == "FAIL":
        next_action = "FIX_OUTCOME_TO_EDGE_CLOSED_LINK"

    audit_payload = {
        "generated_at_utc": _now_utc(),
        "lineage_health_status": graph["lineage_health_status"],
        "total_nodes": graph["lineage_nodes_count"],
        "orphan_nodes": graph["orphan_nodes"],
        "orphan_outcomes": graph["orphan_outcomes"],
        "orphan_edge_rows": graph["orphan_edge_rows"],
        "broken_links": {
            "broken_parent_links": graph["broken_parent_links"],
            "broken_child_links": graph["broken_child_links"],
        },
        "duplicate_lineage_ids": graph["duplicate_lineage_ids"],
        "circular_links": graph["circular_links"],
        "critical_missing_fields": graph["critical_missing_fields"],
        "outcome_to_edge_link_status": graph["outcome_to_edge_link_status"],
        "setup_to_outcome_link_status": graph["setup_to_outcome_link_status"],
        "scenario_to_edge_link_status": graph["scenario_to_edge_link_status"],
        "lineage_depth_stats": graph["lineage_depth_stats"],
        "node_type_distribution": graph["node_type_distribution"],
        "missing_source": [str(path.relative_to(root_path)).replace("\\", "/") for path in missing_sources],
        "non_deterministic_id_risks": sorted(set(non_deterministic_id_risks)),
        "next_action": next_action,
    }

    graph_state = {
        "generated_at_utc": audit_payload["generated_at_utc"],
        "lineage_health_status": audit_payload["lineage_health_status"],
        "lineage_nodes_count": audit_payload["total_nodes"],
        "orphan_outcomes": audit_payload["orphan_outcomes"],
        "orphan_edge_rows": audit_payload["orphan_edge_rows"],
        "duplicate_lineage_ids": audit_payload["duplicate_lineage_ids"],
        "circular_links": audit_payload["circular_links"],
        "outcome_to_edge_link_status": audit_payload["outcome_to_edge_link_status"],
        "node_type_distribution": audit_payload["node_type_distribution"],
    }

    audit_path = state_lineage_dir / "latest_lineage_audit.json"
    graph_path = state_lineage_dir / "lineage_graph_state.json"
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    graph_path.write_text(json.dumps(graph_state, ensure_ascii=False, indent=2), encoding="utf-8")

    event_path = live_data_dir / "lineage_audit_events.jsonl"
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(graph_state, ensure_ascii=False) + "\n")

    report_path = reports_lineage_dir / "lineage_audit_latest_report.md"
    report_lines = [
        "# Lineage Audit Latest Report",
        "",
        f"- lineage_health_status: {audit_payload['lineage_health_status']}",
        f"- total_nodes: {audit_payload['total_nodes']}",
        f"- orphan_outcomes: {len(audit_payload['orphan_outcomes'])}",
        f"- orphan_edge_rows: {len(audit_payload['orphan_edge_rows'])}",
        f"- broken_links: {len(audit_payload['broken_links']['broken_parent_links']) + len(audit_payload['broken_links']['broken_child_links'])}",
        f"- duplicate_ids: {len(audit_payload['duplicate_lineage_ids'])}",
        f"- critical_missing_fields: {len(audit_payload['critical_missing_fields'])}",
        f"- outcome_to_edge_status: {audit_payload['outcome_to_edge_link_status']}",
        f"- next_action: {audit_payload['next_action']}",
        "",
        "## Missing Sources",
    ]
    if audit_payload["missing_source"]:
        report_lines.extend([f"- {item}" for item in audit_payload["missing_source"]])
    else:
        report_lines.append("- NONE")

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return audit_payload


def main() -> None:
    payload = run_lineage_audit()
    print(
        json.dumps(
            {
                "ok": True,
                "lineage_health_status": payload["lineage_health_status"],
                "total_nodes": payload["total_nodes"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
