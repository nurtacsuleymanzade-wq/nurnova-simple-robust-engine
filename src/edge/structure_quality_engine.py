from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, source_state_refs_from_paths, stamp_payload

BLOCK_ID = "STRUCTURE_QUALITY_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
OUTPUT_PATH = STATE_DIR / "latest_structure_quality.json"
OUTPUT_HISTORY = DATA_DIR / "structure_quality_history.jsonl"
EPOCH_OUTPUT_PATH = epoch_state_path("latest_structure_quality.json")
EPOCH_HISTORY_PATH = epoch_data_path("structure_quality_history.jsonl")
REPORT_PATH = Path("reports/simple/epoch_v2/latest_structure_quality_report.md")
MAX_HISTORY = 400
LATEST_PATHS = {
    "market_structure": STATE_DIR / "latest_market_structure.json",
    "mtf_candle_dna": STATE_DIR / "latest_mtf_candle_dna.json",
    "liquidity_map": STATE_DIR / "latest_liquidity_map.json",
    "interpretation": STATE_DIR / "latest_interpretation.json",
    "three_scenarios": STATE_DIR / "latest_three_scenarios.json",
    "unified_context": STATE_DIR / "latest_unified_context.json",
    "volume_profile": STATE_DIR / "latest_volume_profile.json",
    "zone_context": STATE_DIR / "latest_zone_context.json",
}
HISTORY_PATHS = {
    "market_structure_history": DATA_DIR / "market_structure_history.jsonl",
    "mtf_candle_dna_history": DATA_DIR / "mtf_candle_dna_history.jsonl",
    "true_edge_dataset_history": epoch_data_path("true_edge_dataset_history.jsonl"),
}
FEEDS_NEXT = [
    "ZONE_CONTEXT_ENGINE",
    "UNIFIED_CONTEXT_ENGINE",
    "TP_CONDITION_DNA_ENGINE",
    "EDGE_QUERY_ENGINE",
    "EDGE_LEARNING_REPORT",
]
TF_ORDER = {"1s": 1, "3s": 2, "5s": 3, "15s": 4, "1m": 5, "3m": 6, "5m": 7, "15m": 8, "1h": 9, "4h": 10, "12h": 11, "1d": 12}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _structure_id(structure_type: str, timeframe: str, level_price: Any) -> str:
    raw = f"{structure_type}|{timeframe}|{level_price}"
    return "STRUCT_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16].upper()


def _clamp01(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(1.0, value)), 4)


def _quality_band(score: float | None, reasons: list[str]) -> str:
    if score is None or "STRUCTURE_SOURCE_INSUFFICIENT" in reasons:
        return "DIAGNOSTIC_ONLY"
    if score >= 0.75:
        return "HIGH_CONFIDENCE"
    if score >= 0.5:
        return "MEDIUM_CONFIDENCE"
    return "LOW_CONFIDENCE"


def _text(*payloads: Any) -> str:
    return json.dumps(payloads, ensure_ascii=False).upper()


def _current_price(payloads: dict[str, dict[str, Any]]) -> float | None:
    unified = payloads.get("unified_context", {})
    interpretation = payloads.get("interpretation", {})
    return (
        safe_float(unified.get("current_price"))
        or safe_float(interpretation.get("current_price"))
        or safe_float((payloads.get("liquidity_map", {}) or {}).get("current_price"))
    )


def _volume_profile_levels(payloads: dict[str, dict[str, Any]]) -> dict[str, float | None]:
    profile = payloads.get("volume_profile", {})
    window = ((profile.get("windows") or {}).get("30m") or {})
    poc = window.get("poc") or {}
    return {
        "poc": safe_float(poc.get("mid_price")),
        "vah": safe_float(window.get("vah")),
        "val": safe_float(window.get("val")),
        "vamid": safe_float(window.get("vamid")),
    }


def _nearest_liquidity(level_price: float | None, liquidity_map: dict[str, Any]) -> dict[str, Any]:
    if level_price is None:
        return {}
    best: dict[str, Any] = {}
    best_distance = None
    for item in liquidity_map.get("detected_levels") or []:
        if not isinstance(item, dict):
            continue
        price = safe_float(item.get("price"))
        if price is None:
            continue
        distance = abs(price - level_price)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = {
                "liquidity_type": item.get("liquidity_type"),
                "bucket": item.get("bucket"),
                "strength": item.get("strength"),
                "price": price,
                "distance": round(distance, 8),
                "reason_codes": item.get("reason_codes") or [],
            }
    return best


