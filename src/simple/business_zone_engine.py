"""Business Zone Engine.

Approximates auction/value-area context from available candle history without
creating fake profile data. When true profile information is unavailable, all
derived value-area fields are explicitly marked as approximations.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "BUSINESS_ZONE_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_business_zone.json"
HISTORY_PATH = DATA_DIR / "business_zone_history.jsonl"

MTF_DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
MTF_HISTORY_PATH = DATA_DIR / "mtf_candle_dna_history.jsonl"


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


def _quality_level(score: float) -> str:
    if score <= 0.0:
        return "MISSING"
    if score >= 0.95:
        return "HIGH"
    if score >= 0.75:
        return "OK"
    if score >= 0.5:
        return "REDUCED"
    return "LOW"


def _current_price(liquidity_map: dict[str, Any] | None, mtf_dna: dict[str, Any] | None) -> float | None:
    price = _safe_float((liquidity_map or {}).get("current_price"))
    if price is not None:
        return price
    return _safe_float((((mtf_dna or {}).get("1m") or {}).get("close")))


def _read_history_candles(limit: int = 240) -> list[dict[str, Any]]:
    if not MTF_HISTORY_PATH.exists():
        return []
    try:
        lines = [line for line in MTF_HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return []

    candles: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        candle = payload.get("1m") or {}
        if candle:
            candles.append(candle)
    return candles


def _rounded_price(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _value_area_from_history(candles: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str], float]:
    reason_codes: list[str] = []
    volume_by_price: dict[float, float] = defaultdict(float)
    total_volume = 0.0

    for candle in candles:
        close_price = _rounded_price(_safe_float(candle.get("close")))
        volume = _safe_float(candle.get("volume"))
        if close_price is None or volume is None or volume <= 0.0:
            continue
        volume_by_price[close_price] += volume
        total_volume += volume

    if not volume_by_price or total_volume <= 0.0:
        return {
            "vah": None,
            "val": None,
            "poc": None,
            "value_position": "UNKNOWN",
            "value_migration": "UNKNOWN",
        }, ["VALUE_PROFILE_NOT_AVAILABLE"], 0.0

    reason_codes.append("APPROXIMATED_FROM_CANDLE_HISTORY")

    ordered = sorted(volume_by_price.items(), key=lambda item: item[1], reverse=True)
    poc = ordered[0][0]

    selected_prices: list[float] = []
    covered_volume = 0.0
    for price, volume in ordered:
        selected_prices.append(price)
        covered_volume += volume
        if covered_volume >= total_volume * 0.70:
            break

    vah = max(selected_prices) if selected_prices else None
    val = min(selected_prices) if selected_prices else None

    mid = max(len(candles) // 2, 1)
    first_half = [_safe_float(candle.get("close")) for candle in candles[:mid]]
    second_half = [_safe_float(candle.get("close")) for candle in candles[mid:]]
    first_prices = [price for price in first_half if price is not None]
    second_prices = [price for price in second_half if price is not None]
    migration = "UNKNOWN"
    if first_prices and second_prices:
        first_avg = sum(first_prices) / len(first_prices)
        second_avg = sum(second_prices) / len(second_prices)
        threshold = max(abs(first_avg) * 0.0002, 0.01)
        if second_avg > first_avg + threshold:
            migration = "UP"
        elif second_avg < first_avg - threshold:
            migration = "DOWN"
        else:
            migration = "FLAT"

    confidence = min(1.0, len(candles) / 20.0)
    return {
        "vah": vah,
        "val": val,
        "poc": poc,
        "value_position": "UNKNOWN",
        "value_migration": migration,
    }, reason_codes, confidence


def _node_lists(candles: list[dict[str, Any]]) -> dict[str, list[float]]:
    volume_by_price: dict[float, float] = defaultdict(float)
    for candle in candles:
        close_price = _rounded_price(_safe_float(candle.get("close")))
        volume = _safe_float(candle.get("volume"))
        if close_price is None or volume is None or volume <= 0.0:
            continue
        volume_by_price[close_price] += volume

    ordered = sorted(volume_by_price.items(), key=lambda item: item[1], reverse=True)
    reverse_ordered = sorted(volume_by_price.items(), key=lambda item: item[1])
    hvn = [price for price, _ in ordered[:3]]
    lvn = [price for price, _ in reverse_ordered[:3]] if len(reverse_ordered) >= 3 else []
    return {"hvn": hvn, "lvn": lvn, "naked_poc": hvn[:1]}


def run_business_zone_engine() -> dict[str, Any]:
    mtf_dna = _load_json(MTF_DNA_PATH) or {}
    market_structure = _load_json(MARKET_STRUCTURE_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}
    candles = _read_history_candles()

    missing_inputs: list[str] = []
    if not mtf_dna:
        missing_inputs.append("latest_mtf_candle_dna")
    if not market_structure:
        missing_inputs.append("latest_market_structure")
    if not liquidity_map:
        missing_inputs.append("latest_liquidity_map")
    if not candles:
        missing_inputs.append("mtf_candle_dna_history")

    current_price = _current_price(liquidity_map, mtf_dna)
    value_area, reason_codes, history_confidence = _value_area_from_history(candles)
    nodes = _node_lists(candles)

    vah = _safe_float(value_area.get("vah"))
    val = _safe_float(value_area.get("val"))
    poc = _safe_float(value_area.get("poc"))

    if current_price is not None and vah is not None and val is not None:
        if current_price > vah:
            value_area["value_position"] = "ABOVE_VALUE"
        elif current_price < val:
            value_area["value_position"] = "BELOW_VALUE"
        else:
            value_area["value_position"] = "INSIDE_VALUE"

    recent_closes = [_safe_float(candle.get("close")) for candle in candles[-5:]]
    recent_closes = [price for price in recent_closes if price is not None]
    acceptance = False
    rejection = False
    if recent_closes and vah is not None and val is not None:
        inside_count = sum(1 for price in recent_closes if val <= price <= vah)
        above_count = sum(1 for price in recent_closes if price > vah)
        below_count = sum(1 for price in recent_closes if price < val)
        acceptance = inside_count >= 3 or above_count >= 3 or below_count >= 3
        rejection = bool(recent_closes) and recent_closes[-1] is not None and (
            (current_price is not None and current_price > vah and recent_closes[-1] <= vah)
            or (current_price is not None and current_price < val and recent_closes[-1] >= val)
        )

    auction_state = "UNKNOWN"
    if value_area.get("value_position") == "INSIDE_VALUE":
        auction_state = "ACCEPTANCE" if acceptance else "BALANCE"
    elif value_area.get("value_position") in ("ABOVE_VALUE", "BELOW_VALUE"):
        auction_state = "REJECTION" if rejection else "IMBALANCE"

    upper_zone = None
    lower_zone = None
    if poc is not None and vah is not None:
        upper_zone = {"low": poc, "high": vah}
    if poc is not None and val is not None:
        lower_zone = {"low": val, "high": poc}

    zone_role = "UNKNOWN"
    if value_area.get("value_position") == "INSIDE_VALUE":
        zone_role = "TRANSITION"
    elif value_area.get("value_position") == "ABOVE_VALUE":
        zone_role = "TARGET"
    elif value_area.get("value_position") == "BELOW_VALUE":
        zone_role = "REACTION"

    score = 0.0
    if candles:
        score += 0.35
    if current_price is not None:
        score += 0.2
    if poc is not None:
        score += 0.25
    if not missing_inputs:
        score += 0.2
    score = min(1.0, max(score, history_confidence * 0.8))

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(mtf_dna.get("symbol") or liquidity_map.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "CANDLE_HISTORY_VALUE_APPROXIMATION",
        },
        "current_price": current_price,
        "value_area": value_area,
        "volume_nodes": nodes,
        "business_zones": {
            "upper_business_zone": upper_zone,
            "lower_business_zone": lower_zone,
            "current_zone_role": zone_role,
        },
        "auction_summary": {
            "auction_state": auction_state,
            "acceptance": acceptance,
            "rejection": rejection,
            "reason_codes": reason_codes,
        },
        "reason_codes": [
            f"SYMBOL_{str(mtf_dna.get('symbol') or liquidity_map.get('symbol') or 'BTCUSDT')}",
            *reason_codes,
            f"AUCTION_{auction_state}",
            f"DQ_{_quality_level(score)}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "data_quality": {
            "level": _quality_level(score),
            "missing_inputs": missing_inputs,
        },
        "feeds_next": [
            "MARKET_REGIME_CLASSIFIER",
            "TRAP_TRADER_ENGINE",
            "UNIFIED_CONTEXT_ENGINE",
            "S15_FLOW_TO_SETUP_CONTEXT",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_business_zone_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
