from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, source_state_refs_from_paths, stamp_payload

BLOCK_ID = "ZONE_CONTEXT_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORT_PATH = Path("reports/simple/epoch_v2/latest_zone_context_report.md")

LATEST_PATHS = {
    "market_truth": STATE_DIR / "latest_market_truth.json",
    "one_s_evidence": STATE_DIR / "latest_1s_evidence.json",
    "hybrid_candle_dna": STATE_DIR / "latest_hybrid_candle_dna.json",
    "mtf_candle_dna": STATE_DIR / "latest_mtf_candle_dna.json",
    "market_structure": STATE_DIR / "latest_market_structure.json",
    "liquidity_map": STATE_DIR / "latest_liquidity_map.json",
    "interpretation": STATE_DIR / "latest_interpretation.json",
    "business_zone": STATE_DIR / "latest_business_zone.json",
    "market_regime": STATE_DIR / "latest_market_regime.json",
    "intent_analysis": STATE_DIR / "latest_intent_analysis.json",
    "depth_liquidity_memory": STATE_DIR / "latest_depth_liquidity_memory.json",
    "wall_lifecycle": STATE_DIR / "latest_wall_lifecycle.json",
    "unified_context": STATE_DIR / "latest_unified_context.json",
    "atr_state": STATE_DIR / "latest_atr_state.json",
    "three_scenarios": STATE_DIR / "latest_three_scenarios.json",
    "flow_evidence": STATE_DIR / "latest_flow_evidence.json",
    "flow_persistence": STATE_DIR / "latest_flow_persistence.json",
    "volume_profile": STATE_DIR / "latest_volume_profile.json",
    "structure_quality": STATE_DIR / "latest_structure_quality.json",
}

OUTPUT_PATH = STATE_DIR / "latest_zone_context.json"
EPOCH_OUTPUT_PATH = epoch_state_path("latest_zone_context.json")
HISTORY_PATH = DATA_DIR / "zone_context_history.jsonl"
EPOCH_HISTORY_PATH = epoch_data_path("zone_context_history.jsonl")

