#!/usr/bin/env python3
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "reports" / "vps_lineage_outcome_audit.json"
OUT_MD = ROOT / "reports" / "vps_lineage_outcome_audit_report.md"
OUT_REC = ROOT / "reports" / "vps_prompt_9_recommendation.md"

TARGET_ID_FIELDS = [
    "setup_id",
    "active_scenario_id",
    "signal_id",
    "trade_plan_id",
    "plan_id",
    "decision_id",
    "paper_trade_id",
    "outcome_id",
    "edge_event_id",
    "lineage_id",
    "context_id",
]


@dataclass
class LayerConfig:
    name: str
    path: str
    primary_id: str | None
    parent_id: str | None
    ts_fields: tuple[str, ...]


LAYERS = [
    LayerConfig("SETUP", "data/simple/epoch_v2/setup_contract_history.jsonl", "setup_id", "context_id", ("timestamp_utc", "timestamp")),
    LayerConfig("SIGNAL", "data/simple/epoch_v2/signal_event_history.jsonl", "signal_id", "setup_id", ("timestamp_utc", "timestamp")),
    LayerConfig("TRADE_PLAN", "data/simple/epoch_v2/contract_trade_plan_history.jsonl", "trade_plan_id", "signal_id", ("timestamp_utc", "timestamp")),
    LayerConfig("DECISION", "data/simple/epoch_v2/contract_decision_gate_history.jsonl", "decision_id", "trade_plan_id", ("timestamp_utc", "timestamp")),
    LayerConfig("PAPER_LIFECYCLE", "data/simple/epoch_v2/research_paper_lifecycle_history.jsonl", "paper_trade_id", "decision_id", ("timestamp_utc", "timestamp")),
    LayerConfig("OUTCOME", "data/simple/epoch_v2/outcome_accounting_history.jsonl", "outcome_id", "paper_trade_id", ("timestamp_utc", "timestamp")),
    LayerConfig("EDGE_MATRIX", "data/simple/epoch_v2/contract_edge_matrix_history.jsonl", "edge_event_id", "outcome_id", ("timestamp_utc", "timestamp")),
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
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


def parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    s = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def first_present(d: dict[str, Any], keys: list[str] | tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def extract_nested_ids(rows: list[dict[str, Any]], key: str) -> list[str]:
    vals: list[str] = []
    for row in rows:
        v = row.get(key)
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    pv = item.get("paper_trade_id")
                    if isinstance(pv, str) and pv:
                        vals.append(pv)
    return vals


def extract_outcome_types(rows: list[dict[str, Any]]) -> Counter:
    c = Counter()
    for row in rows:
        samples = row.get("closed_samples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            result = sample.get("final_result") or sample.get("result") or sample.get("status")
            if isinstance(result, str):
                u = result.upper()
                if "TP" in u:
                    c["TP"] += 1
                elif "SL" in u:
                    c["SL"] += 1
                elif "INVALID" in u:
                    c["INVALIDATED"] += 1
    return c


def status_from_ratio(traceable: int, total: int) -> str:
    if total <= 0:
        return "KANITLANAMADI"
    if traceable == total:
        return "PASS"
    if traceable > 0:
        return "PARTIAL"
    return "FAIL"


def main() -> None:
    now = datetime.now(timezone.utc)
    layer_results: dict[str, Any] = {}
    risk_codes: set[str] = set()

    lineage_paths = [
        ROOT / "data/simple/epoch_v2/full_lineage_history.jsonl",
        ROOT / "data/simple/epoch_v2/telegram_report_history.jsonl",
    ]

    for lc in LAYERS:
        path = ROOT / lc.path
        rows = load_jsonl(path)
        id_values = [r.get(lc.primary_id) for r in rows] if lc.primary_id else []
        id_values = [v for v in id_values if isinstance(v, str) and v]
        unique_ids = set(id_values)
        duplicates = sum(v - 1 for v in Counter(id_values).values() if v > 1)
        missing_ids = len(rows) - len(id_values) if lc.primary_id else len(rows)

        ts = None
        for r in reversed(rows):
            ts = first_present(r, lc.ts_fields)
            if ts:
                break
        latest_dt = parse_ts(ts)
        age_min = round((now - latest_dt).total_seconds() / 60, 2) if latest_dt else None

        layer_results[lc.name] = {
            "path": str(path.relative_to(ROOT)),
            "rows": len(rows),
            "unique_ids": len(unique_ids),
            "missing_ids": missing_ids,
            "duplicate_ids": duplicates,
            "latest_timestamp": ts,
            "freshness_min": age_min,
            "latest_record_keys": sorted(list(rows[-1].keys())) if rows else [],
            "latest_record_preview": rows[-1] if rows else None,
        }

    setup_rows = load_jsonl(ROOT / "data/simple/epoch_v2/setup_contract_history.jsonl")
    signal_rows = load_jsonl(ROOT / "data/simple/epoch_v2/signal_event_history.jsonl")
    plan_rows = load_jsonl(ROOT / "data/simple/epoch_v2/contract_trade_plan_history.jsonl")
    decision_rows = load_jsonl(ROOT / "data/simple/epoch_v2/contract_decision_gate_history.jsonl")
    paper_rows = load_jsonl(ROOT / "data/simple/epoch_v2/research_paper_lifecycle_history.jsonl")
    outcome_rows = load_jsonl(ROOT / "data/simple/epoch_v2/outcome_accounting_history.jsonl")
    edge_rows = load_jsonl(ROOT / "data/simple/epoch_v2/contract_edge_matrix_history.jsonl")

    signal_event_ids = {
        ev["event_id"]
        for row in signal_rows
        for ev in (row.get("events") if isinstance(row.get("events"), list) else [])
        if isinstance(ev, dict) and isinstance(ev.get("event_id"), str) and ev.get("event_id")
    }
    plan_contract_ids = {r.get("contract_id") for r in plan_rows if isinstance(r.get("contract_id"), str) and r.get("contract_id")}
    setup_selected_contracts = {
        r.get("selected_contract")
        for r in setup_rows
        if isinstance(r.get("selected_contract"), str) and r.get("selected_contract")
    }
    decision_contract_ids = {r.get("contract_id") for r in decision_rows if isinstance(r.get("contract_id"), str) and r.get("contract_id")}

    paper_recent_closed_ids = extract_nested_ids(paper_rows, "recent_closed")
    outcome_closed_ids = extract_nested_ids(outcome_rows, "closed_samples")
    outcome_closed_unique = set(outcome_closed_ids)
    paper_closed_unique = set(paper_recent_closed_ids)

    trace = {
        "SETUP→SIGNAL": {
            "parent_total": len(setup_selected_contracts),
            "traceable": len(setup_selected_contracts & signal_event_ids),
            "orphans": len(setup_selected_contracts - signal_event_ids),
            "evidence": "selected_contract vs signal.events[].event_id",
        },
        "SIGNAL→TRADE_PLAN": {
            "parent_total": len(signal_event_ids),
            "traceable": len(signal_event_ids & plan_contract_ids),
            "orphans": len(signal_event_ids - plan_contract_ids),
            "evidence": "signal.events[].event_id vs trade_plan.contract_id",
        },
        "TRADE_PLAN→DECISION": {
            "parent_total": len(plan_contract_ids),
            "traceable": len(plan_contract_ids & decision_contract_ids),
            "orphans": len(plan_contract_ids - decision_contract_ids),
            "evidence": "trade_plan.contract_id vs decision.contract_id",
        },
        "DECISION→PAPER_LIFECYCLE": {
            "parent_total": len(decision_contract_ids),
            "traceable": 0,
            "orphans": len(decision_contract_ids),
            "evidence": "decision_id/paper_trade_id direct link not present",
        },
        "PAPER_LIFECYCLE→OUTCOME": {
            "parent_total": len(paper_closed_unique),
            "traceable": len(paper_closed_unique & outcome_closed_unique),
            "orphans": len(paper_closed_unique - outcome_closed_unique),
            "evidence": "paper.recent_closed[].paper_trade_id vs outcome.closed_samples[].paper_trade_id",
        },
        "OUTCOME→EDGE_MATRIX": {
            "parent_total": len(outcome_closed_unique),
            "traceable": 0,
            "orphans": len(outcome_closed_unique),
            "evidence": "edge rows contain no per-trade outcome_id/paper_trade_id",
        },
    }
    for link, v in trace.items():
        v["status"] = status_from_ratio(v["traceable"], v["parent_total"])

    outcome_type_counter = extract_outcome_types(outcome_rows)
    tp_count = outcome_type_counter.get("TP", 0)
    sl_count = outcome_type_counter.get("SL", 0)
    invalidated_count = outcome_type_counter.get("INVALIDATED", 0)
    closed_outcome_count = len(outcome_closed_unique)

    edge_closed_only_confirmed = False
    edge_snapshot_contamination_detected = False
    edge_evidence = "edge.sample_summary references aggregates; closed-only feed cannot be proven from per-trade IDs"
    for row in edge_rows[-10:]:
        ss = row.get("sample_summary")
        if isinstance(ss, dict):
            closed_cnt = ss.get("closed_count")
            legacy_cnt = ss.get("legacy_sample_count")
            if isinstance(closed_cnt, int) and isinstance(legacy_cnt, int) and legacy_cnt > closed_cnt:
                edge_snapshot_contamination_detected = True

    checks = {
        "setup_records_found": len(setup_rows),
        "signal_records_found": len(signal_rows),
        "trade_plan_records_found": len(plan_rows),
        "decision_records_found": len(decision_rows),
        "paper_records_found": len(paper_rows),
        "outcome_records_found": len(outcome_rows),
        "edge_records_found": len(edge_rows),
        "setup_to_signal_traceable": trace["SETUP→SIGNAL"]["traceable"] > 0,
        "signal_to_plan_traceable": trace["SIGNAL→TRADE_PLAN"]["traceable"] > 0,
        "plan_to_decision_traceable": trace["TRADE_PLAN→DECISION"]["traceable"] > 0,
        "decision_to_paper_traceable": trace["DECISION→PAPER_LIFECYCLE"]["traceable"] > 0,
        "paper_to_outcome_traceable": trace["PAPER_LIFECYCLE→OUTCOME"]["traceable"] > 0,
        "outcome_to_edge_traceable": trace["OUTCOME→EDGE_MATRIX"]["traceable"] > 0,
        "orphan_setup_count": trace["SETUP→SIGNAL"]["orphans"],
        "orphan_signal_count": trace["SIGNAL→TRADE_PLAN"]["orphans"],
        "orphan_plan_count": trace["TRADE_PLAN→DECISION"]["orphans"],
        "orphan_decision_count": trace["DECISION→PAPER_LIFECYCLE"]["orphans"],
        "orphan_paper_count": trace["PAPER_LIFECYCLE→OUTCOME"]["orphans"],
        "orphan_outcome_count": trace["OUTCOME→EDGE_MATRIX"]["orphans"],
        "duplicate_id_count": sum(layer_results[n]["duplicate_ids"] for n in layer_results),
        "closed_outcome_count": closed_outcome_count,
        "tp_count": tp_count,
        "sl_count": sl_count,
        "invalidated_count": invalidated_count,
        "edge_closed_only_confirmed": edge_closed_only_confirmed,
        "edge_snapshot_contamination_detected": edge_snapshot_contamination_detected,
    }

    if checks["setup_records_found"] == 0:
        risk_codes.add("NO_SETUP_RECORDS")
    if checks["signal_records_found"] == 0:
        risk_codes.add("NO_SIGNAL_RECORDS")
    if checks["trade_plan_records_found"] == 0:
        risk_codes.add("NO_TRADE_PLAN_RECORDS")
    if checks["decision_records_found"] == 0:
        risk_codes.add("NO_DECISION_RECORDS")
    if checks["paper_records_found"] == 0:
        risk_codes.add("NO_PAPER_RECORDS")
    if checks["outcome_records_found"] == 0:
        risk_codes.add("NO_OUTCOME_RECORDS")
    if checks["edge_records_found"] == 0:
        risk_codes.add("NO_EDGE_RECORDS")
    if not checks["setup_to_signal_traceable"]:
        risk_codes.add("SETUP_TO_SIGNAL_NOT_TRACEABLE")
    if not checks["signal_to_plan_traceable"]:
        risk_codes.add("SIGNAL_TO_PLAN_NOT_TRACEABLE")
    if not checks["plan_to_decision_traceable"]:
        risk_codes.add("PLAN_TO_DECISION_NOT_TRACEABLE")
    if not checks["decision_to_paper_traceable"]:
        risk_codes.add("DECISION_TO_PAPER_NOT_TRACEABLE")
    if not checks["paper_to_outcome_traceable"]:
        risk_codes.add("PAPER_TO_OUTCOME_NOT_TRACEABLE")
    if not checks["outcome_to_edge_traceable"]:
        risk_codes.add("OUTCOME_TO_EDGE_NOT_TRACEABLE")
    if checks["duplicate_id_count"] > 0:
        risk_codes.add("DUPLICATE_ID_RISK")
    if any(checks[k] > 0 for k in ["orphan_setup_count", "orphan_signal_count", "orphan_plan_count", "orphan_decision_count", "orphan_paper_count", "orphan_outcome_count"]):
        risk_codes.add("ORPHAN_RECORD_RISK")
    if not checks["edge_closed_only_confirmed"]:
        risk_codes.add("EDGE_NOT_CLOSED_ONLY")
    if checks["edge_snapshot_contamination_detected"]:
        risk_codes.add("SNAPSHOT_CONTAMINATION_RISK")
    if checks["closed_outcome_count"] == 0:
        risk_codes.add("PAPER_OUTCOME_NOT_PROVEN")
    if checks["tp_count"] == 0 and checks["sl_count"] == 0 and checks["invalidated_count"] == 0:
        risk_codes.add("NO_TP_SL_EVIDENCE")

    lineage_judgement = "PASS"
    if any(r in risk_codes for r in ["SETUP_TO_SIGNAL_NOT_TRACEABLE", "SIGNAL_TO_PLAN_NOT_TRACEABLE", "PLAN_TO_DECISION_NOT_TRACEABLE", "DECISION_TO_PAPER_NOT_TRACEABLE", "PAPER_TO_OUTCOME_NOT_TRACEABLE", "OUTCOME_TO_EDGE_NOT_TRACEABLE"]):
        lineage_judgement = "PARTIAL"
    if any(r in risk_codes for r in ["NO_SETUP_RECORDS", "NO_SIGNAL_RECORDS", "NO_TRADE_PLAN_RECORDS", "NO_DECISION_RECORDS", "NO_PAPER_RECORDS", "NO_OUTCOME_RECORDS", "NO_EDGE_RECORDS"]):
        lineage_judgement = "FAIL"

    paper_judgement = "PASS" if closed_outcome_count > 0 and (tp_count + sl_count + invalidated_count) > 0 else "KANITLANAMADI"
    edge_judgement = "PASS" if checks["edge_closed_only_confirmed"] and not checks["edge_snapshot_contamination_detected"] else "FAIL"

    if lineage_judgement == "FAIL" or paper_judgement == "FAIL":
        prompt9 = "Prompt 9 = LOCAL LINEAGE NORMALIZATION PATCH PLAN"
    elif lineage_judgement == "PARTIAL":
        prompt9 = "Prompt 9 = LOCAL LINEAGE HARDENING PATCH PLAN"
    elif edge_judgement != "PASS":
        prompt9 = "Prompt 9 = LOCAL EDGE CLEAN PATCH PLAN"
    else:
        prompt9 = "Prompt 9 = LOCAL MARKET STATE + ACTIVE SCENARIO AUDIT"

    result = {
        "generated_at_utc": now.isoformat(),
        "checks": checks,
        "layer_results": layer_results,
        "traceability": trace,
        "target_id_fields": TARGET_ID_FIELDS,
        "lineage_inputs": [str(p.relative_to(ROOT)) for p in lineage_paths if p.exists()],
        "paper_outcome": {
            "closed_outcome_count": closed_outcome_count,
            "tp_count": tp_count,
            "sl_count": sl_count,
            "invalidated_count": invalidated_count,
            "edge_closed_only_confirmed": edge_closed_only_confirmed,
            "edge_snapshot_contamination_detected": edge_snapshot_contamination_detected,
            "edge_evidence": edge_evidence,
        },
        "net_judgement": {
            "lineage": lineage_judgement,
            "paper_outcome": paper_judgement,
            "edge_cleanliness": edge_judgement,
        },
        "risk_codes": sorted(risk_codes),
        "prompt_9_recommendation": prompt9,
    }

    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    rows_md = []
    for name, d in layer_results.items():
        status = "OK" if d["rows"] > 0 else "KANITLANAMADI"
        rows_md.append(
            f"{name} | {d['rows']} | {d['unique_ids']} | {d['missing_ids']} | {d['duplicate_ids']} | {d['latest_timestamp'] or 'KANITLANAMADI'} | {status}"
        )

    trace_md = []
    for link, d in trace.items():
        trace_md.append(f"{link} | {d['traceable']}/{d['parent_total']} | {d['orphans']} | {d['evidence']} | {d['status']}")

    risks_md = []
    for rc in sorted(risk_codes):
        sev = "HIGH" if rc.startswith("NO_") or rc.endswith("NOT_TRACEABLE") else "MEDIUM"
        fix = "Patch plan gerekli" if sev == "HIGH" else "Hardening gerekli"
        risks_md.append(f"{rc} | JSON evidence available | {sev} | {fix}")

    latest_field_evidence = []
    for name, d in layer_results.items():
        latest_field_evidence.append(
            f"- {name}: file=`{d['path']}`, lines={d['rows']}, latest_fields={','.join(d['latest_record_keys'][:24]) or 'KANITLANAMADI'}"
        )

    md = f"""# VPS LINEAGE + PAPER OUTCOME REALITY AUDIT REPORT

## 1. Net Hüküm
Lineage:
{lineage_judgement}

Paper outcome:
{paper_judgement}

Edge cleanliness:
{edge_judgement}

## 2. Record Counts
Layer | Rows | Unique IDs | Missing IDs | Duplicate IDs | Latest Timestamp | Status
---|---:|---:|---:|---:|---|---
{chr(10).join(rows_md)}

## 3. Parent-Child Traceability
Link | Traceable Count | Orphan Count | Evidence | Status
---|---|---:|---|---
{chr(10).join(trace_md)}

## 4. Paper Outcome Reality
Outcome Type | Count | Evidence | Status
---|---:|---|---
TP | {tp_count} | outcome_accounting.closed_samples[].final_result | {"PASS" if tp_count > 0 else "KANITLANAMADI"}
SL | {sl_count} | outcome_accounting.closed_samples[].final_result | {"PASS" if sl_count > 0 else "KANITLANAMADI"}
INVALIDATED | {invalidated_count} | outcome_accounting.closed_samples[].final_result | {"PASS" if invalidated_count > 0 else "KANITLANAMADI"}

## 5. Edge Cleanliness
Edge Source | Closed Only? | Snapshot Risk | Evidence | Status
---|---|---|---|---
contract_edge_matrix_history.jsonl | {str(edge_closed_only_confirmed)} | {str(edge_snapshot_contamination_detected)} | {edge_evidence} | {edge_judgement}

## 6. Critical Risks
Risk Code | Evidence | Severity | Required Fix
---|---|---|---
{chr(10).join(risks_md) if risks_md else "KANITLANAMADI | KANITLANAMADI | LOW | monitor"}

## 7. Prompt 9 Recommendation
{prompt9}

## 8. Kanıt Notları
{chr(10).join(latest_field_evidence)}
- Orphan örneği (SETUP→SIGNAL): {next(iter(setup_selected_contracts - signal_event_ids), "KANITLANAMADI")}
- Orphan örneği (DECISION→PAPER): {next(iter(decision_contract_ids), "KANITLANAMADI")} (decision_id/paper_trade_id link field yok)
- Edge closed-only kanıtı: KANITLANAMADI (per-trade outcome_id/paper_trade_id mapping edge katmanında yok)
"""
    OUT_MD.write_text(md, encoding="utf-8")
    OUT_REC.write_text(prompt9 + "\n", encoding="utf-8")

    print(f"Wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote: {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote: {OUT_REC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
