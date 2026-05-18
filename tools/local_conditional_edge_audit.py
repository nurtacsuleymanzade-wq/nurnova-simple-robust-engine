from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"

JSON_OUT = REPORTS_DIR / "local_conditional_edge_audit.json"
MD_OUT = REPORTS_DIR / "local_conditional_edge_audit_report.md"
P12_OUT = REPORTS_DIR / "local_prompt_12_recommendation.md"

EDGE_REL = "src/simple/research_edge_matrix_engine.py"
PIPELINE_REL = "src/simple/local_pipeline_runner.py"
TRUE_OUTCOME_REL = "src/edge/true_outcome_engine.py"
CONTRACT_EDGE_REL = "src/simple/contract_edge_matrix_engine.py"
EDGE_V2_REL = "src/simple/edge_matrix_v2.py"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def file_exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def line_of(rel: str, token: str) -> int | None:
    text = read_text(rel)
    if not text:
        return None
    for i, line in enumerate(text.splitlines(), start=1):
        if token in line:
            return i
    return None


def state_json(rel: str) -> dict[str, Any] | None:
    path = ROOT / rel
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def jsonl_last(rel: str) -> dict[str, Any] | None:
    path = ROOT / rel
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                return row
        except Exception:
            continue
    return None


def evidence(items: list[str]) -> str:
    clean = [x for x in items if x]
    return "; ".join(clean) if clean else "KANITLANAMADI"


def check_bool(name: str, ok: bool, ev: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "evidence": ev}


