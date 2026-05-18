from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any

from .lineage_validator import validate_lineage_nodes


def _depth_stats(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(n.get("lineage_id")): n for n in nodes if n.get("lineage_id")}
    indegree = defaultdict(int)
    graph = defaultdict(list)
    for node in nodes:
        nid = str(node.get("lineage_id") or "")
        for parent_id in node.get("parent_lineage_ids") or []:
            if str(parent_id) in by_id:
                graph[str(parent_id)].append(nid)
                indegree[nid] += 1
        indegree.setdefault(nid, indegree.get(nid, 0))

    q = deque([nid for nid, d in indegree.items() if d == 0 and nid])
    depth = {nid: 0 for nid in q}
    while q:
        cur = q.popleft()
        for nxt in graph.get(cur, []):
            depth[nxt] = max(depth.get(nxt, 0), depth.get(cur, 0) + 1)
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)

    values = list(depth.values()) or [0]
    return {
        "min_depth": min(values),
        "max_depth": max(values),
        "avg_depth": round(sum(values) / len(values), 4),
        "known_depth_nodes": len(values),
    }


def _link_status(nodes: list[dict[str, Any]]) -> tuple[str, str, str]:
    by_id = {str(n.get("lineage_id")): n for n in nodes if n.get("lineage_id")}
    outcomes = [n for n in nodes if n.get("node_type") == "outcome"]
    edges = [n for n in nodes if n.get("node_type") == "edge_row"]
    setups = [n for n in nodes if n.get("node_type") == "setup_candidate"]
    scenarios = [n for n in nodes if n.get("node_type") == "scenario"]

    linked_outcomes = 0
    for edge in edges:
        parents = [by_id.get(str(pid)) for pid in (edge.get("parent_lineage_ids") or [])]
        if any(
            p
            and p.get("node_type") == "outcome"
            and str(p.get("outcome_status") or "").upper() == "CLOSED"
            for p in parents
        ):
            linked_outcomes += 1
    outcome_to_edge = "PASS" if linked_outcomes > 0 else "FAIL"

    setup_to_outcome = "FAIL"
    if setups and outcomes:
        setup_ids = {str(x.get("source_record_id") or "") for x in setups}
        for out in outcomes:
            if str(out.get("source_record_id") or "") in setup_ids:
                setup_to_outcome = "PASS"
                break
        if setup_to_outcome == "FAIL":
            setup_to_outcome = "PARTIAL" if outcomes else "FAIL"

    scenario_to_edge = "FAIL"
    if scenarios and edges:
        scenario_ids = {str(x.get("source_record_id") or "") for x in scenarios}
        for edge in edges:
            if str(edge.get("source_record_id") or "") in scenario_ids:
                scenario_to_edge = "PASS"
                break
        if scenario_to_edge == "FAIL":
            scenario_to_edge = "PARTIAL"

    return outcome_to_edge, setup_to_outcome, scenario_to_edge


def build_lineage_graph_report(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    validation = validate_lineage_nodes(nodes)
    counts = Counter(str(n.get("node_type") or "UNKNOWN") for n in nodes)
    outcome_to_edge, setup_to_outcome, scenario_to_edge = _link_status(nodes)

    critical_breaks = (
        len(validation["orphan_outcomes"])
        + len(validation["orphan_edge_rows"])
        + len(validation["duplicate_lineage_ids"])
        + len(validation["circular_links"])
        + len(validation["broken_parent_links"])
    )
    lineage_health_status = "PASS" if critical_breaks == 0 else "PARTIAL" if critical_breaks < 10 else "FAIL"

    return {
        "lineage_nodes_count": len(nodes),
        "node_type_distribution": dict(counts),
        "orphan_nodes": validation["orphan_nodes"],
        "orphan_outcomes": validation["orphan_outcomes"],
        "orphan_edge_rows": validation["orphan_edge_rows"],
        "broken_parent_links": validation["broken_parent_links"],
        "broken_child_links": validation["broken_child_links"],
        "duplicate_lineage_ids": validation["duplicate_lineage_ids"],
        "circular_links": validation["circular_links"],
        "lineage_depth_stats": _depth_stats(nodes),
        "outcome_to_edge_link_status": outcome_to_edge,
        "setup_to_outcome_link_status": setup_to_outcome,
        "scenario_to_edge_link_status": scenario_to_edge,
        "critical_missing_fields": validation["missing_required_fields"],
        "lineage_health_status": lineage_health_status,
        "validator": validation,
    }
