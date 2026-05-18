import json
from pathlib import Path
from datetime import datetime, timezone

BASE = Path("/root/nurnova-simple-robust-engine")

def read_json(path):
    p = BASE / path
    if not p.exists():
        return None, f"MISSING:{path}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, f"INVALID_JSON:{path}:{e}"

files = {
    "market_state": "state/market_state/latest_market_state.json",
    "active_scenario": "state/active_scenario/latest_active_scenario.json",
    "flow_reaction": "state/flow_reaction/latest_flow_reaction.json",
    "setup_entry": "state/setup_entry/latest_setup_entry.json",
    "trade_decision": "state/trade_decision/latest_trade_decision.json",
}

data, errors = {}, []
for name, path in files.items():
    obj, err = read_json(path)
    data[name] = obj
    if err:
        errors.append(err)

critical_failures, warnings, strengths, next_actions = [], [], [], []

required = {
    "market_state": ["timestamp_utc", "market_state_id", "lineage_id", "market_regime", "data_quality", "reason_codes", "feeds_next"],
    "active_scenario": ["timestamp_utc", "active_scenario_id", "lineage_id", "market_state_id", "active_scenario", "scenario_confidence", "data_quality", "reason_codes", "feeds_next"],
    "flow_reaction": ["timestamp_utc", "flow_reaction_id", "lineage_id", "market_state_id", "active_scenario_id", "flow_confirmation", "post_liquidity_reaction", "data_quality", "reason_codes", "feeds_next"],
    "setup_entry": ["timestamp_utc", "setup_candidate_id", "entry_trigger_id", "lineage_id", "market_state_id", "active_scenario_id", "flow_reaction_id", "setup_candidate", "entry_trigger_status", "data_quality", "reason_codes", "feeds_next"],
    "trade_decision": ["timestamp_utc", "trade_plan_id", "decision_id", "lineage_id", "setup_candidate_id", "entry_trigger_id", "side", "decision_status", "data_quality", "reason_codes", "feeds_next"],
}

missing_fields = {}
for name, fields in required.items():
    obj = data.get(name)
    if not obj:
        missing_fields[name] = fields
    else:
        miss = [f for f in fields if f not in obj]
        if miss:
            missing_fields[name] = miss

if missing_fields:
    critical_failures.append({"type": "MISSING_REQUIRED_FIELDS", "details": missing_fields})
else:
    strengths.append("All required output contract fields exist for Phase 4-6 chain.")

link_checks = {}
if data.get("active_scenario") and data.get("market_state"):
    link_checks["active_scenario_market_state_link"] = data["active_scenario"].get("market_state_id") == data["market_state"].get("market_state_id")
if data.get("flow_reaction") and data.get("active_scenario"):
    link_checks["flow_reaction_active_scenario_link"] = data["flow_reaction"].get("active_scenario_id") == data["active_scenario"].get("active_scenario_id")
if data.get("flow_reaction") and data.get("market_state"):
    link_checks["flow_reaction_market_state_link"] = data["flow_reaction"].get("market_state_id") == data["market_state"].get("market_state_id")
if data.get("setup_entry") and data.get("flow_reaction"):
    link_checks["setup_entry_flow_reaction_link"] = data["setup_entry"].get("flow_reaction_id") == data["flow_reaction"].get("flow_reaction_id")
if data.get("setup_entry") and data.get("active_scenario"):
    link_checks["setup_entry_active_scenario_link"] = data["setup_entry"].get("active_scenario_id") == data["active_scenario"].get("active_scenario_id")
if data.get("trade_decision") and data.get("setup_entry"):
    link_checks["trade_decision_setup_candidate_link"] = data["trade_decision"].get("setup_candidate_id") == data["setup_entry"].get("setup_candidate_id")
    link_checks["trade_decision_entry_trigger_link"] = data["trade_decision"].get("entry_trigger_id") == data["setup_entry"].get("entry_trigger_id")

broken_links = {k:v for k,v in link_checks.items() if v is False}
if broken_links:
    critical_failures.append({"type": "BROKEN_CHAIN_LINKS", "details": broken_links})
elif link_checks:
    strengths.append("Phase 4-6 ID links are preserved across available latest state files.")

dq = {k: (v or {}).get("data_quality") for k,v in data.items()}
bad_dq = {k:v for k,v in dq.items() if v in ("INVALID", None)}
if bad_dq:
    warnings.append({"type": "DATA_QUALITY_RISK", "details": bad_dq})

