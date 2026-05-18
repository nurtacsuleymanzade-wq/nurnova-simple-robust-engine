from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .alignment_engine import compute_alignment
from .bias_extractor import extract_perspective_biases
from .conflict_engine import evaluate_conflicts
from .perspective_merger_registry import (
    DEFAULT_FEEDS_NEXT,
    PERSPECTIVE_MERGER_BLOCK_ID,
    build_lineage_id,
    build_perspective_merger_id,
    utc_now,
)
from .perspective_merger_validator import validate_perspective_merger

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/perspective_merger"
REPORTS_DIR = ROOT / "reports/perspective_merger"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_perspective_merger.json"
ENGINE_STATE_PATH = STATE_DIR / "perspective_merger_state.json"
EVENTS_PATH = LIVE_DIR / "perspective_merger_events.jsonl"
REPORT_PATH = REPORTS_DIR / "perspective_merger_latest_report.md"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_inputs() -> tuple[dict[str, dict[str, Any] | None], list[str], list[str]]:
    mapping = {
        "market_state": ROOT / "state/market_state/latest_market_state.json",
        "active_scenario": ROOT / "state/active_scenario/latest_active_scenario.json",
        "flow_reaction": ROOT / "state/flow_reaction/latest_flow_reaction.json",
        "setup_entry": ROOT / "state/setup_entry/latest_setup_entry.json",
        "trade_decision": ROOT / "state/trade_decision/latest_trade_decision.json",
        "edge_matrix": ROOT / "state/edge_matrix/latest_conditional_edge_matrix.json",
        "nova_brain": ROOT / "state/nova_brain/latest_nova_brain_snapshot.json",
        "probabilistic_engine": ROOT / "state/probabilistic_engine/latest_probabilistic_engine.json",
        "smc": ROOT / "state/smc/latest_smart_money_perspective.json",
        "mm": ROOT / "state/mm/latest_market_maker_perspective.json",
    }
    inputs = {name: _read_json(path) for name, path in mapping.items()}
    files_used = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if path.exists()]
    missing = [str(path.relative_to(ROOT)).replace("\\", "/") for path in mapping.values() if not path.exists()]
    return inputs, files_used, missing


def _data_quality(inputs: dict[str, Any]) -> str:
    if not any(inputs.get(name) for name in ("market_state", "active_scenario", "flow_reaction", "setup_entry", "trade_decision", "nova_brain", "probabilistic_engine")):
        return "INVALID"
    missing_count = sum(1 for name in ("smc", "mm") if not inputs.get(name))
    if missing_count == 2:
        return "DEGRADED"
    if missing_count == 1:
        return "ACCEPTABLE"
    upstream = str((inputs.get("nova_brain") or {}).get("data_quality") or "UNKNOWN").upper()
    return upstream if upstream in {"OK", "ACCEPTABLE", "DEGRADED", "INVALID", "UNKNOWN"} else "UNKNOWN"


