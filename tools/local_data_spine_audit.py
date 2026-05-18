from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "simple"
DATA = ROOT / "data" / "simple"
STATE = ROOT / "state" / "simple"
REPORTS = ROOT / "reports"

JSON_OUT = REPORTS / "local_data_spine_reality.json"
MD_OUT = REPORTS / "local_data_spine_reality_report.md"
P4_OUT = REPORTS / "local_prompt_4_recommendation.md"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def jsonl_first(path: Path) -> dict[str, Any] | None:
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


def exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def check_presence() -> dict[str, Any]:
    files = {
        "collector_entrypoint_exists": exists("src/simple/run_s12_flow_collector.py"),
        "raw_event_collector_exists": exists("src/simple/s12_flow_collector.py"),
        "raw_events_output_exists": exists("data/simple/live_flow_events.jsonl"),
        "raw_depth_output_exists": exists("data/simple/live_depth_events.jsonl"),
        "one_second_evidence_detected": exists("state/simple/latest_1s_evidence.json") or exists("state/simple/latest_flow_evidence.json"),
        "candle_dna_detected": exists("state/simple/latest_hybrid_candle_dna.json"),
        "snapshot_latest_exists": exists("state/simple/latest_observation_factory.json"),
    }
    return files


def detect_stream_definitions() -> dict[str, Any]:
    live_ws = read_text(SRC / "live_ws_runtime.py")
    s12 = read_text(SRC / "s12_flow_collector.py")
    ws_agg = read_text(SRC / "ws_agg_trade_collector.py")
    ws_book = read_text(SRC / "ws_book_ticker_collector.py")
    ws_depth = read_text(SRC / "ws_depth_collector.py")

    return {
        "binance_public_source_defined": ("stream.binance.com" in live_ws) or ("api.binance.com" in read_text(SRC / "binance_public_feed.py")),
        "aggtrade_fields_detected": ("aggTrade" in live_ws) and ("agg_trade_id" in ws_agg),
        "bookticker_fields_detected": ("bookTicker" in live_ws) and ("best_bid" in ws_book and "best_ask" in ws_book),
        "depth_fields_detected": ("depth20" in live_ws) and ("bid_levels" in ws_depth and "ask_levels" in ws_depth),
        "bid_ask_notional_detected": "notional" in ws_depth,
        "book_imbalance_detected": "imbalance" in ws_depth,
        "raw_events_schema_detected": "timestamp_utc" in ws_agg and "stream" in ws_agg and "price" in ws_agg,
        "freshness_fields_detected": ("age_seconds" in read_text(SRC / "flow_bucket_builder.py")) or ("latest_event_age_seconds" in read_text(SRC / "live_flow_quality_audit.py")),
        "data_quality_fields_detected": "data_quality" in read_text(SRC / "flow_bucket_builder.py"),
    }


