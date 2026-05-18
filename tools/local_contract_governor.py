from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
STATE_DIR = ROOT / "state"
DATA_DIR = ROOT / "data"
TESTS_DIR = ROOT / "tests"
REPORTS_DIR = ROOT / "reports"

JSON_REPORT = REPORTS_DIR / "local_contract_governor.json"
MD_REPORT = REPORTS_DIR / "local_contract_governor_report.md"
PROMPT3_REPORT = REPORTS_DIR / "local_prompt_3_recommendation.md"

REQUIRED_FIELDS = ["timestamp_utc", "data_quality", "reason_codes"]
EQUIVALENT_LINEAGE_FIELDS = ["context_id", "lineage", "identity", "parent_id", "setup_id", "signal_id"]
EQUIVALENT_FEEDS_FIELDS = ["feeds_next", "next_blocks", "feeds"]


@dataclass
class Layer:
    name: str
    output: str
    tests: list[str]
    producers: list[str]
    expected_input_patterns: list[str]


LAYERS: list[Layer] = [
    Layer("RAW", "data/simple/live_flow_events.jsonl", ["tests/simple/test_s12_flow_collector.py"], ["src/simple/ws_agg_trade_collector.py", "src/simple/raw_flow_event_logger.py"], []),
    Layer("1S", "state/simple/latest_1s_evidence.json", ["tests/simple/test_lightweight_1s_evidence_engine.py"], ["src/simple/lightweight_1s_evidence_engine.py", "src/simple/flow_evidence_engine.py"], ["live_flow_events.jsonl"]),
    Layer("DNA", "state/simple/latest_hybrid_candle_dna.json", ["tests/simple/test_hybrid_candle_dna_engine.py"], ["src/simple/hybrid_candle_dna_engine.py"], ["latest_1s_evidence.json", "latest_market_truth.json"]),
    Layer("MTF", "state/simple/latest_mtf_candle_dna.json", ["tests/simple/test_timeframe_resolver.py"], ["src/simple/mtf_candle_dna_factory.py"], ["latest_hybrid_candle_dna.json"]),
    Layer("FOOTPRINT", "state/simple/latest_observation_factory.json", ["tests/simple/test_flow_bucket_builder.py"], ["src/simple/observation_factory.py"], ["latest_mtf_candle_dna.json", "live_flow_events.jsonl"]),
    Layer("LIQUIDITY", "state/simple/latest_liquidity_map.json", ["tests/simple/test_depth_liquidity_memory.py"], ["src/simple/liquidity_map_engine.py", "src/simple/run_s27_depth_liquidity_memory.py"], ["latest_observation_factory.json", "live_depth_events.jsonl"]),
    Layer("STRUCTURE", "state/simple/latest_market_structure.json", ["tests/simple/test_market_structure_v2_engine.py"], ["src/simple/market_structure_engine.py", "src/simple/market_structure_v2_engine.py"], ["latest_liquidity_map.json", "latest_mtf_candle_dna.json"]),
    Layer("MARKET_STATE", "state/simple/latest_market_regime_classifier.json", ["tests/simple/test_regime_classifier_engine.py"], ["src/simple/market_regime_classifier.py", "src/simple/run_regime_classifier.py"], ["latest_market_structure.json"]),
    Layer("EVENT_INTERPRETATION", "state/simple/latest_interpretation.json", ["tests/simple/test_explainability_engine.py"], ["src/simple/interpretation_engine.py"], ["latest_market_regime", "latest_market_structure.json"]),
    Layer("ACTIVE_SCENARIO", "state/simple/latest_scenario_trigger.json", ["tests/simple/test_scenario_entry_trigger_engine.py"], ["src/simple/scenario_entry_trigger_engine.py", "src/simple/three_scenario_engine.py"], ["latest_interpretation.json", "latest_setup_context.json"]),
    Layer("SETUP", "state/simple/latest_setup_candidate.json", ["tests/simple/test_setup_candidate_engine.py"], ["src/simple/setup_candidate_engine.py"], ["latest_scenario_trigger.json", "latest_setup_context.json"]),
    Layer("SIGNAL", "state/simple/epoch_v2/latest_signal_event.json", ["tests/simple/test_layer_separation_patch_a.py"], ["src/simple/signal_event_consolidator.py"], ["latest_setup_candidate.json", "latest_scenario_trigger.json"]),
    Layer("TRADE_PLAN", "state/simple/latest_trade_plan.json", ["tests/simple/test_trade_plan_engine.py"], ["src/simple/trade_plan_engine.py", "src/simple/contract_driven_trade_plan_engine.py"], ["latest_signal_event.json"]),
    Layer("DECISION", "state/simple/latest_decision_gate.json", ["tests/simple/test_decision_gate_engine.py"], ["src/simple/decision_gate_engine.py", "src/simple/contract_decision_gate.py"], ["latest_trade_plan.json"]),
    Layer("PAPER", "state/simple/latest_paper_lifecycle.json", ["tests/simple/test_paper_lifecycle_tracker.py"], ["src/simple/paper_lifecycle_tracker.py", "src/simple/research_paper_lifecycle_engine.py"], ["latest_decision_gate.json"]),
    Layer("OUTCOME", "state/simple/latest_outcome_monitor.json", ["tests/simple/test_outcome_monitor.py"], ["src/simple/outcome_monitor.py", "src/simple/paper_outcome_tracker.py"], ["latest_paper_lifecycle.json"]),
    Layer("EDGE", "state/simple/epoch_v2/latest_research_edge_matrix.json", ["tests/simple/test_research_edge_matrix_engine.py"], ["src/simple/research_edge_matrix_engine.py", "src/simple/edge_matrix_v2.py"], ["latest_outcome_monitor.json", "outcome_events.jsonl"]),
    Layer("BRAIN", "state/simple/latest_simple_brain_v2.json", ["tests/simple/test_simple_brain_v2.py"], ["src/simple/simple_brain_v2.py", "src/simple/simple_brain_report_engine.py"], ["latest_research_edge_matrix.json", "latest_edge_matrix_v2.json"]),
]

