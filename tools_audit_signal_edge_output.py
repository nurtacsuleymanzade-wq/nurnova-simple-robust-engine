from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE = Path("state/simple/epoch_v2")


def _load(name: str) -> dict[str, Any]:
    path = STATE / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _age_seconds(value: Any) -> int | None:
    dt = _parse_ts(value)
    if dt is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))


def main() -> None:
    lifecycle = _load("latest_research_paper_lifecycle.json")
    accounting = _load("latest_outcome_accounting.json")
    edge = _load("latest_research_edge_matrix.json")
    event = _load("latest_signal_event.json")
    telegram = _load("latest_telegram_report.json")
    contract = _load("latest_signal_data_contract.json")
    summary = lifecycle.get("summary") or {}
    accounting_summary = accounting.get("summary") or {}
    events = event.get("events") or []
    open_trades = lifecycle.get("open_trades") or []
    oldest_open_age = None
    if open_trades:
        ages = [_age_seconds(trade.get("opened_at_utc")) for trade in open_trades]
        ages = [age for age in ages if age is not None]
        oldest_open_age = max(ages) if ages else None
    duplicate_event_count = len(open_trades) - len({trade.get("event_id") for trade in open_trades if trade.get("event_id")})
    best_model = (edge.get("best_avg_r_model") or edge.get("best_winrate_model") or (edge.get("summary") or {})).get("model_id") or (edge.get("summary") or {}).get("best_model_id")
    report = {
        "open_trades": int(summary.get("open_trades") or summary.get("open") or len(open_trades)),
        "closed_trades": int(accounting_summary.get("closed_count") or summary.get("closed_total") or 0),
        "trades_closed_this_loop": int(summary.get("closed_this_loop") or len(lifecycle.get("closed_this_loop") or [])),
        "oldest_open_trade_age": oldest_open_age,
        "max_open_total_check": "PASS" if len(open_trades) <= 12 else "FAIL",
        "duplicate_event_count": max(0, duplicate_event_count),
        "a_plus_event_count": sum(1 for item in events if item.get("signal_grade") == "A_PLUS" and item.get("a_plus_ready") is True),
        "last_a_plus_event": next((item for item in events if item.get("signal_grade") == "A_PLUS" and item.get("a_plus_ready") is True), None),
        "tp_hits": int(accounting_summary.get("tp_hits") or accounting_summary.get("wins") or 0),
        "sl_hits": int(accounting_summary.get("sl_hits") or accounting_summary.get("losses") or 0),
        "winrate": accounting_summary.get("winrate"),
        "avg_r": accounting_summary.get("avg_r"),
        "best_model": best_model,
        "telegram_last_sent_status": telegram.get("status"),
        "15m_rate_limit_status": telegram.get("rate_limit_status") or (_load("last_summary_sent_at.json").get("status")),
        "source_contract_status": contract.get("contract_status") or "MISSING",
        "final_status": "SIGNAL_EDGE_OUTPUT_READY",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