ZONE_MEANINGS = {
    "DISCOUNT_ZONE": "Cheap zone, lower 0-50% of active range.",
    "PREMIUM_ZONE": "Expensive zone, upper 50-100% of active range.",
    "EQUILIBRIUM_ZONE": "Middle of active range.",
    "APPROX_HVN_ZONE": "Approximate high volume acceptance area.",
    "APPROX_LVN_ZONE": "Approximate low volume rejection area.",
    "APPROX_POC_ZONE": "Approximate most interacted/highest activity price.",
    "APPROX_NAKED_POC_ZONE": "Approximate POC with unknown or unrevisited status.",
    "REAL_POC_ZONE": "Real point of control from measurable volume profile.",
    "REAL_HVN_ZONE": "Real high-volume node from measurable volume profile.",
    "REAL_LVN_ZONE": "Real low-volume node from measurable volume profile.",
    "VALUE_AREA_HIGH_ZONE": "Upper boundary of the measured value area.",
    "VALUE_AREA_LOW_ZONE": "Lower boundary of the measured value area.",
    "VALUE_AREA_MID_ZONE": "Midpoint of the measured value area.",
    "NAKED_POC_ZONE": "Measured point of control not yet revisited or revisit-tracked.",
    "LIQUIDITY_POOL_ZONE": "Stop cluster or resting liquidity concentration.",
    "SWEEP_ZONE": "Area where liquidity sweep happened with confirmation evidence.",
    "SWEEP_RISK_ZONE": "Area where sweep risk exists without confirmation.",
    "ABSORPTION_ZONE": "Aggressive flow absorbed by passive liquidity.",
    "RECLAIM_ZONE": "Liquidity or structure level reclaimed after sweep or break.",
    "BREAKOUT_FAILURE_ZONE": "Failed breakout or fake breakout area.",
    "VOLATILITY_EXPANSION_ZONE": "Impulsive volatility expansion area.",
    "COMPRESSION_ZONE": "Range compression or volatility squeeze area.",
    "ICEBERG_ZONE": "Hidden absorption or iceberg-like behavior.",
    "EXHAUSTION_ZONE": "Trend exhaustion area.",
    "APPROX_IMBALANCE_FVG_ZONE": "Approximate inefficiency/FVG-like area.",
    "MEAN_REVERSION_ZONE": "Area with reversion tendency.",
    "SESSION_OPEN_ZONE": "UTC session open liquidity context.",
    "HTF_DECISION_ZONE": "1H/4H structure decision area.",
    "DIAGNOSTIC_ZONE": "Diagnostic zone placeholder when source data is insufficient.",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_utc_session(timestamp_utc: Any) -> str:
    try:
        dt = datetime.fromisoformat(str(timestamp_utc).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    hour = dt.hour
    if 12 <= hour < 16:
        return "OVERLAP"
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 12:
        return "LONDON"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "OFF_SESSION"


def _zone_id(zone_type: str, source_layer: str, low: Any, high: Any, reason_codes: list[str]) -> str:
    raw = f"{zone_type}|{source_layer}|{low}|{high}|{','.join(reason_codes)}"
    return "ZONE_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16].upper()


def _clamp01(value: Any) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    return round(max(0.0, min(1.0, number)), 4)


def _zone(
    zone_type: str,
    source_layer: str,
    *,
    price_low: Any = None,
    price_high: Any = None,
    mid_price: Any = None,
    timeframe: str = "UNKNOWN",
    directional_bias: str = "NEUTRAL",
    strength: Any = None,
    confidence: Any = None,
    status: str = "UNKNOWN",
    formed_at_utc: Any = None,
    last_seen_at_utc: Any = None,
    approximation_level: str = "DIAGNOSTIC",
    source_state_refs: dict[str, Any] | None = None,
    reason_codes: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    low = safe_float(price_low)
    high = safe_float(price_high)
    mid = safe_float(mid_price)
    if mid is None and low is not None and high is not None:
        mid = round((low + high) / 2.0, 8)
    if low is None and mid is not None:
        low = mid
    if high is None and mid is not None:
        high = mid
    reasons = [str(item) for item in (reason_codes or []) if item]
    if approximation_level == "DIAGNOSTIC" and "ZONE_SOURCE_INSUFFICIENT" not in reasons:
        reasons.append("ZONE_SOURCE_INSUFFICIENT")
    zone = {
        "zone_id": _zone_id(zone_type, source_layer, low, high, reasons),
        "zone_type": zone_type,
        "zone_meaning": ZONE_MEANINGS.get(zone_type, "Queryable market context zone."),
        "source_layer": source_layer,
        "price_low": round(low, 8) if low is not None else None,
        "price_high": round(high, 8) if high is not None else None,
        "mid_price": round(mid, 8) if mid is not None else None,
        "timeframe": timeframe,
        "directional_bias": str(directional_bias or "NEUTRAL").upper(),
        "strength": _clamp01(strength),
        "confidence": _clamp01(confidence),
        "status": status if status in {"ACTIVE", "REVISITED", "BROKEN", "RECLAIMED", "EXPIRED", "UNKNOWN"} else "UNKNOWN",
        "formed_at_utc": str(formed_at_utc or ""),
        "last_seen_at_utc": str(last_seen_at_utc or ""),
        "approximation_level": approximation_level if approximation_level in {"EXACT", "APPROX", "DIAGNOSTIC"} else "DIAGNOSTIC",
        "source_state_refs": source_state_refs or {},
        "reason_codes": sorted(set(reasons)),
    }
    if extra:
        zone.update(extra)
    return zone


def _json_text(*payloads: dict[str, Any]) -> str:
    return json.dumps(payloads, ensure_ascii=False).upper()


def _first_number(payload: Any, names: set[str]) -> float | None:
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                lowered = str(key).lower()
                if lowered in names:
                    number = safe_float(value)
                    if number is not None:
                        return number
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return None


def _all_named_numbers(payload: Any, names: set[str]) -> list[tuple[str, float, dict[str, Any]]]:
    found: list[tuple[str, float, dict[str, Any]]] = []
    stack: list[tuple[Any, dict[str, Any]]] = [(payload, {})]
    while stack:
        item, parent = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                lowered = str(key).lower()
                number = safe_float(value)
                if lowered in names and number is not None:
                    found.append((lowered, number, item))
                if isinstance(value, (dict, list)):
                    stack.append((value, item))
        elif isinstance(item, list):
            for child in item:
                stack.append((child, parent))
    return found


def _timestamp(payloads: dict[str, dict[str, Any]]) -> str:
    for payload in payloads.values():
        if payload.get("timestamp_utc"):
            return str(payload["timestamp_utc"])
    return _utc_now()


def _current_price(payloads: dict[str, dict[str, Any]]) -> float | None:
    return (
        _first_number(payloads.get("unified_context", {}), {"current_price", "price", "last_price"})
        or _first_number(payloads.get("market_truth", {}), {"current_price", "price", "last_price"})
        or _first_number(payloads.get("mtf_candle_dna", {}), {"close"})
    )


def _range(payloads: dict[str, dict[str, Any]]) -> tuple[float | None, float | None, str]:
    low_names = {"range_low", "structure_low", "swing_low", "low", "value_area_low", "val"}
    high_names = {"range_high", "structure_high", "swing_high", "high", "value_area_high", "vah"}
    for source in ("market_structure", "business_zone", "unified_context"):
        payload = payloads.get(source, {})
        low = _first_number(payload, low_names)
        high = _first_number(payload, high_names)
        if low is not None and high is not None and high > low:
            return low, high, source
    return None, None, "NONE"


def classify_range_zones(payloads: dict[str, dict[str, Any]], refs: dict[str, Any]) -> list[dict[str, Any]]:
    now = _timestamp(payloads)
    current = _current_price(payloads)
    low, high, source = _range(payloads)
    if low is None or high is None or current is None:
        return [
            _zone(
                "DIAGNOSTIC_ZONE",
                "market_structure+business_zone+unified_context",
                formed_at_utc=now,
                last_seen_at_utc=now,
                source_state_refs=refs,
                reason_codes=["RANGE_OR_CURRENT_PRICE_UNAVAILABLE", "ZONE_SOURCE_INSUFFICIENT"],
                extra={"intended_zone_types": ["DISCOUNT_ZONE", "PREMIUM_ZONE", "EQUILIBRIUM_ZONE"]},
            )
        ]
    equilibrium = round((high + low) / 2.0, 8)
    position = round((current - low) / (high - low), 4)
    base = {
        "price_low": low,
        "price_high": high,
        "mid_price": current,
        "timeframe": "ACTIVE_RANGE",
        "formed_at_utc": now,
        "last_seen_at_utc": now,
        "approximation_level": "APPROX",
        "confidence": 0.6,
        "source_state_refs": refs,
        "extra": {"range_low": low, "range_high": high, "equilibrium_price": equilibrium, "price_position_pct": position},
    }
    zones: list[dict[str, Any]] = []
    if current < equilibrium:
        zones.append(_zone("DISCOUNT_ZONE", source, directional_bias="LONG", status="ACTIVE", reason_codes=["CURRENT_PRICE_BELOW_EQUILIBRIUM"], **base))
    elif current > equilibrium:
        zones.append(_zone("PREMIUM_ZONE", source, directional_bias="SHORT", status="ACTIVE", reason_codes=["CURRENT_PRICE_ABOVE_EQUILIBRIUM"], **base))
    else:
        zones.append(_zone("EQUILIBRIUM_ZONE", source, status="ACTIVE", approximation_level="EXACT", confidence=1.0, reason_codes=["CURRENT_PRICE_EQUALS_EQUILIBRIUM"], **{k: v for k, v in base.items() if k not in {"approximation_level", "confidence"}}))
    text = _json_text(payloads.get("market_structure", {}), payloads.get("business_zone", {}))
    if any(token in text for token in ("EQUILIBRIUM", "MIDPOINT", "MID_RANGE", "FAIR_VALUE")):
        zones.append(_zone("EQUILIBRIUM_ZONE", source, price_low=equilibrium, price_high=equilibrium, mid_price=equilibrium, timeframe="ACTIVE_RANGE", status="ACTIVE", approximation_level="APPROX", confidence=0.5, formed_at_utc=now, last_seen_at_utc=now, source_state_refs=refs, reason_codes=["SOURCE_DESCRIBES_EQUILIBRIUM_PROXIMITY"], extra={"range_low": low, "range_high": high, "equilibrium_price": equilibrium, "price_position_pct": position}))
    return zones


def classify_profile_zones(payloads: dict[str, dict[str, Any]], refs: dict[str, Any]) -> list[dict[str, Any]]:
    now = _timestamp(payloads)
    volume_profile = payloads.get("volume_profile", {})
    if str(volume_profile.get("profile_status") or "").upper() == "OK":
        zones: list[dict[str, Any]] = []
        for window, profile in (volume_profile.get("windows") or {}).items():
            if not isinstance(profile, dict):
                continue
            poc = profile.get("poc") or {}
            if isinstance(poc, dict) and poc.get("mid_price") is not None:
                zones.append(
                    _zone(
                        "REAL_POC_ZONE",
                        "latest_volume_profile",
                        price_low=poc.get("price_low"),
                        price_high=poc.get("price_high"),
                        mid_price=poc.get("mid_price"),
                        timeframe=window,
                        directional_bias="NEUTRAL",
                        strength=poc.get("volume_share"),
                        confidence=poc.get("confidence") or 0.9,
                        status=poc.get("status") or "ACTIVE",
                        formed_at_utc=now,
                        last_seen_at_utc=now,
                        approximation_level="EXACT",
                        source_state_refs=refs,
                        reason_codes=["REAL_VOLUME_PROFILE_POC"],
                        extra={"window": window, "volume": poc.get("volume"), "volume_share": poc.get("volume_share")},
                    )
                )
            for item in profile.get("hvn_zones") or []:
                if isinstance(item, dict):
                    zones.append(
                        _zone(
                            "REAL_HVN_ZONE",
                            "latest_volume_profile",
                            price_low=item.get("price_low"),
                            price_high=item.get("price_high"),
                            mid_price=item.get("mid_price"),
                            timeframe=window,
                            directional_bias="NEUTRAL",
                            strength=item.get("volume_share"),
                            confidence=item.get("confidence") or 0.85,
                            status=item.get("status") or "ACTIVE",
                            formed_at_utc=now,
                            last_seen_at_utc=now,
                            approximation_level="EXACT",
                            source_state_refs=refs,
                            reason_codes=["REAL_VOLUME_PROFILE_HVN"],
                            extra={"window": window, "volume": item.get("volume"), "volume_share": item.get("volume_share")},
                        )
                    )
            for item in profile.get("lvn_zones") or []:
                if isinstance(item, dict):
                    zones.append(
                        _zone(
                            "REAL_LVN_ZONE",
                            "latest_volume_profile",
                            price_low=item.get("price_low"),
                            price_high=item.get("price_high"),
                            mid_price=item.get("mid_price"),
                            timeframe=window,
                            directional_bias="NEUTRAL",
                            strength=item.get("volume_share"),
                            confidence=item.get("confidence") or 0.75,
                            status=item.get("status") or "ACTIVE",
                            formed_at_utc=now,
                            last_seen_at_utc=now,
                            approximation_level="EXACT",
                            source_state_refs=refs,
                            reason_codes=["REAL_VOLUME_PROFILE_LVN"],
                            extra={"window": window, "volume": item.get("volume"), "volume_share": item.get("volume_share")},
                        )
                    )
            vah = safe_float(profile.get("vah"))
            val = safe_float(profile.get("val"))
            vamid = safe_float(profile.get("vamid"))
            if vah is not None:
                zones.append(
                    _zone(
                        "VALUE_AREA_HIGH_ZONE",
                        "latest_volume_profile",
                        mid_price=vah,
                        timeframe=window,
                        confidence=0.85,
                        status="ACTIVE",
                        formed_at_utc=now,
                        last_seen_at_utc=now,
                        approximation_level="EXACT",
                        source_state_refs=refs,
                        reason_codes=["REAL_VOLUME_PROFILE_VAH"],
                        extra={"window": window},
                    )
                )
            if val is not None:
                zones.append(
                    _zone(
                        "VALUE_AREA_LOW_ZONE",
                        "latest_volume_profile",
                        mid_price=val,
                        timeframe=window,
                        confidence=0.85,
                        status="ACTIVE",
                        formed_at_utc=now,
                        last_seen_at_utc=now,
                        approximation_level="EXACT",
                        source_state_refs=refs,
                        reason_codes=["REAL_VOLUME_PROFILE_VAL"],
                        extra={"window": window},
                    )
                )
            if vamid is not None:
                zones.append(
                    _zone(
                        "VALUE_AREA_MID_ZONE",
                        "latest_volume_profile",
                        mid_price=vamid,
                        timeframe=window,
                        confidence=0.8,
                        status="ACTIVE",
                        formed_at_utc=now,
                        last_seen_at_utc=now,
                        approximation_level="EXACT",
                        source_state_refs=refs,
                        reason_codes=["REAL_VOLUME_PROFILE_VAMID"],
                        extra={"window": window},
                    )
                )
            for item in profile.get("naked_pocs") or []:
                if isinstance(item, dict):
                    zones.append(
                        _zone(
                            "NAKED_POC_ZONE",
                            "latest_volume_profile",
                            price_low=item.get("price_low"),
                            price_high=item.get("price_high"),
                            mid_price=item.get("mid_price"),
                            timeframe=window,
                            confidence=item.get("confidence") or 0.75,
                            status=item.get("status") or "UNKNOWN",
                            formed_at_utc=now,
                            last_seen_at_utc=now,
                            approximation_level="EXACT",
                            source_state_refs=refs,
                            reason_codes=list(item.get("reason_codes") or ["REAL_VOLUME_PROFILE_NAKED_POC"]),
                            extra={"window": window, "volume": item.get("volume"), "volume_share": item.get("volume_share")},
                        )
                    )
        if zones:
            return zones
    business = payloads.get("business_zone", {})
    text = _json_text(business)
    zones: list[dict[str, Any]] = []
    profile_exact = any(token in text for token in ("TRUE_VOLUME_PROFILE", "TPO_PROFILE", "EXACT_POC"))
    prefix_level = "EXACT" if profile_exact else "APPROX"
    type_prefix = "" if profile_exact else "APPROX_"
    mapping = [
        ("hvn", f"{type_prefix}HVN_ZONE", {"hvn", "high_volume_node", "acceptance_price", "acceptance_mid"}),
        ("lvn", f"{type_prefix}LVN_ZONE", {"lvn", "low_volume_node", "rejection_price", "rejection_mid"}),
        ("poc", f"{type_prefix}POC_ZONE", {"poc", "point_of_control", "highest_activity_price"}),
    ]
    for label, zone_type, keys in mapping:
        for key, price, parent in _all_named_numbers(business, keys):
            zones.append(
                _zone(
                    zone_type,
                    "latest_business_zone",
                    mid_price=price,
                    timeframe=str(parent.get("timeframe") or "UNKNOWN"),
                    directional_bias=str(parent.get("directional_bias") or "NEUTRAL"),
                    strength=parent.get("volume_score") or parent.get("acceptance_score") or parent.get("strength"),
                    confidence=parent.get("confidence") or (0.7 if profile_exact else 0.45),
                    status=str(parent.get("status") or "ACTIVE").upper(),
                    formed_at_utc=parent.get("formed_at_utc") or now,
                    last_seen_at_utc=parent.get("last_seen_at_utc") or now,
                    approximation_level=prefix_level,
                    source_state_refs=refs,
                    reason_codes=[f"{label.upper()}_SOURCE_FIELD_{key.upper()}", "APPROX_PROFILE_ZONE" if not profile_exact else "EXACT_PROFILE_ZONE"],
                    extra={"volume_score": parent.get("volume_score"), "acceptance_score": parent.get("acceptance_score")},
                )
            )
    poc_price = _first_number(business, {"poc", "point_of_control", "highest_activity_price"})
    if poc_price is not None:
        zones.append(
            _zone(
                "APPROX_NAKED_POC_ZONE" if not profile_exact else "NAKED_POC_ZONE",
                "business_zone_history+market_truth_history",
                mid_price=poc_price,
                status="UNKNOWN",
                formed_at_utc=now,
                last_seen_at_utc=now,
                approximation_level="DIAGNOSTIC" if not profile_exact else "APPROX",
                source_state_refs=refs,
                reason_codes=["NAKED_POC_REVISIT_STATUS_UNKNOWN", *([] if profile_exact else ["ZONE_SOURCE_INSUFFICIENT"])],
            )
        )
    return zones


def classify_liquidity_zones(payloads: dict[str, dict[str, Any]], refs: dict[str, Any]) -> list[dict[str, Any]]:
    now = _timestamp(payloads)
    zones: list[dict[str, Any]] = []
    for source in ("liquidity_map", "depth_liquidity_memory", "wall_lifecycle"):
        payload = payloads.get(source, {})
        for key, price, parent in _all_named_numbers(payload, {"price", "level_price", "wall_price", "liquidity_price", "equal_high", "equal_low", "swing_high", "swing_low"}):
            zones.append(
                _zone(
                    "LIQUIDITY_POOL_ZONE",
                    f"latest_{source}",
                    mid_price=price,
                    timeframe=str(parent.get("timeframe") or "UNKNOWN"),
                    directional_bias=str(parent.get("side") or parent.get("directional_bias") or "NEUTRAL"),
                    strength=parent.get("strength") or parent.get("score") or parent.get("size_score"),
                    confidence=parent.get("confidence") or 0.5,
                    status=str(parent.get("status") or "ACTIVE").upper(),
                    formed_at_utc=parent.get("formed_at_utc") or now,
                    last_seen_at_utc=parent.get("last_seen_at_utc") or now,
                    approximation_level="APPROX",
                    source_state_refs=refs,
                    reason_codes=[f"LIQUIDITY_SOURCE_{key.upper()}"],
                )
            )
    return zones


def classify_event_zones(payloads: dict[str, dict[str, Any]], refs: dict[str, Any]) -> list[dict[str, Any]]:
    now = _timestamp(payloads)
    current = _current_price(payloads)
    text = _json_text(*payloads.values())
    zones: list[dict[str, Any]] = []
    event_specs = [
        ("ABSORPTION_ZONE", ("ABSORPTION",), "flow_evidence+interpretation", {"absorbed_side": "UNKNOWN", "aggressive_side": "UNKNOWN", "absorption_strength": None, "price_response": "UNKNOWN"}),
        ("RECLAIM_ZONE", ("RECLAIM", "RECLAIMED"), "market_structure+interpretation+three_scenarios", {}),
        ("BREAKOUT_FAILURE_ZONE", ("FAILED_BREAKOUT", "FAKE_BREAKOUT", "NO_FOLLOW_THROUGH"), "market_structure+interpretation+three_scenarios", {}),
        ("VOLATILITY_EXPANSION_ZONE", ("ATR_EXPANDING", "VOLATILITY_EXPANSION", "DISPLACEMENT"), "atr_state+mtf_candle_dna+interpretation", {}),
        ("COMPRESSION_ZONE", ("COMPRESSION", "SQUEEZE", "ATR_FALLING", "RANGE_NARROWING"), "atr_state+mtf_candle_dna+market_structure", {}),
        ("ICEBERG_ZONE", ("ICEBERG", "HIDDEN_ABSORPTION"), "intent_analysis+observation_factory+depth_liquidity_memory", {}),
        ("EXHAUSTION_ZONE", ("EXHAUSTION", "DECAY", "FLIP_RISK"), "interpretation+flow_persistence+mtf_candle_dna", {}),
        ("APPROX_IMBALANCE_FVG_ZONE", ("FVG", "IMBALANCE", "LOW_OVERLAP"), "mtf_candle_dna+market_structure+interpretation", {}),
        ("MEAN_REVERSION_ZONE", ("MEAN_REVERSION", "REVERT", "VALUE_AREA", "POC"), "business_zone+market_regime+interpretation", {}),
        ("HTF_DECISION_ZONE", ("1H", "4H", "HTF", "BOS", "CHOCH"), "market_structure+liquidity_map+business_zone", {}),
    ]
    if "SWEEP" in text:
        confirmed = any(token in text for token in ("REJECTION", "REVERSAL", "WICK", "RECLAIM"))
        zones.append(
            _zone(
                "SWEEP_ZONE" if confirmed else "SWEEP_RISK_ZONE",
                "liquidity_map+interpretation+market_structure",
                mid_price=current,
                status="ACTIVE" if confirmed else "UNKNOWN",
                formed_at_utc=now,
                last_seen_at_utc=now,
                approximation_level="APPROX" if confirmed and current is not None else "DIAGNOSTIC",
                source_state_refs=refs,
                reason_codes=["SWEEP_CONFIRMATION_EVIDENCE" if confirmed else "SWEEP_RISK_ONLY"],
            )
        )
    for zone_type, tokens, source_layer, extra in event_specs:
        if any(token in text for token in tokens):
            zones.append(
                _zone(
                    zone_type,
                    source_layer,
                    mid_price=current,
                    status="ACTIVE" if current is not None else "UNKNOWN",
                    formed_at_utc=now,
                    last_seen_at_utc=now,
                    approximation_level="APPROX" if current is not None else "DIAGNOSTIC",
                    source_state_refs=refs,
                    reason_codes=[f"{zone_type}_SOURCE_TEXT_MATCH"],
                    extra=extra,
                )
            )
    zones.append(
        _zone(
            "SESSION_OPEN_ZONE",
            "timestamp_utc+market_truth",
            mid_price=current,
            timeframe=classify_utc_session(now),
            status="ACTIVE" if current is not None else "UNKNOWN",
            formed_at_utc=now,
            last_seen_at_utc=now,
            approximation_level="APPROX" if current is not None else "DIAGNOSTIC",
            source_state_refs=refs,
            reason_codes=["UTC_SESSION_CLASSIFIER"],
            extra={"session": classify_utc_session(now)},
        )
    )
    return zones


def _structure_quality_metadata(payloads: dict[str, dict[str, Any]], zone_type: str) -> dict[str, Any] | None:
    structure_quality = payloads.get("structure_quality", {}) or {}
    mappings = {
        "HTF_DECISION_ZONE": {"HTF_DECISION_HIGH", "HTF_DECISION_LOW"},
        "BREAKOUT_FAILURE_ZONE": {"FAKE_BREAKOUT_HIGH", "FAKE_BREAKOUT_LOW"},
        "RECLAIM_ZONE": {"RECLAIM_AFTER_SWEEP"},
        "SWEEP_ZONE": {"LIQUIDITY_SWEEP_HIGH", "LIQUIDITY_SWEEP_LOW"},
        "COMPRESSION_ZONE": {"DISPLACEMENT_AFTER_BREAK", "RANGE_HIGH", "RANGE_LOW"},
    }
    targets = mappings.get(zone_type)
    if not targets:
        return None
    matches = [event for event in structure_quality.get("structure_events") or [] if isinstance(event, dict) and str(event.get("structure_type")) in targets]
    if not matches and zone_type == "HTF_DECISION_ZONE":
        matches = [event for event in structure_quality.get("htf_decision_zones") or [] if isinstance(event, dict)]
    if not matches:
        return None
    best = sorted(matches, key=lambda item: (safe_float(item.get("quality_score")) or safe_float(item.get("confidence")) or 0.0), reverse=True)[0]
    return {
        "structure_type": best.get("structure_type"),
        "quality_band": best.get("quality_band"),
        "quality_score": best.get("quality_score"),
        "confidence": best.get("confidence"),
        "fakeout_risk": best.get("fakeout_risk"),
    }


def _enrich_with_structure_quality(zones: list[dict[str, Any]], payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for zone in zones:
        updated = dict(zone)
        metadata = _structure_quality_metadata(payloads, str(zone.get("zone_type") or ""))
        if metadata:
            updated["structure_quality_metadata"] = metadata
            if metadata.get("confidence") is not None and updated.get("confidence") is None:
                updated["confidence"] = metadata.get("confidence")
        enriched.append(updated)
    return enriched


def build_zone_context_from_payloads(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    refs = source_state_refs_from_paths(LATEST_PATHS)
    zones: list[dict[str, Any]] = []
    zones.extend(classify_range_zones(payloads, refs))
    zones.extend(classify_profile_zones(payloads, refs))
    zones.extend(classify_liquidity_zones(payloads, refs))
    zones.extend(classify_event_zones(payloads, refs))
    if not zones:
        now = _timestamp(payloads)
        zones.append(_zone("DIAGNOSTIC_ZONE", "zone_context_inputs", formed_at_utc=now, last_seen_at_utc=now, source_state_refs=refs, reason_codes=["ZONE_SOURCE_INSUFFICIENT"]))
    zones = _enrich_with_structure_quality(zones, payloads)
    dedup = {zone["zone_id"]: zone for zone in zones}
    output_zones = list(dedup.values())
    counts: dict[str, int] = {"EXACT": 0, "APPROX": 0, "DIAGNOSTIC": 0}
    for zone in output_zones:
        counts[str(zone.get("approximation_level") or "DIAGNOSTIC")] = counts.get(str(zone.get("approximation_level") or "DIAGNOSTIC"), 0) + 1
    return {"zones": output_zones, "source_state_refs": refs, "approximation_counts": counts}


def _attach_to_unified_context(zone_context: dict[str, Any]) -> None:
    unified_path = LATEST_PATHS["unified_context"]
    unified = load_json(unified_path) or {}
    if not unified:
        return
    enriched = dict(unified)
    enriched["zone_context"] = {
        "timestamp_utc": zone_context.get("timestamp_utc"),
        "block_id": zone_context.get("block_id"),
        "zones": zone_context.get("zones") or [],
        "summary": zone_context.get("summary") or {},
        "passive_mode": True,
    }
    write_json_atomic(unified_path, enriched)


def _write_report(output: dict[str, Any]) -> None:
    zones = output.get("zones") or []
    counts = (output.get("summary") or {}).get("approximation_counts") or {}
    lines = [
        "# NURNOVA Zone Context Report",
        "",
        f"- Total zones: {len(zones)}",
        f"- Exact zones: {counts.get('EXACT', 0)}",
        f"- Approx zones: {counts.get('APPROX', 0)}",
        f"- Diagnostic zones: {counts.get('DIAGNOSTIC', 0)}",
        "",
        "## Detected Active Zones",
    ]
    for zone in zones[:50]:
        lines.append(
            f"- {zone.get('zone_type')} | {zone.get('source_layer')} | confidence={zone.get('confidence')} | "
            f"approx={zone.get('approximation_level')} | status={zone.get('status')} | meaning={zone.get('zone_meaning')}"
        )
        if "ZONE_SOURCE_INSUFFICIENT" in (zone.get("reason_codes") or []):
            lines.append(f"  - diagnostic: {', '.join(zone.get('reason_codes') or [])}")
    lines += ["", "Passive layer only: zones are query context and do not block or allow trades."]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_zone_engine() -> dict[str, Any]:
    context = current_runtime_context()
    payloads = {name: load_json(path) or {} for name, path in LATEST_PATHS.items()}
    built = build_zone_context_from_payloads(payloads)
    output = stamp_payload(
        {
            "source": {"source_mode": "PASSIVE_PROFESSIONAL_ZONE_CONTEXT"},
            "passive_mode": True,
            "zones": built["zones"],
            "summary": {
                "zone_count": len(built["zones"]),
                "approximation_counts": built["approximation_counts"],
                "passive_measure_only": True,
            },
            "source_state_refs": built["source_state_refs"],
            "data_quality": {
                "level": "HIGH" if any(payloads.values()) else "LOW",
                "missing_inputs": [name for name, payload in payloads.items() if not payload],
            },
            "feeds_next": ["UNIFIED_CONTEXT_ENGINE", "TP_CONDITION_DNA_ENGINE", "EDGE_QUERY_ENGINE", "TELEGRAM_RESEARCH_REPORTER"],
            "reason_codes": ["PASSIVE_ZONE_CONTEXT_ONLY", "NO_TRADE_DECISION_CHANGE", "NO_PRIVATE_API", "NO_LIVE_EXECUTION"],
            "execution_safety": {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        },
        BLOCK_ID,
        str((payloads["unified_context"] or payloads["market_truth"] or {}).get("symbol") or "BTCUSDT"),
        context,
    )
    write_json_atomic(OUTPUT_PATH, output)
    write_json_atomic(EPOCH_OUTPUT_PATH, output)
    append_jsonl_stream(HISTORY_PATH, output)
    append_jsonl_stream(EPOCH_HISTORY_PATH, output)
    _attach_to_unified_context(output)
    _write_report(output)
    return output


def main() -> None:
    print(json.dumps(run_zone_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
