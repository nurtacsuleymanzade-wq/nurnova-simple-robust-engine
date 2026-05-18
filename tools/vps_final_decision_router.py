#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IN_AUDIT_JSON = ROOT / "reports" / "vps_final_live_health_audit.json"
IN_AUDIT_MD = ROOT / "reports" / "vps_final_live_health_audit_report.md"
IN_PRE_MD = ROOT / "reports" / "vps_final_live_health_preaudit_report.md"
IN_SPINE_MD = ROOT / "reports" / "vps_data_spine_reality_report.md"
IN_TEMPLATE_MD = ROOT / "reports" / "vps_template_reality_audit_report.md"
IN_LINEAGE_MD = ROOT / "reports" / "vps_lineage_outcome_audit_report.md"
IN_MARKET_MD = ROOT / "reports" / "vps_market_state_scenario_audit_report.md"
IN_EDGE_MD = ROOT / "reports" / "vps_conditional_edge_audit_report.md"

OUT_REPORT = ROOT / "reports" / "vps_final_decision_router_report.md"
OUT_JSON = ROOT / "reports" / "vps_final_decision_router.json"
OUT_NEXT = ROOT / "reports" / "next_prompt_instruction.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def is_pass_criteria(c: dict[str, Any]) -> bool:
    return (
        c.get("FINAL_LIVE_HEALTH_AUDIT") == "PASS"
        and c.get("CHAIN_INTEGRITY") == "PASS"
        and c.get("DATA_SPINE") == "PASS"
        and c.get("LINEAGE") == "PASS"
        and c.get("PAPER_OUTCOME") == "PASS"
        and c.get("EDGE_CLEAN") == "PASS"
        and c.get("DUPLICATE_LOOP") == "NONE"
        and c.get("TEMPLATE_RISK") == "LOW"
    )


def pick_next_prompt(criteria: dict[str, Any], blockers: list[str]) -> str:
    if is_pass_criteria(criteria):
        return "USER_SEND_OUTPUTS_FOR_HUMAN_REVIEW"
    if criteria.get("DUPLICATE_LOOP") != "NONE":
        return "VPS_RUNTIME_DUPLICATE_LOOP_REPAIR_PLAN"
    if criteria.get("DATA_SPINE") in ("FAIL", "PARTIAL", "KANITLANAMADI"):
        return "LOCAL_DATA_SPINE_REPAIR_PATCH_PLAN"
    if criteria.get("CHAIN_INTEGRITY") in ("FAIL", "PARTIAL", "KANITLANAMADI") or criteria.get("LINEAGE") in ("FAIL", "PARTIAL", "KANITLANAMADI"):
        return "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"
    if criteria.get("PAPER_OUTCOME") in ("FAIL", "PARTIAL", "KANITLANAMADI"):
        return "LOCAL_PAPER_LIFECYCLE_OUTCOME_REPAIR_PATCH_PLAN"
    if criteria.get("EDGE_CLEAN") in ("FAIL", "PARTIAL", "KANITLANAMADI"):
        return "LOCAL_EDGE_CLEANNESS_REPAIR_PATCH_PLAN"
    if criteria.get("TEMPLATE_RISK") != "LOW":
        return "LOCAL_DYNAMIC_OUTPUT_FORMULA_REPAIR_PATCH_PLAN"
    if any(x in blockers for x in ["ACTIVE_SCENARIO_NOT_READY", "CONDITIONAL_EDGE_NOT_READY"]):
        return "LOCAL_MARKET_STATE_ACTIVE_SCENARIO_REPAIR_PATCH_PLAN"
    return "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"


