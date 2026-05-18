from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"

JSON_OUT = REPORTS_DIR / "local_lineage_outcome_audit.json"
MD_OUT = REPORTS_DIR / "local_lineage_outcome_audit_report.md"
P8_OUT = REPORTS_DIR / "local_prompt_8_recommendation.md"


SOURCE_FILES = [
    "src/simple/setup_candidate_engine.py",
    "src/simple/scenario_entry_trigger_engine.py",
    "src/simple/signal_event_consolidator.py",
    "src/simple/trade_plan_engine.py",
    "src/simple/decision_gate_engine.py",
    "src/simple/paper_lifecycle_tracker.py",
    "src/simple/outcome_monitor.py",
    "src/simple/paper_outcome_tracker.py",
    "src/simple/research_edge_matrix_engine.py",
    "src/simple/research_paper_lifecycle_engine.py",
    "src/simple/lineage_event_logger.py",
]


ID_FIELDS = [
    "setup_id",
    "active_scenario_id",
    "signal_id",
    "trade_plan_id",
    "plan_id",
    "decision_id",
    "paper_trade_id",
    "outcome_id",
    "edge_event_id",
    "lineage_id",
    "context_id",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def find_literal_line(rel: str, literal: str) -> int | None:
    text = read_text(rel)
    if not text:
        return None
    for idx, line in enumerate(text.splitlines(), start=1):
        if literal in line:
            return idx
    return None


def file_exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def read_json_keys(rel: str) -> list[str]:
    path = ROOT / rel
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return list(payload.keys())
    except Exception:
        return []
    return []


def last_jsonl_keys(rel: str) -> list[str]:
    path = ROOT / rel
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                return list(row.keys())
            return []
    except Exception:
        return []
    return []


def evidence_or_unknown(items: list[str]) -> str:
    clean = [item for item in items if item]
    return "; ".join(clean) if clean else "KANITLANAMADI"


def scan_id_inventory() -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for field in ID_FIELDS:
        producer = None
        consumer = None
        evidence: list[str] = []
        found = False
        for rel in SOURCE_FILES:
            text = read_text(rel)
            if not text:
                continue
            line_num = find_literal_line(rel, field)
            if line_num is None:
                continue
            found = True
            line_hint = f"{rel}:{line_num}"
            if producer is None and (f'"{field}":' in text or f"'{field}':" in text):
                producer = rel
            if consumer is None and (f'.get("{field}")' in text or f".get('{field}')" in text):
                consumer = rel
            evidence.append(line_hint)
        inventory.append(
            {
                "id_field": field,
                "found": found,
                "producer": producer or "KANITLANAMADI",
                "consumer": consumer or "KANITLANAMADI",
                "evidence": evidence_or_unknown(evidence[:3]),
            }
        )
    return inventory


def check_setup_to_signal() -> dict[str, Any]:
    file_rel = "src/simple/signal_event_consolidator.py"
    l1 = find_literal_line(file_rel, '"setup_id": setup_id')
    l2 = find_literal_line(file_rel, '"active_scenario_id": active_scenario_id')
    l3 = find_literal_line(file_rel, "parent_id=setup_id")
    ok = all(v is not None for v in (l1, l2, l3))
    return {
        "link": "SETUP->SIGNAL",
        "status": "PASS" if ok else "BROKEN",
        "evidence": evidence_or_unknown(
            [
                f"{file_rel}:{l1}" if l1 else "",
                f"{file_rel}:{l2}" if l2 else "",
                f"{file_rel}:{l3}" if l3 else "",
                "tests/simple/test_layer_separation_patch_a.py:52",
            ]
        ),
        "risk": None if ok else "SETUP_TO_SIGNAL_BROKEN",
        "required_fix": "Signal outputunda setup_id ve active_scenario_id zorunlu tutulmali." if not ok else "None",
    }


def check_signal_to_plan() -> dict[str, Any]:
    file_rel = "src/simple/trade_plan_engine.py"
    l1 = find_literal_line(file_rel, 'ready_for_entry = bool(signal_event.get("signal_id"))')
    l2 = find_literal_line(file_rel, 'if input_status == "MISSING" or not signal_event or not signal_event.get("signal_id"):')
    l3 = find_literal_line(file_rel, '"trade_plan_id": hashlib.sha1')
    l4 = find_literal_line(file_rel, '"signal_id": signal_event.get("signal_id")')
    ok = all(v is not None for v in (l1, l2, l3, l4))
    return {
        "link": "SIGNAL->TRADE_PLAN",
        "status": "PASS" if ok else "BROKEN",
        "evidence": evidence_or_unknown(
            [
                f"{file_rel}:{l1}" if l1 else "",
                f"{file_rel}:{l2}" if l2 else "",
                f"{file_rel}:{l3}" if l3 else "",
                f"{file_rel}:{l4}" if l4 else "",
                "tests/simple/test_layer_separation_patch_a.py:52",
            ]
        ),
        "risk": None if ok else "SIGNAL_TO_PLAN_BROKEN",
        "required_fix": "signal_id olmadan plan_status NO_PLAN zorunlulugu korunmali." if not ok else "None",
    }


def check_plan_to_decision() -> dict[str, Any]:
    file_rel = "src/simple/decision_gate_engine.py"
    l1 = find_literal_line(file_rel, 'decision = "ALLOW_PAPER"')
    l2 = find_literal_line(file_rel, 'decision = "WATCH_ONLY"')
    l3 = find_literal_line(file_rel, 'decision = "BLOCK"')
    l4 = find_literal_line(file_rel, '"trade_plan_id": trade_plan.get("trade_plan_id")')
    l5 = find_literal_line(file_rel, '"decision_id": decision_id')
    ok = all(v is not None for v in (l1, l2, l3, l4, l5))
    return {
        "link": "TRADE_PLAN->DECISION",
        "status": "PASS" if ok else "BROKEN",
        "evidence": evidence_or_unknown(
            [
                f"{file_rel}:{l1}" if l1 else "",
                f"{file_rel}:{l2}" if l2 else "",
                f"{file_rel}:{l3}" if l3 else "",
                f"{file_rel}:{l4}" if l4 else "",
                f"{file_rel}:{l5}" if l5 else "",
                "tests/simple/test_decision_gate_engine.py:91",
            ]
        ),
        "risk": None if ok else "PLAN_TO_DECISION_BROKEN",
        "required_fix": "Decision contract enum ve plan referans alani sabitlenmeli." if not ok else "None",
    }


def check_decision_to_paper() -> dict[str, Any]:
    file_rel = "src/simple/paper_lifecycle_tracker.py"
    l1 = find_literal_line(file_rel, 'return bool(decision_gate.get("allowed_for_paper_lifecycle", False))')
    l2 = find_literal_line(file_rel, 'if not decision_gate.get("decision_id") or not (trade_plan or {}).get("trade_plan_id") or not (trade_plan or {}).get("signal_id"):')
    l3 = find_literal_line(file_rel, '"paper_trade_id": lifecycle_id')
    ok = all(v is not None for v in (l1, l2, l3))
    return {
        "link": "DECISION->PAPER_LIFECYCLE",
        "status": "PASS" if ok else "BROKEN",
        "evidence": evidence_or_unknown(
            [
                f"{file_rel}:{l1}" if l1 else "",
                f"{file_rel}:{l2}" if l2 else "",
                f"{file_rel}:{l3}" if l3 else "",
                "tests/simple/test_paper_lifecycle_tracker.py:80",
            ]
        ),
        "risk": None if ok else "DECISION_TO_PAPER_BROKEN",
        "required_fix": "Lifecycle acilisi sadece allowed_for_paper_lifecycle ile kalmali." if not ok else "None",
    }


def check_paper_to_outcome() -> dict[str, Any]:
    file_rel = "src/simple/outcome_monitor.py"
    l1 = find_literal_line(file_rel, "if lifecycle is None:")
    l2 = find_literal_line(file_rel, 'if lifecycle_status == "NO_LIFECYCLE" or lifecycle_id is None:')
    l3 = find_literal_line(file_rel, 'if result.get("outcome_status") == "CLOSED":')
    ok = all(v is not None for v in (l1, l2, l3))
    return {
        "link": "PAPER_LIFECYCLE->OUTCOME",
        "status": "PASS" if ok else "BROKEN",
        "evidence": evidence_or_unknown(
            [
                f"{file_rel}:{l1}" if l1 else "",
                f"{file_rel}:{l2}" if l2 else "",
                f"{file_rel}:{l3}" if l3 else "",
                "tests/simple/test_outcome_monitor.py:185",
            ]
        ),
        "risk": None if ok else "PAPER_TO_OUTCOME_BROKEN",
        "required_fix": "Outcome sadece lifecycle girdisiyle uretilmeli." if not ok else "None",
    }


def check_outcome_to_edge() -> dict[str, Any]:
    edge_rel = "src/simple/research_edge_matrix_engine.py"
    out_rel = "src/simple/outcome_monitor.py"
    l1 = find_literal_line(edge_rel, 'OUTCOME_EVENTS_PATH = epoch_data_path("outcome_events.jsonl")')
    l2 = find_literal_line(edge_rel, 'and bool(trade.get("closed_only", True))')
    l3 = find_literal_line(edge_rel, '"source": "closed_outcomes_only"')
    l4 = find_literal_line(out_rel, 'LINEAGE_HISTORY_PATH = DATA_DIR / "closed_outcomes_with_lineage.jsonl"')
    producer_for_outcome_events = find_literal_line("src/simple/research_paper_lifecycle_engine.py", "feeds_next=[\"outcome_events\"]")

    outcome_events_keys = last_jsonl_keys("data/simple/epoch_v2/outcome_events.jsonl")
    has_event_data = len(outcome_events_keys) > 0
    ok = all(v is not None for v in (l1, l2, l3)) and has_event_data

    risk = None
    required_fix = "None"
    if not ok:
        risk = "OUTCOME_TO_EDGE_BROKEN"
        required_fix = "Outcome event producer ve outcome_events.jsonl dolulugu canonical hale getirilmeli."

    evidence = evidence_or_unknown(
        [
            f"{edge_rel}:{l1}" if l1 else "",
            f"{edge_rel}:{l2}" if l2 else "",
            f"{edge_rel}:{l3}" if l3 else "",
            f"{out_rel}:{l4}" if l4 else "",
            "data/simple/epoch_v2/outcome_events.jsonl:last_keys=" + (",".join(outcome_events_keys) if outcome_events_keys else "EMPTY"),
            f"src/simple/research_paper_lifecycle_engine.py:{producer_for_outcome_events}" if producer_for_outcome_events else "",
        ]
    )
    return {
        "link": "OUTCOME->EDGE_MATRIX",
        "status": "PASS" if ok else "BROKEN",
        "evidence": evidence,
        "risk": risk,
        "required_fix": required_fix,
    }


def compute_semantic_checks() -> dict[str, Any]:
    lifecycle_rel = "src/simple/paper_lifecycle_tracker.py"
    outcome_rel = "src/simple/outcome_monitor.py"
    edge_rel = "src/simple/research_edge_matrix_engine.py"
    test_outcome_rel = "tests/simple/test_outcome_monitor.py"

    invalidated_in_lifecycle = find_literal_line(lifecycle_rel, 'lifecycle_status = "INVALIDATED"')
    invalidated_in_outcome = find_literal_line(outcome_rel, 'outcome_result = "INVALIDATED"')
    tp2_in_outcome = find_literal_line(outcome_rel, 'outcome_result = "TP2"')
    sl_in_outcome = find_literal_line(outcome_rel, 'outcome_result = "SL"')
    no_outcome_path = find_literal_line(outcome_rel, "NO_LIFECYCLE_PRESENT")
    timeout_test = find_literal_line(test_outcome_rel, 'assert "TIMEOUT" not in ALLOWED_OUTCOME_RESULT')
    edge_closed_filter = find_literal_line(edge_rel, 'and bool(trade.get("closed_only", True))')
    snapshot_fields = find_literal_line(outcome_rel, '"setup_context_snapshot": _setup_snap(setup_context)')

    no_trade_supported = no_outcome_path is not None
    timeout_removed = timeout_test is not None
    invalidated_supported = invalidated_in_lifecycle is not None and invalidated_in_outcome is not None
    tp_sl_supported = tp2_in_outcome is not None and sl_in_outcome is not None
    closed_only_edge_filter = edge_closed_filter is not None
    snapshot_event_separation = closed_only_edge_filter and snapshot_fields is not None

    return {
        "closed_only_edge_filter": {
            "ok": closed_only_edge_filter,
            "evidence": evidence_or_unknown(
                [
                    f"{edge_rel}:{edge_closed_filter}" if edge_closed_filter else "",
                ]
            ),
            "risk": None if closed_only_edge_filter else "EDGE_USES_SNAPSHOT_NOT_CLOSED_OUTCOME",
        },
        "snapshot_event_separation": {
            "ok": snapshot_event_separation,
            "evidence": evidence_or_unknown(
                [
                    f"{outcome_rel}:{snapshot_fields}" if snapshot_fields else "",
                    f"{edge_rel}:{edge_closed_filter}" if edge_closed_filter else "",
                ]
            ),
            "risk": "SNAPSHOT_EVENT_MIXED" if snapshot_fields and not closed_only_edge_filter else None,
        },
        "no_trade_outcome_supported": {
            "ok": no_trade_supported,
            "evidence": evidence_or_unknown(
                [
                    f"{outcome_rel}:{no_outcome_path}" if no_outcome_path else "",
                ]
            ),
            "risk": None if no_trade_supported else "NO_TRADE_NOT_TRACKED",
        },
        "invalidated_outcome_supported": {
            "ok": invalidated_supported,
            "evidence": evidence_or_unknown(
                [
                    f"{lifecycle_rel}:{invalidated_in_lifecycle}" if invalidated_in_lifecycle else "",
                    f"{outcome_rel}:{invalidated_in_outcome}" if invalidated_in_outcome else "",
                ]
            ),
            "risk": None if invalidated_supported else "INVALIDATED_NOT_TRACKED",
        },
        "tp_sl_outcome_supported": {
            "ok": tp_sl_supported,
            "evidence": evidence_or_unknown(
                [
                    f"{outcome_rel}:{tp2_in_outcome}" if tp2_in_outcome else "",
                    f"{outcome_rel}:{sl_in_outcome}" if sl_in_outcome else "",
                ]
            ),
            "risk": None if tp_sl_supported else "PAPER_TO_OUTCOME_BROKEN",
        },
        "timeout_as_primary_result_removed_or_flagged": {
            "ok": timeout_removed,
            "evidence": evidence_or_unknown(
                [
                    f"{test_outcome_rel}:{timeout_test}" if timeout_test else "",
                ]
            ),
            "risk": None if timeout_removed else "TIMEOUT_USED_AS_PRIMARY_RESULT",
        },
    }


def layer_event_file_map() -> list[dict[str, str]]:
    return [
        {"layer": "SETUP", "output_file": "state/simple/latest_setup_candidate.json", "test_file": "tests/simple/test_layer_separation_patch_a.py"},
        {"layer": "SIGNAL", "output_file": "state/simple/epoch_v2/latest_signal_event.json", "test_file": "tests/simple/test_layer_separation_patch_a.py"},
        {"layer": "TRADE_PLAN", "output_file": "state/simple/latest_trade_plan.json", "test_file": "tests/simple/test_trade_plan_engine.py"},
        {"layer": "DECISION", "output_file": "state/simple/latest_decision_gate.json", "test_file": "tests/simple/test_decision_gate_engine.py"},
        {"layer": "PAPER_LIFECYCLE", "output_file": "state/simple/latest_paper_lifecycle.json", "test_file": "tests/simple/test_paper_lifecycle_tracker.py"},
        {"layer": "OUTCOME", "output_file": "state/simple/latest_outcome_monitor.json", "test_file": "tests/simple/test_outcome_monitor.py"},
        {"layer": "EDGE_MATRIX", "output_file": "state/simple/epoch_v2/latest_research_edge_matrix.json", "test_file": "tests/simple/test_layer_separation_patch_a.py"},
    ]


def build_risks(
    id_inventory: list[dict[str, Any]],
    chain: list[dict[str, Any]],
    semantics: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []

    id_to_risk = {
        "setup_id": "SETUP_ID_MISSING",
        "signal_id": "SIGNAL_ID_MISSING",
        "trade_plan_id": "TRADE_PLAN_ID_MISSING",
        "decision_id": "DECISION_ID_MISSING",
        "paper_trade_id": "PAPER_TRADE_ID_MISSING",
        "outcome_id": "OUTCOME_ID_MISSING",
        "edge_event_id": "EDGE_EVENT_ID_MISSING",
    }
    for row in id_inventory:
        code = id_to_risk.get(row["id_field"])
        if code and not row["found"]:
            risks.append(
                {
                    "risk_code": code,
                    "evidence": row["evidence"],
                    "severity": "HIGH" if code in {"OUTCOME_ID_MISSING", "EDGE_EVENT_ID_MISSING"} else "MEDIUM",
                    "next_action": "Field canonical outputa eklenmeli veya naming bridge tanimlanmali.",
                }
            )

    for link in chain:
        if link["status"] == "BROKEN" and link["risk"]:
            risks.append(
                {
                    "risk_code": link["risk"],
                    "evidence": link["evidence"],
                    "severity": "HIGH" if link["risk"] in {"OUTCOME_TO_EDGE_BROKEN", "DECISION_TO_PAPER_BROKEN"} else "MEDIUM",
                    "next_action": link["required_fix"],
                }
            )

    for key in (
        "closed_only_edge_filter",
        "snapshot_event_separation",
        "no_trade_outcome_supported",
        "invalidated_outcome_supported",
        "tp_sl_outcome_supported",
        "timeout_as_primary_result_removed_or_flagged",
    ):
        item = semantics[key]
        if not item["ok"] and item["risk"]:
            risks.append(
                {
                    "risk_code": item["risk"],
                    "evidence": item["evidence"],
                    "severity": "MEDIUM",
                    "next_action": "Contract check eklenmeli.",
                }
            )
    return risks


def status_from_bool(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def chain_status(chain: list[dict[str, Any]]) -> str:
    failed = sum(1 for item in chain if item["status"] == "BROKEN")
    if failed == 0:
        return "PASS"
    if failed <= 2:
        return "PARTIAL"
    return "FAIL"


def outcome_status(semantics: dict[str, Any]) -> str:
    core = [
        semantics["no_trade_outcome_supported"]["ok"],
        semantics["invalidated_outcome_supported"]["ok"],
        semantics["tp_sl_outcome_supported"]["ok"],
        semantics["timeout_as_primary_result_removed_or_flagged"]["ok"],
    ]
    if all(core):
        return "PASS"
    if any(core):
        return "PARTIAL"
    return "FAIL"


def edge_status(chain: list[dict[str, Any]], semantics: dict[str, Any]) -> str:
    out_edge = next((item for item in chain if item["link"] == "OUTCOME->EDGE_MATRIX"), None)
    out_edge_ok = bool(out_edge and out_edge["status"] == "PASS")
    closed_ok = semantics["closed_only_edge_filter"]["ok"]
    if out_edge_ok and closed_ok:
        return "PASS"
    if out_edge_ok or closed_ok:
        return "PARTIAL"
    return "FAIL"


def recommendation(lineage_stat: str) -> str:
    if lineage_stat == "FAIL":
        return "Prompt 8 = LOCAL LINEAGE NORMALIZATION PATCH PLAN"
    if lineage_stat == "PARTIAL":
        return "Prompt 8 = VPS LINEAGE + PAPER OUTCOME AUDIT"
    return "Prompt 8 = VPS PAPER OUTCOME REALITY AUDIT"


def build_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# LOCAL LINEAGE + PAPER OUTCOME AUDIT REPORT")
    lines.append("")
    lines.append("## 1. Net Hüküm")
    lines.append(f"Lineage status: {payload['summary']['lineage_status']}")
    lines.append("")
    lines.append(f"Paper outcome status: {payload['summary']['paper_outcome_status']}")
    lines.append("")
    lines.append(f"Edge cleanliness: {payload['summary']['edge_cleanliness']}")
    lines.append("")
    lines.append("## 2. ID Field Inventory")
    lines.append("ID Field | Found? | Producer | Consumer | Evidence")
    for row in payload["id_field_inventory"]:
        lines.append(
            f"{row['id_field']} | {row['found']} | {row['producer']} | {row['consumer']} | {row['evidence']}"
        )
    lines.append("")
    lines.append("## 3. Parent-Child Chain")
    lines.append("Link | Status | Evidence | Risk | Required Fix")
    for row in payload["parent_child_chain"]:
        lines.append(
            f"{row['link']} | {row['status']} | {row['evidence']} | {row['risk'] or '-'} | {row['required_fix']}"
        )
    lines.append("")
    lines.append("## 4. Outcome Semantics")
    lines.append("Outcome Type | Supported? | Evidence | Risk")
    sem = payload["outcome_semantics"]
    rows = [
        ("NO_TRADE/NO_OUTCOME", sem["no_trade_outcome_supported"]),
        ("INVALIDATED", sem["invalidated_outcome_supported"]),
        ("TP/SL", sem["tp_sl_outcome_supported"]),
        ("TIMEOUT primary removed", sem["timeout_as_primary_result_removed_or_flagged"]),
    ]
    for name, item in rows:
        lines.append(
            f"{name} | {item['ok']} | {item['evidence']} | {item['risk'] or '-'}"
        )
    lines.append("")
    lines.append("## 5. Edge Input Cleanliness")
    lines.append("Edge Source | Closed Only? | Snapshot Risk | Evidence | Status")
    edge = payload["edge_input_cleanliness"]
    lines.append(
        f"{edge['edge_source']} | {edge['closed_only']} | {edge['snapshot_risk']} | {edge['evidence']} | {edge['status']}"
    )
    lines.append("")
    lines.append("## 6. Broken Lineage Risks")
    lines.append("Risk Code | Evidence | Severity | Next Action")
    if payload["broken_lineage_risks"]:
        for risk in payload["broken_lineage_risks"]:
            lines.append(
                f"{risk['risk_code']} | {risk['evidence']} | {risk['severity']} | {risk['next_action']}"
            )
    else:
        lines.append("NONE | KANITLANAMADI | LOW | KANITLANAMADI")
    lines.append("")
    lines.append("## 7. Prompt 8 Recommendation")
    lines.append(payload["prompt_8_recommendation"])
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    id_inventory = scan_id_inventory()
    chain = [
        check_setup_to_signal(),
        check_signal_to_plan(),
        check_plan_to_decision(),
        check_decision_to_paper(),
        check_paper_to_outcome(),
        check_outcome_to_edge(),
    ]
    semantics = compute_semantic_checks()
    risks = build_risks(id_inventory, chain, semantics)

    lineage_stat = chain_status(chain)
    paper_stat = outcome_status(semantics)
    edge_stat = edge_status(chain, semantics)
    prompt8 = recommendation(lineage_stat)

    payload = {
        "generated_at_utc": now_utc(),
        "summary": {
            "lineage_status": lineage_stat,
            "paper_outcome_status": paper_stat,
            "edge_cleanliness": edge_stat,
        },
        "lineage_checks": {
            "setup_id_detected": any(x["id_field"] == "setup_id" and x["found"] for x in id_inventory),
            "signal_id_detected": any(x["id_field"] == "signal_id" and x["found"] for x in id_inventory),
            "trade_plan_id_detected": any(x["id_field"] in {"trade_plan_id", "plan_id"} and x["found"] for x in id_inventory),
            "decision_id_detected": any(x["id_field"] == "decision_id" and x["found"] for x in id_inventory),
            "paper_trade_id_detected": any(x["id_field"] == "paper_trade_id" and x["found"] for x in id_inventory),
            "outcome_id_detected": any(x["id_field"] == "outcome_id" and x["found"] for x in id_inventory),
            "edge_event_id_detected": any(x["id_field"] == "edge_event_id" and x["found"] for x in id_inventory),
            "setup_to_signal_link": chain[0]["status"] == "PASS",
            "signal_to_trade_plan_link": chain[1]["status"] == "PASS",
            "trade_plan_to_decision_link": chain[2]["status"] == "PASS",
            "decision_to_paper_link": chain[3]["status"] == "PASS",
            "paper_to_outcome_link": chain[4]["status"] == "PASS",
            "outcome_to_edge_link": chain[5]["status"] == "PASS",
            "closed_only_edge_filter": semantics["closed_only_edge_filter"]["ok"],
            "snapshot_event_separation": semantics["snapshot_event_separation"]["ok"],
            "no_trade_outcome_supported": semantics["no_trade_outcome_supported"]["ok"],
            "invalidated_outcome_supported": semantics["invalidated_outcome_supported"]["ok"],
            "tp_sl_outcome_supported": semantics["tp_sl_outcome_supported"]["ok"],
            "timeout_as_primary_result_removed_or_flagged": semantics["timeout_as_primary_result_removed_or_flagged"]["ok"],
            "lineage_report_exists": file_exists("reports/local_lineage_outcome_audit_report.md"),
        },
        "id_field_inventory": id_inventory,
        "parent_child_chain": chain,
        "layer_outputs": layer_event_file_map(),
        "state_key_inventory": {
            "setup_state_keys": read_json_keys("state/simple/latest_setup_candidate.json"),
            "signal_state_keys": read_json_keys("state/simple/epoch_v2/latest_signal_event.json"),
            "trade_plan_state_keys": read_json_keys("state/simple/latest_trade_plan.json"),
            "decision_state_keys": read_json_keys("state/simple/latest_decision_gate.json"),
            "paper_state_keys": read_json_keys("state/simple/latest_paper_lifecycle.json"),
            "outcome_state_keys": read_json_keys("state/simple/latest_outcome_monitor.json"),
            "edge_state_keys": read_json_keys("state/simple/epoch_v2/latest_research_edge_matrix.json"),
        },
        "event_lineage_keys": {
            "signal_events_clean_last_keys": last_jsonl_keys("data/simple/epoch_v2/signal_events_clean.jsonl"),
            "trade_plan_events_last_keys": last_jsonl_keys("data/simple/epoch_v2/trade_plan_events.jsonl"),
            "decision_events_last_keys": last_jsonl_keys("data/simple/epoch_v2/decision_events.jsonl"),
            "paper_close_events_last_keys": last_jsonl_keys("data/simple/epoch_v2/paper_trade_close_events.jsonl"),
            "outcome_events_last_keys": last_jsonl_keys("data/simple/epoch_v2/outcome_events.jsonl"),
            "edge_events_last_keys": last_jsonl_keys("data/simple/epoch_v2/edge_events.jsonl"),
        },
        "outcome_semantics": semantics,
        "edge_input_cleanliness": {
            "edge_source": "data/simple/epoch_v2/outcome_events.jsonl",
            "closed_only": semantics["closed_only_edge_filter"]["ok"],
            "snapshot_risk": "MEDIUM" if semantics["snapshot_event_separation"]["ok"] else "HIGH",
            "evidence": evidence_or_unknown(
                [
                    semantics["closed_only_edge_filter"]["evidence"],
                    semantics["snapshot_event_separation"]["evidence"],
                ]
            ),
            "status": edge_stat,
        },
        "broken_lineage_risks": risks,
        "prompt_8_recommendation": prompt8,
    }
    return payload


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = run()
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(build_markdown(payload), encoding="utf-8")
    P8_OUT.write_text(payload["prompt_8_recommendation"] + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "json": str(JSON_OUT), "report": str(MD_OUT), "recommendation": str(P8_OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
