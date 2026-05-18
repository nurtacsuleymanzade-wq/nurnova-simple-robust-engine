from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "simple"
REPORTS = ROOT / "reports"

JSON_OUT = REPORTS / "local_template_dynamic_audit.json"
MD_OUT = REPORTS / "local_template_dynamic_audit_report.md"
P6_OUT = REPORTS / "local_prompt_6_recommendation.md"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


@dataclass
class FieldSpec:
    name: str
    producers: list[str]
    hints: list[str]


FIELD_SPECS: list[FieldSpec] = [
    FieldSpec("score", ["setup_candidate_engine.py", "scenario_entry_trigger_engine.py", "trade_plan_engine.py", "decision_gate_engine.py"], ["score", "setup_context_score", "scenario_score", "decision_score", "plan_quality_score"]),
    FieldSpec("confidence", ["flow_evidence_engine.py", "flow_to_setup_context_engine.py", "scenario_entry_trigger_engine.py", "trade_plan_engine.py"], ["confidence", "trigger_confidence"]),
    FieldSpec("RR", ["trade_plan_engine.py", "decision_gate_engine.py", "paper_outcome_tracker.py"], ["rr_tp1", "rr_tp2", "rr1", "rr2"]),
    FieldSpec("entry", ["trade_plan_engine.py", "decision_gate_engine.py", "telegram_paper_alert_engine.py"], ["entry_price", "selected_entry"]),
    FieldSpec("stop_loss", ["trade_plan_engine.py", "decision_gate_engine.py", "telegram_paper_alert_engine.py"], ["stop_loss", "selected_stop_loss"]),
    FieldSpec("tp", ["trade_plan_engine.py", "decision_gate_engine.py", "telegram_paper_alert_engine.py"], ["tp1", "tp2", "selected_tp1", "selected_tp2"]),
    FieldSpec("reason_chain", ["scenario_entry_trigger_engine.py", "trade_plan_engine.py", "decision_gate_engine.py", "telegram_paper_alert_engine.py"], ["reason_codes", "block_reasons", "warning_reasons", "reason_summary"]),
    FieldSpec("scenario", ["scenario_entry_trigger_engine.py", "three_scenario_engine.py", "setup_candidate_engine.py"], ["scenario_label", "scenario_type"]),
    FieldSpec("active_scenario", ["scenario_entry_trigger_engine.py"], ["active_scenario", "possible_scenarios"]),
    FieldSpec("trade_plan_status", ["trade_plan_engine.py", "trade_plan_decision_engine.py"], ["plan_status"]),
    FieldSpec("grade", ["trade_plan_engine.py", "decision_gate_engine.py", "signal_grade_engine.py", "telegram_paper_alert_engine.py"], ["plan_grade", "final_grade", "signal_grade"]),
    FieldSpec("telegram_message_fields", ["telegram_paper_alert_engine.py", "telegram_research_reporter.py"], ["_format_message", "message_text"]),
]


AUDIT_CHECKS = [
    "score_static_literal_detected",
    "confidence_static_literal_detected",
    "rr_static_literal_detected",
    "entry_formula_detected",
    "sl_formula_detected",
    "tp_formula_detected",
    "reason_chain_repeated_literal_detected",
    "scenario_static_detected",
    "active_scenario_missing_or_static",
    "grade_static_detected",
    "telegram_template_only_detected",
    "fallback_branch_detected",
    "default_value_overuse_detected",
    "live_input_dependency_detected",
    "market_state_dependency_detected",
    "liquidity_dependency_detected",
    "structure_dependency_detected",
    "candle_dna_dependency_detected",
    "data_quality_dependency_detected",
]


RISK_CODES = [
    "SCORE_TEMPLATE_RISK",
    "CONFIDENCE_TEMPLATE_RISK",
    "RR_TEMPLATE_RISK",
    "ENTRY_TEMPLATE_RISK",
    "SL_TEMPLATE_RISK",
    "TP_TEMPLATE_RISK",
    "REASON_CHAIN_TEMPLATE_RISK",
    "SCENARIO_TEMPLATE_RISK",
    "ACTIVE_SCENARIO_MISSING",
    "GRADE_TEMPLATE_RISK",
    "TELEGRAM_TEMPLATE_ONLY",
    "FALLBACK_OVERUSED",
    "DEFAULT_VALUE_OVERUSED",
    "LIVE_INPUT_NOT_USED",
    "MARKET_STATE_NOT_USED",
    "LIQUIDITY_NOT_USED",
    "STRUCTURE_NOT_USED",
    "DNA_NOT_USED",
]


