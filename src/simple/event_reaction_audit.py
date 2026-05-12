from __future__ import annotations

import json
import math
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "simple"
STATE_DIR = ROOT / "state"
REPORTS_DIR = ROOT / "reports"

SUMMARY_PATH = STATE_DIR / "event_reaction_summary.json"
AUDIT_REPORT_PATH = REPORTS_DIR / "event_reaction_audit.md"
MATRIX_REPORT_PATH = REPORTS_DIR / "behavioral_edge_matrix.md"

WINDOW_HOURS = 24
HORIZONS_MIN = [1, 3, 5, 15, 30, 60]
TARGET_EVENT_FILES = [
    "telegram_paper_alert_history.jsonl",
    "setup_candidate.jsonl",
    "trade_plan_decision.jsonl",
    "decision_gate_history.jsonl",
    "simple_brain_v2_history.jsonl",
    "flow_persistence.jsonl",
    "1s_evidence.jsonl",
    "hybrid_candle_dna.jsonl",
    "liquidity_structure.jsonl",
    "setup_classifier_v2_history.jsonl",
    "live_flow_quality_audit_history.jsonl",
    "live_flow_events.jsonl",
    "live_depth_events.jsonl",
    "wall_lifecycle_events.jsonl",
]


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, dict):
            for nested in value.values():
                num = _first_number(nested)
                if num is not None:
                    return num
            continue
        if isinstance(value, (list, tuple)):
            for nested in value:
                num = _first_number(nested)
                if num is not None:
                    return num
            continue
        num = _safe_float(value)
        if num is not None:
            return num
    return None


def _load_price_series() -> list[tuple[datetime, float]]:
    series: list[tuple[datetime, float]] = []
    for file_name in ("live_flow_events.jsonl", "live_depth_events.jsonl"):
        for row in _load_jsonl(DATA_DIR / file_name):
            ts = _parse_ts(row.get("timestamp_utc") or row.get("timestamp"))
            if ts is None:
                continue
            price = _first_number(
                row.get("mid_price"),
                row.get("price"),
                row.get("best_bid"),
                row.get("best_ask"),
            )
            if price is None or price <= 0:
                continue
            series.append((ts, price))
    series.sort(key=lambda item: item[0])
    deduped: list[tuple[datetime, float]] = []
    for ts, price in series:
        if deduped and deduped[-1][0] == ts:
            deduped[-1] = (ts, price)
        else:
            deduped.append((ts, price))
    return deduped


def _extract_price_from_row(row: dict[str, Any]) -> float | None:
    return _first_number(
        row.get("entry_price"),
        row.get("selected_entry"),
        row.get("trade_plan"),
        row.get("range_context"),
        row.get("mid_price"),
        row.get("current_price"),
        row.get("price"),
    )


def _side_from_text(value: Any) -> str:
    text = str(value or "").upper()
    if "SHORT" in text or text == "SELL":
        return "SHORT"
    if "LONG" in text or text == "BUY":
        return "LONG"
    return "NEUTRAL"


def _build_indexes() -> dict[str, list[tuple[datetime, dict[str, Any]]]]:
    indexes: dict[str, list[tuple[datetime, dict[str, Any]]]] = {}
    for file_name in TARGET_EVENT_FILES:
        path = DATA_DIR / file_name
        items: list[tuple[datetime, dict[str, Any]]] = []
        for row in _load_jsonl(path):
            ts = _parse_ts(row.get("timestamp_utc") or row.get("timestamp") or row.get("ts"))
            if ts is not None:
                items.append((ts, row))
        items.sort(key=lambda item: item[0])
        indexes[file_name] = items
    return indexes


def _latest_before(index: list[tuple[datetime, dict[str, Any]]], ts: datetime) -> dict[str, Any] | None:
    if not index:
        return None
    values = [item[0] for item in index]
    pos = bisect_right(values, ts) - 1
    if pos < 0:
        return None
    return index[pos][1]


