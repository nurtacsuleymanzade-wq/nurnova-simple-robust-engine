from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path, max_lines: int = 5000) -> list[dict[str, Any]]:
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
        except Exception:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _record_hash(record: dict[str, Any]) -> str:
    stable = {k: v for k, v in record.items() if k not in {"timestamp_utc"}}
    return hashlib.sha256(_canonical(stable).encode("utf-8")).hexdigest()


def _extract_keys(record: dict[str, Any], keys: list[str]) -> list[str]:
    out: list[str] = []
    lineage = record.get("lineage")
    identity = record.get("identity")
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            out.append(str(value))
        if isinstance(lineage, dict):
            lv = lineage.get(key)
            if lv not in (None, ""):
                out.append(str(lv))
        if isinstance(identity, dict):
            iv = identity.get(key)
            if iv not in (None, ""):
                out.append(str(iv))
    return sorted(set(out))


def _fallback_record_id(record: dict[str, Any], prefix: str) -> str:
    ts = str(record.get("timestamp_utc") or "")
    sym = str(record.get("symbol") or "UNKNOWN")
    payload_hash = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{sym}_{ts}_{payload_hash}"


def _normalize_outcome_status(record: dict[str, Any]) -> str:
    status = str(record.get("outcome_status") or record.get("status") or record.get("fate") or "").upper()
    result = str(record.get("outcome_result") or record.get("result") or record.get("close_reason") or "").upper()
    combined = {status, result}
    if any("TIMEOUT" in token for token in combined if token):
        return "OPEN"
    if status in {"CLOSED", "WIN", "LOSS", "TP", "SL", "PARTIAL_WIN", "PARTIAL_LOSS", "TP1_HIT", "TP2_HIT", "SL_HIT"}:
        return "CLOSED"
    if result in {"TP1", "TP2", "SL", "INVALIDATED", "WIN", "LOSS", "PARTIAL_WIN", "PARTIAL_LOSS", "TP1_HIT", "TP2_HIT", "SL_HIT"}:
        return "CLOSED"
    if status in {"OPEN", "ACTIVE", "PENDING", "WAIT", "NO_OUTCOME", "INVALID"}:
        return "OPEN"
    if result in {"NO_LIFECYCLE", "STILL_OPEN", "UNKNOWN", "NO_ENTRY"}:
        return "OPEN"
    if status:
        return status
    return "UNKNOWN"


def _collect_sources(root: Path) -> dict[str, list[Path]]:
    data_simple = root / "data/simple"
    state_simple = root / "state/simple"
    return {
        "outcome_jsonl": sorted(data_simple.glob("*outcome*.jsonl")),
        "edge_jsonl": sorted(data_simple.glob("*edge*.jsonl")),
        "paper_jsonl": sorted(data_simple.glob("*paper*.jsonl")),
        "outcome_state": sorted(state_simple.glob("*outcome*.json")),
        "edge_state": sorted(state_simple.glob("*edge*.json")),
        "paper_state": sorted(state_simple.glob("*paper*.json")),
    }