def main() -> None:
    audit = read_json(IN_AUDIT_JSON)
    criteria = {
        "FINAL_LIVE_HEALTH_AUDIT": audit.get("FINAL_LIVE_HEALTH_AUDIT", "KANITLANAMADI"),
        "CHAIN_INTEGRITY": audit.get("CHAIN_INTEGRITY", "KANITLANAMADI"),
        "DATA_SPINE": audit.get("DATA_SPINE", "KANITLANAMADI"),
        "LINEAGE": audit.get("LINEAGE", "KANITLANAMADI"),
        "PAPER_OUTCOME": audit.get("PAPER_OUTCOME", "KANITLANAMADI"),
        "EDGE_CLEAN": audit.get("EDGE_CLEAN", "KANITLANAMADI"),
        "DUPLICATE_LOOP": audit.get("DUPLICATE_LOOP", "KANITLANAMADI"),
        "TEMPLATE_RISK": audit.get("TEMPLATE_RISK", "KANITLANAMADI"),
    }
    blockers = audit.get("FINAL_BLOCKERS", [])
    if not isinstance(blockers, list):
        blockers = []
    blockers = [str(x) for x in blockers]
    next_required_action = str(audit.get("NEXT_REQUIRED_ACTION", "KANITLANAMADI"))

    has_partial = any(v == "PARTIAL" for v in criteria.values())
    has_fail = any(v == "FAIL" for v in criteria.values())
    has_unknown = any(v == "KANITLANAMADI" for v in criteria.values())
    duplicate_detected = criteria["DUPLICATE_LOOP"] == "DETECTED"
    template_not_low = criteria["TEMPLATE_RISK"] in ("MEDIUM", "HIGH", "KANITLANAMADI")

    final_candidate_ready = is_pass_criteria(criteria)
    next_prompt = pick_next_prompt(criteria, blockers)

    not_final_reason = []
    if not final_candidate_ready:
        not_final_reason.extend(blockers if blockers else ["FINAL_CRITERIA_NOT_MET"])
        if has_fail:
            not_final_reason.append("HAS_FAIL")
        if has_partial:
            not_final_reason.append("HAS_PARTIAL")
        if has_unknown:
            not_final_reason.append("HAS_KANITLANAMADI")
        if duplicate_detected:
            not_final_reason.append("DUPLICATE_LOOP_DETECTED")
        if template_not_low:
            not_final_reason.append("TEMPLATE_RISK_NOT_LOW")

    final_label = "FINAL_CANDIDATE_READY" if final_candidate_ready else "NOT_FINAL"
    required_user_action = "send_outputs" if final_candidate_ready else "continue_or_send_outputs"

    blocker_map = {
        "DATA_SPINE_NOT_PASS": ("DATA_SPINE", "HIGH", "LOCAL_DATA_SPINE_REPAIR_PATCH_PLAN"),
        "CHAIN_INTEGRITY_NOT_PASS": ("CHAIN_INTEGRITY", "HIGH", "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"),
        "LINEAGE_NOT_PASS": ("LINEAGE", "HIGH", "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"),
        "PAPER_OUTCOME_NOT_PASS": ("PAPER_OUTCOME", "HIGH", "LOCAL_PAPER_LIFECYCLE_OUTCOME_REPAIR_PATCH_PLAN"),
        "EDGE_CLEAN_NOT_PASS": ("EDGE_CLEAN", "HIGH", "LOCAL_EDGE_CLEANNESS_REPAIR_PATCH_PLAN"),
        "DUPLICATE_LOOP_NOT_NONE": ("DUPLICATE_LOOP", "HIGH", "VPS_RUNTIME_DUPLICATE_LOOP_REPAIR_PLAN"),
        "TEMPLATE_RISK_NOT_LOW": ("TEMPLATE_RISK", "HIGH", "LOCAL_DYNAMIC_OUTPUT_FORMULA_REPAIR_PATCH_PLAN"),
        "ACTIVE_SCENARIO_NOT_READY": ("MARKET_STATE_SCENARIO", "HIGH", "LOCAL_MARKET_STATE_ACTIVE_SCENARIO_REPAIR_PATCH_PLAN"),
        "CONDITIONAL_EDGE_NOT_READY": ("EDGE_CONDITIONAL", "HIGH", "LOCAL_EDGE_CLEANNESS_REPAIR_PATCH_PLAN"),
    }

    evidence_map = {
        "FINAL_LIVE_HEALTH_AUDIT": "reports/vps_final_live_health_audit_report.md",
        "CHAIN_INTEGRITY": "reports/vps_final_live_health_audit_report.md",
        "DATA_SPINE": "reports/vps_data_spine_reality_report.md",
        "LINEAGE": "reports/vps_lineage_outcome_audit_report.md",
        "PAPER_OUTCOME": "reports/vps_lineage_outcome_audit_report.md",
        "EDGE_CLEAN": "reports/vps_conditional_edge_audit_report.md",
        "DUPLICATE_LOOP": "reports/vps_final_live_health_audit_report.md",
        "TEMPLATE_RISK": "reports/vps_template_reality_audit_report.md",
    }

    router_json = {
        "final_candidate_ready": final_candidate_ready,
        "not_final_reason": not_final_reason,
        "next_prompt": next_prompt,
        "required_user_action": required_user_action,
        "criteria": criteria,
        "final_blockers": blockers,
        "next_required_action": next_required_action,
    }
    OUT_JSON.write_text(json.dumps(router_json, ensure_ascii=False, indent=2), encoding="utf-8")

    matrix_rows = []
    for k in [
        "FINAL_LIVE_HEALTH_AUDIT",
        "CHAIN_INTEGRITY",
        "DATA_SPINE",
        "LINEAGE",
        "PAPER_OUTCOME",
        "EDGE_CLEAN",
        "DUPLICATE_LOOP",
        "TEMPLATE_RISK",
    ]:
        v = criteria[k]
        p = "YES" if (
            (k in ["DUPLICATE_LOOP"] and v == "NONE")
            or (k == "TEMPLATE_RISK" and v == "LOW")
            or (k not in ["DUPLICATE_LOOP", "TEMPLATE_RISK"] and v == "PASS")
        ) else "NO"
        matrix_rows.append(f"{k} | {v} | {evidence_map[k]} | {p}")

    blocker_rows = []
    for b in blockers:
        cat, sev, np = blocker_map.get(b, ("UNKNOWN", "MEDIUM", next_prompt))
        blocker_rows.append(f"{b} | {cat} | {sev} | {np}")
    if not blocker_rows:
        blocker_rows = ["NONE | NONE | LOW | USER_SEND_OUTPUTS_FOR_HUMAN_REVIEW"]

    report = f"""# VPS FINAL DECISION ROUTER REPORT

## 1. Net Hüküm
{final_label}

## 2. Criteria Matrix
Criterion | Status | Evidence | Pass?
---|---|---|---
{chr(10).join(matrix_rows)}

## 3. Blocker Classification
Blocker | Category | Severity | Next Prompt
---|---|---|---
{chr(10).join(blocker_rows)}

## 4. Next Prompt Decision
Seçilen bir sonraki prompt:
{next_prompt}

## 5. Human Review Instruction
{"Nur artık final audit çıktılarını Nova’ya göndermeli." if final_candidate_ready else "Devam komutunda seçilen repair promptu verilmelidir."}
"""
    OUT_REPORT.write_text(report, encoding="utf-8")
    OUT_NEXT.write_text(next_prompt + "\n", encoding="utf-8")

    print(f"Wrote: {OUT_REPORT.relative_to(ROOT)}")
    print(f"Wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote: {OUT_NEXT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
