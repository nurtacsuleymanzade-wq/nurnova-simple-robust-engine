"""S28 — Market Structure V2 Engine.

Read-only. Produces objective 1m/5m/15m market structure context:
HH/HL/LH/LL, BOS, CHoCH, range, equal highs/lows, liquidity sweep, reclaim.
No fake signals. No real trades. safe_to_open_real_trade always False.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S28_MARKET_STRUCTURE_V2"
SYMBOL = "BTCUSDT"

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

LATEST_STATE_PATH = STATE_DIR / "latest_market_structure_v2.json"
S28_STATE_PATH = STATE_DIR / "s28_market_structure_v2_state.json"
HISTORY_PATH = DATA_DIR / "market_structure_v2_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s28_market_structure_v2_latest_report.md"

LIVE_FLOW_JSONL = DATA_DIR / "live_flow_events.jsonl"
FLOW_EVIDENCE_JSONL = DATA_DIR / "flow_evidence_history.jsonl"
FLOW_PERSISTENCE_JSONL = DATA_DIR / "flow_persistence_history.jsonl"
LATEST_FLOW_STATE = STATE_DIR / "latest_flow_state.json"
LATEST_FLOW_EVIDENCE = STATE_DIR / "latest_flow_evidence.json"
LATEST_FLOW_PERSISTENCE = STATE_DIR / "latest_flow_persistence.json"
LATEST_LIQUIDITY_MEMORY = STATE_DIR / "latest_depth_liquidity_memory.json"
LATEST_FLOW_QUALITY = STATE_DIR / "latest_live_flow_quality_audit.json"
LATEST_CHAIN_AUDIT = STATE_DIR / "latest_full_chain_truth_audit.json"
LATEST_HYBRID_DNA = STATE_DIR / "latest_hybrid_candle_dna.json"
HYBRID_DNA_JSONL = DATA_DIR / "hybrid_candle_dna_history.jsonl"
LATEST_MARKET_TRUTH = STATE_DIR / "latest_market_truth.json"
MARKET_TRUTH_JSONL = DATA_DIR / "market_truth_history.jsonl"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

MIN_CANDLES_RECOMMENDED = 20
SWING_LOOKBACK = 2          # candles left/right for swing detection
EQUAL_LEVEL_TOLERANCE = 0.001  # 0.1% tolerance for equal highs/lows
MAX_FLOW_RECORDS = 2000


# --------------------------------------------------------------------------- #
# I/O helpers
# --------------------------------------------------------------------------- #

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_jsonl_tail(path: Path, max_records: int = MAX_FLOW_RECORDS) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        records: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records[-max_records:]
    except Exception:
        return []


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Candle building
# --------------------------------------------------------------------------- #

def _extract_price_from_flow_record(rec: dict[str, Any]) -> float | None:
    for key in ("price", "close", "last_price", "mid_price", "bid", "ask"):
        val = rec.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def _extract_timestamp_from_flow_record(rec: dict[str, Any]) -> float | None:
    for key in ("timestamp_utc", "timestamp", "ts", "event_time"):
        val = rec.get(key)
        if val is None:
            continue
        try:
            if isinstance(val, (int, float)):
                ts = float(val)
                # milliseconds epoch
                if ts > 1e12:
                    ts /= 1000
                return ts
            if isinstance(val, str):
                # ISO format
                val = val.rstrip("Z").replace("T", " ")
                dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                return dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass
    return None


def build_1m_candles_from_flow(flow_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive 1m OHLCV candles from timestamped flow price records."""
    ticks: list[tuple[float, float]] = []
    for rec in flow_records:
        ts = _extract_timestamp_from_flow_record(rec)
        price = _extract_price_from_flow_record(rec)
        if ts is not None and price is not None and price > 0:
            ticks.append((ts, price))

    if not ticks:
        return []

    ticks.sort(key=lambda x: x[0])

    candles: dict[int, dict[str, Any]] = {}
    for ts, price in ticks:
        minute_key = int(ts // 60)
        if minute_key not in candles:
            candles[minute_key] = {
                "open": price, "high": price, "low": price,
                "close": price, "volume": 0.0,
                "ts": minute_key * 60,
            }
        else:
            c = candles[minute_key]
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price

    return [candles[k] for k in sorted(candles)]


def aggregate_candles(candles_1m: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
    """Aggregate 1m candles into N-minute candles."""
    if not candles_1m:
        return []
    result: list[dict[str, Any]] = []
    bucket: list[dict[str, Any]] = []
    base_ts = candles_1m[0]["ts"]

    for c in candles_1m:
        bucket_idx = int((c["ts"] - base_ts) // (minutes * 60))
        while len(result) <= bucket_idx:
            result.append({})

        if not result[bucket_idx]:
            result[bucket_idx] = {
                "open": c["open"], "high": c["high"],
                "low": c["low"], "close": c["close"],
                "volume": c.get("volume", 0.0),
                "ts": (base_ts + bucket_idx * minutes * 60),
            }
        else:
            r = result[bucket_idx]
            r["high"] = max(r["high"], c["high"])
            r["low"] = min(r["low"], c["low"])
            r["close"] = c["close"]
            r["volume"] = r.get("volume", 0.0) + c.get("volume", 0.0)

    return [r for r in result if r]


# --------------------------------------------------------------------------- #
# Swing detection
# --------------------------------------------------------------------------- #

def detect_swing_highs(candles: list[dict[str, Any]], lookback: int = SWING_LOOKBACK) -> list[dict[str, Any]]:
    swings: list[dict[str, Any]] = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        h = candles[i]["high"]
        is_swing = all(h > candles[i - j]["high"] for j in range(1, lookback + 1)) and \
                   all(h > candles[i + j]["high"] for j in range(1, lookback + 1))
        if is_swing:
            swings.append({"index": i, "price": h, "ts": candles[i].get("ts", 0)})
    return swings


def detect_swing_lows(candles: list[dict[str, Any]], lookback: int = SWING_LOOKBACK) -> list[dict[str, Any]]:
    swings: list[dict[str, Any]] = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        l = candles[i]["low"]
        is_swing = all(l < candles[i - j]["low"] for j in range(1, lookback + 1)) and \
                   all(l < candles[i + j]["low"] for j in range(1, lookback + 1))
        if is_swing:
            swings.append({"index": i, "price": l, "ts": candles[i].get("ts", 0)})
    return swings


# --------------------------------------------------------------------------- #
# Structure sequence
# --------------------------------------------------------------------------- #

def detect_sequence(swing_highs: list[dict[str, Any]], swing_lows: list[dict[str, Any]]) -> str:
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "INSUFFICIENT_SEQUENCE"

    last_highs = swing_highs[-3:]
    last_lows = swing_lows[-3:]

    hh = all(last_highs[i]["price"] > last_highs[i - 1]["price"] for i in range(1, len(last_highs)))
    hl = all(last_lows[i]["price"] > last_lows[i - 1]["price"] for i in range(1, len(last_lows)))
    lh = all(last_highs[i]["price"] < last_highs[i - 1]["price"] for i in range(1, len(last_highs)))
    ll = all(last_lows[i]["price"] < last_lows[i - 1]["price"] for i in range(1, len(last_lows)))

    if hh and hl:
        return "HH_HL_SEQUENCE"
    if lh and ll:
        return "LH_LL_SEQUENCE"
    if not hh and not hl and not lh and not ll:
        return "RANGE_SEQUENCE"
    return "MIXED_SEQUENCE"


def detect_bias(sequence: str) -> str:
    mapping = {
        "HH_HL_SEQUENCE": "BULLISH_STRUCTURE",
        "LH_LL_SEQUENCE": "BEARISH_STRUCTURE",
        "RANGE_SEQUENCE": "RANGE_STRUCTURE",
        "MIXED_SEQUENCE": "TRANSITION_STRUCTURE",
        "INSUFFICIENT_SEQUENCE": "INSUFFICIENT_DATA",
    }
    return mapping.get(sequence, "UNCLEAR_STRUCTURE")


# --------------------------------------------------------------------------- #
# BOS / CHoCH
# --------------------------------------------------------------------------- #

def detect_bos(candles: list[dict[str, Any]], swing_highs: list[dict[str, Any]], swing_lows: list[dict[str, Any]]) -> str:
    if not candles or (len(swing_highs) < 1 and len(swing_lows) < 1):
        return "INSUFFICIENT_DATA"

    latest_close = candles[-1]["close"]

    if swing_highs:
        prev_high = swing_highs[-1]["price"]
        if latest_close > prev_high:
            return "BULLISH_BOS"

    if swing_lows:
        prev_low = swing_lows[-1]["price"]
        if latest_close < prev_low:
            return "BEARISH_BOS"

    return "NO_BOS"


def detect_choch(sequence: str, bos: str) -> str:
    if sequence == "INSUFFICIENT_SEQUENCE" or bos == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_DATA"
    # CHoCH: bullish structure broken by bearish BOS, or vice versa
    if sequence == "HH_HL_SEQUENCE" and bos == "BEARISH_BOS":
        return "BEARISH_CHOCH"
    if sequence == "LH_LL_SEQUENCE" and bos == "BULLISH_BOS":
        return "BULLISH_CHOCH"
    return "NO_CHOCH"


# --------------------------------------------------------------------------- #
# Range detection
# --------------------------------------------------------------------------- #

def detect_range(swing_highs: list[dict[str, Any]], swing_lows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None, None
    recent_highs = [s["price"] for s in swing_highs[-4:]]
    recent_lows = [s["price"] for s in swing_lows[-4:]]
    range_high = max(recent_highs)
    range_low = min(recent_lows)
    return range_high, range_low


# --------------------------------------------------------------------------- #
# Equal highs / lows
# --------------------------------------------------------------------------- #

def detect_equal_highs(swing_highs: list[dict[str, Any]], tolerance: float = EQUAL_LEVEL_TOLERANCE) -> list[float]:
    equals: list[float] = []
    prices = [s["price"] for s in swing_highs]
    for i in range(len(prices)):
        for j in range(i + 1, len(prices)):
            if abs(prices[i] - prices[j]) / max(prices[i], 1) <= tolerance:
                equals.append(round((prices[i] + prices[j]) / 2, 6))
    return list(set(equals))


def detect_equal_lows(swing_lows: list[dict[str, Any]], tolerance: float = EQUAL_LEVEL_TOLERANCE) -> list[float]:
    equals: list[float] = []
    prices = [s["price"] for s in swing_lows]
    for i in range(len(prices)):
        for j in range(i + 1, len(prices)):
            if abs(prices[i] - prices[j]) / max(prices[i], 1) <= tolerance:
                equals.append(round((prices[i] + prices[j]) / 2, 6))
    return list(set(equals))


# --------------------------------------------------------------------------- #
# Liquidity sweep / reclaim
# --------------------------------------------------------------------------- #

def detect_sweep(
    candles: list[dict[str, Any]],
    swing_highs: list[dict[str, Any]],
    swing_lows: list[dict[str, Any]],
    equal_highs: list[float],
    equal_lows: list[float],
) -> tuple[str, str]:
    if len(candles) < 3:
        return "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"

    last = candles[-1]
    prev = candles[-2]

    buy_sweep = False
    sell_sweep = False

    # Buy-side sweep: wick above prior high/equal high, close back below
    all_highs = [s["price"] for s in swing_highs] + equal_highs
    for level in all_highs:
        if last["high"] > level and last["close"] < level:
            buy_sweep = True
            break
        if prev["high"] > level and last["close"] < level:
            buy_sweep = True
            break

    # Sell-side sweep: wick below prior low/equal low, close back above
    all_lows = [s["price"] for s in swing_lows] + equal_lows
    for level in all_lows:
        if last["low"] < level and last["close"] > level:
            sell_sweep = True
            break
        if prev["low"] < level and last["close"] > level:
            sell_sweep = True
            break

    if buy_sweep and sell_sweep:
        sweep = "BOTH_SIDE_SWEEP"
    elif buy_sweep:
        sweep = "BUY_SIDE_SWEEP"
    elif sell_sweep:
        sweep = "SELL_SIDE_SWEEP"
    else:
        sweep = "NO_SWEEP"

    # Reclaim
    reclaim = "NO_RECLAIM"
    if buy_sweep:
        reclaim = "RECLAIM_AFTER_BUY_SIDE_SWEEP"
    elif sell_sweep:
        reclaim = "RECLAIM_AFTER_SELL_SIDE_SWEEP"

    return sweep, reclaim


# --------------------------------------------------------------------------- #
# Structure strength
# --------------------------------------------------------------------------- #

def compute_structure_strength(
    candle_count: int,
    sequence: str,
    bos: str,
    choch: str,
    range_high: float | None,
    range_low: float | None,
    flow_alignment: str,
    liquidity_alignment: str,
) -> float:
    score = 0.0

    # Candle count
    if candle_count >= MIN_CANDLES_RECOMMENDED:
        score += 0.2
    elif candle_count >= 10:
        score += 0.1

    # Sequence clarity
    if sequence in ("HH_HL_SEQUENCE", "LH_LL_SEQUENCE"):
        score += 0.25
    elif sequence == "RANGE_SEQUENCE":
        score += 0.1

    # BOS/CHoCH clarity
    if bos in ("BULLISH_BOS", "BEARISH_BOS"):
        score += 0.2
    if choch in ("BULLISH_CHOCH", "BEARISH_CHOCH"):
        score += 0.1

    # Range availability
    if range_high is not None and range_low is not None:
        score += 0.1

    # Alignment
    if flow_alignment == "ALIGNED":
        score += 0.1
    if liquidity_alignment == "ALIGNED":
        score += 0.05

    return round(min(score, 1.0), 3)


# --------------------------------------------------------------------------- #
# Per-timeframe analysis
# --------------------------------------------------------------------------- #

def _insufficient_tf_state(tf: str, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "candle_count": 0,
        "latest_price": None,
        "swing_highs": [],
        "swing_lows": [],
        "latest_swing_high": None,
        "latest_swing_low": None,
        "sequence_label": "INSUFFICIENT_SEQUENCE",
        "bias": "INSUFFICIENT_DATA",
        "bos": "INSUFFICIENT_DATA",
        "choch": "INSUFFICIENT_DATA",
        "range_high": None,
        "range_low": None,
        "equal_highs": [],
        "equal_lows": [],
        "sweep": "INSUFFICIENT_DATA",
        "reclaim": "INSUFFICIENT_DATA",
        "structure_strength": 0.0,
        "quality_label": "INSUFFICIENT_DATA",
        "reason_codes": [reason],
    }


def analyze_timeframe(
    candles: list[dict[str, Any]],
    tf_label: str,
    flow_alignment: str,
    liquidity_alignment: str,
) -> dict[str, Any]:
    if len(candles) < SWING_LOOKBACK * 2 + 1:
        return _insufficient_tf_state(tf_label, f"NOT_ENOUGH_CANDLES_{tf_label}")

    reason_codes: list[str] = [f"TF_{tf_label}_ANALYZED"]

    swing_highs = detect_swing_highs(candles)
    swing_lows = detect_swing_lows(candles)
    sequence = detect_sequence(swing_highs, swing_lows)
    bias = detect_bias(sequence)
    bos = detect_bos(candles, swing_highs, swing_lows)
    choch = detect_choch(sequence, bos)
    range_high, range_low = detect_range(swing_highs, swing_lows)
    equal_highs = detect_equal_highs(swing_highs)
    equal_lows = detect_equal_lows(swing_lows)
    sweep, reclaim = detect_sweep(candles, swing_highs, swing_lows, equal_highs, equal_lows)

    strength = compute_structure_strength(
        len(candles), sequence, bos, choch, range_high, range_low,
        flow_alignment, liquidity_alignment,
    )

    if strength >= 0.7:
        quality = "HIGH"
    elif strength >= 0.4:
        quality = "OK"
    elif strength > 0.0:
        quality = "DEGRADED"
    else:
        quality = "INSUFFICIENT_DATA"

    if bos != "NO_BOS" and bos != "INSUFFICIENT_DATA":
        reason_codes.append(bos)
    if choch != "NO_CHOCH" and choch != "INSUFFICIENT_DATA":
        reason_codes.append(choch)
    if sweep != "NO_SWEEP" and sweep != "INSUFFICIENT_DATA":
        reason_codes.append(sweep)

    return {
        "available": True,
        "candle_count": len(candles),
        "latest_price": candles[-1]["close"],
        "swing_highs": [s["price"] for s in swing_highs[-5:]],
        "swing_lows": [s["price"] for s in swing_lows[-5:]],
        "latest_swing_high": swing_highs[-1]["price"] if swing_highs else None,
        "latest_swing_low": swing_lows[-1]["price"] if swing_lows else None,
        "sequence_label": sequence,
        "bias": bias,
        "bos": bos,
        "choch": choch,
        "range_high": range_high,
        "range_low": range_low,
        "equal_highs": equal_highs,
        "equal_lows": equal_lows,
        "sweep": sweep,
        "reclaim": reclaim,
        "structure_strength": strength,
        "quality_label": quality,
        "reason_codes": reason_codes,
    }


# --------------------------------------------------------------------------- #
# Flow / liquidity alignment
# --------------------------------------------------------------------------- #

def _compute_flow_alignment(bias: str, flow_evidence: dict[str, Any] | None, flow_persistence: dict[str, Any] | None) -> str:
    if bias == "INSUFFICIENT_DATA" or bias == "UNCLEAR_STRUCTURE":
        return "UNKNOWN"
    if flow_evidence is None and flow_persistence is None:
        return "UNKNOWN"

    flow_direction = None
    if flow_evidence:
        flow_direction = flow_evidence.get("flow_direction") or flow_evidence.get("direction")
    if flow_direction is None and flow_persistence:
        flow_direction = flow_persistence.get("flow_direction") or flow_persistence.get("direction")

    if flow_direction is None:
        return "UNKNOWN"

    flow_direction = str(flow_direction).upper()
    if bias == "BULLISH_STRUCTURE" and "LONG" in flow_direction:
        return "ALIGNED"
    if bias == "BEARISH_STRUCTURE" and "SHORT" in flow_direction:
        return "ALIGNED"
    if bias in ("BULLISH_STRUCTURE", "BEARISH_STRUCTURE") and flow_direction not in ("UNKNOWN", "NEUTRAL", ""):
        return "CONFLICT"
    return "NEUTRAL"


def _compute_liquidity_alignment(bias: str, liquidity_memory: dict[str, Any] | None) -> str:
    if liquidity_memory is None:
        return "UNKNOWN"
    liq_bias = str(liquidity_memory.get("liquidity_bias", "UNKNOWN")).upper()
    if bias == "BULLISH_STRUCTURE" and liq_bias == "BID_SUPPORT":
        return "ALIGNED"
    if bias == "BEARISH_STRUCTURE" and liq_bias == "ASK_RESISTANCE":
        return "ALIGNED"
    if liq_bias in ("NO_CLEAR_LIQUIDITY", "UNKNOWN"):
        return "NEUTRAL"
    if bias in ("BULLISH_STRUCTURE", "BEARISH_STRUCTURE"):
        return "CONFLICT"
    return "NEUTRAL"


# --------------------------------------------------------------------------- #
# Setup readiness hint
# --------------------------------------------------------------------------- #

def _compute_setup_readiness(
    overall_bias: str,
    flow_alignment: str,
    liquidity_alignment: str,
    structure_strength: float,
    bos: str,
) -> str:
    if overall_bias == "INSUFFICIENT_DATA":
        return "STRUCTURE_NOT_READY"
    if overall_bias == "RANGE_STRUCTURE":
        return "STRUCTURE_RANGE_WAIT"

    conflict = (flow_alignment == "CONFLICT" or liquidity_alignment == "CONFLICT")
    if conflict:
        return "STRUCTURE_CONFLICT"

    if structure_strength < 0.3:
        return "STRUCTURE_NOT_READY"

    if overall_bias == "BULLISH_STRUCTURE":
        return "STRUCTURE_SUPPORTS_LONG"
    if overall_bias == "BEARISH_STRUCTURE":
        return "STRUCTURE_SUPPORTS_SHORT"

    return "STRUCTURE_NOT_READY"


# --------------------------------------------------------------------------- #
# Main engine
# --------------------------------------------------------------------------- #

def run_market_structure_v2() -> dict[str, Any]:
    """Run S28 market structure engine. Never raises."""
    ts = _utc_now()
    reason_codes: list[str] = ["S28_MARKET_STRUCTURE_V2_RUN", "SAFE_TO_OPEN_REAL_TRADE_FALSE"]
    missing_requirements: list[str] = []

    # Load supporting data
    flow_evidence = _load_json(LATEST_FLOW_EVIDENCE)
    flow_persistence = _load_json(LATEST_FLOW_PERSISTENCE)
    liquidity_memory = _load_json(LATEST_LIQUIDITY_MEMORY)
    flow_quality = _load_json(LATEST_FLOW_QUALITY)
    chain_audit = _load_json(LATEST_CHAIN_AUDIT)
    hybrid_dna = _load_json(LATEST_HYBRID_DNA)
    market_truth = _load_json(LATEST_MARKET_TRUTH)

    # Build 1m candles
    candle_source_status: dict[str, Any] = {"source": "NONE", "record_count": 0}
    candles_1m: list[dict[str, Any]] = []

    # Try official market truth candles first
    if market_truth:
        raw = market_truth.get("candles") or market_truth.get("ohlc_candles") or []
        if raw:
            candles_1m = [c for c in raw if isinstance(c, dict) and "close" in c and "high" in c and "low" in c]
            if candles_1m:
                candle_source_status = {"source": "OFFICIAL_MARKET_TRUTH", "record_count": len(candles_1m)}
                reason_codes.append("CANDLES_FROM_MARKET_TRUTH")

    # Try hybrid DNA
    if not candles_1m and hybrid_dna:
        raw = hybrid_dna.get("candles") or hybrid_dna.get("dna_candles") or []
        if raw:
            candles_1m = [c for c in raw if isinstance(c, dict) and "close" in c and "high" in c and "low" in c]
            if candles_1m:
                candle_source_status = {"source": "HYBRID_CANDLE_DNA", "record_count": len(candles_1m)}
                reason_codes.append("CANDLES_FROM_HYBRID_DNA")

    # Derive from flow events
    if not candles_1m:
        flow_records = _load_jsonl_tail(LIVE_FLOW_JSONL)
        if not flow_records:
            flow_state = _load_json(LATEST_FLOW_STATE)
            if flow_state:
                flow_records = [flow_state]
        if flow_records:
            candles_1m = build_1m_candles_from_flow(flow_records)
            if candles_1m:
                candle_source_status = {"source": "DERIVED_FROM_FLOW_EVENTS", "record_count": len(candles_1m)}
                reason_codes.append("CANDLES_DERIVED_FROM_FLOW_EVENTS")

    if not candles_1m:
        missing_requirements.append("NO_1M_CANDLE_DATA")
        reason_codes.append("NO_CANDLE_DATA_AVAILABLE")

    if candles_1m and len(candles_1m) < MIN_CANDLES_RECOMMENDED:
        missing_requirements.append(f"INSUFFICIENT_CANDLES_{len(candles_1m)}_OF_{MIN_CANDLES_RECOMMENDED}_RECOMMENDED")
        reason_codes.append("BELOW_RECOMMENDED_CANDLE_COUNT")

    # Aggregate timeframes
    candles_5m = aggregate_candles(candles_1m, 5) if candles_1m else []
    candles_15m = aggregate_candles(candles_1m, 15) if candles_1m else []

    input_status = "CANDLES_AVAILABLE" if candles_1m else "NO_CANDLE_DATA"

    # Compute overall bias from 1m for alignment purposes (preliminary)
    sw_highs_1m = detect_swing_highs(candles_1m) if len(candles_1m) >= SWING_LOOKBACK * 2 + 1 else []
    sw_lows_1m = detect_swing_lows(candles_1m) if len(candles_1m) >= SWING_LOOKBACK * 2 + 1 else []
    seq_1m = detect_sequence(sw_highs_1m, sw_lows_1m) if candles_1m else "INSUFFICIENT_SEQUENCE"
    overall_bias_pre = detect_bias(seq_1m)

    flow_alignment = _compute_flow_alignment(overall_bias_pre, flow_evidence, flow_persistence)
    liquidity_alignment = _compute_liquidity_alignment(overall_bias_pre, liquidity_memory)

    # Per-timeframe analysis
    tf_1m = analyze_timeframe(candles_1m, "1m", flow_alignment, liquidity_alignment)
    tf_5m = analyze_timeframe(candles_5m, "5m", flow_alignment, liquidity_alignment)
    tf_15m = analyze_timeframe(candles_15m, "15m", flow_alignment, liquidity_alignment)

    timeframe_states = {"1m": tf_1m, "5m": tf_5m, "15m": tf_15m}

    # Overall structure bias: prefer 15m > 5m > 1m if available
    overall_bias = "INSUFFICIENT_DATA"
    overall_sequence = "INSUFFICIENT_SEQUENCE"
    structure_strength = 0.0
    latest_bos = "INSUFFICIENT_DATA"
    latest_choch = "INSUFFICIENT_DATA"
    latest_sweep = "INSUFFICIENT_DATA"
    all_swing_highs: list[float] = []
    all_swing_lows: list[float] = []

    for tf_key in ("15m", "5m", "1m"):
        tf_state = timeframe_states[tf_key]
        if tf_state["available"] and tf_state["bias"] not in ("INSUFFICIENT_DATA", "UNCLEAR_STRUCTURE"):
            overall_bias = tf_state["bias"]
            overall_sequence = tf_state["sequence_label"]
            structure_strength = tf_state["structure_strength"]
            latest_bos = tf_state["bos"]
            latest_choch = tf_state["choch"]
            latest_sweep = tf_state["sweep"]
            all_swing_highs = tf_state["swing_highs"]
            all_swing_lows = tf_state["swing_lows"]
            break

    # Recompute alignment with final bias
    flow_alignment = _compute_flow_alignment(overall_bias, flow_evidence, flow_persistence)
    liquidity_alignment = _compute_liquidity_alignment(overall_bias, liquidity_memory)

    setup_readiness = _compute_setup_readiness(
        overall_bias, flow_alignment, liquidity_alignment, structure_strength, latest_bos
    )

    # Structure quality
    if structure_strength >= 0.7:
        structure_quality = "HIGH"
    elif structure_strength >= 0.4:
        structure_quality = "OK"
    elif structure_strength > 0.0:
        structure_quality = "DEGRADED"
    else:
        structure_quality = "INSUFFICIENT_DATA"

    # Closest structure event
    closest_event = "NONE"
    if latest_choch not in ("NO_CHOCH", "INSUFFICIENT_DATA"):
        closest_event = latest_choch
    elif latest_bos not in ("NO_BOS", "INSUFFICIENT_DATA"):
        closest_event = latest_bos
    elif latest_sweep not in ("NO_SWEEP", "INSUFFICIENT_DATA"):
        closest_event = latest_sweep

    # Data quality
    dq_level = "HIGH" if len(candles_1m) >= MIN_CANDLES_RECOMMENDED else ("LOW" if candles_1m else "NONE")
    dq_score = min(len(candles_1m) / MIN_CANDLES_RECOMMENDED, 1.0) if candles_1m else 0.0

    missing_requirements_out = missing_requirements if missing_requirements else ["NONE"]

    # Reason codes
    reason_codes.append(f"OVERALL_BIAS_{overall_bias}")
    reason_codes.append(f"SETUP_READINESS_{setup_readiness}")
    if flow_alignment != "UNKNOWN":
        reason_codes.append(f"FLOW_ALIGNMENT_{flow_alignment}")
    if liquidity_alignment != "UNKNOWN":
        reason_codes.append(f"LIQUIDITY_ALIGNMENT_{liquidity_alignment}")

    record: dict[str, Any] = {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": SYMBOL,
        "source": candle_source_status.get("source", "NONE"),
        "input_status": input_status,
        "candle_source_status": candle_source_status,
        "timeframe_states": timeframe_states,
        "swing_points": {
            "recent_highs": all_swing_highs,
            "recent_lows": all_swing_lows,
        },
        "structure_sequence": overall_sequence,
        "bos_status": latest_bos,
        "choch_status": latest_choch,
        "range_status": {
            "range_high": timeframe_states["1m"].get("range_high"),
            "range_low": timeframe_states["1m"].get("range_low"),
        },
        "equal_high_low_status": {
            "equal_highs": timeframe_states["1m"].get("equal_highs", []),
            "equal_lows": timeframe_states["1m"].get("equal_lows", []),
        },
        "liquidity_sweep_status": latest_sweep,
        "structure_bias": overall_bias,
        "structure_strength": structure_strength,
        "structure_quality": structure_quality,
        "flow_alignment": flow_alignment,
        "liquidity_alignment": liquidity_alignment,
        "setup_readiness_hint": setup_readiness,
        "closest_structure_event": closest_event,
        "missing_requirements": missing_requirements_out,
        "data_quality": {"level": dq_level, "score": round(dq_score, 3)},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["SETUP_CLASSIFIER_V2", "S29_OR_DOWNSTREAM"]},
        "execution_safety": dict(SAFETY),
    }

    # Write outputs
    _atomic_write(LATEST_STATE_PATH, json.dumps(record, indent=2, ensure_ascii=False))
    _atomic_write(S28_STATE_PATH, json.dumps(record, indent=2, ensure_ascii=False))
    _append_jsonl(HISTORY_PATH, record)
    _write_report(record)

    return record


# --------------------------------------------------------------------------- #
# Markdown report
# --------------------------------------------------------------------------- #

def _write_report(record: dict[str, Any]) -> None:
    tf = record["timeframe_states"]

    def tf_row(label: str, key: str) -> str:
        s = tf.get(label, {})
        if not s.get("available"):
            return f"- **{label}**: NOT AVAILABLE — {s.get('reason_codes', ['?'])[0] if s.get('reason_codes') else '?'}"
        return (
            f"- **{label}**: bias={s.get('bias','?')} | seq={s.get('sequence_label','?')} | "
            f"BOS={s.get('bos','?')} | CHoCH={s.get('choch','?')} | "
            f"sweep={s.get('sweep','?')} | strength={s.get('structure_strength','?')} | "
            f"candles={s.get('candle_count','?')} | latest_price={s.get('latest_price','?')}"
        )

    lines = [
        "# S28 Market Structure V2 — Latest Report",
        "",
        f"- **timestamp_utc**: {record['timestamp_utc']}",
        f"- **block_id**: {record['block_id']}",
        f"- **symbol**: {record['symbol']}",
        f"- **candle_source**: {record['candle_source_status'].get('source','?')} ({record['candle_source_status'].get('record_count',0)} candles)",
        "",
        "## Overall Structure",
        "",
        f"- **structure_bias**: {record['structure_bias']}",
        f"- **structure_sequence**: {record['structure_sequence']}",
        f"- **structure_strength**: {record['structure_strength']}",
        f"- **structure_quality**: {record['structure_quality']}",
        f"- **closest_structure_event**: {record['closest_structure_event']}",
        "",
        "## Timeframe States",
        "",
        tf_row("1m", "1m"),
        tf_row("5m", "5m"),
        tf_row("15m", "15m"),
        "",
        "## Swing Points",
        "",
        f"- recent_highs: {record['swing_points']['recent_highs']}",
        f"- recent_lows: {record['swing_points']['recent_lows']}",
        "",
        "## BOS / CHoCH",
        "",
        f"- **bos_status**: {record['bos_status']}",
        f"- **choch_status**: {record['choch_status']}",
        "",
        "## Range",
        "",
        f"- range_high: {record['range_status'].get('range_high')}",
        f"- range_low: {record['range_status'].get('range_low')}",
        "",
        "## Equal Highs / Lows",
        "",
        f"- equal_highs: {record['equal_high_low_status']['equal_highs']}",
        f"- equal_lows: {record['equal_high_low_status']['equal_lows']}",
        "",
        "## Sweep / Reclaim",
        "",
        f"- **liquidity_sweep_status**: {record['liquidity_sweep_status']}",
        "",
        "## Alignment",
        "",
        f"- **flow_alignment**: {record['flow_alignment']}",
        f"- **liquidity_alignment**: {record['liquidity_alignment']}",
        "",
        "## Setup Readiness",
        "",
        f"- **setup_readiness_hint**: {record['setup_readiness_hint']}",
        "",
        "## Data Quality",
        "",
        f"- level: {record['data_quality']['level']}",
        f"- score: {record['data_quality']['score']}",
        "",
        "## Missing Requirements",
        "",
    ]
    for m in record["missing_requirements"]:
        lines.append(f"- {m}")

    lines += [
        "",
        "## Recommended Next Fix",
        "",
    ]
    if "NO_1M_CANDLE_DATA" in record["missing_requirements"]:
        lines.append("- Feed live_flow_events.jsonl or connect market truth candle source to enable structure detection.")
    elif any("INSUFFICIENT_CANDLES" in m for m in record["missing_requirements"]):
        lines.append("- Allow more data to accumulate for reliable swing detection (target ≥20 candles).")
    else:
        lines.append("- Structure engine is operating. Improve flow/depth data quality for stronger alignment.")

    lines += [
        "",
        "## Safety",
        "",
        f"- safe_to_open_real_trade: {record['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {record['execution_safety']['private_api_used']}",
        f"- live_order_sent: {record['execution_safety']['live_order_sent']}",
        "",
        "## Reason Codes",
        "",
    ]
    for rc in record["reason_codes"]:
        lines.append(f"- {rc}")
    lines.append("")

    _atomic_write(REPORT_PATH, "\n".join(lines))
