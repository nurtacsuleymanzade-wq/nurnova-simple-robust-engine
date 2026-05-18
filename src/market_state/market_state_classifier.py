from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .market_state_registry import DEFAULT_FEEDS_NEXT, MARKET_STATE_BLOCK_ID


def _canon(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_iso(ts: str) -> str | None:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _collect_strings(payload: Any) -> list[str]:
    out: list[str] = []
    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for v in cur.values():
                stack.append(v)
        elif isinstance(cur, list):
            for v in cur:
                stack.append(v)
        elif isinstance(cur, str):
            out.append(cur.upper())
    return out


def _contains_any(haystack: list[str], needles: tuple[str, ...]) -> bool:
    return any(any(needle in item for needle in needles) for item in haystack)


def _extract_best_timestamp(records: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    best: datetime | None = None
    best_iso: str | None = None
    for rec in records.values():
        ts = _to_iso(str(rec.get("timestamp_utc") or ""))
        if ts is None:
            continue
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if best is None or dt > best:
            best = dt
            best_iso = ts
    if best_iso:
        return best_iso, reasons
    reasons.append("MISSING_TIMESTAMP_EVIDENCE")
    return "1970-01-01T00:00:00Z", reasons


def _extract_trend_state(structure_record: dict[str, Any], reason_codes: list[str]) -> str:
    tokens = _collect_strings(structure_record)
    bullish = _contains_any(tokens, ("UPTREND", "BULLISH", "LONG", "HH", "HL", "HH_HL"))
    bearish = _contains_any(tokens, ("DOWNTREND", "BEARISH", "SHORT", "LH", "LL", "LH_LL"))
    neutral = _contains_any(tokens, ("RANGE", "NEUTRAL", "BALANCE"))
    if bullish and bearish:
        reason_codes.append("TREND_CONFLICT_MIXED")
        return "MIXED"
    if bullish:
        return "BULLISH"
    if bearish:
        return "BEARISH"
    if neutral:
        return "NEUTRAL"
    reason_codes.append("TREND_STATE_UNKNOWN_NO_EVIDENCE")
    return "UNKNOWN"


def _extract_structure_state(structure_record: dict[str, Any], reason_codes: list[str]) -> str:
    tokens = _collect_strings(structure_record)
    if _contains_any(tokens, ("HH_HL", "HH", "HL", "BULLISH_BOS", "TREND_UP")):
        return "HH_HL"
    if _contains_any(tokens, ("LH_LL", "LH", "LL", "BEARISH_BOS", "TREND_DOWN")):
        return "LH_LL"
    if _contains_any(tokens, ("RANGE", "RANGE_BOUND", "BALANCE", "RANGE_SEQUENCE")):
        return "RANGE_BOUND"
    if _contains_any(tokens, ("CHOCH", "MSS", "BROKEN", "BREAK", "REVERSAL")):
        return "BROKEN_STRUCTURE"
    reason_codes.append("STRUCTURE_STATE_UNKNOWN_NO_EVIDENCE")
    return "UNKNOWN"


def _extract_volatility_state(records: dict[str, dict[str, Any]], reason_codes: list[str]) -> str:
    tokens = []
    for name in ("candle_dna", "context", "flow", "lineage_graph"):
        rec = records.get(name) or {}
        tokens.extend(_collect_strings(rec))
    if _contains_any(tokens, ("EXPANDING", "EXPANSION", "ATR_EXPANDING", "HIGH_VOL")):
        return "EXPANDING"
    if _contains_any(tokens, ("COMPRESSING", "COMPRESSION", "ATR_CONTRACTING", "SQUEEZE")):
        return "COMPRESSING"
    if _contains_any(tokens, ("HIGH", "VOLATILITY_HIGH")):
        return "HIGH"
    if _contains_any(tokens, ("LOW", "VOLATILITY_LOW")):
        return "LOW"
    if _contains_any(tokens, ("NORMAL", "MEDIUM")):
        return "NORMAL"
    reason_codes.append("VOLATILITY_UNKNOWN_NO_EVIDENCE")
    return "UNKNOWN"


def _extract_liquidity_pressure_state(liquidity_record: dict[str, Any], reason_codes: list[str]) -> str:
    tokens = _collect_strings(liquidity_record)
    above = _contains_any(tokens, ("ABOVE", "UPSIDE", "PREMIUM", "ASK_WALL", "LIQUIDITY_ABOVE"))
    below = _contains_any(tokens, ("BELOW", "DOWNSIDE", "DISCOUNT", "BID_WALL", "LIQUIDITY_BELOW"))
    both = _contains_any(tokens, ("BOTH", "BALANCED_LIQUIDITY", "TWO_SIDED"))
    if both or (above and below):
        return "BOTH"
    if above:
        return "ABOVE"
    if below:
        return "BELOW"
    if _contains_any(tokens, ("NONE", "NO_LIQUIDITY_SIGNAL")):
        return "NONE"
    reason_codes.append("LIQUIDITY_PRESSURE_UNKNOWN_NO_EVIDENCE")
    return "UNKNOWN"


def _extract_auction_state(records: dict[str, dict[str, Any]], reason_codes: list[str]) -> str:
    tokens = _collect_strings(records.get("context") or {})
    if _contains_any(tokens, ("ACCEPTANCE", "ACCEPTED")):
        return "ACCEPTANCE"
    if _contains_any(tokens, ("REJECTION", "REJECTED")):
        return "REJECTION"
    if _contains_any(tokens, ("DISCOVERY", "PRICE_DISCOVERY")):
        return "DISCOVERY"
    if _contains_any(tokens, ("BALANCE", "INSIDE_VALUE", "RANGE")):
        return "BALANCE"
    reason_codes.append("AUCTION_STATE_UNKNOWN_NO_EVIDENCE")
    return "UNKNOWN"


def _extract_flow_state(records: dict[str, dict[str, Any]], reason_codes: list[str]) -> str:
    tokens = _collect_strings(records.get("flow") or {})
    if _contains_any(tokens, ("DIVERGENT", "DIVERGENCE")):
        return "DIVERGENT"
    if _contains_any(tokens, ("BUY_PRESSURE", "BULLISH", "DOMINANT_BUY", "LONG_PRESSURE")):
        if _contains_any(tokens, ("SELL_PRESSURE", "BEARISH", "DOMINANT_SELL", "SHORT_PRESSURE")):
            return "DIVERGENT"
        return "BUY_PRESSURE"
    if _contains_any(tokens, ("SELL_PRESSURE", "BEARISH", "DOMINANT_SELL", "SHORT_PRESSURE")):
        return "SELL_PRESSURE"
    if _contains_any(tokens, ("BALANCED", "CHOPPY", "NEUTRAL")):
        return "BALANCED"
    reason_codes.append("FLOW_STATE_UNKNOWN_NO_EVIDENCE")
    return "UNKNOWN"


def _extract_maturity_state(
    trend_state: str,
    structure_state: str,
    flow_state: str,
    records: dict[str, dict[str, Any]],
    reason_codes: list[str],
) -> str:
    tokens = _collect_strings(records.get("context") or {})
    if _contains_any(tokens, ("EXHAUSTED", "TERMINAL", "CLIMAX")):
        return "EXHAUSTED"
    if _contains_any(tokens, ("LATE", "LATE_STAGE", "OVEREXTENDED")):
        return "LATE"
    if trend_state in ("BULLISH", "BEARISH") and structure_state in ("HH_HL", "LH_LL") and flow_state in ("BUY_PRESSURE", "SELL_PRESSURE"):
        return "MID"
    if trend_state == "UNKNOWN" and structure_state == "UNKNOWN":
        reason_codes.append("MATURITY_UNKNOWN_NO_EVIDENCE")
        return "UNKNOWN"
    return "EARLY"


def _extract_risk_state(
    maturity_state: str,
    flow_state: str,
    volatility_state: str,
    data_quality_weight: float,
    reason_codes: list[str],
) -> str:
    if data_quality_weight <= 0.2:
        reason_codes.append("RISK_NO_TRADE_INSUFFICIENT_DATA")
        return "NO_TRADE"
    if maturity_state in ("EXHAUSTED", "LATE") and flow_state == "DIVERGENT":
        return "HIGH"
    if volatility_state in ("HIGH", "EXPANDING") and flow_state == "DIVERGENT":
        return "HIGH"
    if maturity_state == "MID" and flow_state in ("BUY_PRESSURE", "SELL_PRESSURE"):
        return "LOW"
    if maturity_state == "UNKNOWN":
        return "UNKNOWN"
    return "MEDIUM"


def _detect_liquidity_hunt(records: dict[str, dict[str, Any]]) -> bool:
    tokens = _collect_strings(records.get("liquidity") or {})
    return _contains_any(tokens, ("SWEEP", "STOP_RUN", "LIQUIDITY_HUNT", "TAKEN_LIQUIDITY"))


def _detect_post_sweep_reaction(records: dict[str, dict[str, Any]]) -> bool:
    tokens = _collect_strings(records.get("liquidity") or {})
    has_sweep = _contains_any(tokens, ("SWEEP", "STOP_RUN", "TAKEN_LIQUIDITY"))
    has_reaction = _contains_any(tokens, ("REACTION", "RECLAIM", "ABSORPTION", "REJECTED", "BOUNCE"))
    return has_sweep and has_reaction


def _classify_regime(
    trend_state: str,
    structure_state: str,
    volatility_state: str,
    liquidity_pressure_state: str,
    flow_state: str,
    maturity_state: str,
    records: dict[str, dict[str, Any]],
    reason_codes: list[str],
) -> str:
    if _detect_post_sweep_reaction(records):
        reason_codes.append("REGIME_POST_SWEEP_REACTION")
        return "POST_SWEEP_REACTION"
    if _detect_liquidity_hunt(records):
        reason_codes.append("REGIME_LIQUIDITY_HUNT")
        return "LIQUIDITY_HUNT"
    if maturity_state in ("LATE", "EXHAUSTED") and flow_state in ("DIVERGENT", "BALANCED"):
        reason_codes.append("REGIME_REVERSAL_RISK")
        return "REVERSAL_RISK"
    if volatility_state == "EXPANDING" and flow_state in ("BUY_PRESSURE", "SELL_PRESSURE"):
        reason_codes.append("REGIME_EXPANSION")
        return "EXPANSION"
    if volatility_state == "COMPRESSING" and structure_state == "RANGE_BOUND" and flow_state == "BALANCED":
        reason_codes.append("REGIME_COMPRESSION")
        return "COMPRESSION"
    if structure_state == "RANGE_BOUND" and volatility_state in ("LOW", "NORMAL", "UNKNOWN") and liquidity_pressure_state == "BOTH":
        reason_codes.append("REGIME_RANGE")
        return "RANGE"
    if structure_state == "HH_HL" and trend_state == "BULLISH" and flow_state == "BUY_PRESSURE" and liquidity_pressure_state in ("ABOVE", "BOTH"):
        reason_codes.append("REGIME_UPTREND")
        return "UPTREND"
    if structure_state == "LH_LL" and trend_state == "BEARISH" and flow_state == "SELL_PRESSURE" and liquidity_pressure_state in ("BELOW", "BOTH"):
        reason_codes.append("REGIME_DOWNTREND")
        return "DOWNTREND"
    reason_codes.append("REGIME_UNKNOWN_INSUFFICIENT_EVIDENCE")
    return "UNKNOWN"


def _data_quality(coverage: float, unknown_count: int, reason_codes: list[str]) -> str:
    if coverage == 0.0:
        reason_codes.append("DATA_QUALITY_UNKNOWN_NO_SOURCE")
        return "UNKNOWN"
    if unknown_count >= 5:
        reason_codes.append("DATA_QUALITY_DEGRADED_UNKNOWN_STATES")
        return "DEGRADED"
    if coverage < 0.4:
        reason_codes.append("DATA_QUALITY_DEGRADED_LOW_COVERAGE")
        return "DEGRADED"
    if coverage < 0.7:
        return "ACCEPTABLE"
    return "OK"


def _confidence_components(
    coverage: float,
    structure_state: str,
    liquidity_pressure_state: str,
    flow_state: str,
    volatility_state: str,
) -> dict[str, float]:
    return {
        "data_quality_weight": round(max(0.0, min(1.0, coverage)), 4),
        "structure_weight": 1.0 if structure_state != "UNKNOWN" else 0.0,
        "liquidity_weight": 1.0 if liquidity_pressure_state != "UNKNOWN" else 0.0,
        "flow_weight": 1.0 if flow_state != "UNKNOWN" else 0.0,
        "volatility_weight": 1.0 if volatility_state != "UNKNOWN" else 0.0,
    }


def _build_ids(
    symbol: str,
    timestamp_utc: str,
    parent_lineage_ids: list[str],
    classification_payload: dict[str, Any],
) -> tuple[str, str]:
    payload_hash = _sha256(classification_payload)
    state_raw = {
        "symbol": symbol,
        "timestamp_utc": timestamp_utc,
        "parent_lineage_ids": sorted(parent_lineage_ids),
        "payload_hash": payload_hash,
        "block_id": MARKET_STATE_BLOCK_ID,
    }
    market_state_id = "MS_" + hashlib.sha256(_canon(state_raw).encode("utf-8")).hexdigest()[:24].upper()
    lineage_raw = {
        "node_type": "market_state",
        "market_state_id": market_state_id,
        "parent_lineage_ids": sorted(parent_lineage_ids),
    }
    lineage_id = "LINCTX_" + hashlib.sha256(_canon(lineage_raw).encode("utf-8")).hexdigest()[:24].upper()
    return market_state_id, lineage_id


def classify_market_state(
    *,
    symbol: str,
    evidence_records: dict[str, dict[str, Any]],
    source_files_used: list[str],
    missing_sources: list[str],
    parent_lineage_ids: list[str] | None = None,
) -> dict[str, Any]:
    reason_codes: list[str] = []
    warnings: list[str] = []
    parent_ids = sorted(set(parent_lineage_ids or []))

    timestamp_utc, ts_reasons = _extract_best_timestamp(evidence_records)
    reason_codes.extend(ts_reasons)

    structure_record = evidence_records.get("structure") or {}
    liquidity_record = evidence_records.get("liquidity") or {}

    trend_state = _extract_trend_state(structure_record, reason_codes)
    volatility_state = _extract_volatility_state(evidence_records, reason_codes)
    structure_state = _extract_structure_state(structure_record, reason_codes)
    liquidity_pressure_state = _extract_liquidity_pressure_state(liquidity_record, reason_codes)
    auction_state = _extract_auction_state(evidence_records, reason_codes)
    flow_state = _extract_flow_state(evidence_records, reason_codes)
    maturity_state = _extract_maturity_state(
        trend_state=trend_state,
        structure_state=structure_state,
        flow_state=flow_state,
        records=evidence_records,
        reason_codes=reason_codes,
    )

    coverage = 0.0
    total_sources = len(source_files_used) + len(missing_sources)
    if total_sources > 0:
        coverage = len(source_files_used) / float(total_sources)
    if not source_files_used:
        reason_codes.append("INSUFFICIENT_EVIDENCE")
        warnings.append("NO_SOURCE_FILE_USED")

    risk_state = _extract_risk_state(
        maturity_state=maturity_state,
        flow_state=flow_state,
        volatility_state=volatility_state,
        data_quality_weight=coverage,
        reason_codes=reason_codes,
    )

    market_regime = _classify_regime(
        trend_state=trend_state,
        structure_state=structure_state,
        volatility_state=volatility_state,
        liquidity_pressure_state=liquidity_pressure_state,
        flow_state=flow_state,
        maturity_state=maturity_state,
        records=evidence_records,
        reason_codes=reason_codes,
    )

    unknown_count = sum(
        1
        for s in (
            trend_state,
            volatility_state,
            structure_state,
            liquidity_pressure_state,
            auction_state,
            flow_state,
            maturity_state,
            risk_state,
        )
        if s == "UNKNOWN"
    )
    data_quality = _data_quality(coverage=coverage, unknown_count=unknown_count, reason_codes=reason_codes)
    components = _confidence_components(
        coverage=coverage,
        structure_state=structure_state,
        liquidity_pressure_state=liquidity_pressure_state,
        flow_state=flow_state,
        volatility_state=volatility_state,
    )
    confidence = (
        components["data_quality_weight"] * 0.35
        + components["structure_weight"] * 0.2
        + components["liquidity_weight"] * 0.15
        + components["flow_weight"] * 0.15
        + components["volatility_weight"] * 0.15
    )
    if market_regime == "UNKNOWN":
        confidence = min(confidence, 0.35)
    if data_quality in ("DEGRADED", "INVALID", "UNKNOWN"):
        confidence = min(confidence, 0.5)
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    evidence = {
        "source_files_used": sorted(source_files_used),
        "candle_evidence": evidence_records.get("candle_dna") or {},
        "structure_evidence": structure_record,
        "liquidity_evidence": liquidity_record,
        "flow_evidence": evidence_records.get("flow") or {},
        "volatility_evidence": evidence_records.get("context") or {},
    }
    classification_payload = {
        "market_regime": market_regime,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure_state,
        "liquidity_pressure_state": liquidity_pressure_state,
        "auction_state": auction_state,
        "flow_state": flow_state,
        "maturity_state": maturity_state,
        "risk_state": risk_state,
        "confidence": confidence,
        "evidence_hash": _sha256(evidence),
    }
    market_state_id, lineage_id = _build_ids(
        symbol=symbol,
        timestamp_utc=timestamp_utc,
        parent_lineage_ids=parent_ids,
        classification_payload=classification_payload,
    )

    payload = {
        "timestamp_utc": timestamp_utc,
        "block_id": MARKET_STATE_BLOCK_ID,
        "symbol": symbol or "BTCUSDT",
        "market_state_id": market_state_id,
        "lineage_id": lineage_id,
        "parent_lineage_ids": parent_ids,
        "market_regime": market_regime,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure_state,
        "liquidity_pressure_state": liquidity_pressure_state,
        "auction_state": auction_state,
        "flow_state": flow_state,
        "maturity_state": maturity_state,
        "risk_state": risk_state,
        "confidence": confidence,
        "confidence_components": components,
        "evidence": evidence,
        "reason_codes": sorted(set(reason_codes)) or ["INSUFFICIENT_EVIDENCE"],
        "warnings": sorted(set(warnings)),
        "data_quality": data_quality,
        "feeds_next": list(DEFAULT_FEEDS_NEXT),
    }
    return payload


def build_unknown_market_state(symbol: str = "BTCUSDT") -> dict[str, Any]:
    return classify_market_state(
        symbol=symbol,
        evidence_records={},
        source_files_used=[],
        missing_sources=["NO_EVIDENCE"],
        parent_lineage_ids=[],
    )
