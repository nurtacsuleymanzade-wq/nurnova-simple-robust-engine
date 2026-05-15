from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.model_survival_registry import get_active_models, get_quarantined_models
from src.edge.edge_io import append_jsonl_stream, write_json_atomic
from src.simple.research_epoch import epoch_data_path, epoch_state_path
from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload

BLOCK_ID = "EDGE_LEARNING_DASHBOARD_V2"
DASHBOARD_PATH = epoch_state_path("latest_edge_learning_dashboard.json")
DASHBOARD_HISTORY_PATH = epoch_data_path("edge_learning_dashboard_history.jsonl")
REPORT_PATH = Path("reports/simple/epoch_v2/latest_edge_learning_report.md")

TRUE_OUTCOME_PATH = epoch_state_path("latest_true_outcome.json")
TP_DNA_PATH = epoch_state_path("latest_tp_condition_dna.json")
ZONE_PATH = epoch_state_path("latest_zone_context.json")
LEGACY_ZONE_PATH = Path("state/simple/latest_zone_context.json")
VOLUME_PROFILE_PATH = epoch_state_path("latest_volume_profile.json")
LEGACY_VOLUME_PROFILE_PATH = Path("state/simple/latest_volume_profile.json")
STRUCTURE_QUALITY_PATH = epoch_state_path("latest_structure_quality.json")
LEGACY_STRUCTURE_QUALITY_PATH = Path("state/simple/latest_structure_quality.json")
EDGE_QUERY_PATH = epoch_state_path("latest_edge_query_report.json")
MODEL_SURVIVAL_REPORT_PATH = epoch_state_path("latest_model_survival_report.json")
TELEGRAM_REPORT_PATH = epoch_state_path("latest_telegram_report.json")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _status_counts(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "entry_touched": 0,
        "entry_not_touched": 0,
        "tp1": 0,
        "tp2": 0,
        "sl": 0,
        "expired": 0,
    }
    for item in outcomes:
        status = str(item.get("outcome_status") or "").upper()
        if bool(item.get("entry_touched")):
            counts["entry_touched"] += 1
        elif status == "ENTRY_NOT_TOUCHED":
            counts["entry_not_touched"] += 1
        if status == "TP1_HIT":
            counts["tp1"] += 1
        elif status == "TP2_HIT":
            counts["tp2"] += 1
        elif status == "SL_HIT":
            counts["sl"] += 1
        elif status == "EXPIRED":
            counts["expired"] += 1
    return counts


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _round(value: Any, digits: int = 6) -> float:
    number = safe_float(value)
    return round(number, digits) if number is not None else 0.0


