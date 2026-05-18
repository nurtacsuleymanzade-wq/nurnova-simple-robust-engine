#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "reports" / "vps_final_live_health_preaudit.json"
OUT_MD = ROOT / "reports" / "vps_final_live_health_preaudit_report.md"
OUT_REC = ROOT / "reports" / "vps_prompt_14_recommendation.md"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def load_jsonl_last(path: Path) -> tuple[int, dict[str, Any]]:
    if not path.exists():
        return 0, {}
    lines = path.read_text(encoding="utf-8").splitlines()
    cnt = len(lines)
    if not lines:
        return cnt, {}
    try:
        obj = json.loads(lines[-1])
    except Exception:
        return cnt, {}
    return cnt, obj if isinstance(obj, dict) else {}


def parse_ts(ts: Any) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def freshness_min(ts: Any, now: datetime) -> float | None:
    dt = parse_ts(ts)
    if not dt:
        return None
    return round((now - dt).total_seconds() / 60, 2)


def run_ps() -> list[str]:
    try:
        out = subprocess.check_output(
            ["bash", "-lc", "ps -eo pid,ppid,cmd --sort=pid"],
            cwd=str(ROOT),
            text=True,
        )
    except Exception:
        return []
    return out.splitlines()


def main() -> None:
    now = datetime.now(timezone.utc)
    spine = load_json(ROOT / "reports" / "vps_data_spine_reality.json")
    lineage = load_json(ROOT / "reports" / "vps_lineage_outcome_audit.json")
    market = load_json(ROOT / "reports" / "vps_market_state_scenario_audit.json")
    conditional = load_json(ROOT / "reports" / "vps_conditional_edge_audit.json")
    template = load_json(ROOT / "reports" / "vps_template_reality_audit.json")

    files = {
        "RAW": ROOT / "data/simple/live_depth_events.jsonl",
        "1S": ROOT / "state/simple/latest_1s_evidence.json",
        "DNA": ROOT / "state/simple/latest_mtf_candle_dna.json",
        "MARKET_STATE": ROOT / "state/simple/latest_unified_context.json",
        "ACTIVE_SCENARIO": ROOT / "state/simple/latest_three_scenarios.json",
        "SETUP": ROOT / "data/simple/epoch_v2/setup_contract_history.jsonl",
        "SIGNAL": ROOT / "data/simple/epoch_v2/signal_event_history.jsonl",
        "TRADE_PLAN": ROOT / "data/simple/epoch_v2/contract_trade_plan_history.jsonl",
        "DECISION": ROOT / "data/simple/epoch_v2/contract_decision_gate_history.jsonl",
        "PAPER": ROOT / "data/simple/epoch_v2/research_paper_lifecycle_history.jsonl",
        "OUTCOME": ROOT / "data/simple/epoch_v2/outcome_accounting_history.jsonl",
        "EDGE": ROOT / "data/simple/epoch_v2/research_edge_matrix_history.jsonl",
        "REPORT": ROOT / "data/simple/epoch_v2/telegram_report_history.jsonl",
    }

    layer_rows: dict[str, int] = {}
    layer_ts: dict[str, Any] = {}
    layer_keys: dict[str, list[str]] = {}
    for name, path in files.items():
        if path.suffix == ".jsonl":
            rows, last = load_jsonl_last(path)
        else:
            if not path.exists():
                rows, last = 0, {}
            else:
                txt = path.read_text(encoding="utf-8")
                rows = len(txt.splitlines())
                try:
                    obj = json.loads(txt)
                except Exception:
                    obj = {}
                last = obj if isinstance(obj, dict) else {}
        layer_rows[name] = rows
        ts = last.get("timestamp_utc") or last.get("timestamp") or last.get("generated_at_utc")
        layer_ts[name] = ts
        layer_keys[name] = sorted(last.keys())[:24] if isinstance(last, dict) else []

    ps_lines = run_ps()
    runtime_markers = ["run.py", "run_loop.py", "pipeline.py", "telegram", "nurnova", "nova core", "simple/"]
    proc_lines = [ln for ln in ps_lines if any(m.lower() in ln.lower() for m in runtime_markers)]
    loop_lines = [ln for ln in ps_lines if any(m in ln for m in ["run_loop.py", "pipeline.py", "run.py"])]
    duplicate_loop = "DETECTED" if len(loop_lines) > 1 else "NONE"

    chain_order = ["RAW", "1S", "DNA", "MARKET_STATE", "ACTIVE_SCENARIO", "SETUP", "SIGNAL", "TRADE_PLAN", "DECISION", "PAPER", "OUTCOME", "EDGE", "REPORT"]
    chain_links = []
    for i in range(len(chain_order) - 1):
        a, b = chain_order[i], chain_order[i + 1]
        st = "PASS" if layer_rows[a] > 0 and layer_rows[b] > 0 else "FAIL"
        if st == "PASS" and (layer_ts[a] is None or layer_ts[b] is None):
            st = "PARTIAL"
        chain_links.append(
            {
                "link": f"{a}→{b}",
                "status": st,
                "evidence": f"{a}:{layer_rows[a]} rows ts={layer_ts[a]} | {b}:{layer_rows[b]} rows ts={layer_ts[b]}",
                "risk": "" if st == "PASS" else "CHAIN_LINK_MISSING",
            }
        )

    data_spine_status = spine.get("net_judgement", {}).get("vps_data_spine") if isinstance(spine.get("net_judgement"), dict) else None
    if not data_spine_status:
        data_spine_status = "PARTIAL"
    lineage_status = lineage.get("net_judgement", {}).get("lineage", "KANITLANAMADI")
    paper_status = lineage.get("net_judgement", {}).get("paper_outcome", "KANITLANAMADI")
    edge_status = conditional.get("judgement", {}).get("edge_cleanliness", "KANITLANAMADI")
    template_risk = template.get("template_risk", "MEDIUM")
    if not isinstance(template_risk, str):
        template_risk = "MEDIUM"

    chain_integrity = "PASS" if all(x["status"] == "PASS" for x in chain_links) else "PARTIAL"
    if any(x["status"] == "FAIL" for x in chain_links):
        chain_integrity = "FAIL"

    blockers: list[str] = []
    if chain_integrity != "PASS":
        blockers.append("CHAIN_INTEGRITY_NOT_PASS")
    if lineage_status != "PASS":
        blockers.append("LINEAGE_NOT_PASS")
    if paper_status not in ["PASS", "PARTIAL"]:
        blockers.append("PAPER_OUTCOME_NOT_PROVEN")
    if edge_status != "PASS":
        blockers.append("EDGE_CLEAN_NOT_PASS")
    if duplicate_loop == "DETECTED":
        blockers.append("DUPLICATE_LOOP_DETECTED")
    if str(template_risk).upper() == "HIGH":
        blockers.append("TEMPLATE_RISK_HIGH")
    if market.get("judgement", {}).get("active_scenario") != "PASS":
        blockers.append("ACTIVE_SCENARIO_NOT_READY")
    if conditional.get("judgement", {}).get("conditional_edge") != "PASS":
        blockers.append("CONDITIONAL_EDGE_NOT_READY")

    final_health = "PASS" if not blockers else ("PARTIAL" if len(blockers) <= 3 else "FAIL")
    final_ready = "YES" if final_health == "PASS" else ("PARTIAL" if final_health == "PARTIAL" else "NO")

    final_status = {
        "FINAL_LIVE_HEALTH_AUDIT": final_health,
        "CHAIN_INTEGRITY": chain_integrity,
        "DATA_SPINE": data_spine_status,
        "LINEAGE": lineage_status,
        "PAPER_OUTCOME": paper_status,
        "EDGE_CLEAN": edge_status,
        "DUPLICATE_LOOP": duplicate_loop,
        "TEMPLATE_RISK": str(template_risk).upper(),
        "FINAL_BLOCKERS": blockers,
    }

    data_freshness = []
    for name in ["RAW", "1S", "DNA", "MARKET_STATE", "ACTIVE_SCENARIO", "OUTCOME", "EDGE", "REPORT"]:
        age = freshness_min(layer_ts[name], now)
        st = "PASS" if age is not None and age <= 30 else ("PARTIAL" if age is not None else "FAIL")
        if age is not None and age > 30:
            st = "FAIL"
        data_freshness.append(
            {
                "layer": name,
                "file": str(files[name].relative_to(ROOT)),
                "timestamp": layer_ts[name],
                "freshness_min": age,
                "status": st,
            }
        )

    result = {
        "generated_at_utc": now.isoformat(),
        "final_status": final_status,
        "runtime_health": {
            "active_process_like_count": len(proc_lines),
            "loop_process_like_count": len(loop_lines),
            "duplicate_loop": duplicate_loop,
            "process_evidence": proc_lines[-20:],
        },
        "counts": layer_rows,
        "timestamps": layer_ts,
        "data_freshness": data_freshness,
        "chain_integrity_links": chain_links,
        "template_risk_summary": {
            "status": str(template_risk).upper(),
            "evidence": "reports/vps_template_reality_audit_report.md",
        },
        "prompt_14_recommendation": "Prompt 14 = VPS FINAL LIVE HEALTH AUDIT" if not blockers else "Prompt 14 = LOCAL PATCH PLAN (FINAL_BLOCKERS)",
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    matrix = [
        f"FINAL_LIVE_HEALTH_AUDIT | {final_status['FINAL_LIVE_HEALTH_AUDIT']} | blockers={len(blockers)} | {'YES' if blockers else 'NO'}",
        f"CHAIN_INTEGRITY | {final_status['CHAIN_INTEGRITY']} | links={len(chain_links)} | {'YES' if final_status['CHAIN_INTEGRITY']!='PASS' else 'NO'}",
        f"DATA_SPINE | {final_status['DATA_SPINE']} | reports/vps_data_spine_reality_report.md | {'YES' if final_status['DATA_SPINE']!='PASS' else 'NO'}",
        f"LINEAGE | {final_status['LINEAGE']} | reports/vps_lineage_outcome_audit_report.md | {'YES' if final_status['LINEAGE']!='PASS' else 'NO'}",
        f"PAPER_OUTCOME | {final_status['PAPER_OUTCOME']} | reports/vps_lineage_outcome_audit_report.md | {'YES' if final_status['PAPER_OUTCOME']=='FAIL' else 'NO'}",
        f"EDGE_CLEAN | {final_status['EDGE_CLEAN']} | reports/vps_conditional_edge_audit_report.md | {'YES' if final_status['EDGE_CLEAN']!='PASS' else 'NO'}",
        f"DUPLICATE_LOOP | {final_status['DUPLICATE_LOOP']} | process scan | {'YES' if final_status['DUPLICATE_LOOP']=='DETECTED' else 'NO'}",
        f"TEMPLATE_RISK | {final_status['TEMPLATE_RISK']} | reports/vps_template_reality_audit_report.md | {'YES' if final_status['TEMPLATE_RISK']=='HIGH' else 'NO'}",
    ]

    runtime_rows = []
    for ln in proc_lines[-10:]:
        runtime_rows.append(f"{ln} | yes | process-scan | {'HIGH' if 'run_loop.py' in ln else 'LOW'} | ps -eo")
    if not runtime_rows:
        runtime_rows = ["KANITLANAMADI | no | KANITLANAMADI | KANITLANAMADI | process evidence missing"]

    freshness_rows = []
    for d in data_freshness:
        freshness_rows.append(f"{d['layer']} | {d['file']} | {d['timestamp'] or 'KANITLANAMADI'} | {d['freshness_min'] if d['freshness_min'] is not None else 'KANITLANAMADI'}m | {d['status']}")

    chain_rows = [f"{c['link']} | {c['status']} | {c['evidence']} | {c['risk'] or '-'}" for c in chain_links]

    loe_rows = [
        f"SETUP | {layer_rows['SETUP']} | {('PASS' if lineage_status!='FAIL' else 'FAIL')} | KANITLANAMADI | data/simple/epoch_v2/setup_contract_history.jsonl",
        f"SIGNAL | {layer_rows['SIGNAL']} | {('PASS' if layer_rows['SIGNAL']>0 else 'FAIL')} | KANITLANAMADI | data/simple/epoch_v2/signal_event_history.jsonl",
        f"TRADE_PLAN | {layer_rows['TRADE_PLAN']} | PARTIAL | KANITLANAMADI | data/simple/epoch_v2/contract_trade_plan_history.jsonl",
        f"DECISION | {layer_rows['DECISION']} | PARTIAL | KANITLANAMADI | data/simple/epoch_v2/contract_decision_gate_history.jsonl",
        f"PAPER | {layer_rows['PAPER']} | PARTIAL | NO (open/closed mixed) | data/simple/epoch_v2/research_paper_lifecycle_history.jsonl",
        f"OUTCOME | {layer_rows['OUTCOME']} | {paper_status} | YES (closed_samples exists) | data/simple/epoch_v2/outcome_accounting_history.jsonl",
        f"EDGE | {layer_rows['EDGE']} | {conditional.get('judgement',{}).get('conditional_edge','KANITLANAMADI')} | {('NO' if conditional.get('checks',{}).get('edge_excludes_snapshots') is False else 'KANITLANAMADI')} | data/simple/epoch_v2/research_edge_matrix_history.jsonl",
    ]

    tr_rows = [
        f"active_scenario | {('HIGH' if market.get('judgement',{}).get('active_scenario')!='PASS' else 'LOW')} | reports/vps_market_state_scenario_audit_report.md | {market.get('judgement',{}).get('active_scenario','KANITLANAMADI')}",
        f"conditional_edge | {('HIGH' if conditional.get('judgement',{}).get('conditional_edge')!='PASS' else 'LOW')} | reports/vps_conditional_edge_audit_report.md | {conditional.get('judgement',{}).get('conditional_edge','KANITLANAMADI')}",
        f"edge_cleanliness | {('HIGH' if edge_status!='PASS' else 'LOW')} | reports/vps_conditional_edge_audit_report.md | {edge_status}",
    ]

    blocker_rows = []
    for b in blockers:
        blocker_rows.append(f"{b} | HIGH | Local patch plan gerekli | Prompt 14")
    if not blocker_rows:
        blocker_rows = ["KANITLANAMADI | LOW | blocker yok | Prompt 14"]

    md = f"""# VPS FINAL LIVE HEALTH PRE-AUDIT REPORT

## 1. Net Hüküm
Final’a hazır mı?
{final_ready}

## 2. Final Status Matrix
Criterion | Status | Evidence | Blocker?
---|---|---|---
{chr(10).join(matrix)}

## 3. Runtime Health
Process/Service | Active | Role | Duplicate Risk | Evidence
---|---|---|---|---
{chr(10).join(runtime_rows)}

## 4. Data Freshness
Layer | Latest File | Latest Timestamp | Freshness | Status
---|---|---|---|---
{chr(10).join(freshness_rows)}

## 5. Chain Integrity
Link | Status | Evidence | Risk
---|---|---|---
{chr(10).join(chain_rows)}

## 6. Lineage + Outcome + Edge
Layer | Count | Traceable? | Closed Only? | Evidence
---|---:|---|---|---
{chr(10).join(loe_rows)}

## 7. Template Risk Summary
Field | Risk | Evidence | Status
---|---|---|---
template_output | {final_status['TEMPLATE_RISK']} | reports/vps_template_reality_audit_report.md | {('PASS' if final_status['TEMPLATE_RISK'] in ['LOW','MEDIUM'] else 'FAIL')}

## 8. Final Blockers
Blocker | Severity | Required Fix | Next Prompt
---|---|---|---
{chr(10).join(blocker_rows)}

## 9. Prompt 14 Recommendation
{result['prompt_14_recommendation']}
"""
    OUT_MD.write_text(md, encoding="utf-8")
    OUT_REC.write_text(result["prompt_14_recommendation"] + "\n", encoding="utf-8")

    print(f"Wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote: {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote: {OUT_REC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
