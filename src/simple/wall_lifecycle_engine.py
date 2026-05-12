"""S27B — Wall Lifecycle Engine. Tracks bid/ask wall lifecycle events (spoof vs real liquidity)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "S27B_WALL_LIFECYCLE"
FEEDS_NEXT = {"next_blocks": ["S15_FLOW_TO_SETUP_CONTEXT", "S16_SCENARIO_ENTRY_TRIGGER"]}

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

DEPTH_STATE_PATH = STATE_DIR / "latest_depth_state.json"
WALL_LIFECYCLE_PATH = STATE_DIR / "latest_wall_lifecycle.json"
WALL_EVENTS_PATH = DATA_DIR / "wall_lifecycle_events.jsonl"

SAFETY = {
    "safe_to_open_real_trade": False,
    "private_api_used": False,
    "live_order_sent": False,
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


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _wall_age(appeared_ts: str | None) -> float:
    if not appeared_ts:
        return 0.0
    t = _parse_ts(appeared_ts)
    if t is None:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - t).total_seconds())


def _determine_event(
    prev_notional: float | None,
    curr_notional: float | None,
    curr_price: float | None,
    market_price: float | None,
    side: str,
) -> str:
    if curr_notional is None:
        return "NO_WALL"
    if prev_notional is None:
        return "WALL_APPEARED"
    ratio = (curr_notional - prev_notional) / prev_notional if prev_notional else 0.0
    if ratio > 0.10:
        return "WALL_STRENGTHENED"
    if ratio < -0.10:
        return "WALL_WEAKENED"
    if market_price and curr_price:
        proximity = abs(market_price - curr_price) / market_price if market_price else 1.0
        if proximity < 0.002:
            return "WALL_HELD"
    return "WALL_STABLE"


def _spoof_score(event_history: list[str], wall_age_s: float, price_approached: bool) -> float:
    score = 0.0
    cycle_count = sum(
        1 for i in range(1, len(event_history))
        if event_history[i - 1] == "WALL_APPEARED" and event_history[i] == "WALL_PULLED"
    )
    score += min(0.4, cycle_count * 0.15)
    if wall_age_s < 5.0:
        score += 0.3
    if not price_approached:
        score += 0.2
    return round(min(1.0, score), 4)


def _absorption_score(event_history: list[str]) -> float:
    score = 0.0
    if "WALL_ABSORBED" in event_history:
        score += 0.6
    if "WALL_HELD" in event_history:
        score += 0.2
    return round(min(1.0, score), 4)


def _liquidity_conclusion(spoof: float, absorption: float, wall_age_s: float) -> str:
    if absorption > 0.6:
        return "REAL_LIQUIDITY"
    if spoof > 0.7:
        return "LIKELY_SPOOF"
    if wall_age_s > 60 and spoof < 0.3:
        return "DEFENSIVE_WALL"
    return "UNKNOWN"


def _process_side(
    side: str,
    curr_depth: dict[str, Any] | None,
    prev_lifecycle: dict[str, Any] | None,
    market_price: float | None,
) -> dict[str, Any]:
    wall_key = "bid_wall" if side == "bid" else "ask_wall"
    history_key = "bid_wall_history" if side == "bid" else "ask_wall_history"

    curr_wall = (curr_depth or {}).get(wall_key) or {}
    prev_history = (prev_lifecycle or {}).get(history_key) or {}

    curr_price = curr_wall.get("price")
    curr_notional = curr_wall.get("notional")
    prev_notional = prev_history.get("prev_notional")
    appeared_ts = prev_history.get("appeared_ts")
    event_history: list[str] = list(prev_history.get("event_history") or [])

    event = _determine_event(prev_notional, curr_notional, curr_price, market_price, side)

    if event == "NO_WALL":
        if event_history and event_history[-1] not in ("NO_WALL", "WALL_PULLED"):
            event_history.append("WALL_PULLED")
        appeared_ts = None
        wall_age_s = 0.0
    elif event == "WALL_APPEARED":
        appeared_ts = _utc_now()
        event_history.append("WALL_APPEARED")
        wall_age_s = 0.0
    else:
        if appeared_ts is None:
            appeared_ts = _utc_now()
        event_history.append(event)
        wall_age_s = _wall_age(appeared_ts)

    event_history = event_history[-20:]

    price_approached = False
    if market_price and curr_price:
        price_approached = abs(market_price - curr_price) / max(market_price, 1.0) < 0.003

    spoof = _spoof_score(event_history, wall_age_s if event != "NO_WALL" else 0.0, price_approached)
    absorption = _absorption_score(event_history)
    conclusion = _liquidity_conclusion(spoof, absorption, wall_age_s if event != "NO_WALL" else 0.0)

    return {
        "current_event": event,
        "wall_price": curr_price,
        "wall_notional": curr_notional,
        "wall_age_seconds": round(wall_age_s, 1),
        "spoof_score": spoof,
        "absorption_score": absorption,
        "liquidity_conclusion": conclusion,
        "event_history": event_history,
        "appeared_ts": appeared_ts,
        "prev_notional": curr_notional,
    }


def compute_wall_lifecycle(
    depth: dict[str, Any] | None,
    prev: dict[str, Any] | None,
) -> dict[str, Any]:
    ts = _utc_now()
    symbol = (depth or {}).get("symbol", "BTCUSDT")
    context_id = (depth or {}).get("context_id", "UNKNOWN")
    market_price = (depth or {}).get("mid_price") or (depth or {}).get("last_price")

    bid_hist = _process_side("bid", depth, prev, market_price)
    ask_hist = _process_side("ask", depth, prev, market_price)

    bid_conclusion = bid_hist["liquidity_conclusion"]
    ask_conclusion = ask_hist["liquidity_conclusion"]

    if bid_conclusion == "REAL_LIQUIDITY" and ask_conclusion != "REAL_LIQUIDITY":
        dominant_real = "BID"
        draw_toward = "BELOW"
    elif ask_conclusion == "REAL_LIQUIDITY" and bid_conclusion != "REAL_LIQUIDITY":
        dominant_real = "ASK"
        draw_toward = "ABOVE"
    elif bid_conclusion == "LIKELY_SPOOF" and ask_conclusion != "LIKELY_SPOOF":
        dominant_real = "ASK"
        draw_toward = "ABOVE"
    elif ask_conclusion == "LIKELY_SPOOF" and bid_conclusion != "LIKELY_SPOOF":
        dominant_real = "BID"
        draw_toward = "BELOW"
    else:
        dominant_real = "BALANCED"
        draw_toward = "NEUTRAL"

    sweep_occurred = (
        bid_hist["current_event"] in ("WALL_ABSORBED", "WALL_PULLED")
        or ask_hist["current_event"] in ("WALL_ABSORBED", "WALL_PULLED")
    )

    conf_vals = [
        max(bid_hist["absorption_score"], bid_hist["spoof_score"]),
        max(ask_hist["absorption_score"], ask_hist["spoof_score"]),
    ]
    confidence = round(sum(conf_vals) / len(conf_vals), 4)

    reason_codes = [
        f"SYMBOL_{symbol}",
        f"BID_WALL_{bid_hist['current_event']}",
        f"ASK_WALL_{ask_hist['current_event']}",
        f"BID_CONCLUSION_{bid_conclusion}",
        f"ASK_CONCLUSION_{ask_conclusion}",
        f"DOMINANT_REAL_{dominant_real}",
        f"DRAW_TOWARD_{draw_toward}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]
    if sweep_occurred:
        reason_codes.append("SWEEP_OCCURRED")

    return {
        "timestamp_utc": ts,
        "block_id": BLOCK_ID,
        "context_id": context_id,
        "symbol": symbol,
        "source": "S27_DEPTH_LIQUIDITY_MEMORY",
        "bid_wall_history": bid_hist,
        "ask_wall_history": ask_hist,
        "liquidity_intelligence": {
            "dominant_real_side": dominant_real,
            "sweep_occurred": sweep_occurred,
            "draw_toward": draw_toward,
            "confidence": confidence,
        },
        "data_quality": {
            "level": "OK" if depth else "MISSING",
            "score": 0.8 if depth else 0.0,
        },
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def run_wall_lifecycle_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    depth = _load_json(DEPTH_STATE_PATH)
    prev = _load_json(WALL_LIFECYCLE_PATH)

    result = compute_wall_lifecycle(depth, prev)

    WALL_LIFECYCLE_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    with WALL_EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    return result