def _volume_profile_relation(level_price: float | None, payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    levels = _volume_profile_levels(payloads)
    if level_price is None:
        return {"relation": "UNKNOWN"}
    poc = levels.get("poc")
    vah = levels.get("vah")
    val = levels.get("val")
    if poc is None:
        return {"relation": "UNKNOWN", "reason_codes": ["VOLUME_PROFILE_UNAVAILABLE"]}
    if val is not None and level_price < val:
        relation = "BELOW_VAL"
    elif vah is not None and level_price > vah:
        relation = "ABOVE_VAH"
    elif abs(level_price - poc) <= max(abs(poc) * 0.00001, 0.01):
        relation = "AT_POC"
    else:
        relation = "INSIDE_VALUE_AREA"
    return {"relation": relation, "poc": poc, "vah": vah, "val": val}


def _zone_relation(level_price: float | None, payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    zones = (payloads.get("zone_context", {}) or {}).get("zones") or []
    if level_price is None:
        return {"zone_type": "UNKNOWN"}
    nearest = None
    nearest_distance = None
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        mid = safe_float(zone.get("mid_price"))
        if mid is None:
            continue
        distance = abs(mid - level_price)
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest = {
                "zone_type": zone.get("zone_type"),
                "approximation_level": zone.get("approximation_level"),
                "distance": round(distance, 8),
                "status": zone.get("status"),
            }
    return nearest or {"zone_type": "UNKNOWN"}


def _displacement(payloads: dict[str, dict[str, Any]], timeframe: str, level_price: float | None, direction: str) -> dict[str, Any]:
    tf_payload = (payloads.get("mtf_candle_dna", {}) or {}).get(timeframe) or {}
    close_price = safe_float(tf_payload.get("close"))
    atr = safe_float(tf_payload.get("atr_14") or tf_payload.get("atr_21"))
    if level_price is None or close_price is None:
        return {"magnitude": None, "quality": "UNKNOWN"}
    raw_move = close_price - level_price if direction == "LONG" else level_price - close_price
    magnitude = round(raw_move, 8)
    normalized = round(magnitude / atr, 4) if atr not in (None, 0.0) else None
    if normalized is None:
        quality = "UNKNOWN"
    elif normalized > 1.0:
        quality = "STRONG"
    elif normalized > 0.25:
        quality = "MODEST"
    else:
        quality = "WEAK"
    return {"magnitude": magnitude, "normalized_atr": normalized, "quality": quality}


def _follow_through(displacement: dict[str, Any], interpretation: dict[str, Any]) -> str:
    text = _text(interpretation)
    if displacement.get("quality") == "STRONG" and "NO ACCEPTED DIRECTIONAL BREAK" not in text:
        return "STRONG"
    if displacement.get("quality") == "MODEST":
        return "MODEST"
    if "NO ACCEPTED DIRECTIONAL BREAK" in text or "RANGE-BOUND" in text:
        return "WEAK"
    return "UNKNOWN"


def _fakeout_risk(timeframe_payload: dict[str, Any], interpretation: dict[str, Any], liquidity: dict[str, Any], displacement: dict[str, Any]) -> str:
    text = _text(timeframe_payload, interpretation)
    risk_points = 0
    if str(timeframe_payload.get("trend_state") or "").upper() == "RANGE":
        risk_points += 1
    if "FAILED" in text or "NO ACCEPTED DIRECTIONAL BREAK" in text:
        risk_points += 1
    if str(liquidity.get("bucket") or "").upper() == "NEAR":
        risk_points += 1
    if displacement.get("quality") in {"WEAK", "UNKNOWN"}:
        risk_points += 1
    if risk_points >= 3:
        return "HIGH"
    if risk_points == 2:
        return "MEDIUM"
    return "LOW"


def _event(
    structure_type: str,
    timeframe: str,
    direction: str,
    level_price: float | None,
    payloads: dict[str, dict[str, Any]],
    refs: dict[str, Any],
    source_layer: str,
    reason_codes: list[str] | None = None,
    invalidation_level: float | None = None,
) -> dict[str, Any]:
    tf_payload = (payloads.get("market_structure", {}) or {}).get(timeframe) or {}
    liquidity = _nearest_liquidity(level_price, payloads.get("liquidity_map", {}) or {})
    volume_relation = _volume_profile_relation(level_price, payloads)
    zone_relation = _zone_relation(level_price, payloads)
    displacement = _displacement(payloads, timeframe, level_price, direction)
    interpretation = payloads.get("interpretation", {}) or {}
    reasons = list(reason_codes or [])
    score_parts: list[float] = []
    if tf_payload.get("data_quality", {}).get("level") == "HIGH":
        score_parts.append(0.65)
        reasons.append("CLEAN_SWING_DEFINITION")
    elif tf_payload:
        score_parts.append(0.45)
    else:
        reasons.append("STRUCTURE_SOURCE_INSUFFICIENT")
    if tf_payload.get("bos_detected") or tf_payload.get("choch_detected") or tf_payload.get("mss_detected"):
        score_parts.append(0.8)
        reasons.append("STRUCTURE_BREAK_SOURCE_PRESENT")
    if str(tf_payload.get("trend_state") or "").upper() in {"BULLISH", "BEARISH", "TREND"}:
        score_parts.append(0.65)
        reasons.append("TREND_ALIGNMENT_PRESENT")
    elif str(tf_payload.get("trend_state") or "").upper() == "RANGE":
        score_parts.append(0.35)
    if liquidity:
        score_parts.append(0.7 if str(liquidity.get("bucket") or "").upper() == "NEAR" else 0.5)
        reasons.append("LIQUIDITY_PROXIMITY_MEASURED")
    if volume_relation.get("relation") in {"AT_POC", "INSIDE_VALUE_AREA"}:
        score_parts.append(0.6)
        reasons.append("VOLUME_PROFILE_RELATION_MEASURED")
    elif volume_relation.get("relation") in {"BELOW_VAL", "ABOVE_VAH"}:
        score_parts.append(0.5)
    if zone_relation.get("zone_type") and zone_relation.get("zone_type") != "UNKNOWN":
        score_parts.append(0.55)
        reasons.append("ZONE_CONTEXT_RELATION_MEASURED")
    if displacement.get("quality") == "STRONG":
        score_parts.append(0.85)
        reasons.append("DISPLACEMENT_AFTER_BREAK_STRONG")
    elif displacement.get("quality") == "MODEST":
        score_parts.append(0.55)
    elif displacement.get("quality") == "WEAK":
        score_parts.append(0.25)
    if timeframe in {"1h", "4h"}:
        score_parts.append(0.7)
        reasons.append("HTF_ALIGNMENT_COMPONENT")
    if not score_parts:
        reasons.append("STRUCTURE_SOURCE_INSUFFICIENT")
    quality_score = round(sum(score_parts) / len(score_parts), 4) if score_parts else None
    band = _quality_band(quality_score, reasons)
    return {
        "structure_id": _structure_id(structure_type, timeframe, level_price),
        "structure_type": structure_type,
        "timeframe": timeframe,
        "direction": direction,
        "level_price": round(level_price, 8) if level_price is not None else None,
        "source_layer": source_layer,
        "confidence": _clamp01(quality_score),
        "quality_score": quality_score,
        "quality_band": band,
        "maturity": "MATURE" if tf_payload.get("data_quality", {}).get("sample_count", 0) >= 20 else "EARLY",
        "invalidation_level": round(invalidation_level, 8) if invalidation_level is not None else None,
        "relation_to_liquidity": liquidity,
        "relation_to_volume_profile": volume_relation,
        "relation_to_zone": zone_relation,
        "displacement_after_event": displacement,
        "follow_through_quality": _follow_through(displacement, interpretation),
        "fakeout_risk": _fakeout_risk(tf_payload, interpretation, liquidity, displacement),
        "approximation_level": "DIAGNOSTIC" if "STRUCTURE_SOURCE_INSUFFICIENT" in reasons else "APPROX",
        "source_state_refs": refs,
        "reason_codes": sorted(set(reasons)),
    }


def _range_quality(payloads: dict[str, dict[str, Any]], history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    structure = payloads.get("market_structure", {}) or {}
    highs = []
    lows = []
    eqh = 0
    eql = 0
    range_count = 0
    tf_payloads = []
    for tf, payload in structure.items():
        if not isinstance(payload, dict) or tf in {"summary", "data_quality", "source", "execution_safety"}:
            continue
        tf_payloads.append((tf, payload))
        high = safe_float(payload.get("last_swing_high"))
        low = safe_float(payload.get("last_swing_low"))
        if high is not None:
            highs.append(high)
        if low is not None:
            lows.append(low)
        label = str(payload.get("structure_label") or "").upper()
        if "EQH" in label:
            eqh += 1
        if "EQL" in label:
            eql += 1
        if str(payload.get("trend_state") or "").upper() == "RANGE":
            range_count += 1
    range_high = max(highs) if highs else None
    range_low = min(lows) if lows else None
    range_mid = round((range_high + range_low) / 2.0, 8) if range_high is not None and range_low is not None else None
    width = round(range_high - range_low, 8) if range_high is not None and range_low is not None else None
    age = len(history_rows)
    if width is None:
        band = "UNRELIABLE_RANGE"
    elif width == 0 and range_count >= max(len(tf_payloads) // 2, 1):
        band = "COMPRESSION_RANGE"
    elif range_count >= max(len(tf_payloads) // 2, 1):
        band = "CLEAN_RANGE"
    elif eqh + eql >= max(len(tf_payloads) // 2, 1):
        band = "CHOPPY_RANGE"
    else:
        band = "EXPANDING_RANGE"
    return {
        "range_high": range_high,
        "range_low": range_low,
        "range_mid": range_mid,
        "range_width": width,
        "range_age": age,
        "touches_high": eqh,
        "touches_low": eql,
        "fake_breaks_high": 1 if "FAILED_BREAKOUT" in _text(payloads.get("interpretation", {}), payloads.get("three_scenarios", {})) else 0,
        "fake_breaks_low": 1 if "FAILED_BREAKOUT" in _text(payloads.get("interpretation", {}), payloads.get("three_scenarios", {})) else 0,
        "acceptance_inside_range": "YES" if range_count >= 1 else "UNKNOWN",
        "rejection_at_edges": "YES" if eqh or eql else "UNKNOWN",
        "compression_inside_range": "YES" if band == "COMPRESSION_RANGE" else "NO",
        "breakout_probability_label": "LOW" if band in {"CLEAN_RANGE", "CHOPPY_RANGE"} else "MEDIUM" if band == "COMPRESSION_RANGE" else "UNKNOWN",
        "mean_reversion_probability_label": "HIGH" if band in {"CLEAN_RANGE", "CHOPPY_RANGE"} else "MEDIUM" if band == "COMPRESSION_RANGE" else "UNKNOWN",
        "range_quality_band": band,
    }


def _combo_labels(events: list[dict[str, Any]], payloads: dict[str, dict[str, Any]], range_quality: dict[str, Any]) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    zone_text = _text(payloads.get("zone_context", {}))
    structure_text = _text(payloads.get("market_structure", {}), payloads.get("interpretation", {}))
    for event in events:
        stype = str(event.get("structure_type") or "")
        direction = str(event.get("direction") or "")
        zone_type = str((event.get("relation_to_zone") or {}).get("zone_type") or "")
        liquidity_type = str((event.get("relation_to_liquidity") or {}).get("liquidity_type") or "")
        label = None
        if direction == "LONG" and zone_type == "DISCOUNT_ZONE":
            label = "BULLISH_STRUCTURE_AT_DISCOUNT"
        elif direction == "SHORT" and zone_type == "PREMIUM_ZONE":
            label = "BEARISH_STRUCTURE_AT_PREMIUM"
        elif stype.startswith("BOS") and liquidity_type:
            label = "BOS_INTO_LIQUIDITY_POOL"
        elif "SWEEP" in stype and "RECLAIM" in structure_text:
            label = "SWEEP_THEN_RECLAIM"
        elif stype.startswith("CHOCH") and "ABSORPTION" in structure_text:
            label = "CHOCH_AFTER_ABSORPTION"
        elif "FAKE_BREAKOUT" in stype and "REAL_LVN_ZONE" in zone_text:
            label = "BREAKOUT_FAILURE_AT_LVN"
        elif stype.startswith("HTF_DECISION") and liquidity_type:
            label = "HTF_DECISION_PLUS_LIQUIDITY_POOL"
        elif range_quality.get("range_quality_band") == "COMPRESSION_RANGE" and event.get("displacement_after_event", {}).get("quality") == "STRONG":
            label = "DISPLACEMENT_FROM_COMPRESSION"
        elif event.get("follow_through_quality") == "WEAK":
            label = "STRUCTURE_BREAK_WITHOUT_FOLLOWTHROUGH"
        if label:
            labels.append(
                {
                    "label": label,
                    "structure_id": event.get("structure_id"),
                    "structure_type": stype,
                    "timeframe": event.get("timeframe"),
                    "zone_type": zone_type,
                    "liquidity_type": liquidity_type,
                    "quality_band": event.get("quality_band"),
                }
            )
    if not labels:
        labels.append({"label": "STRUCTURE_SOURCE_INSUFFICIENT", "quality_band": "DIAGNOSTIC_ONLY"})
    return labels


def build_structure_quality_from_payloads(payloads: dict[str, dict[str, Any]], history_rows: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    refs = source_state_refs_from_paths(LATEST_PATHS)
    structure = payloads.get("market_structure", {}) or {}
    events: list[dict[str, Any]] = []
    tf_payloads = [(tf, payload) for tf, payload in structure.items() if isinstance(payload, dict) and tf in TF_ORDER]
    tf_payloads.sort(key=lambda item: TF_ORDER.get(item[0], 999))
    for tf, payload in tf_payloads:
        high = safe_float(payload.get("last_swing_high"))
        low = safe_float(payload.get("last_swing_low"))
        label = str(payload.get("structure_label") or "").upper()
        trend = str(payload.get("trend_state") or "").upper()
        if high is not None:
            events.append(_event("HH" if "HH" in label else "RANGE_HIGH", tf, "LONG", high, payloads, refs, "market_structure", ["SWING_HIGH_OBSERVED"], invalidation_level=low))
        else:
            events.append(_event("RANGE_HIGH", tf, "LONG", None, payloads, refs, "market_structure", ["STRUCTURE_SOURCE_INSUFFICIENT"]))
        if low is not None:
            events.append(_event("LL" if "LL" in label else "RANGE_LOW", tf, "SHORT", low, payloads, refs, "market_structure", ["SWING_LOW_OBSERVED"], invalidation_level=high))
        if "EQH" in label and high is not None:
            events.append(_event("EQH", tf, "SHORT", high, payloads, refs, "market_structure", ["EQH_ZONE_DETECTED"], invalidation_level=low))
        if "EQL" in label and low is not None:
            events.append(_event("EQL", tf, "LONG", low, payloads, refs, "market_structure", ["EQL_ZONE_DETECTED"], invalidation_level=high))
        if payload.get("bos_detected"):
            events.append(_event("BOS_BULLISH" if trend in {"BULLISH", "TREND"} else "BOS_BEARISH", tf, "LONG" if trend in {"BULLISH", "TREND"} else "SHORT", high if trend in {"BULLISH", "TREND"} else low, payloads, refs, "market_structure", ["BOS_SOURCE_TRUE"], invalidation_level=low if trend in {"BULLISH", "TREND"} else high))
        if payload.get("choch_detected"):
            events.append(_event("CHOCH_BULLISH" if trend in {"BULLISH", "TREND"} else "CHOCH_BEARISH", tf, "LONG" if trend in {"BULLISH", "TREND"} else "SHORT", high if trend in {"BULLISH", "TREND"} else low, payloads, refs, "market_structure", ["CHOCH_SOURCE_TRUE"], invalidation_level=low if trend in {"BULLISH", "TREND"} else high))
        if payload.get("mss_detected"):
            events.append(_event("DISPLACEMENT_AFTER_BREAK", tf, "LONG" if trend in {"BULLISH", "TREND"} else "SHORT", high if trend in {"BULLISH", "TREND"} else low, payloads, refs, "market_structure", ["MSS_SOURCE_TRUE"], invalidation_level=low if trend in {"BULLISH", "TREND"} else high))
    text = _text(payloads.get("interpretation", {}), payloads.get("three_scenarios", {}), payloads.get("liquidity_map", {}))
    if "FAILED_BREAKOUT" in text or "NO ACCEPTED DIRECTIONAL BREAK" in text:
        price = _current_price(payloads)
        events.append(_event("FAKE_BREAKOUT_HIGH", "15m", "SHORT", price, payloads, refs, "interpretation+three_scenarios", ["FAILED_BREAKOUT_INTERPRETATION"]))
        events.append(_event("FAKE_BREAKOUT_LOW", "15m", "LONG", price, payloads, refs, "interpretation+three_scenarios", ["FAILED_BREAKOUT_INTERPRETATION"]))
    if "SWEEP" in text:
        price = _current_price(payloads)
        events.append(_event("LIQUIDITY_SWEEP_HIGH", "5m", "SHORT", price, payloads, refs, "liquidity_map+interpretation", ["SWEEP_CONTEXT_DETECTED"]))
        events.append(_event("LIQUIDITY_SWEEP_LOW", "5m", "LONG", price, payloads, refs, "liquidity_map+interpretation", ["SWEEP_CONTEXT_DETECTED"]))
    if "RECLAIM" in text or "RECLAIMED" in text:
        events.append(_event("RECLAIM_AFTER_SWEEP", "5m", "LONG", _current_price(payloads), payloads, refs, "interpretation+three_scenarios", ["RECLAIM_CONTEXT_DETECTED"]))
    if not events:
        events.append(_event("RANGE_HIGH", "UNKNOWN", "NEUTRAL", None, payloads, refs, "market_structure", ["STRUCTURE_SOURCE_INSUFFICIENT"]))
    history = history_rows or {}
    range_quality = _range_quality(payloads, history.get("market_structure_history", []))
    htf_decision_zones = []
    for tf in ("1h", "4h"):
        tf_payload = structure.get(tf) or {}
        level = safe_float(tf_payload.get("last_swing_high") or tf_payload.get("last_swing_low"))
        decision_type = "HTF_DECISION_HIGH" if safe_float(tf_payload.get("last_swing_high")) is not None else "HTF_DECISION_LOW"
        event = _event(decision_type, tf, "LONG" if decision_type.endswith("LOW") else "SHORT", level, payloads, refs, "market_structure+volume_profile+zone_context", ["HTF_DECISION_ZONE_QUALITY"])
        htf_decision_zones.append(
            {
                "htf_timeframe": tf,
                "decision_level": level,
                "structure_type": decision_type,
                "directional_bias": event.get("direction"),
                "confidence": event.get("confidence"),
                "liquidity_nearby": event.get("relation_to_liquidity"),
                "volume_profile_relation": event.get("relation_to_volume_profile"),
                "zone_relation": event.get("relation_to_zone"),
                "last_reaction": event.get("follow_through_quality"),
                "invalidation_level": event.get("invalidation_level"),
                "tp_association_if_available": None,
                "sl_association_if_available": None,
                "quality_band": event.get("quality_band"),
                "structure_id": event.get("structure_id"),
            }
        )
        events.append(event)
    combos = _combo_labels(events, payloads, range_quality)
    high_confidence_count = sum(1 for event in events if event.get("quality_band") == "HIGH_CONFIDENCE")
    diagnostic_count = sum(1 for event in events if event.get("quality_band") == "DIAGNOSTIC_ONLY")
    quality_counter = Counter(event.get("quality_band") for event in events)
    return {
        "structure_events": events,
        "range_quality": range_quality,
        "htf_decision_zones": htf_decision_zones,
        "structure_liquidity_zone_combos": combos,
        "summary": {
            "structure_event_count": len(events),
            "high_confidence_count": high_confidence_count,
            "diagnostic_count": diagnostic_count,
            "range_quality": range_quality.get("range_quality_band"),
            "htf_decision_quality": htf_decision_zones[0].get("quality_band") if htf_decision_zones else "DIAGNOSTIC_ONLY",
            "quality_band_distribution": dict(quality_counter),
        },
        "source_state_refs": refs,
    }


def _attach_to_unified_context(output: dict[str, Any]) -> None:
    path = LATEST_PATHS["unified_context"]
    unified = load_json(path) or {}
    if not unified:
        return
    enriched = dict(unified)
    enriched["structure_quality"] = {
        "timestamp_utc": output.get("timestamp_utc"),
        "block_id": output.get("block_id"),
        "summary": output.get("summary") or {},
        "structure_events": output.get("structure_events") or [],
        "range_quality": output.get("range_quality") or {},
        "htf_decision_zones": output.get("htf_decision_zones") or [],
        "structure_liquidity_zone_combos": output.get("structure_liquidity_zone_combos") or [],
        "passive_mode": True,
    }
    write_json_atomic(path, enriched)


def _write_report(output: dict[str, Any]) -> None:
    lines = [
        "# NURNOVA Structure Quality Report",
        "",
        f"- Structure events: {len(output.get('structure_events') or [])}",
        f"- Range quality: {json.dumps(output.get('range_quality') or {}, ensure_ascii=False)}",
        f"- HTF decision zones: {json.dumps(output.get('htf_decision_zones') or [], ensure_ascii=False)}",
        f"- High confidence events: {sum(1 for event in output.get('structure_events') or [] if event.get('quality_band') == 'HIGH_CONFIDENCE')}",
        f"- Diagnostic-only events: {sum(1 for event in output.get('structure_events') or [] if event.get('quality_band') == 'DIAGNOSTIC_ONLY')}",
        f"- Structure/liquidity/zone combos: {json.dumps(output.get('structure_liquidity_zone_combos') or [], ensure_ascii=False)}",
        "- Limitations: passive structure research only; no trade gating changes.",
        f"- Structure source mode: {'exact/engine-backed' if not any(event.get('approximation_level') == 'DIAGNOSTIC' for event in output.get('structure_events') or []) else 'contains diagnostic approximation'}",
        "",
        "## Active Structure Events",
    ]
    for event in (output.get("structure_events") or [])[:40]:
        lines.append(
            f"- {event.get('structure_type')} | tf={event.get('timeframe')} | level={event.get('level_price')} | "
            f"band={event.get('quality_band')} | score={event.get('quality_score')} | fakeout={event.get('fakeout_risk')}"
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_structure_quality_engine(max_history: int = MAX_HISTORY) -> dict[str, Any]:
    context = current_runtime_context()
    payloads = {name: load_json(path) or {} for name, path in LATEST_PATHS.items()}
    history_rows = {name: read_jsonl_tail_objects(path, max_lines=max_history) for name, path in HISTORY_PATHS.items()}
    built = build_structure_quality_from_payloads(payloads, history_rows)
    output = stamp_payload(
        {
            "summary": built["summary"],
            "structure_events": built["structure_events"],
            "range_quality": built["range_quality"],
            "htf_decision_zones": built["htf_decision_zones"],
            "structure_liquidity_zone_combos": built["structure_liquidity_zone_combos"],
            "source": {"source_mode": "PASSIVE_STRUCTURE_QUALITY_LAYER"},
            "data_quality": {
                "level": "HIGH" if any(payloads.values()) else "LOW",
                "missing_inputs": [name for name, payload in payloads.items() if not payload],
                "history_rows": {name: len(rows) for name, rows in history_rows.items()},
            },
            "source_state_refs": built["source_state_refs"],
            "reason_codes": ["PASSIVE_STRUCTURE_QUALITY_ONLY", "NO_TRADE_DECISION_CHANGE", "NO_PRIVATE_API", "NO_LIVE_EXECUTION"],
            "feeds_next": FEEDS_NEXT,
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str((payloads.get("unified_context", {}) or {}).get("symbol") or "BTCUSDT"),
        context,
    )
    write_json_atomic(OUTPUT_PATH, output)
    write_json_atomic(EPOCH_OUTPUT_PATH, output)
    append_jsonl_stream(OUTPUT_HISTORY, output)
    append_jsonl_stream(EPOCH_HISTORY_PATH, output)
    _attach_to_unified_context(output)
    _write_report(output)
    return output


def main() -> None:
    print(json.dumps(run_structure_quality_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
