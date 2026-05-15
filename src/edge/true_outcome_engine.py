from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, source_state_refs_from_paths, stamp_payload

BLOCK_ID = "TRUE_OUTCOME_ENGINE"
MAX_TAIL_ROWS = 5000
DEFAULT_EXPIRY_MINUTES = 90

FACTORY_PATH = epoch_state_path("latest_paper_trade_factory.json")
LIFECYCLE_PATH = epoch_state_path("latest_research_paper_lifecycle.json")
EPOCH_MARKET_TRUTH_PATH = epoch_state_path("latest_market_truth.json")
MARKET_TRUTH_PATH = Path("state/simple/latest_market_truth.json")
HYBRID_DNA_PATH = Path("state/simple/latest_hybrid_candle_dna.json")
MTF_DNA_PATH = Path("state/simple/latest_mtf_candle_dna.json")
ZONE_CONTEXT_PATH = epoch_state_path("latest_zone_context.json")
TP_DNA_PATH = epoch_state_path("latest_tp_condition_dna.json")

LIFECYCLE_HISTORY_PATH = epoch_data_path("research_paper_lifecycle_history.jsonl")
MARKET_TRUTH_HISTORY_PATH = epoch_data_path("market_truth_history.jsonl")
HYBRID_DNA_HISTORY_PATH = epoch_data_path("hybrid_candle_dna_history.jsonl")

OUTPUT_PATH = epoch_state_path("latest_true_outcome.json")
HISTORY_PATH = epoch_data_path("true_outcome_history.jsonl")
DATASET_PATH = epoch_state_path("latest_true_edge_dataset.json")
DATASET_HISTORY_PATH = epoch_data_path("true_edge_dataset_history.jsonl")
REPORT_PATH = Path("reports/simple/epoch_v2/latest_true_outcome_report.md")

