"""Observation Factory.

Transforms the existing flow, depth, wall, and candle states into a
microstructure observation block without introducing trade logic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "OBSERVATION_FACTORY"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_observation_factory.json"
HISTORY_PATH = DATA_DIR / "observation_factory_history.jsonl"

FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"
FLOW_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
FLOW_PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
DEPTH_MEMORY_PATH = STATE_DIR / "latest_depth_liquidity_memory.json"
WALL_LIFECYCLE_PATH = STATE_DIR / "latest_wall_lifecycle.json"
MARKET_TRUTH_PATH = STATE_DIR / "latest_market_truth.json"
ONE_SECOND_EVIDENCE_PATH = STATE_DIR / "latest_1s_evidence.json"
HYBRID_DNA_PATH = STATE_DIR / "latest_hybrid_candle_dna.json"
AR01_PATH = STATE_DIR / "latest_ar01.json"

INPUT_PATHS = {
    "flow_state": FLOW_STATE_PATH,
    "flow_evidence": FLOW_EVIDENCE_PATH,
    "flow_persistence": FLOW_PERSISTENCE_PATH,
    "depth_liquidity_memory": DEPTH_MEMORY_PATH,
    "wall_lifecycle": WALL_LIFECYCLE_PATH,
    "market_truth": MARKET_TRUTH_PATH,
    "one_second_evidence": ONE_SECOND_EVIDENCE_PATH,
    "hybrid_candle_dna": HYBRID_DNA_PATH,
    "ar01": AR01_PATH,
}


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


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_history_deltas() -> list[float]:
    if not HISTORY_PATH.exists():
        return []
    deltas: list[float] = []
    try:
        for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            delta = _safe_float(((record.get("aggression") or {}).get("delta")))
            if delta is not None:
                deltas.append(delta)
    except Exception:
        return []
    return deltas


def _read_history_records() -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return records


def _source_is_fake(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    source = payload.get("source")
    if isinstance(source, dict):
        source_mode = str(source.get("source_mode", "")).upper()
        if "FAKE" in source_mode:
            return True
        reason_codes = source.get("reason_codes") or []
        if any("FAKE" in str(code).upper() for code in reason_codes):
            return True
    source_str = str(source or "").upper()
    if "FAKE" in source_str:
        return True
    reason_codes = payload.get("reason_codes") or []
    return any("FAKE" in str(code).upper() for code in reason_codes)


def _candidate_has_volume_fields(payload: dict[str, Any] | None, buy_key: str, sell_key: str) -> bool:
    if not payload:
        return False
    return payload.get(buy_key) is not None or payload.get(sell_key) is not None


def _build_volume_flow(
    latest_bucket: dict[str, Any],
    flow_evidence: dict[str, Any],
    one_second_evidence: dict[str, Any],
    hybrid_dna: dict[str, Any],
) -> dict[str, Any]:
    flow_snapshot = flow_evidence.get("flow_snapshot") or {}
    aggression_evidence = flow_evidence.get("aggression_evidence") or {}
    trade_flow = one_second_evidence.get("trade_flow") or {}
    official_candle = hybrid_dna.get("official_candle") or {}

    source = "UNKNOWN"
    buy_volume_raw: float | None = None
    sell_volume_raw: float | None = None
    buy_trade_count_raw: int | None = None
    sell_trade_count_raw: int | None = None

    if latest_bucket and not _source_is_fake({"reason_codes": latest_bucket.get("reason_codes", [])}) and _candidate_has_volume_fields(latest_bucket, "buy_volume", "sell_volume"):
        source = "aggTrade"
        buy_volume_raw = _safe_float(latest_bucket.get("buy_volume"))
        sell_volume_raw = _safe_float(latest_bucket.get("sell_volume"))
        buy_trade_count_raw = _safe_int(latest_bucket.get("buy_trade_count"))
        sell_trade_count_raw = _safe_int(latest_bucket.get("sell_trade_count"))
    elif flow_snapshot and not _source_is_fake(flow_evidence) and _candidate_has_volume_fields(flow_snapshot, "buy_volume", "sell_volume"):
        source = "flow_evidence"
        buy_volume_raw = _safe_float(flow_snapshot.get("buy_volume"))
        sell_volume_raw = _safe_float(flow_snapshot.get("sell_volume"))
        buy_trade_count_raw = _safe_int(flow_snapshot.get("buy_trade_count"))
        sell_trade_count_raw = _safe_int(flow_snapshot.get("sell_trade_count"))
        if buy_trade_count_raw is None:
            buy_trade_count_raw = _safe_int(aggression_evidence.get("buy_trade_count"))
        if sell_trade_count_raw is None:
            sell_trade_count_raw = _safe_int(aggression_evidence.get("sell_trade_count"))
    elif trade_flow and not _source_is_fake(one_second_evidence) and _candidate_has_volume_fields(trade_flow, "buy_volume", "sell_volume"):
        source = "aggTrade"
        buy_volume_raw = _safe_float(trade_flow.get("buy_volume"))
        sell_volume_raw = _safe_float(trade_flow.get("sell_volume"))
        buy_trade_count_raw = _safe_int(flow_snapshot.get("buy_trade_count"))
        sell_trade_count_raw = _safe_int(flow_snapshot.get("sell_trade_count"))
        if buy_trade_count_raw is None:
            buy_trade_count_raw = _safe_int(aggression_evidence.get("buy_trade_count"))
        if sell_trade_count_raw is None:
            sell_trade_count_raw = _safe_int(aggression_evidence.get("sell_trade_count"))
    elif official_candle:
        source = "hybrid_candle_dna"

    reason_codes: list[str] = []
    if buy_volume_raw is None or sell_volume_raw is None:
        buy_volume = 0.0
        sell_volume = 0.0
        total_volume = 0.0
        delta = 0.0
        reason_codes.append("MISSING_AGGRESSIVE_VOLUME_FIELDS")
    else:
        buy_volume = round(buy_volume_raw, 8)
        sell_volume = round(sell_volume_raw, 8)
        total_volume = round(buy_volume + sell_volume, 8)
        delta = round(buy_volume - sell_volume, 8)

    aggressive_buy_trade_count = max(buy_trade_count_raw or 0, 0)
    aggressive_sell_trade_count = max(sell_trade_count_raw or 0, 0)

    avg_buy_trade_size = None
    if aggressive_buy_trade_count > 0 and buy_volume > 0.0:
        avg_buy_trade_size = round(buy_volume / aggressive_buy_trade_count, 8)

    avg_sell_trade_size = None
    if aggressive_sell_trade_count > 0 and sell_volume > 0.0:
        avg_sell_trade_size = round(sell_volume / aggressive_sell_trade_count, 8)

    cumulative_delta = None
    history_records = _read_history_records()
    prior_deltas: list[float] = []
    prior_cumulative_delta: float | None = None
    for record in history_records:
        volume_flow = record.get("volume_flow") or {}
        aggression = record.get("aggression") or {}
        prior_delta = _first_float(volume_flow.get("delta"), aggression.get("delta"))
        if prior_delta is not None:
            prior_deltas.append(prior_delta)
        prior_cumulative_delta = _first_float(
            volume_flow.get("cumulative_delta"),
            aggression.get("cumulative_delta"),
            prior_cumulative_delta,
        )
    if prior_deltas:
        base_cumulative_delta = prior_cumulative_delta if prior_cumulative_delta is not None else sum(prior_deltas)
        cumulative_delta = round(base_cumulative_delta + delta, 8)
    else:
        reason_codes.append("CUMULATIVE_DELTA_HISTORY_NOT_AVAILABLE")

    volume_imbalance = None
    if sell_volume > 0.0:
        volume_imbalance = round(buy_volume / sell_volume, 8)
    elif buy_volume > 0.0 and sell_volume == 0.0:
        reason_codes.append("SELL_VOLUME_ZERO")
    else:
        reason_codes.append("NO_VOLUME_DATA")

    return {
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "total_volume": total_volume,
        "delta": delta,
        "cumulative_delta": cumulative_delta,
        "volume_imbalance": volume_imbalance,
        "aggressive_buy_trade_count": aggressive_buy_trade_count,
        "aggressive_sell_trade_count": aggressive_sell_trade_count,
        "avg_buy_trade_size": avg_buy_trade_size,
        "avg_sell_trade_size": avg_sell_trade_size,
        "source": source,
        "reason_codes": reason_codes,
    }


def _data_quality(available_inputs: list[str], missing_inputs: list[str]) -> dict[str, Any]:
    total = len(available_inputs) + len(missing_inputs)
    score = round(len(available_inputs) / total, 4) if total else 0.0
    if not available_inputs:
        level = "MISSING"
    elif score >= 0.99:
        level = "HIGH"
    elif score >= 0.75:
        level = "OK"
    elif score >= 0.5:
        level = "REDUCED"
    else:
        level = "LOW"
    return {
        "level": level,
        "score": score,
        "missing_inputs": missing_inputs,
        "available_inputs": available_inputs,
    }


def _trade_side(buy_volume: float, sell_volume: float, delta: float) -> str:
    if buy_volume > sell_volume or delta > 0:
        return "BUY"
    if sell_volume > buy_volume or delta < 0:
        return "SELL"
    if buy_volume == 0.0 and sell_volume == 0.0 and delta == 0.0:
        return "UNKNOWN"
    return "NEUTRAL"


def _aggressor_side(delta: float, pressure_score: float) -> str:
    if delta > 0 or pressure_score > 0:
        return "BUYERS"
    if delta < 0 or pressure_score < 0:
        return "SELLERS"
    if delta == 0 and pressure_score == 0:
        return "NEUTRAL"
    return "UNKNOWN"


def _copy_wall_snapshot(wall: dict[str, Any] | None) -> dict[str, Any] | None:
    if not wall:
        return None
    return {
        "price": _first_float(wall.get("wall_price"), wall.get("price")),
        "notional": _first_float(wall.get("wall_notional")),
        "strength": _first_float(wall.get("wall_strength")),
        "has_wall": bool(wall.get("has_wall", True)) if wall else False,
    }


def _liquidity_wall(
    bid_wall: dict[str, Any] | None,
    ask_wall: dict[str, Any] | None,
    bid_history: dict[str, Any],
    ask_history: dict[str, Any],
) -> tuple[str, str]:
    bid_strength = _first_float((bid_wall or {}).get("strength"), bid_history.get("spoof_score"), 0.0) or 0.0
    ask_strength = _first_float((ask_wall or {}).get("strength"), ask_history.get("spoof_score"), 0.0) or 0.0
    bid_conclusion = bid_history.get("liquidity_conclusion", "UNKNOWN")
    ask_conclusion = ask_history.get("liquidity_conclusion", "UNKNOWN")

    if bid_conclusion == "LIKELY_SPOOF" and ask_conclusion != "LIKELY_SPOOF":
        return "BID_WALL", "bid wall flagged as likely spoof"
    if ask_conclusion == "LIKELY_SPOOF" and bid_conclusion != "LIKELY_SPOOF":
        return "ASK_WALL", "ask wall flagged as likely spoof"
    if bid_strength > ask_strength and bid_strength > 0:
        return "BID_WALL", f"bid wall stronger ({bid_strength:.2f}) than ask wall ({ask_strength:.2f})"
    if ask_strength > bid_strength and ask_strength > 0:
        return "ASK_WALL", f"ask wall stronger ({ask_strength:.2f}) than bid wall ({bid_strength:.2f})"
    if bid_strength == 0 and ask_strength == 0:
        return "NONE", "no persistent wall detected"
    return "UNKNOWN", "wall dominance unclear"


def _build_observation(inputs: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    flow_state = inputs["flow_state"] or {}
    flow_evidence = inputs["flow_evidence"] or {}
    flow_persistence = inputs["flow_persistence"] or {}
    depth_memory = inputs["depth_liquidity_memory"] or {}
    wall_lifecycle = inputs["wall_lifecycle"] or {}
    market_truth = inputs["market_truth"] or {}
    one_second_evidence = inputs["one_second_evidence"] or {}
    hybrid_dna = inputs["hybrid_candle_dna"] or {}
    ar01 = inputs["ar01"] or {}

    latest_bucket = flow_state.get("latest_bucket") or {}
    market_truth_block = market_truth.get("market_truth") or {}
    price_truth = market_truth.get("price_truth") or {}
    official_candle = (hybrid_dna.get("official_candle") or market_truth.get("official_candle") or {})
    bid_wall_raw = depth_memory.get("bid_wall") or {}
    ask_wall_raw = depth_memory.get("ask_wall") or {}
    bid_history = wall_lifecycle.get("bid_wall_history") or {}
    ask_history = wall_lifecycle.get("ask_wall_history") or {}
    liquidity_intelligence = wall_lifecycle.get("liquidity_intelligence") or {}

    symbol = (
        latest_bucket.get("symbol")
        or flow_evidence.get("symbol")
        or market_truth.get("symbol")
        or depth_memory.get("symbol")
        or "BTCUSDT"
    )

    volume_flow = _build_volume_flow(latest_bucket, flow_evidence, one_second_evidence, hybrid_dna)
    aggressive_buy_volume = _safe_float(volume_flow.get("buy_volume")) or 0.0
    aggressive_sell_volume = _safe_float(volume_flow.get("sell_volume")) or 0.0
    delta = _safe_float(volume_flow.get("delta")) or 0.0
    pressure_score = _first_float(
        (flow_evidence.get("pressure_evidence") or {}).get("pressure_score"),
        flow_evidence.get("evidence_score"),
        0.0,
    ) or 0.0
    evidence_score = _first_float(flow_evidence.get("evidence_score"), 0.0) or 0.0
    aggressor_side = _aggressor_side(delta, pressure_score)
    cumulative_delta = _safe_float(volume_flow.get("cumulative_delta"))

    price = _first_float(
        market_truth_block.get("current_price"),
        official_candle.get("close"),
        latest_bucket.get("last_price"),
        price_truth.get("mid_price"),
    )
    bid_price = _first_float(price_truth.get("best_bid"), latest_bucket.get("best_bid"))
    ask_price = _first_float(price_truth.get("best_ask"), latest_bucket.get("best_ask"))
    spread = _first_float(price_truth.get("spread"), latest_bucket.get("spread"))
    last_trade_price = _first_float(latest_bucket.get("last_price"), market_truth_block.get("official_close"))
    trade_size = None
    trade_side = _trade_side(aggressive_buy_volume, aggressive_sell_volume, delta)

    bid_wall = _copy_wall_snapshot(bid_wall_raw)
    ask_wall = _copy_wall_snapshot(ask_wall_raw)
    orderbook_depth = None
    bid_total = _first_float(bid_wall_raw.get("total_notional"))
    ask_total = _first_float(ask_wall_raw.get("total_notional"))
    if bid_total is not None or ask_total is not None:
        orderbook_depth = round((bid_total or 0.0) + (ask_total or 0.0), 2)
    liquidity_wall, wall_conclusion = _liquidity_wall(bid_wall, ask_wall, bid_history, ask_history)

    evidence_delta_ratio = _first_float(
        latest_bucket.get("delta_ratio"),
        (one_second_evidence.get("trade_flow") or {}).get("delta_ratio"),
    ) or 0.0
    buy_pressure = _first_float((one_second_evidence.get("evidence") or {}).get("buy_pressure"), 0.0) or 0.0
    sell_pressure = _first_float((one_second_evidence.get("evidence") or {}).get("sell_pressure"), 0.0) or 0.0
    spoof_candidate = (
        bid_history.get("liquidity_conclusion") == "LIKELY_SPOOF"
        or ask_history.get("liquidity_conclusion") == "LIKELY_SPOOF"
        or any("LIKELY_SPOOF" in code for code in wall_lifecycle.get("reason_codes", []))
    )
    absorption_candidate = bool(ar01.get("absorption_detected", False))
    imbalance_candidate = (
        abs(evidence_delta_ratio) >= 0.6
        or abs(buy_pressure - sell_pressure) >= 0.6
        or "IMBALANCE" in " ".join(depth_memory.get("reason_codes", []))
    )
    liquidation_candidate = False

    open_price = _first_float(official_candle.get("open"), market_truth_block.get("official_open"))
    price_advanced = False
    price_failed_to_advance = False
    if price is not None and open_price is not None:
        if delta > 0 and price > open_price:
            price_advanced = True
        elif delta < 0 and price < open_price:
            price_advanced = True
        elif delta != 0:
            price_failed_to_advance = True

    if aggressor_side == "BUYERS":
        who_attacked = "BUYERS"
    elif aggressor_side == "SELLERS":
        who_attacked = "SELLERS"
    elif delta == 0.0:
        who_attacked = "NONE"
    else:
        who_attacked = "UNKNOWN"

    if ar01.get("absorbed_side") in ("BUYERS", "SELLERS"):
        who_defended = ar01["absorbed_side"]
    elif absorption_candidate and who_attacked == "BUYERS":
        who_defended = "SELLERS"
    elif absorption_candidate and who_attacked == "SELLERS":
        who_defended = "BUYERS"
    elif liquidity_wall == "ASK_WALL" and who_attacked == "BUYERS":
        who_defended = "SELLERS"
    elif liquidity_wall == "BID_WALL" and who_attacked == "SELLERS":
        who_defended = "BUYERS"
    elif who_attacked == "NONE":
        who_defended = "NONE"
    else:
        who_defended = "UNKNOWN"

    why_price_moved: list[str] = []
    why_price_failed: list[str] = []
    if aggressive_buy_volume > aggressive_sell_volume:
        why_price_moved.append("AGGRESSIVE_BUYING_DOMINANT")
    if aggressive_sell_volume > aggressive_buy_volume:
        why_price_moved.append("AGGRESSIVE_SELLING_DOMINANT")
    if flow_persistence.get("persistence_label") in ("SUSTAINED_LONG_PRESSURE", "SUSTAINED_SHORT_PRESSURE"):
        why_price_moved.append(str(flow_persistence.get("persistence_label")))
    if liquidity_intelligence.get("dominant_real_side") in ("BID", "ASK"):
        why_price_moved.append(f"REAL_LIQUIDITY_{liquidity_intelligence.get('dominant_real_side')}")

    if absorption_candidate:
        why_price_failed.append("ABSORPTION_DETECTED")
    if spoof_candidate:
        why_price_failed.append("LIKELY_SPOOF_PRESENT")
    if who_defended in ("BUYERS", "SELLERS"):
        why_price_failed.append(f"DEFENDED_BY_{who_defended}")
    if flow_persistence.get("decay_risk"):
        why_price_failed.append("FLOW_DECAY_RISK")

    if price_advanced and who_attacked == "BUYERS":
        who_won = "BUYERS"
    elif price_advanced and who_attacked == "SELLERS":
        who_won = "SELLERS"
    elif price_failed_to_advance and who_attacked == "BUYERS":
        who_won = "SELLERS"
    elif price_failed_to_advance and who_attacked == "SELLERS":
        who_won = "BUYERS"
    elif who_attacked == "NONE":
        who_won = "BALANCED"
    else:
        who_won = liquidity_intelligence.get("dominant_real_side", "UNKNOWN")
        if who_won == "BID":
            who_won = "BUYERS"
        elif who_won == "ASK":
            who_won = "SELLERS"
        elif who_won == "BALANCED":
            who_won = "BALANCED"

    available_inputs = [name for name, payload in inputs.items() if payload is not None]
    missing_inputs = [name for name, payload in inputs.items() if payload is None]
    data_quality = _data_quality(available_inputs, missing_inputs)

    reason_codes = [
        f"SYMBOL_{symbol}",
        f"AGGRESSOR_{aggressor_side}",
        f"WAR_WINNER_{who_won}",
        f"LIQUIDITY_{liquidity_wall}",
        f"DQ_{data_quality['level']}",
        "NO_FAKE_DATA",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]
    if spoof_candidate:
        reason_codes.append("SPOOF_CANDIDATE_TRUE")
    if absorption_candidate:
        reason_codes.append("ABSORPTION_CANDIDATE_TRUE")
    if imbalance_candidate:
        reason_codes.append("IMBALANCE_CANDIDATE_TRUE")

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": "STATE_OBSERVATION_AGGREGATION",
            "input_files": [str(path).replace("\\", "/") for path in INPUT_PATHS.values()],
        },
        "market_snapshot": {
            "price": price,
            "bid_price": bid_price,
            "ask_price": ask_price,
            "bid_size": None,
            "ask_size": None,
            "spread": spread,
            "last_trade_price": last_trade_price,
            "trade_side": trade_side,
            "trade_size": trade_size,
        },
        "price": price,
        "bid_price": bid_price,
        "ask_price": ask_price,
        "bid_size": None,
        "ask_size": None,
        "spread": spread,
        "last_trade_price": last_trade_price,
        "trade_side": trade_side,
        "trade_size": trade_size,
        "aggression": {
            "aggressive_buy_volume": aggressive_buy_volume,
            "aggressive_sell_volume": aggressive_sell_volume,
            "delta": delta,
            "cumulative_delta": cumulative_delta,
            "aggressor_side": aggressor_side,
            "pressure_score": pressure_score,
            "evidence_score": evidence_score,
        },
        "aggressive_buy_volume": aggressive_buy_volume,
        "aggressive_sell_volume": aggressive_sell_volume,
        "delta": delta,
        "cumulative_delta": cumulative_delta,
        "volume_flow": volume_flow,
        "orderbook": {
            "orderbook_depth": orderbook_depth,
            "bid_wall": bid_wall,
            "ask_wall": ask_wall,
            "liquidity_wall": liquidity_wall,
            "wall_conclusion": wall_conclusion,
        },
        "orderbook_depth": orderbook_depth,
        "liquidity_wall": liquidity_wall,
        "micro_candidates": {
            "spoof_candidate": spoof_candidate,
            "absorption_candidate": absorption_candidate,
            "imbalance_candidate": imbalance_candidate,
            "liquidation_candidate": liquidation_candidate,
        },
        "spoof_candidate": spoof_candidate,
        "absorption_candidate": absorption_candidate,
        "imbalance_candidate": imbalance_candidate,
        "liquidation_candidate": liquidation_candidate,
        "war_reading": {
            "who_attacked": who_attacked,
            "who_defended": who_defended,
            "who_won": who_won,
            "price_advanced": price_advanced,
            "price_failed_to_advance": price_failed_to_advance,
            "why_price_moved": why_price_moved,
            "why_price_failed": why_price_failed,
        },
        "data_quality": data_quality,
        "reason_codes": reason_codes,
        "feeds_next": [
            "MTF_CANDLE_DNA_FACTORY",
            "SIGNAL_TAXONOMY_ENGINE",
            "EDGE_MATRIX",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_observation_factory() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    inputs = {name: _load_json(path) for name, path in INPUT_PATHS.items()}
    result = _build_observation(inputs)

    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, result)
    return result


def main() -> None:
    print(json.dumps(run_observation_factory(), indent=2))


if __name__ == "__main__":
    main()
