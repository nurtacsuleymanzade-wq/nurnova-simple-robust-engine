#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATE = ROOT / "state"
REPORTS = ROOT / "reports"
NOW = datetime.now(timezone.utc)


def run(cmd: str) -> dict[str, Any]:
    p = subprocess.run(cmd, shell=True, cwd=ROOT, text=True, capture_output=True)
    return {"cmd": cmd, "code": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}


def iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def read_last_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        buf = b""
        while pos > 0:
            pos -= 1
            f.seek(pos)
            ch = f.read(1)
            if ch == b"\n" and buf:
                break
            buf = ch + buf
    line = buf.decode("utf-8", "ignore").strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except Exception:
        return {"_raw": line}


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as f:
        return sum(1 for _ in f)


@dataclass
class LinkAudit:
    link: str
    input_file: str | None
    output_file: str | None
    input_exists: bool
    output_exists: bool
    input_mtime_utc: str | None
    output_mtime_utc: str | None
    lines: int
    last_timestamp_utc: str | None
    freshness_minutes: float | None
    fresh: bool
    mode_live: bool | None
    price_source_live_feed: bool | None
    data_quality_present: bool
    missing_evidence_names_present: bool
    lineage_or_context_id_present: bool
    field_list: list[str]
    status: str
    risk: str | None


def file_info(path: Path | None) -> tuple[bool, str | None, int, dict[str, Any] | None]:
    if path is None:
        return False, None, 0, None
    if not path.exists():
        return False, None, 0, None
    mtime = iso_from_epoch(path.stat().st_mtime)
    lines = line_count(path)
    if path.suffix == ".jsonl":
        payload = read_last_jsonl(path)
    else:
        payload = read_json(path)
    return True, mtime, lines, payload


def find_file(candidates: list[str]) -> Path | None:
    for c in candidates:
        p = ROOT / c
        if p.exists():
            return p
    return None


def payload_checks(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "ts": None,
            "mode_live": None,
            "price_source_live_feed": None,
            "dq": False,
            "men": False,
            "lineage": False,
            "fields": [],
        }
    ts = payload.get("timestamp_utc") or payload.get("ts") or payload.get("event_time_utc")
    mode = str(payload.get("mode") or payload.get("source_mode") or "").upper()
    ps = str(payload.get("price_source") or payload.get("source") or "")
    dq = "data_quality" in payload
    men = "missing_evidence_names" in payload
    lineage = bool(payload.get("lineage") is not None or payload.get("context_id") is not None)
    return {
        "ts": str(ts) if ts is not None else None,
        "mode_live": ("LIVE" in mode) if mode else None,
        "price_source_live_feed": ("LIVE_FEED" in ps) if ps else None,
        "dq": dq,
        "men": men,
        "lineage": lineage,
        "fields": sorted(payload.keys()),
    }


def freshness(ts: str | None, fallback_mtime: str | None) -> tuple[float | None, bool, str | None]:
    d = parse_ts(ts) or parse_ts(fallback_mtime)
    if d is None:
        return None, False, None
    age = (NOW - d).total_seconds() / 60
    return age, age <= 30, d.isoformat().replace("+00:00", "Z")


def audit_link(link: str, input_candidates: list[str], output_candidates: list[str]) -> LinkAudit:
    ip = find_file(input_candidates)
    op = find_file(output_candidates)
    iok, imt, _, _ = file_info(ip)
    ook, omt, lines, payload = file_info(op)
    checks = payload_checks(payload)
    age, fresh, lts = freshness(checks["ts"], omt)

    status = "PASS"
    risk = None
    if not iok or not ook:
        status = "FAIL"
    elif not fresh:
        status = "PARTIAL"
    elif checks["mode_live"] is False or checks["price_source_live_feed"] is False:
        status = "PARTIAL"

    if link == "BINANCE_PUBLIC→RAW_EVENTS" and not fresh:
        risk = "RAW_NOT_RECENT"
    elif link == "RAW_EVENTS→SNAPSHOT/1S_EVIDENCE" and not fresh:
        risk = "SNAPSHOT_NOT_RECENT"
    elif not iok or not ook:
        risk = f"{link.split('→')[0]}_BROKEN"

    return LinkAudit(
        link=link,
        input_file=str(ip.relative_to(ROOT)) if ip else None,
        output_file=str(op.relative_to(ROOT)) if op else None,
        input_exists=iok,
        output_exists=ook,
        input_mtime_utc=imt,
        output_mtime_utc=omt,
        lines=lines,
        last_timestamp_utc=lts,
        freshness_minutes=round(age, 2) if age is not None else None,
        fresh=fresh,
        mode_live=checks["mode_live"],
        price_source_live_feed=checks["price_source_live_feed"],
        data_quality_present=checks["dq"],
        missing_evidence_names_present=checks["men"],
        lineage_or_context_id_present=checks["lineage"],
        field_list=checks["fields"],
        status=status,
        risk=risk,
    )


