from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload

BLOCK_ID = "EDGE_QUERY_ENGINE"
LIFECYCLE_HISTORY = epoch_data_path("research_paper_lifecycle_history.jsonl")
SIGNAL_EVENT_HISTORY = epoch_data_path("signal_event_history.jsonl")
TP_DNA_PATH = epoch_state_path("latest_tp_condition_dna.json")
ZONE_PATH = Path("state/simple/latest_zone_context.json")
TRUE_OUTCOME_PATH = epoch_state_path("latest_true_outcome.json")
VOLUME_PROFILE_PATH = Path("state/simple/latest_volume_profile.json")
STRUCTURE_QUALITY_PATH = Path("state/simple/latest_structure_quality.json")
OUTPUT_HISTORY = epoch_data_path("edge_query_report_history.jsonl")
OUTPUT_STATE = epoch_state_path("latest_edge_query_report.json")
MAX_ROWS = 5000


def _records() -> list[dict[str, Any]]:
    true_outcome = load_json(TRUE_OUTCOME_PATH) or {}
    true_records = [dict(item) for item in true_outcome.get("outcomes") or [] if isinstance(item, dict)]
    if true_records:
        return true_records
    rows = read_jsonl_tail_objects(LIFECYCLE_HISTORY, max_lines=MAX_ROWS) + read_jsonl_tail_objects(SIGNAL_EVENT_HISTORY, max_lines=MAX_ROWS)
    out: list[dict[str, Any]] = []
    for row in rows:
        for key in ("trades_closed_this_loop", "closed_trades", "open_trades", "events"):
            out.extend(dict(item) for item in row.get(key) or [] if isinstance(item, dict))
        if isinstance(row.get("latest_event"), dict):
            out.append(dict(row["latest_event"]))
    return out


def _result(record: dict[str, Any]) -> str:
    text = str(record.get("outcome_status") or record.get("close_reason") or record.get("result") or record.get("status") or "").upper()
    if text.startswith("TP") or text == "WIN":
        return "TP"
    if text.startswith("SL") or text == "LOSS":
        return "SL"
    if "EXPIRED" in text:
        return "EXPIRED"
    return "UNKNOWN"


def _metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    tp = sum(1 for item in items if _result(item) == "TP")
    sl = sum(1 for item in items if _result(item) == "SL")
    expired = sum(1 for item in items if _result(item) == "EXPIRED")
    r_values = [safe_float(item.get("r_result")) for item in items if safe_float(item.get("r_result")) is not None]
    return {"samples": total, "tp": tp, "sl": sl, "expired": expired, "winrate": round(tp / (tp + sl), 4) if tp + sl else 0.0, "avg_r": round(sum(r_values) / len(r_values), 4) if r_values else 0.0}