def run_checks() -> tuple[dict[str, Any], dict[str, str]]:
    checks: dict[str, Any] = {}
    ev_map: dict[str, str] = {}

    edge_engine_found = file_exists(EDGE_REL) and (line_of(PIPELINE_REL, "RESEARCH_EDGE_MATRIX_ENGINE") is not None)
    ev_map["edge_engine_found"] = evidence(
        [
            f"{EDGE_REL}:1" if file_exists(EDGE_REL) else "",
            f"{PIPELINE_REL}:{line_of(PIPELINE_REL, 'RESEARCH_EDGE_MATRIX_ENGINE')}",
        ]
    )
    checks["edge_engine_found"] = edge_engine_found

    reads_outcomes = line_of(EDGE_REL, "OUTCOME_EVENTS_PATH") is not None and line_of(EDGE_REL, "read_jsonl_tail_objects(OUTCOME_EVENTS_PATH") is not None
    ev_map["edge_reads_closed_outcomes"] = evidence(
        [
            f"{EDGE_REL}:{line_of(EDGE_REL, 'OUTCOME_EVENTS_PATH')}",
            f"{EDGE_REL}:{line_of(EDGE_REL, 'read_jsonl_tail_objects(OUTCOME_EVENTS_PATH')}",
        ]
    )
    checks["edge_reads_closed_outcomes"] = reads_outcomes

    rejects_open = (
        line_of(EDGE_REL, "bool(trade.get(\"closed_only\", True))") is not None
        and line_of(EDGE_REL, "outcome_status") is not None
        and line_of(EDGE_REL, "in {\"TP1_HIT\", \"TP2_HIT\", \"SL_HIT\", \"EXPIRED\"}") is not None
    )
    ev_map["edge_rejects_open_trades"] = evidence(
        [
            f"{EDGE_REL}:{line_of(EDGE_REL, 'bool(trade.get(\"closed_only\", True))')}",
            f"{EDGE_REL}:{line_of(EDGE_REL, 'in {\"TP1_HIT\", \"TP2_HIT\", \"SL_HIT\", \"EXPIRED\"}')}",
        ]
    )
    checks["edge_rejects_open_trades"] = rejects_open

    replay_source_present = (
        line_of(TRUE_OUTCOME_REL, "\"source_mode\": \"BOUNDED_CANDLE_REPLAY\"") is not None
        and line_of(TRUE_OUTCOME_REL, "append_event(\"outcome_events.jsonl\"") is not None
    )
    rejects_snapshots = False
    ev_map["edge_rejects_snapshots"] = evidence(
        [
            f"{TRUE_OUTCOME_REL}:{line_of(TRUE_OUTCOME_REL, '\"source_mode\": \"BOUNDED_CANDLE_REPLAY\"')}" if replay_source_present else "",
            f"{TRUE_OUTCOME_REL}:{line_of(TRUE_OUTCOME_REL, 'append_event(\"outcome_events.jsonl\"')}" if replay_source_present else "",
            "KANITLANAMADI",
        ]
    )
    checks["edge_rejects_snapshots"] = rejects_snapshots

    outcome_id_used = line_of(EDGE_REL, "outcome_id") is not None
    checks["outcome_id_used"] = outcome_id_used
    ev_map["outcome_id_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, 'outcome_id')}" if outcome_id_used else "KANITLANAMADI"])

    paper_trade_id_used = line_of(EDGE_REL, "paper_trade_id") is not None
    checks["paper_trade_id_used"] = paper_trade_id_used
    ev_map["paper_trade_id_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, 'paper_trade_id')}"])

    setup_family_used = line_of(EDGE_REL, "\"setup_family\"") is not None
    checks["setup_family_used"] = setup_family_used
    ev_map["setup_family_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, '\"setup_family\"')}"])

    signal_type_used = line_of(EDGE_REL, "\"signal_type\"") is not None
    checks["signal_type_used"] = signal_type_used
    ev_map["signal_type_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, '\"signal_type\"')}" if signal_type_used else "KANITLANAMADI"])

    trend_used = line_of(EDGE_REL, "\"trend\"") is not None
    regime_used = line_of(EDGE_REL, "\"regime\"") is not None
    liquidity_state_used = line_of(EDGE_REL, "\"liquidity_state\"") is not None
    active_scenario_used = line_of(EDGE_REL, "\"active_scenario\"") is not None
    market_state_used = line_of(EDGE_REL, "\"market_state\"") is not None

    checks["trend_used"] = trend_used
    checks["regime_used"] = regime_used
    checks["liquidity_state_used"] = liquidity_state_used
    checks["active_scenario_used"] = active_scenario_used
    checks["market_state_used"] = market_state_used

    ev_map["trend_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, '\"trend\"')}" if trend_used else "KANITLANAMADI"])
    ev_map["regime_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, '\"regime\"')}" if regime_used else "KANITLANAMADI"])
    ev_map["liquidity_state_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, '\"liquidity_state\"')}" if liquidity_state_used else "KANITLANAMADI"])
    ev_map["active_scenario_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, '\"active_scenario\"')}" if active_scenario_used else "KANITLANAMADI"])
    ev_map["market_state_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, '\"market_state\"')}" if market_state_used else "KANITLANAMADI"])

    grouping_detected = (
        setup_family_used
        and trend_used
        and regime_used
        and liquidity_state_used
        and active_scenario_used
        and signal_type_used
    )
    checks["conditional_grouping_detected"] = grouping_detected
    ev_map["conditional_grouping_detected"] = evidence(
        [
            f"{EDGE_REL}:{line_of(EDGE_REL, 'GROUP_FIELDS = (')}",
            f"{EDGE_REL}:{line_of(EDGE_REL, '\"setup_family\"')}",
        ]
    )

    winrate_calculated = line_of(EDGE_REL, "winrate = round(") is not None
    expectancy_calculated = line_of(EDGE_REL, "expectancy = round(") is not None
    profit_factor_calculated = line_of(EDGE_REL, "profit_factor") is not None
    sample_size_threshold_used = (
        line_of(EDGE_REL, "if sample_size < 20:") is not None
        or line_of(EDGE_REL, ">= 20") is not None
    )
    edge_status_classification_used = (
        line_of(EDGE_REL, "edge_status = \"SAMPLE_BUILDING\"") is not None
        and line_of(EDGE_REL, "edge_status = \"EDGE_ACTIVE\"") is not None
    )

    checks["winrate_calculated"] = winrate_calculated
    checks["expectancy_calculated"] = expectancy_calculated
    checks["profit_factor_calculated"] = profit_factor_calculated
    checks["sample_size_threshold_used"] = sample_size_threshold_used
    checks["edge_status_classification_used"] = edge_status_classification_used

    ev_map["winrate_calculated"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, 'winrate = round(')}"])
    ev_map["expectancy_calculated"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, 'expectancy = round(')}"])
    ev_map["profit_factor_calculated"] = evidence(
        [
            f"{CONTRACT_EDGE_REL}:{line_of(CONTRACT_EDGE_REL, 'profit_factor = round(')}"
            if line_of(CONTRACT_EDGE_REL, "profit_factor = round(") is not None
            else "KANITLANAMADI"
        ]
    )
    ev_map["sample_size_threshold_used"] = evidence([f"{EDGE_REL}:{line_of(EDGE_REL, 'if sample_size < 20:')}"])
    ev_map["edge_status_classification_used"] = evidence(
        [
            f"{EDGE_REL}:{line_of(EDGE_REL, 'edge_status = \"SAMPLE_BUILDING\"')}",
            f"{EDGE_REL}:{line_of(EDGE_REL, 'edge_status = \"EDGE_ACTIVE\"')}",
        ]
    )

    return checks, ev_map


