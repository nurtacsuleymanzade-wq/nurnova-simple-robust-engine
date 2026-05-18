from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .conditional_edge_engine import build_conditional_edge_rows
from .edge_matrix_registry import (
    DEFAULT_FEEDS_NEXT,
    EDGE_MATRIX_BLOCK_ID,
    build_edge_matrix_id,
    build_lineage_id,
    utc_now,
)
from .edge_matrix_validator import validate_conditional_edge_matrix
from .edge_metrics_engine import calculate_all_edge_metrics

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/edge_matrix"
REPORTS_DIR = ROOT / "reports/edge_matrix"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_conditional_edge_matrix.json"
ENGINE_STATE_PATH = STATE_DIR / "edge_matrix_engine_state.json"
EVENTS_PATH = LIVE_DIR / "conditional_edge_matrix_events.jsonl"
REPORT_PATH = REPORTS_DIR / "conditional_edge_matrix_latest_report.md"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path, max_lines: int = 1000) -> list[dict[str, Any]]:
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


def _collect_outcomes() -> tuple[list[dict[str, Any]], list[str], list[str]]:
    records: list[dict[str, Any]] = []
    files_used: list[str] = []
    missing: list[str] = []

    configured = [
        ROOT / "state/paper_outcome/latest_paper_outcome.json",
        ROOT / "data/live/paper_outcome_events.jsonl",
        ROOT / "state/lineage/latest_edge_source_outcome_mapping.json",
        ROOT / "state/setup_entry/latest_setup_entry.json",
        ROOT / "state/trade_decision/latest_trade_decision.json",
        ROOT / "state/active_scenario/latest_active_scenario.json",
        ROOT / "state/market_state/latest_market_state.json",
        ROOT / "state/flow_reaction/latest_flow_reaction.json",
    ]
    for path in configured:
        if not path.exists():
            missing.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    direct_paths = [
        ROOT / "state/paper_outcome/latest_paper_outcome.json",
        ROOT / "data/live/paper_outcome_events.jsonl",
    ]
    for path in direct_paths:
        if path.suffix.lower() == ".json":
            payload = _read_json(path)
            if payload is not None:
                records.append(payload)
                files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
        else:
            items = _read_jsonl(path)
            if items:
                records.extend(items)
                files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    for pattern in ("data/simple/*outcome*.jsonl", "data/simple/*paper*.jsonl"):
        matched = sorted(ROOT.glob(pattern))
        if not matched:
            missing.append(pattern)
        for path in matched:
            items = _read_jsonl(path)
            if not items:
                continue
            records.extend(items)
            files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        key = str(record.get("outcome_id") or record.get("paper_trade_id") or json.dumps(record, sort_keys=True, ensure_ascii=False))
        deduped[key] = record
    return list(deduped.values()), sorted(set(files_used)), sorted(set(missing))


def _latest_context() -> dict[str, dict[str, Any] | None]:
    return {
        "setup_entry": _read_json(ROOT / "state/setup_entry/latest_setup_entry.json"),
        "trade_decision": _read_json(ROOT / "state/trade_decision/latest_trade_decision.json"),
        "active_scenario": _read_json(ROOT / "state/active_scenario/latest_active_scenario.json"),
        "market_state": _read_json(ROOT / "state/market_state/latest_market_state.json"),
        "flow_reaction": _read_json(ROOT / "state/flow_reaction/latest_flow_reaction.json"),
        "lineage_mapping": _read_json(ROOT / "state/lineage/latest_edge_source_outcome_mapping.json"),
    }


def _assess_data_quality(metrics_rows: list[dict[str, Any]], missing_sources: list[str]) -> str:
    if not metrics_rows and missing_sources:
        return "DEGRADED"
    degraded_like = sum(1 for row in metrics_rows if row.get("edge_status") == "DEGRADED_BY_DATA_QUALITY")
    if metrics_rows and degraded_like / len(metrics_rows) >= 0.4:
        return "DEGRADED"
    if missing_sources:
        return "ACCEPTABLE"
    return "OK"


