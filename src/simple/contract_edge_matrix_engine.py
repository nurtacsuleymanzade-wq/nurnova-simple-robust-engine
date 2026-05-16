from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, write_json

BLOCK_ID = "CONTRACT_EDGE_MATRIX"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple/epoch_v2")
REPORTS_DIR = Path("reports/simple")

PAPER_LIFECYCLE_HISTORY_PATH = DATA_DIR / "paper_lifecycle_history.jsonl"
RESEARCH_PAPER_LIFECYCLE_HISTORY_PATH = DATA_DIR / "research_paper_lifecycle_history.jsonl"
TRUE_OUTCOME_HISTORY_PATH = DATA_DIR / "true_outcome_history.jsonl"

LATEST_CONTRACT_PLAN_PATH = STATE_DIR / "latest_contract_trade_plan.json"
LATEST_CONTRACT_DECISION_PATH = STATE_DIR / "latest_contract_decision_gate.json"
LATEST_SETUP_CONTRACT_PATH = STATE_DIR / "latest_setup_contract.json"
LATEST_REGIME_PATH = STATE_DIR / "latest_regime_classifier.json"
LATEST_STRUCTURE_PATH = STATE_DIR / "latest_market_structure_v2.json"

OUTPUT_PATH = STATE_DIR / "latest_contract_edge_matrix.json"
HISTORY_PATH = DATA_DIR / "contract_edge_matrix_history.jsonl"
REPORT_PATH = REPORTS_DIR / "contract_edge_matrix_latest_report.md"