def input_sources(ev_map: dict[str, str]) -> list[dict[str, Any]]:
    outcome_last = jsonl_last("data/simple/epoch_v2/outcome_events.jsonl")
    outcome_empty = outcome_last is None
    source_mode_replay_line = line_of(TRUE_OUTCOME_REL, "\"source_mode\": \"BOUNDED_CANDLE_REPLAY\"")

    return [
        {
            "input_source": "data/simple/epoch_v2/outcome_events.jsonl",
            "used": True,
            "closed_only": True,
            "snapshot_risk": "HIGH" if source_mode_replay_line else "MEDIUM",
            "evidence": evidence(
                [
                    ev_map.get("edge_reads_closed_outcomes", ""),
                    ev_map.get("edge_rejects_open_trades", ""),
                    f"{TRUE_OUTCOME_REL}:{source_mode_replay_line}" if source_mode_replay_line else "",
                    "data/simple/epoch_v2/outcome_events.jsonl:last_record=EMPTY" if outcome_empty else "data/simple/epoch_v2/outcome_events.jsonl:last_record=FOUND",
                ]
            ),
        },
        {
            "input_source": "data/simple/outcome_monitor_history.jsonl",
            "used": False,
            "closed_only": False,
            "snapshot_risk": "LOW",
            "evidence": evidence([f"{EDGE_V2_REL}:{line_of(EDGE_V2_REL, 'OUTCOME_HISTORY_PATH = DATA_DIR / \"outcome_monitor_history.jsonl\"')}"]),
        },
        {
            "input_source": "data/simple/epoch_v2/true_outcome_history.jsonl",
            "used": False,
            "closed_only": False,
            "snapshot_risk": "HIGH",
            "evidence": evidence([f"{TRUE_OUTCOME_REL}:{line_of(TRUE_OUTCOME_REL, 'HISTORY_PATH = epoch_data_path(\"true_outcome_history.jsonl\")')}"]),
        },
    ]