def _group(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        buckets[str(record.get(field) or "UNKNOWN")].append(record)
    return {key: _metrics(items) for key, items in buckets.items()}


def _record_zone_types(record: dict[str, Any]) -> list[str]:
    zones = record.get("zone_context") or record.get("zones") or []
    if isinstance(zones, dict):
        zones = zones.get("zones") or []
    return [str(zone.get("zone_type")) for zone in zones if isinstance(zone, dict) and zone.get("zone_type")]


def _entry_price(record: dict[str, Any]) -> float | None:
    return safe_float(record.get("entry_price") if record.get("entry_price") is not None else record.get("entry"))


def _profile_levels(volume_profile: dict[str, Any]) -> dict[str, float | None]:
    window = ((volume_profile.get("windows") or {}).get("30m") or {})
    poc = window.get("poc") or {}
    return {"poc": safe_float(poc.get("mid_price")), "vah": safe_float(window.get("vah")), "val": safe_float(window.get("val"))}


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
    return "INSIDE_VALUE_AREA"


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
    return [str(event.get("structure_type")) for event in (structure_quality.get("structure_events") or [])[:4] if isinstance(event, dict) and event.get("structure_type")]


def _range_quality_label(record: dict[str, Any], structure_quality: dict[str, Any]) -> str:
    source = record.get("structure_quality") or {}
    if isinstance(source, dict):
        range_quality = source.get("range_quality") or {}
        if isinstance(range_quality, dict) and range_quality.get("range_quality_band"):
            return str(range_quality.get("range_quality_band"))
    return str(((structure_quality.get("range_quality") or {}).get("range_quality_band")) or "UNKNOWN")


def _has_combo(record: dict[str, Any], label: str, structure_quality: dict[str, Any]) -> bool:
    combos = record.get("structure_liquidity_zone_combos")
    if isinstance(combos, list):
        return any(str(item.get("label")) == label for item in combos if isinstance(item, dict))
    return any(str(item.get("label")) == label for item in (structure_quality.get("structure_liquidity_zone_combos") or []) if isinstance(item, dict))


def _zone_records(records: list[dict[str, Any]], zone_type: str, fallback: bool) -> list[dict[str, Any]]:
    if fallback:
        return records
    target = zone_type.upper()
    return [record for record in records if target in {item.upper() for item in _record_zone_types(record)} or target in _text(record)]


def _zone_answer(records: list[dict[str, Any]], zones: list[dict[str, Any]], name: str, predicate) -> dict[str, Any]:
    answers = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        zone_type = str(zone.get("zone_type") or "UNKNOWN")
        fallback = not any(_record_zone_types(record) for record in records)
        samples = [record for record in _zone_records(records, zone_type, fallback) if predicate(record)]
        answers.append({"zone_type": zone_type, "zone_meaning": zone.get("zone_meaning"), "approximation_level": zone.get("approximation_level"), "summary": _metrics(samples)})
    return {"question": name, "zones": answers}


def _text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False).upper()


def _question(records: list[dict[str, Any]], name: str, predicate) -> dict[str, Any]:
    samples = [record for record in records if predicate(_text(record), record)]
    return {"question": name, "summary": _metrics(samples), "sample_count": len(samples), "examples": samples[:10]}