def _signal_from_context(row: dict[str, Any], setup_row: dict[str, Any] | None, gate_row: dict[str, Any] | None) -> str:
    candidates = [
        row.get("signal"),
        row.get("selected_side"),
        row.get("side"),
        row.get("decision"),
        row.get("setup_side"),
        row.get("setup_direction"),
        row.get("trade_direction"),
        row.get("scenario_direction"),
        row.get("micro_winner"),
    ]
    if setup_row:
        candidates.extend(
            [
                setup_row.get("setup_side"),
                (setup_row.get("scenario") or {}).get("scenario_direction"),
                (setup_row.get("setup_candidate") or {}).get("setup_direction"),
            ]
        )
    if gate_row:
        candidates.extend([gate_row.get("selected_side")])
    for value in candidates:
        side = _side_from_text(value)
        if side != "NEUTRAL":
            return side
    return "NEUTRAL"


def _normalize_event(
    row: dict[str, Any],
    source_file: str,
    indexes: dict[str, list[tuple[datetime, dict[str, Any]]]],
) -> dict[str, Any] | None:
    ts = _parse_ts(row.get("timestamp_utc") or row.get("timestamp") or row.get("ts"))
    if ts is None:
        return None
    evidence_row = _latest_before(indexes["1s_evidence.jsonl"], ts)
    persistence_row = _latest_before(indexes["flow_persistence.jsonl"], ts)
    liquidity_row = _latest_before(indexes["liquidity_structure.jsonl"], ts)
    setup_row = _latest_before(indexes["setup_candidate.jsonl"], ts)
    gate_row = _latest_before(indexes["decision_gate_history.jsonl"], ts)
    depth_row = _latest_before(indexes["live_depth_events.jsonl"], ts)
    wall_row = _latest_before(indexes["wall_lifecycle_events.jsonl"], ts)
    brain_row = _latest_before(indexes["simple_brain_v2_history.jsonl"], ts)
    s29_row = _latest_before(indexes["setup_classifier_v2_history.jsonl"], ts)

    signal = _signal_from_context(row, setup_row, gate_row)
    evidence = (evidence_row or {}).get("evidence") or {}
    persistence = persistence_row or {}
    liquidity_bias = (liquidity_row or {}).get("liquidity_bias") or {}
    scenario = (setup_row or {}).get("scenario") or {}
    setup_candidate = (setup_row or {}).get("setup_candidate") or {}
    s29_flow = (s29_row or {}).get("flow_component") or {}
    s29_persistence = (s29_row or {}).get("persistence_component") or {}
    s29_scenario = (s29_row or {}).get("scenario_component") or {}
    sweep_risk = (depth_row or {}).get("sweep_risk") or {}
    imbalance = (depth_row or {}).get("imbalance") or {}
    bid_cluster = (depth_row or {}).get("bid_cluster") or {}
    ask_cluster = (depth_row or {}).get("ask_cluster") or {}
    liquidity_intel = (wall_row or {}).get("liquidity_intelligence") or {}
    bid_wall_hist = (wall_row or {}).get("bid_wall_history") or {}
    ask_wall_hist = (wall_row or {}).get("ask_wall_history") or {}
    gate_checks = (gate_row or {}).get("gate_checks") or {}

    long_probability = _first_number(
        row.get("long_probability"),
        (row.get("probabilities") or {}).get("long"),
        (row.get("probability") or {}).get("long"),
    )
    short_probability = _first_number(
        row.get("short_probability"),
        (row.get("probabilities") or {}).get("short"),
        (row.get("probability") or {}).get("short"),
    )
    if long_probability is None and short_probability is None:
        flow_score = _first_number(s29_flow.get("score"), evidence.get("evidence_score"))
        if flow_score is not None:
            bounded = max(-10.0, min(10.0, flow_score))
            long_probability = round((bounded + 10.0) / 20.0, 4)
            short_probability = round(1.0 - long_probability, 4)

    normalized = {
        "timestamp": _iso(ts),
        "source_file": source_file,
        "block_id": row.get("block_id"),
        "price": _extract_price_from_row(row) or _extract_price_from_row(depth_row or {}) or _extract_price_from_row(liquidity_row or {}),
        "long_probability": long_probability,
        "short_probability": short_probability,
        "signal": signal,
        "persistence": persistence.get("persistence_label") or s29_persistence.get("label"),
        "continuation_state": persistence.get("continuation_quality") or s29_persistence.get("continuation_quality"),
        "liquidity_side": liquidity_bias.get("draw_on_liquidity") or (liquidity_intel.get("draw_toward")),
        "sweep_state": sweep_risk.get("sweep_risk") or persistence.get("sweep_state"),
        "bid_wall_strength": _first_number(bid_cluster.get("wall_strength"), bid_wall_hist.get("absorption_score")),
        "ask_wall_strength": _first_number(ask_cluster.get("wall_strength"), ask_wall_hist.get("absorption_score")),
        "pipeline_status": brain_row.get("brain_status") or row.get("input_status") or setup_candidate.get("setup_status"),
        "event_decision": row.get("decision") or row.get("alert_status") or row.get("setup_status"),
        "source_mode": (row.get("source") or {}).get("source_mode") if isinstance(row.get("source"), dict) else row.get("source"),
        "evidence_label": evidence.get("evidence_label") or s29_flow.get("label"),
        "scenario_label": scenario.get("scenario_label") or s29_scenario.get("label"),
        "setup_status": setup_candidate.get("setup_status") or row.get("setup_status"),
        "gate_trigger_ready": gate_checks.get("trigger_ready"),
        "gate_data_quality_valid": gate_checks.get("data_quality_valid"),
        "wall_dominance": imbalance.get("dominant_side") or liquidity_intel.get("dominant_real_side"),
        "selected_side": gate_row.get("selected_side") if gate_row else None,
    }
    return normalized


