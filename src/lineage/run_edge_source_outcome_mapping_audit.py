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


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path, max_lines: int = 10000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _status_tokens(record: dict[str, Any]) -> set[str]:
    return {
        str(record.get("outcome_status") or record.get("status") or "").upper(),
        str(record.get("outcome_result") or record.get("result") or "").upper(),
        str(record.get("close_reason") or "").upper(),
        str(record.get("fate") or "").upper(),
    }


def _is_timeout_like(record: dict[str, Any]) -> bool:
    return any("TIMEOUT" in token for token in _status_tokens(record) if token)


def _is_closed_outcome(record: dict[str, Any]) -> bool:
    if _is_timeout_like(record):
        return False
    tokens = _status_tokens(record)
    if any(token in {"OPEN", "ACTIVE", "PENDING", "WAIT", "NO_ENTRY", "INVALID", "NO_LIFECYCLE", "STILL_OPEN", "NO_OUTCOME"} for token in tokens):
        return False
    return any(
        token in {
            "CLOSED",
            "WIN",
            "LOSS",
            "TP",
            "SL",
            "PARTIAL_WIN",
            "PARTIAL_LOSS",
            "TP1",
            "TP2",
            "INVALIDATED",
            "TP1_HIT",
            "TP2_HIT",
            "SL_HIT",
        }
        for token in tokens
    )


def _source_field(record: dict[str, Any], key: str) -> Any:
    if record.get(key) not in (None, ""):
        return record.get(key)
    identity = record.get("identity")
    if isinstance(identity, dict) and identity.get(key) not in (None, ""):
        return identity.get(key)
    lineage = record.get("lineage")
    if isinstance(lineage, dict) and lineage.get(key) not in (None, ""):
        return lineage.get(key)
    return None


def _deterministic_outcome_id(record: dict[str, Any]) -> str:
    if record.get("outcome_id") not in (None, ""):
        return str(record.get("outcome_id"))
    basis = {
        "symbol": str(record.get("symbol") or "UNKNOWN"),
        "timestamp_utc": str(record.get("timestamp_utc") or "1970-01-01T00:00:00Z"),
        "paper_trade_id": str(_source_field(record, "paper_trade_id") or _source_field(record, "trade_id") or ""),
        "decision_id": str(_source_field(record, "decision_id") or ""),
        "setup_candidate_id": str(_source_field(record, "setup_candidate_id") or _source_field(record, "setup_id") or ""),
        "payload_hash": _sha256(record),
    }
    return f"OUT_{_sha256(basis)[:24].upper()}"


def _collect_outcomes(root: Path) -> list[dict[str, Any]]:
    paths = sorted((root / "data/simple").glob("*outcome*.jsonl"))
    paths.extend(sorted((root / "state/simple").glob("*outcome*.json")))
    records: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() == ".jsonl":
            records.extend(_read_jsonl(path))
        else:
            payload = _read_json(path)
            if payload is not None:
                records.append(payload)
    return records


def _collect_edges(root: Path) -> list[dict[str, Any]]:
    paths = sorted((root / "data/simple").glob("*edge*.jsonl"))
    paths.extend(sorted((root / "state/simple").glob("*edge*.json")))
    records: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() == ".jsonl":
            records.extend(_read_jsonl(path))
        else:
            payload = _read_json(path)
            if payload is not None:
                records.append(payload)
    return records