def chain_audit() -> list[dict[str, Any]]:
    chain = [
        ("BINANCE_PUBLIC", "RAW_EVENTS"),
        ("RAW_EVENTS", "1S_EVIDENCE"),
        ("1S_EVIDENCE", "CANDLE_DNA"),
        ("CANDLE_DNA", "MARKET_CONTEXT"),
        ("MARKET_CONTEXT", "SCENARIO"),
        ("SCENARIO", "TRADE_PLAN"),
        ("TRADE_PLAN", "DECISION"),
    ]

    checks = []
    checks.append(
        {
            "link": "BINANCE_PUBLIC->RAW_EVENTS",
            "real_input": "stream.binance.com" in read_text(SRC / "live_ws_runtime.py"),
            "input_readable": True,
            "output_written": exists("data/simple/live_flow_events.jsonl"),
            "timestamp_preserved": bool((jsonl_first(DATA / "live_flow_events.jsonl") or {}).get("timestamp_utc")),
            "price_source_present": "SOURCE_LIVE_WS_REAL" in read_text(SRC / "ws_agg_trade_collector.py") or "SOURCE_LIVE_WS_REAL" in read_text(SRC / "ws_depth_collector.py"),
            "live_sim_mode_split": "FAKE_SAMPLE" in read_text(SRC / "run_s12_flow_collector.py"),
            "data_quality_present": "data_quality" in read_text(SRC / "flow_bucket_builder.py"),
            "missing_evidence_reported": "NO_DATA" in read_text(SRC / "run_s1_market_truth.py"),
            "evidence": "src/simple/live_ws_runtime.py, src/simple/s12_flow_collector.py",
        }
    )
    checks.append(
        {
            "link": "RAW_EVENTS->1S_EVIDENCE",
            "real_input": "latest_flow_state.json" in read_text(SRC / "run_s2_1s_evidence.py"),
            "input_readable": exists("state/simple/latest_flow_state.json"),
            "output_written": exists("state/simple/latest_1s_evidence.json"),
            "timestamp_preserved": bool((read_json(STATE / "latest_1s_evidence.json") or {}).get("timestamp_utc")),
            "price_source_present": "FLOW_STATE_LIVE" in read_text(SRC / "run_s2_1s_evidence.py"),
            "live_sim_mode_split": "FAKE_SAMPLE" in read_text(SRC / "run_s2_1s_evidence.py"),
            "data_quality_present": bool((read_json(STATE / "latest_1s_evidence.json") or {}).get("data_quality")),
            "missing_evidence_reported": "NO_DATA" in read_text(SRC / "run_s2_1s_evidence.py"),
            "evidence": "src/simple/run_s2_1s_evidence.py",
        }
    )
    checks.append(
        {
            "link": "1S_EVIDENCE->CANDLE_DNA",
            "real_input": "latest_1s_evidence.json" in read_text(SRC / "run_s3_hybrid_candle_dna.py"),
            "input_readable": exists("state/simple/latest_1s_evidence.json"),
            "output_written": exists("state/simple/latest_hybrid_candle_dna.json"),
            "timestamp_preserved": bool((read_json(STATE / "latest_hybrid_candle_dna.json") or {}).get("timestamp_utc")),
            "price_source_present": "BINANCE_CLOSED_KLINE" in read_text(SRC / "run_s3_hybrid_candle_dna.py"),
            "live_sim_mode_split": "FAKE_SAMPLE" in read_text(SRC / "run_s3_hybrid_candle_dna.py"),
            "data_quality_present": bool((read_json(STATE / "latest_hybrid_candle_dna.json") or {}).get("data_quality")),
            "missing_evidence_reported": "NO_DATA" in read_text(SRC / "run_s3_hybrid_candle_dna.py"),
            "evidence": "src/simple/run_s3_hybrid_candle_dna.py",
        }
    )
    checks.append(
        {
            "link": "CANDLE_DNA->MARKET_CONTEXT",
            "real_input": "latest_observation_factory.json" in read_text(SRC / "mtf_candle_dna_factory.py"),
            "input_readable": exists("state/simple/latest_hybrid_candle_dna.json"),
            "output_written": exists("state/simple/latest_observation_factory.json"),
            "timestamp_preserved": bool((read_json(STATE / "latest_observation_factory.json") or {}).get("timestamp_utc")),
            "price_source_present": "market_snapshot" in read_text(SRC / "observation_factory.py"),
            "live_sim_mode_split": "FAKE" in read_text(SRC / "observation_factory.py"),
            "data_quality_present": bool((read_json(STATE / "latest_observation_factory.json") or {}).get("data_quality")),
            "missing_evidence_reported": "MISSING" in read_text(SRC / "observation_factory.py"),
            "evidence": "src/simple/observation_factory.py",
        }
    )
    checks.append(
        {
            "link": "MARKET_CONTEXT->SCENARIO",
            "real_input": "latest_setup_context.json" in read_text(SRC / "scenario_entry_trigger_engine.py"),
            "input_readable": exists("state/simple/latest_setup_context.json"),
            "output_written": exists("state/simple/latest_scenario_trigger.json"),
            "timestamp_preserved": bool((read_json(STATE / "latest_scenario_trigger.json") or {}).get("timestamp_utc")),
            "price_source_present": "direction_bias" in read_text(SRC / "scenario_entry_trigger_engine.py"),
            "live_sim_mode_split": "no_valid_output" in read_text(SRC / "scenario_entry_trigger_engine.py"),
            "data_quality_present": bool((read_json(STATE / "latest_scenario_trigger.json") or {}).get("data_quality")),
            "missing_evidence_reported": "INSUFFICIENT_DATA" in read_text(SRC / "scenario_entry_trigger_engine.py"),
            "evidence": "src/simple/scenario_entry_trigger_engine.py",
        }
    )
    checks.append(
        {
            "link": "SCENARIO->TRADE_PLAN",
            "real_input": "latest_signal_event.json" in read_text(SRC / "trade_plan_engine.py"),
            "input_readable": exists("state/simple/latest_signal_event.json") or exists("state/simple/epoch_v2/latest_signal_event.json"),
            "output_written": exists("state/simple/latest_trade_plan.json"),
            "timestamp_preserved": bool((read_json(STATE / "latest_trade_plan.json") or {}).get("timestamp_utc")),
            "price_source_present": "reference price" in read_text(SRC / "trade_plan_engine.py"),
            "live_sim_mode_split": "FAKE_SAMPLE" in read_text(SRC / "trade_plan_decision_engine.py"),
            "data_quality_present": bool((read_json(STATE / "latest_trade_plan.json") or {}).get("data_quality")),
            "missing_evidence_reported": "NO_PLAN" in read_text(SRC / "trade_plan_engine.py"),
            "evidence": "src/simple/trade_plan_engine.py",
        }
    )
    checks.append(
        {
            "link": "TRADE_PLAN->DECISION",
            "real_input": "latest_trade_plan.json" in read_text(SRC / "decision_gate_engine.py"),
            "input_readable": exists("state/simple/latest_trade_plan.json"),
            "output_written": exists("state/simple/latest_decision_gate.json"),
            "timestamp_preserved": bool((read_json(STATE / "latest_decision_gate.json") or {}).get("timestamp_utc")),
            "price_source_present": "selected_entry" in read_text(SRC / "decision_gate_engine.py"),
            "live_sim_mode_split": "no_valid_output" in read_text(SRC / "decision_gate_engine.py"),
            "data_quality_present": bool((read_json(STATE / "latest_decision_gate.json") or {}).get("data_quality")),
            "missing_evidence_reported": "TRADE_PLAN_MISSING" in read_text(SRC / "decision_gate_engine.py"),
            "evidence": "src/simple/decision_gate_engine.py",
        }
    )
    return checks