def grouping_rows(checks: dict[str, Any], ev_map: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"field": "pattern/setup_family", "used": checks["setup_family_used"], "evidence": ev_map["setup_family_used"], "risk": "-" if checks["setup_family_used"] else "SETUP_FAMILY_NOT_USED"},
        {"field": "signal_type", "used": checks["signal_type_used"], "evidence": ev_map["signal_type_used"], "risk": "-" if checks["signal_type_used"] else "SIGNAL_TYPE_NOT_USED"},
        {"field": "trend", "used": checks["trend_used"], "evidence": ev_map["trend_used"], "risk": "-" if checks["trend_used"] else "TREND_NOT_USED_IN_EDGE"},
        {"field": "regime", "used": checks["regime_used"], "evidence": ev_map["regime_used"], "risk": "-" if checks["regime_used"] else "REGIME_NOT_USED_IN_EDGE"},
        {"field": "liquidity_state", "used": checks["liquidity_state_used"], "evidence": ev_map["liquidity_state_used"], "risk": "-" if checks["liquidity_state_used"] else "LIQUIDITY_STATE_NOT_USED_IN_EDGE"},
        {"field": "active_scenario", "used": checks["active_scenario_used"], "evidence": ev_map["active_scenario_used"], "risk": "-" if checks["active_scenario_used"] else "ACTIVE_SCENARIO_NOT_USED_IN_EDGE"},
        {"field": "market_state", "used": checks["market_state_used"], "evidence": ev_map["market_state_used"], "risk": "-" if checks["market_state_used"] else "CONDITIONAL_GROUPING_MISSING"},
        {"field": "conditional_grouping_detected", "used": checks["conditional_grouping_detected"], "evidence": ev_map["conditional_grouping_detected"], "risk": "-" if checks["conditional_grouping_detected"] else "CONDITIONAL_GROUPING_MISSING"},
    ]


def metric_rows(checks: dict[str, Any], ev_map: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"metric": "winrate", "present": checks["winrate_calculated"], "evidence": ev_map["winrate_calculated"], "risk": "-" if checks["winrate_calculated"] else "EDGE_STATUS_MISSING"},
        {"metric": "expectancy", "present": checks["expectancy_calculated"], "evidence": ev_map["expectancy_calculated"], "risk": "-" if checks["expectancy_calculated"] else "EXPECTANCY_MISSING"},
        {"metric": "profit_factor", "present": checks["profit_factor_calculated"], "evidence": ev_map["profit_factor_calculated"], "risk": "-" if checks["profit_factor_calculated"] else "PROFIT_FACTOR_MISSING"},
        {"metric": "sample_size_threshold", "present": checks["sample_size_threshold_used"], "evidence": ev_map["sample_size_threshold_used"], "risk": "-" if checks["sample_size_threshold_used"] else "SAMPLE_SIZE_THRESHOLD_MISSING"},
        {"metric": "edge_status_classification", "present": checks["edge_status_classification_used"], "evidence": ev_map["edge_status_classification_used"], "risk": "-" if checks["edge_status_classification_used"] else "EDGE_STATUS_MISSING"},
    ]