FEEDS_NEXT = ["NOVA_BRAIN_REPORT", "DECISION_GATE"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                if isinstance(raw, dict):
                    out.append(raw)
            except Exception:
                continue
    return out


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _iter_trade_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in ("trades_closed_this_loop", "closed_this_loop", "recent_closed", "closed_trades", "trades"):
        items = payload.get(key)
        if isinstance(items, list):
            for row in items:
                if isinstance(row, dict):
                    candidates.append(row)
    if not candidates and str(payload.get("outcome_status", "")).upper() in {"CLOSED", "WIN", "LOSS"}:
        candidates.append(payload)
    return candidates


def _normalize_trade(raw: dict[str, Any]) -> dict[str, Any] | None:
    outcome_status = str(raw.get("outcome_status", raw.get("status", ""))).upper()
    close_reason = str(raw.get("close_reason", raw.get("result", ""))).upper()
    is_closed = outcome_status in {"CLOSED", "WIN", "LOSS"} or close_reason in {"TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"}
    if not is_closed:
        return None

    lineage = raw.get("lineage") if isinstance(raw.get("lineage"), dict) else {}
    identity = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}

    contract_id = raw.get("contract_id") or lineage.get("contract_id") or identity.get("contract_id")
    setup_family = raw.get("setup_family") or lineage.get("setup_family") or identity.get("setup_family")
    direction = str(raw.get("direction") or raw.get("side") or lineage.get("direction") or "NEUTRAL").upper()
    primary_regime = str(raw.get("primary_regime") or lineage.get("primary_regime") or "UNKNOWN").upper()
    structure_bias = str(raw.get("structure_bias") or lineage.get("structure_bias") or "UNKNOWN").upper()
    liquidity_bias = str(raw.get("liquidity_bias") or lineage.get("liquidity_bias") or "UNKNOWN").upper()

    rr1 = _safe_float(raw.get("rr1", raw.get("rr_tp1", 0.0)))
    rr2 = _safe_float(raw.get("rr2", raw.get("rr_tp2", 0.0)))
    outcome_r = _safe_float(raw.get("outcome_r", raw.get("r_result", 0.0)))
    opened_at = raw.get("opened_at") or raw.get("opened_at_utc")
    closed_at = raw.get("closed_at") or raw.get("closed_at_utc")

    result = "UNKNOWN"
    if close_reason in {"TP1_HIT", "TP2_HIT"} or outcome_r > 0:
        result = "WIN"
    elif close_reason in {"SL_HIT"} or outcome_r < 0:
        result = "LOSS"

    return {
        "contract_id": contract_id,
        "setup_family": setup_family,
        "direction": direction,
        "primary_regime": primary_regime,
        "structure_bias": structure_bias,
        "liquidity_bias": liquidity_bias,
        "rr1": rr1,
        "rr2": rr2,
        "result": result,
        "outcome_r": outcome_r,
        "opened_at": opened_at,
        "closed_at": closed_at,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    losses = sum(1 for r in rows if r["result"] == "LOSS")
    winrate = round((wins / n), 4) if n else 0.0
    avg_r = round(sum(r["outcome_r"] for r in rows) / n, 4) if n else 0.0
    expectancy = avg_r
    gross_profit = sum(max(0.0, r["outcome_r"]) for r in rows)
    gross_loss = sum(abs(min(0.0, r["outcome_r"])) for r in rows)
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    return {
        "sample_size": n,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "average_r": avg_r,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
    }


def _signal_label(sample_size: int, expectancy: float) -> str:
    if sample_size < 5:
        return "INSUFFICIENT_SAMPLE"
    if sample_size < 20:
        return "EARLY_POSITIVE_SIGNAL" if expectancy > 0 else "EARLY_NEGATIVE_SIGNAL"
    return "WATCHLIST_EDGE"


def _estimate_daily_open(trades: list[dict[str, Any]]) -> float:
    dates: dict[str, int] = defaultdict(int)
    for t in trades:
        ts = str(t.get("opened_at") or t.get("closed_at") or "")
        if len(ts) >= 10:
            dates[ts[:10]] += 1
    if not dates:
        return 0.0
    return round(sum(dates.values()) / len(dates), 2)


def _report_markdown(result: dict[str, Any]) -> str:
    by_contract = result.get("by_contract") or []
    by_regime = result.get("by_regime") or []
    early = result.get("early_signals") or []
    best_early = early[0] if early else {}
    worst_early = early[-1] if early else {}
    best_regime = by_regime[0] if by_regime else {}
    usable = sum(1 for x in by_contract if int(x.get("sample_size", 0)) >= 5)
    return "\n".join(
        [
            "# Contract Edge Matrix - Latest Report",
            "",
            f"- Timestamp: {result.get('timestamp_utc')}",
            f"- General performance: winrate={result['sample_summary']['winrate']} expectancy={result['sample_summary']['expectancy']} pf={result['sample_summary']['profit_factor']}",
            f"- Contract sample count: {result['sample_summary']['contract_sample_count']}",
            f"- Legacy sample count: {result['sample_summary']['legacy_sample_count']}",
            f"- Best early contract: {best_early.get('contract_id', 'N/A')}",
            f"- Worst early contract: {worst_early.get('contract_id', 'N/A')}",
            f"- Best regime: {best_regime.get('primary_regime', 'N/A')}",
            f"- Usable samples (>=5): {usable}",
            f"- Estimated paper trades/day: {result.get('estimated_paper_trades_per_day', 0.0)}",
            f"- Next action: {result.get('next_action', 'KEEP_SAMPLING')}",
        ]
    ) + "\n"


def run_contract_edge_matrix_engine(symbol: str = "BTCUSDT", fake_sample: bool = False) -> dict[str, Any]:
    context = current_runtime_context(symbol)
    latest_plan = _load_json(LATEST_CONTRACT_PLAN_PATH) or {}
    latest_decision = _load_json(LATEST_CONTRACT_DECISION_PATH) or {}
    latest_setup_contract = _load_json(LATEST_SETUP_CONTRACT_PATH) or {}
    latest_regime = _load_json(LATEST_REGIME_PATH) or {}
    latest_structure = _load_json(LATEST_STRUCTURE_PATH) or {}

    rows: list[dict[str, Any]] = []
    if fake_sample:
        rows = [
            {
                "contract_id": "SC003",
                "setup_family": "TREND_CONTINUATION_LONG",
                "direction": "LONG",
                "primary_regime": "TREND",
                "structure_bias": "LONG",
                "liquidity_bias": "BALANCED",
                "rr1": 1.2,
                "rr2": 1.8,
                "result": "WIN",
                "outcome_r": 1.2,
                "opened_at": "2026-05-16T00:00:00Z",
                "closed_at": "2026-05-16T00:10:00Z",
            }
        ] * 5 + [
            {
                "contract_id": None,
                "setup_family": "LEGACY",
                "direction": "LONG",
                "primary_regime": "UNKNOWN",
                "structure_bias": "UNKNOWN",
                "liquidity_bias": "UNKNOWN",
                "rr1": 1.0,
                "rr2": 1.0,
                "result": "LOSS",
                "outcome_r": -1.0,
                "opened_at": "2026-05-16T00:20:00Z",
                "closed_at": "2026-05-16T00:30:00Z",
            }
        ]
    else:
        sources = [
            *_read_jsonl(PAPER_LIFECYCLE_HISTORY_PATH),
            *_read_jsonl(RESEARCH_PAPER_LIFECYCLE_HISTORY_PATH),
            *_read_jsonl(TRUE_OUTCOME_HISTORY_PATH),
        ]
        for payload in sources:
            for candidate in _iter_trade_candidates(payload):
                trade = _normalize_trade(candidate)
                if trade:
                    rows.append(trade)

    legacy_rows = [r for r in rows if not r.get("contract_id")]
    contract_rows = [r for r in rows if r.get("contract_id")]

    by_contract_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_regime_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_contract_regime_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in contract_rows:
        by_contract_map[str(r["contract_id"])].append(r)
        by_regime_map[str(r["primary_regime"])].append(r)
        by_contract_regime_map[f"{r['contract_id']}|{r['primary_regime']}"].append(r)

    by_contract: list[dict[str, Any]] = []
    early_signals: list[dict[str, Any]] = []
    tradeable_candidates: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []

    for cid, items in by_contract_map.items():
        m = _metrics(items)
        rec = {
            "contract_id": cid,
            "setup_family": items[0].get("setup_family"),
            **m,
            "signal": _signal_label(m["sample_size"], m["expectancy"]),
        }
        by_contract.append(rec)
        if m["sample_size"] >= 5:
            early_signals.append(
                {
                    "contract_id": cid,
                    "sample_size": m["sample_size"],
                    "signal": rec["signal"],
                    "expectancy": m["expectancy"],
                }
            )
        if m["sample_size"] >= 20 and (m["expectancy"] > 0 or m["profit_factor"] > 1.05) and m["average_r"] > 0:
            tradeable_candidates.append({**rec, "status": "TRADEABLE_EDGE_CANDIDATE"})
        else:
            if m["sample_size"] < 5:
                blocked_candidates.append({**rec, "blocked_reason": "TOO_EARLY"})
            elif m["expectancy"] <= 0:
                blocked_candidates.append({**rec, "blocked_reason": "NEGATIVE_EXPECTANCY"})

    by_contract.sort(key=lambda x: (x["sample_size"], x["expectancy"]), reverse=True)
    early_signals.sort(key=lambda x: (x["sample_size"], x["expectancy"]), reverse=True)

    by_regime = [
        {"primary_regime": regime_name, **_metrics(items)}
        for regime_name, items in by_regime_map.items()
    ]
    by_regime.sort(key=lambda x: (x["sample_size"], x["expectancy"]), reverse=True)

    by_contract_regime = []
    for key, items in by_contract_regime_map.items():
        cid, regime_name = key.split("|", 1)
        by_contract_regime.append({"contract_id": cid, "primary_regime": regime_name, **_metrics(items)})
    by_contract_regime.sort(key=lambda x: (x["sample_size"], x["expectancy"]), reverse=True)

    overall = _metrics(rows)
    sample_summary = {
        "closed_count": len(rows),
        "wins": overall["wins"],
        "losses": overall["losses"],
        "winrate": overall["winrate"],
        "expectancy": overall["expectancy"],
        "profit_factor": overall["profit_factor"],
        "legacy_sample_count": len(legacy_rows),
        "contract_sample_count": len(contract_rows),
    }

    reason_codes = [
        f"CLOSED_COUNT_{len(rows)}",
        f"CONTRACT_SAMPLE_{len(contract_rows)}",
        f"LEGACY_SAMPLE_{len(legacy_rows)}",
        "FAST_SAMPLE_MODE_ACTIVE",
    ]
    if legacy_rows:
        reason_codes.append("LEGACY_SAMPLE_NO_CONTRACT_ID")

    next_action = "KEEP_SAMPLING"
    if tradeable_candidates:
        next_action = "REVIEW_TRADEABLE_EDGE_CANDIDATES"
    elif early_signals:
        next_action = "MONITOR_EARLY_SIGNALS"

    output = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": str(
            latest_plan.get("symbol")
            or latest_decision.get("symbol")
            or latest_setup_contract.get("symbol")
            or symbol
        ),
        "source": {"source_mode": "EPOCH_HISTORY_ANALYSIS"},
        "data_quality": "OK" if rows else "DEGRADED",
        "sample_mode": "FAST_SAMPLE_MODE",
        "sample_summary": sample_summary,
        "by_contract": by_contract,
        "by_regime": by_regime,
        "by_contract_regime": by_contract_regime,
        "early_signals": early_signals,
        "tradeable_candidates": tradeable_candidates,
        "blocked_candidates": blocked_candidates,
        "estimated_paper_trades_per_day": _estimate_daily_open(rows),
        "next_action": next_action,
        "lineage_preview": {
            "contract_id": latest_plan.get("contract_id"),
            "setup_family": latest_plan.get("setup_family"),
            "direction": latest_plan.get("direction"),
            "primary_regime": latest_regime.get("primary_regime"),
            "structure_bias": latest_structure.get("structure_bias"),
            "liquidity_bias": (latest_decision.get("metadata") or {}).get("liquidity_bias"),
            "rr1": latest_plan.get("rr1"),
            "rr2": latest_plan.get("rr2"),
        },
        "reason_codes": sorted(set(reason_codes)),
        "feeds_next": FEEDS_NEXT,
        "context_id": context.get("context_id"),
        "loop_id": context.get("loop_id"),
    }

    write_json(OUTPUT_PATH, output)
    _append_jsonl(HISTORY_PATH, output)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_report_markdown(output), encoding="utf-8")
    return output


def main() -> None:
    print(json.dumps(run_contract_edge_matrix_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