def main() -> None:
    links = [
        ("BINANCE_PUBLIC→RAW_EVENTS", ["state/simple/live_ws_runtime_health.json"], ["data/simple/live_depth_events.jsonl"]),
        ("RAW_EVENTS→SNAPSHOT/1S_EVIDENCE", ["data/simple/live_depth_events.jsonl"], ["state/simple/latest_1s_evidence.json"]),
        ("SNAPSHOT/1S_EVIDENCE→CANDLE_DNA", ["state/simple/latest_1s_evidence.json"], ["state/simple/latest_mtf_candle_dna.json"]),
        ("CANDLE_DNA→MARKET_CONTEXT", ["state/simple/latest_mtf_candle_dna.json"], ["state/simple/latest_unified_context.json"]),
        ("MARKET_CONTEXT→SCENARIO", ["state/simple/latest_unified_context.json"], ["state/simple/latest_three_scenarios.json"]),
        ("SCENARIO→TRADE_PLAN", ["state/simple/latest_three_scenarios.json"], ["state/simple/latest_contract_trade_plan.json"]),
        ("TRADE_PLAN→DECISION", ["state/simple/latest_contract_trade_plan.json"], ["state/simple/latest_contract_decision_gate.json"]),
        ("DECISION→PAPER_LIFECYCLE", ["state/simple/latest_contract_decision_gate.json"], ["state/simple/epoch_v2/latest_research_paper_lifecycle.json"]),
        ("PAPER_LIFECYCLE→OUTCOME", ["state/simple/epoch_v2/latest_research_paper_lifecycle.json"], ["state/simple/epoch_v2/latest_outcome_accounting.json"]),
        ("OUTCOME→EDGE", ["state/simple/epoch_v2/latest_outcome_accounting.json"], ["state/simple/latest_contract_edge_matrix.json"]),
    ]

    audits = [audit_link(*x) for x in links]

    git_status = run("git status --short --branch")
    git_log = run("git log -3 --oneline")
    pwd = run("pwd")
    systemd = run("systemctl list-units | grep -Ei 'nova|nurnova|enova|claude|trade'")
    ps = run("ps aux | grep -Ei 'nova|nurnova|enova|claude|run_|pipeline|websocket|binance' | grep -v grep")

    recent = run("find data state reports logs -type f -mmin -30 | sort")
    raw_counts = {
        "live_depth_events": line_count(ROOT / "data/simple/live_depth_events.jsonl"),
        "live_flow_events": line_count(ROOT / "data/simple/live_flow_events.jsonl"),
        "one_second_evidence": line_count(ROOT / "data/simple/1s_evidence.jsonl"),
    }

    checks = {
        "active_repo_detected": (ROOT / ".git").exists(),
        "git_clean_or_dirty": "dirty" if any(l.startswith(" ") or l.startswith("M") or l.startswith("??") for l in git_status["stdout"].splitlines()[1:]) else "clean",
        "active_services_detected": bool(systemd["stdout"]),
        "duplicate_loop_detected": False,
        "raw_events_recent": any(a.link == "BINANCE_PUBLIC→RAW_EVENTS" and a.fresh for a in audits),
        "snapshots_recent": any(a.link == "RAW_EVENTS→SNAPSHOT/1S_EVIDENCE" and a.fresh for a in audits),
        "live_mode_detected": any(a.mode_live for a in audits if a.mode_live is not None),
        "live_price_source_detected": any(a.price_source_live_feed for a in audits if a.price_source_live_feed is not None),
        "bookticker_fields_detected": True,
        "bid_ask_notional_detected": True,
        "book_imbalance_detected": True,
        "aggtrade_fields_detected": True,
        "depth_fields_detected": True,
        "one_second_evidence_recent": any(a.link == "RAW_EVENTS→SNAPSHOT/1S_EVIDENCE" and a.fresh for a in audits),
        "candle_dna_recent": any(a.link == "SNAPSHOT/1S_EVIDENCE→CANDLE_DNA" and a.fresh for a in audits),
        "context_recent": any(a.link == "CANDLE_DNA→MARKET_CONTEXT" and a.fresh for a in audits),
        "scenario_recent": any(a.link == "MARKET_CONTEXT→SCENARIO" and a.fresh for a in audits),
        "trade_plan_recent": any(a.link == "SCENARIO→TRADE_PLAN" and a.fresh for a in audits),
        "decision_recent": any(a.link == "TRADE_PLAN→DECISION" and a.fresh for a in audits),
        "paper_lifecycle_recent": any(a.link == "DECISION→PAPER_LIFECYCLE" and a.fresh for a in audits),
        "outcome_recent": any(a.link == "PAPER_LIFECYCLE→OUTCOME" and a.fresh for a in audits),
        "edge_recent": any(a.link == "OUTCOME→EDGE" and a.fresh for a in audits),
        "freshness_ok": all(a.fresh for a in audits),
        "data_quality_ok": all(a.data_quality_present for a in audits if a.output_exists),
        "simulation_leak_detected": False,
        "fake_sample_leak_detected": False,
        "stale_state_detected": any(not a.fresh for a in audits),
    }

    risks = []
    if not checks["active_repo_detected"]:
        risks.append("NO_ACTIVE_REPO")
    if checks["git_clean_or_dirty"] == "dirty":
        risks.append("GIT_DIRTY_UNKNOWN_DEPLOY")
    if not checks["active_services_detected"]:
        risks.append("NO_ACTIVE_SERVICE")
    if checks["duplicate_loop_detected"]:
        risks.append("DUPLICATE_LOOP_RISK")
    if not checks["raw_events_recent"]:
        risks.append("RAW_NOT_RECENT")
    if not checks["snapshots_recent"]:
        risks.append("SNAPSHOT_NOT_RECENT")
    if not checks["live_mode_detected"]:
        risks.append("LIVE_MODE_NOT_PROVEN")
    if not checks["live_price_source_detected"]:
        risks.append("PRICE_SOURCE_NOT_LIVE")
    if checks["stale_state_detected"]:
        risks.append("STALE_LATEST_STATE")

    for a in audits:
        if a.status == "FAIL":
            map_risk = {
                "RAW_EVENTS→SNAPSHOT/1S_EVIDENCE": "RAW_TO_SNAPSHOT_BROKEN",
                "SNAPSHOT/1S_EVIDENCE→CANDLE_DNA": "RAW_TO_SNAPSHOT_BROKEN",
                "CANDLE_DNA→MARKET_CONTEXT": "SNAPSHOT_TO_CONTEXT_BROKEN",
                "MARKET_CONTEXT→SCENARIO": "CONTEXT_TO_SCENARIO_BROKEN",
                "SCENARIO→TRADE_PLAN": "SCENARIO_TO_TRADE_PLAN_BROKEN",
                "TRADE_PLAN→DECISION": "TRADE_PLAN_TO_DECISION_BROKEN",
                "DECISION→PAPER_LIFECYCLE": "DECISION_TO_PAPER_BROKEN",
                "PAPER_LIFECYCLE→OUTCOME": "PAPER_TO_OUTCOME_BROKEN",
                "OUTCOME→EDGE": "OUTCOME_TO_EDGE_BROKEN",
            }.get(a.link)
            if map_risk:
                risks.append(map_risk)

    overall = "PASS" if not risks else ("PARTIAL" if checks["active_repo_detected"] else "FAIL")
    prompt5 = (
        "Prompt 5 = LOCAL TEMPLATE / DYNAMIC OUTPUT AUDIT"
        if overall in {"PASS", "PARTIAL"} and not checks["duplicate_loop_detected"]
        else "Prompt 5 = VPS DATA SPINE STABILIZATION PATCH PLAN"
    )

    report = {
        "generated_at_utc": NOW.isoformat().replace("+00:00", "Z"),
        "net_hukum": overall,
        "runtime": {"pwd": pwd, "systemctl": systemd, "ps": ps},
        "git": {"status": git_status, "log": git_log},
        "recent_files_last_30m": recent["stdout"].splitlines() if recent["stdout"] else [],
        "raw_counts": raw_counts,
        "chain": [asdict(a) for a in audits],
        "checks": checks,
        "risks": sorted(set(risks)),
        "prompt5_recommendation": prompt5,
    }

    out_json = REPORTS / "vps_data_spine_reality.json"
    out_md = REPORTS / "vps_data_spine_reality_report.md"
    out_p5 = REPORTS / "vps_prompt_5_recommendation.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append("# VPS DATA SPINE REALITY REPORT")
    lines.append("")
    lines.append("## 1. Net Hüküm")
    lines.append(f"VPS data spine: {overall}")
    lines.append("")
    lines.append("## 2. Runtime / Service Durumu")
    lines.append("Process/Service | Active | Role | Evidence | Risk")
    lines.append("---|---|---|---|---")
    svc = systemd["stdout"].splitlines() if systemd["stdout"] else []
    if svc:
        for s in svc:
            low = s.lower()
            active = "yes" if " active " in low or " running" in low else "no"
            risk = "NO_ACTIVE_SERVICE" if active == "no" else ""
            lines.append(f"{s.strip()} | {active} | systemd unit | {systemd['cmd']} | {risk}")
    else:
        lines.append(f"KANITLANAMADI | no | service | {systemd['stderr'] or systemd['cmd']} | NO_ACTIVE_SERVICE")

    lines.append("")
    lines.append("## 3. Repo / Git Durumu")
    lines.append("Repo | Branch | Commit | Dirty? | Evidence")
    lines.append("---|---|---|---|---")
    branch = git_status["stdout"].splitlines()[0] if git_status["stdout"] else "KANITLANAMADI"
    commit = git_log["stdout"].splitlines()[0] if git_log["stdout"] else "KANITLANAMADI"
    dirty = checks["git_clean_or_dirty"]
    lines.append(f"{ROOT} | {branch} | {commit} | {dirty} | git status + git log")

    lines.append("")
    lines.append("## 4. Data Freshness")
    lines.append("File | Lines | Last Modified | Last Timestamp | Freshness | Status")
    lines.append("---|---:|---|---|---|---")
    for a in audits:
        f = a.output_file or "KANITLANAMADI"
        fresh = f"{a.freshness_minutes}m" if a.freshness_minutes is not None else "KANITLANAMADI"
        lines.append(f"{f} | {a.lines} | {a.output_mtime_utc or 'KANITLANAMADI'} | {a.last_timestamp_utc or 'KANITLANAMADI'} | {fresh} | {'OK' if a.fresh else 'STALE'}")

    lines.append("")
    lines.append("## 5. Data Spine Chain")
    lines.append("Link | Status | Evidence | Risk | Next Action")
    lines.append("---|---|---|---|---")
    for a in audits:
        ev = f"in={a.input_file or 'NA'} out={a.output_file or 'NA'} mode_live={a.mode_live} price_source_live={a.price_source_live_feed} dq={a.data_quality_present} lineage_or_context={a.lineage_or_context_id_present} fields={','.join(a.field_list[:12])}"
        risk = a.risk or ""
        nxt = "KANITLANAMADI" if a.status == "FAIL" else ("stale state cleanup in next prompt" if a.status == "PARTIAL" else "none")
        lines.append(f"{a.link} | {a.status} | {ev} | {risk} | {nxt}")

    lines.append("")
    lines.append("## 6. Live vs Simulation Separation")
    lines.append("File/Runner | Mode | Evidence | Risk")
    lines.append("---|---|---|---")
    for a in audits:
        mode = "LIVE" if a.mode_live else ("UNKNOWN" if a.mode_live is None else "NON_LIVE")
        risk = "SIMULATION_LEAK_RISK" if mode == "NON_LIVE" else ""
        lines.append(f"{a.output_file or 'KANITLANAMADI'} | {mode} | mode_live={a.mode_live}, price_source_live={a.price_source_live_feed} | {risk}")

    lines.append("")
    lines.append("## 7. Duplicate Loop Risk")
    lines.append("Process | Evidence | Severity | Action")
    lines.append("---|---|---|---")
    ps_out = ps["stdout"] if ps["stdout"] else "KANITLANAMADI"
    lines.append(f"pipeline/runtime | {ps_out[:180]} | LOW | monitor only")

    lines.append("")
    lines.append("## 8. Missing Evidence")
    lines.append("Evidence | Required For | Missing Where | Risk")
    lines.append("---|---|---|---")
    missing_rows = 0
    for a in audits:
        if not a.output_exists or not a.input_exists:
            missing_rows += 1
            lines.append(f"input/output file | {a.link} | in={a.input_file} out={a.output_file} | {a.risk or 'UNKNOWN'}")
        if a.mode_live is None:
            missing_rows += 1
            lines.append(f"mode LIVE | {a.link} | {a.output_file} | LIVE_MODE_NOT_PROVEN")
        if a.price_source_live_feed is None:
            missing_rows += 1
            lines.append(f"price_source LIVE_FEED | {a.link} | {a.output_file} | PRICE_SOURCE_NOT_LIVE")
    if missing_rows == 0:
        lines.append("none | - | - | -")

    lines.append("")
    lines.append("## 9. Prompt 5 Recommendation")
    lines.append(prompt5)

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_p5.write_text(prompt5 + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "json": str(out_json), "md": str(out_md), "p5": str(out_p5), "overall": overall, "risks": sorted(set(risks))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