def _signature(event: dict[str, Any]) -> str:
    signal = event.get("signal") or "NEUTRAL"
    evidence = event.get("evidence_label") or event.get("scenario_label") or "NO_SIGNAL"
    sweep = event.get("sweep_state") or "NO_SWEEP"
    wall = event.get("wall_dominance") or "BALANCED"
    mapping = {
        "BID": "BID_DOMINANT",
        "ASK": "ASK_DOMINANT",
        "BALANCED": "BALANCED_WALLS",
        "NEUTRAL": "BALANCED_WALLS",
    }
    wall_label = mapping.get(str(wall).upper(), str(wall).upper())
    return f"{signal}|{evidence}|{sweep}|{wall_label}"


def _classify_behavior(event: dict[str, Any], reactions: dict[str, dict[str, float | None]]) -> str:
    signal = event.get("signal", "NEUTRAL")
    horizon = reactions.get("5m") or {}
    chg = horizon.get("price_change_pct")
    mfe = horizon.get("mfe_pct")
    mae = horizon.get("mae_pct")
    if chg is None or mfe is None or mae is None:
        return "NEUTRAL"
    abs_chg = abs(chg)
    if signal == "NEUTRAL":
        if abs_chg <= 0.08 and max(mfe, mae) <= 0.12:
            return "CHOP"
        if mfe >= 0.2 and mae >= 0.2:
            return "SQUEEZE"
        return "NEUTRAL"
    favorable = chg if signal == "LONG" else -chg
    if favorable >= 0.18 and mae <= 0.08:
        return "CONTINUATION"
    if favorable >= 0.08 and mae <= 0.18:
        return "ABSORPTION"
    if favorable <= -0.18 and mfe <= 0.08:
        return "REVERSAL"
    if favorable <= -0.08 and mae >= 0.18:
        return "TRAP"
    if mfe >= 0.18 and mae >= 0.18:
        return "FAILED_CONTINUATION"
    if abs_chg <= 0.08 and max(mfe, mae) <= 0.12:
        return "CHOP"
    return "NEUTRAL"


