from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.model_survival_registry import load_model_survival_registry, split_active_quarantined, update_model_survival_report
from src.simple.lineage_event_logger import append_event, lineage_record, stable_id
from src.simple.research_epoch import ACTIVE_EPOCH_ID, append_epoch_jsonl, epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, source_state_refs_from_paths, stamp_payload, write_json

BLOCK_ID = "SIGNAL_EVENT_CONSOLIDATOR"
STATE_DIR = Path("state/simple")
OUTPUT_PATH = epoch_state_path("latest_signal_event.json")
HISTORY_PATH = epoch_data_path("signal_event_history.jsonl")
FACTORY_PATH = epoch_state_path("latest_paper_trade_factory.json")
GRADE_PATH = epoch_state_path("latest_signal_grade.json")
SETUP_PATH = STATE_DIR / "latest_setup_family_activation.json"
SETUP_CANDIDATE_PATH = STATE_DIR / "latest_setup_candidate.json"
SCENARIO_PATH = STATE_DIR / "latest_scenario_trigger.json"
TIMEFRAME_PATH = epoch_state_path("latest_timeframe_resolution.json")


def _bucket_5m(value: Any | None = None) -> str:
    if value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    minute = (dt.minute // 5) * 5
    return dt.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _basis_price(value: Any, tolerance_pct: float) -> str:
    number = safe_float(value)
    if number is None or number == 0:
        return "NA"
    bucket = number * (tolerance_pct / 100.0)
    return str(round(number / bucket)) if bucket else str(round(number, 8))


def event_identity_basis(trade: dict[str, Any], bucket_5m: str | None = None) -> str:
    bucket = bucket_5m or _bucket_5m(trade.get("opened_at_utc") or trade.get("timestamp_utc"))
    return "|".join(
        [
            str(trade.get("symbol") or "BTCUSDT"),
            str(trade.get("direction") or "UNKNOWN").upper(),
            _basis_price(trade.get("entry"), 0.03),
            _basis_price(trade.get("stop_loss"), 0.03),
            _basis_price(trade.get("tp1"), 0.05),
            bucket,
        ]
    )


def derive_event_id(trade: dict[str, Any], bucket_5m: str | None = None) -> str:
    basis = event_identity_basis(trade, bucket_5m)
    return "EVT_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20].upper()


def enrich_trade_event_fields(trade: dict[str, Any], grade: dict[str, Any] | None = None) -> dict[str, Any]:
    enriched = dict(trade)
    bucket = _bucket_5m(enriched.get("opened_at_utc") or enriched.get("timestamp_utc"))
    enriched["event_bucket_5m"] = bucket
    enriched["event_id"] = enriched.get("event_id") or derive_event_id(enriched, bucket)
    if grade:
        enriched["signal_grade"] = grade.get("signal_grade", enriched.get("signal_grade"))
        enriched["grade_score"] = grade.get("grade_score", enriched.get("grade_score"))
        enriched["grade_reasons"] = grade.get("grade_reasons", enriched.get("grade_reasons"))
        enriched["grade_blockers"] = grade.get("grade_blockers", enriched.get("grade_blockers"))
        enriched["a_plus_ready"] = grade.get("a_plus_ready", enriched.get("a_plus_ready", False))
    enriched["event_confluence_count"] = int(enriched.get("event_confluence_count") or len(enriched.get("source_models") or []) or 1)
    return enriched


def _grade_by_trade_id(grade_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in grade_payload.get("graded_signals") or []:
        trade_id = str(item.get("paper_trade_id") or "")
        if trade_id:
            out[trade_id] = item
    return out


def _merge_event(items: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(items, key=lambda item: ((safe_float(item.get("grade_score")) or 0.0), (safe_float(item.get("activation_score")) or 0.0)), reverse=True)
    primary = ranked[0]
    supporting_models = sorted({str(item.get("model_id")) for item in ranked[1:] if item.get("model_id")})
    supporting_setups = sorted({str(item.get("setup_family")) for item in ranked[1:] if item.get("setup_family") and item.get("setup_family") != primary.get("setup_family")})
    supporting_tfs = sorted({str(item.get("primary_tf")) for item in ranked[1:] if item.get("primary_tf") and item.get("primary_tf") != primary.get("primary_tf")})
    confluence_count = max(len(ranked), int(primary.get("event_confluence_count") or 1))
    return {
        "event_id": primary.get("event_id"),
        "event_bucket_5m": primary.get("event_bucket_5m"),
        "event_confluence_count": confluence_count,
        "symbol": primary.get("symbol"),
        "direction": primary.get("direction"),
        "primary_model": primary.get("model_id"),
        "primary_setup": primary.get("setup_family"),
        "primary_tf": primary.get("primary_tf"),
        "context_tf": primary.get("context_tf"),
        "trigger_tf": primary.get("trigger_tf"),
        "entry": primary.get("entry"),
        "stop_loss": primary.get("stop_loss"),
        "tp1": primary.get("tp1"),
        "tp2": primary.get("tp2"),
        "rr1": primary.get("rr1"),
        "rr2": primary.get("rr2"),
        "expected_hold_label": primary.get("expected_hold_label"),
        "expected_hold_max_minutes": primary.get("expected_hold_max_minutes"),
        "plan_style": primary.get("plan_style"),
        "signal_grade": primary.get("signal_grade") or "D",
        "grade_score": primary.get("grade_score") or 0.0,
        "a_plus_ready": bool(primary.get("a_plus_ready")),
        "grade_reasons": list(primary.get("grade_reasons") or []),
        "grade_blockers": list(primary.get("grade_blockers") or []),
        "activation_score": primary.get("activation_score"),
        "supporting_models": supporting_models,
        "supporting_setups": supporting_setups,
        "supporting_timeframes": supporting_tfs,
        "source_trade_ids": [item.get("paper_trade_id") for item in ranked if item.get("paper_trade_id")],
        "source_state_refs": source_state_refs_from_paths({"paper_trade_factory": FACTORY_PATH, "signal_grade": GRADE_PATH, "setup_activation": SETUP_PATH, "timeframe_resolution": TIMEFRAME_PATH}),
        "execution_safety": {"live_order_sent": False, "private_api_used": False},
        "setup_id": primary.get("setup_id"),
        "active_scenario_id": primary.get("active_scenario_id"),
        "trigger_type": primary.get("trigger_type", "EVENT_CONSOLIDATED"),
        "trigger_state": primary.get("trigger_state", "TRIGGERED"),
        "trigger_price": primary.get("entry"),
        "confidence": safe_float(primary.get("grade_score")) or 0.0,
        "blockers": list(primary.get("grade_blockers") or []),
        "signal_id": primary.get("signal_id") or stable_id("SIG", primary.get("event_id"), primary.get("symbol"), primary.get("direction")),
    }


def run_signal_event_consolidator() -> dict[str, Any]:
    context = current_runtime_context()
    factory = load_json(FACTORY_PATH) or {}
    setup_candidate = load_json(SETUP_CANDIDATE_PATH) or {}
    scenario_payload = load_json(SCENARIO_PATH) or {}
    grade_payload = load_json(GRADE_PATH) or {}
    grade_map = _grade_by_trade_id(grade_payload)
    registry = load_model_survival_registry()
    raw_factory_trades = list(factory.get("newest_opened_this_loop") or factory.get("top_candidate_diagnostics") or [])
    filtered_factory_trades, blocked_trades = split_active_quarantined(raw_factory_trades, BLOCK_ID)
    survival_report = update_model_survival_report(location=BLOCK_ID, allowed_count=len(filtered_factory_trades), blocked_items=blocked_trades, registry=registry)
    trades = []
    for trade in filtered_factory_trades:
        trades.append(enrich_trade_event_fields(dict(trade), grade_map.get(str(trade.get("paper_trade_id") or ""))))
    grouped: dict[str, list[dict[str, Any]]] = {}
    bucket_directions: dict[str, set[str]] = {}
    for trade in trades:
        grouped.setdefault(str(trade.get("event_id")), []).append(trade)
        bucket_key = "|".join([str(trade.get("symbol") or "UNKNOWN"), str(trade.get("event_bucket_5m") or "UNKNOWN_BUCKET")])
        direction = str(trade.get("direction") or "UNKNOWN").upper()
        if direction in {"LONG", "SHORT"}:
            bucket_directions.setdefault(bucket_key, set()).add(direction)
    events = [_merge_event(items) for items in grouped.values() if items]
    if not events:
        setup_id = str(setup_candidate.get("setup_id") or (setup_candidate.get("identity") or {}).get("setup_id") or "")
        scenario_obj = scenario_payload.get("active_scenario") or {}
        active_scenario_id = str(scenario_obj.get("scenario_id") or "")
        if setup_id and active_scenario_id:
            direction = str((setup_candidate.get("setup_candidate") or {}).get("setup_direction", "UNKNOWN")).upper()
            event_id = stable_id("EVT", setup_id, active_scenario_id, context.get("loop_id"))
            synthetic = {
                "event_id": event_id,
                "event_bucket_5m": _bucket_5m(),
                "event_confluence_count": 1,
                "symbol": str(setup_candidate.get("symbol") or context.get("symbol") or "BTCUSDT"),
                "direction": direction,
                "primary_model": "NO_MODEL",
                "primary_setup": (setup_candidate.get("setup_candidate") or {}).get("setup_family"),
                "entry": None,
                "stop_loss": None,
                "tp1": None,
                "tp2": None,
                "rr1": None,
                "rr2": None,
                "signal_grade": "WATCH",
                "grade_score": 0.0,
                "a_plus_ready": False,
                "grade_reasons": ["SCENARIO_SETUP_SYNTHETIC_SIGNAL"],
                "grade_blockers": [],
                "activation_score": 0.0,
                "supporting_models": [],
                "supporting_setups": [],
                "supporting_timeframes": [],
                "source_trade_ids": [],
                "source_state_refs": source_state_refs_from_paths({"setup_candidate": SETUP_CANDIDATE_PATH, "active_scenario": SCENARIO_PATH}),
                "execution_safety": {"live_order_sent": False, "private_api_used": False},
                "setup_id": setup_id,
                "active_scenario_id": active_scenario_id,
                "trigger_type": "SCENARIO_CONFIRMATION",
                "trigger_state": "TRIGGERED",
                "trigger_price": None,
                "confidence": 0.0,
                "blockers": [],
                "signal_id": stable_id("SIG", setup_id, active_scenario_id),
            }
            events = [synthetic]
    events.sort(key=lambda item: (safe_float(item.get("grade_score")) or 0.0, int(item.get("event_confluence_count") or 0)), reverse=True)
    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "source": {"source_mode": "EPOCH_V2_PAPER_CANDIDATE_CONSOLIDATION"},
            "latest_event": events[0] if events else {},
            "events": events[:50],
            "summary": {
                "source_trade_count": len(trades),
                "model_survival_blocked_count": len(blocked_trades),
                "event_count": len(events),
                "duplicate_event_count": max(0, len(trades) - len(events)),
                "opposite_direction_bucket_count": sum(1 for values in bucket_directions.values() if len(values) > 1),
                "a_plus_event_count": sum(1 for item in events if item.get("a_plus_ready") and item.get("signal_grade") == "A_PLUS"),
            },
            "data_quality": {"level": "HIGH" if factory else "MEDIUM", "missing_inputs": [name for name, payload in {"paper_trade_factory": factory, "signal_grade": grade_payload}.items() if not payload]},
            "reason_codes": ["EVENT_LEVEL_SIGNAL_IDENTITY_ACTIVE", "ONE_TELEGRAM_SIGNAL_PER_EVENT", "OPPOSITE_BUCKET_AUDIT_ACTIVE", "PAPER_ONLY", "NO_LIVE_EXECUTION", "NO_PRIVATE_API"],
            "model_survival_registry": {"registry_status": survival_report.get("registry_status"), "blocked_count": len(blocked_trades)},
            "feeds_next": ["TELEGRAM_RESEARCH_REPORTER", "RESEARCH_PAPER_LIFECYCLE_ENGINE"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str(factory.get("symbol") or context.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, output)
    append_epoch_jsonl("signal_event_history.jsonl", output)
    for event in events[:50]:
        setup_id = str(event.get("setup_id") or "")
        signal_id = str(event.get("signal_id") or "")
        if not setup_id or not signal_id or not str(event.get("active_scenario_id") or ""):
            continue
        append_event(
            "signal_events_clean.jsonl",
            lineage_record(
                record_type="signal_event",
                event_id=signal_id,
                parent_id=setup_id,
                setup_id=setup_id,
                signal_id=signal_id,
                context_id=context.get("context_id"),
                loop_id=context.get("loop_id"),
                reason_codes=list(event.get("grade_reasons") or []),
                blocked_by=list(event.get("grade_blockers") or []),
                feeds_next=["trade_plan_events"],
                extra={"symbol": event.get("symbol"), "direction": event.get("direction")},
            ),
        )
    return output


def main() -> None:
    print(json.dumps(run_signal_event_consolidator(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
