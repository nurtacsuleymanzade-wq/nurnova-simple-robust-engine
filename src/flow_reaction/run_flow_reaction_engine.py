from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .flow_confirmation_engine import build_flow_confirmation
from .flow_reaction_registry import (
    DEFAULT_FEEDS_NEXT,
    FLOW_REACTION_BLOCK_ID,
)
from .flow_reaction_validator import validate_flow_reaction
from .post_liquidity_reaction_engine import build_post_liquidity_reaction

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/flow_reaction"
REPORTS_DIR = ROOT / "reports/flow_reaction"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_flow_reaction.json"
ENGINE_STATE_PATH = STATE_DIR / "flow_reaction_engine_state.json"
EVENTS_PATH = LIVE_DIR / "flow_reaction_events.jsonl"
REPORT_PATH = REPORTS_DIR / "flow_reaction_latest_report.md"

INPUT_JSON_PATHS = [
    "state/lineage/latest_lineage_audit.json",
    "state/lineage/lineage_graph_state.json",
    "state/market_state/latest_market_state.json",
    "state/market_state/market_state_engine_state.json",
    "state/active_scenario/latest_active_scenario.json",
    "state/active_scenario/active_scenario_engine_state.json",
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
                step = min(4096, pos)
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

    # Also scan data/live and data/simple for last jsonl records
    for live_path in (ROOT / "data/live").glob("*.jsonl"):
        key = live_path.stem + "_live"
        last = _read_last_jsonl(live_path)
        if last:
            records[key] = last

    for simple_path in (ROOT / "data/simple").glob("*.jsonl"):
        key = simple_path.stem + "_simple"
        last = _read_last_jsonl(simple_path)
        if last:
            records[key] = last

    return records, used, missing


def _make_flow_reaction_id(ts: str, payload_seed: dict[str, Any]) -> str:
    seed = ts + _canon(payload_seed)
    return "FR_" + hashlib.md5(seed.encode()).hexdigest().upper()[:24]


def _assess_data_quality(records: dict[str, Any], missing: list[str]) -> str:
    critical = ["market_state", "active_scenario"]
    missing_critical = [k for k in critical if k not in records]
    if len(missing_critical) >= 2:
        return "DEGRADED"
    if len(missing) >= len(INPUT_JSON_PATHS) - 2:
        return "DEGRADED"
    if len(missing) > 5:
        return "ACCEPTABLE"
    return "OK"


def _compute_scores(
    fc_result: dict[str, Any],
    plr_result: dict[str, Any],
    active_scenario: dict[str, Any] | None,
) -> dict[str, float]:
    flow_alignment = 0.0
    reaction_strength = 0.0
    absorption_score = 0.0
    trap_score = 0.0
    breakout_quality = 0.0
    conflict_penalty = 0.0
    data_quality_penalty = 0.0

    fc = fc_result.get("flow_confirmation", "UNKNOWN")
    plr = plr_result.get("post_liquidity_reaction", "UNKNOWN")
    abs_state = plr_result.get("absorption_state", "NONE")
    trap_state = plr_result.get("trap_state", "NONE")

    if fc == "CONFIRMED_LONG":
        flow_alignment = 0.85
    elif fc == "CONFIRMED_SHORT":
        flow_alignment = 0.85
    elif fc == "NOT_CONFIRMED":
        flow_alignment = 0.3
    elif fc == "CONFLICTED":
        flow_alignment = 0.1
        conflict_penalty = 0.3

    if plr in ("CONTINUATION_AFTER_SWEEP", "REAL_BREAKOUT"):
        reaction_strength = 0.85
        breakout_quality = 0.8
    elif plr in ("REVERSAL_AFTER_SWEEP", "RECLAIM_AFTER_SWEEP"):
        reaction_strength = 0.75
    elif plr in ("REJECTION_AFTER_SWEEP", "FAILED_BREAKOUT"):
        reaction_strength = 0.6
    elif plr in ("BUYERS_TRAPPED", "SELLERS_TRAPPED"):
        reaction_strength = 0.7
        trap_score = 0.8
    elif plr == "ABSORPTION_DETECTED":
        reaction_strength = 0.5
        absorption_score = 0.75
    elif plr in ("NO_LIQUIDITY_EVENT", "INSUFFICIENT_EVIDENCE"):
        reaction_strength = 0.1
        data_quality_penalty = 0.2

    if abs_state in ("BUY_ABSORPTION", "SELL_ABSORPTION"):
        absorption_score = max(absorption_score, 0.6)
    elif abs_state == "BOTH":
        absorption_score = 0.5
        conflict_penalty = max(conflict_penalty, 0.1)

    if trap_state in ("BUYERS_TRAPPED", "SELLERS_TRAPPED"):
        trap_score = max(trap_score, 0.7)

    # Scenario alignment boost
    if active_scenario:
        sc = float(active_scenario.get("scenario_confidence") or 0.0)
        flow_alignment = min(1.0, flow_alignment + sc * 0.1)

    return {
        "flow_alignment_score": round(flow_alignment, 4),
        "reaction_strength_score": round(reaction_strength, 4),
        "absorption_score": round(absorption_score, 4),
        "trap_score": round(trap_score, 4),
        "breakout_quality_score": round(breakout_quality, 4),
        "conflict_penalty": round(conflict_penalty, 4),
        "data_quality_penalty": round(data_quality_penalty, 4),
    }


def _compute_confidence_and_quality(
    scores: dict[str, float],
    fc: str,
    plr: str,
    data_quality: str,
) -> tuple[float, str, str]:
    if data_quality == "INVALID":
        return 0.0, "INVALID", "INVALID"

    raw = (
        scores["flow_alignment_score"] * 0.35
        + scores["reaction_strength_score"] * 0.35
        + scores["absorption_score"] * 0.1
        + scores["trap_score"] * 0.1
        + scores["breakout_quality_score"] * 0.1
        - scores["conflict_penalty"]
        - scores["data_quality_penalty"]
    )
    confidence = max(0.0, min(1.0, raw))

    if fc == "UNKNOWN" or plr == "UNKNOWN":
        quality = "UNKNOWN"
    elif confidence >= 0.7:
        quality = "HIGH"
    elif confidence >= 0.45:
        quality = "MEDIUM"
    elif confidence >= 0.2:
        quality = "LOW"
    else:
        quality = "INVALID"

    # Reaction bias
    if fc == "CONFIRMED_LONG" and plr in ("CONTINUATION_AFTER_SWEEP", "REAL_BREAKOUT", "SELLERS_TRAPPED"):
        bias = "LONG"
    elif fc == "CONFIRMED_SHORT" and plr in ("CONTINUATION_AFTER_SWEEP", "REAL_BREAKOUT", "BUYERS_TRAPPED"):
        bias = "SHORT"
    elif plr in ("REVERSAL_AFTER_SWEEP", "RECLAIM_AFTER_SWEEP", "SELLERS_TRAPPED"):
        bias = "LONG"
    elif plr in ("REJECTION_AFTER_SWEEP", "BUYERS_TRAPPED"):
        bias = "SHORT"
    elif fc in ("NOT_CONFIRMED", "CONFLICTED"):
        bias = "NO_TRADE"
    else:
        bias = "NEUTRAL"

    return round(confidence, 4), quality, bias


def _build_report(payload: dict[str, Any]) -> str:
    ts = payload.get("timestamp_utc", "N/A")
    fc = payload.get("flow_confirmation", "N/A")
    plr = payload.get("post_liquidity_reaction", "N/A")
    abs_s = payload.get("absorption_state", "N/A")
    trap_s = payload.get("trap_state", "N/A")
    bias = payload.get("reaction_bias", "N/A")
    conf = payload.get("reaction_confidence", 0.0)
    quality = payload.get("reaction_quality", "N/A")
    ms_id = payload.get("market_state_id", "N/A")
    asc_id = payload.get("active_scenario_id", "N/A")
    dq = payload.get("data_quality", "N/A")
    scores = payload.get("scores", {})
    evidence = payload.get("evidence", {})
    warnings = payload.get("warnings", [])
    reason_codes = payload.get("reason_codes", [])
    feeds_next = payload.get("feeds_next", [])

    lines = [
        f"# Flow Reaction Report — {ts}",
        "",
        "## Flow Reaction Status",
        f"- Block ID: {payload.get('block_id')}",
        f"- Flow Reaction ID: {payload.get('flow_reaction_id')}",
        f"- Lineage ID: {payload.get('lineage_id')}",
        "",
        "## Flow Confirmation",
        f"- **{fc}**",
        f"- Confirmation codes: {payload.get('confirmation_reason_codes', [])}",
        f"- Rejection codes: {payload.get('rejection_reason_codes', [])}",
        "",
        "## Post-Liquidity Reaction",
        f"- **{plr}**",
        "",
        "## Absorption State",
        f"- **{abs_s}**",
        f"- Absorption codes: {payload.get('absorption_reason_codes', [])}",
        "",
        "## Trap State",
        f"- **{trap_s}**",
        f"- Trap codes: {payload.get('trap_reason_codes', [])}",
        "",
        "## Reaction Bias",
        f"- **{bias}**",
        "",
        "## Reaction Confidence",
        f"- **{conf}**",
        "",
        "## Reaction Quality",
        f"- **{quality}**",
        "",
        "## Market State Link",
        f"- market_state_id: {ms_id}",
        "",
        "## Active Scenario Link",
        f"- active_scenario_id: {asc_id}",
        "",
        "## Evidence Used",
        f"```json\n{json.dumps(evidence, indent=2)}\n```",
        "",
        "## Scores",
        f"```json\n{json.dumps(scores, indent=2)}\n```",
        "",
        "## Confirmation Reasons",
        f"{payload.get('confirmation_reason_codes', [])}",
        "",
        "## Rejection Reasons",
        f"{payload.get('rejection_reason_codes', [])}",
        "",
        "## Trap Reasons",
        f"{payload.get('trap_reason_codes', [])}",
        "",
        "## Absorption Reasons",
        f"{payload.get('absorption_reason_codes', [])}",
        "",
        "## Conflict Reasons",
        f"{payload.get('conflict_reason_codes', [])}",
        "",
        "## Data Quality",
        f"- **{dq}**",
        "",
        "## Warnings",
        "\n".join(f"- {w}" for w in warnings) if warnings else "- None",
        "",
        "## Feeds Next",
        "\n".join(f"- {f}" for f in feeds_next),
        "",
        "## Next Action",
        "- Pass flow_reaction output to PHASE 5 Setup Candidate Entry Trigger",
        "- Pass to PHASE 8 Conditional Edge Matrix",
        "- Pass to PHASE 10 NOVA Brain Snapshot",
    ]
    return "\n".join(lines)


def run() -> dict[str, Any]:
    ts = _utc_now()
    records, used_files, missing_files = _collect_records()

    active_scenario = records.get("active_scenario")
    market_state = records.get("market_state")
    candle = records.get("hybrid_candle_dna") or records.get("candle_dna") or records.get("latest_candle_dna")
    footprint = records.get("footprint")
    order_flow = records.get("order_flow")
    liquidity = records.get("liquidity") or records.get("liquidity_structure")
    structure = records.get("structure") or records.get("liquidity_structure")
    lineage_audit = records.get("lineage_audit")
    lineage_graph = records.get("lineage_graph_state")

    # Resolve IDs
    market_state_id = (market_state or {}).get("market_state_id", "")
    active_scenario_id = (active_scenario or {}).get("active_scenario_id", "")
    lineage_id = (
        (active_scenario or {}).get("lineage_id")
        or (market_state or {}).get("lineage_id")
        or (lineage_audit or {}).get("lineage_id")
        or ("LINCTX_" + hashlib.md5(ts.encode()).hexdigest().upper()[:24])
    )
    parent_lineage_ids = list({
        lid
        for src in [active_scenario, market_state]
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

    # Build flow confirmation
    fc_result = build_flow_confirmation(
        active_scenario=active_scenario,
        market_state=market_state,
        candle=candle,
        footprint=footprint,
        order_flow=order_flow,
        liquidity=liquidity,
        data_quality=data_quality,
    )

    # Build post-liquidity reaction
    plr_result = build_post_liquidity_reaction(
        liquidity=liquidity,
        candle=candle,
        order_flow=order_flow,
        footprint=footprint,
        structure=structure,
        active_scenario=active_scenario,
        market_state=market_state,
    )

    flow_confirmation = fc_result["flow_confirmation"]
    post_liquidity_reaction = plr_result["post_liquidity_reaction"]
    absorption_state = plr_result["absorption_state"]
    trap_state = plr_result["trap_state"]

    scores = _compute_scores(fc_result, plr_result, active_scenario)
    reaction_confidence, reaction_quality, reaction_bias = _compute_confidence_and_quality(
        scores, flow_confirmation, post_liquidity_reaction, data_quality
    )

    # Merge evidence
    evidence = {
        "liquidity_event": plr_result["evidence"].get("liquidity_event", {}),
        "candle_reaction": plr_result["evidence"].get("candle_reaction", {}),
        "delta_evidence": {"delta": plr_result["evidence"].get("delta", 0.0)},
        "cvd_evidence": fc_result.get("evidence_used", {}).get("cvd_trend", "UNKNOWN"),
        "footprint_evidence": {
            "fp_buy_dominant": plr_result["evidence"].get("fp_buy_dominant", False),
            "fp_sell_dominant": plr_result["evidence"].get("fp_sell_dominant", False),
        },
        "wick_evidence": {
            "wick_above": plr_result["evidence"].get("liquidity_event", {}).get("wick_above", False),
            "wick_below": plr_result["evidence"].get("liquidity_event", {}).get("wick_below", False),
        },
        "structure_response": {},
        "active_scenario_evidence": {
            "active_scenario": (active_scenario or {}).get("active_scenario", "UNKNOWN"),
            "scenario_bias": (active_scenario or {}).get("scenario_bias", "UNKNOWN"),
            "scenario_confidence": (active_scenario or {}).get("scenario_confidence", 0.0),
        },
        "market_state_evidence": {
            "market_regime": (market_state or {}).get("market_regime", "UNKNOWN"),
            "trend_state": (market_state or {}).get("trend_state", "UNKNOWN"),
            "flow_state": (market_state or {}).get("flow_state", "UNKNOWN"),
        },
    }

    # Aggregate reason codes
    all_reason_codes = list(reason_codes)
    all_reason_codes.extend(fc_result.get("confirmation_reason_codes", []))
    all_reason_codes.extend(plr_result.get("reaction_reason_codes", []))
    if not all_reason_codes:
        all_reason_codes.append("FLOW_REACTION_COMPUTED")

    flow_reaction_id = _make_flow_reaction_id(ts, {
        "fc": flow_confirmation,
        "plr": post_liquidity_reaction,
        "lineage_id": lineage_id,
    })

    payload: dict[str, Any] = {
        "timestamp_utc": ts,
        "block_id": FLOW_REACTION_BLOCK_ID,
        "symbol": "BTCUSDT",
        "flow_reaction_id": flow_reaction_id,
        "lineage_id": lineage_id,
        "parent_lineage_ids": parent_lineage_ids,
        "market_state_id": market_state_id,
        "active_scenario_id": active_scenario_id,
        "flow_confirmation": flow_confirmation,
        "post_liquidity_reaction": post_liquidity_reaction,
        "absorption_state": absorption_state,
        "trap_state": trap_state,
        "reaction_bias": reaction_bias,
        "reaction_confidence": reaction_confidence,
        "reaction_quality": reaction_quality,
        "evidence": evidence,
        "scores": scores,
        "confirmation_reason_codes": fc_result.get("confirmation_reason_codes", []),
        "rejection_reason_codes": fc_result.get("rejection_reason_codes", []),
        "trap_reason_codes": plr_result.get("trap_reason_codes", []),
        "absorption_reason_codes": plr_result.get("absorption_reason_codes", []),
        "conflict_reason_codes": fc_result.get("conflict_reason_codes", []),
        "data_quality": data_quality,
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "reason_codes": all_reason_codes,
        "warnings": warnings,
    }

    # Validate
    validation = validate_flow_reaction(payload)
    if not validation["is_valid"]:
        warnings.extend(validation["errors"])
        payload["warnings"] = warnings

    # Write outputs
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    LATEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    engine_state = {
        "timestamp_utc": ts,
        "last_flow_reaction_id": flow_reaction_id,
        "last_flow_confirmation": flow_confirmation,
        "last_post_liquidity_reaction": post_liquidity_reaction,
        "last_reaction_confidence": reaction_confidence,
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
