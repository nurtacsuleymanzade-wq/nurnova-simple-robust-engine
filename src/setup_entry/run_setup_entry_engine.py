from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .entry_trigger_engine import build_entry_trigger
from .setup_candidate_engine import build_setup_candidate
from .setup_entry_registry import (
    DEFAULT_FEEDS_NEXT,
    SETUP_ENTRY_BLOCK_ID,
)
from .setup_entry_validator import validate_setup_entry

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/setup_entry"
REPORTS_DIR = ROOT / "reports/setup_entry"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_setup_entry.json"
ENGINE_STATE_PATH = STATE_DIR / "setup_entry_engine_state.json"
EVENTS_PATH = LIVE_DIR / "setup_entry_events.jsonl"
REPORT_PATH = REPORTS_DIR / "setup_entry_latest_report.md"

INPUT_JSON_PATHS = [
    "state/lineage/latest_lineage_audit.json",
    "state/lineage/lineage_graph_state.json",
    "state/market_state/latest_market_state.json",
    "state/active_scenario/latest_active_scenario.json",
    "state/flow_reaction/latest_flow_reaction.json",
    "state/latest_liquidity.json",
    "state/latest_structure.json",
    "state/latest_context.json",
    "state/latest_candle_dna.json",
    "state/latest_footprint.json",
    "state/latest_order_flow.json",
    "state/simple/latest_hybrid_candle_dna.json",
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

    return records, used, missing


def _make_id(ts: str, label: str, seed: dict[str, Any]) -> str:
    s = ts + label + _canon(seed)
    return label.upper()[:3] + "_" + hashlib.md5(s.encode()).hexdigest().upper()[:24]


def _assess_data_quality(records: dict[str, Any], missing: list[str]) -> str:
    critical = ["market_state", "active_scenario"]
    missing_critical = [k for k in critical if k not in records]
    if len(missing_critical) >= 2:
        return "INVALID"
    if len(missing) >= len(INPUT_JSON_PATHS) - 3:
        return "DEGRADED"
    if len(missing) > 5:
        return "ACCEPTABLE"
    return "OK"


def _compute_scores(
    setup_result: dict[str, Any],
    trigger_result: dict[str, Any],
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
) -> dict[str, float]:
    setup_conf = setup_result.get("setup_confidence", 0.0)
    setup_quality = setup_result.get("setup_quality", "INVALID")
    trigger_conf = trigger_result.get("entry_trigger_confidence", 0.0)
    trigger_quality = trigger_result.get("entry_trigger_quality", "INVALID")

    scenario_alignment = 0.0
    if active_scenario:
        scenario_alignment = float(active_scenario.get("scenario_confidence") or 0.0)

    market_alignment = 0.0
    if market_state:
        # Rough alignment score based on regime
        regime = str(market_state.get("market_regime") or "").upper()
        if regime in ("UPTREND", "DOWNTREND"):
            market_alignment = 0.8
        elif regime in ("RANGE", "EXPANSION", "COMPRESSION"):
            market_alignment = 0.6
        else:
            market_alignment = 0.2

    flow_alignment = 0.0
    if flow_reaction:
        flow_alignment = float(flow_reaction.get("reaction_confidence") or 0.0)

    setup_quality_score = {"A": 1.0, "B": 0.7, "C": 0.5, "INVALID": 0.0, "UNKNOWN": 0.0}.get(setup_quality, 0.0)
    trigger_quality_score = {"HIGH": 1.0, "MEDIUM": 0.65, "LOW": 0.35, "INVALID": 0.0, "UNKNOWN": 0.0}.get(
        trigger_quality, 0.0
    )

    return {
        "scenario_alignment_score": round(scenario_alignment, 4),
        "market_state_alignment_score": round(market_alignment, 4),
        "flow_reaction_alignment_score": round(flow_alignment, 4),
        "liquidity_alignment_score": 0.5,
        "structure_alignment_score": 0.5,
        "timeframe_alignment_score": 0.7,
        "setup_quality_score": round(setup_quality_score, 4),
        "trigger_quality_score": round(trigger_quality_score, 4),
        "conflict_penalty": 0.0,
        "data_quality_penalty": 0.0,
    }


def _build_report(payload: dict[str, Any]) -> str:
    ts = payload.get("timestamp_utc", "N/A")
    setup = payload.get("setup_candidate", "N/A")
    direction = payload.get("setup_direction", "N/A")
    quality = payload.get("setup_quality", "N/A")
    confidence = payload.get("setup_confidence", 0.0)
    trigger = payload.get("entry_trigger_status", "N/A")
    trigger_quality = payload.get("entry_trigger_quality", "N/A")
    trigger_conf = payload.get("entry_trigger_confidence", 0.0)

    evidence = payload.get("evidence", {})
    scores = payload.get("scores", {})
    warnings = payload.get("warnings", [])
    reason_codes = payload.get("reason_codes", [])
    feeds_next = payload.get("feeds_next", [])

    lines = [
        f"# Setup Entry Report — {ts}",
        "",
        "## Setup Entry Status",
        f"- Block ID: {payload.get('block_id')}",
        f"- Setup Candidate ID: {payload.get('setup_candidate_id')}",
        f"- Entry Trigger ID: {payload.get('entry_trigger_id')}",
        f"- Lineage ID: {payload.get('lineage_id')}",
        "",
        "## Setup Candidate",
        f"- **{setup}**",
        "",
        "## Setup Direction",
        f"- **{direction}**",
        "",
        "## Setup Quality",
        f"- **{quality}**",
        "",
        "## Setup Confidence",
        f"- **{confidence}**",
        f"- Reasons: {payload.get('setup_reason_codes', [])}",
        "",
        "## Entry Trigger Status",
        f"- **{trigger}**",
        "",
        "## Entry Trigger Quality",
        f"- **{trigger_quality}**",
        "",
        "## Entry Trigger Confidence",
        f"- **{trigger_conf}**",
        f"- Reasons: {payload.get('entry_trigger_reason_codes', [])}",
        "",
        "## Market State Link",
        f"- market_state_id: {payload.get('market_state_id')}",
        "",
        "## Active Scenario Link",
        f"- active_scenario_id: {payload.get('active_scenario_id')}",
        "",
        "## Flow Reaction Link",
        f"- flow_reaction_id: {payload.get('flow_reaction_id')}",
        "",
        "## Timeframe Context",
        f"```json\n{json.dumps(payload.get('timeframe_context', {}), indent=2)}\n```",
        "",
        "## Evidence Used",
        f"```json\n{json.dumps(evidence, indent=2)}\n```",
        "",
        "## Scores",
        f"```json\n{json.dumps(scores, indent=2)}\n```",
        "",
        "## Setup Reasons",
        "\n".join(f"- {r}" for r in payload.get("setup_reason_codes", [])) or "- None",
        "",
        "## Entry Trigger Reasons",
        "\n".join(f"- {r}" for r in payload.get("entry_trigger_reason_codes", [])) or "- None",
        "",
        "## Blocking Reasons",
        "\n".join(f"- {r}" for r in payload.get("blocking_reason_codes", [])) or "- None",
        "",
        "## Conflict Reasons",
        "\n".join(f"- {r}" for r in payload.get("conflict_reason_codes", [])) or "- None",
        "",
        "## Data Quality",
        f"- **{payload.get('data_quality')}**",
        "",
        "## Warnings",
        "\n".join(f"- {w}" for w in warnings) if warnings else "- None",
        "",
        "## Feeds Next",
        "\n".join(f"- {f}" for f in feeds_next),
        "",
        "## Next Action",
        "- Pass setup_entry output to PHASE 6 Trade Plan Decision Gate",
        "- Pass to PHASE 8 Conditional Edge Matrix",
        "- Pass to PHASE 10 NOVA Brain Snapshot",
    ]
    return "\n".join(lines)


def run() -> dict[str, Any]:
    ts = _utc_now()
    records, used_files, missing_files = _collect_records()

    market_state = records.get("market_state")
    active_scenario = records.get("active_scenario")
    flow_reaction = records.get("flow_reaction")
    liquidity = records.get("liquidity") or records.get("liquidity_structure")
    structure = records.get("structure") or records.get("liquidity_structure")
    candle = records.get("hybrid_candle_dna") or records.get("candle_dna")

    market_state_id = (market_state or {}).get("market_state_id", "")
    active_scenario_id = (active_scenario or {}).get("active_scenario_id", "")
    flow_reaction_id = (flow_reaction or {}).get("flow_reaction_id", "")
    lineage_id = (
        (flow_reaction or {}).get("lineage_id")
        or (active_scenario or {}).get("lineage_id")
        or (market_state or {}).get("lineage_id")
        or ("LINCTX_" + hashlib.md5(ts.encode()).hexdigest().upper()[:24])
    )
    parent_lineage_ids = list({
        lid
        for src in [market_state, active_scenario, flow_reaction]
        if src
        for lid in ([src.get("lineage_id")] if src.get("lineage_id") else [])
    })

    data_quality = _assess_data_quality(records, missing_files)

    warnings: list[str] = []
    reason_codes: list[str] = []

    if not market_state_id:
        reason_codes.append("MARKET_STATE_MISSING")
        warnings.append("market_state not available")
    if not active_scenario_id:
        reason_codes.append("ACTIVE_SCENARIO_MISSING")
        warnings.append("active_scenario not available")
    if not flow_reaction_id:
        reason_codes.append("FLOW_REACTION_MISSING")
        warnings.append("flow_reaction not available")

    setup_result = build_setup_candidate(
        market_state=market_state,
        active_scenario=active_scenario,
        flow_reaction=flow_reaction,
        liquidity=liquidity,
        structure=structure,
        candle=candle,
        data_quality=data_quality,
    )

    trigger_result = build_entry_trigger(
        setup_result=setup_result,
        active_scenario=active_scenario,
        flow_reaction=flow_reaction,
        market_state=market_state,
        data_quality=data_quality,
    )

    setup_candidate = setup_result.get("setup_candidate", "UNKNOWN")
    setup_direction = setup_result.get("setup_direction", "UNKNOWN")
    setup_quality = setup_result.get("setup_quality", "INVALID")
    setup_confidence = setup_result.get("setup_confidence", 0.0)

    entry_trigger_status = trigger_result.get("entry_trigger_status", "TRIGGER_UNKNOWN")
    entry_trigger_quality = trigger_result.get("entry_trigger_quality", "INVALID")
    entry_trigger_confidence = trigger_result.get("entry_trigger_confidence", 0.0)

    scores = _compute_scores(setup_result, trigger_result, market_state, active_scenario, flow_reaction)

    setup_candidate_id = _make_id(ts, "SCE", {"setup": setup_candidate, "lineage": lineage_id})
    entry_trigger_id = _make_id(ts, "ETG", {"trigger": entry_trigger_status, "lineage": lineage_id})

    all_reason_codes = list(reason_codes)
    all_reason_codes.extend(setup_result.get("setup_reason_codes", []))
    all_reason_codes.extend(trigger_result.get("entry_trigger_reason_codes", []))
    if not all_reason_codes:
        all_reason_codes.append("SETUP_ENTRY_COMPUTED")

    timeframe_context = {
        "primary_tf": "1m",
        "supporting_tfs": ["5m", "15m"],
        "blocking_tfs": [],
        "timeframe_alignment_score": 0.7,
    }

    payload: dict[str, Any] = {
        "timestamp_utc": ts,
        "block_id": SETUP_ENTRY_BLOCK_ID,
        "symbol": "BTCUSDT",
        "setup_candidate_id": setup_candidate_id,
        "entry_trigger_id": entry_trigger_id,
        "lineage_id": lineage_id,
        "parent_lineage_ids": parent_lineage_ids,
        "market_state_id": market_state_id,
        "active_scenario_id": active_scenario_id,
        "flow_reaction_id": flow_reaction_id,
        "setup_candidate": setup_candidate,
        "setup_direction": setup_direction,
        "setup_quality": setup_quality,
        "setup_confidence": setup_confidence,
        "entry_trigger_status": entry_trigger_status,
        "entry_trigger_quality": entry_trigger_quality,
        "entry_trigger_confidence": entry_trigger_confidence,
        "timeframe_context": timeframe_context,
        "evidence": setup_result.get("evidence_dict", {}),
        "scores": scores,
        "setup_reason_codes": setup_result.get("setup_reason_codes", []),
        "entry_trigger_reason_codes": trigger_result.get("entry_trigger_reason_codes", []),
        "blocking_reason_codes": trigger_result.get("blocking_reason_codes", []),
        "conflict_reason_codes": list(
            set(
                setup_result.get("conflict_reason_codes", []) + trigger_result.get("conflict_reason_codes", [])
            )
        ),
        "missing_evidence": setup_result.get("missing_evidence", []),
        "data_quality": data_quality,
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "reason_codes": all_reason_codes,
        "warnings": warnings,
    }

    validation = validate_setup_entry(payload)
    if not validation["is_valid"]:
        warnings.extend(validation["errors"])
        payload["warnings"] = warnings

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    LATEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    engine_state = {
        "timestamp_utc": ts,
        "last_setup_candidate_id": setup_candidate_id,
        "last_setup_candidate": setup_candidate,
        "last_entry_trigger_id": entry_trigger_id,
        "last_entry_trigger_status": entry_trigger_status,
        "last_setup_confidence": setup_confidence,
        "last_entry_trigger_confidence": entry_trigger_confidence,
        "last_data_quality": data_quality,
        "validation_passed": validation["is_valid"],
        "validation_errors": validation["errors"],
        "files_used": used_files,
        "files_missing": missing_files,
    }
    ENGINE_STATE_PATH.write_text(json.dumps(engine_state, indent=2, ensure_ascii=False), encoding="utf-8")

    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    REPORT_PATH.write_text(_build_report(payload), encoding="utf-8")

    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