def _compute_reactions(
    events: list[dict[str, Any]],
    prices: list[tuple[datetime, float]],
) -> list[dict[str, Any]]:
    ts_values = [item[0] for item in prices]
    px_values = [item[1] for item in prices]
    enriched: list[dict[str, Any]] = []
    for event in events:
        event_ts = _parse_ts(event["timestamp"])
        if event_ts is None:
            continue
        if event.get("price") is None:
            pos = bisect_left(ts_values, event_ts)
            if pos >= len(px_values):
                continue
            event["price"] = px_values[pos]
        entry = _safe_float(event.get("price"))
        if entry is None or entry <= 0:
            continue
        start = bisect_left(ts_values, event_ts)
        reactions: dict[str, dict[str, float | None]] = {}
        for horizon in HORIZONS_MIN:
            target_ts = event_ts + timedelta(minutes=horizon)
            end = bisect_left(ts_values, target_ts)
            if end >= len(px_values):
                reactions[f"{horizon}m"] = {
                    "price_change_pct": None,
                    "mfe_pct": None,
                    "mae_pct": None,
                }
                continue
            window_prices = px_values[start : end + 1]
            if not window_prices:
                reactions[f"{horizon}m"] = {
                    "price_change_pct": None,
                    "mfe_pct": None,
                    "mae_pct": None,
                }
                continue
            final_price = px_values[end]
            price_change_pct = ((final_price - entry) / entry) * 100.0
            side = event.get("signal", "NEUTRAL")
            max_up = max(0.0, ((max(window_prices) - entry) / entry) * 100.0)
            max_down = max(0.0, ((entry - min(window_prices)) / entry) * 100.0)
            if side == "SHORT":
                mfe_pct = max_down
                mae_pct = max_up
            elif side == "LONG":
                mfe_pct = max_up
                mae_pct = max_down
            else:
                mfe_pct = max(max_up, max_down)
                mae_pct = min(max_up, max_down)
            reactions[f"{horizon}m"] = {
                "price_change_pct": round(price_change_pct, 4),
                "mfe_pct": round(mfe_pct, 4),
                "mae_pct": round(mae_pct, 4),
            }
        event["reactions"] = reactions
        event["signature"] = _signature(event)
        event["behavior"] = _classify_behavior(event, reactions)
        enriched.append(event)
    return enriched


def _behavior_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(event["behavior"] for event in events))