def critical_risks(checks: dict[str, Any], ev_map: dict[str, str]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if not checks["edge_engine_found"]:
        risks.append({"risk_code": "EDGE_ENGINE_MISSING", "evidence": ev_map["edge_engine_found"], "severity": "HIGH", "required_fix": "Active pipeline icin canonical edge engine zorunlu."})
    if not checks["edge_rejects_open_trades"]:
        risks.append({"risk_code": "EDGE_USES_OPEN_TRADES", "evidence": ev_map["edge_rejects_open_trades"], "severity": "HIGH", "required_fix": "Open trade kayitlari edge ogrenmesine girmemeli."})
    if not checks["edge_rejects_snapshots"]:
        risks.append({"risk_code": "EDGE_USES_SNAPSHOT", "evidence": ev_map["edge_rejects_snapshots"], "severity": "HIGH", "required_fix": "Replay/snapshot kaynakli outcome eventleri ayristirilmali."})
    if not checks["outcome_id_used"]:
        risks.append({"risk_code": "OUTCOME_ID_NOT_USED", "evidence": ev_map["outcome_id_used"], "severity": "HIGH", "required_fix": "Grouping ve lineage icin outcome_id kullanilmali."})
    if not checks["signal_type_used"]:
        risks.append({"risk_code": "SIGNAL_TYPE_NOT_USED", "evidence": ev_map["signal_type_used"], "severity": "MEDIUM", "required_fix": "Signal type conditional bucket'a eklenmeli."})
    if not checks["trend_used"]:
        risks.append({"risk_code": "TREND_NOT_USED_IN_EDGE", "evidence": ev_map["trend_used"], "severity": "HIGH", "required_fix": "Trend field edge grouping anahtarina tasinmali."})
    if not checks["regime_used"]:
        risks.append({"risk_code": "REGIME_NOT_USED_IN_EDGE", "evidence": ev_map["regime_used"], "severity": "HIGH", "required_fix": "Regime field edge grouping anahtarina tasinmali."})
    if not checks["liquidity_state_used"]:
        risks.append({"risk_code": "LIQUIDITY_STATE_NOT_USED_IN_EDGE", "evidence": ev_map["liquidity_state_used"], "severity": "HIGH", "required_fix": "Liquidity state conditional edge baglamina eklenmeli."})
    if not checks["active_scenario_used"]:
        risks.append({"risk_code": "ACTIVE_SCENARIO_NOT_USED_IN_EDGE", "evidence": ev_map["active_scenario_used"], "severity": "HIGH", "required_fix": "Active scenario field edge lineage/grouping'e eklenmeli."})
    if not checks["conditional_grouping_detected"]:
        risks.append({"risk_code": "CONDITIONAL_GROUPING_MISSING", "evidence": ev_map["conditional_grouping_detected"], "severity": "HIGH", "required_fix": "pattern+trend+regime+liquidity+active_scenario+signal_type grouping zorunlu."})
    if not checks["profit_factor_calculated"]:
        risks.append({"risk_code": "PROFIT_FACTOR_MISSING", "evidence": ev_map["profit_factor_calculated"], "severity": "MEDIUM", "required_fix": "Canonical edge outputunda profit_factor eklenmeli."})
    if not checks["sample_size_threshold_used"]:
        risks.append({"risk_code": "SAMPLE_SIZE_THRESHOLD_MISSING", "evidence": ev_map["sample_size_threshold_used"], "severity": "MEDIUM", "required_fix": "Sample threshold policy zorunlu."})
    if not checks["edge_status_classification_used"]:
        risks.append({"risk_code": "EDGE_STATUS_MISSING", "evidence": ev_map["edge_status_classification_used"], "severity": "MEDIUM", "required_fix": "Edge status siniflandirmasi zorunlu."})
    return risks


def summary_status(checks: dict[str, Any], risks: list[dict[str, Any]]) -> dict[str, str]:
    high = sum(1 for r in risks if r["severity"] == "HIGH")
    medium = sum(1 for r in risks if r["severity"] == "MEDIUM")

    if checks["edge_engine_found"] and checks["edge_reads_closed_outcomes"] and checks["edge_rejects_open_trades"]:
        edge_matrix = "PASS" if high == 0 and medium == 0 else "PARTIAL"
    else:
        edge_matrix = "FAIL"

    conditional = "PASS" if checks["conditional_grouping_detected"] else ("PARTIAL" if checks["setup_family_used"] else "FAIL")

    if checks["edge_reads_closed_outcomes"] and checks["edge_rejects_open_trades"] and checks["edge_rejects_snapshots"]:
        cleanliness = "PASS"
    elif checks["edge_reads_closed_outcomes"] and checks["edge_rejects_open_trades"]:
        cleanliness = "PARTIAL"
    else:
        cleanliness = "FAIL"

    return {
        "edge_matrix_status": edge_matrix,
        "conditional_edge_readiness": conditional,
        "edge_cleanliness": cleanliness,
    }


def recommendation(summary: dict[str, str]) -> str:
    if summary["conditional_edge_readiness"] != "PASS":
        return "Prompt 12 = LOCAL CONDITIONAL EDGE PATCH PLAN"
    if summary["edge_matrix_status"] == "PASS" and summary["edge_cleanliness"] == "PASS":
        return "Prompt 12 = VPS FINAL PRE-AUDIT"
    return "Prompt 12 = VPS CONDITIONAL EDGE REALITY AUDIT"


def markdown(payload: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("# LOCAL CONDITIONAL EDGE MATRIX AUDIT REPORT")
    out.append("")
    out.append("## 1. Net Hüküm")
    out.append(f"Edge Matrix: {payload['summary']['edge_matrix_status']}")
    out.append("")
    out.append(f"Conditional Edge Readiness: {payload['summary']['conditional_edge_readiness']}")
    out.append("")
    out.append(f"Edge Cleanliness: {payload['summary']['edge_cleanliness']}")
    out.append("")
    out.append("## 2. Edge Input Sources")
    out.append("Input Source | Used? | Closed Only? | Snapshot Risk | Evidence")
    for row in payload["edge_input_sources"]:
        out.append(f"{row['input_source']} | {row['used']} | {row['closed_only']} | {row['snapshot_risk']} | {row['evidence']}")
    out.append("")
    out.append("## 3. Conditional Grouping")
    out.append("Field | Used? | Evidence | Risk")
    for row in payload["conditional_grouping"]:
        out.append(f"{row['field']} | {row['used']} | {row['evidence']} | {row['risk']}")
    out.append("")
    out.append("## 4. Edge Metrics")
    out.append("Metric | Present? | Evidence | Risk")
    for row in payload["edge_metrics"]:
        out.append(f"{row['metric']} | {row['present']} | {row['evidence']} | {row['risk']}")
    out.append("")
    out.append("## 5. Critical Edge Risks")
    out.append("Risk Code | Evidence | Severity | Required Fix")
    if payload["critical_edge_risks"]:
        for row in payload["critical_edge_risks"]:
            out.append(f"{row['risk_code']} | {row['evidence']} | {row['severity']} | {row['required_fix']}")
    else:
        out.append("NONE | KANITLANAMADI | LOW | NONE")
    out.append("")
    out.append("## 6. Prompt 12 Recommendation")
    out.append(payload["prompt_12_recommendation"])
    return "\n".join(out) + "\n"


def run() -> dict[str, Any]:
    checks, ev_map = run_checks()
    sources = input_sources(ev_map)
    grouping = grouping_rows(checks, ev_map)
    metrics = metric_rows(checks, ev_map)
    risks = critical_risks(checks, ev_map)
    summary = summary_status(checks, risks)

    latest_research = state_json("state/simple/epoch_v2/latest_research_edge_matrix.json") or {}
    latest_contract = state_json("state/simple/latest_contract_edge_matrix.json") or {}
    latest_edge_v2 = state_json("state/simple/latest_edge_matrix_v2.json") or {}

    payload = {
        "generated_at_utc": now_utc(),
        "summary": summary,
        "audit_checks": checks,
        "audit_evidence_map": ev_map,
        "edge_input_sources": sources,
        "conditional_grouping": grouping,
        "edge_metrics": metrics,
        "critical_edge_risks": risks,
        "state_evidence": {
            "latest_research_edge_matrix_keys": list(latest_research.keys()) if latest_research else [],
            "latest_research_edge_status": latest_research.get("edge_status"),
            "latest_research_group_count": ((latest_research.get("summary") or {}).get("group_count") if isinstance(latest_research.get("summary"), dict) else None),
            "latest_contract_edge_matrix_keys": list(latest_contract.keys()) if latest_contract else [],
            "latest_edge_matrix_v2_keys": list(latest_edge_v2.keys()) if latest_edge_v2 else [],
            "outcome_events_last_keys": list((jsonl_last("data/simple/epoch_v2/outcome_events.jsonl") or {}).keys()),
        },
    }
    payload["prompt_12_recommendation"] = recommendation(summary)
    payload["risk_codes_detected"] = sorted({row["risk_code"] for row in risks})
    return payload


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = run()
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(markdown(payload), encoding="utf-8")
    P12_OUT.write_text(payload["prompt_12_recommendation"] + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(JSON_OUT),
                "report": str(MD_OUT),
                "recommendation": str(P12_OUT),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
