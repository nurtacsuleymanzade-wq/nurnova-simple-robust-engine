"""MTF Candle DNA Factory.

Builds multi-timeframe candle/footprint classifications from real observation
history and the existing 1s candle DNA state.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MTF_CANDLE_DNA_FACTORY"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OBSERVATION_HISTORY_PATH = DATA_DIR / "observation_factory_history.jsonl"
LATEST_OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
HYBRID_DNA_PATH = STATE_DIR / "latest_hybrid_candle_dna.json"
MARKET_TRUTH_PATH = STATE_DIR / "latest_market_truth.json"
FLOW_EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
FLOW_PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
LIQUIDITY_STRUCTURE_PATH = STATE_DIR / "latest_liquidity_structure.json"
DEPTH_MEMORY_PATH = STATE_DIR / "latest_depth_liquidity_memory.json"
WALL_LIFECYCLE_PATH = STATE_DIR / "latest_wall_lifecycle.json"
ATR_STATE_PATH = STATE_DIR / "latest_atr_state.json"

OUTPUT_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
HISTORY_PATH = DATA_DIR / "mtf_candle_dna_history.jsonl"

TIMEFRAMES: list[tuple[str, int | None]] = [
    ("sub_second", None),
    ("1s", 1),
    ("3s", 3),
    ("5s", 5),
    ("15s", 15),
    ("1m", 60),
    ("3m", 180),
    ("5m", 300),
    ("15m", 900),
    ("1h", 3600),
    ("4h", 14400),
    ("12h", 43200),
    ("1d", 86400),
]

SUPPORTED_CANDLE_CATEGORIES = [
    "NORMAL_BALANCED",
    "BUY_IMBALANCE",
    "SELL_IMBALANCE",
    "BUY_ABSORPTION",
    "SELL_ABSORPTION",
    "FAILED_AUCTION",
    "LIQUIDITY_SWEEP_UP",
    "LIQUIDITY_SWEEP_DOWN",
    "STOP_RUN_UP",
    "STOP_RUN_DOWN",
    "EXHAUSTION_BUY",
    "EXHAUSTION_SELL",
    "REVERSAL_CANDLE",
    "CONTINUATION_CANDLE",
    "TRAP_CANDLE",
    "UNKNOWN",
]


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


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _compute_volume_imbalance(buy_volume: float | None, sell_volume: float | None) -> tuple[float | None, list[str]]:
    if buy_volume is None or sell_volume is None:
        return None, ["NO_VOLUME_DATA"]
    if sell_volume > 0.0:
        return round(buy_volume / sell_volume, 8), []
    if buy_volume > 0.0 and sell_volume == 0.0:
        return None, ["SELL_VOLUME_ZERO"]
    if buy_volume == 0.0 and sell_volume == 0.0:
        return None, ["NO_VOLUME_DATA"]
    return None, ["NO_VOLUME_DATA"]


def _default_volatility(reason_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "atr_14": None,
        "atr_21": None,
        "true_range_latest": None,
        "atr_available": False,
        "atr_quality": "MISSING",
        "reason_codes": reason_codes or ["ATR_STATE_NOT_AVAILABLE"],
    }




def _observation_volume_metrics(record: dict[str, Any]) -> dict[str, Any]:
    volume_flow = record.get("volume_flow") or {}
    aggression = record.get("aggression") or {}
    reason_codes = list(volume_flow.get("reason_codes") or [])

    buy_volume = _safe_float(volume_flow.get("buy_volume"))
    if buy_volume is None:
        buy_volume = _safe_float(aggression.get("aggressive_buy_volume"))
    sell_volume = _safe_float(volume_flow.get("sell_volume"))
    if sell_volume is None:
        sell_volume = _safe_float(aggression.get("aggressive_sell_volume"))
    delta = _safe_float(volume_flow.get("delta"))
    if delta is None and buy_volume is not None and sell_volume is not None:
        delta = round(buy_volume - sell_volume, 8)
    if delta is None:
        delta = _safe_float(aggression.get("delta"))
    cumulative_delta = _safe_float(volume_flow.get("cumulative_delta"))
    if cumulative_delta is None:
        cumulative_delta = _safe_float(aggression.get("cumulative_delta"))

    if buy_volume is None or sell_volume is None or delta is None:
        if "MISSING_AGGRESSIVE_VOLUME_FIELDS" not in reason_codes:
            reason_codes.append("MISSING_AGGRESSIVE_VOLUME_FIELDS")
    if cumulative_delta is None:
        reason_codes.append("CUMULATIVE_DELTA_HISTORY_NOT_AVAILABLE")

    return {
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "delta": delta,
        "cumulative_delta": cumulative_delta,
        "total_volume": _safe_float(volume_flow.get("total_volume")),
        "aggressive_buy_trade_count": _safe_int(volume_flow.get("aggressive_buy_trade_count")),
        "aggressive_sell_trade_count": _safe_int(volume_flow.get("aggressive_sell_trade_count")),
        "avg_buy_trade_size": _safe_float(volume_flow.get("avg_buy_trade_size")),
        "avg_sell_trade_size": _safe_float(volume_flow.get("avg_sell_trade_size")),
        "source": volume_flow.get("source", "observation_factory"),
        "reason_codes": reason_codes,
    }


def _apply_atr_state(payload: dict[str, Any], tf_name: str, atr_state: dict[str, Any] | None) -> None:
    if not isinstance(payload, dict):
        return
    if not atr_state:
        payload["volatility"] = _default_volatility(["ATR_STATE_NOT_AVAILABLE"])
        return

    atr_tf = atr_state.get(tf_name)
    if not isinstance(atr_tf, dict):
        payload["volatility"] = _default_volatility(["ATR_TIMEFRAME_NOT_SUPPORTED"])
        return

    atr_14 = _safe_float(atr_tf.get("atr_14"))
    atr_21 = _safe_float(atr_tf.get("atr_21"))
    true_range_latest = _safe_float(atr_tf.get("true_range_latest"))
    reason_codes = list(atr_tf.get("reason_codes") or [])
    if not reason_codes:
        reason_codes = ["ATR_STATE_APPLIED"]

    payload["volatility"] = {
        "atr_14": atr_14,
        "atr_21": atr_21,
        "true_range_latest": true_range_latest,
        "atr_available": atr_14 is not None or atr_21 is not None,
        "atr_quality": atr_tf.get("atr_quality", "MISSING"),
        "reason_codes": reason_codes,
    }


def _direction_from_truth(candle_truth: str | None) -> str:
    if candle_truth in ("REAL_BULLISH", "WEAK_BULLISH", "FAKE_BULLISH"):
        return "BULLISH"
    if candle_truth in ("REAL_BEARISH", "WEAK_BEARISH", "FAKE_BEARISH"):
        return "BEARISH"
    if candle_truth == "BALANCED":
        return "BALANCED"
    return "UNKNOWN"


def _imbalance_ratio(buy_volume: float, sell_volume: float, delta: float) -> float:
    total = max(buy_volume + sell_volume, abs(delta), 0.0)
    if total <= 0:
        return 0.0
    return round(abs(delta) / total, 4)


def _empty_candle_category(reason_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "primary": "UNKNOWN",
        "secondary": [],
        "reason_codes": reason_codes or ["INSUFFICIENT_CANDLE_FIELDS"],
        "confidence": None,
        "is_trade_signal": False,
    }


def _empty_tf(tf: str, level: str = "MISSING", missing_fields: list[str] | None = None) -> dict[str, Any]:
    return {
        "tf": tf,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "volume": 0.0,
        "buy_volume": 0.0,
        "sell_volume": 0.0,
        "delta": 0.0,
        "cumulative_delta": None,
        "max_delta": 0.0,
        "min_delta": 0.0,
        "volume_imbalance": None,
        "aggressive_buy_trade_count": 0,
        "aggressive_sell_trade_count": 0,
        "avg_trade_size": None,
        "imbalance_count": 0,
        "absorption_count": 0,
        "wick_type": "UNKNOWN",
        "body_strength": "UNKNOWN",
        "close_position": "UNKNOWN",
        "structure_label": "UNKNOWN",
        "footprint_label": "UNKNOWN",
        "liquidity_event": "UNKNOWN" if level == "MISSING" else "NONE",
        "war_summary": {
            "dominant_side": "UNKNOWN",
            "aggression_result": "UNKNOWN",
            "candle_truth": "UNKNOWN",
        },
        "candle_category": _empty_candle_category(),
        "volatility": _default_volatility(["ATR_STATE_NOT_AVAILABLE"]),
        "source_sample_count": 0,
        "data_quality": {
            "level": level,
            "missing_fields": missing_fields or [
                "open",
                "high",
                "low",
                "close",
                "buy_volume",
                "sell_volume",
                "cumulative_delta",
            ],
        },
    }


def _load_observations() -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    if OBSERVATION_HISTORY_PATH.exists():
        try:
            for line in OBSERVATION_HISTORY_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                observations.append(record)
        except Exception:
            observations = []

    latest = _load_json(LATEST_OBSERVATION_PATH)
    if latest:
        latest_ts = latest.get("timestamp_utc")
        if not observations or observations[-1].get("timestamp_utc") != latest_ts:
            observations.append(latest)

    observations.sort(key=lambda item: item.get("timestamp_utc", ""))
    return observations


def _window(
    observations: list[dict[str, Any]],
    ref_time: datetime,
    window_seconds: int,
    offset_seconds: int = 0,
) -> list[dict[str, Any]]:
    end = ref_time - timedelta(seconds=offset_seconds)
    start = end - timedelta(seconds=window_seconds)
    selected: list[dict[str, Any]] = []
    for record in observations:
        ts = _parse_ts(record.get("timestamp_utc"))
        if ts is None:
            continue
        if start < ts <= end:
            selected.append(record)
    return selected


def _price_from_observation(record: dict[str, Any]) -> float | None:
    snapshot = record.get("market_snapshot") or {}
    return _safe_float(snapshot.get("price") or snapshot.get("last_trade_price"))


def _wick_type(open_: float | None, high: float | None, low: float | None, close: float | None) -> str:
    if None in (open_, high, low, close):
        return "UNKNOWN"
    candle_range = high - low
    if candle_range <= 0:
        return "NO_WICK"
    upper = high - max(open_, close)
    lower = min(open_, close) - low
    upper_present = upper > candle_range * 0.1
    lower_present = lower > candle_range * 0.1
    if upper_present and lower_present:
        return "DOUBLE_WICK"
    if upper_present:
        return "UPPER_WICK"
    if lower_present:
        return "LOWER_WICK"
    return "NO_WICK"


def _body_strength(open_: float | None, high: float | None, low: float | None, close: float | None) -> str:
    if None in (open_, high, low, close):
        return "UNKNOWN"
    candle_range = high - low
    body = abs(close - open_)
    if candle_range <= 0:
        return "DOJI" if body == 0 else "WEAK"
    ratio = body / candle_range
    if ratio < 0.05:
        return "DOJI"
    if ratio >= 0.6:
        return "STRONG"
    if ratio >= 0.3:
        return "MODERATE"
    return "WEAK"


def _close_position(high: float | None, low: float | None, close: float | None) -> str:
    if None in (high, low, close):
        return "UNKNOWN"
    candle_range = high - low
    if candle_range <= 0:
        return "MID"
    rel = (close - low) / candle_range
    if rel >= 0.75:
        return "NEAR_HIGH"
    if rel <= 0.25:
        return "NEAR_LOW"
    return "MID"


def _structure_label(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    liquidity_structure: dict[str, Any] | None,
) -> str:
    if current.get("high") is None or current.get("low") is None or current.get("close") is None:
        return "UNKNOWN"
    if previous and previous.get("high") is not None and previous.get("low") is not None and previous.get("close") is not None:
        if current["high"] > previous["high"] and current["close"] >= previous["close"]:
            return "HH"
        if current["low"] > previous["low"] and current["close"] >= previous["close"]:
            return "HL"
        if current["high"] < previous["high"] and current["close"] <= previous["close"]:
            return "LH"
        if current["low"] < previous["low"] and current["close"] <= previous["close"]:
            return "LL"
        return "RANGE"
    structure_bias = (((liquidity_structure or {}).get("structure") or {}).get("structure_bias"))
    if structure_bias == "RANGE":
        return "RANGE"
    return "UNKNOWN"


def _candle_truth(open_: float | None, close: float | None, delta: float) -> str:
    if open_ is None or close is None:
        return "UNKNOWN"
    if close > open_ and delta > 0:
        return "REAL_BULLISH"
    if close > open_ and delta < 0:
        return "FAKE_BULLISH"
    if close > open_ and delta == 0:
        return "WEAK_BULLISH"
    if close < open_ and delta < 0:
        return "REAL_BEARISH"
    if close < open_ and delta > 0:
        return "FAKE_BEARISH"
    if close < open_ and delta == 0:
        return "WEAK_BEARISH"
    return "BALANCED"


def _war_summary(
    open_: float | None,
    close: float | None,
    buy_volume: float,
    sell_volume: float,
    delta: float,
    absorption_count: int,
) -> dict[str, str]:
    if buy_volume > sell_volume or delta > 0:
        dominant = "BUYERS"
    elif sell_volume > buy_volume or delta < 0:
        dominant = "SELLERS"
    elif buy_volume == 0.0 and sell_volume == 0.0 and delta == 0.0:
        dominant = "UNKNOWN"
    else:
        dominant = "BALANCED"

    if absorption_count > 0:
        result = "ABSORBED"
    elif open_ is not None and close is not None and ((close > open_ and delta > 0) or (close < open_ and delta < 0)):
        result = "SUCCESS"
    elif open_ is not None and close is not None and ((close > open_ and delta <= 0) or (close < open_ and delta >= 0)):
        result = "FAILED"
    else:
        result = "UNKNOWN"

    return {
        "dominant_side": dominant,
        "aggression_result": result,
        "candle_truth": _candle_truth(open_, close, delta),
    }


def _footprint_label(open_: float | None, close: float | None, delta: float, absorption_count: int, imbalance_count: int) -> str:
    if open_ is None or close is None:
        return "UNKNOWN"
    if absorption_count > 0:
        return "ABSORPTION"
    if close > open_ and delta > 0:
        return "REAL_BUYING"
    if close < open_ and delta < 0:
        return "REAL_SELLING"
    if (close > open_ and delta <= 0) or (close < open_ and delta >= 0):
        return "TRAP"
    if imbalance_count > 0 or delta == 0:
        return "BALANCED"
    return "UNKNOWN"


def _liquidity_event(
    window_records: list[dict[str, Any]],
    wall_lifecycle: dict[str, Any] | None,
    depth_memory: dict[str, Any] | None,
) -> str:
    if any(((record.get("micro_candidates") or {}).get("spoof_candidate")) for record in window_records):
        return "SPOOF_RISK"
    if ((wall_lifecycle or {}).get("liquidity_intelligence") or {}).get("sweep_occurred"):
        return "SWEEP"
    wall_codes = " ".join((wall_lifecycle or {}).get("reason_codes", []))
    depth_codes = " ".join((depth_memory or {}).get("reason_codes", []))
    if "WALL" in wall_codes or "WALL" in depth_codes:
        return "WALL_REACTION"
    if not window_records:
        return "UNKNOWN"
    return "NONE"


def _quality_level(tf: str, sample_count: int, missing_fields: list[str], hybrid_available: bool) -> str:
    if sample_count == 0:
        return "MISSING"
    if tf == "1s" and hybrid_available and not missing_fields:
        return "HIGH"
    if tf == "sub_second" and not missing_fields:
        return "OK"
    if not missing_fields and sample_count >= 3:
        return "OK"
    if not missing_fields and sample_count >= 1:
        return "LOW"
    return "LOW"


def infer_wick_context(candle: dict[str, Any]) -> dict[str, bool]:
    wick_type = candle.get("wick_type", "UNKNOWN")
    close_position = candle.get("close_position", "UNKNOWN")
    return {
        "upper_probe": wick_type in ("UPPER_WICK", "DOUBLE_WICK"),
        "lower_probe": wick_type in ("LOWER_WICK", "DOUBLE_WICK"),
        "high_rejected": wick_type in ("UPPER_WICK", "DOUBLE_WICK") and close_position != "NEAR_HIGH",
        "low_recovered": wick_type in ("LOWER_WICK", "DOUBLE_WICK") and close_position != "NEAR_LOW",
    }


def infer_delta_price_relationship(candle: dict[str, Any]) -> dict[str, bool]:
    open_ = _safe_float(candle.get("open"))
    close = _safe_float(candle.get("close"))
    delta = _safe_float(candle.get("delta")) or 0.0
    candle_truth = ((candle.get("war_summary") or {}).get("candle_truth")) or "UNKNOWN"
    return {
        "price_up": open_ is not None and close is not None and close > open_,
        "price_down": open_ is not None and close is not None and close < open_,
        "delta_positive": delta > 0,
        "delta_negative": delta < 0,
        "bullish_alignment": candle_truth == "REAL_BULLISH",
        "bearish_alignment": candle_truth == "REAL_BEARISH",
        "bullish_divergence": candle_truth in ("WEAK_BULLISH", "FAKE_BULLISH"),
        "bearish_divergence": candle_truth in ("WEAK_BEARISH", "FAKE_BEARISH"),
        "price_progress_weak": candle.get("body_strength") in ("WEAK", "DOJI") or candle.get("close_position") == "MID",
    }


def infer_absorption_context(candle: dict[str, Any]) -> dict[str, bool]:
    wick_context = infer_wick_context(candle)
    buy_volume = _safe_float(candle.get("buy_volume")) or 0.0
    sell_volume = _safe_float(candle.get("sell_volume")) or 0.0
    delta = _safe_float(candle.get("delta")) or 0.0
    absorption_seen = int(candle.get("absorption_count", 0) or 0) > 0 or candle.get("footprint_label") == "ABSORPTION"
    return {
        "buy_absorption": absorption_seen and wick_context["lower_probe"] and sell_volume >= buy_volume and candle.get("close_position") != "NEAR_LOW",
        "sell_absorption": absorption_seen and wick_context["upper_probe"] and buy_volume >= sell_volume and candle.get("close_position") != "NEAR_HIGH",
        "absorption_seen": absorption_seen or (delta == 0.0 and candle.get("body_strength") == "DOJI"),
    }


def infer_sweep_context(candle: dict[str, Any]) -> dict[str, bool]:
    wick_context = infer_wick_context(candle)
    liquidity_event = candle.get("liquidity_event", "UNKNOWN")
    delta_relationship = infer_delta_price_relationship(candle)
    is_sweep_like = liquidity_event in ("SWEEP", "WALL_REACTION")
    return {
        "sweep_up": is_sweep_like and wick_context["upper_probe"] and candle.get("close_position") != "NEAR_HIGH",
        "sweep_down": is_sweep_like and wick_context["lower_probe"] and candle.get("close_position") != "NEAR_LOW",
        "stop_run_up": is_sweep_like and wick_context["upper_probe"] and wick_context["high_rejected"] and delta_relationship["delta_positive"],
        "stop_run_down": is_sweep_like and wick_context["lower_probe"] and wick_context["low_recovered"] and delta_relationship["delta_negative"],
    }


def classify_candle_category(
    candle: dict[str, Any],
    previous_candle: dict[str, Any] | None = None,
    persistence_direction: str | None = None,
) -> dict[str, Any]:
    required_fields = ("open", "high", "low", "close", "buy_volume", "sell_volume", "delta")
    missing = [field_name for field_name in required_fields if candle.get(field_name) is None]
    if missing:
        return _empty_candle_category([f"MISSING_{field_name.upper()}" for field_name in missing])

    wick_context = infer_wick_context(candle)
    delta_relationship = infer_delta_price_relationship(candle)
    absorption_context = infer_absorption_context(candle)
    sweep_context = infer_sweep_context(candle)

    open_ = _safe_float(candle.get("open")) or 0.0
    close = _safe_float(candle.get("close")) or 0.0
    high = _safe_float(candle.get("high")) or max(open_, close)
    low = _safe_float(candle.get("low")) or min(open_, close)
    buy_volume = _safe_float(candle.get("buy_volume")) or 0.0
    sell_volume = _safe_float(candle.get("sell_volume")) or 0.0
    delta = _safe_float(candle.get("delta")) or 0.0
    body_strength = candle.get("body_strength", "UNKNOWN")
    close_position = candle.get("close_position", "UNKNOWN")
    footprint_label = candle.get("footprint_label", "UNKNOWN")
    war_summary = candle.get("war_summary") or {}
    dominant_side = war_summary.get("dominant_side", "UNKNOWN")
    candle_truth = war_summary.get("candle_truth", "UNKNOWN")
    prior_truth = ((previous_candle or {}).get("war_summary") or {}).get("candle_truth", "UNKNOWN")
    imbalance_ratio = _imbalance_ratio(buy_volume, sell_volume, delta)
    candle_range = max(high - low, 0.0)
    progress_ratio = abs(close - open_) / candle_range if candle_range > 0 else 0.0

    primary = "UNKNOWN"
    secondary: list[str] = []
    reason_codes: list[str] = []

    balanced_delta = imbalance_ratio <= 0.15
    buy_imbalance = buy_volume > sell_volume and delta > 0 and (close_position == "NEAR_HIGH" or candle_truth in ("REAL_BULLISH", "WEAK_BULLISH"))
    sell_imbalance = sell_volume > buy_volume and delta < 0 and (close_position == "NEAR_LOW" or candle_truth in ("REAL_BEARISH", "WEAK_BEARISH"))
    failed_auction = (
        (wick_context["upper_probe"] or wick_context["lower_probe"])
        and close_position == "MID"
        and body_strength in ("DOJI", "WEAK")
    )
    trap_candle = (
        footprint_label == "TRAP"
        or ((buy_imbalance and delta_relationship["bearish_divergence"]) or (sell_imbalance and delta_relationship["bullish_divergence"]))
        and (failed_auction or absorption_context["absorption_seen"])
    )
    exhaustion_buy = delta > 0 and (wick_context["high_rejected"] or delta_relationship["bullish_divergence"]) and delta_relationship["price_progress_weak"]
    exhaustion_sell = delta < 0 and (wick_context["low_recovered"] or delta_relationship["bearish_divergence"]) and delta_relationship["price_progress_weak"]
    reversal_candle = (
        previous_candle is not None
        and _direction_from_truth(prior_truth) not in ("UNKNOWN", "BALANCED")
        and _direction_from_truth(prior_truth) != _direction_from_truth(candle_truth)
        and (failed_auction or absorption_context["absorption_seen"] or sweep_context["sweep_up"] or sweep_context["sweep_down"] or trap_candle)
    )
    continuation_candle = (
        body_strength in ("STRONG", "MODERATE")
        and (
            (previous_candle is not None and _direction_from_truth(prior_truth) == _direction_from_truth(candle_truth) and _direction_from_truth(candle_truth) in ("BULLISH", "BEARISH"))
            or (persistence_direction == "LONG" and candle_truth in ("REAL_BULLISH", "WEAK_BULLISH"))
            or (persistence_direction == "SHORT" and candle_truth in ("REAL_BEARISH", "WEAK_BEARISH"))
        )
        and close_position in ("NEAR_HIGH", "NEAR_LOW")
    )
    normal_balanced = (
        body_strength in ("WEAK", "DOJI")
        and balanced_delta
        and footprint_label in ("BALANCED", "UNKNOWN")
        and candle.get("liquidity_event") not in ("SWEEP", "WALL_REACTION")
        and not wick_context["upper_probe"]
        and not wick_context["lower_probe"]
    )

    if trap_candle:
        primary = "TRAP_CANDLE"
        reason_codes.extend(["IMBALANCE_CLOSES_AGAINST_SIDE", "TRAP_EVIDENCE_PRESENT"])
    elif sweep_context["stop_run_up"]:
        primary = "STOP_RUN_UP"
        reason_codes.extend(["UPPER_SWEEP_REJECTION", "DELTA_SPIKE_UP"])
    elif sweep_context["stop_run_down"]:
        primary = "STOP_RUN_DOWN"
        reason_codes.extend(["LOWER_SWEEP_RECOVERY", "DELTA_SPIKE_DOWN"])
    elif absorption_context["buy_absorption"]:
        primary = "BUY_ABSORPTION"
        reason_codes.extend(["LOWER_WICK_PRESENT", "SELL_PRESSURE_ABSORBED", "CLOSE_RECOVERED_FROM_LOW"])
    elif absorption_context["sell_absorption"]:
        primary = "SELL_ABSORPTION"
        reason_codes.extend(["UPPER_WICK_PRESENT", "BUY_PRESSURE_ABSORBED", "CLOSE_REJECTED_HIGH"])
    elif sweep_context["sweep_up"]:
        primary = "LIQUIDITY_SWEEP_UP"
        reason_codes.extend(["UPPER_PROBE", f"LIQUIDITY_EVENT_{candle.get('liquidity_event', 'UNKNOWN')}"])
    elif sweep_context["sweep_down"]:
        primary = "LIQUIDITY_SWEEP_DOWN"
        reason_codes.extend(["LOWER_PROBE", f"LIQUIDITY_EVENT_{candle.get('liquidity_event', 'UNKNOWN')}"])
    elif failed_auction:
        primary = "FAILED_AUCTION"
        reason_codes.extend(["LONG_WICK_PRESENT", "CLOSE_RETURNED_TO_RANGE"])
    elif exhaustion_buy:
        primary = "EXHAUSTION_BUY"
        reason_codes.extend(["POSITIVE_DELTA_WEAK_PROGRESS", "HIGH_REJECTION_PRESENT"])
    elif exhaustion_sell:
        primary = "EXHAUSTION_SELL"
        reason_codes.extend(["NEGATIVE_DELTA_WEAK_PROGRESS", "LOW_RECOVERY_PRESENT"])
    elif reversal_candle:
        primary = "REVERSAL_CANDLE"
        reason_codes.extend([f"PRIOR_{prior_truth}", f"CURRENT_{candle_truth}", "DIRECTION_CHANGED"])
    elif continuation_candle:
        primary = "CONTINUATION_CANDLE"
        reason_codes.extend([f"CURRENT_{candle_truth}", f"PERSISTENCE_{persistence_direction or 'UNKNOWN'}", "BODY_MEANINGFUL"])
    elif buy_imbalance:
        primary = "BUY_IMBALANCE"
        reason_codes.extend(["BUY_VOLUME_GT_SELL_VOLUME", "DELTA_POSITIVE", f"CLOSE_{close_position}"])
    elif sell_imbalance:
        primary = "SELL_IMBALANCE"
        reason_codes.extend(["SELL_VOLUME_GT_BUY_VOLUME", "DELTA_NEGATIVE", f"CLOSE_{close_position}"])
    elif normal_balanced:
        primary = "NORMAL_BALANCED"
        reason_codes.extend(["WEAK_BODY", "BALANCED_DELTA", "NO_SWEEP_OR_WICK_EVENT"])
    else:
        primary = "UNKNOWN"
        reason_codes.extend(["NO_CLEAR_CATEGORY_MATCH", f"FOOTPRINT_{footprint_label}", f"DOMINANT_{dominant_side}"])

    if buy_imbalance and primary != "BUY_IMBALANCE":
        secondary.append("BUY_IMBALANCE")
    if sell_imbalance and primary != "SELL_IMBALANCE":
        secondary.append("SELL_IMBALANCE")
    if failed_auction and primary != "FAILED_AUCTION":
        secondary.append("FAILED_AUCTION")
    if reversal_candle and primary != "REVERSAL_CANDLE":
        secondary.append("REVERSAL_CANDLE")
    if continuation_candle and primary != "CONTINUATION_CANDLE":
        secondary.append("CONTINUATION_CANDLE")

    base_confidence = 0.25 if primary == "UNKNOWN" else 0.45
    if len(reason_codes) >= 4:
        base_confidence = 0.85
    elif len(reason_codes) == 3:
        base_confidence = 0.7
    elif len(reason_codes) == 2:
        base_confidence = 0.6
    elif len(reason_codes) == 1:
        base_confidence = 0.45

    dq_level = ((candle.get("data_quality") or {}).get("level")) or "LOW"
    if dq_level in ("LOW", "MISSING"):
        base_confidence = min(base_confidence, 0.55)
    confidence = round(base_confidence, 4) if primary != "UNKNOWN" or reason_codes else None

    return {
        "primary": primary,
        "secondary": secondary,
        "reason_codes": reason_codes,
        "confidence": confidence,
        "is_trade_signal": False,
    }


def _previous_candle_from_records(previous_window_records: list[dict[str, Any]], tf: str) -> dict[str, Any] | None:
    if not previous_window_records:
        return None
    prices = [_price_from_observation(record) for record in previous_window_records]
    valid_prices = [price for price in prices if price is not None]
    if not valid_prices:
        return None

    buy_volume = 0.0
    sell_volume = 0.0
    deltas: list[float] = []
    absorption_count = 0
    imbalance_count = 0
    for record in previous_window_records:
        volume_metrics = _observation_volume_metrics(record)
        micro_candidates = record.get("micro_candidates") or {}
        buy_volume += _safe_float(volume_metrics.get("buy_volume")) or 0.0
        sell_volume += _safe_float(volume_metrics.get("sell_volume")) or 0.0
        deltas.append(_safe_float(volume_metrics.get("delta")) or 0.0)
        if micro_candidates.get("absorption_candidate"):
            absorption_count += 1
        if micro_candidates.get("imbalance_candidate"):
            imbalance_count += 1

    open_ = valid_prices[0]
    close = valid_prices[-1]
    high = max(valid_prices)
    low = min(valid_prices)
    delta = round(sum(deltas), 8)
    previous_candle = {
        "tf": tf,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "buy_volume": round(buy_volume, 8),
        "sell_volume": round(sell_volume, 8),
        "delta": delta,
        "wick_type": _wick_type(open_, high, low, close),
        "body_strength": _body_strength(open_, high, low, close),
        "close_position": _close_position(high, low, close),
        "footprint_label": _footprint_label(open_, close, delta, absorption_count, imbalance_count),
        "liquidity_event": "NONE",
        "war_summary": _war_summary(open_, close, buy_volume, sell_volume, delta, absorption_count),
        "absorption_count": absorption_count,
        "imbalance_count": imbalance_count,
        "data_quality": {"level": "OK", "missing_fields": []},
    }
    previous_candle["candle_category"] = classify_candle_category(previous_candle)
    return previous_candle


def _build_from_window(
    tf: str,
    window_records: list[dict[str, Any]],
    previous_window_records: list[dict[str, Any]],
    liquidity_structure: dict[str, Any] | None,
    depth_memory: dict[str, Any] | None,
    wall_lifecycle: dict[str, Any] | None,
    persistence_direction: str | None,
    hybrid_available: bool = False,
) -> dict[str, Any]:
    if not window_records:
        return _empty_tf(tf)

    prices = [_price_from_observation(record) for record in window_records]
    valid_prices = [price for price in prices if price is not None]

    buy_volume = 0.0
    sell_volume = 0.0
    deltas: list[float] = []
    cumulative_delta_values: list[float] = []
    aggressive_buy_trade_count = 0
    aggressive_sell_trade_count = 0
    imbalance_count = 0
    absorption_count = 0
    missing_fields: set[str] = set()
    seen_missing_aggressive_volume = False
    seen_missing_cumulative_delta = False
    for record in window_records:
        volume_metrics = _observation_volume_metrics(record)
        micro_candidates = record.get("micro_candidates") or {}
        if "MISSING_AGGRESSIVE_VOLUME_FIELDS" in volume_metrics.get("reason_codes", []):
            seen_missing_aggressive_volume = True
        if "CUMULATIVE_DELTA_HISTORY_NOT_AVAILABLE" in volume_metrics.get("reason_codes", []):
            seen_missing_cumulative_delta = True

        record_buy_volume = _safe_float(volume_metrics.get("buy_volume"))
        record_sell_volume = _safe_float(volume_metrics.get("sell_volume"))
        record_delta = _safe_float(volume_metrics.get("delta"))
        record_cumulative_delta = _safe_float(volume_metrics.get("cumulative_delta"))
        record_buy_trade_count = _safe_int(volume_metrics.get("aggressive_buy_trade_count"))
        record_sell_trade_count = _safe_int(volume_metrics.get("aggressive_sell_trade_count"))

        if record_buy_volume is None:
            missing_fields.add("buy_volume")
            record_buy_volume = 0.0
        if record_sell_volume is None:
            missing_fields.add("sell_volume")
            record_sell_volume = 0.0
        if record_delta is None:
            missing_fields.add("delta")
            record_delta = round(record_buy_volume - record_sell_volume, 8)
        if record_cumulative_delta is not None:
            cumulative_delta_values.append(record_cumulative_delta)
        if record_buy_trade_count is None:
            record_buy_trade_count = 0
            missing_fields.add("aggressive_buy_trade_count")
        if record_sell_trade_count is None:
            record_sell_trade_count = 0
            missing_fields.add("aggressive_sell_trade_count")

        buy_volume += record_buy_volume
        sell_volume += record_sell_volume
        deltas.append(record_delta)
        aggressive_buy_trade_count += record_buy_trade_count
        aggressive_sell_trade_count += record_sell_trade_count
        if micro_candidates.get("imbalance_candidate"):
            imbalance_count += 1
        if micro_candidates.get("absorption_candidate"):
            absorption_count += 1

    open_ = valid_prices[0] if valid_prices else None
    close = valid_prices[-1] if valid_prices else None
    high = max(valid_prices) if valid_prices else None
    low = min(valid_prices) if valid_prices else None
    buy_volume = round(buy_volume, 8)
    sell_volume = round(sell_volume, 8)
    volume = round(buy_volume + sell_volume, 8)
    delta = round(sum(deltas), 8)
    max_delta = round(max(deltas), 8) if deltas else 0.0
    min_delta = round(min(deltas), 8) if deltas else 0.0
    if cumulative_delta_values:
        cumulative_delta = round(cumulative_delta_values[-1], 8)
    elif deltas:
        cumulative_delta = round(delta, 8)
        missing_fields.add("cumulative_delta")
    else:
        cumulative_delta = None
        missing_fields.add("cumulative_delta")
    volume_imbalance, volume_imbalance_reasons = _compute_volume_imbalance(buy_volume, sell_volume)
    if volume_imbalance is None:
        missing_fields.add("volume_imbalance")
    total_trade_count = aggressive_buy_trade_count + aggressive_sell_trade_count
    avg_trade_size = round(volume / total_trade_count, 8) if total_trade_count > 0 and volume > 0.0 else None
    if total_trade_count == 0:
        missing_fields.add("avg_trade_size")

    previous_summary = None
    if previous_window_records:
        prev_prices = [_price_from_observation(record) for record in previous_window_records]
        prev_valid_prices = [price for price in prev_prices if price is not None]
        if prev_valid_prices:
            previous_summary = {
                "high": max(prev_valid_prices),
                "low": min(prev_valid_prices),
                "close": prev_valid_prices[-1],
            }

    payload = {
        "tf": tf,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "delta": delta,
        "cumulative_delta": cumulative_delta,
        "max_delta": max_delta,
        "min_delta": min_delta,
        "volume_imbalance": volume_imbalance,
        "aggressive_buy_trade_count": aggressive_buy_trade_count,
        "aggressive_sell_trade_count": aggressive_sell_trade_count,
        "avg_trade_size": avg_trade_size,
        "imbalance_count": imbalance_count,
        "absorption_count": absorption_count,
        "wick_type": _wick_type(open_, high, low, close),
        "body_strength": _body_strength(open_, high, low, close),
        "close_position": _close_position(high, low, close),
        "structure_label": "UNKNOWN",
        "footprint_label": _footprint_label(open_, close, delta, absorption_count, imbalance_count),
        "liquidity_event": _liquidity_event(window_records, wall_lifecycle, depth_memory),
        "war_summary": _war_summary(open_, close, buy_volume, sell_volume, delta, absorption_count),
        "candle_category": _empty_candle_category(),
        "volatility": _default_volatility(["ATR_STATE_NOT_AVAILABLE"]),
        "source_sample_count": len(window_records),
        "data_quality": {
            "level": "MISSING",
            "missing_fields": [],
        },
    }
    payload["structure_label"] = _structure_label(payload, previous_summary, liquidity_structure)

    missing_ohlc_fields = [
        field_name
        for field_name in ("open", "high", "low", "close")
        if payload.get(field_name) is None
    ]
    if seen_missing_aggressive_volume:
        missing_fields.update({"buy_volume", "sell_volume", "delta"})
    if seen_missing_cumulative_delta:
        missing_fields.add("cumulative_delta")
    if any(code in ("SELL_VOLUME_ZERO", "NO_VOLUME_DATA") for code in volume_imbalance_reasons):
        missing_fields.add("volume_imbalance")
    combined_missing_fields = missing_ohlc_fields + sorted(missing_fields)
    payload["data_quality"] = {
        "level": _quality_level(tf, len(window_records), combined_missing_fields, hybrid_available),
        "missing_fields": combined_missing_fields,
    }
    previous_candle = _previous_candle_from_records(previous_window_records, tf)
    payload["candle_category"] = classify_candle_category(payload, previous_candle, persistence_direction)
    return payload


def _build_one_second(
    latest_observation: dict[str, Any] | None,
    hybrid_dna: dict[str, Any] | None,
    liquidity_structure: dict[str, Any] | None,
    depth_memory: dict[str, Any] | None,
    wall_lifecycle: dict[str, Any] | None,
    previous_window_records: list[dict[str, Any]],
    persistence_direction: str | None,
) -> dict[str, Any]:
    observation = latest_observation or {}
    volume_flow = observation.get("volume_flow") or {}
    aggression = observation.get("aggression") or {}
    micro_candidates = observation.get("micro_candidates") or {}
    official_candle = (hybrid_dna or {}).get("official_candle") or {}

    open_ = _safe_float(official_candle.get("open"))
    high = _safe_float(official_candle.get("high"))
    low = _safe_float(official_candle.get("low"))
    close = _safe_float(official_candle.get("close"))
    buy_volume = _safe_float(volume_flow.get("buy_volume"))
    if buy_volume is None:
        buy_volume = _safe_float(aggression.get("aggressive_buy_volume"))
    sell_volume = _safe_float(volume_flow.get("sell_volume"))
    if sell_volume is None:
        sell_volume = _safe_float(aggression.get("aggressive_sell_volume"))
    delta = _safe_float(volume_flow.get("delta"))
    if delta is None and buy_volume is not None and sell_volume is not None:
        delta = round(buy_volume - sell_volume, 8)
    if delta is None:
        delta = _safe_float(aggression.get("delta"))
    cumulative_delta = _safe_float(volume_flow.get("cumulative_delta"))
    if cumulative_delta is None:
        cumulative_delta = _safe_float(aggression.get("cumulative_delta"))
    buy_volume = round(buy_volume or 0.0, 8)
    sell_volume = round(sell_volume or 0.0, 8)
    delta = round(delta or 0.0, 8)
    volume = _safe_float(official_candle.get("volume"))
    if volume is None or volume == 0.0:
        volume = round(buy_volume + sell_volume, 8)
    volume_imbalance, volume_imbalance_reasons = _compute_volume_imbalance(buy_volume, sell_volume)
    aggressive_buy_trade_count = _safe_int(volume_flow.get("aggressive_buy_trade_count")) or 0
    aggressive_sell_trade_count = _safe_int(volume_flow.get("aggressive_sell_trade_count")) or 0
    total_trade_count = aggressive_buy_trade_count + aggressive_sell_trade_count
    avg_trade_size = round(volume / total_trade_count, 8) if total_trade_count > 0 and volume > 0.0 else None

    payload = {
        "tf": "1s",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "delta": delta,
        "cumulative_delta": round(cumulative_delta, 8) if cumulative_delta is not None else None,
        "max_delta": delta,
        "min_delta": delta,
        "volume_imbalance": volume_imbalance,
        "aggressive_buy_trade_count": aggressive_buy_trade_count,
        "aggressive_sell_trade_count": aggressive_sell_trade_count,
        "avg_trade_size": avg_trade_size,
        "imbalance_count": 1 if micro_candidates.get("imbalance_candidate") else 0,
        "absorption_count": 1 if micro_candidates.get("absorption_candidate") else 0,
        "wick_type": _wick_type(open_, high, low, close),
        "body_strength": _body_strength(open_, high, low, close),
        "close_position": _close_position(high, low, close),
        "structure_label": _structure_label(
            {"open": open_, "high": high, "low": low, "close": close},
            None,
            liquidity_structure,
        ),
        "footprint_label": _footprint_label(
            open_,
            close,
            delta,
            1 if micro_candidates.get("absorption_candidate") else 0,
            1 if micro_candidates.get("imbalance_candidate") else 0,
        ),
        "liquidity_event": _liquidity_event([observation] if observation else [], wall_lifecycle, depth_memory),
        "war_summary": _war_summary(
            open_,
            close,
            buy_volume,
            sell_volume,
            delta,
            1 if micro_candidates.get("absorption_candidate") else 0,
        ),
        "candle_category": _empty_candle_category(),
        "volatility": _default_volatility(["ATR_STATE_NOT_AVAILABLE"]),
        "source_sample_count": 1 if latest_observation else 0,
        "data_quality": {
            "level": "MISSING",
            "missing_fields": [],
        },
    }
    missing_fields = [field_name for field_name in ("open", "high", "low", "close") if payload.get(field_name) is None]
    if "MISSING_AGGRESSIVE_VOLUME_FIELDS" in volume_flow.get("reason_codes", []):
        missing_fields.extend(["buy_volume", "sell_volume", "delta"])
    if payload.get("cumulative_delta") is None:
        missing_fields.append("cumulative_delta")
    if any(code in ("SELL_VOLUME_ZERO", "NO_VOLUME_DATA") for code in volume_imbalance_reasons):
        missing_fields.append("volume_imbalance")
    if total_trade_count == 0:
        missing_fields.extend(["aggressive_buy_trade_count", "aggressive_sell_trade_count", "avg_trade_size"])
    payload["data_quality"] = {
        "level": _quality_level("1s", payload["source_sample_count"], missing_fields, bool(hybrid_dna)),
        "missing_fields": missing_fields,
    }
    previous_candle = _previous_candle_from_records(previous_window_records, "1s")
    payload["candle_category"] = classify_candle_category(payload, previous_candle, persistence_direction)
    return payload


def _build_summary(timeframes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    low_quality = [
        tf_name
        for tf_name, payload in timeframes.items()
        if (payload.get("data_quality") or {}).get("level") in ("LOW", "MISSING")
    ]
    produced = [tf_name for tf_name, payload in timeframes.items() if payload.get("source_sample_count", 0) > 0]
    standard_tfs = [tf_name for tf_name in timeframes if tf_name != "sub_second"]
    standard_produced = [tf_name for tf_name in standard_tfs if timeframes[tf_name].get("source_sample_count", 0) > 0]
    return {
        "total_timeframes": len(timeframes),
        "produced_timeframes": len(produced),
        "total_standard_timeframes": len(standard_tfs),
        "produced_standard_timeframes": len(standard_produced),
        "low_quality_timeframes": low_quality,
        "generated_timeframes": list(timeframes.keys()),
    }


def _overall_data_quality(timeframes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    quality_levels = [(payload.get("data_quality") or {}).get("level", "MISSING") for payload in timeframes.values()]
    missing = [tf_name for tf_name, payload in timeframes.items() if (payload.get("data_quality") or {}).get("level") == "MISSING"]
    low = [tf_name for tf_name, payload in timeframes.items() if (payload.get("data_quality") or {}).get("level") == "LOW"]
    if all(level == "MISSING" for level in quality_levels):
        level = "MISSING"
    elif missing:
        level = "LOW"
    elif low:
        level = "LOW"
    elif all(level == "HIGH" for level in quality_levels if level):
        level = "HIGH"
    else:
        level = "OK"
    score_map = {"HIGH": 1.0, "OK": 0.75, "LOW": 0.4, "MISSING": 0.0}
    return {
        "level": level,
        "score": score_map[level],
        "missing_timeframes": missing,
        "low_quality_timeframes": low,
    }


def run_mtf_candle_dna_factory() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    observations = _load_observations()
    latest_observation = _load_json(LATEST_OBSERVATION_PATH)
    hybrid_dna = _load_json(HYBRID_DNA_PATH)
    market_truth = _load_json(MARKET_TRUTH_PATH)
    flow_evidence = _load_json(FLOW_EVIDENCE_PATH)
    flow_persistence = _load_json(FLOW_PERSISTENCE_PATH)
    liquidity_structure = _load_json(LIQUIDITY_STRUCTURE_PATH)
    depth_memory = _load_json(DEPTH_MEMORY_PATH)
    wall_lifecycle = _load_json(WALL_LIFECYCLE_PATH)
    atr_state = _load_json(ATR_STATE_PATH)

    symbol = (
        (latest_observation or {}).get("symbol")
        or (hybrid_dna or {}).get("symbol")
        or (market_truth or {}).get("symbol")
        or "BTCUSDT"
    )
    latest_ts = _parse_ts((latest_observation or {}).get("timestamp_utc")) or datetime.now(timezone.utc)
    persistence_direction = (flow_persistence or {}).get("direction_label")

    timeframes: dict[str, dict[str, Any]] = {}
    timeframes["sub_second"] = _build_from_window(
        "sub_second",
        [latest_observation] if latest_observation else [],
        [],
        liquidity_structure,
        depth_memory,
        wall_lifecycle,
        persistence_direction,
    )
    previous_one_second_window = _window(observations, latest_ts, 1, offset_seconds=1)
    timeframes["1s"] = _build_one_second(
        latest_observation,
        hybrid_dna,
        liquidity_structure,
        depth_memory,
        wall_lifecycle,
        previous_one_second_window,
        persistence_direction,
    )

    for tf_name, window_seconds in TIMEFRAMES[2:]:
        if window_seconds is None:
            continue
        current_window = _window(observations, latest_ts, window_seconds)
        previous_window = _window(observations, latest_ts, window_seconds, offset_seconds=window_seconds)
        timeframes[tf_name] = _build_from_window(
            tf_name,
            current_window,
            previous_window,
            liquidity_structure,
            depth_memory,
            wall_lifecycle,
            persistence_direction,
        )

    for tf_name, payload in timeframes.items():
        _apply_atr_state(payload, tf_name, atr_state)
        volatility = payload.get("volatility") or {}
        candle_category = payload.get("candle_category") or {}
        payload["atr_14"] = volatility.get("atr_14")
        payload["atr_21"] = volatility.get("atr_21")
        payload["quality"] = (payload.get("data_quality") or {}).get("level")
        payload["reason_codes"] = sorted(
            set(
                [
                    *list((payload.get("data_quality") or {}).get("missing_fields") or []),
                    *list(candle_category.get("reason_codes") or []),
                    *list(volatility.get("reason_codes") or []),
                ]
            )
        )
        payload["candle_category_label"] = candle_category.get("primary", "UNKNOWN")

    summary = _build_summary(timeframes)
    data_quality = _overall_data_quality(timeframes)

    available_inputs = [
        name
        for name, payload in {
            "observation_history": observations if observations else None,
            "latest_observation": latest_observation,
            "hybrid_dna": hybrid_dna,
            "market_truth": market_truth,
            "flow_evidence": flow_evidence,
            "flow_persistence": flow_persistence,
            "liquidity_structure": liquidity_structure,
            "depth_memory": depth_memory,
            "wall_lifecycle": wall_lifecycle,
            "atr_state": atr_state,
        }.items()
        if payload is not None
    ]
    missing_inputs = [
        name
        for name, payload in {
            "observation_history": observations if observations else None,
            "latest_observation": latest_observation,
            "hybrid_dna": hybrid_dna,
            "market_truth": market_truth,
            "flow_evidence": flow_evidence,
            "flow_persistence": flow_persistence,
            "liquidity_structure": liquidity_structure,
            "depth_memory": depth_memory,
            "wall_lifecycle": wall_lifecycle,
            "atr_state": atr_state,
        }.items()
        if payload is None
    ]

    result: dict[str, Any] = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": "OBSERVATION_HISTORY_AGGREGATION",
            "latest_reference_ts": latest_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "supported_candle_categories": SUPPORTED_CANDLE_CATEGORIES,
        "summary": summary,
        "data_quality": {
            **data_quality,
            "available_inputs": available_inputs,
            "missing_inputs": missing_inputs,
        },
        "reason_codes": [
            f"SYMBOL_{symbol}",
            f"TF_TOTAL_{summary['total_timeframes']}",
            f"TF_STANDARD_{summary['produced_standard_timeframes']}_{summary['total_standard_timeframes']}",
            f"DQ_{data_quality['level']}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "feeds_next": [
            "MARKET_STRUCTURE_ENGINE",
            "LIQUIDITY_MAP_ENGINE",
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
    result.update(timeframes)

    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, result)
    return result


def main() -> None:
    print(json.dumps(run_mtf_candle_dna_factory(), indent=2))


if __name__ == "__main__":
    main()