def run_edge_source_outcome_mapping_audit(root: Path | None = None) -> dict[str, Any]:
    root_path = root or Path(__file__).resolve().parents[2]
    state_dir = root_path / "state/lineage"
    report_dir = root_path / "reports/lineage"
    state_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    outcomes = _collect_outcomes(root_path)
    edges = _collect_edges(root_path)

    closed_index: set[str] = set()
    for rec in outcomes:
        if not _is_closed_outcome(rec):
            continue
        closed_index.add(_deterministic_outcome_id(rec))
        for field in ("outcome_id", "paper_trade_id", "lifecycle_id", "trade_id", "decision_id", "setup_candidate_id", "setup_id"):
            value = _source_field(rec, field)
            if value not in (None, ""):
                closed_index.add(str(value))

    edge_rows_before = len(edges)
    linked = 0
    suppressed = 0
    invalid = 0

    for row in edges:
        edge_data_status = str(row.get("edge_data_status") or "").upper()
        row_reason_codes = {str(code).upper() for code in (row.get("reason_codes") or [])}
        if edge_data_status == "NO_EDGE_DATA" or "NO_CLOSED_OUTCOMES_FOR_EDGE" in row_reason_codes:
            suppressed += 1
            continue
        refs = [
            row.get("source_outcome_id"),
            row.get("parent_outcome_id"),
            row.get("outcome_id"),
            row.get("source_paper_trade_id"),
            row.get("paper_trade_id"),
            row.get("lifecycle_id"),
        ]
        refs = [str(x) for x in refs if x not in (None, "")]
        if any(ref in closed_index for ref in refs):
            linked += 1
        else:
            invalid += 1

    edge_rows_after = linked
    if edge_rows_after > 0 and invalid == 0:
        status = "PASS"
    elif edge_rows_after > 0:
        status = "PARTIAL"
    else:
        status = "FAIL"

    reason_codes: list[str] = []
    if not closed_index:
        reason_codes.append("NO_CLOSED_OUTCOMES_FOUND")
    if invalid > 0:
        reason_codes.append("EDGE_ROWS_WITHOUT_CLOSED_OUTCOME")
    if suppressed > 0:
        reason_codes.append("EDGE_ROWS_SUPPRESSED_NO_CLOSED_OUTCOME")

    next_action = "MONITOR_ONLY" if status == "PASS" else "RUN_S22_WITH_CLOSED_OUTCOME_INPUTS"
    if status == "FAIL":
        next_action = "FIX_EDGE_SOURCE_OUTCOME_MAPPING"

    payload = {
        "timestamp_utc": _now_utc(),
        "block_id": "PHASE_1C_EDGE_SOURCE_OUTCOME_MAPPING_FIX",
        "closed_outcomes_found": len(closed_index),
        "edge_rows_before": edge_rows_before,
        "edge_rows_after": edge_rows_after,
        "edge_rows_linked_to_closed_outcome": linked,
        "edge_rows_suppressed_no_closed_outcome": suppressed,
        "edge_rows_invalid_without_closed_outcome": invalid,
        "outcome_to_edge_link_status": status,
        "reason_codes": sorted(set(reason_codes)),
        "next_action": next_action,
    }

    json_path = state_dir / "latest_edge_source_outcome_mapping.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Edge Source Outcome Mapping Report",
        "",
        f"- timestamp_utc: {payload['timestamp_utc']}",
        f"- block_id: {payload['block_id']}",
        f"- closed_outcomes_found: {payload['closed_outcomes_found']}",
        f"- edge_rows_before: {payload['edge_rows_before']}",
        f"- edge_rows_after: {payload['edge_rows_after']}",
        f"- edge_rows_linked_to_closed_outcome: {payload['edge_rows_linked_to_closed_outcome']}",
        f"- edge_rows_suppressed_no_closed_outcome: {payload['edge_rows_suppressed_no_closed_outcome']}",
        f"- edge_rows_invalid_without_closed_outcome: {payload['edge_rows_invalid_without_closed_outcome']}",
        f"- outcome_to_edge_link_status: {payload['outcome_to_edge_link_status']}",
        f"- next_action: {payload['next_action']}",
        "",
        "## Reason Codes",
    ]
    if payload["reason_codes"]:
        md_lines.extend([f"- {code}" for code in payload["reason_codes"]])
    else:
        md_lines.append("- NONE")
    md_lines.append("")

    md_path = report_dir / "edge_source_outcome_mapping_report.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return payload


def main() -> None:
    payload = run_edge_source_outcome_mapping_audit()
    print(
        json.dumps(
            {
                "ok": True,
                "closed_outcomes_found": payload["closed_outcomes_found"],
                "edge_rows_linked_to_closed_outcome": payload["edge_rows_linked_to_closed_outcome"],
                "outcome_to_edge_link_status": payload["outcome_to_edge_link_status"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