_STATIC_VALUE_RE = re.compile(r":\s*(?:-?\d+(?:\.\d+)?|None|\"[^\"]*\"|'[^']*')\s*(?:,|$)")
_DICT_KEY_RE = re.compile(r"([\"'])(?P<key>[A-Za-z0-9_]+)\\1\\s*:")


def _extract_line_evidence(text: str, token: str, max_hits: int = 3) -> list[str]:
    out: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if token in line:
            out.append(f"L{i}: {line.strip()}")
            if len(out) >= max_hits:
                break
    return out


def _classify_value_line(line: str) -> dict[str, Any]:
    # Heuristic classification for mapping lines like '"rr_tp1": rr_tp1,' or '"rr_tp1": 0.0,'
    static_literal = bool(_STATIC_VALUE_RE.search(line))
    uses_get = ".get(" in line
    has_math = any(op in line for op in ("+", "-", "*", "/", "abs(", "min(", "max(", "round("))
    return {
        "static_literal": static_literal,
        "formula": has_math and not static_literal,
        "copies_from_state": uses_get,
    }


def _detect_fallback_branches(text: str) -> list[str]:
    markers = ["FAKE_SAMPLE", "_FAKE_", "NO_DATA", "no_valid_output", "fallback", "preview_plan", "INPUT_MISSING"]
    found = [m for m in markers if m in text]
    return found[:8]


def _detect_dependencies(text: str) -> dict[str, bool]:
    deps = {
        "live_input_dependency_detected": any(tok in text for tok in ["latest_flow_state", "live_flow_events.jsonl", "SOURCE_LIVE_WS_REAL", "FLOW_STATE_LIVE"]),
        "market_state_dependency_detected": any(tok in text for tok in ["market_regime", "regime", "latest_market_regime", "MARKET_REGIME"]),
        "liquidity_dependency_detected": any(tok in text for tok in ["liquidity", "depth_liquidity_memory", "latest_depth", "bid_wall", "ask_wall"]),
        "structure_dependency_detected": any(tok in text for tok in ["market_structure", "structure_label", "BOS", "CHOCH"]),
        "candle_dna_dependency_detected": any(tok in text for tok in ["candle_dna", "latest_hybrid_candle_dna", "dna_", "candle_category"]),
        "data_quality_dependency_detected": "data_quality" in text or "dq_" in text,
    }
    return deps


def _producer_path(rel: str) -> Path:
    return SRC / rel


