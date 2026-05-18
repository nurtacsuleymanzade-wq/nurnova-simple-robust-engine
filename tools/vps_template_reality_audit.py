#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATE = ROOT / "state"
REPORTS = ROOT / "reports"
NOW = datetime.now(timezone.utc)

MIN_SAMPLES = 50


def run(cmd: str) -> dict[str, Any]:
    proc = subprocess.run(cmd, shell=True, cwd=ROOT, text=True, capture_output=True)
    return {"cmd": cmd, "code": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def fmt_ts(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except Exception:
            continue
    return rows


def tail_rows(rows: list[dict[str, Any]], limit: int = 200) -> list[dict[str, Any]]:
    return rows[-limit:] if len(rows) > limit else rows


def flatten_fields(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten_fields(v, key))
        else:
            out[key] = v
    return out


def find_file(candidates: list[str]) -> Path | None:
    for rel in candidates:
        p = ROOT / rel
        if p.exists():
            return p
    return None


def normalize_value(v: Any) -> Any:
    if isinstance(v, float):
        if math.isfinite(v):
            return round(v, 8)
        return str(v)
    if isinstance(v, (int, str, bool)) or v is None:
        return v
    if isinstance(v, list):
        return tuple(normalize_value(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, normalize_value(x)) for k, x in v.items()))
    return str(v)


def stats_for(values: list[Any]) -> dict[str, Any]:
    non_null = [v for v in values if v is not None]
    unique = {normalize_value(v) for v in non_null}
    counter = Counter(normalize_value(v) for v in non_null)
    most_common = counter.most_common(3)
    repeat_ratio = 0.0
    if non_null:
        repeat_ratio = 1.0 - (len(unique) / len(non_null))
    numeric = [float(v) for v in non_null if isinstance(v, (int, float))]
    res = {
        "count": len(values),
        "non_null": len(non_null),
        "unique_count": len(unique),
        "most_common": most_common,
        "repeat_ratio": round(repeat_ratio, 4),
    }
    if numeric:
        res.update(
            {
                "min": min(numeric),
                "max": max(numeric),
                "mean": round(statistics.mean(numeric), 8),
                "std": round(statistics.pstdev(numeric), 8) if len(numeric) > 1 else 0.0,
            }
        )
    return res


def compact(v: Any) -> str:
    if isinstance(v, tuple):
        return json.dumps(list(v), ensure_ascii=False)
    return json.dumps(v, ensure_ascii=False)


def latest_record_with_ts(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: parse_ts(r.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc))
    return rows[-1]


def freshness_minutes(ts: str | None, fallback_mtime: str | None) -> float | None:
    dt = parse_ts(ts) or parse_ts(fallback_mtime)
    if not dt:
        return None
    return round((NOW - dt).total_seconds() / 60, 2)


def load_samples() -> dict[str, list[dict[str, Any]]]:
    sources = {
        "trade_plan_history": ["data/simple/epoch_v2/contract_trade_plan_history.jsonl", "data/simple/trade_plan_history.jsonl"],
        "signal_event_history": ["data/simple/epoch_v2/signal_event_history.jsonl"],
        "telegram_report_history": ["data/simple/epoch_v2/telegram_report_history.jsonl"],
        "signal_grade_history": ["data/simple/epoch_v2/signal_grade_history.jsonl"],
        "paper_lifecycle_history": ["data/simple/epoch_v2/research_paper_lifecycle_history.jsonl"],
        "paper_trade_factory_history": ["data/simple/epoch_v2/paper_trade_factory_history.jsonl"],
        "scenario_history": ["data/simple/three_scenarios_history.jsonl"],
        "decision_history": ["data/simple/epoch_v2/contract_decision_gate_history.jsonl"],
        "context_history": ["data/simple/unified_context_history.jsonl"],
        "evidence_history": ["data/simple/1s_evidence.jsonl"],
        "market_truth_history": ["data/simple/market_truth.jsonl"],
        "liquidity_map_history": ["data/simple/liquidity_map_history.jsonl"],
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for name, rels in sources.items():
        p = find_file(rels)
        if not p:
            out[name] = []
            continue
        rows = read_jsonl(p) if p.suffix == ".jsonl" else []
        out[name] = tail_rows(rows, 300)
    return out


def merged_samples(samples: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for source, rows in samples.items():
        for row in rows:
            merged.append({"_source": source, **row})
    merged.sort(key=lambda r: parse_ts(r.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc))
    return merged


def field_values(rows: list[dict[str, Any]], field_paths: list[str]) -> dict[str, list[Any]]:
    values: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        flat = flatten_fields(row)
        for field in field_paths:
            values[field].append(flat.get(field))
    return values


def get_first_present(row: dict[str, Any], fields: list[str]) -> Any:
    flat = flatten_fields(row)
    for field in fields:
        if field in flat and flat[field] is not None:
            return flat[field]
    return None


def main() -> None:
    samples = load_samples()
    merged = merged_samples(samples)
    merged = merged[-500:]
    total_samples = len(merged)

    trade_plan_file = find_file(["data/simple/epoch_v2/contract_trade_plan_history.jsonl", "data/simple/trade_plan_history.jsonl"])
    signal_event_file = find_file(["data/simple/epoch_v2/signal_event_history.jsonl"])
    telegram_file = find_file(["data/simple/epoch_v2/telegram_report_history.jsonl"])
    signal_grade_file = find_file(["data/simple/epoch_v2/signal_grade_history.jsonl"])
    lifecycle_file = find_file(["data/simple/epoch_v2/research_paper_lifecycle_history.jsonl"])
    decision_file = find_file(["data/simple/epoch_v2/contract_decision_gate_history.jsonl"])
    scenario_file = find_file(["data/simple/three_scenarios_history.jsonl"])
    context_file = find_file(["data/simple/unified_context_history.jsonl"])
    evidence_file = find_file(["data/simple/1s_evidence.jsonl"])

    fields = [
        "score",
        "confidence",
        "grade",
        "rr",
        "rr1",
        "rr2",
        "entry",
        "stop_loss",
        "sl",
        "tp1",
        "tp2",
        "take_profit",
        "scenario",
        "active_scenario",
        "reason_chain",
        "reason_codes",
        "blockers",
        "direction",
        "price_source",
        "data_age_seconds",
        "regime",
        "market_state",
        "liquidity",
        "plan_confidence",
        "grade_score",
        "signal_grade",
        "activation_score",
        "plan_status",
        "report_mode",
        "source.source_mode",
        "execution_safety.live_order_sent",
    ]
    values = field_values(merged, fields)

    # Derived measurements
    rr_values = [v for v in values.get("rr", []) if isinstance(v, (int, float))]
    if not rr_values:
        rr_values = [v for v in values.get("rr1", []) if isinstance(v, (int, float))]

    chain_repeat_counter = Counter()
    for row in merged:
        rc = get_first_present(row, ["reason_chain", "reason_codes"])
        chain_repeat_counter[normalize_value(rc)] += 1
    repeated_chain_ratio = round(max(chain_repeat_counter.values(), default=0) / total_samples, 4) if total_samples else 0.0

    price_source_live = 0
    price_source_total = 0
    fresh_total = 0
    fresh_count = 0
    dynamic_pairs = []
    for row in merged:
        flat = flatten_fields(row)
        src = flat.get("price_source")
        if src is not None:
            price_source_total += 1
            if "LIVE_FEED" in str(src).upper():
                price_source_live += 1
        ts = flat.get("timestamp_utc")
        age = freshness_minutes(str(ts) if ts is not None else None, None)
        if age is not None:
            fresh_total += 1
            if age <= 30:
                fresh_count += 1
        dynamic_pairs.append((flat.get("entry"), flat.get("stop_loss"), flat.get("tp1"), flat.get("tp2"), flat.get("entry"), flat.get("direction")))

    field_stats = {field: stats_for(values.get(field, [])) for field in fields}

    sample_sources = []
    for name, rows in samples.items():
        if not rows:
            continue
        latest = latest_record_with_ts(rows)
        latest_ts = latest.get("timestamp_utc") if latest else None
        mtime = iso_mtime(find_file([f"data/simple/{name.replace('_history','').replace('signal_event_history','epoch_v2/signal_event_history.jsonl')}"]) ) if False else None
        file_path = find_file({
            "trade_plan_history": ["data/simple/epoch_v2/contract_trade_plan_history.jsonl", "data/simple/trade_plan_history.jsonl"],
            "signal_event_history": ["data/simple/epoch_v2/signal_event_history.jsonl"],
            "telegram_report_history": ["data/simple/epoch_v2/telegram_report_history.jsonl"],
            "signal_grade_history": ["data/simple/epoch_v2/signal_grade_history.jsonl"],
            "paper_lifecycle_history": ["data/simple/epoch_v2/research_paper_lifecycle_history.jsonl"],
            "paper_trade_factory_history": ["data/simple/epoch_v2/paper_trade_factory_history.jsonl"],
            "scenario_history": ["data/simple/three_scenarios_history.jsonl"],
            "decision_history": ["data/simple/epoch_v2/contract_decision_gate_history.jsonl"],
            "context_history": ["data/simple/unified_context_history.jsonl"],
            "evidence_history": ["data/simple/1s_evidence.jsonl"],
            "market_truth_history": ["data/simple/market_truth.jsonl"],
            "liquidity_map_history": ["data/simple/liquidity_map_history.jsonl"],
        }[name])
        sample_sources.append(
            {
                "file": str(file_path.relative_to(ROOT)) if file_path else "KANITLANAMADI",
                "rows_used": len(rows),
                "latest_timestamp": latest_ts or "KANITLANAMADI",
                "freshness_minutes": freshness_minutes(latest_ts, iso_mtime(file_path) if file_path else None),
                "status": "OK" if len(rows) >= MIN_SAMPLES else "LOW_SAMPLE_SIZE",
                "mtime": iso_mtime(file_path) if file_path else "KANITLANAMADI",
            }
        )

    def unique_count(field: str) -> int:
        return int(field_stats[field]["unique_count"])

    def most_common(field: str) -> str:
        mc = field_stats[field]["most_common"]
        return compact(mc[0][0]) if mc else "KANITLANAMADI"

    risk_map = []
    if total_samples < MIN_SAMPLES:
        risk_map.append("LOW_SAMPLE_SIZE")
    if repeated_chain_ratio >= 0.8:
        risk_map.append("REASON_CHAIN_REPEATED")
    if unique_count("score") <= 1:
        risk_map.append("SCORE_STATIC_IN_OUTPUT")
    if unique_count("confidence") <= 1:
        risk_map.append("CONFIDENCE_STATIC_IN_OUTPUT")
    if unique_count("grade") <= 1:
        risk_map.append("GRADE_STATIC_IN_OUTPUT")
    if unique_count("rr1") <= 1 and unique_count("rr2") <= 1:
        risk_map.append("RR_STATIC_IN_OUTPUT")
    if unique_count("entry") <= 1:
        risk_map.append("ENTRY_DISTANCE_STATIC")
    if unique_count("stop_loss") <= 1:
        risk_map.append("SL_DISTANCE_STATIC")
    if unique_count("tp1") <= 1 and unique_count("tp2") <= 1:
        risk_map.append("TP_DISTANCE_STATIC")
    if unique_count("scenario") <= 1:
        risk_map.append("SCENARIO_REPEATED_STATIC")
    if unique_count("active_scenario") == 0:
        risk_map.append("ACTIVE_SCENARIO_MISSING_IN_OUTPUT")
    if price_source_total and price_source_live == 0:
        risk_map.append("LIVE_PRICE_NOT_AFFECTING_OUTPUT")
    if fresh_total and fresh_count / fresh_total < 0.5:
        risk_map.append("STALE_SAMPLE_RISK")

    template_risk_level = "KANITLANAMADI"
    if not merged:
        template_risk_level = "KANITLANAMADI"
    elif len(risk_map) >= 7 or "LOW_SAMPLE_SIZE" in risk_map:
        template_risk_level = "HIGH"
    elif len(risk_map) >= 3:
        template_risk_level = "MEDIUM"
    else:
        template_risk_level = "LOW"

    def dynamic_evidence(field: str) -> dict[str, Any]:
        vals = [v for v in values.get(field, []) if v is not None]
        if not vals:
            return {"changes": "KANITLANAMADI", "depends_on": "KANITLANAMADI", "confidence": "LOW"}
        uniq = {normalize_value(v) for v in vals}
        return {
            "changes": f"{len(uniq)} unique values across {len(vals)} samples",
            "depends_on": "live market variation and upstream state fields" if len(uniq) > 1 else "template or fallback behavior",
            "confidence": "HIGH" if len(uniq) > 1 else "LOW",
        }

    report_json = {
        "generated_at_utc": fmt_ts(NOW),
        "sample_summary": sample_sources,
        "total_samples": total_samples,
        "field_stats": field_stats,
        "checks": {
            "samples_found": total_samples,
            "score_unique_count": unique_count("score"),
            "confidence_unique_count": unique_count("confidence"),
            "grade_unique_count": unique_count("grade"),
            "rr_unique_count": unique_count("rr1") or unique_count("rr2") or unique_count("rr"),
            "entry_unique_count": unique_count("entry"),
            "sl_unique_count": unique_count("stop_loss") or unique_count("sl"),
            "tp_unique_count": max(unique_count("tp1"), unique_count("tp2"), unique_count("take_profit")),
            "scenario_unique_count": unique_count("scenario"),
            "active_scenario_present": unique_count("active_scenario") > 0,
            "reason_chain_unique_count": unique_count("reason_chain") or unique_count("reason_codes"),
            "reason_chain_repeat_ratio": repeated_chain_ratio,
            "price_source_live_ratio": round(price_source_live / price_source_total, 4) if price_source_total else None,
            "data_age_fresh_ratio": round(fresh_count / fresh_total, 4) if fresh_total else None,
            "entry_distance_varies": unique_count("entry") > 1,
            "sl_distance_varies": unique_count("stop_loss") > 1 or unique_count("sl") > 1,
            "tp_distance_varies": unique_count("tp1") > 1 or unique_count("tp2") > 1 or unique_count("take_profit") > 1,
            "dynamic_output_score": unique_count("score") > 1 or unique_count("grade_score") > 1,
            "template_risk_level": template_risk_level,
        },
        "risk_codes": sorted(set(risk_map)),
        "dynamic_evidence": {
            f: dynamic_evidence(f) for f in ["score", "confidence", "grade", "rr1", "entry", "stop_loss", "tp1", "tp2", "scenario", "active_scenario", "reason_chain"]
        },
        "static_evidence": {
            "score": {"pattern": f"{most_common('score')}", "evidence": field_stats["score"], "severity": "HIGH" if "SCORE_STATIC_IN_OUTPUT" in risk_map else "LOW"},
            "confidence": {"pattern": f"{most_common('confidence')}", "evidence": field_stats["confidence"], "severity": "HIGH" if "CONFIDENCE_STATIC_IN_OUTPUT" in risk_map else "LOW"},
            "grade": {"pattern": f"{most_common('grade')}", "evidence": field_stats["grade"], "severity": "HIGH" if "GRADE_STATIC_IN_OUTPUT" in risk_map else "LOW"},
            "rr": {"pattern": f"{most_common('rr1') or most_common('rr2') or most_common('rr')}", "evidence": field_stats["rr1"], "severity": "HIGH" if "RR_STATIC_IN_OUTPUT" in risk_map else "LOW"},
            "entry": {"pattern": f"{most_common('entry')}", "evidence": field_stats["entry"], "severity": "HIGH" if "ENTRY_DISTANCE_STATIC" in risk_map else "LOW"},
            "stop_loss": {"pattern": f"{most_common('stop_loss')}", "evidence": field_stats["stop_loss"], "severity": "HIGH" if "SL_DISTANCE_STATIC" in risk_map else "LOW"},
            "tp": {"pattern": f"{most_common('tp1')}/{most_common('tp2')}", "evidence": {"tp1": field_stats["tp1"], "tp2": field_stats["tp2"]}, "severity": "HIGH" if "TP_DISTANCE_STATIC" in risk_map else "LOW"},
            "scenario": {"pattern": f"{most_common('scenario')}", "evidence": field_stats["scenario"], "severity": "HIGH" if "SCENARIO_REPEATED_STATIC" in risk_map else "LOW"},
            "reason_chain": {"pattern": f"{most_common('reason_chain') or most_common('reason_codes')}", "evidence": field_stats["reason_chain"], "severity": "HIGH" if "REASON_CHAIN_REPEATED" in risk_map else "LOW"},
        },
        "telegram": {
            "file": str(telegram_file.relative_to(ROOT)) if telegram_file else "KANITLANAMADI",
            "mode": get_first_present(latest_record_with_ts(samples["telegram_report_history"]) or {}, ["report_mode", "mode"]),
            "dynamic": unique_count("report_mode") > 1 or unique_count("reason_chain") > 1,
            "evidence": field_stats.get("report_mode", {}),
            "risk": "TELEGRAM_TEMPLATE_RISK" if unique_count("report_mode") <= 1 else None,
        },
        "trade_plan": {
            "file": str(trade_plan_file.relative_to(ROOT)) if trade_plan_file else "KANITLANAMADI",
            "dynamic": unique_count("entry") > 1 or unique_count("stop_loss") > 1 or unique_count("tp1") > 1 or unique_count("tp2") > 1,
            "evidence": {
                "entry": field_stats["entry"],
                "stop_loss": field_stats["stop_loss"],
                "tp1": field_stats["tp1"],
                "tp2": field_stats["tp2"],
                "rr1": field_stats["rr1"],
                "rr2": field_stats["rr2"],
            },
            "risk": "TRADE_PLAN_TEMPLATE_RISK" if unique_count("entry") <= 1 and unique_count("stop_loss") <= 1 else None,
        },
        "sources": {
            "trade_plan": str(trade_plan_file.relative_to(ROOT)) if trade_plan_file else "KANITLANAMADI",
            "signal_event": str(signal_event_file.relative_to(ROOT)) if signal_event_file else "KANITLANAMADI",
            "telegram": str(telegram_file.relative_to(ROOT)) if telegram_file else "KANITLANAMADI",
            "signal_grade": str(signal_grade_file.relative_to(ROOT)) if signal_grade_file else "KANITLANAMADI",
            "paper_lifecycle": str(lifecycle_file.relative_to(ROOT)) if lifecycle_file else "KANITLANAMADI",
            "decision": str(decision_file.relative_to(ROOT)) if decision_file else "KANITLANAMADI",
            "scenario": str(scenario_file.relative_to(ROOT)) if scenario_file else "KANITLANAMADI",
            "context": str(context_file.relative_to(ROOT)) if context_file else "KANITLANAMADI",
            "evidence": str(evidence_file.relative_to(ROOT)) if evidence_file else "KANITLANAMADI",
        },
    }

    prompt7 = (
        "Prompt 7 = LOCAL DYNAMIC FORMULA PATCH PLAN"
        if template_risk_level == "HIGH"
        else "Prompt 7 = LOCAL FORMULA HARDENING PLAN"
        if template_risk_level == "MEDIUM"
        else "Prompt 7 = LOCAL LINEAGE + PAPER OUTCOME AUDIT"
    )

    report_md = REPORTS / "vps_template_reality_audit_report.md"
    report_json_path = REPORTS / "vps_template_reality_audit.json"
    report_p7 = REPORTS / "vps_prompt_7_recommendation.md"

    report_json_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# VPS TEMPLATE REALITY AUDIT REPORT")
    lines.append("")
    lines.append("## 1. Net Hüküm")
    lines.append(f"Template risk: {template_risk_level}")
    lines.append("")
    lines.append("## 2. Sample Summary")
    lines.append("File | Rows Used | Latest Timestamp | Freshness | Status")
    lines.append("---|---:|---|---|---")
    for row in sample_sources:
        lines.append(f"{row['file']} | {row['rows_used']} | {row['latest_timestamp']} | {row['freshness_minutes']}m | {row['status']}")
    lines.append("")
    lines.append("## 3. Field Diversity Table")
    lines.append("Field | Unique Count | Most Common | Repeat Ratio | Risk")
    lines.append("---|---:|---|---:|---")
    field_risks = {
        "score": "SCORE_STATIC_IN_OUTPUT",
        "confidence": "CONFIDENCE_STATIC_IN_OUTPUT",
        "grade": "GRADE_STATIC_IN_OUTPUT",
        "rr1": "RR_STATIC_IN_OUTPUT",
        "entry": "ENTRY_DISTANCE_STATIC",
        "stop_loss": "SL_DISTANCE_STATIC",
        "tp1": "TP_DISTANCE_STATIC",
        "scenario": "SCENARIO_REPEATED_STATIC",
        "reason_chain": "REASON_CHAIN_REPEATED",
    }
    for field in ["score", "confidence", "grade", "rr1", "entry", "stop_loss", "tp1", "tp2", "scenario", "active_scenario", "reason_chain"]:
        risk = field_risks.get(field, "")
        if field == "tp2":
            risk = "TP_DISTANCE_STATIC"
        if field == "active_scenario":
            risk = "ACTIVE_SCENARIO_MISSING_IN_OUTPUT"
        lines.append(f"{field} | {field_stats[field]['unique_count']} | {compact(field_stats[field]['most_common'][0][0]) if field_stats[field]['most_common'] else 'KANITLANAMADI'} | {field_stats[field]['repeat_ratio']} | {risk}")
    lines.append("")
    lines.append("## 4. Dynamic Behavior Evidence")
    lines.append("Field | Evidence That It Changes | Depends On | Confidence")
    lines.append("---|---|---|---")
    for field in ["score", "confidence", "grade", "rr1", "entry", "stop_loss", "tp1", "tp2", "scenario", "active_scenario", "reason_chain"]:
        ev = report_json["dynamic_evidence"][field]
        lines.append(f"{field} | {ev['changes']} | {ev['depends_on']} | {ev['confidence']}")
    lines.append("")
    lines.append("## 5. Static/Fallback Evidence")
    lines.append("Field | Static Pattern | Evidence | Severity")
    lines.append("---|---|---|---")
    for field, ev in report_json["static_evidence"].items():
        lines.append(f"{field} | {ev['pattern']} | {json.dumps(ev['evidence'], ensure_ascii=False)} | {ev['severity']}")
    lines.append("")
    lines.append("## 6. Telegram Reality")
    lines.append("Alert Field | Dynamic? | Source | Evidence | Risk")
    lines.append("---|---|---|---|---")
    lines.append(f"report_mode | {report_json['telegram']['dynamic']} | {report_json['telegram']['file']} | {json.dumps(report_json['telegram']['evidence'], ensure_ascii=False)} | {report_json['telegram']['risk'] or ''}")
    lines.append("")
    lines.append("## 7. Trade Plan Reality")
    lines.append("Plan Field | Dynamic? | Source | Evidence | Risk")
    lines.append("---|---|---|---|---")
    for field in ["entry", "stop_loss", "tp1", "tp2", "rr1", "rr2"]:
        lines.append(f"{field} | {report_json['trade_plan']['dynamic']} | {report_json['trade_plan']['file']} | {json.dumps(report_json['trade_plan']['evidence'][field], ensure_ascii=False)} | {report_json['trade_plan']['risk'] or ''}")
    lines.append("")
    lines.append("## 8. Prompt 7 Recommendation")
    lines.append(prompt7)

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report_p7.write_text(prompt7 + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "template_risk_level": template_risk_level, "json": str(report_json_path), "md": str(report_md), "p7": str(report_p7)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
