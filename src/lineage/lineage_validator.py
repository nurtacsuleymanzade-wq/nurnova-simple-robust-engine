from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .lineage_registry import LINEAGE_REGISTRY, NODE_TYPES


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _build_children(nodes: list[dict[str, Any]]) -> None:
    by_id = {str(n.get("lineage_id")): n for n in nodes if n.get("lineage_id")}
    for node in nodes:
        node["child_lineage_ids"] = list(node.get("child_lineage_ids") or [])
    for node in nodes:
        nid = str(node.get("lineage_id") or "")
        for parent_id in node.get("parent_lineage_ids") or []:
            p = by_id.get(str(parent_id))
            if p is not None and nid and nid not in p["child_lineage_ids"]:
                p["child_lineage_ids"].append(nid)


def _detect_cycles(nodes: list[dict[str, Any]]) -> list[list[str]]:
    by_id = {str(n.get("lineage_id")): n for n in nodes if n.get("lineage_id")}
    graph = defaultdict(list)
    for n in nodes:
        nid = str(n.get("lineage_id") or "")
        for parent in n.get("parent_lineage_ids") or []:
            if nid and parent in by_id:
                graph[str(parent)].append(nid)

    cycles: list[list[str]] = []
    seen: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []

    def dfs(node_id: str) -> None:
        seen.add(node_id)
        stack.add(node_id)
        path.append(node_id)
        for nxt in graph.get(node_id, []):
            if nxt not in seen:
                dfs(nxt)
            elif nxt in stack:
                if nxt in path:
                    idx = path.index(nxt)
                    cycles.append(path[idx:] + [nxt])
        stack.discard(node_id)
        path.pop()

    for nid in by_id:
        if nid not in seen:
            dfs(nid)
    return cycles


def validate_lineage_nodes(nodes: list[dict[str, Any]], stale_threshold_hours: int = 24 * 30) -> dict[str, Any]:
    _build_children(nodes)
    by_id = {str(n.get("lineage_id")): n for n in nodes if n.get("lineage_id")}
    id_counts = Counter(str(n.get("lineage_id")) for n in nodes if n.get("lineage_id"))
    duplicate_lineage_ids = sorted([nid for nid, cnt in id_counts.items() if cnt > 1])

    missing_required: list[dict[str, Any]] = []
    invalid_node_type: list[str] = []
    missing_source_block: list[str] = []
    invalid_timestamp: list[str] = []
    stale_nodes: list[str] = []
    broken_parent_links: list[dict[str, Any]] = []
    broken_child_links: list[dict[str, Any]] = []
    parent_type_mismatch: list[dict[str, Any]] = []
    child_type_mismatch: list[dict[str, Any]] = []

    now = datetime.now(timezone.utc)
    for node in nodes:
        lineage_id = str(node.get("lineage_id") or "")
        node_type = str(node.get("node_type") or "")
        if node_type not in NODE_TYPES:
            invalid_node_type.append(lineage_id)
            continue

        spec = LINEAGE_REGISTRY[node_type]
        for field in spec["required_fields"]:
            if field not in node:
                missing_required.append({"lineage_id": lineage_id, "field": field})

        if not node.get("source_block"):
            missing_source_block.append(lineage_id)

        ts = _parse_ts(node.get("timestamp_utc"))
        if ts is None:
            invalid_timestamp.append(lineage_id)
        else:
            age_hours = (now - ts).total_seconds() / 3600.0
            if age_hours > stale_threshold_hours:
                stale_nodes.append(lineage_id)

        parent_ids = [str(x) for x in (node.get("parent_lineage_ids") or []) if str(x)]
        if node_type != "raw_event" and not parent_ids:
            missing_required.append({"lineage_id": lineage_id, "field": "parent_lineage_ids"})

        for parent_id in parent_ids:
            parent = by_id.get(parent_id)
            if parent is None:
                broken_parent_links.append({"lineage_id": lineage_id, "parent_lineage_id": parent_id})
                continue
            if parent.get("node_type") not in spec["expected_parent_types"]:
                parent_type_mismatch.append(
                    {
                        "lineage_id": lineage_id,
                        "node_type": node_type,
                        "parent_lineage_id": parent_id,
                        "parent_node_type": parent.get("node_type"),
                    }
                )

        child_ids = [str(x) for x in (node.get("child_lineage_ids") or []) if str(x)]
        for child_id in child_ids:
            child = by_id.get(child_id)
            if child is None:
                broken_child_links.append({"lineage_id": lineage_id, "child_lineage_id": child_id})
                continue
            if child.get("node_type") not in spec["expected_child_types"]:
                child_type_mismatch.append(
                    {
                        "lineage_id": lineage_id,
                        "node_type": node_type,
                        "child_lineage_id": child_id,
                        "child_node_type": child.get("node_type"),
                    }
                )

    orphan_nodes = []
    orphan_outcomes = []
    orphan_edge_rows = []
    for node in nodes:
        node_type = str(node.get("node_type") or "")
        lineage_id = str(node.get("lineage_id") or "")
        has_parents = bool(node.get("parent_lineage_ids"))
        if node_type != "raw_event" and not has_parents:
            orphan_nodes.append(lineage_id)
        if node_type == "outcome":
            parent_ok = any(
                (by_id.get(str(pid)) or {}).get("node_type") == "paper_trade"
                for pid in (node.get("parent_lineage_ids") or [])
            )
            if not parent_ok:
                orphan_outcomes.append(lineage_id)
        if node_type == "edge_row":
            parent_ok = any(
                (by_id.get(str(pid)) or {}).get("node_type") == "outcome"
                and str((by_id.get(str(pid)) or {}).get("outcome_status") or "").upper() == "CLOSED"
                for pid in (node.get("parent_lineage_ids") or [])
            )
            if not parent_ok:
                orphan_edge_rows.append(lineage_id)

    circular_links = _detect_cycles(nodes)

    return {
        "total_nodes": len(nodes),
        "missing_required_fields": missing_required,
        "invalid_node_type": sorted(set(invalid_node_type)),
        "missing_source_block": sorted(set(missing_source_block)),
        "invalid_timestamp": sorted(set(invalid_timestamp)),
        "stale_nodes": sorted(set(stale_nodes)),
        "broken_parent_links": broken_parent_links,
        "broken_child_links": broken_child_links,
        "parent_type_mismatch": parent_type_mismatch,
        "child_type_mismatch": child_type_mismatch,
        "orphan_nodes": sorted(set(orphan_nodes)),
        "orphan_outcomes": sorted(set(orphan_outcomes)),
        "orphan_edge_rows": sorted(set(orphan_edge_rows)),
        "duplicate_lineage_ids": duplicate_lineage_ids,
        "circular_links": circular_links,
    }