def audit() -> dict[str, Any]:
    producers_set = sorted({p for spec in FIELD_SPECS for p in spec.producers})
    producer_text: dict[str, str] = {p: read_text(_producer_path(p)) for p in producers_set}

    field_map: list[dict[str, Any]] = []
    static_findings: list[dict[str, Any]] = []
    dynamic_findings: list[dict[str, Any]] = []
    telegram_findings: list[dict[str, Any]] = []

    # Global dependency footprint (what the set of producer files mentions)
    deps_rollup = {k: False for k in _detect_dependencies("x").keys()}
    for p, t in producer_text.items():
        deps = _detect_dependencies(t)
        for k, v in deps.items():
            deps_rollup[k] = deps_rollup[k] or v

    # Field-by-field evidence
    for spec in FIELD_SPECS:
        for producer in spec.producers:
            text = producer_text.get(producer, "")
            if not text:
                field_map.append({
                    "field": spec.name,
                    "producer_file": f"src/simple/{producer}",
                    "function": "KANITLANAMADI",
                    "input_dependency": "KANITLANAMADI",
                    "static_fallback_risk": "UNKNOWN",
                    "evidence": "KANITLANAMADI",
                })
                continue

            # Evidence lines: pick first matching hint token
            evidence_lines: list[str] = []
            selected_hint = None
            for hint in spec.hints:
                hits = _extract_line_evidence(text, hint)
                if hits:
                    selected_hint = hint
                    evidence_lines = hits
                    break

            if not evidence_lines:
                field_map.append({
                    "field": spec.name,
                    "producer_file": f"src/simple/{producer}",
                    "function": "KANITLANAMADI",
                    "input_dependency": "KANITLANAMADI",
                    "static_fallback_risk": "UNKNOWN",
                    "evidence": "KANITLANAMADI",
                })
                continue

            # Classify risk based on the first evidence line
            first_line = evidence_lines[0]
            value_class = _classify_value_line(first_line)
            fallback_markers = _detect_fallback_branches(text)

            risk = "LOW"
            if value_class["static_literal"]:
                risk = "HIGH"
            elif "preview_plan" in text and spec.name in ("entry", "stop_loss", "tp", "RR"):
                risk = "MEDIUM"
            elif fallback_markers:
                risk = "MEDIUM"

            input_dep = "dynamic_inputs" if (".get(" in "\n".join(evidence_lines) or "flow_state" in text or "signal_event" in text) else "KANITLANAMADI"

            field_map.append({
                "field": spec.name,
                "producer_file": f"src/simple/{producer}",
                "function": "KANITLANAMADI",
                "input_dependency": input_dep,
                "static_fallback_risk": risk,
                "evidence": {
                    "hint": selected_hint,
                    "lines": evidence_lines,
                    "fallback_markers": fallback_markers,
                },
            })

            # Static/fallback finding extraction
            if value_class["static_literal"] or fallback_markers:
                static_findings.append({
                    "field": spec.name,
                    "static_value_or_fallback_logic": f"static_literal={value_class['static_literal']} fallback_markers={fallback_markers}",
                    "evidence": {"file": f"src/simple/{producer}", "lines": evidence_lines[:2]},
                    "severity": "HIGH" if value_class["static_literal"] else "MEDIUM",
                    "next_action": "Mode isolation + canonical producer; template/fallback audit for this field.",
                })

            # Dynamic dependency finding extraction
            if input_dep != "KANITLANAMADI":
                depends_on = []
                if "signal_event" in text or "latest_signal_event" in text:
                    depends_on.append("signal_event")
                if "flow_state" in text or "latest_flow_state" in text:
                    depends_on.append("flow_state")
                if "depth_memory" in text or "latest_depth_liquidity_memory" in text:
                    depends_on.append("depth_liquidity_memory")
                if "data_quality" in text or "dq_" in text:
                    depends_on.append("data_quality")
                if "scenario_trigger" in text or "latest_scenario_trigger" in text:
                    depends_on.append("scenario_trigger")
                if depends_on:
                    dynamic_findings.append({
                        "field": spec.name,
                        "depends_on": sorted(set(depends_on)),
                        "evidence": {"file": f"src/simple/{producer}", "hint": selected_hint},
                        "reliability": "MEDIUM",
                    })

            # Telegram specific
            if spec.name == "telegram_message_fields" and producer in ("telegram_paper_alert_engine.py", "telegram_research_reporter.py"):
                # Detect template-only lines: fixed labels + no conditional insertion except variables
                template_lines = _extract_line_evidence(text, "PAPER ONLY / REAL TRADE DISABLED") or _extract_line_evidence(text, "message_text")
                telegram_findings.append({
                    "field": "message_text",
                    "dynamic": True if "decision_gate.get(" in text or "load_json(" in text else False,
                    "source": f"src/simple/{producer}",
                    "evidence": template_lines[:3] or "KANITLANAMADI",
                    "risk": "MEDIUM" if template_lines else "KANITLANAMADI",
                })

    # Aggregate checks and risk codes
    checks: dict[str, bool] = {k: False for k in AUDIT_CHECKS}

    # Simple heuristics for check flags
    checks["fallback_branch_detected"] = any(
        isinstance(item.get("evidence"), dict) and item["evidence"].get("fallback_markers")
        for item in field_map
    )
    checks["default_value_overuse_detected"] = any(
        isinstance(item.get("evidence"), dict) and any("0.0" in ln for ln in (item["evidence"].get("lines") or []))
        for item in field_map
    )
    checks["telegram_template_only_detected"] = any(
        (tf.get("risk") == "MEDIUM" and "PAPER ONLY / REAL TRADE DISABLED" in "\n".join(tf.get("evidence") if isinstance(tf.get("evidence"), list) else []))
        for tf in telegram_findings
    )

    # Formula detection from known plan engine
    tpe = producer_text.get("trade_plan_engine.py", "")
    checks["entry_formula_detected"] = "ref_price" in tpe and "entry_price" in tpe
    checks["sl_formula_detected"] = "stop_loss" in tpe and "_stop_pct" in tpe
    checks["tp_formula_detected"] = "tp1" in tpe and "tp2" in tpe and "_direction_ok" in tpe

    checks.update(deps_rollup)

    # Static literal checks: look for explicit "0.0" assignment lines for key fields
    checks["rr_static_literal_detected"] = "rr_tp1 = 0.0" in tpe or "rr_tp2 = 0.0" in tpe
    scen = producer_text.get("scenario_entry_trigger_engine.py", "")
    checks["confidence_static_literal_detected"] = "trigger_confidence = 0.0" in scen or "confidence: 0.0" in scen
    checks["score_static_literal_detected"] = "scenario_score\": 0.0" in scen or "decision_score\": 0.0" in producer_text.get("decision_gate_engine.py", "")

    # Scenario static risk: if scenario label forced in a branch
    checks["scenario_static_detected"] = "scenario_label = \"NO_SCENARIO\"" in scen or "MODEL_" in scen
    checks["active_scenario_missing_or_static"] = "active_scenario = possible_scenarios[0]" in scen
    checks["grade_static_detected"] = "plan_grade = \"NO_PLAN\"" in tpe or "final_grade = \"BLOCKED\"" in producer_text.get("decision_gate_engine.py", "")

    # Reason-chain repeated literal: detect fixed safety codes appended across files
    safety_token = "SAFE_TO_OPEN_REAL_TRADE_FALSE"
    checks["reason_chain_repeated_literal_detected"] = sum(1 for t in producer_text.values() if safety_token in t) >= 4

    risk_codes: list[str] = []
    if checks["score_static_literal_detected"]:
        risk_codes.append("SCORE_TEMPLATE_RISK")
    if checks["confidence_static_literal_detected"]:
        risk_codes.append("CONFIDENCE_TEMPLATE_RISK")
    if checks["rr_static_literal_detected"]:
        risk_codes.append("RR_TEMPLATE_RISK")
    if not checks["entry_formula_detected"]:
        risk_codes.append("ENTRY_TEMPLATE_RISK")
    if not checks["sl_formula_detected"]:
        risk_codes.append("SL_TEMPLATE_RISK")
    if not checks["tp_formula_detected"]:
        risk_codes.append("TP_TEMPLATE_RISK")
    if checks["reason_chain_repeated_literal_detected"]:
        risk_codes.append("REASON_CHAIN_TEMPLATE_RISK")
    if checks["scenario_static_detected"]:
        risk_codes.append("SCENARIO_TEMPLATE_RISK")
    if checks["active_scenario_missing_or_static"]:
        risk_codes.append("ACTIVE_SCENARIO_MISSING")
    if checks["grade_static_detected"]:
        risk_codes.append("GRADE_TEMPLATE_RISK")
    if checks["telegram_template_only_detected"]:
        risk_codes.append("TELEGRAM_TEMPLATE_ONLY")
    if checks["fallback_branch_detected"]:
        risk_codes.append("FALLBACK_OVERUSED")
    if checks["default_value_overuse_detected"]:
        risk_codes.append("DEFAULT_VALUE_OVERUSED")

    if not checks["live_input_dependency_detected"]:
        risk_codes.append("LIVE_INPUT_NOT_USED")
    if not checks["market_state_dependency_detected"]:
        risk_codes.append("MARKET_STATE_NOT_USED")
    if not checks["liquidity_dependency_detected"]:
        risk_codes.append("LIQUIDITY_NOT_USED")
    if not checks["structure_dependency_detected"]:
        risk_codes.append("STRUCTURE_NOT_USED")
    if not checks["candle_dna_dependency_detected"]:
        risk_codes.append("DNA_NOT_USED")

    risk_codes = sorted(set(risk_codes))

    # Template risk summary
    severity_score = 0
    for code in risk_codes:
        if code in {"ENTRY_TEMPLATE_RISK", "SL_TEMPLATE_RISK", "TP_TEMPLATE_RISK", "RR_TEMPLATE_RISK", "TELEGRAM_TEMPLATE_ONLY"}:
            severity_score += 2
        elif code.endswith("_RISK") or code.endswith("_OVERUSED") or code.endswith("_MISSING"):
            severity_score += 1
    if severity_score >= 8:
        template_risk = "HIGH"
        p6 = {"title": "LOCAL DYNAMIC FORMULA PATCH PLAN", "reason": "Template/fallback risk HIGH; dynamic field ownership ve mode isolation patch planı gerekiyor."}
    elif severity_score >= 4:
        template_risk = "MEDIUM"
        p6 = {"title": "VPS TEMPLATE REALITY AUDIT", "reason": "Template risk MEDIUM; VPS’te gerçek değişkenlik kanıtı toplanmalı."}
    else:
        template_risk = "LOW"
        p6 = {"title": "VPS TEMPLATE REALITY AUDIT", "reason": "Template risk LOW; VPS gerçeklik denetimi ile doğrula."}

    payload = {
        "timestamp_utc": now_utc(),
        "summary": {"template_risk": template_risk, "risk_codes": risk_codes, "severity_score": severity_score},
        "audit_checks": checks,
        "field_production_map": field_map,
        "static_fallback_findings": static_findings,
        "dynamic_dependency_findings": dynamic_findings,
        "telegram_output_reality": telegram_findings,
        "prompt_6_recommendation": p6,
    }
    return payload