td = data.get("trade_decision") or {}
template_risks = []
if td:
    if td.get("rr_to_tp1") in (1.8, "1.8") or td.get("rr_to_tp2") in (1.8, "1.8"):
        template_risks.append("RR_EQUALS_1_8_TEMPLATE_RISK")
    scores = td.get("scores") or {}
    if isinstance(scores, dict) and scores.get("template_risk_score", 0) not in (0, 0.0, None):
        template_risks.append(f"TEMPLATE_RISK_SCORE={scores.get('template_risk_score')}")
    if td.get("decision_status") == "ALLOW_PAPER":
        for f in ["entry_price", "stop_loss", "take_profit_1", "invalidation_level"]:
            if td.get(f) in (None, "", 0):
                template_risks.append(f"ALLOW_PAPER_WITH_MISSING_{f.upper()}")
        if ((td.get("position_policy") or {}).get("real_trade_allowed") is not False):
            template_risks.append("REAL_TRADE_ALLOWED_NOT_FALSE")
    if td.get("decision_status") == "BLOCK":
        strengths.append("Decision Gate currently blocks invalid/unsafe plan instead of forcing trade.")

if template_risks:
    warnings.append({"type": "TEMPLATE_OR_GATE_RISK", "details": template_risks})

evidence_empty = {}
for name, obj in data.items():
    if obj and isinstance(obj.get("evidence"), dict):
        ev = obj.get("evidence")
        if all(v in ({}, [], None, "") for v in ev.values()):
            evidence_empty[name] = True
if evidence_empty:
    warnings.append({"type": "EMPTY_EVIDENCE_OBJECTS", "details": evidence_empty})

audit_status = "FAIL" if critical_failures else ("PARTIAL" if warnings else "PASS")
next_actions.append("Review critical_failures and warnings before Phase 7." if audit_status != "PASS" else "Phase 4-6 chain is acceptable for Phase 7 paper outcome layer.")

result = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "audit_name": "PHASE_4_6_LIVE_CHAIN_AUDIT",
    "audit_status": audit_status,
    "causal_integrity": {"link_checks": link_checks, "broken_links": broken_links},
    "lineage_integrity": {"lineage_ids": {k: (v or {}).get("lineage_id") for k,v in data.items()}},
    "setup_quality": {
        "setup_candidate": (data.get("setup_entry") or {}).get("setup_candidate"),
        "entry_trigger_status": (data.get("setup_entry") or {}).get("entry_trigger_status"),
        "setup_confidence": (data.get("setup_entry") or {}).get("setup_confidence"),
    },
    "template_risk": {"risks": template_risks, "rr_to_tp1": td.get("rr_to_tp1"), "rr_to_tp2": td.get("rr_to_tp2")},
    "gate_integrity": {
        "decision_status": td.get("decision_status"),
        "blocking_reason_codes": td.get("blocking_reason_codes"),
        "real_trade_allowed": ((td.get("position_policy") or {}).get("real_trade_allowed")),
    },
    "critical_failures": critical_failures,
    "warnings": warnings,
    "strengths": strengths,
    "next_required_actions": next_actions,
    "input_errors": errors,
}

out_json = BASE / "state/audit/latest_phase_4_6_chain_audit.json"
out_md = BASE / "reports/audit/phase_4_6_live_chain_audit.md"
out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

md = [
    "# PHASE 4→6 LIVE CHAIN AUDIT",
    f"- timestamp_utc: {result['timestamp_utc']}",
    f"- audit_status: **{audit_status}**",
    "",
    "## Causal Integrity",
    "```json",
    json.dumps(result["causal_integrity"], indent=2, ensure_ascii=False),
    "```",
    "",
    "## Template Risk",
    "```json",
    json.dumps(result["template_risk"], indent=2, ensure_ascii=False),
    "```",
    "",
    "## Gate Integrity",
    "```json",
    json.dumps(result["gate_integrity"], indent=2, ensure_ascii=False),
    "```",
    "",
    "## Critical Failures",
    "```json",
    json.dumps(critical_failures, indent=2, ensure_ascii=False),
    "```",
    "",
    "## Warnings",
    "```json",
    json.dumps(warnings, indent=2, ensure_ascii=False),
    "```",
    "",
    "## Strengths",
]
md += [f"- {s}" for s in strengths]
md += ["", "## Next Required Actions"]
md += [f"- {a}" for a in next_actions]
out_md.write_text("\n".join(md), encoding="utf-8")

print(json.dumps({
    "audit_status": audit_status,
    "critical_failures": len(critical_failures),
    "warnings": len(warnings),
    "report": str(out_md),
    "json": str(out_json),
}, indent=2))