def context_dependency_table() -> list[dict[str, Any]]:
    rows = [
        ("MARKET_CONTEXT", "src/simple/observation_factory.py", ["state/simple/latest_flow_evidence.json", "state/simple/latest_depth_liquidity_memory.json"], "state/simple/latest_observation_factory.json"),
        ("SCENARIO", "src/simple/scenario_entry_trigger_engine.py", ["state/simple/latest_setup_context.json", "state/simple/latest_flow_state.json"], "state/simple/latest_scenario_trigger.json"),
        ("TRADE_PLAN", "src/simple/trade_plan_engine.py", ["state/simple/latest_signal_event.json", "state/simple/latest_scenario_trigger.json"], "state/simple/latest_trade_plan.json"),
        ("DECISION", "src/simple/decision_gate_engine.py", ["state/simple/latest_trade_plan.json"], "state/simple/latest_decision_gate.json"),
    ]
    out: list[dict[str, Any]] = []
    for layer, file_rel, reads, writes in rows:
        text = read_text(ROOT / file_rel)
        proven = any(Path(r).name in text for r in reads)
        out.append(
            {
                "layer": layer,
                "reads_from": reads,
                "writes_to": writes,
                "live_dependency_proven": proven,
                "evidence": file_rel if proven else "KANITLANAMADI",
            }
        )
    return out