def run_edge_query_engine() -> dict[str, Any]:
    context = current_runtime_context()
    records = _records()
    tp_dna = load_json(TP_DNA_PATH) or {}
    zone = load_json(ZONE_PATH) or {}
    volume_profile = load_json(VOLUME_PROFILE_PATH) or {}
    structure_quality = load_json(STRUCTURE_QUALITY_PATH) or {}
    profile_levels = _profile_levels(volume_profile)
    reports = [
        _question(records, "Which models truly TP?", lambda text, record: _result(record) == "TP"),
        _question(records, "Which zones truly TP?", lambda text, record: _result(record) == "TP" and bool(_record_zone_types(record))),
        _question(records, "Which condition DNA truly TP?", lambda text, record: _result(record) == "TP" and bool(record.get("condition_dna"))),
        _question(records, "Which setups never touch entry?", lambda text, record: record.get("entry_touched") is False),
        _question(records, "Which structures fail most?", lambda text, record: _result(record) == "SL" and ("STRUCTURE" in text or record.get("structure_tf"))),
        _question(records, "Which contexts expire most?", lambda text, record: _result(record) == "EXPIRED"),
        _question(records, "Which zone + structure + liquidity combos produce strongest displacement?", lambda text, record: safe_float(record.get("mfe")) is not None),
        _question(records, "Which contexts produce best realized R?", lambda text, record: safe_float(record.get("realized_r")) is not None),
        _question(records, "Liquidity Sweep -> Reaction", lambda text, _: "SWEEP" in text),
        _question(records, "Absorption Edge", lambda text, _: "ABSORPTION" in text),
        _question(records, "Delta Divergence", lambda text, _: "DELTA" in text and "DIVERGENCE" in text),
        _question(records, "Timeframe Alignment", lambda text, record: bool(record.get("primary_tf") and record.get("context_tf"))),
        _question(records, "Entry Touch", lambda text, record: "ENTRY" in text and ("TOUCH" in text or record.get("entry_touched") is not None)),
        _question(records, "NO_TRADE Edge", lambda text, _: "NO_TRADE" in text),
        _question(records, "Liquidity + Structure", lambda text, _: "LIQUIDITY" in text and any(token in text for token in ("STRUCTURE", "BOS", "CHOCH"))),
        _question(records, "Wall Lifecycle", lambda text, _: "WALL" in text),
        _question(records, "Scenario -> Outcome", lambda text, record: bool(record.get("scenario_label") or "SCENARIO" in text)),
        _question(records, "Fake Move Detection", lambda text, _: "FAKE" in text or "FAILED_BREAKOUT" in text),
        _question(records, "Which POC zones produced TP?", lambda text, record: _result(record) == "TP" and "REAL_POC_ZONE" in _record_zone_types(record)),
        _question(records, "Which HVN zones produced SL?", lambda text, record: _result(record) == "SL" and "REAL_HVN_ZONE" in _record_zone_types(record)),
        _question(records, "Which LVN rejection produced displacement?", lambda text, record: "REAL_LVN_ZONE" in _record_zone_types(record) and safe_float(record.get("mfe")) is not None),
        _question(records, "Which Naked POC revisits produced reversal?", lambda text, record: "NAKED_POC_ZONE" in _record_zone_types(record) and any(token in text for token in ("RECLAIM", "REVERSAL"))),
        _question(records, "Which value area location produced best R?", lambda text, record: _poc_relation(record, profile_levels) in {"BELOW_VAL", "ABOVE_VAH", "AT_POC", "INSIDE_VALUE_AREA"} and safe_float(record.get("realized_r")) is not None),
        _question(records, "Is TP more likely from discount below VAL or premium above VAH?", lambda text, record: _poc_relation(record, profile_levels) in {"BELOW_VAL", "ABOVE_VAH"} and _result(record) == "TP"),
        _question(records, "Which BOS quality produced TP?", lambda text, record: any(item.startswith("BOS") for item in _structure_types(record, structure_quality)) and _result(record) == "TP"),
        _question(records, "Which CHOCH quality produced SL?", lambda text, record: any(item.startswith("CHOCH") for item in _structure_types(record, structure_quality)) and _result(record) == "SL"),
        _question(records, "Which range quality works?", lambda text, record: _range_quality_label(record, structure_quality) != "UNKNOWN"),
        _question(records, "Which HTF decision zones produce displacement?", lambda text, record: any(item.startswith("HTF_DECISION") for item in _structure_types(record, structure_quality)) and safe_float(record.get("mfe")) is not None),
        _question(records, "Which structure + liquidity + zone combo works?", lambda text, record: _has_combo(record, "SWEEP_THEN_RECLAIM", structure_quality) or _has_combo(record, "BOS_INTO_LIQUIDITY_POOL", structure_quality) or _has_combo(record, "DISPLACEMENT_FROM_COMPRESSION", structure_quality)),
        _question(records, "Which fake breaks reverse?", lambda text, record: any(item.startswith("FAKE_BREAKOUT") for item in _structure_types(record, structure_quality))),
    ]
    by_zone = {}
    zones = list(zone.get("zones") or [])
    for zone_item in zones:
        if isinstance(zone_item, dict):
            zone_type = str(zone_item.get("zone_type") or "UNKNOWN")
            samples = _zone_records(records, zone_type, fallback=not any(_record_zone_types(record) for record in records))
            by_zone[zone_type] = {"observed_zone": zone_item, "outcomes": _metrics(samples)}
    zone_queries = [
        _zone_answer(records, zones, "Which zones produced TP?", lambda record: _result(record) == "TP"),
        _zone_answer(records, zones, "Which zones produced SL?", lambda record: _result(record) == "SL"),
        _zone_answer(records, zones, "Which zones expired?", lambda record: _result(record) == "EXPIRED"),
        _zone_answer(records, zones, "Which zones are associated with fake breakout?", lambda record: "FAKE" in _text(record) or "BREAKOUT_FAILURE" in _text(record)),
        _zone_answer(records, zones, "Which zones had entry touch but failed?", lambda record: bool(record.get("entry_touched") or record.get("entry_touched_at_utc")) and _result(record) in {"SL", "EXPIRED"}),
        _zone_answer(records, zones, "Which zones produced strongest displacement?", lambda record: "DISPLACEMENT" in _text(record) or "VOLATILITY_EXPANSION" in _text(record)),
        _zone_answer(records, zones, "Which zones are most associated with ELITE_CONTINUATION_CONTEXT?", lambda record: "ELITE_CONTINUATION_CONTEXT" in _text(record)),
    ]
    groups = [("model", _group(records, "model_id")), ("family", _group(records, "setup_family")), ("timeframe", _group(records, "primary_tf"))]
    all_edges = []
    for _name, bucket in groups:
        for key, metrics in bucket.items():
            all_edges.append({"key": key, **metrics})
    all_edges.sort(key=lambda item: (item.get("avg_r", 0), item.get("winrate", 0), item.get("samples", 0)), reverse=True)
    output = stamp_payload(
        {
            "summary": {"records_analyzed": len(records), "question_count": len(reports), "true_outcome_used": TRUE_OUTCOME_PATH.exists()},
            "questions": reports,
            "best_observed_edges": all_edges[:10],
            "worst_observed_edges": list(reversed(all_edges[-10:])),
            "by_model": dict(groups[0][1]),
            "by_family": dict(groups[1][1]),
            "by_timeframe": dict(groups[2][1]),
            "by_zone": by_zone,
            "by_volume_profile_zone": tp_dna.get("by_volume_profile_zone") or {},
            "by_structure_quality": tp_dna.get("by_structure_quality") or {},
            "by_structure_type": {
                "tp": tp_dna.get("tp_by_structure_type") or {},
                "sl": tp_dna.get("sl_by_structure_type") or {},
                "range": {
                    "tp": tp_dna.get("tp_by_range_quality") or {},
                    "sl": tp_dna.get("sl_by_range_quality") or {},
                },
            },
            "volume_profile_queries": {
                "tp_by_poc_relation": tp_dna.get("tp_by_poc_relation") or {},
                "sl_by_poc_relation": tp_dna.get("sl_by_poc_relation") or {},
                "tp_by_value_area_location": tp_dna.get("tp_by_value_area_location") or {},
                "levels_30m": profile_levels,
                "profile_status": volume_profile.get("profile_status"),
            },
            "structure_quality_context": {
                "summary": structure_quality.get("summary") or {},
                "range_quality": structure_quality.get("range_quality") or {},
                "htf_decision_zones": structure_quality.get("htf_decision_zones") or [],
                "structure_liquidity_zone_combos": structure_quality.get("structure_liquidity_zone_combos") or [],
            },
            "zone_queries": zone_queries,
            "zone_context": {"timestamp_utc": zone.get("timestamp_utc"), "summary": zone.get("summary") or {}},
            "by_condition_cluster": {"tp_edge_conditions": tp_dna.get("tp_edge_conditions") or [], "sl_risk_conditions": tp_dna.get("sl_risk_conditions") or []},
            "limitations": ["Tail-based research view; missing local histories are reported, not invented.", "No hypothetical outcomes are generated unless already present in source records."],
            "data_quality": {"level": "HIGH" if records else "LOW", "missing_inputs": [str(path) for path in (LIFECYCLE_HISTORY, SIGNAL_EVENT_HISTORY) if not path.exists()]},
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
    print(json.dumps(run_edge_query_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
