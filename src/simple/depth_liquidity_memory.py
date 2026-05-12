"""S27 — Depth / Liquidity Memory Engine.

Read-only. Tracks order book wall lifecycle: appeared, strengthened, weakened,
pulled, absorbed, broken. No fake signals. No real trades.
safe_to_open_real_trade always False.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S27_DEPTH_LIQUIDITY_MEMORY"
SYMBOL = "BTCUSDT"

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

LATEST_STATE_PATH = STATE_DIR / "latest_depth_liquidity_memory.json"
S27_STATE_PATH = STATE_DIR / "s27_depth_liquidity_memory_state.json"
HISTORY_PATH = DATA_DIR / "depth_liquidity_memory_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s27_depth_liquidity_memory_latest_report.md"

# Preferred inputs
LIVE_DEPTH_JSONL = DATA_DIR / "live_depth_events.jsonl"
LATEST_DEPTH_STATE = STATE_DIR / "latest_depth_state.json"

# Fallback inputs
LIVE_FLOW_JSONL = DATA_DIR / "live_flow_events.jsonl"
LATEST_FLOW_STATE = STATE_DIR / "latest_flow_state.json"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
}

# Wall detection thresholds
WALL_NOTIONAL_MULTIPLIER = 3.0   # level must be 3x avg to be a wall
WALL_STRENGTHEN_PCT = 0.10       # 10% increase = strengthened
WALL_WEAKEN_PCT = 0.10           # 10% decrease = weakened
WALL_DEPTH_LEVELS = 20           # how many levels to consider on each side
MAX_DEPTH_RECORDS = 500          # tail of JSONL to read


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


def _load_jsonl_tail(path: Path, max_records: int = MAX_DEPTH_RECORDS) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    try:
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
# Wall detection logic
# --------------------------------------------------------------------------- #

def _find_wall(levels: list[tuple[float, float]]) -> dict[str, Any]:
    """Given sorted (price, notional) levels, find the largest wall."""
    if not levels:
        return {"available": False, "nearest_wall_price": None,
                "nearest_wall_notional": None, "wall_strength": 0.0,
                "wall_age_seconds": 0, "wall_status": "NO_WALL"}
    notionals = [n for _, n in levels]
    avg = sum(notionals) / len(notionals) if notionals else 0.0
    best_price, best_notional = None, 0.0
    for price, notional in levels:
        if avg > 0 and notional >= avg * WALL_NOTIONAL_MULTIPLIER:
            if notional > best_notional:
                best_price, best_notional = price, notional
    if best_price is None:
        return {"available": False, "nearest_wall_price": None,
                "nearest_wall_notional": None, "wall_strength": 0.0,
                "wall_age_seconds": 0, "wall_status": "NO_WALL"}
    strength = (best_notional / avg) if avg > 0 else 0.0
    return {"available": True, "nearest_wall_price": best_price,
            "nearest_wall_notional": round(best_notional, 2),
            "wall_strength": round(strength, 2),
            "wall_age_seconds": 0, "wall_status": "APPEARED"}


def _determine_wall_status(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    mid_price: float | None,
) -> dict[str, Any]:
    """Compare current wall against previous memory to assign lifecycle status."""
    out = dict(current)
    if not current["available"]:
        out["wall_status"] = "NO_WALL"
        return out
    if previous is None or not previous.get("available"):
        out["wall_status"] = "APPEARED"
        return out

    prev_notional = previous.get("nearest_wall_notional") or 0.0
    curr_notional = current.get("nearest_wall_notional") or 0.0
    prev_price = previous.get("nearest_wall_price")
    curr_price = current.get("nearest_wall_price")

    if prev_price is not None and curr_price is not None and abs(prev_price - curr_price) / max(prev_price, 1) > 0.005:
        out["wall_status"] = "APPEARED"
        return out

    if prev_notional > 0:
        delta = (curr_notional - prev_notional) / prev_notional
        if delta >= WALL_STRENGTHEN_PCT:
            out["wall_status"] = "STRENGTHENED"
        elif delta <= -WALL_WEAKEN_PCT:
            out["wall_status"] = "WEAKENED"
        else:
            out["wall_status"] = "APPEARED"
    else:
        out["wall_status"] = "APPEARED"

    # Pulled: wall vanished before price reached it (handled in caller)
    # Absorbed/broken: need price context (handled in caller)
    return out


def _extract_depth_snapshot(records: list[dict[str, Any]]) -> tuple[
    list[tuple[float, float]], list[tuple[float, float]], float | None
]:
    """Extract the latest bid/ask levels and mid price from depth records."""
    bid_levels: list[tuple[float, float]] = []
    ask_levels: list[tuple[float, float]] = []
    mid_price: float | None = None

    for rec in reversed(records):
        bids = rec.get("bids") or rec.get("b") or []
        asks = rec.get("asks") or rec.get("a") or []
        if bids or asks:
            for entry in bids[:WALL_DEPTH_LEVELS]:
                try:
                    bid_levels.append((float(entry[0]), float(entry[0]) * float(entry[1])))
                except (IndexError, TypeError, ValueError):
                    pass
            for entry in asks[:WALL_DEPTH_LEVELS]:
                try:
                    ask_levels.append((float(entry[0]), float(entry[0]) * float(entry[1])))
                except (IndexError, TypeError, ValueError):
                    pass
            if bids and asks:
                try:
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    mid_price = (best_bid + best_ask) / 2
                except (IndexError, TypeError, ValueError):
                    pass
            break

    return bid_levels, ask_levels, mid_price


def _load_previous_memory() -> dict[str, Any] | None:
    return _load_json(LATEST_STATE_PATH)


# --------------------------------------------------------------------------- #
# Main engine
# --------------------------------------------------------------------------- #

def run_depth_liquidity_memory() -> dict[str, Any]:
    """Run S27 depth/liquidity memory cycle. Never raises."""
    ts = _utc_now()
    reason_codes: list[str] = ["S27_DEPTH_LIQUIDITY_MEMORY_RUN", "SAFE_TO_OPEN_REAL_TRADE_FALSE"]

    depth_available = False
    fallback_used = False
    source = "NONE"
    input_status = "NO_INPUT"

    depth_records: list[dict[str, Any]] = []
    prev_memory = _load_previous_memory()

    # Try preferred depth inputs
    depth_records = _load_jsonl_tail(LIVE_DEPTH_JSONL)
    if not depth_records:
        depth_state = _load_json(LATEST_DEPTH_STATE)
        if depth_state:
            depth_records = [depth_state]

    if depth_records:
        depth_available = True
        source = "LIVE_DEPTH"
        input_status = "DEPTH_DATA_AVAILABLE"
        reason_codes.append("DEPTH_DATA_USED")
    else:
        # Fallback to flow/bookTicker data
        flow_records = _load_jsonl_tail(LIVE_FLOW_JSONL)
        if not flow_records:
            flow_state = _load_json(LATEST_FLOW_STATE)
            if flow_state:
                flow_records = [flow_state]
        if flow_records:
            fallback_used = True
            source = "FLOW_FALLBACK"
            input_status = "FALLBACK_FLOW_DATA"
            reason_codes.append("FALLBACK_USED_FLOW_DATA")
            reason_codes.append("NOT_ENOUGH_DEPTH_DATA")
        else:
            input_status = "NOT_ENOUGH_DEPTH_DATA"
            reason_codes.append("NOT_ENOUGH_DEPTH_DATA")
            reason_codes.append("NO_FALLBACK_DATA")

    # Extract walls
    bid_wall_state: dict[str, Any]
    ask_wall_state: dict[str, Any]
    wall_events: list[dict[str, Any]] = []
    absorption_candidates: list[dict[str, Any]] = []
    pull_candidates: list[dict[str, Any]] = []
    broken_wall_candidates: list[dict[str, Any]] = []
    mid_price: float | None = None

    if depth_available and depth_records:
        bid_levels, ask_levels, mid_price = _extract_depth_snapshot(depth_records)
        bid_current = _find_wall(sorted(bid_levels, key=lambda x: x[0], reverse=True))
        ask_current = _find_wall(sorted(ask_levels, key=lambda x: x[0]))

        prev_bid = (prev_memory or {}).get("bid_wall_state")
        prev_ask = (prev_memory or {}).get("ask_wall_state")

        bid_wall_state = _determine_wall_status(bid_current, prev_bid, mid_price)
        ask_wall_state = _determine_wall_status(ask_current, prev_ask, mid_price)

        # Pulled: previous had wall, now no wall.
        # BID wall broken = price went BELOW wall (mid < prev_price). Pulled = price stayed above.
        # ASK wall broken = price went ABOVE wall (mid > prev_price). Pulled = price stayed below.
        if prev_bid and prev_bid.get("available") and not bid_current["available"]:
            prev_price = prev_bid.get("nearest_wall_price")
            if prev_price and mid_price and mid_price < prev_price:
                bid_wall_state["wall_status"] = "BROKEN"
                broken_wall_candidates.append({"side": "BID", "price": prev_price, "reason": "PRICE_CROSSED_BELOW_BID_WALL"})
            else:
                bid_wall_state["wall_status"] = "PULLED"
                pull_candidates.append({"side": "BID", "price": prev_price})

        if prev_ask and prev_ask.get("available") and not ask_current["available"]:
            prev_price = prev_ask.get("nearest_wall_price")
            if prev_price and mid_price and mid_price > prev_price:
                ask_wall_state["wall_status"] = "BROKEN"
                broken_wall_candidates.append({"side": "ASK", "price": prev_price, "reason": "PRICE_CROSSED_ABOVE_ASK_WALL"})
            else:
                ask_wall_state["wall_status"] = "PULLED"
                pull_candidates.append({"side": "ASK", "price": prev_price})

        # Absorption: wall weakened while price approached
        if bid_wall_state.get("wall_status") == "WEAKENED" and bid_wall_state.get("available"):
            wall_price = bid_wall_state.get("nearest_wall_price")
            if wall_price and mid_price and abs(mid_price - wall_price) / max(wall_price, 1) < 0.005:
                bid_wall_state["wall_status"] = "ABSORBED"
                absorption_candidates.append({"side": "BID", "price": wall_price})

        if ask_wall_state.get("wall_status") == "WEAKENED" and ask_wall_state.get("available"):
            wall_price = ask_wall_state.get("nearest_wall_price")
            if wall_price and mid_price and abs(mid_price - wall_price) / max(wall_price, 1) < 0.005:
                ask_wall_state["wall_status"] = "ABSORBED"
                absorption_candidates.append({"side": "ASK", "price": wall_price})

        # Collect wall events
        for side, state in [("BID", bid_wall_state), ("ASK", ask_wall_state)]:
            status = state.get("wall_status", "UNKNOWN")
            if status not in ("NO_WALL", "UNKNOWN"):
                wall_events.append({
                    "side": side,
                    "status": status,
                    "price": state.get("nearest_wall_price"),
                    "notional": state.get("nearest_wall_notional"),
                })
    else:
        # Fallback or no data: weak hints only, no real wall claims
        bid_wall_state = {"available": False, "nearest_wall_price": None,
                          "nearest_wall_notional": None, "wall_strength": 0.0,
                          "wall_age_seconds": 0, "wall_status": "UNKNOWN"}
        ask_wall_state = {"available": False, "nearest_wall_price": None,
                          "nearest_wall_notional": None, "wall_strength": 0.0,
                          "wall_age_seconds": 0, "wall_status": "UNKNOWN"}

        if fallback_used:
            reason_codes.append("FALLBACK_WEAK_HINTS_ONLY")

    # Liquidity bias
    bid_status = bid_wall_state.get("wall_status", "UNKNOWN")
    ask_status = ask_wall_state.get("wall_status", "UNKNOWN")
    bid_active = bid_wall_state.get("available", False)
    ask_active = ask_wall_state.get("available", False)

    if bid_active and ask_active:
        liquidity_bias = "BOTH_SIDES"
    elif bid_active and not ask_active:
        liquidity_bias = "BID_SUPPORT"
    elif ask_active and not bid_active:
        liquidity_bias = "ASK_RESISTANCE"
    elif depth_available:
        liquidity_bias = "NO_CLEAR_LIQUIDITY"
    else:
        liquidity_bias = "UNKNOWN"

    # Memory status
    if not depth_available and not fallback_used:
        liquidity_memory_status = "NOT_ENOUGH_DEPTH_DATA"
    elif not depth_available and fallback_used:
        liquidity_memory_status = "FALLBACK_WEAK"
    elif wall_events:
        liquidity_memory_status = "WALLS_DETECTED"
    else:
        liquidity_memory_status = "NO_WALLS_DETECTED"

    confidence = "HIGH" if depth_available else ("LOW" if fallback_used else "NONE")

    wall_lifecycle_summary = {
        "total_wall_events": len(wall_events),
        "bid_status": bid_status,
        "ask_status": ask_status,
        "absorption_candidates": len(absorption_candidates),
        "pull_candidates": len(pull_candidates),
        "broken_wall_candidates": len(broken_wall_candidates),
    }

    record: dict[str, Any] = {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "symbol": SYMBOL,
        "source": source,
        "input_status": input_status,
        "depth_available": depth_available,
        "fallback_used": fallback_used,
        "liquidity_memory_status": liquidity_memory_status,
        "bid_wall_state": bid_wall_state,
        "ask_wall_state": ask_wall_state,
        "wall_events": wall_events,
        "wall_lifecycle_summary": wall_lifecycle_summary,
        "absorption_candidates": absorption_candidates,
        "pull_candidates": pull_candidates,
        "broken_wall_candidates": broken_wall_candidates,
        "liquidity_bias": liquidity_bias,
        "confidence": confidence,
        "data_quality": {"level": confidence, "score": 1.0 if depth_available else (0.3 if fallback_used else 0.0)},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["SIMPLE_ROBUST_ENGINE_V1_COMPLETE"]},
        "execution_safety": dict(SAFETY),
    }

    # Write outputs
    _atomic_write(LATEST_STATE_PATH, json.dumps(record, indent=2, ensure_ascii=False))
    _atomic_write(S27_STATE_PATH, json.dumps(record, indent=2, ensure_ascii=False))
    _append_jsonl(HISTORY_PATH, record)
    _write_report(record)

    return record


def _write_report(record: dict[str, Any]) -> None:
    bid = record["bid_wall_state"]
    ask = record["ask_wall_state"]
    lines = [
        "# S27 Depth / Liquidity Memory — Latest Report",
        "",
        f"- **timestamp_utc**: {record['timestamp_utc']}",
        f"- **block_id**: {record['block_id']}",
        f"- **symbol**: {record['symbol']}",
        f"- **source**: {record['source']}",
        f"- **input_status**: {record['input_status']}",
        f"- **depth_available**: {record['depth_available']}",
        f"- **fallback_used**: {record['fallback_used']}",
        f"- **liquidity_memory_status**: {record['liquidity_memory_status']}",
        f"- **liquidity_bias**: {record['liquidity_bias']}",
        f"- **confidence**: {record['confidence']}",
        "",
        "## Bid Wall State",
        "",
        f"- available: {bid.get('available')}",
        f"- nearest_wall_price: {bid.get('nearest_wall_price')}",
        f"- nearest_wall_notional: {bid.get('nearest_wall_notional')}",
        f"- wall_strength: {bid.get('wall_strength')}",
        f"- wall_status: {bid.get('wall_status')}",
        "",
        "## Ask Wall State",
        "",
        f"- available: {ask.get('available')}",
        f"- nearest_wall_price: {ask.get('nearest_wall_price')}",
        f"- nearest_wall_notional: {ask.get('nearest_wall_notional')}",
        f"- wall_strength: {ask.get('wall_strength')}",
        f"- wall_status: {ask.get('wall_status')}",
        "",
        "## Wall Events",
        "",
    ]
    if record["wall_events"]:
        for ev in record["wall_events"]:
            lines.append(f"- {ev}")
    else:
        lines.append("- None")
    lines += [
        "",
        "## Wall Lifecycle Summary",
        "",
        f"- total_wall_events: {record['wall_lifecycle_summary']['total_wall_events']}",
        f"- absorption_candidates: {record['wall_lifecycle_summary']['absorption_candidates']}",
        f"- pull_candidates: {record['wall_lifecycle_summary']['pull_candidates']}",
        f"- broken_wall_candidates: {record['wall_lifecycle_summary']['broken_wall_candidates']}",
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