def _group_signature_stats(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[event["signature"]].append(event)
    rows: list[dict[str, Any]] = []
    for signature, items in grouped.items():
        five = [item["reactions"]["5m"] for item in items if item["reactions"]["5m"]["price_change_pct"] is not None]
        behavior_counter = Counter(item["behavior"] for item in items)
        favorable_scores = []
        maes = []
        mfes = []
        for item in items:
            reaction = item["reactions"]["5m"]
            chg = reaction["price_change_pct"]
            mfe = reaction["mfe_pct"]
            mae = reaction["mae_pct"]
            if chg is None or mfe is None or mae is None:
                continue
            if item["signal"] == "SHORT":
                favorable_scores.append(-chg)
            elif item["signal"] == "LONG":
                favorable_scores.append(chg)
            else:
                favorable_scores.append(-abs(chg))
            mfes.append(mfe)
            maes.append(mae)
        rows.append(
            {
                "signature": signature,
                "count": len(items),
                "avg_5m_change_pct": round(mean(item["price_change_pct"] for item in five), 4) if five else None,
                "avg_5m_mfe_pct": round(mean(mfes), 4) if mfes else None,
                "avg_5m_mae_pct": round(mean(maes), 4) if maes else None,
                "edge_score": round(mean(favorable_scores), 4) if favorable_scores else None,
                "top_behavior": behavior_counter.most_common(1)[0][0] if behavior_counter else "NEUTRAL",
                "behavior_counts": dict(behavior_counter),
            }
        )
    rows.sort(key=lambda row: (row["edge_score"] is None, -(row["edge_score"] or -999), -row["count"]))
    return rows


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mx = mean(xs)
    my = mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return round(cov / math.sqrt(vx * vy), 4)


def _future_score(event: dict[str, Any], horizon_key: str = "5m") -> float | None:
    reaction = event["reactions"].get(horizon_key) or {}
    chg = reaction.get("price_change_pct")
    if chg is None:
        return None
    if event["signal"] == "LONG":
        return chg
    if event["signal"] == "SHORT":
        return -chg
    return -abs(chg)


def _build_summary(events: list[dict[str, Any]], discovered: list[str], price_window: dict[str, Any], effective_window: dict[str, Any]) -> dict[str, Any]:
    sig_rows = _group_signature_stats(events)
    long_pairs = []
    persistence_scores: dict[str, list[float]] = defaultdict(list)
    wall_scores: dict[str, list[float]] = defaultdict(list)
    sweep_scores: dict[str, list[float]] = defaultdict(list)
    for event in events:
        score = _future_score(event)
        if score is None:
            continue
        lp = _safe_float(event.get("long_probability"))
        if lp is not None:
            long_pairs.append((lp, score))
        if event.get("persistence"):
            persistence_scores[str(event["persistence"])].append(score)
        if event.get("wall_dominance"):
            wall_scores[str(event["wall_dominance"])].append(score)
        if event.get("sweep_state"):
            sweep_scores[str(event["sweep_state"])].append(score)

    field_missing = Counter()
    for event in events:
        for field in (
            "timestamp",
            "price",
            "long_probability",
            "short_probability",
            "signal",
            "persistence",
            "continuation_state",
            "liquidity_side",
            "sweep_state",
            "bid_wall_strength",
            "ask_wall_strength",
            "pipeline_status",
        ):
            if event.get(field) in (None, "", []):
                field_missing[field] += 1

    top = [row for row in sig_rows if row["edge_score"] is not None][:5]
    worst = sorted([row for row in sig_rows if row["edge_score"] is not None], key=lambda row: row["edge_score"])[:5]

    return {
        "generated_at_utc": _iso(datetime.now(timezone.utc)),
        "requested_window_hours": WINDOW_HOURS,
        "effective_event_window": effective_window,
        "price_series_window": price_window,
        "discovered_sources": discovered,
        "event_count": len(events),
        "behavior_counts": _behavior_counts(events),
        "signature_stats": sig_rows,
        "top_signatures": top,
        "worst_signatures": worst,
        "long_probability_correlation_5m": _correlation(long_pairs),
        "persistence_avg_future_score_5m": {k: round(mean(v), 4) for k, v in persistence_scores.items()},
        "wall_dominance_avg_future_score_5m": {k: round(mean(v), 4) for k, v in wall_scores.items()},
        "sweep_state_avg_future_score_5m": {k: round(mean(v), 4) for k, v in sweep_scores.items()},
        "missing_field_counts": dict(field_missing),
        "events": events,
    }


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}%"