def _md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# LOCAL TEMPLATE / DYNAMIC OUTPUT AUDIT REPORT")
    lines.append("")
    lines.append("## 1. Net Hüküm")
    lines.append(f"Template risk: {payload['summary']['template_risk']}")
    lines.append("")
    lines.append("## 2. Field Production Map")
    lines.append("Field | Producer File | Function | Input Dependency | Static/Fallback Risk | Evidence")
    for row in payload["field_production_map"]:
        ev = row.get("evidence")
        ev_text = "KANITLANAMADI"
        if isinstance(ev, dict):
            hint = ev.get("hint")
            first = (ev.get("lines") or ["KANITLANAMADI"])[0]
            ev_text = f"{hint or '?'}; {first}"
        lines.append(f"{row['field']} | {row['producer_file']} | {row['function']} | {row['input_dependency']} | {row['static_fallback_risk']} | {ev_text}")
    lines.append("")
    lines.append("## 3. Static / Fallback Findings")
    lines.append("Field | Static Value / Fallback Logic | Evidence | Severity | Next Action")
    if payload["static_fallback_findings"]:
        for row in payload["static_fallback_findings"][:40]:
            ev = row["evidence"]
            ev_text = f"{ev.get('file')}; {(ev.get('lines') or ['KANITLANAMADI'])[0]}"
            lines.append(f"{row['field']} | {row['static_value_or_fallback_logic']} | {ev_text} | {row['severity']} | {row['next_action']}")
    else:
        lines.append("NONE | KANITLANAMADI | KANITLANAMADI | LOW | KANITLANAMADI")
    lines.append("")
    lines.append("## 4. Dynamic Dependency Findings")
    lines.append("Field | Depends On | Evidence | Reliability")
    if payload["dynamic_dependency_findings"]:
        for row in payload["dynamic_dependency_findings"][:40]:
            lines.append(f"{row['field']} | {', '.join(row['depends_on'])} | {row['evidence']['file']} | {row['reliability']}")
    else:
        lines.append("NONE | KANITLANAMADI | KANITLANAMADI | UNKNOWN")
    lines.append("")
    lines.append("## 5. Telegram Output Reality")
    lines.append("Field | Dynamic? | Source | Evidence | Risk")
    if payload["telegram_output_reality"]:
        for row in payload["telegram_output_reality"]:
            ev = row.get("evidence")
            ev_text = ev[0] if isinstance(ev, list) and ev else str(ev)
            lines.append(f"{row['field']} | {row['dynamic']} | {row['source']} | {ev_text} | {row['risk']}")
    else:
        lines.append("message_text | KANITLANAMADI | KANITLANAMADI | KANITLANAMADI | UNKNOWN")
    lines.append("")
    lines.append("## 6. Critical Template Risks")
    lines.append("Risk Code | Evidence | Severity | Why It Matters")
    for code in payload["summary"]["risk_codes"]:
        sev = "HIGH" if code in {"ENTRY_TEMPLATE_RISK", "SL_TEMPLATE_RISK", "TP_TEMPLATE_RISK", "RR_TEMPLATE_RISK", "TELEGRAM_TEMPLATE_ONLY"} else "MEDIUM"
        lines.append(f"{code} | see JSON evidence | {sev} | Dynamic outputs trade safety ve edge kalitesini etkiler.")
    lines.append("")
    lines.append("## 7. Prompt 6 Recommendation")
    lines.append(payload["prompt_6_recommendation"]["title"])
    lines.append(payload["prompt_6_recommendation"]["reason"])
    return "\n".join(lines) + "\n"


def main() -> None:
    payload = audit()
    REPORTS.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(_md(payload), encoding="utf-8")
    P6_OUT.write_text(
        "# LOCAL PROMPT 6 RECOMMENDATION\n\n"
        f"- Recommendation: {payload['prompt_6_recommendation']['title']}\n"
        f"- Reason: {payload['prompt_6_recommendation']['reason']}\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
