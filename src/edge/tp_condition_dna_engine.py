from __future__ import annotations

import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload

BLOCK_ID = "TP_CONDITION_DNA_ENGINE"
MAX_TAIL_ROWS = 5000
INPUTS = {
    "research_lifecycle": epoch_data_path("research_paper_lifecycle_history.jsonl"),
    "outcome_accounting": epoch_data_path("outcome_accounting_history.jsonl"),
    "model_clusters": Path("data/simple/model_clusters_history.jsonl"),
    "setup_family_activation": Path("data/simple/setup_family_activation_history.jsonl"),
    "unified_context": Path("data/simple/unified_context_history.jsonl"),
    "signal_grade": epoch_data_path("signal_grade_history.jsonl"),
    "signal_event": epoch_data_path("signal_event_history.jsonl"),
}
OUTPUT_HISTORY = epoch_data_path("tp_condition_dna_history.jsonl")
OUTPUT_STATE = epoch_state_path("latest_tp_condition_dna.json")
ZONE_CONTEXT_PATH = Path("state/simple/latest_zone_context.json")
TRUE_OUTCOME_PATH = epoch_state_path("latest_true_outcome.json")
VOLUME_PROFILE_PATH = Path("state/simple/latest_volume_profile.json")
STRUCTURE_QUALITY_PATH = Path("state/simple/latest_structure_quality.json")


def _status(record: dict[str, Any]) -> str:
    text = str(record.get("outcome_status") or record.get("close_reason") or record.get("result") or record.get("outcome") or record.get("status") or "").upper()
    if text in {"TP1_HIT", "TP2_HIT", "TP_HIT", "WIN"} or text.startswith("TP"):
        return "TP"
    if text in {"SL_HIT", "LOSS"} or text.startswith("SL"):
        return "SL"
    if "EXPIRED" in text:
        return "EXPIRED"
    return "UNKNOWN"


def _conditions(record: dict[str, Any]) -> list[str]:
    keys = {"conditions", "matched_conditions", "activation_reasons", "grade_reasons", "reason_codes", "condition_dna"}
    found: set[str] = set()
    stack: list[Any] = [record]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key in keys and isinstance(value, list):
                    found.update(str(part).upper() for part in value if part)
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return sorted(found)