def live_sim_separation() -> list[dict[str, Any]]:
    files = ["src/simple/local_pipeline_runner.py", "src/simple/run_local_full_pipeline.py", "src/simple/vps_observer.py", "src/simple/run_s12_flow_collector.py"]
    out = []
    for rel in files:
        t = read_text(ROOT / rel)
        mode = []
        if "LIVE" in t:
            mode.append("LIVE")
        if "FAKE_SAMPLE" in t or "fake-sample" in t:
            mode.append("FAKE_SAMPLE")
        if "SIMULATION" in t or "replay" in t.lower():
            mode.append("SIMULATION/REPLAY")
        risk = "HIGH" if ("LIVE" in mode and ("FAKE_SAMPLE" in mode or "SIMULATION/REPLAY" in mode)) else "LOW"
        out.append({"file": rel, "mode_handling": ",".join(mode) or "KANITLANAMADI", "risk": risk, "evidence": "mixed markers present" if risk == "HIGH" else "isolated_or_unknown"})
    return out


def template_fallback_risk() -> list[dict[str, Any]]:
    checks = [
        ("src/simple/trade_plan_engine.py", ["_FAKE", "preview_plan", "NO_PLAN"]),
        ("src/simple/trade_plan_decision_engine.py", ["_FAKE_", "PLAN_READY"]),
        ("src/simple/contract_driven_trade_plan_engine.py", ["source_mode\": \"STATE_FILE", "NOT_READY"]),
    ]
    out = []
    for rel, toks in checks:
        t = read_text(ROOT / rel)
        found = [tok for tok in toks if tok in t]
        if not found:
            out.append({"file": rel, "risk": "KANITLANAMADI", "evidence": "KANITLANAMADI", "severity": "LOW", "next_action": "manual inspect"})
            continue
        sev = "MEDIUM"
        risk = "TRADE_PLAN_TEMPLATE_RISK" if "_FAKE" in "".join(found) or "preview_plan" in found else "LOW"
        if risk != "LOW":
            sev = "HIGH" if "trade_plan_decision_engine.py" in rel else "MEDIUM"
        out.append({"file": rel, "risk": risk, "evidence": ", ".join(found), "severity": sev, "next_action": "runtime mode guard + canonical producer"})
    return out


def missing_critical_evidence() -> list[dict[str, Any]]:
    required = [
        ("raw_events_schema", "RAW_EVENTS", "data/simple/live_flow_events.jsonl"),
        ("book_ticker_stream", "RAW_EVENTS", "src/simple/live_ws_runtime.py"),
        ("depth_stream", "RAW_EVENTS", "src/simple/live_ws_runtime.py"),
        ("1s_evidence_latest", "1S_EVIDENCE", "state/simple/latest_1s_evidence.json"),
        ("candle_dna_latest", "CANDLE_DNA", "state/simple/latest_hybrid_candle_dna.json"),
        ("market_state_latest", "MARKET_CONTEXT", "state/simple/latest_market_regime_classifier.json"),
    ]
    out = []
    for ev, req_for, rel in required:
        ok = exists(rel)
        out.append(
            {
                "evidence": ev,
                "required_for": req_for,
                "missing_where": rel if not ok else "",
                "risk": "HIGH" if not ok else "LOW",
            }
        )
    return out


