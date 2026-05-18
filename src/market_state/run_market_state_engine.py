from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .market_state_classifier import classify_market_state
from .market_state_validator import validate_market_state


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/market_state"
REPORTS_DIR = ROOT / "reports/market_state"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_market_state.json"
ENGINE_STATE_PATH = STATE_DIR / "market_state_engine_state.json"
EVENTS_PATH = LIVE_DIR / "market_state_events.jsonl"
REPORT_PATH = REPORTS_DIR / "market_state_latest_report.md"


INPUT_JSON_PATHS = [
    "state/lineage/latest_lineage_audit.json",
    "state/lineage/lineage_graph_state.json",
    "state/latest_candle_dna.json",
    "state/latest_structure.json",
    "state/latest_liquidity.json",
    "state/latest_context.json",
    "state/latest_setup_candidate.json",
    "state/latest_trade_plan.json",
    "state/latest_decision_gate.json",
    "state/latest_outcome.json",
    "state/simple/latest_hybrid_candle_dna.json",
    "state/simple/latest_liquidity_structure.json",
    "state/simple/latest_setup_candidate.json",
    "state/simple/latest_decision.json",
    "state/simple/latest_outcome.json",
    "state/simple/latest_flow_state.json",
    "state/simple/latest_flow_evidence.json",
    "state/simple/latest_market_regime.json",
    "state/simple/latest_regime_classifier.json",
    "state/simple/latest_market_structure_v2.json",
    "state/simple/latest_liquidity_map.json",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_last_jsonl_record(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            end = handle.tell()
            if end <= 0:
                return None
            chunk_size = 4096
            data = b""
            pos = end
            while pos > 0 and data.count(b"\n") < 2:
                step = chunk_size if pos >= chunk_size else pos
                pos -= step
                handle.seek(pos)
                data = handle.read(step) + data
        lines = [ln.strip() for ln in data.decode("utf-8", errors="ignore").splitlines() if ln.strip()]
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
                    "flow",
                    "liquidity",
                    "structure",
                    "regime",
                    "candle",
                    "context",
                    "setup",
                    "trade_plan",
                    "decision",
                    "outcome",
                    "edge",
                )
            ):
                continue
            payload = _read_last_jsonl_record(path)
            if payload is None:
                continue
            key = f"jsonl_{path.stem}"
            records[key] = payload
            used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return records, sorted(set(used)), sorted(set(missing))


def _pick_symbol(records: dict[str, dict[str, Any]]) -> str:
    for payload in records.values():
        symbol = payload.get("symbol")
        if isinstance(symbol, str) and symbol:
            return symbol
    return "BTCUSDT"


