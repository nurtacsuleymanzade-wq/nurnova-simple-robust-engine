from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

from .outcome_truth_engine import evaluate_outcome_truth
from .paper_lifecycle_engine import build_paper_lifecycle
from .paper_outcome_registry import (
    DEFAULT_FEEDS_NEXT,
    PAPER_OUTCOME_BLOCK_ID,
    build_lineage_id,
    build_outcome_id,
    utc_now,
)
from .paper_outcome_validator import validate_paper_outcome

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state/paper_outcome"
REPORTS_DIR = ROOT / "reports/paper_outcome"
LIVE_DIR = ROOT / "data/live"

LATEST_PATH = STATE_DIR / "latest_paper_outcome.json"
ENGINE_STATE_PATH = STATE_DIR / "paper_outcome_engine_state.json"
EVENTS_PATH = LIVE_DIR / "paper_outcome_events.jsonl"
REPORT_PATH = REPORTS_DIR / "paper_outcome_latest_report.md"

TRADE_DECISION_PATH = ROOT / "state/trade_decision/latest_trade_decision.json"
SETUP_ENTRY_PATH = ROOT / "state/setup_entry/latest_setup_entry.json"
ACTIVE_SCENARIO_PATH = ROOT / "state/active_scenario/latest_active_scenario.json"
MARKET_STATE_PATH = ROOT / "state/market_state/latest_market_state.json"
FLOW_REACTION_PATH = ROOT / "state/flow_reaction/latest_flow_reaction.json"
NON_ACTIONABLE_DECISION_STATUSES = {"NO_TRADE", "BLOCK", "WAIT"}
MAX_JSONL_FILES_PER_BASE = 12
MAX_TOTAL_PRICE_RECORDS = 1200


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path, max_lines: int = 250) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        tail: deque[str] = deque(maxlen=max_lines)
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                tail.append(line)
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for line in tail:
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


