"""Research Paper Lifecycle Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "RESEARCH_PAPER_LIFECYCLE_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_research_paper_lifecycle.json"
HISTORY_PATH = DATA_DIR / "research_paper_lifecycle_history.jsonl"

PAPER_FACTORY_PATH = STATE_DIR / "latest_paper_trade_factory.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"


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


def _load_previous_snapshot() -> dict[str, Any]:
    if OUTPUT_PATH.exists():
        payload = _load_json(OUTPUT_PATH)
        if payload:
            return payload
    if not HISTORY_PATH.exists():
        return {}
    try:
        lines = [line for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return {}
    for line in reversed(lines):
        try:
            return json.loads(line)
        except Exception:
            continue
    return {}


def _current_price(observation: dict[str, Any]) -> float | None:
    return _safe_float(((observation.get("market_snapshot") or {}).get("price")))


def _trade_update(trade: dict[str, Any], current_price: float | None, now_ts: str) -> dict[str, Any]:
    updated = dict(trade)
    entry = _safe_float(updated.get("entry"))
    risk_distance = _safe_float(updated.get("risk_distance"))
    direction = str(updated.get("direction", "UNKNOWN"))
    tp1 = _safe_float(updated.get("tp1"))
    tp2 = _safe_float(updated.get("tp2"))
    stop_loss = _safe_float(updated.get("stop_loss"))

    updated.setdefault("current_price", current_price)
    updated.setdefault("mfe", 0.0)
    updated.setdefault("mae", 0.0)
    updated.setdefault("status", "OPEN")
    updated.setdefault("opened_at", now_ts)

    if current_price is not None and entry is not None and risk_distance and risk_distance > 0:
        updated["current_price"] = current_price
        if direction == "LONG":
            favorable = (current_price - entry) / risk_distance
            adverse = (entry - current_price) / risk_distance
        else:
            favorable = (entry - current_price) / risk_distance
            adverse = (current_price - entry) / risk_distance
        updated["mfe"] = round(max(_safe_float(updated.get("mfe")) or 0.0, favorable), 8)
        updated["mae"] = round(max(_safe_float(updated.get("mae")) or 0.0, adverse), 8)

    opened_at = str(updated.get("opened_at") or now_ts)
    try:
        opened_dt = datetime.strptime(opened_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now_dt = datetime.strptime(now_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        age_seconds = int((now_dt - opened_dt).total_seconds())
    except Exception:
        age_seconds = 0
    updated["age_seconds"] = age_seconds

    close_reason = None
    exit_price = current_price
    if current_price is not None and direction == "LONG":
        if tp2 is not None and current_price >= tp2:
            close_reason = "TP2_HIT"
            exit_price = tp2
        elif tp1 is not None and current_price >= tp1:
            close_reason = "TP1_HIT"
            exit_price = tp1
        elif stop_loss is not None and current_price <= stop_loss:
            close_reason = "SL_HIT"
            exit_price = stop_loss
    elif current_price is not None and direction == "SHORT":
        if tp2 is not None and current_price <= tp2:
            close_reason = "TP2_HIT"
            exit_price = tp2
        elif tp1 is not None and current_price <= tp1:
            close_reason = "TP1_HIT"
            exit_price = tp1
        elif stop_loss is not None and current_price >= stop_loss:
            close_reason = "SL_HIT"
            exit_price = stop_loss

    if close_reason is None and age_seconds >= int(updated.get("max_holding_seconds") or 1800):
        close_reason = "EXPIRED"

    if close_reason:
        updated["status"] = close_reason
        updated["closed_at"] = now_ts
        updated["exit_price"] = exit_price
        if entry is not None and risk_distance and risk_distance > 0 and exit_price is not None:
            if direction == "LONG":
                realized_r = (exit_price - entry) / risk_distance
            else:
                realized_r = (entry - exit_price) / risk_distance
            updated["realized_r"] = round(realized_r, 8)
        else:
            updated["realized_r"] = None
    else:
        updated["status"] = "OPEN"

    return updated


def run_research_paper_lifecycle_engine() -> dict[str, Any]:
    factory = _load_json(PAPER_FACTORY_PATH) or {}
    observation = _load_json(OBSERVATION_PATH) or {}
    previous = _load_previous_snapshot()
    now_ts = _utc_now()
    current_price = _current_price(observation)

    previous_open = {trade.get("paper_trade_id"): dict(trade) for trade in (previous.get("open_trades") or [])}
    previous_closed = {trade.get("paper_trade_id"): dict(trade) for trade in (previous.get("closed_trades") or [])}

    new_trades_opened: list[dict[str, Any]] = []
    for trade in factory.get("paper_trades") or []:
        if trade.get("status") != "OPEN_CANDIDATE":
            continue
        trade_id = trade.get("paper_trade_id")
        model_instance_id = trade.get("model_instance_id")
        if trade_id in previous_open or trade_id in previous_closed:
            continue
        if any(existing.get("model_instance_id") == model_instance_id for existing in previous_open.values()):
            continue
        opened = dict(trade)
        opened["status"] = "OPEN"
        opened["current_price"] = current_price
        opened["mfe"] = 0.0
        opened["mae"] = 0.0
        previous_open[trade_id] = opened
        new_trades_opened.append(opened)

    updated_open: dict[str, dict[str, Any]] = {}
    trades_closed_this_loop: list[dict[str, Any]] = []
    close_reasons: dict[str, int] = {}
    for trade_id, trade in previous_open.items():
        updated_trade = _trade_update(trade, current_price, now_ts)
        if updated_trade.get("status") == "OPEN":
            updated_open[trade_id] = updated_trade
        else:
            previous_closed[trade_id] = updated_trade
            trades_closed_this_loop.append(updated_trade)
            reason = str(updated_trade.get("status"))
            close_reasons[reason] = close_reasons.get(reason, 0) + 1

    output = {
        "timestamp_utc": now_ts,
        "symbol": str(observation.get("symbol") or factory.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "PAPER_FACTORY_LIFECYCLE",
        },
        "open_trades": list(updated_open.values()),
        "closed_trades": list(previous_closed.values()),
        "new_trades_opened": new_trades_opened,
        "trades_closed_this_loop": trades_closed_this_loop,
        "total_open": len(updated_open),
        "total_closed": len(previous_closed),
        "close_reasons": close_reasons,
        "reason_codes": [
            f"OPEN_{len(updated_open)}",
            f"CLOSED_{len(previous_closed)}",
            "NO_LIVE_EXECUTION",
            "NO_PRIVATE_API",
            "PAPER_ONLY",
        ],
        "data_quality": {
            "level": "HIGH" if factory else "LOW",
            "missing_inputs": [name for name, payload in {
                "latest_paper_trade_factory": factory,
                "latest_observation_factory": observation,
            }.items() if not payload],
        },
        "feeds_next": [
            "RESEARCH_EDGE_MATRIX_ENGINE",
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
    print(json.dumps(run_research_paper_lifecycle_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
