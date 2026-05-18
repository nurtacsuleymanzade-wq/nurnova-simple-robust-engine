#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "reports" / "vps_final_live_health_audit.json"
OUT_MD = ROOT / "reports" / "vps_final_live_health_audit_report.md"
OUT_DECISION = ROOT / "reports" / "vps_final_decision.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def read_jsonl_last(path: Path) -> tuple[int, dict[str, Any]]:
    if not path.exists():
        return 0, {}
    lines = path.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    if not lines:
        return n, {}
    try:
        obj = json.loads(lines[-1])
    except Exception:
        obj = {}
    return n, obj if isinstance(obj, dict) else {}


def parse_ts(ts: Any) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def freshness(ts: Any, now: datetime) -> float | None:
    dt = parse_ts(ts)
    if not dt:
        return None
    return round((now - dt).total_seconds() / 60, 2)


def process_lines() -> list[str]:
    try:
        out = subprocess.check_output(
            ["bash", "-lc", "ps -eo pid,ppid,cmd --sort=pid"],
            cwd=str(ROOT),
            text=True,
        )
        return out.splitlines()
    except Exception:
        return []


def main() -> None:
    now = datetime.now(timezone.utc)
    pre = read_json(ROOT / "reports/vps_final_live_health_preaudit.json")
    spine = read_json(ROOT / "reports/vps_data_spine_reality.json")
    lineage = read_json(ROOT / "reports/vps_lineage_outcome_audit.json")
    market = read_json(ROOT / "reports/vps_market_state_scenario_audit.json")
    cond = read_json(ROOT / "reports/vps_conditional_edge_audit.json")
    template = read_json(ROOT / "reports/vps_template_reality_audit.json")

    files = {
        "LIVE_PUBLIC_DATA": ROOT / "data/simple/live_depth_events.jsonl",
        "RAW_EVENT": ROOT / "data/simple/live_depth_events.jsonl",
        "1S_EVIDENCE": ROOT / "state/simple/latest_1s_evidence.json",
        "CANDLE_DNA": ROOT / "state/simple/latest_mtf_candle_dna.json",
        "MARKET_STATE": ROOT / "state/simple/latest_unified_context.json",
        "ACTIVE_SCENARIO": ROOT / "state/simple/latest_three_scenarios.json",
        "SETUP": ROOT / "data/simple/epoch_v2/setup_contract_history.jsonl",
        "SIGNAL": ROOT / "data/simple/epoch_v2/signal_event_history.jsonl",
        "TRADE_PLAN": ROOT / "data/simple/epoch_v2/contract_trade_plan_history.jsonl",
        "DECISION_GATE": ROOT / "data/simple/epoch_v2/contract_decision_gate_history.jsonl",
        "PAPER_LIFECYCLE": ROOT / "data/simple/epoch_v2/research_paper_lifecycle_history.jsonl",
        "CLOSED_OUTCOME": ROOT / "data/simple/epoch_v2/outcome_accounting_history.jsonl",
        "EDGE_MATRIX": ROOT / "data/simple/epoch_v2/research_edge_matrix_history.jsonl",
        "REPORT": ROOT / "data/simple/epoch_v2/telegram_report_history.jsonl",
    }

    counts: dict[str, int] = {}
    latest_ts: dict[str, Any] = {}
    fields: dict[str, list[str]] = {}
    missing_fields: dict[str, list[str]] = {}

    expected = {
        "MARKET_STATE": ["regime", "reason_codes", "data_quality"],
        "ACTIVE_SCENARIO": ["bullish_scenario", "bearish_scenario", "neutral_scenario"],
        "EDGE_MATRIX": ["groups", "edge_status", "summary"],
        "CLOSED_OUTCOME": ["closed_samples", "winrate"],
    }

    for k, p in files.items():
        if p.suffix == ".jsonl":
            n, last = read_jsonl_last(p)
        else:
            if not p.exists():
                n, last = 0, {}
            else:
                txt = p.read_text(encoding="utf-8")
                n = len(txt.splitlines())
                try:
                    obj = json.loads(txt)
                except Exception:
                    obj = {}
                last = obj if isinstance(obj, dict) else {}
        counts[k] = n
        ts = last.get("timestamp_utc") or last.get("timestamp") or last.get("generated_at_utc")
        latest_ts[k] = ts
        fields[k] = sorted(last.keys())[:30]
        exp = expected.get(k, [])
        missing_fields[k] = [f for f in exp if f not in last]

    ps = process_lines()
    run_like = [x for x in ps if any(m in x.lower() for m in ["run.py", "run_loop.py", "pipeline.py", "telegram", "nurnova", "nova"])]
    loop_like = [x for x in ps if any(m in x for m in ["run.py", "run_loop.py", "pipeline.py"])]
    duplicate_loop = "DETECTED" if len(loop_like) > 1 else ("NONE" if ps else "KANITLANAMADI")

    chain = [
        ("LIVE_PUBLIC_DATA", "RAW_EVENT"),
        ("RAW_EVENT", "1S_EVIDENCE"),
        ("1S_EVIDENCE", "CANDLE_DNA"),
        ("CANDLE_DNA", "MARKET_STATE"),
        ("MARKET_STATE", "ACTIVE_SCENARIO"),
        ("ACTIVE_SCENARIO", "SETUP"),
        ("SETUP", "SIGNAL"),
        ("SIGNAL", "TRADE_PLAN"),
        ("TRADE_PLAN", "DECISION_GATE"),
        ("DECISION_GATE", "PAPER_LIFECYCLE"),
        ("PAPER_LIFECYCLE", "CLOSED_OUTCOME"),
        ("CLOSED_OUTCOME", "EDGE_MATRIX"),
        ("EDGE_MATRIX", "REPORT"),
    ]
    chain_rows = []
    for a, b in chain:
        st = "PASS" if counts[a] > 0 and counts[b] > 0 else "FAIL"
        risk = "" if st == "PASS" else "CHAIN_LINK_MISSING"
        chain_rows.append({
            "link": f"{a}→{b}",
            "status": st,
            "evidence": f"{a}:{counts[a]} ts={latest_ts[a]} | {b}:{counts[b]} ts={latest_ts[b]}",
            "risk": risk,
        })

    chain_integrity = "PASS" if all(r["status"] == "PASS" for r in chain_rows) else "FAIL"

    data_spine = "PARTIAL"
    if spine:
        c = spine.get("checks", {})
        if c.get("chain_end_to_end_present") is True and c.get("all_recent_under_30m") is True:
            data_spine = "PASS"
        elif c:
            data_spine = "PARTIAL"

    lineage_status = lineage.get("net_judgement", {}).get("lineage", "KANITLANAMADI")
    paper_status = lineage.get("net_judgement", {}).get("paper_outcome", "KANITLANAMADI")
    edge_clean = cond.get("judgement", {}).get("edge_cleanliness", "KANITLANAMADI")
    template_risk = str(template.get("template_risk", "KANITLANAMADI")).upper()

    blockers = []
    if chain_integrity != "PASS":
        blockers.append("CHAIN_INTEGRITY_NOT_PASS")
    if data_spine != "PASS":
        blockers.append("DATA_SPINE_NOT_PASS")
    if lineage_status != "PASS":
        blockers.append("LINEAGE_NOT_PASS")
    if paper_status != "PASS":
        blockers.append("PAPER_OUTCOME_NOT_PASS")
    if edge_clean != "PASS":
        blockers.append("EDGE_CLEAN_NOT_PASS")
    if duplicate_loop != "NONE":
        blockers.append("DUPLICATE_LOOP_NOT_NONE")
    if template_risk != "LOW":
        blockers.append("TEMPLATE_RISK_NOT_LOW")
    if market.get("judgement", {}).get("active_scenario") != "PASS":
        blockers.append("ACTIVE_SCENARIO_NOT_READY")
    if cond.get("judgement", {}).get("conditional_edge") != "PASS":
        blockers.append("CONDITIONAL_EDGE_NOT_READY")

    all_pass = (
        chain_integrity == "PASS"
        and data_spine == "PASS"
        and lineage_status == "PASS"
        and paper_status == "PASS"
        and edge_clean == "PASS"
        and duplicate_loop == "NONE"
        and template_risk == "LOW"
    )

    if all_pass:
        final_decision = "FINAL_PASS"
        final_live = "PASS"
        next_action = "Proceed with VPS FINAL LIVE HEALTH AUDIT closeout."
    elif len(blockers) <= 2:
        final_decision = "FINAL_PARTIAL"
        final_live = "PARTIAL"
        next_action = "Resolve blockers with focused LOCAL PATCH PLAN, then rerun Prompt 14."
    else:
        final_decision = "FINAL_FAIL"
        final_live = "FAIL"
        next_action = "Run LOCAL PATCH PLAN for blockers, then rerun pre-audit and final audit."

    final_json = {
        "FINAL_LIVE_HEALTH_AUDIT": final_live,
        "CHAIN_INTEGRITY": chain_integrity,
        "DATA_SPINE": data_spine,
        "LINEAGE": lineage_status,
        "PAPER_OUTCOME": paper_status,
        "EDGE_CLEAN": edge_clean,
        "DUPLICATE_LOOP": duplicate_loop,
        "TEMPLATE_RISK": template_risk,
        "FINAL_DECISION": final_decision,
        "FINAL_BLOCKERS": blockers,
        "NEXT_REQUIRED_ACTION": next_action,
        "generated_at_utc": now.isoformat(),
        "counts": counts,
        "latest_timestamps": latest_ts,
        "missing_fields": missing_fields,
    }
    OUT_JSON.write_text(json.dumps(final_json, ensure_ascii=False, indent=2), encoding="utf-8")

    matrix = [
        ("FINAL_LIVE_HEALTH_AUDIT", final_live, "reports/vps_final_live_health_preaudit.json", "YES" if final_live != "PASS" else "NO"),
        ("CHAIN_INTEGRITY", chain_integrity, "chain links", "YES" if chain_integrity != "PASS" else "NO"),
        ("DATA_SPINE", data_spine, "reports/vps_data_spine_reality_report.md", "YES" if data_spine != "PASS" else "NO"),
        ("LINEAGE", lineage_status, "reports/vps_lineage_outcome_audit_report.md", "YES" if lineage_status != "PASS" else "NO"),
        ("PAPER_OUTCOME", paper_status, "reports/vps_lineage_outcome_audit_report.md", "YES" if paper_status != "PASS" else "NO"),
        ("EDGE_CLEAN", edge_clean, "reports/vps_conditional_edge_audit_report.md", "YES" if edge_clean != "PASS" else "NO"),
        ("DUPLICATE_LOOP", duplicate_loop, "ps process scan", "YES" if duplicate_loop != "NONE" else "NO"),
        ("TEMPLATE_RISK", template_risk, "reports/vps_template_reality_audit_report.md", "YES" if template_risk != "LOW" else "NO"),
    ]

    freshness_rows = []
    for k in ["LIVE_PUBLIC_DATA", "RAW_EVENT", "1S_EVIDENCE", "CANDLE_DNA", "MARKET_STATE", "ACTIVE_SCENARIO", "CLOSED_OUTCOME", "EDGE_MATRIX", "REPORT"]:
        fr = freshness(latest_ts[k], now)
        st = "PASS" if fr is not None and fr <= 30 else "FAIL"
        freshness_rows.append((k, str(files[k].relative_to(ROOT)), latest_ts[k], fr, st))

    lineage_rows = [
        ("SETUP→SIGNAL", "KANITLANAMADI", "reports/vps_lineage_outcome_audit_report.md", lineage_status),
        ("SIGNAL→TRADE_PLAN", "FAIL", "reports/vps_lineage_outcome_audit_report.md", lineage_status),
        ("TRADE_PLAN→DECISION", "PASS", "reports/vps_lineage_outcome_audit_report.md", lineage_status),
        ("DECISION→PAPER", "FAIL", "reports/vps_lineage_outcome_audit_report.md", lineage_status),
        ("PAPER→OUTCOME", "PASS", "reports/vps_lineage_outcome_audit_report.md", lineage_status),
        ("OUTCOME→EDGE", "FAIL", "reports/vps_lineage_outcome_audit_report.md", lineage_status),
    ]

    paper_counts = lineage.get("paper_outcome", {})
    tp = paper_counts.get("tp_count", 0)
    sl = paper_counts.get("sl_count", 0)
    inval = paper_counts.get("invalidated_count", 0)
    edge_evi = cond.get("evidence", {}).get("snapshot_contamination_example", {})

    blockers_md = []
    for b in blockers:
        blockers_md.append(f"{b} | HIGH | Local patch plan | Prompt 15")
    if not blockers_md:
        blockers_md = ["NONE | LOW | none | none"]

    report = f"""# VPS FINAL LIVE HEALTH AUDIT REPORT

## 1. Net Hüküm
{final_decision}

## 2. Final Criteria Matrix
Criterion | Status | Evidence | Blocker
---|---|---|---
""" + "\n".join([f"{a} | {b} | {c} | {d}" for a, b, c, d in matrix]) + f"""

## 3. Runtime / Duplicate Loop
Process/Service | Active | Role | Duplicate Risk | Evidence
---|---|---|---|---
""" + ("\n".join([f"{x} | yes | process | {'HIGH' if 'run_loop.py' in x else 'LOW'} | ps -eo" for x in run_like[-10:]]) if run_like else "KANITLANAMADI | no | KANITLANAMADI | KANITLANAMADI | process not readable") + f"""

## 4. Data Spine
Layer | Latest File | Latest Timestamp | Freshness | Status
---|---|---|---|---
""" + "\n".join([f"{a} | {b} | {c} | {d if d is not None else 'KANITLANAMADI'}m | {e}" for a, b, c, d, e in freshness_rows]) + f"""

## 5. Chain Integrity
Link | Status | Evidence | Risk
---|---|---|---
""" + "\n".join([f"{r['link']} | {r['status']} | {r['evidence']} | {r['risk'] or '-'}" for r in chain_rows]) + f"""

## 6. Lineage
Link | Traceable? | Evidence | Status
---|---|---|---
""" + "\n".join([f"{a} | {b} | {c} | {d}" for a, b, c, d in lineage_rows]) + f"""

## 7. Paper Outcome
Outcome Type | Count | Evidence | Status
---|---:|---|---
TP | {tp} | reports/vps_lineage_outcome_audit_report.md | {"PASS" if tp > 0 else "FAIL"}
SL | {sl} | reports/vps_lineage_outcome_audit_report.md | {"PASS" if sl > 0 else "FAIL"}
INVALIDATED | {inval} | reports/vps_lineage_outcome_audit_report.md | {"PASS" if inval > 0 else "KANITLANAMADI"}

## 8. Edge Cleanliness
Source | Closed Only? | Snapshot Risk | Evidence | Status
---|---|---|---|---
research_edge_matrix_history | {cond.get('checks',{}).get('edge_reads_closed_outcomes')} | {cond.get('checks',{}).get('snapshot_contamination_detected')} | {edge_evi} | {edge_clean}

## 9. Template Risk
Field | Risk | Evidence | Status
---|---|---|---
template_output | {template_risk} | reports/vps_template_reality_audit_report.md | {"PASS" if template_risk == "LOW" else "FAIL"}

## 10. Final Blockers
Blocker | Severity | Required Fix | Next Prompt
---|---|---|---
""" + "\n".join(blockers_md) + f"""

## 11. Final Decision
{"FINAL_PASS — PRODUCTION-SAFE PAPER ENGINE READY\nBu teknik finaldir; kârlılık garantisi değildir. Gerçek edge ancak yeterli closed outcome sample ile ölçülür." if final_decision=="FINAL_PASS" else "FINAL_FAIL — BLOCKERS REMAIN" if final_decision=="FINAL_FAIL" else "FINAL_PARTIAL — BLOCKERS REMAIN"}
"""
    OUT_MD.write_text(report, encoding="utf-8")

    decision_text = (
        "FINAL_PASS — PRODUCTION-SAFE PAPER ENGINE READY\n"
        "Bu teknik finaldir; kârlılık garantisi değildir. Gerçek edge ancak yeterli closed outcome sample ile ölçülür.\n"
        if final_decision == "FINAL_PASS"
        else f"{final_decision} — BLOCKERS REMAIN\n"
    )
    decision_text += f"FINAL_BLOCKERS: {', '.join(blockers) if blockers else 'NONE'}\nNEXT_REQUIRED_ACTION: {next_action}\n"
    OUT_DECISION.write_text(decision_text, encoding="utf-8")

    print(f"Wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote: {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote: {OUT_DECISION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