def _extract_parent_lineage_ids(records: dict[str, dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for payload in records.values():
        lineage_id = payload.get("lineage_id")
        if isinstance(lineage_id, str) and lineage_id:
            out.add(lineage_id)
        lineage = payload.get("lineage")
        if isinstance(lineage, dict):
            lid = lineage.get("lineage_id")
            if isinstance(lid, str) and lid:
                out.add(lid)
            parents = lineage.get("parent_lineage_ids")
            if isinstance(parents, list):
                for parent in parents:
                    if isinstance(parent, str) and parent:
                        out.add(parent)
    return sorted(out)


def _evidence_bundle(records: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "lineage_audit": records.get("lineage_audit", {}),
        "lineage_graph": records.get("lineage_graph_state", {}),
        "candle_dna": records.get("candle_dna", records.get("hybrid_candle_dna", {})),
        "structure": records.get("structure", records.get("market_structure_v2", records.get("liquidity_structure", {}))),
        "liquidity": records.get("liquidity", records.get("liquidity_map", records.get("liquidity_structure", {}))),
        "context": records.get("context", records.get("market_regime", records.get("regime_classifier", {}))),
        "flow": records.get("flow_evidence", records.get("flow_state", {})),
        "setup_candidate": records.get("setup_candidate", {}),
        "trade_plan": records.get("trade_plan", {}),
        "decision_gate": records.get("decision_gate", records.get("decision", {})),
        "outcome": records.get("outcome", {}),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _build_report(payload: dict[str, Any], validation: dict[str, Any]) -> str:
    lines = [
        "# Market State Latest Report",
        "",
        "## Market State Status",
        f"- {'PASS' if validation.get('is_valid') else 'FAIL'}",
        "",
        "## Market Regime",
        f"- {payload.get('market_regime')}",
        "",
        "## Confidence",
        f"- {payload.get('confidence')}",
        "",
        "## Data Quality",
        f"- {payload.get('data_quality')}",
        "",
        "## Evidence Used",
    ]
    used = (payload.get("evidence") or {}).get("source_files_used") or []
    if used:
        lines.extend([f"- {item}" for item in used])
    else:
        lines.append("- NONE")
    lines.extend(
        [
            "",
            "## Reason Codes",
        ]
    )
    for code in payload.get("reason_codes") or []:
        lines.append(f"- {code}")
    lines.extend(
        [
            "",
            "## Warnings",
        ]
    )
    warnings = list(payload.get("warnings") or [])
    warnings.extend(validation.get("errors") or [])
    if warnings:
        for w in sorted(set(warnings)):
            lines.append(f"- {w}")
    else:
        lines.append("- NONE")
    lines.extend(
        [
            "",
            "## Lineage Link",
            f"- lineage_id: {payload.get('lineage_id')}",
            f"- parent_lineage_ids: {len(payload.get('parent_lineage_ids') or [])}",
            "",
            "## Feeds Next",
        ]
    )
    for nxt in payload.get("feeds_next") or []:
        lines.append(f"- {nxt}")
    lines.extend(
        [
            "",
            "## Next Action",
            f"- {'PROMPT_3_ACTIVE_SCENARIO_ENGINE' if validation.get('is_valid') else 'FIX_MARKET_STATE_CONTRACT_ERRORS'}",
            "",
        ]
    )
    return "\n".join(lines)


def run_market_state_engine() -> dict[str, Any]:
    records, source_files_used, missing_sources = _collect_records()
    symbol = _pick_symbol(records)
    parent_lineage_ids = _extract_parent_lineage_ids(records)
    evidence = _evidence_bundle(records)

    payload = classify_market_state(
        symbol=symbol,
        evidence_records=evidence,
        source_files_used=source_files_used,
        missing_sources=missing_sources,
        parent_lineage_ids=parent_lineage_ids,
    )

    validation = validate_market_state(payload)
    if not validation["is_valid"]:
        payload["warnings"] = sorted(set(list(payload.get("warnings") or []) + validation["errors"]))
        payload["reason_codes"] = sorted(set(list(payload.get("reason_codes") or []) + ["VALIDATOR_FAILED"]))
        payload["data_quality"] = "INVALID"

    engine_state = {
        "timestamp_utc": _utc_now(),
        "block_id": "PHASE_2_MARKET_STATE_ENGINE_STATE",
        "status": "PASS" if validation["is_valid"] else "FAIL",
        "symbol": payload.get("symbol"),
        "market_state_id": payload.get("market_state_id"),
        "lineage_id": payload.get("lineage_id"),
        "input_summary": {
            "source_files_used_count": len(source_files_used),
            "missing_sources_count": len(missing_sources),
            "source_files_used": source_files_used,
            "missing_sources": missing_sources,
        },
        "validation": validation,
    }

    _write_json(LATEST_PATH, payload)
    _write_json(ENGINE_STATE_PATH, engine_state)
    _append_jsonl(EVENTS_PATH, payload)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_build_report(payload, validation), encoding="utf-8")
    return payload


def main() -> None:
    payload = run_market_state_engine()
    print(
        json.dumps(
            {
                "ok": True,
                "market_state_id": payload.get("market_state_id"),
                "market_regime": payload.get("market_regime"),
                "data_quality": payload.get("data_quality"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

