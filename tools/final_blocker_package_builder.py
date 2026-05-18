#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

IN_ROUTER_JSON = ROOT / "reports" / "vps_final_decision_router.json"
IN_ROUTER_REPORT = ROOT / "reports" / "vps_final_decision_router_report.md"
IN_NEXT_PROMPT = ROOT / "reports" / "next_prompt_instruction.md"
IN_FINAL_AUDIT_JSON = ROOT / "reports" / "vps_final_live_health_audit.json"
IN_FINAL_AUDIT_REPORT = ROOT / "reports" / "vps_final_live_health_audit_report.md"
IN_FINAL_DECISION = ROOT / "reports" / "vps_final_decision.md"

OUT_REPORT = ROOT / "reports" / "final_blocker_package_report.md"
OUT_JSON = ROOT / "reports" / "final_blocker_package.json"
OUT_REVIEW = ROOT / "reports" / "final_review_bundle.md"
OUT_NEXT_EXACT = ROOT / "reports" / "next_exact_prompt_type.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def meets_final(c: dict[str, Any]) -> bool:
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


def main() -> None:
    router = read_json(IN_ROUTER_JSON)
    audit = read_json(IN_FINAL_AUDIT_JSON)

    criteria = router.get("criteria", {})
    if not isinstance(criteria, dict) or not criteria:
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

    router_ready = bool(router.get("final_candidate_ready", False))
    audit_ready = meets_final(criteria)
    consistent = (router_ready == audit_ready)
    final_candidate_ready = router_ready and audit_ready and consistent

    next_prompt = str(router.get("next_prompt", "")).strip() or IN_NEXT_PROMPT.read_text(encoding="utf-8").strip()
    not_final_reason = router.get("not_final_reason", [])
    if not isinstance(not_final_reason, list):
        not_final_reason = []
    final_blockers = router.get("final_blockers", audit.get("FINAL_BLOCKERS", []))
    if not isinstance(final_blockers, list):
        final_blockers = []
    final_blockers = [str(x) for x in final_blockers]

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
    blocker_category = {
        "DATA_SPINE_NOT_PASS": ("DATA_SPINE", "LOCAL_DATA_SPINE_REPAIR_PATCH_PLAN"),
        "CHAIN_INTEGRITY_NOT_PASS": ("CHAIN_LINEAGE", "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"),
        "LINEAGE_NOT_PASS": ("CHAIN_LINEAGE", "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"),
        "PAPER_OUTCOME_NOT_PASS": ("PAPER_OUTCOME", "LOCAL_PAPER_LIFECYCLE_OUTCOME_REPAIR_PATCH_PLAN"),
        "EDGE_CLEAN_NOT_PASS": ("EDGE_CLEAN", "LOCAL_EDGE_CLEANNESS_REPAIR_PATCH_PLAN"),
        "DUPLICATE_LOOP_NOT_NONE": ("RUNTIME", "VPS_RUNTIME_DUPLICATE_LOOP_REPAIR_PLAN"),
        "TEMPLATE_RISK_NOT_LOW": ("TEMPLATE", "LOCAL_DYNAMIC_OUTPUT_FORMULA_REPAIR_PATCH_PLAN"),
        "ACTIVE_SCENARIO_NOT_READY": ("MARKET_SCENARIO", "LOCAL_MARKET_STATE_ACTIVE_SCENARIO_REPAIR_PATCH_PLAN"),
        "CONDITIONAL_EDGE_NOT_READY": ("EDGE_CLEAN", "LOCAL_EDGE_CLEANNESS_REPAIR_PATCH_PLAN"),
    }

    if not consistent:
        final_candidate_ready = False
        if "ROUTER_AUDIT_INCONSISTENT" not in final_blockers:
            final_blockers.append("ROUTER_AUDIT_INCONSISTENT")
        if "ROUTER_AUDIT_INCONSISTENT" not in not_final_reason:
            not_final_reason.append("ROUTER_AUDIT_INCONSISTENT")
        next_prompt = "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"

    final_label = "FINAL_CANDIDATE_READY" if final_candidate_ready else "NOT_FINAL"
    required_user_action = "send_outputs" if final_candidate_ready else "continue_or_send_outputs"

    # choose exact next prompt for NOT_FINAL
    if not final_candidate_ready:
        # Preserve router priority if valid
        allowed = {
            "LOCAL_DATA_SPINE_REPAIR_PATCH_PLAN",
            "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN",
            "LOCAL_PAPER_LIFECYCLE_OUTCOME_REPAIR_PATCH_PLAN",
            "LOCAL_EDGE_CLEANNESS_REPAIR_PATCH_PLAN",
            "VPS_RUNTIME_DUPLICATE_LOOP_REPAIR_PLAN",
            "LOCAL_DYNAMIC_OUTPUT_FORMULA_REPAIR_PATCH_PLAN",
            "LOCAL_MARKET_STATE_ACTIVE_SCENARIO_REPAIR_PATCH_PLAN",
        }
        if next_prompt not in allowed:
            next_prompt = "LOCAL_LINEAGE_CHAIN_REPAIR_PATCH_PLAN"
        OUT_NEXT_EXACT.write_text(next_prompt + "\n", encoding="utf-8")
    else:
        OUT_NEXT_EXACT.write_text("USER_SEND_OUTPUTS_FOR_HUMAN_REVIEW\n", encoding="utf-8")

    package_json = {
        "final_candidate_ready": final_candidate_ready,
        "not_final_reason": not_final_reason,
        "next_prompt": next_prompt if not final_candidate_ready else "USER_SEND_OUTPUTS_FOR_HUMAN_REVIEW",
        "required_user_action": required_user_action,
        "criteria": criteria,
        "router_audit_consistent": consistent,
        "final_blockers": final_blockers,
        "evidence_files": [
            str(IN_ROUTER_REPORT.relative_to(ROOT)),
            str(IN_ROUTER_JSON.relative_to(ROOT)),
            str(IN_FINAL_AUDIT_REPORT.relative_to(ROOT)),
            str(IN_FINAL_AUDIT_JSON.relative_to(ROOT)),
            str(IN_FINAL_DECISION.relative_to(ROOT)),
        ],
    }
    OUT_JSON.write_text(json.dumps(package_json, ensure_ascii=False, indent=2), encoding="utf-8")

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
        v = criteria.get(k, "KANITLANAMADI")
        pass_v = (
            (k not in ["DUPLICATE_LOOP", "TEMPLATE_RISK"] and v == "PASS")
            or (k == "DUPLICATE_LOOP" and v == "NONE")
            or (k == "TEMPLATE_RISK" and v == "LOW")
        )
        is_block = "YES" if not pass_v else "NO"
        matrix_rows.append(f"{k} | {v} | {evidence_map[k]} | {is_block}")

    blocker_rows = []
    for b in final_blockers:
        cat, prompt = blocker_category.get(b, ("UNKNOWN", next_prompt))
        blocker_rows.append(f"{b} | {cat} | {prompt} | HIGH")
    if not blocker_rows:
        blocker_rows = ["NONE | NONE | USER_SEND_OUTPUTS_FOR_HUMAN_REVIEW | LOW"]

    report = f"""# FINAL BLOCKER PACKAGE REPORT

## 1. Net Hüküm
{final_label}

## 2. Evidence Matrix
Criterion | Status | Evidence | Final Blocker?
---|---|---|---
{chr(10).join(matrix_rows)}

## 3. Blocker Package
Blocker | Category | Required Repair Prompt | Severity
---|---|---|---
{chr(10).join(blocker_rows)}

## 4. Next Exact Prompt Type
{("USER_SEND_OUTPUTS_FOR_HUMAN_REVIEW" if final_candidate_ready else next_prompt)}

## 5. User Instruction
{"Nur final audit çıktılarını Nova’ya göndermeli." if final_candidate_ready else "Devam komutunda next_exact_prompt_type içindeki repair promptu uygulanmalı."}
"""
    OUT_REPORT.write_text(report, encoding="utf-8")

    if final_candidate_ready:
        review = f"""# FINAL REVIEW BUNDLE

## Final criteria matrix
{chr(10).join(matrix_rows)}

## Runtime status
Kaynak: reports/vps_final_live_health_audit_report.md

## Data spine status
{criteria.get("DATA_SPINE", "KANITLANAMADI")}

## Lineage status
{criteria.get("LINEAGE", "KANITLANAMADI")}

## Paper outcome status
{criteria.get("PAPER_OUTCOME", "KANITLANAMADI")}

## Edge clean status
{criteria.get("EDGE_CLEAN", "KANITLANAMADI")}

## Template risk status
{criteria.get("TEMPLATE_RISK", "KANITLANAMADI")}

## Duplicate loop status
{criteria.get("DUPLICATE_LOOP", "KANITLANAMADI")}

## Human review için dosyalar
- reports/vps_final_live_health_audit_report.md
- reports/vps_final_live_health_audit.json
- reports/vps_final_decision.md
- reports/vps_final_decision_router_report.md
- reports/vps_final_decision_router.json
"""
    else:
        review = "# FINAL REVIEW BUNDLE\n\nNOT_FINAL\n"
    OUT_REVIEW.write_text(review, encoding="utf-8")

    print(f"Wrote: {OUT_REPORT.relative_to(ROOT)}")
    print(f"Wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote: {OUT_REVIEW.relative_to(ROOT)}")
    print(f"Wrote: {OUT_NEXT_EXACT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