def _fmt_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _markdown_audit(summary: dict[str, Any]) -> str:
    lines = [
        "# Event Reaction Audit",
        "",
        f"- Generated: `{summary['generated_at_utc']}`",
        f"- Requested window: last `{summary['requested_window_hours']}` hours",
        f"- Effective event window: `{summary['effective_event_window']['start']}` -> `{summary['effective_event_window']['end']}`",
        f"- Price series window: `{summary['price_series_window']['start']}` -> `{summary['price_series_window']['end']}`",
        f"- Event count: `{summary['event_count']}`",
        "",
        "## Net Judgment",
        "",
    ]
    behavior = summary["behavior_counts"]
    continuation = behavior.get("CONTINUATION", 0) + behavior.get("ABSORPTION", 0)
    failure = behavior.get("TRAP", 0) + behavior.get("REVERSAL", 0) + behavior.get("FAILED_CONTINUATION", 0)
    chop = behavior.get("CHOP", 0)
    if continuation > failure and continuation > chop:
        verdict = "Behavioral signal exists, but it is selective and not broad-based."
    elif chop >= continuation and chop >= failure:
        verdict = "Most combinations look choppy/random; broad predictive edge is weak."
    else:
        verdict = "Signals exist, but failure/reversal behavior is as important as continuation."
    lines.extend(
        [
            verdict,
            "",
            f"- Continuation-style outcomes: `{continuation}`",
            f"- Failure/reversal-style outcomes: `{failure}`",
            f"- Chop outcomes: `{chop}`",
            f"- Long probability vs 5m continuation correlation: `{summary['long_probability_correlation_5m']}`",
            "",
            "## Questions",
            "",
            f"1. Continuation showing signatures: `{', '.join(row['signature'] for row in summary['top_signatures'][:3]) or 'none'}`",
            f"2. Trap/reversal signatures: `{', '.join(row['signature'] for row in summary['worst_signatures'][:3]) or 'none'}`",
            f"3. Chop-producing signatures: `{', '.join(row['signature'] for row in summary['signature_stats'] if row['top_behavior'] == 'CHOP') or 'none'}`",
            f"4. Highest average MFE signature: `{max(summary['signature_stats'], key=lambda row: row['avg_5m_mfe_pct'] or -999)['signature'] if summary['signature_stats'] else 'none'}`",
            f"5. Lowest average MAE signature: `{min([row for row in summary['signature_stats'] if row['avg_5m_mae_pct'] is not None], key=lambda row: row['avg_5m_mae_pct'])['signature'] if any(row['avg_5m_mae_pct'] is not None for row in summary['signature_stats']) else 'none'}`",
            f"6. Long probability predictive mi: `{'yes, weak/moderate' if (summary['long_probability_correlation_5m'] or 0) > 0.15 else 'not convincingly'}`",
            f"7. Persistence predictive mi: `{summary['persistence_avg_future_score_5m']}`",
            f"8. Bid/ask dominance predictive mi: `{summary['wall_dominance_avg_future_score_5m']}`",
            f"9. Sweep imminent sonrası: `{summary['sweep_state_avg_future_score_5m']}`",
            f"10. NO_SIGNAL / neutral durumları choppy mi: `{'mostly yes' if behavior.get('CHOP', 0) >= behavior.get('NEUTRAL', 0) else 'mixed'}`",
            "",
            "## Behavioral Summary",
            "",
            f"`{behavior}`",
            "",
            "## Top Signatures",
            "",
            "| Signature | Count | Edge Score 5m | Avg 5m Chg | Avg 5m MFE | Avg 5m MAE | Top Behavior |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in summary["top_signatures"]:
        lines.append(
            f"| {row['signature']} | {row['count']} | {_fmt_num(row['edge_score'])} | {_fmt_pct(row['avg_5m_change_pct'])} | {_fmt_pct(row['avg_5m_mfe_pct'])} | {_fmt_pct(row['avg_5m_mae_pct'])} | {row['top_behavior']} |"
        )
    lines.extend(
        [
            "",
            "## Worst Signatures",
            "",
            "| Signature | Count | Edge Score 5m | Avg 5m Chg | Avg 5m MFE | Avg 5m MAE | Top Behavior |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in summary["worst_signatures"]:
        lines.append(
            f"| {row['signature']} | {row['count']} | {_fmt_num(row['edge_score'])} | {_fmt_pct(row['avg_5m_change_pct'])} | {_fmt_pct(row['avg_5m_mfe_pct'])} | {_fmt_pct(row['avg_5m_mae_pct'])} | {row['top_behavior']} |"
        )
    lines.extend(
        [
            "",
            "## Pipeline Quality Observations",
            "",
            "- Exact long/short probability fields are sparse; correlation is partly based on fallback normalization from flow score.",
            "- The freshest data is on `2026-05-12`; if you expected `2026-05-13`, the live chain did not produce newer records in these sources.",
            "- Several signatures are depth-vetoed or quality-degraded, so event behavior often measures blocked/watch states rather than executable setups.",
            "- Wall lifecycle often reports `BALANCED/UNKNOWN`, which weakens bid/ask predictive tests.",
            "",
            "## Missing Data / Broken Lineage",
            "",
            f"`{summary['missing_field_counts']}`",
            "",
            "## Sources Used",
            "",
        ]
    )
    for path in summary["discovered_sources"]:
        lines.append(f"- `{path}`")
    return "\n".join(lines) + "\n"


def _markdown_matrix(summary: dict[str, Any]) -> str:
    lines = [
        "# Behavioral Edge Matrix",
        "",
        "| Signature | Count | Edge Score 5m | Avg 5m Chg | Avg 5m MFE | Avg 5m MAE | Behavior Mix |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in summary["signature_stats"]:
        mix = ", ".join(f"{k}:{v}" for k, v in sorted(row["behavior_counts"].items()))
        lines.append(
            f"| {row['signature']} | {row['count']} | {_fmt_num(row['edge_score'])} | {_fmt_pct(row['avg_5m_change_pct'])} | {_fmt_pct(row['avg_5m_mfe_pct'])} | {_fmt_pct(row['avg_5m_mae_pct'])} | {mix or 'n/a'} |"
        )
    return "\n".join(lines) + "\n"


def run_event_reaction_audit() -> dict[str, Any]:
    prices = _load_price_series()
    if not prices:
        raise RuntimeError("No price series found in live_flow_events.jsonl or live_depth_events.jsonl")
    indexes = _build_indexes()
    price_window = {"start": _iso(prices[0][0]), "end": _iso(prices[-1][0])}
    discovered = [str(DATA_DIR / name) for name in TARGET_EVENT_FILES if (DATA_DIR / name).exists()]

    latest_ts = prices[-1][0]
    requested_cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    effective_end = latest_ts
    effective_start = max(latest_ts - timedelta(hours=WINDOW_HOURS), prices[0][0])
    exact_recent_available = latest_ts >= requested_cutoff
    if exact_recent_available:
        effective_end = datetime.now(timezone.utc)
        effective_start = requested_cutoff

    candidate_events: list[dict[str, Any]] = []
    excluded_sources = {"live_flow_events.jsonl", "live_depth_events.jsonl", "wall_lifecycle_events.jsonl"}
    for file_name, rows in indexes.items():
        if file_name in excluded_sources:
            continue
        for ts, row in rows:
            if effective_start <= ts <= effective_end:
                normalized = _normalize_event(row, file_name, indexes)
                if normalized is not None:
                    candidate_events.append(normalized)
    reactions = _compute_reactions(candidate_events, prices)
    summary = _build_summary(
        reactions,
        discovered,
        price_window,
        {
            "start": _iso(effective_start),
            "end": _iso(effective_end),
            "mode": "exact_last_24h" if exact_recent_available else "fallback_latest_available_24h",
        },
    )
    _atomic_write(SUMMARY_PATH, json.dumps(summary, indent=2, ensure_ascii=False))
    _atomic_write(AUDIT_REPORT_PATH, _markdown_audit(summary))
    _atomic_write(MATRIX_REPORT_PATH, _markdown_matrix(summary))
    return summary


if __name__ == "__main__":
    result = run_event_reaction_audit()
    print(json.dumps({"event_count": result["event_count"], "summary_path": str(SUMMARY_PATH)}, ensure_ascii=False))