def _collect_price_path_records(symbol: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    files_used: list[str] = []

    for base, pattern in (
        (ROOT / "data/live", "*.jsonl"),
        (ROOT / "data/simple", "*.jsonl"),
    ):
        if not base.exists():
            continue
        paths = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[:MAX_JSONL_FILES_PER_BASE]:
            items = _read_jsonl(path)
            if not items:
                continue
            files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
            for item in items:
                if item.get("symbol") not in (None, "", symbol):
                    continue
                item = dict(item)
                item["source_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
                records.append(item)
                if len(records) >= MAX_TOTAL_PRICE_RECORDS:
                    return records, files_used

    state_simple = ROOT / "state/simple"
    if state_simple.exists():
        for path in sorted(state_simple.glob("*.json")):
            payload = _read_json(path)
            if payload is None:
                continue
            if payload.get("symbol") not in (None, "", symbol):
                continue
            files_used.append(str(path.relative_to(ROOT)).replace("\\", "/"))
            payload = dict(payload)
            payload["source_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            records.append(payload)

    return records, files_used


def _assess_data_quality(
    trade_decision: dict[str, Any] | None,
    price_path_records: list[dict[str, Any]],
    missing_sources: list[str],
) -> str:
    if trade_decision is None:
        return "INVALID"
    if not price_path_records:
        return "DEGRADED"
    if missing_sources:
        return "ACCEPTABLE"
    return "OK"


def _finalize_lineage(payload: dict[str, Any], trade_decision: dict[str, Any] | None) -> tuple[str, list[str]]:
    decision_lineage_id = str((trade_decision or {}).get("lineage_id") or "")
    if payload.get("_allow_paper") is True:
        paper_trade_lineage_id = build_lineage_id(
            "paper_trade",
            payload.get("symbol"),
            payload.get("paper_trade_id"),
            payload.get("trade_plan_id"),
            payload.get("decision_id"),
            decision_lineage_id,
        )
        outcome_lineage_id = build_lineage_id(
            "outcome",
            payload.get("symbol"),
            payload.get("paper_trade_id"),
            payload.get("outcome_id"),
            payload.get("trade_fate"),
            payload.get("closed_at") or payload.get("opened_at") or "",
        )
        return outcome_lineage_id, [paper_trade_lineage_id]

    context_lineage_id = build_lineage_id(
        "outcome_context",
        payload.get("symbol"),
        payload.get("paper_trade_id"),
        payload.get("decision_id"),
        decision_lineage_id,
        payload.get("trade_fate"),
    )
    return context_lineage_id, []


def _build_report(payload: dict[str, Any]) -> str:
    reason_lines = [f"- {code}" for code in payload.get("reason_codes", [])] or ["- NONE"]
    warning_lines = [f"- {warning}" for warning in payload.get("warnings", [])] or ["- NONE"]
    feed_lines = [f"- {item}" for item in payload.get("feeds_next", [])] or ["- NONE"]

    lines = [
        f"# Paper Outcome Report - {payload.get('timestamp_utc')}",
        "",
        "## Paper Outcome Status",
        f"- Block ID: {payload.get('block_id')}",
        f"- Paper Trade ID: {payload.get('paper_trade_id')}",
        f"- Outcome ID: {payload.get('outcome_id')}",
        f"- Lineage ID: {payload.get('lineage_id')}",
        "",
        "## Lifecycle State",
        f"- {payload.get('lifecycle_state')}",
        "",
        "## Trade Fate",
        f"- {payload.get('trade_fate')}",
        "",
        "## Edge Eligible",
        f"- {payload.get('edge_eligible')}",
        "",
        "## Entry / SL / TP Touch Status",
        f"- Entry Touched: {payload.get('entry_touched')}",
        f"- TP1 Touched: {payload.get('tp1_touched')}",
        f"- TP2 Touched: {payload.get('tp2_touched')}",
        f"- SL Touched: {payload.get('sl_touched')}",
        f"- Invalidation Touched: {payload.get('invalidation_touched')}",
        "",
        "## R Multiple",
        f"- {payload.get('r_multiple')}",
        "",
        "## Close Reason",
        f"- {payload.get('close_reason')}",
        "",
        "## Trade Decision Link",
        f"- trade_plan_id: {payload.get('trade_plan_id')}",
        f"- decision_id: {payload.get('decision_id')}",
        "",
        "## Setup Entry Link",
        f"- setup_candidate_id: {payload.get('setup_candidate_id')}",
        f"- entry_trigger_id: {payload.get('entry_trigger_id')}",
        "",
        "## Evidence Used",
        f"```json\n{json.dumps(payload.get('evidence', {}), indent=2)}\n```",
        "",
        "## Data Quality",
        f"- {payload.get('data_quality')}",
        "",
        "## Reason Codes",
        *reason_lines,
        "",
        "## Warnings",
        *warning_lines,
        "",
        "## Feeds Next",
        *feed_lines,
        "",
        "## Next Action",
    ]

    if payload.get("edge_eligible"):
        lines.append("- Feed this closed outcome to PHASE 8 and PHASE 10.")
    elif payload.get("trade_fate") == "DIAGNOSTIC_TIMEOUT":
        lines.append("- Keep TIMEOUT as diagnostic only; do not treat as edge sample.")
    elif payload.get("trade_fate") in ("NO_ENTRY_TOUCH", "EXPIRED_NO_ENTRY"):
        lines.append("- Keep waiting or expire cleanly; no edge sample should be emitted.")
    else:
        lines.append("- Review trade decision and price path evidence before downstream use.")
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    timestamp_utc = utc_now()

    trade_decision = _read_json(TRADE_DECISION_PATH)
    decision_status = str((trade_decision or {}).get("decision_status") or "UNKNOWN").upper()
    setup_entry = _read_json(SETUP_ENTRY_PATH)
    active_scenario = _read_json(ACTIVE_SCENARIO_PATH)
    market_state = _read_json(MARKET_STATE_PATH)
    flow_reaction = _read_json(FLOW_REACTION_PATH)

    missing_sources = []
    for path in (
        TRADE_DECISION_PATH,
        SETUP_ENTRY_PATH,
        ACTIVE_SCENARIO_PATH,
        MARKET_STATE_PATH,
        FLOW_REACTION_PATH,
    ):
        if not path.exists():
            missing_sources.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    lifecycle = build_paper_lifecycle(trade_decision, timestamp_utc=timestamp_utc)
    lifecycle["evidence"]["trade_decision_evidence"] = {
        "trade_decision_id": (trade_decision or {}).get("decision_id"),
        "trade_plan_id": (trade_decision or {}).get("trade_plan_id"),
        "decision_status": (trade_decision or {}).get("decision_status"),
        "side": (trade_decision or {}).get("side"),
        "entry_price": (trade_decision or {}).get("entry_price"),
        "stop_loss": (trade_decision or {}).get("stop_loss"),
        "take_profit_1": (trade_decision or {}).get("take_profit_1"),
        "take_profit_2": (trade_decision or {}).get("take_profit_2"),
        "invalidation_level": (trade_decision or {}).get("invalidation_level"),
        "lineage_id": (trade_decision or {}).get("lineage_id"),
    }

    allow_paper = lifecycle.get("_allow_paper") is True and decision_status not in NON_ACTIONABLE_DECISION_STATUSES
    symbol = str((trade_decision or {}).get("symbol") or "BTCUSDT")
    price_path_records: list[dict[str, Any]] = []
    price_source_files: list[str] = []
    if allow_paper:
        price_path_records, price_source_files = _collect_price_path_records(symbol)

    payload = evaluate_outcome_truth(lifecycle, price_path_records, as_of_timestamp_utc=timestamp_utc)
    payload["timestamp_utc"] = timestamp_utc
    payload["block_id"] = PAPER_OUTCOME_BLOCK_ID
    payload["feeds_next"] = list(DEFAULT_FEEDS_NEXT)
    payload["data_quality"] = (
        "ACCEPTABLE"
        if not allow_paper
        else _assess_data_quality(trade_decision, price_path_records, missing_sources)
    )

    lineage_id, parent_lineage_ids = _finalize_lineage(payload, trade_decision)
    payload["lineage_id"] = lineage_id
    payload["parent_lineage_ids"] = parent_lineage_ids
    payload["outcome_id"] = payload.get("outcome_id") or build_outcome_id(
        paper_trade_id=payload.get("paper_trade_id"),
        trade_fate=payload.get("trade_fate"),
        closed_at=payload.get("closed_at"),
        evidence_seed=payload.get("evidence"),
    )

    payload["evidence"]["trade_decision_evidence"].update(
        {
            "setup_entry_id": (setup_entry or {}).get("setup_candidate_id"),
            "active_scenario_id": (active_scenario or {}).get("active_scenario_id"),
            "market_state_id": (market_state or {}).get("market_state_id"),
            "flow_reaction_id": (flow_reaction or {}).get("flow_reaction_id"),
        }
    )

    payload["reason_codes"] = list(dict.fromkeys(payload.get("reason_codes") or []))
    payload["warnings"] = list(dict.fromkeys(payload.get("warnings") or []))
    if not payload["reason_codes"]:
        payload["reason_codes"] = ["PAPER_OUTCOME_COMPUTED"]

    validation = validate_paper_outcome(payload)
    if not validation["is_valid"]:
        payload["warnings"] = list(dict.fromkeys((payload.get("warnings") or []) + validation["errors"]))

    public_payload = {k: v for k, v in payload.items() if not str(k).startswith("_")}

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    LATEST_PATH.write_text(json.dumps(public_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    engine_state = {
        "timestamp_utc": timestamp_utc,
        "last_paper_trade_id": public_payload.get("paper_trade_id"),
        "last_outcome_id": public_payload.get("outcome_id"),
        "last_lineage_id": public_payload.get("lineage_id"),
        "last_trade_fate": public_payload.get("trade_fate"),
        "last_lifecycle_state": public_payload.get("lifecycle_state"),
        "last_edge_eligible": public_payload.get("edge_eligible"),
        "last_data_quality": public_payload.get("data_quality"),
        "validation_passed": validation["is_valid"],
        "validation_errors": validation["errors"],
        "price_source_files": price_source_files,
        "missing_sources": missing_sources,
    }
    ENGINE_STATE_PATH.write_text(json.dumps(engine_state, indent=2, ensure_ascii=False), encoding="utf-8")

    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(public_payload, ensure_ascii=False) + "\n")

    REPORT_PATH.write_text(_build_report(public_payload), encoding="utf-8")
    return public_payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