def _summaries(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    positive = [row for row in rows if (row.get("expectancy_r") or 0.0) > 0]
    negative = [row for row in rows if (row.get("expectancy_r") or 0.0) < 0]

    top_positive = sorted(
        positive,
        key=lambda row: ((row.get("expectancy_r") or 0.0), (row.get("winrate") or 0.0), row.get("sample_size") or 0),
        reverse=True,
    )[:5]
    top_negative = sorted(
        negative,
        key=lambda row: ((row.get("expectancy_r") or 0.0), -(row.get("sample_size") or 0)),
    )[:5]

    failure_patterns = [
        {
            "edge_row_id": row.get("edge_row_id"),
            "group_key": row.get("group_key"),
            "failure_reason_top": row.get("failure_reason_top"),
            "expectancy_r": row.get("expectancy_r"),
            "sample_size": row.get("sample_size"),
        }
        for row in top_negative
    ]

    high_probability_clusters = [
        {
            "edge_row_id": row.get("edge_row_id"),
            "group_key": row.get("group_key"),
            "winrate": row.get("winrate"),
            "expectancy_r": row.get("expectancy_r"),
            "sample_size": row.get("sample_size"),
            "edge_status": row.get("edge_status"),
        }
        for row in rows
        if (row.get("sample_size") or 0) >= 10 and (row.get("winrate") or 0.0) >= 0.6 and (row.get("expectancy_r") or 0.0) > 0
    ][:5]
    return top_positive, top_negative, failure_patterns, high_probability_clusters


def _build_report(payload: dict[str, Any]) -> str:
    def _rows(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[str]:
        lines: list[str] = []
        if not items:
            return ["- NONE"]
        for item in items:
            parts = [f"{field}={item.get(field)}" for field in fields]
            lines.append(f"- {' | '.join(parts)}")
        return lines

    lines = [
        f"# Conditional Edge Matrix Report - {payload.get('timestamp_utc')}",
        "",
        "## Conditional Edge Matrix Status",
        f"- edge_matrix_id: {payload.get('edge_matrix_id')}",
        f"- lineage_id: {payload.get('lineage_id')}",
        "",
        "## Source Outcomes",
        f"- {payload.get('source_outcome_count')}",
        "",
        "## Edge Eligible Outcomes",
        f"- {payload.get('edge_eligible_outcome_count')}",
        "",
        "## Excluded Outcomes",
        f"- excluded_outcome_count: {payload.get('excluded_outcome_count')}",
        f"- excluded_breakdown: {json.dumps(payload.get('excluded_breakdown', {}), ensure_ascii=False)}",
        "",
        "## Top Positive Edges",
        *_rows(payload.get("top_positive_edges", []), ("edge_row_id", "expectancy_r", "winrate", "sample_size", "edge_status")),
        "",
        "## Top Negative Edges",
        *_rows(payload.get("top_negative_edges", []), ("edge_row_id", "expectancy_r", "lossrate", "sample_size", "edge_status")),
        "",
        "## Failure Patterns",
        *_rows(payload.get("failure_patterns", []), ("edge_row_id", "failure_reason_top", "expectancy_r", "sample_size")),
        "",
        "## High Probability Clusters",
        *_rows(payload.get("high_probability_clusters", []), ("edge_row_id", "winrate", "expectancy_r", "sample_size", "edge_status")),
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
    if payload.get("edge_eligible_outcome_count", 0) == 0:
        lines.append("- No closed eligible outcomes yet; keep collecting PHASE 7 truth records.")
    else:
        lines.append("- Review top positive and negative clusters before using them in PHASE 10 or PHASE 11.")
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    timestamp_utc = utc_now()
    records, files_used, missing_sources = _collect_outcomes()
    latest_context = _latest_context()

    conditional = build_conditional_edge_rows(records, latest_context=latest_context)
    metrics_rows = calculate_all_edge_metrics(conditional["conditional_rows"])

    source_outcome_ids = sorted(
        {
            source_id
            for row in metrics_rows
            for source_id in row.get("source_outcome_ids", [])
            if source_id
        }
    )
    symbol = str(
        (latest_context.get("trade_decision") or {}).get("symbol")
        or (next((record.get("symbol") for record in records if record.get("symbol")), None))
        or "BTCUSDT"
    )
    edge_matrix_id = build_edge_matrix_id(symbol, source_outcome_ids)
    lineage_mapping = latest_context.get("lineage_mapping") or {}
    lineage_id = build_lineage_id(
        "edge_matrix",
        symbol,
        edge_matrix_id,
        lineage_mapping.get("outcome_to_edge_link_status"),
        conditional["excluded_outcome_count"],
    )

    top_positive_edges, top_negative_edges, failure_patterns, high_probability_clusters = _summaries(metrics_rows)
    data_quality = _assess_data_quality(metrics_rows, missing_sources)

    reason_codes = list(conditional.get("reason_codes") or [])
    if missing_sources:
        reason_codes.append("NO_DATA_SOURCE_MISSING")
    if not metrics_rows:
        reason_codes.append("NO_DATA")

    payload = {
        "timestamp_utc": timestamp_utc,
        "block_id": EDGE_MATRIX_BLOCK_ID,
        "symbol": symbol,
        "edge_matrix_id": edge_matrix_id,
        "lineage_id": lineage_id,
        "source_outcome_count": len(conditional["source_records"]),
        "edge_eligible_outcome_count": len(conditional["eligible_records"]),
        "excluded_outcome_count": conditional["excluded_outcome_count"],
        "excluded_breakdown": conditional["excluded_breakdown"],
        "conditional_edge_rows": metrics_rows,
        "top_positive_edges": top_positive_edges,
        "top_negative_edges": top_negative_edges,
        "failure_patterns": failure_patterns,
        "high_probability_clusters": high_probability_clusters,
        "data_quality": data_quality,
        "reason_codes": list(dict.fromkeys(reason_codes or ["EDGE_MATRIX_COMPUTED"])),
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "warnings": [],
    }

    validation = validate_conditional_edge_matrix(payload)
    if not validation["is_valid"]:
        payload["warnings"] = list(dict.fromkeys(validation["errors"]))

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    LATEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    status_counts = Counter(row.get("edge_status") for row in metrics_rows)
    engine_state = {
        "timestamp_utc": timestamp_utc,
        "last_edge_matrix_id": edge_matrix_id,
        "last_lineage_id": lineage_id,
        "source_outcome_count": payload["source_outcome_count"],
        "edge_eligible_outcome_count": payload["edge_eligible_outcome_count"],
        "excluded_outcome_count": payload["excluded_outcome_count"],
        "edge_status_counts": dict(status_counts),
        "data_quality": data_quality,
        "validation_passed": validation["is_valid"],
        "validation_errors": validation["errors"],
        "files_used": files_used,
        "missing_sources": missing_sources,
    }
    ENGINE_STATE_PATH.write_text(json.dumps(engine_state, indent=2, ensure_ascii=False), encoding="utf-8")

    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    REPORT_PATH.write_text(_build_report(payload), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
