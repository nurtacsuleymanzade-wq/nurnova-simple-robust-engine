from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .decision_gate_engine import run_decision_gate
from .trade_decision_registry import (
    DEFAULT_FEEDS_NEXT,
    TRADE_DECISION_BLOCK_ID,
)
from .trade_decision_validator import validate_trade_decision
from .trade_plan_engine import build_trade_plan

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/trade_decision"
REPORTS_DIR = ROOT / "reports/trade_decision"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_trade_decision.json"
ENGINE_STATE_PATH = STATE_DIR / "trade_decision_engine_state.json"
EVENTS_PATH = LIVE_DIR / "trade_decision_events.jsonl"
REPORT_PATH = REPORTS_DIR / "trade_decision_latest_report.md"

INPUT_JSON_PATHS = [
    "state/lineage/latest_lineage_audit.json",
    "state/market_state/latest_market_state.json",
    "state/active_scenario/latest_active_scenario.json",
    "state/flow_reaction/latest_flow_reaction.json",
    "state/setup_entry/latest_setup_entry.json",
    "state/latest_liquidity.json",
    "state/latest_structure.json",
    "state/latest_candle_dna.json",
    "state/latest_footprint.json",
    "state/latest_order_flow.json",
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
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


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
    critical = ["market_state", "active_scenario", "setup_entry"]
    missing_critical = [k for k in critical if k not in records]
    if len(missing_critical) >= 2:
        return "INVALID"
    if len(missing) >= len(INPUT_JSON_PATHS) - 3:
        return "DEGRADED"
    if len(missing) > 5:
        return "ACCEPTABLE"
    return "OK"


def _build_evidence_sections(
    setup_entry: dict[str, Any] | None,
    market_state: dict[str, Any] | None,
    active_scenario: dict[str, Any] | None,
    flow_reaction: dict[str, Any] | None,
    liquidity: dict[str, Any] | None,
    structure: dict[str, Any] | None,
    candle: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "setup_entry_evidence": {
            "setup_candidate": (setup_entry or {}).get("setup_candidate"),
            "setup_direction": (setup_entry or {}).get("setup_direction"),
            "setup_quality": (setup_entry or {}).get("setup_quality"),
            "entry_trigger_status": (setup_entry or {}).get("entry_trigger_status"),
            "entry_trigger_quality": (setup_entry or {}).get("entry_trigger_quality"),
        },
        "market_state_evidence": {
            "market_regime": (market_state or {}).get("market_regime"),
            "trend_state": (market_state or {}).get("trend_state"),
            "volatility_state": (market_state or {}).get("volatility_state"),
            "flow_state": (market_state or {}).get("flow_state"),
        },
        "active_scenario_evidence": {
            "active_scenario": (active_scenario or {}).get("active_scenario"),
            "scenario_bias": (active_scenario or {}).get("scenario_bias"),
            "scenario_confidence": (active_scenario or {}).get("scenario_confidence"),
        },
        "flow_reaction_evidence": {
            "flow_confirmation": (flow_reaction or {}).get("flow_confirmation"),
            "post_liquidity_reaction": (flow_reaction or {}).get("post_liquidity_reaction"),
            "reaction_quality": (flow_reaction or {}).get("reaction_quality"),
        },
        "liquidity_evidence": {
            "current_price": (
                ((liquidity or {}).get("range_context") or {}).get("current_price")
            ),
            "nearest_liquidity_above": (
                (((liquidity or {}).get("liquidity_levels") or {}).get("nearest_liquidity_above") or {}).get("price")
            ),
            "nearest_liquidity_below": (
                (((liquidity or {}).get("liquidity_levels") or {}).get("nearest_liquidity_below") or {}).get("price")
            ),
        },
        "structure_evidence": {
            "structure_bias": (structure or {}).get("structure", {}).get("structure_bias") if structure else None,
            "nearest_support": (liquidity or {}).get("nearest_support"),
            "nearest_resistance": (liquidity or {}).get("nearest_resistance"),
        },
        "candle_dna_evidence": {
            "candle_direction": (
                ((candle or {}).get("shape") or {}).get("candle_direction")
            ),
            "micro_winner": (
                ((candle or {}).get("micro_evidence") or {}).get("micro_winner")
            ),
        },
    }


def _build_report(payload: dict[str, Any]) -> str:
    ts = payload.get("timestamp_utc", "N/A")
    lines = [
        f"# Trade Decision Report — {ts}",
        "",
        "## Trade Decision Status",
        f"- Block ID: {payload.get('block_id')}",
        f"- Trade Plan ID: {payload.get('trade_plan_id')}",
        f"- Decision ID: {payload.get('decision_id')}",
        f"- Lineage ID: {payload.get('lineage_id')}",
        "",
        "## Side",
        f"- **{payload.get('side')}**",
        "",
        "## Entry Model",
        f"- **{payload.get('entry_model')}**",
        "",
        "## Entry / SL / TP / RR",
        f"- Entry Price: {payload.get('entry_price')}",
        f"- Stop Loss: {payload.get('stop_loss')}",
        f"- Take Profit 1: {payload.get('take_profit_1')}",
        f"- Take Profit 2: {payload.get('take_profit_2')}",
        f"- RR to TP1: {payload.get('rr_to_tp1')}",
        f"- RR to TP2: {payload.get('rr_to_tp2')}",
        "",
        "## Invalidation",
        f"- Invalidation Level: {payload.get('invalidation_level')}",
        "",
        "## Risk Grade",
        f"- **{payload.get('risk_grade')}**",
        "",
        "## Decision Status",
        f"- **{payload.get('decision_status')}**",
        "",
        "## Decision Confidence",
        f"- **{payload.get('decision_confidence')}**",
        "",
        "## Plan Quality",
        f"- **{payload.get('plan_quality')}**",
        "",
        "## Setup Entry Link",
        f"- setup_candidate_id: {payload.get('setup_candidate_id')}",
        f"- entry_trigger_id: {payload.get('entry_trigger_id')}",
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
        "## Evidence Used",
        f"```json\n{json.dumps(payload.get('evidence', {}), indent=2)}\n```",
        "",
        "## Scores",
        f"```json\n{json.dumps(payload.get('scores', {}), indent=2)}\n```",
        "",
        "## Entry Reasons",
        "\n".join(f"- {r}" for r in payload.get("entry_reason_codes", [])) or "- None",
        "",
        "## SL Reasons",
        "\n".join(f"- {r}" for r in payload.get("sl_reason_codes", [])) or "- None",
        "",
        "## TP Reasons",
        "\n".join(f"- {r}" for r in payload.get("tp_reason_codes", [])) or "- None",
        "",
        "## Invalidation Reasons",
        "\n".join(f"- {r}" for r in payload.get("invalidation_reason_codes", [])) or "- None",
        "",
        "## Blocking Reasons",
        "\n".join(f"- {r}" for r in payload.get("blocking_reason_codes", [])) or "- None",
        "",
        "## Risk Reasons",
        "\n".join(f"- {r}" for r in payload.get("risk_reason_codes", [])) or "- None",
        "",
        "## Data Quality",
        f"- **{payload.get('data_quality')}**",
        "",
        "## Warnings",
        "\n".join(f"- {w}" for w in payload.get("warnings", [])) or "- None",
        "",
        "## Feeds Next",
        "\n".join(f"- {f}" for f in payload.get("feeds_next", [])),
        "",
        "## Next Action",
        "- If ALLOW_PAPER: pass to PHASE 7 Paper Lifecycle Outcome Truth",
        "- If WAIT: re-evaluate when entry trigger status changes to TRIGGER_READY",
        "- If BLOCK/NO_TRADE: do not open paper trade; pass context to PHASE 8 and PHASE 10",
    ]
    return "\n".join(lines)


def run() -> dict[str, Any]:
    ts = _utc_now()
    records, used_files, missing_files = _collect_records()

    setup_entry = records.get("setup_entry")
    market_state = records.get("market_state")
    active_scenario = records.get("active_scenario")
    flow_reaction = records.get("flow_reaction")
    liquidity = records.get("liquidity") or records.get("liquidity_structure")
    structure = records.get("structure") or records.get("liquidity_structure")
    candle = records.get("hybrid_candle_dna") or records.get("candle_dna")

    market_state_id = (market_state or {}).get("market_state_id", "")
    active_scenario_id = (active_scenario or {}).get("active_scenario_id", "")
    flow_reaction_id = (flow_reaction or {}).get("flow_reaction_id", "")
    setup_candidate_id = (setup_entry or {}).get("setup_candidate_id", "")
    entry_trigger_id = (setup_entry or {}).get("entry_trigger_id", "")

    lineage_id = (
        (setup_entry or {}).get("lineage_id")
        or (flow_reaction or {}).get("lineage_id")
        or (active_scenario or {}).get("lineage_id")
        or (market_state or {}).get("lineage_id")
        or ("LINCTX_" + hashlib.md5(ts.encode()).hexdigest().upper()[:24])
    )
    parent_lineage_ids = list({
        lid
        for src in [setup_entry, market_state, active_scenario, flow_reaction]
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
    if not setup_candidate_id:
        reason_codes.append("SETUP_ENTRY_MISSING")
        warnings.append("setup_entry not available — NO_TRADE will be produced")

    plan = build_trade_plan(
        setup_entry=setup_entry,
        market_state=market_state,
        active_scenario=active_scenario,
        flow_reaction=flow_reaction,
        liquidity_structure=liquidity,
        data_quality=data_quality,
    )

    gate = run_decision_gate(plan=plan, data_quality=data_quality)

    trade_plan_id = _make_id(ts, "TPN", {"side": plan["side"], "lineage": lineage_id})
    decision_id = _make_id(ts, "DEC", {"status": gate["decision_status"], "lineage": lineage_id})

    all_reason_codes = list(reason_codes)
    all_reason_codes.extend(plan.get("entry_reason_codes", []))
    all_reason_codes.extend(plan.get("sl_reason_codes", []))
    all_reason_codes.extend(plan.get("tp_reason_codes", []))
    all_reason_codes.extend(plan.get("blocking_reason_codes", []))
    all_reason_codes.extend(gate.get("blocking_reason_codes", []))
    if not all_reason_codes:
        all_reason_codes.append("TRADE_DECISION_COMPUTED")

    internal_evidence = plan.get("evidence", {})
    full_evidence = _build_evidence_sections(
        setup_entry=setup_entry,
        market_state=market_state,
        active_scenario=active_scenario,
        flow_reaction=flow_reaction,
        liquidity=liquidity,
        structure=structure,
        candle=candle,
    )
    full_evidence.update({k: v for k, v in internal_evidence.items() if k not in full_evidence})

    payload: dict[str, Any] = {
        "timestamp_utc": ts,
        "block_id": TRADE_DECISION_BLOCK_ID,
        "symbol": "BTCUSDT",
        "trade_plan_id": trade_plan_id,
        "decision_id": decision_id,
        "lineage_id": lineage_id,
        "parent_lineage_ids": parent_lineage_ids,
        "setup_candidate_id": setup_candidate_id or None,
        "entry_trigger_id": entry_trigger_id or None,
        "market_state_id": market_state_id or None,
        "active_scenario_id": active_scenario_id or None,
        "flow_reaction_id": flow_reaction_id or None,
        "side": plan["side"],
        "entry_model": plan["entry_model"],
        "entry_price": plan["entry_price"],
        "stop_loss": plan["stop_loss"],
        "take_profit_1": plan["take_profit_1"],
        "take_profit_2": plan["take_profit_2"],
        "invalidation_level": plan["invalidation_level"],
        "rr_to_tp1": plan["rr_to_tp1"],
        "rr_to_tp2": plan["rr_to_tp2"],
        "risk_grade": plan["risk_grade"],
        "decision_status": gate["decision_status"],
        "decision_confidence": gate["decision_confidence"],
        "plan_quality": plan["plan_quality"],
        "position_policy": {
            "paper_only": True,
            "real_trade_allowed": False,
            "max_risk_pct": None,
            "risk_notes": plan.get("risk_reason_codes", []),
        },
        "entry_reason_codes": plan.get("entry_reason_codes", []),
        "sl_reason_codes": plan.get("sl_reason_codes", []),
        "tp_reason_codes": plan.get("tp_reason_codes", []),
        "invalidation_reason_codes": plan.get("invalidation_reason_codes", []),
        "blocking_reason_codes": gate.get("blocking_reason_codes", []),
        "risk_reason_codes": plan.get("risk_reason_codes", []),
        "evidence": full_evidence,
        "scores": plan.get("scores", {}),
        "data_quality": data_quality,
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
        "reason_codes": list(dict.fromkeys(all_reason_codes)),
        "warnings": warnings,
    }

    validation = validate_trade_decision(payload)
    if not validation["is_valid"]:
        warnings.extend(validation["errors"])
        payload["warnings"] = warnings

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    LATEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    engine_state = {
        "timestamp_utc": ts,
        "last_trade_plan_id": trade_plan_id,
        "last_decision_id": decision_id,
        "last_side": plan["side"],
        "last_entry_model": plan["entry_model"],
        "last_decision_status": gate["decision_status"],
        "last_plan_quality": plan["plan_quality"],
        "last_risk_grade": plan["risk_grade"],
        "last_decision_confidence": gate["decision_confidence"],
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
