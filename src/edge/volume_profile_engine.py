from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload

BLOCK_ID = "REAL_VOLUME_PROFILE_ENGINE"
MAX_RECORDS = 6000
VALUE_AREA_SHARE = 0.70
HVN_SHARE = 0.75
LVN_SHARE = 0.25
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
OUTPUT_PATH = STATE_DIR / "latest_volume_profile.json"
OUTPUT_HISTORY = DATA_DIR / "volume_profile_history.jsonl"
EPOCH_OUTPUT_PATH = epoch_state_path("latest_volume_profile.json")
EPOCH_HISTORY_PATH = epoch_data_path("volume_profile_history.jsonl")
REPORT_PATH = Path("reports/simple/epoch_v2/latest_volume_profile_report.md")
INPUTS = {
    "live_flow_events": DATA_DIR / "live_flow_events.jsonl",
    "market_truth": DATA_DIR / "market_truth.jsonl",
    "hybrid_candle_dna": DATA_DIR / "hybrid_candle_dna.jsonl",
    "mtf_candle_dna": DATA_DIR / "mtf_candle_dna_history.jsonl",
    "observation_factory": DATA_DIR / "observation_factory_history.jsonl",
}
WINDOWS = {"30m": 30 * 60, "1h": 60 * 60, "4h": 4 * 60 * 60}
FEEDS_NEXT = [
    "ZONE_CONTEXT_ENGINE",
    "UNIFIED_CONTEXT_ENGINE",
    "TP_CONDITION_DNA_ENGINE",
    "EDGE_QUERY_ENGINE",
    "EDGE_LEARNING_REPORT",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _session_name(ts: datetime) -> str:
    hour = ts.hour
    if 12 <= hour < 16:
        return "OVERLAP"
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 12:
        return "LONDON"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "OFF_SESSION"


def _session_start(ts: datetime) -> datetime:
    name = _session_name(ts)
    if name == "ASIA":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if name == "LONDON":
        return ts.replace(hour=7, minute=0, second=0, microsecond=0)
    if name == "OVERLAP":
        return ts.replace(hour=12, minute=0, second=0, microsecond=0)
    if name == "NEW_YORK":
        return ts.replace(hour=16, minute=0, second=0, microsecond=0)
    return ts.replace(hour=21, minute=0, second=0, microsecond=0)


def _iter_sample(payload: dict[str, Any], source_name: str) -> list[dict[str, Any]]:
    ts = _parse_ts(payload.get("timestamp_utc"))
    if ts is None:
        return []
    samples: list[dict[str, Any]] = []
    if source_name == "observation_factory":
        price = safe_float(payload.get("last_trade_price") or payload.get("price") or (payload.get("market_snapshot") or {}).get("price"))
        volume = safe_float((payload.get("volume_flow") or {}).get("total_volume") or payload.get("aggressive_buy_volume"))
        if price is not None and volume is not None and volume > 0:
            samples.append({"timestamp": ts, "price": price, "volume": volume, "source": "TRADE_VOLUME"})
    elif source_name == "market_truth":
        candle = payload.get("official_candle") or {}
        close_price = safe_float(candle.get("close") or (payload.get("market_truth") or {}).get("official_close"))
        volume = safe_float(candle.get("volume") or (payload.get("market_truth") or {}).get("official_volume"))
        low = safe_float(candle.get("low"))
        high = safe_float(candle.get("high"))
        if close_price is not None and volume is not None and volume > 0:
            samples.append({"timestamp": ts, "price": close_price, "volume": volume, "source": "CANDLE_VOLUME", "low": low, "high": high})
    elif source_name == "hybrid_candle_dna":
        candle = payload.get("official_candle") or {}
        close_price = safe_float(candle.get("close"))
        volume = safe_float(candle.get("volume"))
        low = safe_float(candle.get("low"))
        high = safe_float(candle.get("high"))
        if close_price is not None and volume is not None and volume > 0:
            samples.append({"timestamp": ts, "price": close_price, "volume": volume, "source": "CANDLE_VOLUME", "low": low, "high": high})
    elif source_name == "mtf_candle_dna":
        stack = [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                close_price = safe_float(item.get("close") or item.get("dna_close"))
                volume = safe_float(item.get("volume"))
                low = safe_float(item.get("low") or item.get("dna_low"))
                high = safe_float(item.get("high") or item.get("dna_high"))
                if close_price is not None and volume is not None and volume > 0:
                    samples.append({"timestamp": ts, "price": close_price, "volume": volume, "source": "CANDLE_VOLUME", "low": low, "high": high})
                for value in item.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)
    elif source_name == "live_flow_events":
        if str(payload.get("stream") or "").lower() == "aggtrade":
            price = safe_float(payload.get("price") or payload.get("p"))
            volume = safe_float(payload.get("quantity") or payload.get("q"))
            if price is not None and volume is not None and volume > 0:
                samples.append({"timestamp": ts, "price": price, "volume": volume, "source": "TRADE_VOLUME"})
    return samples


def _load_samples(max_records: int = MAX_RECORDS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    stats: dict[str, Any] = {"records_read": {}, "source_counts": defaultdict(int), "reasons": []}
    for name, path in INPUTS.items():
        rows = read_jsonl_tail_objects(path, max_lines=max_records)
        stats["records_read"][name] = len(rows)
        for row in rows:
            extracted = _iter_sample(row, name)
            samples.extend(extracted)
            for item in extracted:
                stats["source_counts"][item["source"]] += 1
    samples.sort(key=lambda item: item["timestamp"])
    stats["source_counts"] = dict(stats["source_counts"])
    if not samples:
        stats["reasons"].append("NO_PRICE_VOLUME_SAMPLES")
    return samples[-max_records:], stats


def _price_bounds(samples: list[dict[str, Any]]) -> tuple[float, float]:
    lows = [safe_float(item.get("low")) if safe_float(item.get("low")) is not None else safe_float(item.get("price")) for item in samples]
    highs = [safe_float(item.get("high")) if safe_float(item.get("high")) is not None else safe_float(item.get("price")) for item in samples]
    return min(value for value in lows if value is not None), max(value for value in highs if value is not None)


def _bin_size(samples: list[dict[str, Any]]) -> float:
    prices = sorted({round(safe_float(item.get("price")) or 0.0, 8) for item in samples if safe_float(item.get("price")) is not None})
    if len(prices) > 1:
        deltas = [round(prices[i] - prices[i - 1], 8) for i in range(1, len(prices)) if prices[i] > prices[i - 1]]
        min_delta = min((delta for delta in deltas if delta > 0), default=0.0)
    else:
        min_delta = 0.0
    low, high = _price_bounds(samples)
    observed_range = max(high - low, 0.0)
    adaptive = observed_range / max(min(len(prices), 40), 1)
    raw = max(min_delta or 0.0, adaptive or 0.0, 0.01 if high > 1000 else 0.0001)
    return round(raw, 8)


def _bin_floor(price: float, size: float) -> float:
    return round(math.floor(price / size) * size, 8)


def _zone_id(prefix: str, window: str, low: float, high: float) -> str:
    return f"{prefix}_{window}_{str(low).replace('.', '_')}_{str(high).replace('.', '_')}"


def _build_zone(zone_type: str, window: str, low: float, high: float, volume: float, total_volume: float, source: str, confidence: float, status: str = "ACTIVE", reason_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "zone_id": _zone_id(zone_type, window, low, high),
        "zone_type": zone_type,
        "price_low": round(low, 8),
        "price_high": round(high, 8),
        "mid_price": round((low + high) / 2.0, 8),
        "volume": round(volume, 8),
        "volume_share": round(volume / total_volume, 6) if total_volume > 0 else 0.0,
        "window": window,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "status": status if status in {"ACTIVE", "REVISITED", "BROKEN", "UNKNOWN"} else "UNKNOWN",
        "source": source,
        "reason_codes": reason_codes or [],
    }


def _cluster_bins(sorted_bins: list[tuple[float, float]], size: float, threshold: float, mode: str) -> list[list[tuple[float, float]]]:
    if not sorted_bins:
        return []
    max_volume = max(volume for _price, volume in sorted_bins)
    clusters: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for price, volume in sorted_bins:
        qualifies = volume >= max_volume * threshold if mode == "high" else volume <= max_volume * threshold
        if qualifies:
            if current and abs(price - current[-1][0] - size) > (size * 1.5):
                clusters.append(current)
                current = []
            current.append((price, volume))
        elif current:
            clusters.append(current)
            current = []
    if current:
        clusters.append(current)
    return clusters


def _value_area(sorted_bins: list[tuple[float, float]], poc_index: int, total_volume: float) -> tuple[int, int]:
    covered = sorted_bins[poc_index][1]
    left = right = poc_index
    while covered / total_volume < VALUE_AREA_SHARE and (left > 0 or right < len(sorted_bins) - 1):
        left_vol = sorted_bins[left - 1][1] if left > 0 else -1.0
        right_vol = sorted_bins[right + 1][1] if right < len(sorted_bins) - 1 else -1.0
        if right_vol >= left_vol and right < len(sorted_bins) - 1:
            right += 1
            covered += sorted_bins[right][1]
        elif left > 0:
            left -= 1
            covered += sorted_bins[left][1]
        else:
            break
    return left, right


def _acceptance_and_rejection(samples: list[dict[str, Any]], zones: list[dict[str, Any]], window: str, bin_size: float, total_volume: float, source: str, confidence: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    acceptance: list[dict[str, Any]] = []
    rejection: list[dict[str, Any]] = []
    for zone in zones:
        low = safe_float(zone.get("price_low")) or 0.0
        high = safe_float(zone.get("price_high")) or low
        touches = [item for item in samples if low <= (safe_float(item.get("price")) or 0.0) <= high]
        if len(touches) >= 3:
            acceptance.append(_build_zone("ACCEPTANCE", window, low, high, sum(safe_float(item.get("volume")) or 0.0 for item in touches), total_volume, source, confidence, reason_codes=["REPEATED_INTERACTIONS_NEAR_ZONE"]))
        elif len(touches) == 1:
            idx = samples.index(touches[0])
            later = samples[idx + 1 : idx + 4]
            if later and any(abs((safe_float(item.get("price")) or low) - (safe_float(touches[0].get("price")) or low)) > bin_size for item in later):
                rejection.append(_build_zone("REJECTION", window, low, high, safe_float(touches[0].get("volume")) or 0.0, total_volume, source, max(confidence - 0.1, 0.0), reason_codes=["SINGLE_INTERACTION_AND_MOVE_AWAY"]))
    return acceptance, rejection


def _naked_poc(samples: list[dict[str, Any]], poc_zone: dict[str, Any], bin_size: float, total_volume: float, source: str, confidence: float) -> list[dict[str, Any]]:
    low = safe_float(poc_zone.get("price_low")) or 0.0
    high = safe_float(poc_zone.get("price_high")) or low
    touched_indices = [idx for idx, item in enumerate(samples) if low <= (safe_float(item.get("price")) or 0.0) <= high]
    if not touched_indices:
        return []
    first_idx = touched_indices[0]
    later = samples[first_idx + 1 :]
    if len(later) < 3:
        status = "UNKNOWN"
        reasons = ["NAKED_POC_STATUS_UNKNOWN", "NOT_ENOUGH_FUTURE_SAMPLES"]
    else:
        revisited = any(low <= (safe_float(item.get("price")) or 0.0) <= high for item in later)
        status = "REVISITED" if revisited else "ACTIVE"
        reasons = ["POC_REVISITED_AFTER_FORMATION"] if revisited else ["POC_NOT_REVISITED_AFTER_FORMATION"]
    volume = sum(safe_float(item.get("volume")) or 0.0 for item in samples if low <= (safe_float(item.get("price")) or 0.0) <= high)
    return [_build_zone("NAKED_POC", str(poc_zone.get("window") or "UNKNOWN"), low, high, volume, total_volume, source, confidence, status=status, reason_codes=reasons)]


def _build_window_profile(window: str, samples: list[dict[str, Any]], source: str, confidence: float) -> dict[str, Any]:
    total_volume = sum(safe_float(item.get("volume")) or 0.0 for item in samples)
    if len(samples) < 5 or total_volume <= 0:
        return {
            "poc": {},
            "vah": None,
            "val": None,
            "vamid": None,
            "hvn_zones": [],
            "lvn_zones": [],
            "naked_pocs": [],
            "acceptance_zones": [],
            "rejection_zones": [],
            "bin_size": 0.0,
            "sample_count": len(samples),
            "volume_total": round(total_volume, 8),
        }
    size = _bin_size(samples)
    bins: dict[float, float] = defaultdict(float)
    for item in samples:
        price = safe_float(item.get("price"))
        volume = safe_float(item.get("volume"))
        if price is None or volume is None or volume <= 0:
            continue
        bins[_bin_floor(price, size)] += volume
    sorted_bins = sorted(bins.items())
    if not sorted_bins:
        return {
            "poc": {},
            "vah": None,
            "val": None,
            "vamid": None,
            "hvn_zones": [],
            "lvn_zones": [],
            "naked_pocs": [],
            "acceptance_zones": [],
            "rejection_zones": [],
            "bin_size": size,
            "sample_count": len(samples),
            "volume_total": round(total_volume, 8),
        }
    poc_index = max(range(len(sorted_bins)), key=lambda idx: sorted_bins[idx][1])
    poc_price, poc_volume = sorted_bins[poc_index]
    poc = _build_zone("POC", window, poc_price, poc_price + size, poc_volume, total_volume, source, confidence, reason_codes=["HIGHEST_VOLUME_BIN"])
    left, right = _value_area(sorted_bins, poc_index, total_volume)
    val = sorted_bins[left][0]
    vah = sorted_bins[right][0] + size
    vamid = round((val + vah) / 2.0, 8)
    hvn_zones = []
    for cluster in _cluster_bins(sorted_bins, size, HVN_SHARE, "high"):
        low = cluster[0][0]
        high = cluster[-1][0] + size
        hvn_zones.append(_build_zone("HVN", window, low, high, sum(volume for _price, volume in cluster), total_volume, source, confidence, reason_codes=["HIGH_VOLUME_CLUSTER"]))
    lvn_zones = []
    for cluster in _cluster_bins(sorted_bins, size, LVN_SHARE, "low"):
        low = cluster[0][0]
        high = cluster[-1][0] + size
        lvn_zones.append(_build_zone("LVN", window, low, high, sum(volume for _price, volume in cluster), total_volume, source, max(confidence - 0.1, 0.0), reason_codes=["LOW_VOLUME_GAP_CLUSTER"]))
    acceptance_zones, rejection_zones = _acceptance_and_rejection(samples, [poc] + hvn_zones + lvn_zones, window, size, total_volume, source, confidence)
    naked_pocs = _naked_poc(samples, poc, size, total_volume, source, confidence)
    return {
        "poc": poc,
        "vah": round(vah, 8),
        "val": round(val, 8),
        "vamid": vamid,
        "hvn_zones": hvn_zones,
        "lvn_zones": lvn_zones,
        "naked_pocs": naked_pocs,
        "acceptance_zones": acceptance_zones,
        "rejection_zones": rejection_zones,
        "bin_size": size,
        "sample_count": len(samples),
        "volume_total": round(total_volume, 8),
    }


def _filter_window(samples: list[dict[str, Any]], now: datetime, seconds: int) -> list[dict[str, Any]]:
    cutoff = now - timedelta(seconds=seconds)
    return [item for item in samples if item["timestamp"] >= cutoff]


def _filter_session(samples: list[dict[str, Any]], now: datetime) -> tuple[list[dict[str, Any]], str]:
    session = _session_name(now)
    start = _session_start(now)
    return [item for item in samples if item["timestamp"] >= start], session


def build_volume_profile_from_samples(samples: list[dict[str, Any]], symbol: str = "BTCUSDT") -> dict[str, Any]:
    context = current_runtime_context(symbol)
    if not samples:
        return stamp_payload(
            {
                "profile_status": "INSUFFICIENT_DATA",
                "windows": {},
                "data_quality": {"level": "LOW", "records_analyzed": 0, "source_used": "NONE"},
                "reason_codes": ["INSUFFICIENT_VOLUME_PROFILE_DATA", "NO_PRICE_VOLUME_SAMPLES"],
                "feeds_next": FEEDS_NEXT,
            },
            BLOCK_ID,
            symbol,
            context,
        )
    now = samples[-1]["timestamp"]
    source_priority = "TRADE_VOLUME" if any(item.get("source") == "TRADE_VOLUME" for item in samples) else "CANDLE_VOLUME"
    profile_status = "OK" if source_priority == "TRADE_VOLUME" else "APPROX"
    confidence = 0.9 if source_priority == "TRADE_VOLUME" else 0.55
    windows: dict[str, Any] = {}
    for label, seconds in WINDOWS.items():
        window_samples = _filter_window(samples, now, seconds)
        windows[label] = _build_window_profile(label, window_samples, source_priority, confidence)
    session_samples, session_name = _filter_session(samples, now)
    windows["session"] = _build_window_profile("session", session_samples, source_priority, confidence)
    windows["session"]["session_label"] = session_name
    return stamp_payload(
        {
            "profile_status": profile_status if any(window.get("sample_count", 0) >= 5 for window in windows.values()) else "INSUFFICIENT_DATA",
            "windows": windows,
            "data_quality": {
                "level": "HIGH" if profile_status == "OK" else "MEDIUM",
                "records_analyzed": len(samples),
                "source_used": source_priority,
                "trade_volume_available": source_priority == "TRADE_VOLUME",
                "candle_volume_fallback": source_priority == "CANDLE_VOLUME",
            },
            "reason_codes": ["REAL_TRADE_VOLUME_PROFILE" if source_priority == "TRADE_VOLUME" else "CANDLE_VOLUME_PROFILE_APPROX"],
            "feeds_next": FEEDS_NEXT,
        },
        BLOCK_ID,
        symbol,
        context,
    )


def _write_report(output: dict[str, Any], stats: dict[str, Any]) -> None:
    lines = [
        "# NURNOVA Volume Profile Report",
        "",
        f"- Profile status: {output.get('profile_status')}",
        f"- Data source used: {(output.get('data_quality') or {}).get('source_used')}",
        f"- Sample count: {(output.get('data_quality') or {}).get('records_analyzed')}",
        f"- Source counts: {json.dumps(stats.get('source_counts') or {}, ensure_ascii=False)}",
        "",
    ]
    for window, payload in (output.get("windows") or {}).items():
        poc = payload.get("poc") or {}
        lines.extend(
            [
                f"## {window}",
                f"- POC: {json.dumps(poc, ensure_ascii=False)}",
                f"- VAH: {payload.get('vah')}",
                f"- VAL: {payload.get('val')}",
                f"- VAMID: {payload.get('vamid')}",
                f"- HVN zones: {json.dumps(payload.get('hvn_zones') or [], ensure_ascii=False)}",
                f"- LVN zones: {json.dumps(payload.get('lvn_zones') or [], ensure_ascii=False)}",
                f"- Naked POC status: {json.dumps(payload.get('naked_pocs') or [], ensure_ascii=False)}",
                "",
            ]
        )
    lines.extend(
        [
            "- Exact vs approx warning: OK means trade-volume-backed profile. APPROX means candle-volume fallback only.",
            f"- Limitations: {json.dumps(stats.get('reasons') or [], ensure_ascii=False)}",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_volume_profile_engine(max_records: int = MAX_RECORDS) -> dict[str, Any]:
    samples, stats = _load_samples(max_records=max_records)
    latest_market_truth = load_json(STATE_DIR / "latest_market_truth.json") or {}
    symbol = str(latest_market_truth.get("symbol") or "BTCUSDT")
    output = build_volume_profile_from_samples(samples, symbol=symbol)
    output["data_quality"]["records_by_input"] = stats.get("records_read") or {}
    output["data_quality"]["source_counts"] = stats.get("source_counts") or {}
    if stats.get("reasons"):
        output["reason_codes"] = sorted(set((output.get("reason_codes") or []) + list(stats["reasons"])))
    output["execution_safety"] = {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False}
    write_json_atomic(OUTPUT_PATH, output)
    write_json_atomic(EPOCH_OUTPUT_PATH, output)
    append_jsonl_stream(OUTPUT_HISTORY, output)
    append_jsonl_stream(EPOCH_HISTORY_PATH, output)
    _write_report(output, stats)
    return output


def main() -> None:
    print(json.dumps(run_volume_profile_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
