"""Liquidity Map Engine.

Produces a conservative descriptive liquidity map from observed structure,
candle DNA, and live wall/depth state. No fabricated unsupported feeds.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "LIQUIDITY_MAP_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
DEPTH_MEMORY_PATH = STATE_DIR / "latest_depth_liquidity_memory.json"
WALL_LIFECYCLE_PATH = STATE_DIR / "latest_wall_lifecycle.json"
MTF_HISTORY_PATH = DATA_DIR / "mtf_candle_dna_history.jsonl"

OUTPUT_PATH = STATE_DIR / "latest_liquidity_map.json"
HISTORY_PATH = DATA_DIR / "liquidity_map_history.jsonl"

NEAR_MAX_PCT = 2.0
MID_MAX_PCT = 10.0
LIQUIDITY_TYPES_SUPPORTED = [
    "stop_liquidity",
    "liquidation_cluster",
    "resting_limit_wall",
    "magnet_level",
    "untested_high",
    "untested_low",
    "NPOC",
    "volume_node",
    "fair_value_gap",
    "premium_zone",
    "discount_zone",
]
STRUCTURE_TIMEFRAMES = ["1s", "3s", "5s", "15s", "1m", "3m", "5m", "15m", "1h", "4h", "12h", "1d"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket(distance_pct: float | None) -> str:
    if distance_pct is None:
        return "FAR"
    if distance_pct <= NEAR_MAX_PCT:
        return "NEAR"
    if distance_pct <= MID_MAX_PCT:
        return "MID"
    return "FAR"


def _distance_pct(current_price: float | None, level_price: float | None) -> float | None:
    if current_price is None or current_price <= 0 or level_price is None:
        return None
    return round(abs(level_price - current_price) / current_price * 100.0, 6)


def _strength_from_wall(wall_strength: float | None) -> str:
    if wall_strength is None:
        return "UNKNOWN"
    if wall_strength >= 10.0:
        return "HIGH"
    if wall_strength >= 5.0:
        return "MEDIUM"
    return "LOW"


def _strength_from_tf(tf: str) -> str:
    if tf in ("1h", "4h", "12h", "1d"):
        return "HIGH"
    if tf in ("5m", "15m"):
        return "MEDIUM"
    return "LOW"


def _strength_rank(strength: str) -> int:
    return {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(strength, 0)


def _level(
    current_price: float | None,
    price: float | None,
    liquidity_type: str,
    source: str,
    strength: str,
    reason_codes: list[str],
) -> dict[str, Any] | None:
    if price is None:
        return None
    distance = _distance_pct(current_price, price)
    return {
        "price": round(price, 8),
        "distance_pct": distance,
        "bucket": _bucket(distance),
        "liquidity_type": liquidity_type,
        "source": source,
        "strength": strength,
        "reason_codes": reason_codes,
    }


def _recent_range_from_mtf(mtf_dna: dict[str, Any] | None) -> tuple[float | None, float | None, str | None]:
    for tf in ("5m", "1m", "15s"):
        payload = (mtf_dna or {}).get(tf) or {}
        high = _safe_float(payload.get("high"))
        low = _safe_float(payload.get("low"))
        if high is not None and low is not None and high > low:
            return high, low, tf
    return None, None, None


def run_liquidity_map_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    observation = _load_json(OBSERVATION_PATH) or {}
    mtf_dna = _load_json(MTF_DNA_PATH) or {}
    market_structure = _load_json(MARKET_STRUCTURE_PATH) or {}
    depth_memory = _load_json(DEPTH_MEMORY_PATH) or {}
    wall_lifecycle = _load_json(WALL_LIFECYCLE_PATH) or {}
    mtf_history_exists = MTF_HISTORY_PATH.exists()

    symbol = observation.get("symbol") or mtf_dna.get("symbol") or market_structure.get("symbol") or "BTCUSDT"
    current_price = _safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if current_price is None:
        current_price = _safe_float((((mtf_dna.get("1s") or {}).get("close"))))

    detected_levels: list[dict[str, Any]] = []

    for tf in STRUCTURE_TIMEFRAMES:
        structure = market_structure.get(tf) or {}
        last_swing_high = _safe_float(structure.get("last_swing_high"))
        last_swing_low = _safe_float(structure.get("last_swing_low"))
        if last_swing_high is not None:
            level = _level(
                current_price,
                last_swing_high,
                "untested_high",
                f"market_structure:{tf}",
                _strength_from_tf(tf),
                [f"TF_{tf}", "SWING_HIGH_STOP_LIQUIDITY", f"STRUCTURE_{structure.get('structure_label', 'UNKNOWN')}"],
            )
            if level:
                detected_levels.append(level)
        if last_swing_low is not None:
            level = _level(
                current_price,
                last_swing_low,
                "untested_low",
                f"market_structure:{tf}",
                _strength_from_tf(tf),
                [f"TF_{tf}", "SWING_LOW_STOP_LIQUIDITY", f"STRUCTURE_{structure.get('structure_label', 'UNKNOWN')}"],
            )
            if level:
                detected_levels.append(level)

        equal_high_zone = structure.get("equal_high_zone") or {}
        equal_low_zone = structure.get("equal_low_zone") or {}
        eqh_price = _safe_float(equal_high_zone.get("price"))
        eql_price = _safe_float(equal_low_zone.get("price"))
        if eqh_price is not None:
            level = _level(
                current_price,
                eqh_price,
                "magnet_level",
                f"market_structure:{tf}",
                _strength_from_tf(tf),
                [f"TF_{tf}", "EQH_MAGNET_LEVEL"],
            )
            if level:
                detected_levels.append(level)
        if eql_price is not None:
            level = _level(
                current_price,
                eql_price,
                "magnet_level",
                f"market_structure:{tf}",
                _strength_from_tf(tf),
                [f"TF_{tf}", "EQL_MAGNET_LEVEL"],
            )
            if level:
                detected_levels.append(level)

    bid_wall = (depth_memory.get("bid_wall") or {})
    ask_wall = (depth_memory.get("ask_wall") or {})
    bid_wall_price = _safe_float(bid_wall.get("wall_price"))
    ask_wall_price = _safe_float(ask_wall.get("wall_price"))
    if bid_wall.get("has_wall") and bid_wall_price is not None:
        level = _level(
            current_price,
            bid_wall_price,
            "resting_limit_wall",
            "depth_liquidity_memory:bid_wall",
            _strength_from_wall(_safe_float(bid_wall.get("wall_strength"))),
            ["BID_WALL_DETECTED", f"WALL_EVENT_{((wall_lifecycle.get('bid_wall_history') or {}).get('current_event', 'UNKNOWN'))}"],
        )
        if level:
            detected_levels.append(level)
    if ask_wall.get("has_wall") and ask_wall_price is not None:
        level = _level(
            current_price,
            ask_wall_price,
            "resting_limit_wall",
            "depth_liquidity_memory:ask_wall",
            _strength_from_wall(_safe_float(ask_wall.get("wall_strength"))),
            ["ASK_WALL_DETECTED", f"WALL_EVENT_{((wall_lifecycle.get('ask_wall_history') or {}).get('current_event', 'UNKNOWN'))}"],
        )
        if level:
            detected_levels.append(level)

    range_high, range_low, range_tf = _recent_range_from_mtf(mtf_dna)
    if range_high is not None and range_low is not None and range_tf is not None:
        premium_price = range_low + (range_high - range_low) * 0.75
        discount_price = range_low + (range_high - range_low) * 0.25
        premium_level = _level(
            current_price,
            premium_price,
            "premium_zone",
            f"mtf_range:{range_tf}",
            "LOW",
            [f"RANGE_TF_{range_tf}", "PREMIUM_ZONE_FROM_OBSERVED_RANGE"],
        )
        discount_level = _level(
            current_price,
            discount_price,
            "discount_zone",
            f"mtf_range:{range_tf}",
            "LOW",
            [f"RANGE_TF_{range_tf}", "DISCOUNT_ZONE_FROM_OBSERVED_RANGE"],
        )
        if premium_level:
            detected_levels.append(premium_level)
        if discount_level:
            detected_levels.append(discount_level)

    collapsed: dict[tuple[float, str], dict[str, Any]] = {}
    for level in detected_levels:
        key = (round(level["price"], 8), level["liquidity_type"])
        existing = collapsed.get(key)
        if existing is None:
            collapsed[key] = dict(level)
            continue
        if _strength_rank(level["strength"]) > _strength_rank(existing["strength"]):
            existing["strength"] = level["strength"]
        merged_sources = existing["source"].split(", ")
        if level["source"] not in merged_sources:
            merged_sources.append(level["source"])
        existing["source"] = ", ".join(merged_sources)
        for code in level["reason_codes"]:
            if code not in existing["reason_codes"]:
                existing["reason_codes"].append(code)
        if existing["distance_pct"] is None or (level["distance_pct"] is not None and level["distance_pct"] < existing["distance_pct"]):
            existing["distance_pct"] = level["distance_pct"]
            existing["bucket"] = level["bucket"]

    deduped_levels = list(collapsed.values())

    deduped_levels.sort(key=lambda item: (item["distance_pct"] is None, item["distance_pct"] if item["distance_pct"] is not None else 999999.0))
    near_liquidity = [level for level in deduped_levels if level["bucket"] == "NEAR"]
    mid_liquidity = [level for level in deduped_levels if level["bucket"] == "MID"]
    far_liquidity = [level for level in deduped_levels if level["bucket"] == "FAR"]

    unsupported_features = [
        {"liquidity_type": "liquidation_cluster", "reason": "LIQUIDATION_DATA_NOT_AVAILABLE"},
        {"liquidity_type": "NPOC", "reason": "NPOC_DATA_NOT_AVAILABLE"},
        {"liquidity_type": "volume_node", "reason": "VOLUME_NODE_DATA_NOT_AVAILABLE"},
        {"liquidity_type": "fair_value_gap", "reason": "FAIR_VALUE_GAP_DATA_NOT_AVAILABLE"},
    ]
    if not mtf_history_exists:
        unsupported_features.append({"liquidity_type": "magnet_level", "reason": "MTF_HISTORY_NOT_AVAILABLE"})

    missing_inputs = []
    if not observation:
        missing_inputs.append("latest_observation_factory")
    if not mtf_dna:
        missing_inputs.append("latest_mtf_candle_dna")
    if not market_structure:
        missing_inputs.append("latest_market_structure")
    if not depth_memory:
        missing_inputs.append("latest_depth_liquidity_memory")
    if not wall_lifecycle:
        missing_inputs.append("latest_wall_lifecycle")
    if not mtf_history_exists:
        missing_inputs.append("mtf_candle_dna_history")

    available_count = 6 - len(missing_inputs)
    if available_count <= 0:
        dq_level = "MISSING"
    elif available_count >= 5:
        dq_level = "HIGH"
    elif available_count >= 4:
        dq_level = "OK"
    elif available_count >= 3:
        dq_level = "REDUCED"
    else:
        dq_level = "LOW"

    result = {
        "timestamp_utc": _utc_now(),
        "symbol": symbol,
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "OBSERVATION_STRUCTURE_DEPTH_MAP",
        },
        "current_price": current_price,
        "near_liquidity": near_liquidity,
        "mid_liquidity": mid_liquidity,
        "far_liquidity": far_liquidity,
        "liquidity_types_supported": LIQUIDITY_TYPES_SUPPORTED,
        "detected_levels": deduped_levels,
        "unsupported_features": unsupported_features,
        "data_quality": {
            "level": dq_level,
            "missing_inputs": missing_inputs,
        },
        "reason_codes": [
            f"SYMBOL_{symbol}",
            f"NEAR_LEVELS_{len(near_liquidity)}",
            f"MID_LEVELS_{len(mid_liquidity)}",
            f"FAR_LEVELS_{len(far_liquidity)}",
            "LIQUIDATION_DATA_NOT_AVAILABLE",
            "NPOC_DATA_NOT_AVAILABLE",
            "VOLUME_NODE_DATA_NOT_AVAILABLE",
            "FAIR_VALUE_GAP_DATA_NOT_AVAILABLE",
            f"DQ_{dq_level}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "S15_FLOW_TO_SETUP_CONTEXT",
            "SIGNAL_TAXONOMY_ENGINE",
            "EDGE_MATRIX",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, result)
    return result


def main() -> None:
    print(json.dumps(run_liquidity_map_engine(), indent=2))


if __name__ == "__main__":
    main()