BROKEN_CODES = [
    "HAS_RAW_NO_1S",
    "HAS_1S_NO_DNA",
    "HAS_DNA_NO_MTF",
    "HAS_MTF_NO_FOOTPRINT",
    "HAS_FOOTPRINT_NO_LIQUIDITY",
    "HAS_LIQUIDITY_NO_STRUCTURE",
    "HAS_STRUCTURE_NO_MARKET_STATE",
    "HAS_MARKET_STATE_NO_INTERPRETATION",
    "HAS_INTERPRETATION_NO_ACTIVE_SCENARIO",
    "HAS_SCENARIO_NO_SETUP",
    "HAS_SETUP_NO_SIGNAL",
    "HAS_SIGNAL_NO_TRADE_PLAN",
    "HAS_TRADE_PLAN_NO_DECISION",
    "HAS_DECISION_NO_PAPER",
    "HAS_PAPER_NO_OUTCOME",
    "HAS_OUTCOME_NO_EDGE",
    "HAS_EDGE_NO_BRAIN",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_first_jsonl(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                return json.loads(line)
    except Exception:
        return None
    return None


def exists_rel(rel: str) -> bool:
    return (ROOT / rel).exists()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def has_any_field(payload: dict[str, Any], fields: list[str]) -> bool:
    return any(field in payload for field in fields)


def detect_duplicate_outputs() -> list[dict[str, Any]]:
    pattern = re.compile(r"latest_[A-Za-z0-9_]+\.json")
    producers: dict[str, list[str]] = {}
    for py in (SRC_DIR / "simple").glob("*.py"):
        text = read_text(py)
        for m in pattern.findall(text):
            producers.setdefault(m, [])
            producers[m].append(str(py.relative_to(ROOT)).replace("\\", "/"))
    out: list[dict[str, Any]] = []
    for output, files in sorted(producers.items()):
        uniq = sorted(set(files))
        if len(uniq) > 1:
            sev = "HIGH" if any(k in output for k in ["trade_plan", "decision", "outcome", "edge", "market_structure"]) else "MEDIUM"
            out.append({"output": output, "producers": uniq, "severity": sev, "action": "Canonical producer belirlenmeli."})
    return out


def stale_file_detection() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        name = p.name.lower()
        if ".bak_" in name or name.endswith(".tmp") or name.endswith(".old"):
            findings.append({"file": rel, "risk": "STALE_FILE", "evidence": "backup/tmp artifact", "action": "Manual review"})
    return findings


def gather_layer_status(layer: Layer) -> dict[str, Any]:
    output_path = ROOT / layer.output
    output_exists = output_path.exists()
    output_payload: dict[str, Any] = {}
    valid_json_latest_state = False
    jsonl_readable = False

    if output_path.suffix == ".json":
        payload = load_json(output_path)
        if isinstance(payload, dict):
            output_payload = payload
            valid_json_latest_state = True
    elif output_path.suffix == ".jsonl":
        row = read_first_jsonl(output_path)
        if isinstance(row, dict):
            output_payload = row
            jsonl_readable = True

    history_guess = None
    if layer.output.endswith(".json"):
        stem = Path(layer.output).name.replace("latest_", "").replace(".json", "")
        guess1 = ROOT / "data" / "simple" / f"{stem}_history.jsonl"
        guess2 = ROOT / "data" / "simple" / f"{stem}.jsonl"
        if guess1.exists():
            history_guess = str(guess1.relative_to(ROOT)).replace("\\", "/")
        elif guess2.exists():
            history_guess = str(guess2.relative_to(ROOT)).replace("\\", "/")

    tests_exist = [t for t in layer.tests if exists_rel(t)]
    missing_required = [k for k in REQUIRED_FIELDS if k not in output_payload]
    missing_timestamp = "timestamp_utc" not in output_payload
    missing_data_quality = "data_quality" not in output_payload
    missing_reason_codes = "reason_codes" not in output_payload
    missing_lineage = not has_any_field(output_payload, EQUIVALENT_LINEAGE_FIELDS)
    missing_feeds = not has_any_field(output_payload, EQUIVALENT_FEEDS_FIELDS)

    required_fields_present = len(missing_required) == 0

    status = "PASS"
    if not output_exists:
        status = "FAIL"
    elif not required_fields_present:
        status = "PARTIAL"

    input_exists = all((ROOT / p).exists() for p in layer.expected_input_patterns if "/" in p and p.startswith(("state/", "data/")))
    if not layer.expected_input_patterns:
        input_exists = True

    return {
        "layer": layer.name,
        "input_exists": input_exists,
        "output_exists": output_exists,
        "output_path": layer.output,
        "history_path": history_guess,
        "valid_json_latest_state": valid_json_latest_state if output_path.suffix == ".json" else None,
        "jsonl_readable": jsonl_readable if output_path.suffix == ".jsonl" else None,
        "required_fields_present": required_fields_present,
        "timestamp_present": not missing_timestamp,
        "data_quality_present": not missing_data_quality,
        "reason_codes_present": not missing_reason_codes,
        "feeds_next_present_or_equivalent": not missing_feeds,
        "parent_id_or_lineage_present": not missing_lineage,
        "tests": layer.tests,
        "tests_existing": tests_exist,
        "missing_required_fields": missing_required,
        "status": status,
    }


def output_to_input_link(src_layer: Layer, dst_layer: Layer) -> tuple[bool, str]:
    src_name = Path(src_layer.output).name
    used_by_dst = False
    evidence = "KANITLANAMADI"
    for producer in dst_layer.producers:
        p = ROOT / producer
        text = read_text(p)
        if src_name in text:
            used_by_dst = True
            evidence = f"{producer} references {src_name}"
            break
        for pat in src_layer.expected_input_patterns:
            if pat and pat in text:
                used_by_dst = True
                evidence = f"{producer} references {pat}"
                break
    return used_by_dst, evidence


def chain_links(layer_statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links = []
    for i in range(len(LAYERS) - 1):
        a = LAYERS[i]
        b = LAYERS[i + 1]
        a_status = layer_statuses[i]
        b_status = layer_statuses[i + 1]
        uses, ev = output_to_input_link(a, b)
        ok = a_status["output_exists"] and b_status["output_exists"] and uses
        links.append(
            {
                "from": a.name,
                "to": b.name,
                "output_exists": a_status["output_exists"],
                "upper_uses_output": uses,
                "feeds_next_or_equivalent": a_status["feeds_next_present_or_equivalent"],
                "timestamp_present": a_status["timestamp_present"],
                "reason_codes_present": a_status["reason_codes_present"],
                "data_quality_present": a_status["data_quality_present"],
                "lineage_or_context_present": a_status["parent_id_or_lineage_present"],
                "status": "PASS" if ok else "BROKEN",
                "evidence": ev,
            }
        )
    return links


def broken_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for idx, link in enumerate(links):
        if link["status"] == "PASS":
            continue
        code = BROKEN_CODES[idx] if idx < len(BROKEN_CODES) else "UNKNOWN_BROKEN_LINK"
        severity = "HIGH" if idx >= 10 else "MEDIUM"
        missing_bits = []
        if not link["output_exists"]:
            missing_bits.append("output_missing")
        if not link["upper_uses_output"]:
            missing_bits.append("input_link_missing")
        if not link["feeds_next_or_equivalent"]:
            missing_bits.append("feeds_next_missing")
        out.append(
            {
                "code": code,
                "evidence": f"{link['from']}->{link['to']}: {', '.join(missing_bits) or 'KANITLANAMADI'}; {link['evidence']}",
                "severity": severity,
                "why_it_matters": "Data spine kopar, üst katman güvenilir karar üretemez.",
                "next_fix": "Canonical output-input bağlantısı ve contract alanları netleştirilmeli.",
            }
        )
    return out


def snapshot_event_risk() -> list[dict[str, Any]]:
    checks = [
        ("src/simple/outcome_monitor.py", "snapshot"),
        ("src/simple/research_edge_matrix_engine.py", "outcome_events.jsonl"),
        ("src/simple/edge_matrix_v2.py", "history"),
    ]
    out = []
    for rel, token in checks:
        p = ROOT / rel
        t = read_text(p)
        if not t:
            out.append({"file": rel, "risk": "UNKNOWN", "evidence": "KANITLANAMADI", "action": "File inspection"})
            continue
        risk = "MEDIUM" if token in t else "LOW"
        ev = f"token `{token}` found" if token in t else "KANITLANAMADI"
        action = "Closed outcome event whitelist kullan." if risk == "MEDIUM" else "Monitor"
        out.append({"file": rel, "risk": risk, "evidence": ev, "action": action})
    return out


def live_simulation_mixing_risk() -> list[dict[str, Any]]:
    targets = ["src/simple/local_pipeline_runner.py", "run_loop.py", "src/simple/vps_observer.py"]
    out = []
    for rel in targets:
        t = read_text(ROOT / rel)
        if not t:
            out.append({"file": rel, "risk": "UNKNOWN", "evidence": "KANITLANAMADI", "action": "Inspect"})
            continue
        has_live = "LIVE" in t
        has_fake = "FAKE" in t or "fake" in t
        has_legacy = "_LEGACY_BRIDGE_STAGES" in t
        if has_live and (has_fake or has_legacy):
            risk = "HIGH"
            ev = "LIVE + FAKE/LEGACY markers aynı dosyada"
            action = "Runtime stage isolation denetimi gerekli."
        elif has_live and has_fake:
            risk = "MEDIUM"
            ev = "LIVE + FAKE markers"
            action = "Mode guard güçlendirilmeli."
        else:
            risk = "LOW"
            ev = "mixing marker yok"
            action = "Monitor"
        out.append({"file": rel, "risk": risk, "evidence": ev, "action": action})
    return out


def build_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# LOCAL CONTRACT GOVERNOR REPORT")
    lines.append("")
    lines.append("## 1. Net Hüküm")
    lines.append(f"- Chain integrity durumu: {payload['summary']['chain_integrity']}")
    lines.append(f"- En kritik kırık link: {payload['summary']['most_critical_broken_link']}")
    lines.append("")
    lines.append("## 2. Layer Contract Status")
    lines.append("Layer | Input Exists | Output Exists | Required Fields | Tests | Status")
    for row in payload["layers"]:
        lines.append(
            f"{row['layer']} | {row['input_exists']} | {row['output_exists']} | {row['required_fields_present']} | {len(row['tests_existing'])}/{len(row['tests'])} | {row['status']}"
        )
    lines.append("")
    lines.append("## 3. Broken Links")
    lines.append("Code | Evidence | Severity | Why It Matters | Next Fix")
    if payload["broken_links"]:
        for b in payload["broken_links"]:
            lines.append(f"{b['code']} | {b['evidence']} | {b['severity']} | {b['why_it_matters']} | {b['next_fix']}")
    else:
        lines.append("NONE | KANITLANAMADI | LOW | KANITLANAMADI | KANITLANAMADI")
    lines.append("")
    lines.append("## 4. Field Integrity")
    lines.append("Layer | Missing timestamp | Missing data_quality | Missing reason_codes | Missing lineage | Missing feeds_next")
    for row in payload["layers"]:
        lines.append(
            f"{row['layer']} | {not row['timestamp_present']} | {not row['data_quality_present']} | {not row['reason_codes_present']} | {not row['parent_id_or_lineage_present']} | {not row['feeds_next_present_or_equivalent']}"
        )
    lines.append("")
    lines.append("## 5. Snapshot/Event Risk")
    lines.append("File | Risk | Evidence | Action")
    for r in payload["snapshot_event_risk"]:
        lines.append(f"{r['file']} | {r['risk']} | {r['evidence']} | {r['action']}")
    lines.append("")
    lines.append("## 6. Live/Simulation Mixing Risk")
    lines.append("File | Risk | Evidence | Action")
    for r in payload["live_simulation_mixing_risk"]:
        lines.append(f"{r['file']} | {r['risk']} | {r['evidence']} | {r['action']}")
    lines.append("")
    lines.append("## 7. Duplicate Output Risk")
    lines.append("Output | Producers | Severity | Action")
    if payload["duplicate_output_risk"]:
        for d in payload["duplicate_output_risk"]:
            lines.append(f"{d['output']} | {', '.join(d['producers'])} | {d['severity']} | {d['action']}")
    else:
        lines.append("NONE | KANITLANAMADI | LOW | KANITLANAMADI")
    lines.append("")
    lines.append("## 8. Prompt 3 Recommendation")
    lines.append(payload["prompt_3_recommendation"]["title"])
    lines.append(payload["prompt_3_recommendation"]["reason"])
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_REPORT.write_text(build_report(payload), encoding="utf-8")
    p3 = payload["prompt_3_recommendation"]
    PROMPT3_REPORT.write_text(
        "# LOCAL PROMPT 3 RECOMMENDATION\n\n"
        f"- Recommendation: {p3['title']}\n"
        f"- Reason: {p3['reason']}\n"
        f"- Scope: {p3['scope']}\n",
        encoding="utf-8",
    )


def run() -> dict[str, Any]:
    layer_rows = [gather_layer_status(layer) for layer in LAYERS]
    links = chain_links(layer_rows)
    broken = broken_links(links)
    duplicate = detect_duplicate_outputs()
    stale = stale_file_detection()
    snap_risk = snapshot_event_risk()
    live_mix = live_simulation_mixing_risk()

    pass_count = sum(1 for l in links if l["status"] == "PASS")
    if pass_count == len(links):
        integrity = "PASS"
    elif pass_count >= len(links) // 2:
        integrity = "PARTIAL"
    else:
        integrity = "FAIL"

    most_critical = broken[0]["code"] if broken else "NONE"
    p3_title = "LOCAL DATA SPINE REALITY AUDIT" if integrity != "PASS" else "VPS DATA SPINE REALITY AUDIT"
    p3_reason = (
        "Chain link ve contract alanlarında lokal kırıklar var; önce local data spine doğrulanmalı."
        if integrity != "PASS"
        else "Lokal chain integrity yeterli; uzun süreli gerçeklik denetimi VPS tarafında yapılabilir."
    )

    payload = {
        "timestamp_utc": now_utc(),
        "chain": [f"{LAYERS[i].name}->{LAYERS[i+1].name}" for i in range(len(LAYERS) - 1)],
        "summary": {
            "chain_integrity": integrity,
            "pass_links": pass_count,
            "total_links": len(links),
            "most_critical_broken_link": most_critical,
        },
        "layers": layer_rows,
        "links": links,
        "broken_links": broken,
        "duplicate_output_risk": duplicate,
        "stale_file_detection": stale,
        "snapshot_event_risk": snap_risk,
        "live_simulation_mixing_risk": live_mix,
        "prompt_3_recommendation": {
            "title": p3_title,
            "reason": p3_reason,
            "scope": "read-only reality audit, no trade logic changes",
        },
    }
    write_reports(payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