def _report(payload: dict[str, Any]) -> str:
    def _rows(items: list[Any]) -> list[str]:
        return [f"- {item}" for item in items] if items else ["- NONE"]

    lines = [
        f"# Perspective Merger Report - {payload.get('timestamp_utc')}",
        "",
        "## Perspective Merger Status",
        f"- perspective_merger_id: {payload.get('perspective_merger_id')}",
        f"- lineage_id: {payload.get('lineage_id')}",
        "",
        "## Core Bias",
        f"- {payload.get('core_bias')} ({payload.get('core_confidence')})",
        "",
        "## Smart Money Bias",
        f"- {payload.get('smc_bias')} ({payload.get('smc_confidence')})",
        "",
        "## Market Maker Bias",
        f"- {payload.get('mm_bias')} ({payload.get('mm_confidence')})",
        "",
        "## Alignment Status",
        f"- {payload.get('alignment_status')}",
        "",
        "## Alignment Score",
        f"- {payload.get('alignment_score')}",
        "",
        "## Perspective Agreement",
        f"```json\n{json.dumps(payload.get('perspective_agreement', {}), indent=2)}\n```",
        "",
        "## Bias Conflicts",
        f"```json\n{json.dumps(payload.get('bias_conflicts', []), indent=2)}\n```",
        "",
        "## Conflict Sources",
        *_rows(payload.get("conflict_sources", [])),
        "",
        "## Confidence Adjustment",
        f"```json\n{json.dumps(payload.get('confidence_adjustment', {}), indent=2)}\n```",
        "",
        "## Decision Gate Context Note",
        f"- {payload.get('decision_gate_context_note')}",
        "",
        "## Nova Brain Context Note",
        f"- {payload.get('nova_brain_context_note')}",
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
    lines.append("- Use merged alignment as context only; do not override decision or brain outputs.")
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    timestamp_utc = utc_now()
    inputs, files_used, missing = _load_inputs()
    extracted = extract_perspective_biases(inputs)
    alignment = compute_alignment(extracted["core_bias"], extracted["smc_bias"], extracted["mm_bias"])
    conflicts = evaluate_conflicts(
        core_bias=extracted["core_bias"],
        smc_bias=extracted["smc_bias"],
        mm_bias=extracted["mm_bias"],
        core_confidence=extracted["core_confidence"],
        smc_confidence=extracted["smc_confidence"],
        mm_confidence=extracted["mm_confidence"],
        alignment_status=alignment["alignment_status"],
    )

    symbol = str((inputs.get("trade_decision") or {}).get("symbol") or (inputs.get("market_state") or {}).get("symbol") or "BTCUSDT")
    seed = {
        "core_bias": extracted["core_bias"],
        "smc_bias": extracted["smc_bias"],
        "mm_bias": extracted["mm_bias"],
        "alignment_status": alignment["alignment_status"],
        "alignment_score": alignment["alignment_score"],
    }
    merger_id = build_perspective_merger_id(symbol, seed)
    lineage_id = build_lineage_id(
        "perspective_merger",
        symbol,
        merger_id,
        (inputs.get("nova_brain") or {}).get("brain_snapshot_id"),
        (inputs.get("probabilistic_engine") or {}).get("scenario_engine_id"),
        (inputs.get("trade_decision") or {}).get("decision_id"),
    )

    reason_codes = list(
        dict.fromkeys(
            extracted["reason_codes"]
            + conflicts["reason_codes"]
            + (["MISSING_PERSPECTIVE"] if any(code in {"MISSING_SMC_PERSPECTIVE", "MISSING_MM_PERSPECTIVE", "MISSING_CORE_PERSPECTIVE"} for code in extracted["reason_codes"] + conflicts["reason_codes"]) else [])
        )
    )

    payload = {
        "timestamp_utc": timestamp_utc,
        "block_id": PERSPECTIVE_MERGER_BLOCK_ID,
        "symbol": symbol,
        "perspective_merger_id": merger_id,
        "lineage_id": lineage_id,
        "core_bias": extracted["core_bias"],
        "smc_bias": extracted["smc_bias"],
        "mm_bias": extracted["mm_bias"],
        "core_confidence": extracted["core_confidence"],
        "smc_confidence": extracted["smc_confidence"],
        "mm_confidence": extracted["mm_confidence"],
        "alignment_status": alignment["alignment_status"],
        "alignment_score": alignment["alignment_score"],
        "perspective_agreement": alignment["perspective_agreement"],
        "bias_conflicts": conflicts["bias_conflicts"],
        "conflict_sources": conflicts["conflict_sources"],
        "confidence_adjustment": conflicts["confidence_adjustment"],
        "core_summary": extracted["core_summary"],
        "smc_summary": extracted["smc_summary"],
        "mm_summary": extracted["mm_summary"],
        "merged_context": {
            "core_bias": extracted["core_bias"],
            "smart_money_bias": extracted["smc_bias"],
            "market_maker_bias": extracted["mm_bias"],
            "alignment_status": alignment["alignment_status"],
            "alignment_score": alignment["alignment_score"],
        },
        "decision_gate_context_note": conflicts["decision_gate_context_note"],
        "nova_brain_context_note": conflicts["nova_brain_context_note"],
        "data_quality": _data_quality(inputs),
        "reason_codes": reason_codes,
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "warnings": [],
    }

    validation = validate_perspective_merger(payload)
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
                "last_perspective_merger_id": merger_id,
                "last_lineage_id": lineage_id,
                "core_bias": extracted["core_bias"],
                "smc_bias": extracted["smc_bias"],
                "mm_bias": extracted["mm_bias"],
                "alignment_status": alignment["alignment_status"],
                "alignment_score": alignment["alignment_score"],
                "validation_passed": validation["is_valid"],
                "validation_errors": validation["errors"],
                "files_used": files_used,
                "missing_sources": missing,
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