SOURCE_PATHS = {
    "paper_trade_factory": FACTORY_PATH,
    "research_paper_lifecycle": LIFECYCLE_PATH,
    "epoch_market_truth": EPOCH_MARKET_TRUTH_PATH,
    "market_truth": MARKET_TRUTH_PATH,
    "hybrid_candle_dna": HYBRID_DNA_PATH,
    "mtf_candle_dna": MTF_DNA_PATH,
    "zone_context": ZONE_CONTEXT_PATH,
    "tp_condition_dna": TP_DNA_PATH,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _fmt_ts(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else ""


def _trade_id(trade: dict[str, Any]) -> str:
    return str(trade.get("paper_trade_id") or trade.get("event_id") or "")


def _required_diagnostic(trade: dict[str, Any], missing: list[str], refs: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    return {
        "paper_trade_id": trade.get("paper_trade_id"),
        "event_id": trade.get("event_id"),
        "model_id": trade.get("model_id") or trade.get("primary_model"),
        "setup_family": trade.get("setup_family") or trade.get("primary_setup"),
        "direction": trade.get("direction"),
        "entry_price": safe_float(trade.get("entry") or trade.get("entry_price")),
        "stop_loss": safe_float(trade.get("stop_loss")),
        "tp1": safe_float(trade.get("tp1")),
        "tp2": safe_float(trade.get("tp2")),
        "entry_touched": False,
        "outcome_status": "UNKNOWN",
        "first_hit": "UNKNOWN",
        "realized_r": None,
        "mfe": None,
        "mae": None,
        "hold_seconds": None,
        "hold_minutes": None,
        "born_at_utc": str(trade.get("opened_at_utc") or trade.get("timestamp_utc") or ""),
        "closed_at_utc": "",
        "outcome_truth_confidence": "DIAGNOSTIC",
        "zone_context": trade.get("zone_context") or {},
        "condition_dna": trade.get("condition_dna") or {},
        "source_state_refs": refs,
        "reason_codes": ["TRUE_OUTCOME_REQUIRED_FIELDS_MISSING", *[f"MISSING_{field.upper()}" for field in missing]],
        "raw_trade": trade,
        "timestamp_utc": now,
        "block_id": BLOCK_ID,
    }


def _extract_candidates(factory: dict[str, Any], lifecycle: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for source in (
        factory.get("newest_opened_this_loop"),
        factory.get("top_candidate_diagnostics"),
        lifecycle.get("open_trades"),
        lifecycle.get("trades_closed_this_loop"),
        lifecycle.get("trades"),
        lifecycle.get("closed_trades"),
    ):
        for item in source or []:
            if not isinstance(item, dict):
                continue
            key = _trade_id(item)
            if not key:
                continue
            existing = candidates.get(key, {})
            existing.update({k: v for k, v in item.items() if v not in (None, "", [], {})})
            candidates[key] = existing
    return list(candidates.values())


def _is_candle_like(item: dict[str, Any]) -> bool:
    return safe_float(item.get("high")) is not None and safe_float(item.get("low")) is not None and safe_float(item.get("close")) is not None


def _walk_candles(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if _is_candle_like(item):
                ts = item.get("timestamp_utc") or item.get("close_time_utc") or item.get("open_time_utc") or item.get("timestamp")
                out.append(
                    {
                        "timestamp_utc": str(ts or ""),
                        "open": safe_float(item.get("open") or item.get("open_price") or item.get("close")),
                        "high": safe_float(item.get("high")),
                        "low": safe_float(item.get("low")),
                        "close": safe_float(item.get("close")),
                        "source": str(item.get("block_id") or item.get("source") or "UNKNOWN"),
                    }
                )
            for value in item.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return out


def _load_replay_candles() -> list[dict[str, Any]]:
    payloads = [
        load_json(EPOCH_MARKET_TRUTH_PATH) or {},
        load_json(MARKET_TRUTH_PATH) or {},
        load_json(HYBRID_DNA_PATH) or {},
        load_json(MTF_DNA_PATH) or {},
    ]
    for path in (MARKET_TRUTH_HISTORY_PATH, HYBRID_DNA_HISTORY_PATH):
        payloads.extend(read_jsonl_tail_objects(path, max_lines=MAX_TAIL_ROWS))
    candles: dict[tuple[str, float, float, float], dict[str, Any]] = {}
    for payload in payloads:
        for candle in _walk_candles(payload):
            ts = _parse_ts(candle.get("timestamp_utc"))
            if ts is None:
                continue
            key = (_fmt_ts(ts), float(candle["high"]), float(candle["low"]), float(candle["close"]))
            candle["timestamp_utc"] = _fmt_ts(ts)
            candles[key] = candle
    return sorted(candles.values(), key=lambda item: _parse_ts(item.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc))


def _expiry_minutes(trade: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    for field in ("expected_hold_minutes", "expected_hold_max_minutes"):
        value = safe_float(trade.get(field))
        if value is not None and value > 0:
            return int(value), reasons
    max_seconds = safe_float(trade.get("max_holding_seconds"))
    if max_seconds is not None and max_seconds > 0:
        return int(max_seconds / 60), reasons
    expires = _parse_ts(trade.get("expires_at_utc") or trade.get("expiration_utc"))
    born = _parse_ts(trade.get("opened_at_utc") or trade.get("timestamp_utc"))
    if expires and born and expires > born:
        return int((expires - born).total_seconds() / 60), reasons
    reasons.append("EXPIRY_FALLBACK_USED")
    return DEFAULT_EXPIRY_MINUTES, reasons


def _risk(entry: float, stop_loss: float, direction: str) -> float:
    return entry - stop_loss if direction == "LONG" else stop_loss - entry


def _favorable_price(candle: dict[str, Any], direction: str) -> float:
    return float(candle["high"] if direction == "LONG" else candle["low"])


def _adverse_price(candle: dict[str, Any], direction: str) -> float:
    return float(candle["low"] if direction == "LONG" else candle["high"])


def _r_multiple(price: float, entry: float, risk: float, direction: str) -> float | None:
    if risk <= 0:
        return None
    return round((price - entry) / risk, 4) if direction == "LONG" else round((entry - price) / risk, 4)


def replay_trade_outcome(trade: dict[str, Any], candles: list[dict[str, Any]], refs: dict[str, Any] | None = None) -> dict[str, Any]:
    refs = refs or {}
    required = {
        "paper_trade_id": trade.get("paper_trade_id"),
        "direction": trade.get("direction"),
        "entry": trade.get("entry") or trade.get("entry_price"),
        "stop_loss": trade.get("stop_loss"),
        "born_at_utc": trade.get("opened_at_utc") or trade.get("born_at_utc") or trade.get("timestamp_utc"),
    }
    missing = [field for field, value in required.items() if value in (None, "")]
    entry = safe_float(required["entry"])
    stop_loss = safe_float(required["stop_loss"])
    tp1 = safe_float(trade.get("tp1"))
    tp2 = safe_float(trade.get("tp2"))
    direction = str(required["direction"] or "").upper()
    born = _parse_ts(required["born_at_utc"])
    if missing or entry is None or stop_loss is None or direction not in {"LONG", "SHORT"} or born is None:
        return _required_diagnostic(trade, missing, refs)
    risk = _risk(entry, stop_loss, direction)
    if risk <= 0:
        return _required_diagnostic(trade, ["risk_distance"], refs)
    expiry_minutes, expiry_reasons = _expiry_minutes(trade)
    expires_at = born + timedelta(minutes=expiry_minutes)
    future = [c for c in candles if (ts := _parse_ts(c.get("timestamp_utc"))) and born <= ts <= expires_at]
    reason_codes = list(expiry_reasons)
    entry_touched = False
    entry_ts: datetime | None = None
    close_ts: datetime | None = None
    outcome = "ENTRY_NOT_TOUCHED"
    first_hit = "ENTRY_NOT_TOUCHED"
    max_fav = 0.0
    max_adv = 0.0
    last_close = entry
    for candle in future:
        ts = _parse_ts(candle.get("timestamp_utc"))
        if ts is None:
            continue
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        if not entry_touched:
            touched = low <= entry if direction == "LONG" else high >= entry
            if not touched:
                continue
            entry_touched = True
            entry_ts = ts
        fav = (_favorable_price(candle, direction) - entry) if direction == "LONG" else (entry - _favorable_price(candle, direction))
        adv = (entry - _adverse_price(candle, direction)) if direction == "LONG" else (_adverse_price(candle, direction) - entry)
        max_fav = max(max_fav, fav)
        max_adv = max(max_adv, adv)
        last_close = close
        if direction == "LONG":
            hit_tp2 = tp2 is not None and high >= tp2
            hit_tp1 = tp1 is not None and high >= tp1
            hit_sl = low <= stop_loss
        else:
            hit_tp2 = tp2 is not None and low <= tp2
            hit_tp1 = tp1 is not None and low <= tp1
            hit_sl = high >= stop_loss
        if hit_sl and (hit_tp1 or hit_tp2):
            reason_codes.append("INTRACANDLE_TP_SL_ORDER_ESTIMATED")
            open_price = safe_float(candle.get("open")) or entry
            sl_distance = abs(open_price - stop_loss)
            tp_price = tp2 if hit_tp2 else tp1
            tp_distance = abs(open_price - float(tp_price)) if tp_price is not None else sl_distance + 1
            if sl_distance <= tp_distance:
                outcome = "SL_HIT"
                first_hit = "SL_HIT"
            else:
                outcome = "TP2_HIT" if hit_tp2 else "TP1_HIT"
                first_hit = outcome
            close_ts = ts
            break
        if hit_tp2:
            outcome = "TP2_HIT"
            first_hit = "TP2_HIT"
            close_ts = ts
            break
        if hit_tp1:
            outcome = "TP1_HIT"
            first_hit = "TP1_HIT"
            close_ts = ts
            break
        if hit_sl:
            outcome = "SL_HIT"
            first_hit = "SL_HIT"
            close_ts = ts
            break
    if not entry_touched:
        close_ts = expires_at
        realized_r = None
        confidence = "HIGH" if future else "LOW"
    elif outcome == "ENTRY_NOT_TOUCHED":
        outcome = "EXPIRED"
        first_hit = "EXPIRED"
        close_ts = expires_at
        realized_r = _r_multiple(last_close, entry, risk, direction)
        confidence = "MEDIUM"
    elif outcome == "SL_HIT":
        realized_r = -1.0
        confidence = "HIGH"
    elif outcome == "TP2_HIT":
        realized_r = _r_multiple(float(tp2), entry, risk, direction) if tp2 is not None else None
        confidence = "HIGH"
    elif outcome == "TP1_HIT":
        realized_r = _r_multiple(float(tp1), entry, risk, direction) if tp1 is not None else None
        confidence = "HIGH"
    else:
        realized_r = None
        confidence = "LOW"
    hold_seconds = int((close_ts - born).total_seconds()) if close_ts else None
    mfe_r = round(max_fav / risk, 4) if risk > 0 else None
    mae_r = round(max_adv / risk, 4) if risk > 0 else None
    return {
        "paper_trade_id": trade.get("paper_trade_id"),
        "event_id": trade.get("event_id"),
        "model_id": trade.get("model_id") or trade.get("primary_model"),
        "setup_family": trade.get("setup_family") or trade.get("primary_setup"),
        "direction": direction,
        "entry_price": entry,
        "entry": entry,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "entry_touched": entry_touched,
        "outcome_status": outcome,
        "close_reason": outcome,
        "first_hit": first_hit,
        "realized_r": round(realized_r, 4) if realized_r is not None else None,
        "r_result": round(realized_r, 4) if realized_r is not None else None,
        "mfe": round(max_fav, 8),
        "mae": round(max_adv, 8),
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "hold_seconds": hold_seconds,
        "hold_minutes": round(hold_seconds / 60, 4) if hold_seconds is not None else None,
        "born_at_utc": _fmt_ts(born),
        "opened_at_utc": _fmt_ts(born),
        "closed_at_utc": _fmt_ts(close_ts),
        "outcome_truth_confidence": confidence,
        "zone_context": trade.get("zone_context") or {},
        "condition_dna": trade.get("condition_dna") or {},
        "source_state_refs": refs,
        "reason_codes": sorted(set(reason_codes + ["TRUE_OUTCOME_REPLAY"])),
        "primary_tf": trade.get("primary_tf"),
        "trigger_tf": trade.get("trigger_tf"),
        "context_tf": trade.get("context_tf"),
        "structure_tf": trade.get("structure_tf"),
        "plan_style": trade.get("plan_style"),
    }


def _zone_types(value: Any) -> list[str]:
    zones = value if isinstance(value, list) else (value.get("zones") if isinstance(value, dict) else [])
    return [str(zone.get("zone_type")) for zone in zones or [] if isinstance(zone, dict) and zone.get("zone_type")]


def build_true_edge_dataset(outcomes: list[dict[str, Any]], zone_context: dict[str, Any], condition_dna: dict[str, Any]) -> dict[str, Any]:
    rows = []
    fallback_zones = _zone_types(zone_context)[:5]
    top_conditions = [
        str(item.get("condition") or item.get("key"))
        for item in (condition_dna.get("tp_edge_conditions") or condition_dna.get("top_tp_conditions") or [])
        if isinstance(item, dict)
    ][:10]
    for outcome in outcomes:
        rows.append(
            {
                "paper_trade_id": outcome.get("paper_trade_id"),
                "event_id": outcome.get("event_id"),
                "model_id": outcome.get("model_id"),
                "setup_family": outcome.get("setup_family"),
                "timeframe_combo": "/".join(str(outcome.get(field) or "n/a") for field in ("primary_tf", "trigger_tf", "context_tf", "structure_tf")),
                "plan_style": outcome.get("plan_style"),
                "zone_context": outcome.get("zone_context") or {"zone_types": fallback_zones},
                "condition_dna": outcome.get("condition_dna") or {"conditions": top_conditions},
                "structure_state": {"structure_tf": outcome.get("structure_tf")},
                "liquidity_state": {},
                "regime_state": {},
                "outcome_status": outcome.get("outcome_status"),
                "realized_r": outcome.get("realized_r"),
                "mfe": outcome.get("mfe"),
                "mae": outcome.get("mae"),
                "hold_time": outcome.get("hold_seconds"),
                "entry_touched": outcome.get("entry_touched"),
                "tp_truth": outcome.get("outcome_status") in {"TP1_HIT", "TP2_HIT"},
                "sl_truth": outcome.get("outcome_status") == "SL_HIT",
            }
        )
    return {"dataset_id": "TRUE_EDGE_DATASET", "rows": rows, "summary": {"row_count": len(rows)}}


def _metrics(outcomes: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        buckets[str(outcome.get(field) or "UNKNOWN")].append(outcome)
    rows = []
    for key, items in buckets.items():
        avg_r_values = [safe_float(item.get("realized_r")) for item in items if safe_float(item.get("realized_r")) is not None]
        rows.append(
            {
                "key": key,
                "samples": len(items),
                "tp": sum(1 for item in items if item.get("outcome_status") in {"TP1_HIT", "TP2_HIT"}),
                "sl": sum(1 for item in items if item.get("outcome_status") == "SL_HIT"),
                "expired": sum(1 for item in items if item.get("outcome_status") == "EXPIRED"),
                "avg_r": round(sum(avg_r_values) / len(avg_r_values), 4) if avg_r_values else 0.0,
            }
        )
    return sorted(rows, key=lambda item: (item["avg_r"], item["samples"]), reverse=True)


def _write_report(outcomes: list[dict[str, Any]], dataset: dict[str, Any]) -> None:
    total = len(outcomes)
    best_models = _metrics(outcomes, "model_id")[:5]
    worst_models = list(reversed(_metrics(outcomes, "model_id")[-5:]))
    highest_r = max(outcomes, key=lambda item: safe_float(item.get("realized_r")) or -9999, default={})
    highest_mfe = max(outcomes, key=lambda item: safe_float(item.get("mfe")) or -9999, default={})
    worst_mae = max(outcomes, key=lambda item: safe_float(item.get("mae")) or -9999, default={})
    lines = [
        "# NURNOVA True Outcome Report",
        "",
        f"- Total analyzed: {total}",
        f"- Entry touched: {sum(1 for item in outcomes if item.get('entry_touched') is True)}",
        f"- Entry not touched: {sum(1 for item in outcomes if item.get('outcome_status') == 'ENTRY_NOT_TOUCHED')}",
        f"- TP1 hits: {sum(1 for item in outcomes if item.get('outcome_status') == 'TP1_HIT')}",
        f"- TP2 hits: {sum(1 for item in outcomes if item.get('outcome_status') == 'TP2_HIT')}",
        f"- SL hits: {sum(1 for item in outcomes if item.get('outcome_status') == 'SL_HIT')}",
        f"- Expired: {sum(1 for item in outcomes if item.get('outcome_status') == 'EXPIRED')}",
        f"- Best models: {json.dumps(best_models, ensure_ascii=False)}",
        f"- Worst models: {json.dumps(worst_models, ensure_ascii=False)}",
        f"- Best zones: sample-building",
        f"- Worst zones: sample-building",
        f"- Best condition DNA: sample-building",
        f"- Worst condition DNA: sample-building",
        f"- Best TF combo: sample-building",
        f"- Highest realized R: {json.dumps(highest_r, ensure_ascii=False)}",
        f"- Highest MFE: {json.dumps(highest_mfe, ensure_ascii=False)}",
        f"- Worst MAE: {json.dumps(worst_mae, ensure_ascii=False)}",
        f"- Top expired contexts: {json.dumps([item for item in outcomes if item.get('outcome_status') == 'EXPIRED'][:5], ensure_ascii=False)}",
        "",
        "Live execution remains off. This report is replay-only research truth.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_true_outcome_engine() -> dict[str, Any]:
    context = current_runtime_context()
    refs = source_state_refs_from_paths(SOURCE_PATHS)
    factory = load_json(FACTORY_PATH) or {}
    lifecycle = load_json(LIFECYCLE_PATH) or {}
    zone_context = load_json(ZONE_CONTEXT_PATH) or {}
    condition_dna = load_json(TP_DNA_PATH) or {}
    candidates = _extract_candidates(factory, lifecycle)
    if not candidates:
        for payload in read_jsonl_tail_objects(LIFECYCLE_HISTORY_PATH, max_lines=MAX_TAIL_ROWS):
            candidates.extend(_extract_candidates({}, payload))
    candles = _load_replay_candles()
    outcomes = [replay_trade_outcome(trade, candles, refs) for trade in candidates]
    dataset = build_true_edge_dataset(outcomes, zone_context, condition_dna)
    output = stamp_payload(
        {
            "source": {"source_mode": "BOUNDED_CANDLE_REPLAY"},
            "outcomes": outcomes,
            "summary": {
                "total_analyzed": len(outcomes),
                "entry_touched": sum(1 for item in outcomes if item.get("entry_touched") is True),
                "entry_not_touched": sum(1 for item in outcomes if item.get("outcome_status") == "ENTRY_NOT_TOUCHED"),
                "tp1_hits": sum(1 for item in outcomes if item.get("outcome_status") == "TP1_HIT"),
                "tp2_hits": sum(1 for item in outcomes if item.get("outcome_status") == "TP2_HIT"),
                "sl_hits": sum(1 for item in outcomes if item.get("outcome_status") == "SL_HIT"),
                "expired": sum(1 for item in outcomes if item.get("outcome_status") == "EXPIRED"),
                "candle_count": len(candles),
            },
            "data_quality": {
                "level": "HIGH" if outcomes and candles else "MEDIUM" if outcomes else "LOW",
                "missing_inputs": [name for name, path in SOURCE_PATHS.items() if not path.exists()],
            },
            "feeds_next": ["TP_CONDITION_DNA_ENGINE", "EDGE_QUERY_ENGINE", "EDGE_LEARNING_REPORT", "MODEL_SURVIVAL_REGISTRY", "TELEGRAM_REPORTER"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str(factory.get("symbol") or lifecycle.get("symbol") or "BTCUSDT"),
        context,
    )
    dataset_output = stamp_payload(
        {**dataset, "source": {"source_mode": "TRUE_OUTCOME_NORMALIZED_LEARNING_DATASET"}, "execution_safety": output["execution_safety"]},
        "TRUE_EDGE_DATASET",
        output["symbol"],
        context,
    )
    write_json_atomic(OUTPUT_PATH, output)
    append_jsonl_stream(HISTORY_PATH, output)
    write_json_atomic(DATASET_PATH, dataset_output)
    append_jsonl_stream(DATASET_HISTORY_PATH, dataset_output)
    _write_report(outcomes, dataset_output)
    return output


def main() -> None:
    print(json.dumps(run_true_outcome_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
