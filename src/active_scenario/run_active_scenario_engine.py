from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .active_scenario_candidate_engine import build_scenario_candidates
from .active_scenario_registry import ACTIVE_SCENARIO_BLOCK_ID, DEFAULT_FEEDS_NEXT
from .active_scenario_selector import select_active_scenario
from .active_scenario_validator import validate_active_scenario


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/active_scenario"
REPORTS_DIR = ROOT / "reports/active_scenario"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_active_scenario.json"
ENGINE_STATE_PATH = STATE_DIR / "active_scenario_engine_state.json"
EVENTS_PATH = LIVE_DIR / "active_scenario_events.jsonl"
REPORT_PATH = REPORTS_DIR / "active_scenario_latest_report.md"

INPUT_JSON_PATHS = [
    "state/lineage/latest_lineage_audit.json",
    "state/lineage/lineage_graph_state.json",
    "state/market_state/latest_market_state.json",
    "state/market_state/market_state_engine_state.json",
    "state/latest_liquidity.json",
    "state/latest_structure.json",
    "state/latest_context.json",
    "state/latest_setup_candidate.json",
    "state/latest_trade_plan.json",
    "state/latest_decision_gate.json",
    "state/latest_outcome.json",
    "state/simple/latest_liquidity_structure.json",
    "state/simple/latest_setup_candidate.json",
    "state/simple/latest_decision.json",
    "state/simple/latest_outcome.json",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canon(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_last_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            end = handle.tell()
            if end <= 0:
                return None
            pos = end
            chunk = b""
            while pos > 0 and chunk.count(b"\n") < 2:
                step = 4096 if pos >= 4096 else pos
                pos -= step
                handle.seek(pos)
                chunk = handle.read(step) + chunk
        lines = [x.strip() for x in chunk.decode("utf-8", errors="ignore").splitlines() if x.strip()]
        if not lines:
            return None
        payload = json.loads(lines[-1])
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _collect_records() -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    records: dict[str, dict[str, Any]] = {}
    used: list[str] = []
    missing: list[str] = []

    for rel in INPUT_JSON_PATHS:
        path = ROOT / rel
        payload = _read_json(path)
        key = path.stem.replace("latest_", "")
        if payload is None:
            missing.append(rel)
            continue
        records[key] = payload
        used.append(rel)

    for base_rel in ("data/live", "data/simple"):
        base = ROOT / base_rel
        if not base.exists():
            missing.append(base_rel)
            continue
        for path in sorted(base.glob("*.jsonl")):
            name = path.name.lower()
            if not any(
                tag in name
                for tag in (
                    "scenario",
                    "liquidity",
                    "structure",
                    "flow",
                    "reaction",
                    "market_state",
                    "decision",
                    "setup",
                    "trade_plan",
                    "outcome",
                )
            ):
                continue
            payload = _read_last_jsonl(path)
            if payload is None:
                continue
            records[f"jsonl_{path.stem}"] = payload
            used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return records, sorted(set(used)), sorted(set(missing))


def _pick_symbol(records: dict[str, dict[str, Any]]) -> str:
    for payload in records.values():
        symbol = payload.get("symbol")
        if isinstance(symbol, str) and symbol:
            return symbol
    return "BTCUSDT"


def _best_timestamp(records: dict[str, dict[str, Any]]) -> str:
    best: datetime | None = None
    out = None
    for p in records.values():
        raw = p.get("timestamp_utc")
        if not isinstance(raw, str):
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        if best is None or dt > best:
            best = dt
            out = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out or _utc_now()


def _extract_parent_lineage_ids(records: dict[str, dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for p in records.values():
        lid = p.get("lineage_id")
        if isinstance(lid, str) and lid:
            out.add(lid)
        lineage = p.get("lineage")
        if isinstance(lineage, dict):
            x = lineage.get("lineage_id")
            if isinstance(x, str) and x:
                out.add(x)
            parent_ids = lineage.get("parent_lineage_ids")
            if isinstance(parent_ids, list):
                for pid in parent_ids:
                    if isinstance(pid, str) and pid:
                        out.add(pid)
    return sorted(out)


def _evidence_bundle(records: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    market_state = records.get("market_state", {})
    liquidity = records.get("liquidity", records.get("liquidity_structure", records.get("jsonl_liquidity_structure", {})))
    structure = records.get("structure", records.get("jsonl_market_structure_history", records.get("jsonl_market_structure_v2_history", {})))
    flow = records.get("jsonl_flow_evidence", records.get("jsonl_flow_persistence", records.get("jsonl_live_flow_events", {})))
    reaction = records.get("jsonl_liquidity_structure", records.get("jsonl_outcome_monitor_history", records.get("outcome", {})))
    risk = {
        "market_state_risk": market_state.get("risk_state"),
        "market_state_quality": market_state.get("data_quality"),
        "decision_snapshot": records.get("decision", {}),
        "outcome_snapshot": records.get("outcome", {}),
    }
    return {
        "market_state_evidence": market_state if isinstance(market_state, dict) else {},
        "liquidity_evidence": liquidity if isinstance(liquidity, dict) else {},
        "structure_evidence": structure if isinstance(structure, dict) else {},
        "flow_evidence": flow if isinstance(flow, dict) else {},
        "reaction_evidence": reaction if isinstance(reaction, dict) else {},
        "risk_evidence": risk,
    }


def _deterministic_ids(
    *,
    symbol: str,
    timestamp_utc: str,
    market_state_id: str | None,
    active_scenario: str,
    parent_lineage_ids: list[str],
    selected_candidate: dict[str, Any],
) -> tuple[str, str]:
    candidate_hash = hashlib.sha256(_canon(selected_candidate or {}).encode("utf-8")).hexdigest()[:20]
    raw = {
        "symbol": symbol,
        "timestamp_utc": timestamp_utc,
        "market_state_id": market_state_id or "",
        "active_scenario": active_scenario,
        "parent_lineage_ids": sorted(parent_lineage_ids),
        "candidate_hash": candidate_hash,
    }
    active_scenario_id = "ASC_" + hashlib.sha256(_canon(raw).encode("utf-8")).hexdigest()[:24].upper()
    lineage_raw = {
        "node_type": "scenario",
        "active_scenario_id": active_scenario_id,
        "market_state_id": market_state_id or "",
    }
    lineage_id = "LINCTX_" + hashlib.sha256(_canon(lineage_raw).encode("utf-8")).hexdigest()[:24].upper()
    return active_scenario_id, lineage_id


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _report(payload: dict[str, Any], validation: dict[str, Any]) -> str:
    lines = [
        "# Active Scenario Latest Report",
        "",
        "## Active Scenario Status",
        f"- {'PASS' if validation.get('is_valid') else 'FAIL'}",
        "",
        "## Selected Scenario",
        f"- {payload.get('active_scenario')}",
        "",
        "## Scenario Bias",
        f"- {payload.get('scenario_bias')}",
        "",
        "## Scenario Confidence",
        f"- {payload.get('scenario_confidence')}",
        "",
        "## Scenario Quality",
        f"- {payload.get('scenario_quality')}",
        "",
        "## Market State Link",
        f"- market_state_id: {payload.get('market_state_id')}",
        f"- lineage_id: {payload.get('lineage_id')}",
        "",
        "## Evidence Used",
    ]
    for src in (payload.get("evidence") or {}).get("market_state_evidence", {}):
        _ = src
        break
    lines.append(f"- scenario_candidates_count: {len(payload.get('scenario_candidates') or [])}")
    lines.extend(
        [
            "",
            "## Candidate Scores",
        ]
    )
    for k, v in (payload.get("candidate_scores") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "## Selection Reasons"])
    for x in payload.get("selection_reason_codes") or []:
        lines.append(f"- {x}")
    lines.extend(["", "## Rejection Reasons"])
    for x in payload.get("rejection_reason_codes") or []:
        lines.append(f"- {x}")
    lines.extend(["", "## Conflict Reasons"])
    for x in payload.get("conflict_reason_codes") or []:
        lines.append(f"- {x}")
    lines.extend(["", "## Data Quality", f"- {payload.get('data_quality')}", "", "## Warnings"])
    warnings = list(payload.get("warnings") or []) + list(validation.get("errors") or [])
    if warnings:
        for x in sorted(set(warnings)):
            lines.append(f"- {x}")
    else:
        lines.append("- NONE")
    lines.extend(["", "## Feeds Next"])
    for nxt in payload.get("feeds_next") or []:
        lines.append(f"- {nxt}")
    lines.extend(["", "## Next Action", f"- {'PHASE_4_FLOW_CONFIRMATION_POST_LIQUIDITY_REACTION' if validation.get('is_valid') else 'FIX_ACTIVE_SCENARIO_CONTRACT'}", ""])
    return "\n".join(lines)


def run_active_scenario_engine() -> dict[str, Any]:
    records, used, missing = _collect_records()
    symbol = _pick_symbol(records)
    ts = _best_timestamp(records)
    evidence = _evidence_bundle(records)

    market_state = evidence.get("market_state_evidence") or {}
    market_state_id = market_state.get("market_state_id") if isinstance(market_state, dict) else None
    market_state_present = isinstance(market_state_id, str) and bool(market_state_id)
    data_quality = str((market_state or {}).get("data_quality") or "UNKNOWN")

    candidates, frame = build_scenario_candidates(evidence=evidence, data_quality=data_quality)
    selected = select_active_scenario(
        candidates=candidates,
        feature_frame=frame,
        data_quality=data_quality,
        market_state_present=market_state_present,
    )

    parent_lineage_ids = _extract_parent_lineage_ids(records)
    if isinstance(market_state, dict):
        ms_lid = market_state.get("lineage_id")
        if isinstance(ms_lid, str) and ms_lid and ms_lid not in parent_lineage_ids:
            parent_lineage_ids.append(ms_lid)
    parent_lineage_ids = sorted(set(parent_lineage_ids))

    active_scenario_id, lineage_id = _deterministic_ids(
        symbol=symbol,
        timestamp_utc=ts,
        market_state_id=market_state_id if isinstance(market_state_id, str) else None,
        active_scenario=str(selected.get("active_scenario") or "UNKNOWN"),
        parent_lineage_ids=parent_lineage_ids,
        selected_candidate=selected.get("selected_candidate") if isinstance(selected.get("selected_candidate"), dict) else {},
    )

    reason_codes: list[str] = []
    warnings: list[str] = []
    if not market_state_present:
        reason_codes.append("MARKET_STATE_MISSING")
    if not parent_lineage_ids:
        reason_codes.append("PARENT_LINEAGE_MISSING")
    if not candidates:
        reason_codes.append("NO_CANDIDATE_GENERATED")
    if missing:
        warnings.append(f"MISSING_INPUT_COUNT_{len(missing)}")
    if data_quality in ("INVALID", "UNKNOWN"):
        reason_codes.append("LOW_QUALITY_MARKET_STATE_INPUT")

    payload = {
        "timestamp_utc": ts,
        "block_id": ACTIVE_SCENARIO_BLOCK_ID,
        "symbol": symbol,
        "active_scenario_id": active_scenario_id,
        "lineage_id": lineage_id,
        "parent_lineage_ids": parent_lineage_ids,
        "market_state_id": market_state_id if isinstance(market_state_id, str) else None,
        "active_scenario": selected["active_scenario"],
        "scenario_bias": selected["scenario_bias"],
        "scenario_confidence": selected["scenario_confidence"],
        "scenario_quality": selected["scenario_quality"],
        "selection_reason_codes": selected["selection_reason_codes"],
        "rejection_reason_codes": selected["rejection_reason_codes"],
        "conflict_reason_codes": selected["conflict_reason_codes"],
        "scenario_candidates": candidates,
        "selected_candidate": selected["selected_candidate"] if isinstance(selected["selected_candidate"], dict) else {},
        "evidence": evidence,
        "candidate_scores": selected["candidate_scores"],
        "data_quality": data_quality if data_quality in ("OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN") else "UNKNOWN",
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "reason_codes": sorted(set(reason_codes + list(selected["selection_reason_codes"]))),
        "warnings": sorted(set(warnings)),
    }

    validation = validate_active_scenario(payload)
    if not validation["is_valid"]:
        payload["scenario_quality"] = "INVALID"
        payload["data_quality"] = "INVALID"
        payload["warnings"] = sorted(set(list(payload["warnings"]) + validation["errors"]))
        payload["reason_codes"] = sorted(set(list(payload["reason_codes"]) + ["VALIDATOR_FAILED"]))

    engine_state = {
        "timestamp_utc": _utc_now(),
        "block_id": "PHASE_3_ACTIVE_SCENARIO_ENGINE_STATE",
        "status": "PASS" if validation["is_valid"] else "FAIL",
        "symbol": symbol,
        "active_scenario_id": active_scenario_id,
        "lineage_id": lineage_id,
        "market_state_id": payload.get("market_state_id"),
        "input_summary": {
            "source_files_used_count": len(used),
            "missing_sources_count": len(missing),
            "source_files_used": used,
            "missing_sources": missing,
        },
        "validation": validation,
    }

    _write_json(LATEST_PATH, payload)
    _write_json(ENGINE_STATE_PATH, engine_state)
    _append_jsonl(EVENTS_PATH, payload)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_report(payload, validation), encoding="utf-8")
    return payload


def main() -> None:
    payload = run_active_scenario_engine()
    print(
        json.dumps(
            {
                "ok": True,
                "active_scenario": payload.get("active_scenario"),
                "scenario_confidence": payload.get("scenario_confidence"),
                "scenario_quality": payload.get("scenario_quality"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