def _extract_trade_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in ("trades_closed_this_loop", "closed_trades", "open_trades", "trades", "newest_opened_this_loop", "top_candidate_diagnostics", "events", "graded_signals"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                records.append(dict(item))
    if payload.get("latest_event") and isinstance(payload["latest_event"], dict):
        records.append(dict(payload["latest_event"]))
    if not records and any(payload.get(key) for key in ("model_id", "setup_family", "close_reason", "result", "status")):
        records.append(dict(payload))
    return records


def _metric_bucket(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        buckets[str(record.get(field) or "UNKNOWN")].append(record)
    return {key: _sample_metrics(items) for key, items in sorted(buckets.items())}


def _sample_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    tp1 = sum(1 for item in items if str(item.get("close_reason") or item.get("result") or "").upper() == "TP1_HIT")
    tp2 = sum(1 for item in items if str(item.get("close_reason") or item.get("result") or "").upper() == "TP2_HIT")
    tp = sum(1 for item in items if _status(item) == "TP")
    sl = sum(1 for item in items if _status(item) == "SL")
    expired = sum(1 for item in items if _status(item) == "EXPIRED")
    touched = sum(1 for item in items if item.get("entry_touched") is True or item.get("entry_touch") is True or item.get("entry_touched_at_utc"))
    r_values = [safe_float(item.get("realized_r") if item.get("realized_r") is not None else item.get("r_result")) for item in items if safe_float(item.get("realized_r") if item.get("realized_r") is not None else item.get("r_result")) is not None]
    mae_values = [safe_float(item.get("mae")) for item in items if safe_float(item.get("mae")) is not None]
    mfe_values = [safe_float(item.get("mfe")) for item in items if safe_float(item.get("mfe")) is not None]
    return {
        "samples": total,
        "tp_count": tp,
        "sl_count": sl,
        "expired_count": expired,
        "entry_touch_rate": round(touched / total, 4) if total else 0.0,
        "tp1_hit_rate": round(tp1 / total, 4) if total else 0.0,
        "tp2_hit_rate": round(tp2 / total, 4) if total else 0.0,
        "sl_rate": round(sl / total, 4) if total else 0.0,
        "expired_rate": round(expired / total, 4) if total else 0.0,
        "avg_r": round(sum(r_values) / len(r_values), 4) if r_values else 0.0,
        "mae": round(sum(mae_values) / len(mae_values), 4) if mae_values else None,
        "mfe": round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else None,
    }


def _record_zone_types(record: dict[str, Any]) -> list[str]:
    zones = record.get("zone_context") or record.get("zones") or []
    if isinstance(zones, dict):
        zones = zones.get("zones") or []
    out = [str(zone.get("zone_type")) for zone in zones if isinstance(zone, dict) and zone.get("zone_type")]
    return out


def _entry_price(record: dict[str, Any]) -> float | None:
    return safe_float(record.get("entry_price") if record.get("entry_price") is not None else record.get("entry"))


def _profile_levels(volume_profile: dict[str, Any]) -> dict[str, float | None]:
    window = ((volume_profile.get("windows") or {}).get("30m") or {})
    poc = window.get("poc") or {}
    return {
        "poc": safe_float(poc.get("mid_price")),
        "vah": safe_float(window.get("vah")),
        "val": safe_float(window.get("val")),
    }


def _poc_relation(record: dict[str, Any], levels: dict[str, float | None]) -> str:
    entry = _entry_price(record)
    poc = levels.get("poc")
    vah = levels.get("vah")
    val = levels.get("val")
    if entry is None or poc is None:
        return "UNKNOWN"
    if val is not None and entry < val:
        return "BELOW_VAL"
    if vah is not None and entry > vah:
        return "ABOVE_VAH"
    if abs(entry - poc) <= max(abs(poc) * 0.00001, 0.01):
        return "AT_POC"
    if val is not None and entry < poc:
        return "BETWEEN_VAL_AND_POC"
    if vah is not None and entry > poc:
        return "BETWEEN_POC_AND_VAH"
    return "INSIDE_VALUE_AREA"


def _value_area_location(record: dict[str, Any], levels: dict[str, float | None]) -> str:
    entry = _entry_price(record)
    vah = levels.get("vah")
    val = levels.get("val")
    if entry is None or vah is None or val is None:
        return "UNKNOWN"
    if entry < val:
        return "DISCOUNT_BELOW_VAL"
    if entry > vah:
        return "PREMIUM_ABOVE_VAH"
    midpoint = (vah + val) / 2.0
    return "LOWER_VALUE_AREA" if entry <= midpoint else "UPPER_VALUE_AREA"


def _volume_profile_zone_types(record: dict[str, Any], fallback_zones: list[dict[str, Any]]) -> list[str]:
    exact_types = {"REAL_POC_ZONE", "REAL_HVN_ZONE", "REAL_LVN_ZONE", "VALUE_AREA_HIGH_ZONE", "VALUE_AREA_LOW_ZONE", "VALUE_AREA_MID_ZONE", "NAKED_POC_ZONE"}
    zone_types = [zone_type for zone_type in _record_zone_types(record) if zone_type in exact_types]
    if zone_types:
        return zone_types
    return [str(zone.get("zone_type")) for zone in fallback_zones if isinstance(zone, dict) and str(zone.get("zone_type")) in exact_types]


def _structure_types(record: dict[str, Any], structure_quality: dict[str, Any]) -> list[str]:
    found = record.get("structure_types")
    if isinstance(found, list) and found:
        return [str(item) for item in found if item]
    source = record.get("structure_quality") or {}
    if isinstance(source, dict):
        events = source.get("structure_events") or []
        values = [str(event.get("structure_type")) for event in events if isinstance(event, dict) and event.get("structure_type")]
        if values:
            return values
    latest_events = structure_quality.get("structure_events") or []
    return [str(event.get("structure_type")) for event in latest_events[:4] if isinstance(event, dict) and event.get("structure_type")]


def _range_quality_label(record: dict[str, Any], structure_quality: dict[str, Any]) -> str:
    source = record.get("structure_quality") or {}
    if isinstance(source, dict):
        range_quality = source.get("range_quality") or {}
        if isinstance(range_quality, dict) and range_quality.get("range_quality_band"):
            return str(range_quality.get("range_quality_band"))
    return str(((structure_quality.get("range_quality") or {}).get("range_quality_band")) or "UNKNOWN")


def _structure_quality_band(record: dict[str, Any], structure_quality: dict[str, Any]) -> str:
    source = record.get("structure_quality") or {}
    if isinstance(source, dict):
        events = [event for event in source.get("structure_events") or [] if isinstance(event, dict)]
        if events:
            ordered = sorted(events, key=lambda item: safe_float(item.get("quality_score")) or 0.0, reverse=True)
            return str(ordered[0].get("quality_band") or "UNKNOWN")
    latest_events = [event for event in structure_quality.get("structure_events") or [] if isinstance(event, dict)]
    if latest_events:
        ordered = sorted(latest_events, key=lambda item: safe_float(item.get("quality_score")) or 0.0, reverse=True)
        return str(ordered[0].get("quality_band") or "UNKNOWN")
    return "UNKNOWN"


def _zone_rollup(records: list[dict[str, Any]], fallback_zones: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        zone_types = _record_zone_types(record)
        if not zone_types:
            zone_types = [str(zone.get("zone_type")) for zone in fallback_zones[:3] if isinstance(zone, dict) and zone.get("zone_type")]
        for zone_type in zone_types:
            buckets[zone_type].append(record)
    return {key: _sample_metrics(items) for key, items in sorted(buckets.items())}


def _zone_list(records: list[dict[str, Any]], fallback_zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rollup = _zone_rollup(records, fallback_zones)
    return [{"zone_type": key, **value} for key, value in sorted(rollup.items(), key=lambda item: (item[1].get("samples", 0), item[0]), reverse=True)]


def _top(counter: Counter[Any], limit: int = 20) -> list[Any]:
    return [{"key": key, "count": count} for key, count in counter.most_common(limit)]


def run_tp_condition_dna_engine(max_tail_rows: int = MAX_TAIL_ROWS) -> dict[str, Any]:
    context = current_runtime_context()
    zone_context = load_json(ZONE_CONTEXT_PATH) or {}
    volume_profile = load_json(VOLUME_PROFILE_PATH) or {}
    structure_quality = load_json(STRUCTURE_QUALITY_PATH) or {}
    profile_levels = _profile_levels(volume_profile)
    fallback_zones = list(zone_context.get("zones") or [])
    true_outcome = load_json(TRUE_OUTCOME_PATH) or {}
    true_records = [dict(item) for item in true_outcome.get("outcomes") or [] if isinstance(item, dict)]
    payloads = {name: read_jsonl_tail_objects(path, max_lines=max_tail_rows) for name, path in INPUTS.items()}
    records: list[dict[str, Any]] = []
    if true_records:
        records = true_records
    else:
        for rows in payloads.values():
            for payload in rows:
                records.extend(_extract_trade_records(payload))
    by_trade_id: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for record in records:
        trade_id = str(record.get("paper_trade_id") or record.get("event_id") or "")
        if trade_id:
            existing = by_trade_id.get(trade_id, {})
            existing.update({key: value for key, value in record.items() if value not in (None, "", [], {})})
            by_trade_id[trade_id] = existing
        else:
            anonymous.append(record)
    merged = list(by_trade_id.values()) + anonymous
    records_with_structure = [
        {
            **record,
            "structure_quality_band": _structure_quality_band(record, structure_quality),
            "range_quality_label": _range_quality_label(record, structure_quality),
            "structure_type_primary": (_structure_types(record, structure_quality) or ["UNKNOWN"])[0],
        }
        for record in merged
    ]
    tp_conditions: Counter[str] = Counter()
    sl_conditions: Counter[str] = Counter()
    tp_pairs: Counter[tuple[str, str]] = Counter()
    tp_triples: Counter[tuple[str, str, str]] = Counter()
    tp_records: list[dict[str, Any]] = []
    sl_records: list[dict[str, Any]] = []
    expired_records: list[dict[str, Any]] = []
    for record in merged:
        status = _status(record)
        conds = _conditions(record)
        if status == "TP":
            tp_records.append(record)
            tp_conditions.update(conds)
            tp_pairs.update(itertools.combinations(conds, 2))
            tp_triples.update(itertools.combinations(conds, 3))
        elif status == "SL":
            sl_records.append(record)
            sl_conditions.update(conds)
        elif status == "EXPIRED":
            expired_records.append(record)
    by_volume_profile_zone = _zone_rollup(
        [
            {
                **record,
                "zone_context": [{"zone_type": zone_type} for zone_type in _volume_profile_zone_types(record, fallback_zones)],
            }
            for record in merged
        ],
        [],
    )
    edge_conditions = []
    for condition, tp_count in tp_conditions.items():
        sl_count = sl_conditions.get(condition, 0)
        edge_conditions.append({"condition": condition, "tp_count": tp_count, "sl_count": sl_count, "tp_minus_sl": tp_count - sl_count})
    edge_conditions.sort(key=lambda item: (item["tp_minus_sl"], item["tp_count"]), reverse=True)
    sl_risk = [{"condition": condition, "sl_count": count, "tp_count": tp_conditions.get(condition, 0), "sl_minus_tp": count - tp_conditions.get(condition, 0)} for condition, count in sl_conditions.items()]
    sl_risk.sort(key=lambda item: (item["sl_minus_tp"], item["sl_count"]), reverse=True)
    output = stamp_payload(
        {
            "summary": {"tp_samples": len(tp_records), "sl_samples": len(sl_records), "expired_samples": len(expired_records)},
            "top_tp_conditions": _top(tp_conditions),
            "top_sl_conditions": _top(sl_conditions),
            "tp_edge_conditions": edge_conditions[:25],
            "sl_risk_conditions": sl_risk[:25],
            "top_tp_pairs": _top(tp_pairs),
            "top_tp_triples": _top(tp_triples),
            "by_model": _metric_bucket(merged, "model_id"),
            "by_family": _metric_bucket(merged, "setup_family"),
            "by_timeframe": _metric_bucket(merged, "primary_tf"),
            "by_plan_style": _metric_bucket(merged, "plan_style"),
            "by_zone": _zone_rollup(merged, fallback_zones),
            "by_volume_profile_zone": by_volume_profile_zone,
            "by_structure_quality": _metric_bucket(records_with_structure, "structure_quality_band"),
            "tp_by_structure_type": _metric_bucket([record for record in records_with_structure if _status(record) == "TP"], "structure_type_primary"),
            "sl_by_structure_type": _metric_bucket([record for record in records_with_structure if _status(record) == "SL"], "structure_type_primary"),
            "tp_by_range_quality": _metric_bucket([record for record in records_with_structure if _status(record) == "TP"], "range_quality_label"),
            "sl_by_range_quality": _metric_bucket([record for record in records_with_structure if _status(record) == "SL"], "range_quality_label"),
            "tp_by_poc_relation": _metric_bucket([{**record, "poc_relation": _poc_relation(record, profile_levels)} for record in merged], "poc_relation"),
            "sl_by_poc_relation": _metric_bucket([{**record, "poc_relation": _poc_relation(record, profile_levels)} for record in merged if _status(record) == "SL"], "poc_relation"),
            "tp_by_value_area_location": _metric_bucket([{**record, "value_area_location": _value_area_location(record, profile_levels)} for record in merged], "value_area_location"),
            "tp_zones": _zone_list(tp_records, fallback_zones),
            "sl_zones": _zone_list(sl_records, fallback_zones),
            "expired_zones": _zone_list(expired_records, fallback_zones),
            "volume_profile_context": {
                "profile_status": volume_profile.get("profile_status"),
                "levels_30m": profile_levels,
            },
            "structure_quality_context": {
                "summary": structure_quality.get("summary") or {},
                "range_quality": structure_quality.get("range_quality") or {},
            },
            "zone_context": {
                "timestamp_utc": zone_context.get("timestamp_utc"),
                "block_id": zone_context.get("block_id"),
                "summary": zone_context.get("summary") or {},
            },
            "data_quality": {
                "level": "HIGH" if merged else "LOW",
                "input_rows": {name: len(rows) for name, rows in payloads.items()},
                "missing_inputs": [name for name, path in INPUTS.items() if not path.exists()],
                "true_outcome_used": bool(true_records),
            },
            "feeds_next": ["EDGE_QUERY_ENGINE", "TELEGRAM_RESEARCH_REPORTER"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        "BTCUSDT",
        context,
    )
    write_json_atomic(OUTPUT_STATE, output)
    append_jsonl_stream(OUTPUT_HISTORY, output)
    return output


def main() -> None:
    print(json.dumps(run_tp_condition_dna_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