def _collect_records(paths: list[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() == ".jsonl":
            out.extend(_read_jsonl(path))
        else:
            payload = _read_json(path)
            if payload is not None:
                out.append(payload)
    return out


def _build_outcome_index(outcomes: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    closed_index: dict[str, dict[str, Any]] = {}
    normalized: list[dict[str, Any]] = []
    key_fields = [
        "outcome_id",
        "paper_trade_id",
        "lifecycle_id",
        "trade_id",
        "decision_id",
        "setup_candidate_id",
        "setup_id",
        "candidate_id",
    ]
    for record in outcomes:
        status = _normalize_outcome_status(record)
        rid = _extract_keys(record, key_fields)
        if not rid:
            rid = [_fallback_record_id(record, "outcome")]
        entry = {
            "record": record,
            "status": status,
            "ids": rid,
            "timestamp": _parse_ts(record.get("timestamp_utc")),
            "symbol": str(record.get("symbol") or "BTCUSDT"),
        }
        normalized.append(entry)
        if status == "CLOSED":
            for key in rid:
                closed_index[key] = entry
    return closed_index, normalized


def evaluate_edge_rows(
    edge_rows: list[dict[str, Any]],
    closed_outcome_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    key_fields = [
        "source_outcome_id",
        "parent_outcome_id",
        "outcome_id",
        "source_paper_trade_id",
        "source_decision_id",
        "source_setup_candidate_id",
        "paper_trade_id",
        "lifecycle_id",
        "edge_event_id",
    ]
    for row in edge_rows:
        refs = _extract_keys(row, key_fields)
        if not refs:
            refs = [_fallback_record_id(row, "edge")]
        linked_key = next((key for key in refs if key in closed_outcome_index), None)
        linked_entry = closed_outcome_index.get(linked_key) if linked_key is not None else None
        linked_is_closed = isinstance(linked_entry, dict) and str(linked_entry.get("status") or "").upper() == "CLOSED"
        reasons = list(row.get("reason_codes") or [])
        if linked_key is None or not linked_is_closed:
            if "EDGE_WITHOUT_CLOSED_OUTCOME" not in reasons:
                reasons.append("EDGE_WITHOUT_CLOSED_OUTCOME")
            results.append(
                {
                    "edge_row": row,
                    "linked_closed_outcome_id": None,
                    "edge_lineage_status": "INVALID_EDGE_LINEAGE",
                    "reason_codes": sorted(set(reasons)),
                }
            )
            continue
        results.append(
            {
                "edge_row": row,
                "linked_closed_outcome_id": linked_key,
                "edge_lineage_status": "VALID_EDGE_LINEAGE",
                "reason_codes": sorted(set(reasons)),
            }
        )
    return results


def _repair_orphan_outcomes(
    outcomes_normalized: list[dict[str, Any]],
    paper_records: list[dict[str, Any]],
) -> tuple[int, int, int]:
    paper_keys: set[str] = set()
    paper_times: list[tuple[datetime, str]] = []
    for record in paper_records:
        ids = _extract_keys(record, ["paper_trade_id", "lifecycle_id", "trade_id", "decision_id", "setup_candidate_id", "setup_id", "lineage_id"])
        paper_keys.update(ids)
        ts = _parse_ts(record.get("timestamp_utc"))
        sym = str(record.get("symbol") or "BTCUSDT")
        if ts is not None:
            paper_times.append((ts, sym))

    orphan_total = 0
    repairable = 0
    unrepairable = 0
    for entry in outcomes_normalized:
        ids = set(entry["ids"])
        ts = entry["timestamp"]
        sym = entry["symbol"]
        matched = bool(ids.intersection(paper_keys))
        if not matched and ts is not None:
            for pts, psym in paper_times:
                if psym == sym and abs((ts - pts).total_seconds()) <= 300:
                    matched = True
                    break
        if matched:
            repairable += 1
        else:
            orphan_total += 1
            unrepairable += 1
    return orphan_total, repairable, unrepairable


def _duplicate_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        lineage_id = record.get("lineage_id")
        if not isinstance(lineage_id, str) or not lineage_id:
            lineage = record.get("lineage")
            if isinstance(lineage, dict):
                lineage_id = lineage.get("lineage_id")
        if not isinstance(lineage_id, str) or not lineage_id:
            continue
        groups.setdefault(lineage_id, []).append(record)

    duplicates: list[dict[str, Any]] = []
    for lineage_id, items in groups.items():
        if len(items) <= 1:
            continue
        hashes = sorted(set(_record_hash(item) for item in items))
        if len(hashes) == 1:
            cls = "SAME_PAYLOAD_DUPLICATE"
        elif len(hashes) > 1:
            cls = "CONFLICTING_PAYLOAD_DUPLICATE"
        else:
            cls = "UNKNOWN_DUPLICATE"
        duplicates.append(
            {
                "lineage_id": lineage_id,
                "count": len(items),
                "classification": cls,
            }
        )
    return {
        "total": len(duplicates),
        "items": duplicates,
    }


def _non_deterministic_risks(root: Path) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    patterns = {
        "BUILTIN_HASH_USAGE": "hash(",
        "UUID_USAGE": "uuid",
        "RANDOM_USAGE": "random",
        "RUNTIME_NOW_USAGE": "datetime.now(",
    }
    for path in sorted((root / "src/lineage").glob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for idx, line in enumerate(lines, start=1):
            low = line.lower()
            for code, pat in patterns.items():
                if pat in low:
                    if code == "BUILTIN_HASH_USAGE" and "hashlib" in low:
                        continue
                    risks.append(
                        {
                            "risk_code": code,
                            "file": str(path.relative_to(root)).replace("\\", "/"),
                            "line": idx,
                            "snippet": line.strip(),
                            "suggested_safe_alternative": "use deterministic hashlib.sha256 over canonical payload",
                        }
                    )
    return risks


def run_lineage_repair_audit(root: Path | None = None) -> dict[str, Any]:
    root_path = root or Path(__file__).resolve().parents[2]
    state_lineage = root_path / "state/lineage"
    reports_lineage = root_path / "reports/lineage"
    data_live = root_path / "data/live"
    state_lineage.mkdir(parents=True, exist_ok=True)
    reports_lineage.mkdir(parents=True, exist_ok=True)
    data_live.mkdir(parents=True, exist_ok=True)

    latest_audit = _read_json(state_lineage / "latest_lineage_audit.json") or {}
    health_before = str(latest_audit.get("lineage_health_status") or "UNKNOWN")

    src = _collect_sources(root_path)
    outcome_records = _collect_records(src["outcome_jsonl"] + src["outcome_state"])
    edge_records = _collect_records(src["edge_jsonl"] + src["edge_state"])
    paper_records = _collect_records(src["paper_jsonl"] + src["paper_state"])

    closed_index, outcomes_normalized = _build_outcome_index(outcome_records)
    edge_eval = evaluate_edge_rows(edge_records, closed_index)
    orphan_total, orphan_repairable, orphan_unrepairable = _repair_orphan_outcomes(outcomes_normalized, paper_records)

    all_records = outcome_records + edge_records + paper_records
    duplicate_info = _duplicate_audit(all_records)
    non_det = _non_deterministic_risks(root_path)

    edge_total = len(edge_eval)
    linked_closed = sum(1 for item in edge_eval if item["edge_lineage_status"] == "VALID_EDGE_LINEAGE")
    invalid_edge = edge_total - linked_closed

    if edge_total == 0:
        outcome_to_edge_status = "FAIL"
    elif invalid_edge == 0:
        outcome_to_edge_status = "PASS"
    elif linked_closed > 0:
        outcome_to_edge_status = "PARTIAL"
    else:
        outcome_to_edge_status = "FAIL"

    if outcome_to_edge_status == "PASS" and orphan_unrepairable == 0 and duplicate_info["total"] == 0:
        health_after = "PASS"
    elif linked_closed > 0:
        health_after = "PARTIAL"
    else:
        health_after = "FAIL"

    reason_codes: list[str] = []
    if invalid_edge > 0:
        reason_codes.append("EDGE_WITHOUT_CLOSED_OUTCOME_DETECTED")
    if orphan_unrepairable > 0:
        reason_codes.append("ORPHAN_OUTCOMES_UNREPAIRABLE_PRESENT")
    if duplicate_info["total"] > 0:
        reason_codes.append("DUPLICATE_LINEAGE_IDS_PRESENT")
    if non_det:
        reason_codes.append("NON_DETERMINISTIC_ID_RISKS_PRESENT")

    next_action = "FIX_EDGE_SOURCE_OUTCOME_MAPPING"
    if outcome_to_edge_status == "PASS" and orphan_unrepairable == 0:
        next_action = "RESOLVE_DUPLICATES_AND_NON_DETERMINISTIC_RISKS"
    if health_after == "PASS":
        next_action = "MONITOR_ONLY"

    payload = {
        "timestamp_utc": _now_utc(),
        "block_id": "PHASE_1B_LINEAGE_HYGIENE_REPAIR",
        "lineage_health_before": health_before,
        "lineage_health_after_estimate": health_after,
        "closed_outcome_count": len(closed_index),
        "edge_rows_total": edge_total,
        "edge_rows_linked_to_closed_outcome": linked_closed,
        "edge_rows_invalid_without_closed_outcome": invalid_edge,
        "orphan_outcomes_total": orphan_total,
        "orphan_outcomes_repairable": orphan_repairable,
        "orphan_outcomes_unrepairable": orphan_unrepairable,
        "duplicate_lineage_ids_total": duplicate_info["total"],
        "non_deterministic_id_risks_total": len(non_det),
        "outcome_to_edge_link_status": outcome_to_edge_status,
        "next_action": next_action,
        "reason_codes": sorted(set(reason_codes)),
        "duplicate_lineage_audit": duplicate_info["items"][:200],
        "non_deterministic_id_risks": non_det[:200],
        "invalid_edge_samples": [
            {
                "edge_lineage_status": item["edge_lineage_status"],
                "linked_closed_outcome_id": item["linked_closed_outcome_id"],
                "reason_codes": item["reason_codes"],
            }
            for item in edge_eval
            if item["edge_lineage_status"] == "INVALID_EDGE_LINEAGE"
        ][:200],
    }

    json_path = state_lineage / "latest_lineage_repair.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    event_path = data_live / "lineage_repair_events.jsonl"
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    report_lines = [
        "# Lineage Repair Latest Report",
        "",
        f"- lineage_health_before: {payload['lineage_health_before']}",
        f"- lineage_health_after_estimate: {payload['lineage_health_after_estimate']}",
        f"- closed_outcome_count: {payload['closed_outcome_count']}",
        f"- edge_rows_total: {payload['edge_rows_total']}",
        f"- edge_rows_linked_to_closed_outcome: {payload['edge_rows_linked_to_closed_outcome']}",
        f"- edge_rows_invalid_without_closed_outcome: {payload['edge_rows_invalid_without_closed_outcome']}",
        f"- orphan_outcomes_total: {payload['orphan_outcomes_total']}",
        f"- orphan_outcomes_repairable: {payload['orphan_outcomes_repairable']}",
        f"- orphan_outcomes_unrepairable: {payload['orphan_outcomes_unrepairable']}",
        f"- duplicate_lineage_ids_total: {payload['duplicate_lineage_ids_total']}",
        f"- non_deterministic_id_risks_total: {payload['non_deterministic_id_risks_total']}",
        f"- outcome_to_edge_link_status: {payload['outcome_to_edge_link_status']}",
        f"- next_action: {payload['next_action']}",
        "",
        "## Reason Codes",
    ]
    if payload["reason_codes"]:
        report_lines.extend([f"- {code}" for code in payload["reason_codes"]])
    else:
        report_lines.append("- NONE")
    report_lines.extend(["", "## Duplicate Classifications"])
    if payload["duplicate_lineage_audit"]:
        for item in payload["duplicate_lineage_audit"][:20]:
            report_lines.append(f"- {item['lineage_id']} | {item['classification']} | count={item['count']}")
    else:
        report_lines.append("- NONE")
    report_lines.extend(["", "## Non-Deterministic ID Risks"])
    if payload["non_deterministic_id_risks"]:
        for item in payload["non_deterministic_id_risks"][:20]:
            report_lines.append(f"- {item['risk_code']} | {item['file']}:{item['line']}")
    else:
        report_lines.append("- NONE")
    report_lines.append("")

    report_path = reports_lineage / "lineage_repair_latest_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return payload


def main() -> None:
    payload = run_lineage_repair_audit()
    print(
        json.dumps(
            {
                "ok": True,
                "lineage_health_before": payload["lineage_health_before"],
                "lineage_health_after_estimate": payload["lineage_health_after_estimate"],
                "outcome_to_edge_link_status": payload["outcome_to_edge_link_status"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