def risk_codes(payload: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    p = payload["presence"]
    s = payload["streams"]
    if not p["raw_event_collector_exists"]:
        codes.append("NO_RAW_COLLECTOR")
    if p["raw_events_output_exists"] and not p["one_second_evidence_detected"]:
        codes.append("RAW_EXISTS_BUT_NOT_USED")
    if not s["bookticker_fields_detected"]:
        codes.append("BOOKTICKER_MISSING")
    if not s["depth_fields_detected"]:
        codes.append("DEPTH_MISSING")
    if s["bid_ask_notional_detected"] is False:
        codes.append("BID_ASK_NOTIONAL_NULL_RISK")

    links = {c["link"]: c for c in payload["chain_checks"]}
    if not links["RAW_EVENTS->1S_EVIDENCE"]["real_input"]:
        codes.append("RAW_TO_1S_BROKEN")
    if not p["one_second_evidence_detected"]:
        codes.append("ONE_SECOND_EVIDENCE_MISSING")
    if not links["1S_EVIDENCE->CANDLE_DNA"]["real_input"]:
        codes.append("CANDLE_DNA_NOT_FROM_1S")
    if not links["CANDLE_DNA->MARKET_CONTEXT"]["real_input"]:
        codes.append("CONTEXT_NOT_FROM_DATA_SPINE")
    if not links["MARKET_CONTEXT->SCENARIO"]["real_input"]:
        codes.append("SCENARIO_NOT_FROM_CONTEXT")

    if any(r["risk"] == "TRADE_PLAN_TEMPLATE_RISK" for r in payload["template_fallback_risk"]):
        codes.append("TRADE_PLAN_TEMPLATE_RISK")
    if any(r["risk"] == "HIGH" for r in payload["live_vs_simulation"]):
        codes.append("LIVE_SIMULATION_MIXED")
    if "FAKE_SAMPLE" in read_text(SRC / "local_pipeline_runner.py") and "LIVE" in read_text(SRC / "local_pipeline_runner.py"):
        codes.append("FAKE_SAMPLE_LEAK_RISK")
    if not links["BINANCE_PUBLIC->RAW_EVENTS"]["price_source_present"]:
        codes.append("PRICE_SOURCE_UNKNOWN")
    if any(not c["data_quality_present"] for c in payload["chain_checks"]):
        codes.append("DATA_QUALITY_MISSING")
    if not s["freshness_fields_detected"]:
        codes.append("FRESHNESS_MISSING")
    return sorted(set(codes))


def decide_status(codes: list[str]) -> str:
    if not codes:
        return "PASS"
    high = {"NO_RAW_COLLECTOR", "RAW_TO_1S_BROKEN", "ONE_SECOND_EVIDENCE_MISSING", "LIVE_SIMULATION_MIXED", "FAKE_SAMPLE_LEAK_RISK"}
    if any(c in high for c in codes):
        return "FAIL"
    return "PARTIAL"


def prompt4_reco(status: str) -> dict[str, str]:
    if status == "PASS":
        return {
            "title": "VPS DATA SPINE REALITY AUDIT",
            "reason": "Lokal data spine contract yeterince net; uzun koşu gerçeklik denetimi VPS tarafına taşınabilir.",
        }
    return {
        "title": "LOCAL DATA SPINE CONTRACT PATCH PLAN",
        "reason": "Lokal data spine zincirinde contract/izolasyon kırıkları bulundu; önce lokal contract patch planı gerekli.",
    }


def to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# LOCAL DATA SPINE REALITY REPORT")
    lines.append("")
    lines.append("## 1. Net Hüküm")
    lines.append(f"Data spine durumu: {payload['summary']['status']}")
    lines.append("")
    lines.append("## 2. Data Source Inventory")
    lines.append("Source | File | Function | Output | Evidence | Status")
    for r in payload["source_inventory"]:
        lines.append(f"{r['source']} | {r['file']} | {r['function']} | {r['output']} | {r['evidence']} | {r['status']}")
    lines.append("")
    lines.append("## 3. Raw → 1S → DNA Chain")
    lines.append("Link | Status | Evidence | Risk")
    for c in payload["chain_checks"]:
        ok = all([c["real_input"], c["input_readable"], c["output_written"], c["timestamp_preserved"], c["data_quality_present"]])
        status = "PASS" if ok else "PARTIAL"
        risk = "LOW" if ok else "MEDIUM"
        lines.append(f"{c['link']} | {status} | {c['evidence']} | {risk}")
    lines.append("")
    lines.append("## 4. Context/Scenario/Trade Plan Data Dependency")
    lines.append("Layer | Reads From | Writes To | Live Dependency Proven? | Evidence")
    for r in payload["context_dependency"]:
        lines.append(f"{r['layer']} | {', '.join(r['reads_from'])} | {r['writes_to']} | {r['live_dependency_proven']} | {r['evidence']}")
    lines.append("")
    lines.append("## 5. Live vs Simulation Separation")
    lines.append("File | Mode Handling | Risk | Evidence")
    for r in payload["live_vs_simulation"]:
        lines.append(f"{r['file']} | {r['mode_handling']} | {r['risk']} | {r['evidence']}")
    lines.append("")
    lines.append("## 6. Template/Fallback Risk")
    lines.append("File | Risk | Evidence | Severity | Next Action")
    for r in payload["template_fallback_risk"]:
        lines.append(f"{r['file']} | {r['risk']} | {r['evidence']} | {r['severity']} | {r['next_action']}")
    lines.append("")
    lines.append("## 7. Missing Critical Evidence")
    lines.append("Evidence | Required For | Missing Where | Risk")
    for r in payload["missing_critical_evidence"]:
        lines.append(f"{r['evidence']} | {r['required_for']} | {r['missing_where'] or '-'} | {r['risk']}")
    lines.append("")
    lines.append("## 8. Prompt 4 Recommendation")
    lines.append(payload["prompt_4_recommendation"]["title"])
    lines.append(payload["prompt_4_recommendation"]["reason"])
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    presence = check_presence()
    streams = detect_stream_definitions()
    chain = chain_audit()
    context_dep = context_dependency_table()
    live_sim = live_sim_separation()
    template = template_fallback_risk()
    missing = missing_critical_evidence()

    source_inventory = [
        {
            "source": "BINANCE_PUBLIC_STREAM",
            "file": "src/simple/live_ws_runtime.py",
            "function": "LiveWsRuntime.run",
            "output": "data/simple/live_flow_events.jsonl,data/simple/live_depth_events.jsonl",
            "evidence": "wss://stream.binance.com + aggTrade/bookTicker/kline/depth20",
            "status": "ACTIVE" if streams["binance_public_source_defined"] else "MISSING",
        },
        {
            "source": "RAW_EVENT_COLLECTOR",
            "file": "src/simple/s12_flow_collector.py",
            "function": "FlowCollector.ingest",
            "output": "state/simple/latest_flow_state.json,state/simple/latest_depth_state.json",
            "evidence": "parse_agg_trade/parse_book_ticker/parse_depth20",
            "status": "ACTIVE" if presence["raw_event_collector_exists"] else "MISSING",
        },
        {
            "source": "1S_EVIDENCE",
            "file": "src/simple/run_s2_1s_evidence.py",
            "function": "main",
            "output": "state/simple/latest_1s_evidence.json",
            "evidence": "reads latest_flow_state.json",
            "status": "ACTIVE" if presence["one_second_evidence_detected"] else "MISSING",
        },
        {
            "source": "CANDLE_DNA",
            "file": "src/simple/run_s3_hybrid_candle_dna.py",
            "function": "main",
            "output": "state/simple/latest_hybrid_candle_dna.json",
            "evidence": "reads latest_1s_evidence + flow kline",
            "status": "ACTIVE" if presence["candle_dna_detected"] else "MISSING",
        },
    ]

    payload = {
        "timestamp_utc": now_utc(),
        "presence": presence,
        "streams": streams,
        "chain_checks": chain,
        "context_dependency": context_dep,
        "live_vs_simulation": live_sim,
        "template_fallback_risk": template,
        "missing_critical_evidence": missing,
        "source_inventory": source_inventory,
    }
    codes = risk_codes(payload)
    status = decide_status(codes)
    reco = prompt4_reco(status)
    payload["summary"] = {"status": status, "risk_codes": codes}
    payload["prompt_4_recommendation"] = reco

    REPORTS.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(to_markdown(payload), encoding="utf-8")
    P4_OUT.write_text(
        "# LOCAL PROMPT 4 RECOMMENDATION\n\n"
        f"- Recommendation: {reco['title']}\n"
        f"- Reason: {reco['reason']}\n",
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