def _model_scores(outcomes: list[dict[str, Any]], active_models: list[str], quarantined: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_model: dict[str, dict[str, Any]] = {}
    active_set = set(active_models)
    quarantined_set = set(quarantined)
    for item in outcomes:
        model_id = str(item.get("model_id") or "").strip()
        if not model_id:
            continue
        bucket = by_model.setdefault(model_id, {"samples": 0, "tp": 0, "sl": 0, "expired": 0, "entry_not_touched": 0, "sum_r": 0.0})
        bucket["samples"] += 1
        status = str(item.get("outcome_status") or "").upper()
        if status in {"TP1_HIT", "TP2_HIT"}:
            bucket["tp"] += 1
        elif status == "SL_HIT":
            bucket["sl"] += 1
        elif status == "EXPIRED":
            bucket["expired"] += 1
        elif status == "ENTRY_NOT_TOUCHED":
            bucket["entry_not_touched"] += 1
        bucket["sum_r"] += safe_float(item.get("realized_r")) or 0.0

    scored: list[dict[str, Any]] = []
    for model_id, bucket in by_model.items():
        samples = int(bucket["samples"])
        winrate = (bucket["tp"] / samples) if samples else 0.0
        avg_r = (bucket["sum_r"] / samples) if samples else 0.0
        scored.append(
            {
                "model_id": model_id,
                "samples": samples,
                "tp": int(bucket["tp"]),
                "sl": int(bucket["sl"]),
                "expired": int(bucket["expired"]),
                "entry_not_touched": int(bucket["entry_not_touched"]),
                "winrate": round(winrate, 6),
                "avg_r": round(avg_r, 6),
                "is_active": model_id in active_set,
                "is_quarantined": model_id in quarantined_set,
            }
        )
    eligible = [item for item in scored if item["is_active"] and not item["is_quarantined"]]
    best = sorted(eligible, key=lambda x: (x["avg_r"], x["winrate"], x["samples"]), reverse=True)[:5]
    worst = sorted(eligible, key=lambda x: (x["avg_r"], x["winrate"], -x["samples"]))[:5]
    if not best and active_models:
        best = [{"model_id": active_models[0], "status": "SAMPLE_BUILDING"}]
    if not worst and active_models:
        worst = [{"model_id": active_models[0], "status": "SAMPLE_BUILDING"}]
    return best, worst


def _score_list(source: dict[str, Any], key: str, out_key: str) -> list[dict[str, Any]]:
    rows = []
    for item in _as_list(source.get(key)):
        if isinstance(item, dict):
            rows.append({"name": item.get("condition") or item.get("key") or "UNKNOWN", out_key: item.get("tp_minus_sl") or item.get("score") or 0.0})
        else:
            rows.append({"name": str(item), out_key: 0.0})
    return rows[:5]


def _extract_zone_scores(tp_dna: dict[str, Any], edge_query: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_zone = _as_dict(edge_query.get("by_zone")) or _as_dict(tp_dna.get("by_zone"))
    scored: list[dict[str, Any]] = []
    for zone_name, payload in by_zone.items():
        outcomes = _as_dict(payload.get("outcomes") if isinstance(payload, dict) else payload)
        tp = int(outcomes.get("tp") or 0)
        sl = int(outcomes.get("sl") or 0)
        samples = int(outcomes.get("samples") or (tp + sl + int(outcomes.get("expired") or 0)))
        avg_r = safe_float(outcomes.get("avg_r")) or 0.0
        score = avg_r if samples else float(tp - sl)
        scored.append({"zone": str(zone_name), "samples": samples, "tp": tp, "sl": sl, "avg_r": round(avg_r, 6), "score": round(score, 6)})
    best = sorted(scored, key=lambda x: (x["score"], x["tp"], x["samples"]), reverse=True)[:5]
    worst = sorted(scored, key=lambda x: (x["score"], -x["tp"], -x["samples"]))[:5]
    return best, worst


def _volume_zone_scores(volume_profile: dict[str, Any], outcomes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    reason_codes: list[str] = []
    status = str(volume_profile.get("profile_status") or "")
    if status and status != "OK":
        reason_codes.append("APPROX_PROFILE_USED" if status == "APPROX" else "TRUE_OUTCOME_REQUIRED")
    windows = _as_dict(volume_profile.get("windows"))
    zones: list[dict[str, Any]] = []
    for window, payload in windows.items():
        frame = _as_dict(payload)
        if frame.get("poc"):
            zones.append({"zone": f"POC_{window}", "window": window, "zone_type": "POC"})
        for z in _as_list(frame.get("hvn_zones")):
            zones.append({"zone": f"HVN_{window}", "window": window, "zone_type": "HVN"})
        for z in _as_list(frame.get("lvn_zones")):
            zones.append({"zone": f"LVN_{window}", "window": window, "zone_type": "LVN"})
    if not zones:
        return [], [], reason_codes
    tp = sum(1 for row in outcomes if str(row.get("outcome_status") or "").upper() in {"TP1_HIT", "TP2_HIT"})
    sl = sum(1 for row in outcomes if str(row.get("outcome_status") or "").upper() == "SL_HIT")
    base_score = tp - sl
    scored = [{"zone": z["zone"], "zone_type": z["zone_type"], "window": z["window"], "score": base_score, "tp": tp, "sl": sl} for z in zones]
    return scored[:5], list(reversed(scored[:5])), reason_codes


def _structure_scores(structure_quality: dict[str, Any], outcomes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    reason_codes: list[str] = []
    events = [item for item in _as_list(structure_quality.get("structure_events")) if isinstance(item, dict)]
    if not events:
        reason_codes.append("STRUCTURE_DIAGNOSTIC_ONLY")
        return [], [], reason_codes
    by_band: dict[str, dict[str, Any]] = {}
    tp = sum(1 for row in outcomes if str(row.get("outcome_status") or "").upper() in {"TP1_HIT", "TP2_HIT"})
    sl = sum(1 for row in outcomes if str(row.get("outcome_status") or "").upper() == "SL_HIT")
    avg_r = _mean([safe_float(row.get("realized_r")) or 0.0 for row in outcomes])
    for item in events:
        band = str(item.get("quality_band") or "DIAGNOSTIC_ONLY")
        bucket = by_band.setdefault(band, {"samples": 0, "quality_sum": 0.0})
        bucket["samples"] += 1
        bucket["quality_sum"] += safe_float(item.get("quality_score")) or 0.0
    scored = []
    for band, bucket in by_band.items():
        quality_avg = bucket["quality_sum"] / max(1, int(bucket["samples"]))
        scored.append({"quality_band": band, "samples": int(bucket["samples"]), "quality_score": round(quality_avg, 6), "tp": tp, "sl": sl, "avg_r": round(avg_r, 6), "score": round(avg_r + quality_avg, 6)})
    best = sorted(scored, key=lambda x: x["score"], reverse=True)[:5]
    worst = sorted(scored, key=lambda x: x["score"])[:5]
    return best, worst, reason_codes


def _timeframe_scores(tp_dna: dict[str, Any], edge_query: dict[str, Any]) -> list[dict[str, Any]]:
    by_tf = _as_dict(edge_query.get("by_timeframe")) or _as_dict(tp_dna.get("by_timeframe"))
    scored = []
    for tf, payload in by_tf.items():
        p = _as_dict(payload)
        outcomes = _as_dict(p.get("outcomes"))
        scored.append(
            {
                "timeframe_combo": tf,
                "samples": int(p.get("samples") or outcomes.get("samples") or 0),
                "tp": int(outcomes.get("tp") or 0),
                "sl": int(outcomes.get("sl") or 0),
                "avg_r": _round(outcomes.get("avg_r")),
            }
        )
    scored.sort(key=lambda x: (x["avg_r"], x["tp"], x["samples"]), reverse=True)
    return scored[:5]


def _entry_touch_failures(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: dict[str, dict[str, Any]] = {}
    for row in outcomes:
        status = str(row.get("outcome_status") or "").upper()
        if status != "ENTRY_NOT_TOUCHED":
            continue
        key = f"{row.get('setup_family') or 'UNKNOWN'}|{row.get('model_id') or 'UNKNOWN'}"
        bucket = failures.setdefault(key, {"setup_family": row.get("setup_family") or "UNKNOWN", "model_id": row.get("model_id") or "UNKNOWN", "count": 0})
        bucket["count"] += 1
    ranked = sorted(failures.values(), key=lambda x: x["count"], reverse=True)
    return ranked[:10]


def _telegram_watchlist(
    best_models: list[dict[str, Any]],
    best_conditions: list[dict[str, Any]],
    best_zones: list[dict[str, Any]],
    best_volume_zones: list[dict[str, Any]],
    best_structure: list[dict[str, Any]],
    best_tf: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    watchlist = []
    for row in best_models[:3]:
        watchlist.append({"watch_type": "MODEL", "target": row.get("model_id"), "reason": "ACTIVE_TP_CANDIDATE"})
    for row in best_conditions[:2]:
        watchlist.append({"watch_type": "CONDITION_DNA", "target": row.get("name"), "reason": "TP_EDGE_CONDITION"})
    for row in best_zones[:2]:
        watchlist.append({"watch_type": "ZONE", "target": row.get("zone"), "reason": "TP_ZONE_EDGE"})
    for row in best_volume_zones[:2]:
        watchlist.append({"watch_type": "VOLUME_PROFILE_ZONE", "target": row.get("zone"), "reason": "AUCTION_EDGE"})
    for row in best_structure[:2]:
        watchlist.append({"watch_type": "STRUCTURE_QUALITY", "target": row.get("quality_band"), "reason": "STRUCTURE_EDGE"})
    for row in best_tf[:2]:
        watchlist.append({"watch_type": "TIMEFRAME_COMBO", "target": row.get("timeframe_combo"), "reason": "TF_ALIGNMENT_EDGE"})
    return watchlist[:12]


def run_edge_learning_dashboard() -> dict[str, Any]:
    context = current_runtime_context()
    true_outcome = _as_dict(load_json(TRUE_OUTCOME_PATH))
    tp_dna = _as_dict(load_json(TP_DNA_PATH))
    zone_ctx = _as_dict(load_json(ZONE_PATH) or load_json(LEGACY_ZONE_PATH))
    volume_profile = _as_dict(load_json(VOLUME_PROFILE_PATH) or load_json(LEGACY_VOLUME_PROFILE_PATH))
    structure_quality = _as_dict(load_json(STRUCTURE_QUALITY_PATH) or load_json(LEGACY_STRUCTURE_QUALITY_PATH))
    edge_query = _as_dict(load_json(EDGE_QUERY_PATH))
    survival_report = _as_dict(load_json(MODEL_SURVIVAL_REPORT_PATH))
    telegram = _as_dict(load_json(TELEGRAM_REPORT_PATH))

    outcomes = [row for row in _as_list(true_outcome.get("outcomes")) if isinstance(row, dict)]
    counts = _status_counts(outcomes)
    tp_total = counts["tp1"] + counts["tp2"]
    sl_total = counts["sl"]
    closed_total = tp_total + sl_total + counts["expired"]
    winrate = round(tp_total / (tp_total + sl_total), 6) if (tp_total + sl_total) else 0.0
    expectancy = _mean([safe_float(row.get("realized_r")) or 0.0 for row in outcomes if row.get("realized_r") is not None])

    active_models = _as_list(survival_report.get("active_models")) or get_active_models()
    quarantined_models = _as_list(survival_report.get("quarantined_models")) or get_quarantined_models()
    best_models, worst_models = _model_scores(outcomes, [str(x) for x in active_models], [str(x) for x in quarantined_models])
    best_conditions = _score_list(tp_dna, "tp_edge_conditions", "tp_edge_score")
    worst_conditions = _score_list(tp_dna, "sl_risk_conditions", "sl_risk_score")
    best_zones, worst_zones = _extract_zone_scores(tp_dna, edge_query)
    best_volume_zones, worst_volume_zones, volume_reasons = _volume_zone_scores(volume_profile, outcomes)
    best_structure, worst_structure, structure_reasons = _structure_scores(structure_quality, outcomes)
    best_tf = _timeframe_scores(tp_dna, edge_query)
    entry_touch_failures = _entry_touch_failures(outcomes)
    watchlist = _telegram_watchlist(best_models, best_conditions, best_zones, best_volume_zones, best_structure, best_tf)

    reason_codes: list[str] = ["PASSIVE_MEASURE_ONLY"]
    if not outcomes:
        reason_codes.append("TRUE_OUTCOME_REQUIRED")
    if not best_models and active_models:
        reason_codes.append("SAMPLE_BUILDING")
    reason_codes.extend(volume_reasons)
    reason_codes.extend(structure_reasons)

    dashboard = stamp_payload(
        {
            "block_id": BLOCK_ID,
            "summary": {
                "total_true_samples": len(outcomes),
                "entry_touched": counts["entry_touched"],
                "entry_not_touched": counts["entry_not_touched"],
                "tp1": counts["tp1"],
                "tp2": counts["tp2"],
                "sl": counts["sl"],
                "expired": counts["expired"],
                "winrate": winrate,
                "expectancy": round(expectancy, 6),
            },
            "active_models": active_models,
            "quarantined_models": quarantined_models,
            "best_active_models": best_models,
            "worst_active_models": worst_models,
            "best_condition_dna": best_conditions or [{"name": "SAMPLE_BUILDING"}],
            "worst_condition_dna": worst_conditions or [{"name": "SAMPLE_BUILDING"}],
            "best_zones": best_zones or [{"zone": "SAMPLE_BUILDING"}],
            "worst_zones": worst_zones or [{"zone": "SAMPLE_BUILDING"}],
            "best_volume_profile_zones": best_volume_zones or [{"zone": "SAMPLE_BUILDING"}],
            "worst_volume_profile_zones": worst_volume_zones or [{"zone": "SAMPLE_BUILDING"}],
            "best_structure_quality": best_structure or [{"quality_band": "SAMPLE_BUILDING"}],
            "worst_structure_quality": worst_structure or [{"quality_band": "SAMPLE_BUILDING"}],
            "best_timeframe_combo": best_tf or [{"timeframe_combo": "SAMPLE_BUILDING"}],
            "entry_touch_failures": entry_touch_failures,
            "no_trade_effectiveness": _as_dict(edge_query.get("questions", [{}] * 6)[5]).get("summary", {}) if len(_as_list(edge_query.get("questions"))) > 5 else {},
            "telegram_watchlist": watchlist,
            "data_quality": {
                "level": "HIGH" if outcomes else "MEDIUM",
                "true_outcome_available": bool(outcomes),
                "zone_count": len(_as_list(zone_ctx.get("zones"))),
                "volume_profile_status": volume_profile.get("profile_status") or "UNKNOWN",
                "structure_event_count": int(_as_dict(structure_quality.get("summary")).get("structure_event_count") or len(_as_list(structure_quality.get("structure_events")))),
                "telegram_last_status": telegram.get("status"),
            },
            "reason_codes": list(dict.fromkeys(reason_codes)),
            "execution_safety": {"live_order_sent": False, "private_api_used": False},
            "source_state_refs": {
                "true_outcome": str(TRUE_OUTCOME_PATH),
                "tp_condition_dna": str(TP_DNA_PATH),
                "zone_context": str(ZONE_PATH),
                "volume_profile": str(VOLUME_PROFILE_PATH),
                "structure_quality": str(STRUCTURE_QUALITY_PATH),
                "edge_query": str(EDGE_QUERY_PATH),
                "model_survival_report": str(MODEL_SURVIVAL_REPORT_PATH),
                "telegram_report": str(TELEGRAM_REPORT_PATH),
            },
        },
        BLOCK_ID,
        "BTCUSDT",
        context,
    )

    write_json_atomic(DASHBOARD_PATH, dashboard)
    append_jsonl_stream(DASHBOARD_HISTORY_PATH, dashboard)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# NURNOVA EDGE LEARNING REPORT",
        "",
        "## 1. Current System Status",
        f"- Timestamp UTC: {dashboard.get('timestamp_utc')}",
        f"- Active Models: {', '.join(str(x) for x in _as_list(dashboard.get('active_models'))) or 'none'}",
        f"- Quarantined Models: {', '.join(str(x) for x in _as_list(dashboard.get('quarantined_models'))) or 'none'}",
        "",
        "## 2. True Outcome Summary",
        f"- Total True Samples: {dashboard['summary']['total_true_samples']}",
        f"- Entry Touched: {dashboard['summary']['entry_touched']}",
        f"- Entry Not Touched: {dashboard['summary']['entry_not_touched']}",
        f"- TP1: {dashboard['summary']['tp1']} | TP2: {dashboard['summary']['tp2']} | SL: {dashboard['summary']['sl']} | Expired: {dashboard['summary']['expired']}",
        f"- Winrate: {dashboard['summary']['winrate']}",
        f"- Expectancy: {dashboard['summary']['expectancy']}",
        "",
        "## 3. Best Active Models",
        f"- {json.dumps(dashboard.get('best_active_models') or [], ensure_ascii=False)}",
        "",
        "## 4. Worst / Blocked Models",
        f"- Worst Active: {json.dumps(dashboard.get('worst_active_models') or [], ensure_ascii=False)}",
        f"- Blocked/Quarantined: {json.dumps(dashboard.get('quarantined_models') or [], ensure_ascii=False)}",
        "",
        "## 5. Best Condition DNA",
        f"- {json.dumps(dashboard.get('best_condition_dna') or [], ensure_ascii=False)}",
        "",
        "## 6. Best Zones",
        f"- {json.dumps(dashboard.get('best_zones') or [], ensure_ascii=False)}",
        "",
        "## 7. Volume Profile Findings",
        f"- {json.dumps(dashboard.get('best_volume_profile_zones') or [], ensure_ascii=False)}",
        "",
        "## 8. Structure Quality Findings",
        f"- {json.dumps(dashboard.get('best_structure_quality') or [], ensure_ascii=False)}",
        "",
        "## 9. Timeframe Findings",
        f"- {json.dumps(dashboard.get('best_timeframe_combo') or [], ensure_ascii=False)}",
        "",
        "## 10. Entry Touch Problems",
        f"- {json.dumps(dashboard.get('entry_touch_failures') or [], ensure_ascii=False)}",
        "",
        "## 11. NO_TRADE Effectiveness",
        f"- {json.dumps(dashboard.get('no_trade_effectiveness') or {}, ensure_ascii=False)}",
        "",
        "## 12. Telegram Watchlist",
        f"- {json.dumps(dashboard.get('telegram_watchlist') or [], ensure_ascii=False)}",
        "",
        "## 13. Current Limitations",
        f"- {', '.join(str(x) for x in _as_list(dashboard.get('reason_codes'))) or 'none'}",
        "",
        "## 14. Next Recommended Action",
        f"- Focus watchlist items with highest TP alignment and keep quarantined models excluded from ranking.",
        "",
        "Live execution remains off. No private API usage or real orders are introduced by this dashboard.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dashboard


def run_edge_learning_report() -> dict[str, Any]:
    return run_edge_learning_dashboard()


def main() -> None:
    print(json.dumps(run_edge_learning_dashboard(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
