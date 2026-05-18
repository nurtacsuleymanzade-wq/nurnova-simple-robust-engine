from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"

JSON_OUT = REPORTS_DIR / "local_market_state_scenario_audit.json"
MD_OUT = REPORTS_DIR / "local_market_state_scenario_audit_report.md"
P10_OUT = REPORTS_DIR / "local_prompt_10_recommendation.md"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def read_json(rel: str) -> dict[str, Any] | None:
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except Exception:
        return None


def line_of(rel: str, token: str) -> int | None:
    txt = read_text(rel)
    if not txt:
        return None
    for i, line in enumerate(txt.splitlines(), start=1):
        if token in line:
            return i
    return None


def has_token(rel: str, token: str) -> bool:
    return line_of(rel, token) is not None


def file_exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def state_keys(rel: str) -> list[str]:
    payload = read_json(rel)
    return list(payload.keys()) if isinstance(payload, dict) else []


def ev(items: list[str]) -> str:
    clean = [x for x in items if x]
    return "; ".join(clean) if clean else "KANITLANAMADI"


def level(exact: bool, alias: bool) -> tuple[bool, str]:
    if exact:
        return True, "EXACT"
    if alias:
        return True, "PARTIAL"
    return False, "MISSING"


def scan_market_fields() -> list[dict[str, Any]]:
    checks = [
        {
            "field": "trend",
            "producer": "src/simple/market_structure_engine.py::run_market_structure_engine",
            "inputs": "state/simple/latest_market_truth.json",
            "exact_tokens": ['"trend":'],
            "alias_tokens": ['"trend_state":', '"trend_1m":', '"trend_5m":'],
            "evidence_rel": "src/simple/market_structure_engine.py",
            "test_file": "tests/simple/test_market_structure_engine.py",
        },
        {
            "field": "regime",
            "producer": "src/simple/market_regime_classifier.py::run_market_regime_classifier",
            "inputs": "latest_market_structure + latest_business_zone + latest_interpretation",
            "exact_tokens": ['"regime": regime'],
            "alias_tokens": ['"primary_regime":'],
            "evidence_rel": "src/simple/market_regime_classifier.py",
            "test_file": "tests/simple/test_regime_classifier_engine.py",
        },
        {
            "field": "volatility_state",
            "producer": "src/simple/regime_classifier_engine.py::build_regime_classifier",
            "inputs": "state/simple/latest_1s_evidence.json + latest_quality_weight.json",
            "exact_tokens": ['"volatility_state": vol_state'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/regime_classifier_engine.py",
            "test_file": "tests/simple/test_regime_classifier_engine.py",
        },
        {
            "field": "alignment",
            "producer": "src/simple/market_structure_v2.py::run_market_structure_v2",
            "inputs": "flow_evidence + flow_persistence + depth_liquidity_memory",
            "exact_tokens": ['"alignment":'],
            "alias_tokens": ['"flow_alignment":', '"liquidity_alignment":'],
            "evidence_rel": "src/simple/market_structure_v2.py",
            "test_file": "KANITLANAMADI",
        },
        {
            "field": "liquidity_state",
            "producer": "src/simple/liquidity_map_engine.py::run_liquidity_map_engine",
            "inputs": "latest_observation_factory + latest_market_structure + latest_depth_liquidity_memory",
            "exact_tokens": ['"liquidity_state":'],
            "alias_tokens": ['"liquidity_context":', '"liquidity_memory_status":', '"liquidity_bias":'],
            "evidence_rel": "src/simple/liquidity_map_engine.py",
            "test_file": "tests/simple/test_depth_liquidity_memory.py",
        },
        {
            "field": "auction_state",
            "producer": "src/simple/business_zone_engine.py::run_business_zone_engine",
            "inputs": "latest_mtf_candle_dna + latest_market_structure + latest_liquidity_map",
            "exact_tokens": ['"auction_state":'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/business_zone_engine.py",
            "test_file": "KANITLANAMADI",
        },
        {
            "field": "state_confidence",
            "producer": "src/simple/regime_classifier_engine.py::build_regime_classifier",
            "inputs": "latest_market_structure_v2 + latest_1s_evidence",
            "exact_tokens": ['"state_confidence":'],
            "alias_tokens": ['"confidence": round(_clamp(confidence), 3)'],
            "evidence_rel": "src/simple/regime_classifier_engine.py",
            "test_file": "tests/simple/test_regime_classifier_engine.py",
        },
        {
            "field": "reason_codes",
            "producer": "multiple market state engines",
            "inputs": "market state inputs",
            "exact_tokens": ['"reason_codes":'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/market_regime_classifier.py",
            "test_file": "tests/simple/test_regime_classifier_engine.py",
        },
        {
            "field": "data_quality",
            "producer": "multiple market state engines",
            "inputs": "market state inputs",
            "exact_tokens": ['"data_quality":'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/market_regime_classifier.py",
            "test_file": "tests/simple/test_regime_classifier_engine.py",
        },
        {
            "field": "feeds_next",
            "producer": "multiple market state engines",
            "inputs": "market state inputs",
            "exact_tokens": ['"feeds_next":'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/market_regime_classifier.py",
            "test_file": "tests/simple/test_scenario_entry_trigger_engine.py",
        },
    ]

    rows: list[dict[str, Any]] = []
    for item in checks:
        rel = item["evidence_rel"]
        exact_line = next((line_of(rel, t) for t in item["exact_tokens"] if line_of(rel, t) is not None), None)
        alias_line = next((line_of(rel, t) for t in item["alias_tokens"] if line_of(rel, t) is not None), None)
        found, status = level(exact_line is not None, alias_line is not None)
        evidence = ev(
            [
                f"{rel}:{exact_line}" if exact_line else "",
                f"{rel}:{alias_line}" if (alias_line and not exact_line) else "",
                item["test_file"] if file_exists(item["test_file"]) else ("KANITLANAMADI" if item["test_file"] == "KANITLANAMADI" else ""),
            ]
        )
        rows.append(
            {
                "field": item["field"],
                "found": found,
                "producer": item["producer"],
                "input_dependency": item["inputs"],
                "evidence": evidence,
                "status": status,
            }
        )
    return rows


def scan_scenario_fields() -> list[dict[str, Any]]:
    checks = [
        {
            "field": "possible_scenarios",
            "producer": "src/simple/scenario_entry_trigger_engine.py::compute_scenario_trigger",
            "inputs": "latest_setup_context + latest_flow_evidence + latest_flow_persistence",
            "exact_tokens": ['"possible_scenarios": possible_scenarios'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/scenario_entry_trigger_engine.py",
            "test_file": "tests/simple/test_layer_separation_patch_a.py",
        },
        {
            "field": "active_scenario",
            "producer": "src/simple/scenario_entry_trigger_engine.py::compute_scenario_trigger",
            "inputs": "possible_scenarios list",
            "exact_tokens": ['"active_scenario": active_scenario'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/scenario_entry_trigger_engine.py",
            "test_file": "tests/simple/test_layer_separation_patch_a.py",
        },
        {
            "field": "scenario_confidence",
            "producer": "src/simple/scenario_entry_trigger_engine.py::compute_scenario_trigger",
            "inputs": "setup confidence + trigger_strength",
            "exact_tokens": ['"scenario_confidence":'],
            "alias_tokens": ['"trigger_confidence": trigger_confidence'],
            "evidence_rel": "src/simple/scenario_entry_trigger_engine.py",
            "test_file": "tests/simple/test_scenario_entry_trigger_engine.py",
        },
        {
            "field": "selection_reason_codes",
            "producer": "src/simple/scenario_entry_trigger_engine.py::compute_scenario_trigger",
            "inputs": "scenario + regime + risks",
            "exact_tokens": ['"selection_reason_codes":'],
            "alias_tokens": ['"reason_codes": reason_codes'],
            "evidence_rel": "src/simple/scenario_entry_trigger_engine.py",
            "test_file": "tests/simple/test_scenario_entry_trigger_engine.py",
        },
        {
            "field": "market_state_id",
            "producer": "KANITLANAMADI",
            "inputs": "KANITLANAMADI",
            "exact_tokens": ['"market_state_id":'],
            "alias_tokens": [],
            "evidence_rel": "src/simple/scenario_entry_trigger_engine.py",
            "test_file": "KANITLANAMADI",
        },
        {
            "field": "feeds_next",
            "producer": "src/simple/scenario_entry_trigger_engine.py::compute_scenario_trigger",
            "inputs": "scenario payload",
            "exact_tokens": ['"feeds_next": {"next_blocks": ["SIGNAL_EVENT_CONSOLIDATOR"]}'],
            "alias_tokens": ['"feeds_next":'],
            "evidence_rel": "src/simple/scenario_entry_trigger_engine.py",
            "test_file": "tests/simple/test_scenario_entry_trigger_engine.py",
        },
    ]
    rows: list[dict[str, Any]] = []
    for item in checks:
        rel = item["evidence_rel"]
        exact_line = next((line_of(rel, t) for t in item["exact_tokens"] if line_of(rel, t) is not None), None)
        alias_line = next((line_of(rel, t) for t in item["alias_tokens"] if line_of(rel, t) is not None), None)
        found, status = level(exact_line is not None, alias_line is not None)
        evidence = ev(
            [
                f"{rel}:{exact_line}" if exact_line else "",
                f"{rel}:{alias_line}" if (alias_line and not exact_line) else "",
                item["test_file"] if file_exists(item["test_file"]) else ("KANITLANAMADI" if item["test_file"] == "KANITLANAMADI" else ""),
            ]
        )
        rows.append(
            {
                "field": item["field"],
                "found": found,
                "producer": item["producer"],
                "input_dependency": item["inputs"],
                "evidence": evidence,
                "status": status,
            }
        )
    return rows


def scan_checks() -> dict[str, Any]:
    market_txt = read_text("src/simple/market_regime_classifier.py")
    regime_txt = read_text("src/simple/regime_classifier_engine.py")
    scenario_txt = read_text("src/simple/scenario_entry_trigger_engine.py")
    setup_classifier_txt = read_text("src/simple/setup_classifier_v2.py")
    local_runner_txt = read_text("src/simple/local_pipeline_runner.py")

    latest_scenario_keys = state_keys("state/simple/latest_scenario_trigger.json")
    latest_market_keys = state_keys("state/simple/latest_market_regime.json")

    market_state_engine_found = file_exists("src/simple/market_regime_classifier.py") or file_exists("src/simple/regime_classifier_engine.py")
    trend_field_found = ("trend" in latest_market_keys) or has_token("src/simple/market_regime_classifier.py", '"trend":') or has_token("src/simple/market_structure_engine.py", '"trend_state":')
    regime_field_found = ("regime" in latest_market_keys) or ('"regime": regime' in market_txt)
    volatility_state_found = ("volatility_state" in state_keys("state/simple/latest_regime_classifier.json")) or ('"volatility_state": vol_state' in regime_txt)
    alignment_found = has_token("src/simple/market_structure_v2.py", '"flow_alignment":') or has_token("src/simple/market_structure_v2.py", '"liquidity_alignment":')
    liquidity_state_found = has_token("src/simple/liquidity_map_engine.py", '"liquidity_state":') or has_token("src/simple/liquidity_map_engine.py", '"liquidity_context":')
    auction_state_found = has_token("src/simple/business_zone_engine.py", '"auction_state":')
    state_confidence_found = has_token("src/simple/market_regime_classifier.py", '"state_confidence":') or has_token("src/simple/regime_classifier_engine.py", '"confidence": round(_clamp(confidence), 3)')

    scenario_engine_found = file_exists("src/simple/scenario_entry_trigger_engine.py")
    possible_scenarios_found = ("possible_scenarios" in latest_scenario_keys) or has_token("src/simple/scenario_entry_trigger_engine.py", '"possible_scenarios": possible_scenarios')
    active_scenario_found = ("active_scenario" in latest_scenario_keys) or has_token("src/simple/scenario_entry_trigger_engine.py", '"active_scenario": active_scenario')
    scenario_confidence_found = ("scenario_confidence" in latest_scenario_keys) or has_token("src/simple/scenario_entry_trigger_engine.py", '"trigger_confidence": trigger_confidence')
    selection_reason_codes_found = ("selection_reason_codes" in latest_scenario_keys) or has_token("src/simple/scenario_entry_trigger_engine.py", '"reason_codes": reason_codes')

    market_state_feeds_scenario = (
        has_token("src/simple/scenario_entry_trigger_engine.py", "latest_market_regime.json")
        or has_token("src/simple/three_scenario_engine.py", "latest_market_regime.json")
        or has_token("src/simple/scenario_entry_trigger_engine.py", "MARKET_REGIME_PATH")
    )
    scenario_feeds_setup = (
        has_token("src/simple/setup_classifier_v2.py", 'STATE_DIR / "latest_scenario_trigger.json"')
        or has_token("src/simple/setup_family_activation_engine.py", "latest_three_scenarios")
    )

    branch_only_scenario_risk = (
        has_token("src/simple/scenario_entry_trigger_engine.py", "trigger_state = \"SCENARIO_ONLY\"")
        and (not market_state_feeds_scenario)
    )
    no_active_scenario_risk = ("active_scenario" not in latest_scenario_keys)

    return {
        "market_state_engine_found": market_state_engine_found,
        "trend_field_found": trend_field_found,
        "regime_field_found": regime_field_found,
        "volatility_state_found": volatility_state_found,
        "alignment_found": alignment_found,
        "liquidity_state_found": liquidity_state_found,
        "auction_state_found": auction_state_found,
        "state_confidence_found": state_confidence_found,
        "scenario_engine_found": scenario_engine_found,
        "possible_scenarios_found": possible_scenarios_found,
        "active_scenario_found": active_scenario_found,
        "scenario_confidence_found": scenario_confidence_found,
        "selection_reason_codes_found": selection_reason_codes_found,
        "market_state_feeds_scenario": market_state_feeds_scenario,
        "scenario_feeds_setup": scenario_feeds_setup,
        "branch_only_scenario_risk": branch_only_scenario_risk,
        "no_active_scenario_risk": no_active_scenario_risk,
        "pipeline_stage_market_state": ("MARKET_REGIME_CLASSIFIER" in local_runner_txt or "REGIME_CLASSIFIER" in local_runner_txt),
        "pipeline_stage_scenario": ("SCENARIO_ENTRY_TRIGGER" in local_runner_txt or "THREE_SCENARIO_ENGINE" in local_runner_txt),
    }


def market_status(market_rows: list[dict[str, Any]]) -> str:
    critical = {"trend", "regime", "volatility_state", "alignment", "liquidity_state", "auction_state", "state_confidence"}
    exact_count = sum(1 for row in market_rows if row["field"] in critical and row["status"] == "EXACT")
    found_count = sum(1 for row in market_rows if row["field"] in critical and row["found"])
    if exact_count >= 5:
        return "PASS"
    if found_count >= 3:
        return "PARTIAL"
    return "FAIL"


def scenario_status(s_rows: list[dict[str, Any]]) -> str:
    critical = {"possible_scenarios", "active_scenario", "scenario_confidence", "selection_reason_codes", "market_state_id"}
    exact_count = sum(1 for row in s_rows if row["field"] in critical and row["status"] == "EXACT")
    found_count = sum(1 for row in s_rows if row["field"] in critical and row["found"])
    if exact_count >= 4:
        return "PASS"
    if found_count >= 2:
        return "PARTIAL"
    return "FAIL"


def context_status(checks: dict[str, Any], m_status: str, s_status: str) -> str:
    ok_links = checks["market_state_feeds_scenario"] and checks["scenario_feeds_setup"]
    if m_status == "PASS" and s_status == "PASS" and ok_links:
        return "PASS"
    if s_status in {"PASS", "PARTIAL"} and checks["scenario_feeds_setup"]:
        return "PARTIAL"
    return "FAIL"


def build_links(checks: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ms_sc_ok = checks["market_state_feeds_scenario"]
    sc_setup_ok = checks["scenario_feeds_setup"]
    link_ms = {
        "link": "MARKET_STATE -> SCENARIO",
        "status": "PASS" if ms_sc_ok else "FAIL",
        "evidence": ev(
            [
                (
                    "src/simple/scenario_entry_trigger_engine.py:uses_market_state_input"
                    if ms_sc_ok
                    else f"src/simple/scenario_entry_trigger_engine.py:{line_of('src/simple/scenario_entry_trigger_engine.py', 'def _market_regime(')}"
                ),
                f"src/simple/local_pipeline_runner.py:{line_of('src/simple/local_pipeline_runner.py', 'MARKET_REGIME_CLASSIFIER')}",
            ]
        ),
        "risk": "-" if ms_sc_ok else "MARKET_STATE_NOT_FEEDING_SCENARIO",
    }
    link_sc = {
        "link": "SCENARIO -> SETUP",
        "status": "PASS" if sc_setup_ok else "FAIL",
        "evidence": ev(
            [
                f"src/simple/setup_classifier_v2.py:{line_of('src/simple/setup_classifier_v2.py', '\"scenario_trigger\": STATE_DIR / \"latest_scenario_trigger.json\"')}" if sc_setup_ok else "",
                f"src/simple/setup_classifier_v2.py:{line_of('src/simple/setup_classifier_v2.py', 'scenario_component, scenario_side, scenario_family = _assess_scenario(')}",
                f"src/simple/setup_candidate_engine.py:{line_of('src/simple/setup_candidate_engine.py', 'def _calc_scenario(')}",
            ]
        ),
        "risk": "-" if sc_setup_ok else "SCENARIO_NOT_FEEDING_SETUP",
    }
    return link_ms, link_sc


def missing_fields(market_rows: list[dict[str, Any]], scenario_rows: list[dict[str, Any]], checks: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    risk_map = {
        "trend": "TREND_MISSING",
        "regime": "REGIME_MISSING",
        "volatility_state": "VOLATILITY_STATE_MISSING",
        "alignment": "ALIGNMENT_MISSING",
        "liquidity_state": "LIQUIDITY_STATE_MISSING",
        "auction_state": "AUCTION_STATE_MISSING",
        "state_confidence": "STATE_CONFIDENCE_MISSING",
        "possible_scenarios": "POSSIBLE_SCENARIOS_MISSING",
        "active_scenario": "ACTIVE_SCENARIO_MISSING",
        "scenario_confidence": "SCENARIO_CONFIDENCE_MISSING",
        "selection_reason_codes": "SELECTION_REASON_CODES_MISSING",
        "market_state_id": "CONTEXT_UNAWARE_EDGE_RISK",
    }
    why_map = {
        "trend": "Pattern yorumu yön bağlamı olmadan zayıflar.",
        "regime": "Setup aileleri bağlama göre değişir.",
        "volatility_state": "Risk ve trigger eşiği rejime göre değişir.",
        "alignment": "Flow/structure uyumu olmadan confidence yanıltıcı olabilir.",
        "liquidity_state": "Likidite yönü setup geçerliliğini etkiler.",
        "auction_state": "Auction kabul/red bilgisi senaryo seçimini etkiler.",
        "state_confidence": "Bağlam güveni olmadan scenario weighting zayıflar.",
        "possible_scenarios": "Çoklu yol hipotezi olmadan active seçim tek dala sıkışır.",
        "active_scenario": "Downstream signal katmanı scenario-id taşıyamaz.",
        "scenario_confidence": "Seçim güveni olmadan setup grading şeffaflığı düşer.",
        "selection_reason_codes": "Scenario selection açıklanamaz hale gelir.",
        "market_state_id": "Scenario-market_state lineage kurulamaz.",
    }
    for row in [*market_rows, *scenario_rows]:
        if row["status"] == "EXACT":
            continue
        field = row["field"]
        if field not in risk_map:
            continue
        rows.append(
            {
                "field": field,
                "risk_code": risk_map[field],
                "why_critical": why_map[field],
                "evidence": row["evidence"],
                "required_fix": "Canonical contract alanı ve field bridge netleştirilmeli.",
            }
        )
    if checks["branch_only_scenario_risk"]:
        rows.append(
            {
                "field": "branch_only_scenario_risk",
                "risk_code": "BRANCH_ONLY_SCENARIO_RISK",
                "why_critical": "Scenario doğrudan branch label’dan türetilirse context-aware seçim bozulur.",
                "evidence": ev(
                    [
                        f"src/simple/scenario_entry_trigger_engine.py:{line_of('src/simple/scenario_entry_trigger_engine.py', 'trigger_state = \"SCENARIO_ONLY\"')}",
                        f"src/simple/scenario_entry_trigger_engine.py:{line_of('src/simple/scenario_entry_trigger_engine.py', 'def _market_regime(')}",
                    ]
                ),
                "required_fix": "Market state input bağı netleştirilmeli ve selection contract ayrıştırılmalı.",
            }
        )
    if checks["no_active_scenario_risk"]:
        rows.append(
            {
                "field": "no_active_scenario_risk",
                "risk_code": "ACTIVE_SCENARIO_MISSING",
                "why_critical": "State dosyasında active_scenario yoksa downstream lineage kopar.",
                "evidence": "state/simple/latest_scenario_trigger.json keys: active_scenario KANITLANAMADI",
                "required_fix": "latest_scenario_trigger canonical producer/schema drift denetlenmeli.",
            }
        )
    return rows


def recommendation(m_status: str, s_status: str) -> str:
    if m_status == "PASS" and s_status == "PASS":
        return "Prompt 10 = VPS MARKET STATE + ACTIVE SCENARIO REALITY AUDIT"
    if m_status == "FAIL" or s_status == "FAIL":
        return "Prompt 10 = LOCAL MARKET STATE + ACTIVE SCENARIO PATCH PLAN"
    return "Prompt 10 = LOCAL MARKET STATE + ACTIVE SCENARIO HARDENING PLAN"


def build_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# LOCAL MARKET STATE + ACTIVE SCENARIO AUDIT REPORT")
    lines.append("")
    lines.append("## 1. Net Hüküm")
    lines.append(f"Market State: {payload['summary']['market_state_status']}")
    lines.append("")
    lines.append(f"Active Scenario: {payload['summary']['active_scenario_status']}")
    lines.append("")
    lines.append(f"Context-Aware Readiness: {payload['summary']['context_aware_readiness']}")
    lines.append("")
    lines.append("## 2. Market State Inventory")
    lines.append("Field | Found? | Producer | Input Dependency | Evidence | Status")
    for row in payload["market_state_inventory"]:
        lines.append(
            f"{row['field']} | {row['found']} | {row['producer']} | {row['input_dependency']} | {row['evidence']} | {row['status']}"
        )
    lines.append("")
    lines.append("## 3. Scenario Inventory")
    lines.append("Field | Found? | Producer | Input Dependency | Evidence | Status")
    for row in payload["scenario_inventory"]:
        lines.append(
            f"{row['field']} | {row['found']} | {row['producer']} | {row['input_dependency']} | {row['evidence']} | {row['status']}"
        )
    lines.append("")
    lines.append("## 4. Market State → Scenario Link")
    lines.append("Link | Status | Evidence | Risk")
    ms = payload["market_state_to_scenario_link"]
    lines.append(f"{ms['link']} | {ms['status']} | {ms['evidence']} | {ms['risk']}")
    lines.append("")
    lines.append("## 5. Scenario → Setup Link")
    lines.append("Link | Status | Evidence | Risk")
    ss = payload["scenario_to_setup_link"]
    lines.append(f"{ss['link']} | {ss['status']} | {ss['evidence']} | {ss['risk']}")
    lines.append("")
    lines.append("## 6. Critical Missing Context Fields")
    lines.append("Field | Why Critical | Evidence | Required Fix")
    if payload["critical_missing_context_fields"]:
        for row in payload["critical_missing_context_fields"]:
            lines.append(f"{row['field']} | {row['why_critical']} | {row['evidence']} | {row['required_fix']}")
    else:
        lines.append("NONE | KANITLANAMADI | KANITLANAMADI | KANITLANAMADI")
    lines.append("")
    lines.append("## 7. Prompt 10 Recommendation")
    lines.append(payload["prompt_10_recommendation"])
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    market_rows = scan_market_fields()
    scenario_rows = scan_scenario_fields()
    checks = scan_checks()
    link_ms, link_ss = build_links(checks)
    m_status = market_status(market_rows)
    s_status = scenario_status(scenario_rows)
    c_status = context_status(checks, m_status, s_status)
    missing = missing_fields(market_rows, scenario_rows, checks)
    rec = recommendation(m_status, s_status)

    risk_codes = sorted({row["risk_code"] for row in missing if row.get("risk_code")})

    payload = {
        "generated_at_utc": now_utc(),
        "summary": {
            "market_state_status": m_status,
            "active_scenario_status": s_status,
            "context_aware_readiness": c_status,
        },
        "audit_checks": checks,
        "market_state_inventory": market_rows,
        "scenario_inventory": scenario_rows,
        "market_state_to_scenario_link": link_ms,
        "scenario_to_setup_link": link_ss,
        "critical_missing_context_fields": missing,
        "risk_codes_detected": risk_codes,
        "state_key_inventory": {
            "latest_market_regime_keys": state_keys("state/simple/latest_market_regime.json"),
            "latest_regime_classifier_keys": state_keys("state/simple/latest_regime_classifier.json"),
            "latest_scenario_trigger_keys": state_keys("state/simple/latest_scenario_trigger.json"),
            "latest_three_scenarios_keys": state_keys("state/simple/latest_three_scenarios.json"),
        },
        "prompt_10_recommendation": rec,
    }
    return payload


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = run()
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(build_markdown(payload), encoding="utf-8")
    P10_OUT.write_text(payload["prompt_10_recommendation"] + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(JSON_OUT),
                "report": str(MD_OUT),
                "recommendation": str(P10_OUT),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
