#!/usr/bin/env python3
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "reports" / "vps_market_state_scenario_audit.json"
OUT_MD = ROOT / "reports" / "vps_market_state_scenario_audit_report.md"
OUT_REC = ROOT / "reports" / "vps_prompt_11_recommendation.md"

MARKET_FIELDS = [
    "trend",
    "regime",
    "volatility_state",
    "alignment",
    "liquidity_state",
    "auction_state",
    "state_confidence",
    "reason_codes",
    "data_quality",
]
SCENARIO_FIELDS = [
    "possible_scenarios",
    "bullish_scenario",
    "bearish_scenario",
    "neutral_scenario",
    "neutral_range_scenario",
    "active_scenario",
    "selected_scenario",
    "dominant_scenario",
    "scenario_confidence",
    "selection_reason_codes",
    "market_state_id",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def parse_ts(ts: Any) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def walk_values(obj: Any, key: str) -> list[Any]:
    values: list[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                values.append(v)
            values.extend(walk_values(v, key))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(walk_values(item, key))
    return values


def to_string_value(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, dict):
        for k in ["regime", "trend", "state", "label", "name", "value", "type"]:
            x = v.get(k)
            if isinstance(x, (str, int, float, bool)):
                return str(x)
    return None


def latest_timestamp(rows: list[dict[str, Any]]) -> str | None:
    for r in reversed(rows):
        ts = r.get("timestamp_utc") or r.get("timestamp")
        if ts:
            return ts
    return None


def dist_from_field(rows: list[dict[str, Any]], field: str) -> Counter:
    c = Counter()
    for r in rows:
        vals = walk_values(r, field)
        for v in vals:
            s = to_string_value(v)
            if s:
                c[s] += 1
    return c


def presence_and_unique(rows: list[dict[str, Any]], field: str) -> tuple[int, int]:
    present_rows = 0
    uniq: set[str] = set()
    for r in rows:
        vals = walk_values(r, field)
        if vals:
            present_rows += 1
        for v in vals:
            if isinstance(v, dict):
                sid = v.get("scenario_id")
                if isinstance(sid, str) and sid:
                    uniq.add(sid)
                    continue
            s = to_string_value(v)
            if s:
                uniq.add(s)
            elif isinstance(v, (dict, list)):
                try:
                    uniq.add(json.dumps(v, sort_keys=True, ensure_ascii=False))
                except Exception:
                    pass
    return present_rows, len(uniq)


def main() -> None:
    now = datetime.now(timezone.utc)
    market_path = ROOT / "data/simple/unified_context_history.jsonl"
    scenario_path = ROOT / "data/simple/three_scenarios_history.jsonl"
    setup_path = ROOT / "data/simple/epoch_v2/setup_contract_history.jsonl"

    market_rows = load_jsonl(market_path)
    scenario_rows = load_jsonl(scenario_path)
    setup_rows = load_jsonl(setup_path)

    market_latest = latest_timestamp(market_rows)
    scenario_latest = latest_timestamp(scenario_rows)
    setup_latest = latest_timestamp(setup_rows)

    market_field_stats: dict[str, Any] = {}
    for f in MARKET_FIELDS:
        d = dist_from_field(market_rows, f)
        present_rows, uniq_count = presence_and_unique(market_rows, f)
        found = present_rows > 0
        market_field_stats[f] = {
            "found": found,
            "present_rows": present_rows,
            "unique_values": uniq_count,
            "distribution_top": d.most_common(10),
            "latest_timestamp": market_latest,
            "source_file": str(market_path.relative_to(ROOT)),
        }

    scenario_field_stats: dict[str, Any] = {}
    for f in SCENARIO_FIELDS:
        d = dist_from_field(scenario_rows, f)
        present_rows, uniq_count = presence_and_unique(scenario_rows, f)
        found = present_rows > 0
        scenario_field_stats[f] = {
            "found": found,
            "present_rows": present_rows,
            "unique_values": uniq_count,
            "distribution_top": d.most_common(10),
            "latest_timestamp": scenario_latest,
            "source_file": str(scenario_path.relative_to(ROOT)),
        }

    active_values = dist_from_field(scenario_rows, "active_scenario")
    selected_values = dist_from_field(scenario_rows, "selected_scenario")
    dominant_values = dist_from_field(scenario_rows, "dominant_scenario")
    scenario_conf_values = dist_from_field(scenario_rows, "scenario_confidence")

    active_record_count = 0
    branch_only_count = 0
    for r in scenario_rows:
        has_active = bool(walk_values(r, "active_scenario") or walk_values(r, "selected_scenario") or walk_values(r, "dominant_scenario"))
        has_branch = all(k in r for k in ["bullish_scenario", "bearish_scenario"]) and ("neutral_scenario" in r or "neutral_range_scenario" in r)
        if has_active:
            active_record_count += 1
        if has_branch and not has_active:
            branch_only_count += 1

    market_context_ids = {r.get("context_id") for r in market_rows if isinstance(r.get("context_id"), str)}
    scenario_context_ids = {r.get("context_id") for r in scenario_rows if isinstance(r.get("context_id"), str)}
    setup_context_ids = {r.get("context_id") for r in setup_rows if isinstance(r.get("context_id"), str)}
    market_to_scenario = market_context_ids & scenario_context_ids
    scenario_to_setup = scenario_context_ids & setup_context_ids
    if len(market_to_scenario) == 0:
        market_loop_ids = {r.get("loop_id") for r in market_rows if isinstance(r.get("loop_id"), int)}
        scenario_loop_ids = {r.get("loop_id") for r in scenario_rows if isinstance(r.get("loop_id"), int)}
        market_to_scenario = {str(x) for x in (market_loop_ids & scenario_loop_ids)}
    if len(scenario_to_setup) == 0:
        scenario_loop_ids = {r.get("loop_id") for r in scenario_rows if isinstance(r.get("loop_id"), int)}
        setup_loop_ids = {r.get("loop_id") for r in setup_rows if isinstance(r.get("loop_id"), int)}
        scenario_to_setup = {str(x) for x in (scenario_loop_ids & setup_loop_ids)}

    checks = {
        "market_state_records_found": len(market_rows),
        "trend_found_in_output": market_field_stats["trend"]["found"],
        "regime_found_in_output": market_field_stats["regime"]["found"],
        "volatility_state_found_in_output": market_field_stats["volatility_state"]["found"],
        "alignment_found_in_output": market_field_stats["alignment"]["found"],
        "liquidity_state_found_in_output": market_field_stats["liquidity_state"]["found"],
        "auction_state_found_in_output": market_field_stats["auction_state"]["found"],
        "state_confidence_found": market_field_stats["state_confidence"]["found"],
        "scenario_records_found": len(scenario_rows),
        "possible_scenarios_found": scenario_field_stats["possible_scenarios"]["found"],
        "active_scenario_found": active_record_count > 0,
        "branch_only_scenario_detected": branch_only_count > 0,
        "scenario_confidence_found": len(scenario_conf_values) > 0,
        "selection_reason_codes_found": scenario_field_stats["selection_reason_codes"]["found"],
        "market_state_to_scenario_traceable": len(market_to_scenario) > 0,
        "scenario_to_setup_traceable": len(scenario_to_setup) > 0,
        "context_aware_scenario_possible": len(market_to_scenario) > 0 and len(scenario_to_setup) > 0,
        "context_unaware_scenario_risk": active_record_count == 0 and branch_only_count > 0,
    }

    risk_codes: set[str] = set()
    if len(market_rows) == 0:
        risk_codes.add("NO_MARKET_STATE_RECORDS")
    if not checks["trend_found_in_output"]:
        risk_codes.add("TREND_NOT_IN_OUTPUT")
    if not checks["regime_found_in_output"]:
        risk_codes.add("REGIME_NOT_IN_OUTPUT")
    if not checks["volatility_state_found_in_output"]:
        risk_codes.add("VOLATILITY_NOT_IN_OUTPUT")
    if not checks["alignment_found_in_output"]:
        risk_codes.add("ALIGNMENT_NOT_IN_OUTPUT")
    if not checks["liquidity_state_found_in_output"]:
        risk_codes.add("LIQUIDITY_STATE_NOT_IN_OUTPUT")
    if not checks["auction_state_found_in_output"]:
        risk_codes.add("AUCTION_STATE_NOT_IN_OUTPUT")
    if len(scenario_rows) == 0:
        risk_codes.add("NO_SCENARIO_RECORDS")
    if not checks["active_scenario_found"]:
        risk_codes.add("ACTIVE_SCENARIO_MISSING_IN_VPS_OUTPUT")
    if checks["branch_only_scenario_detected"]:
        risk_codes.add("BRANCH_ONLY_SCENARIO_RISK")
    if not checks["scenario_confidence_found"]:
        risk_codes.add("SCENARIO_CONFIDENCE_MISSING")
    if not checks["market_state_to_scenario_traceable"]:
        risk_codes.add("MARKET_STATE_NOT_LINKED_TO_SCENARIO")
    if not checks["scenario_to_setup_traceable"]:
        risk_codes.add("SCENARIO_NOT_LINKED_TO_SETUP")
    if checks["context_unaware_scenario_risk"]:
        risk_codes.add("CONTEXT_UNAWARE_EDGE_RISK")
    if len(market_rows) < 100 or len(scenario_rows) < 100:
        risk_codes.add("LOW_SAMPLE_SIZE")

    market_status = "PASS"
    if any(rc in risk_codes for rc in ["NO_MARKET_STATE_RECORDS"]):
        market_status = "FAIL"
    elif any(rc in risk_codes for rc in ["TREND_NOT_IN_OUTPUT", "REGIME_NOT_IN_OUTPUT", "VOLATILITY_NOT_IN_OUTPUT", "ALIGNMENT_NOT_IN_OUTPUT", "LIQUIDITY_STATE_NOT_IN_OUTPUT", "AUCTION_STATE_NOT_IN_OUTPUT"]):
        market_status = "PARTIAL"

    active_status = "PASS"
    if any(rc in risk_codes for rc in ["NO_SCENARIO_RECORDS", "ACTIVE_SCENARIO_MISSING_IN_VPS_OUTPUT"]):
        active_status = "FAIL"
    elif any(rc in risk_codes for rc in ["BRANCH_ONLY_SCENARIO_RISK", "SCENARIO_CONFIDENCE_MISSING"]):
        active_status = "PARTIAL"

    context_status = "PASS"
    if any(rc in risk_codes for rc in ["MARKET_STATE_NOT_LINKED_TO_SCENARIO", "SCENARIO_NOT_LINKED_TO_SETUP", "CONTEXT_UNAWARE_EDGE_RISK"]):
        context_status = "PARTIAL"
    if any(rc in risk_codes for rc in ["NO_MARKET_STATE_RECORDS", "NO_SCENARIO_RECORDS"]):
        context_status = "FAIL"

    if market_status == "FAIL" or active_status == "FAIL":
        prompt11 = "Prompt 11 = LOCAL MARKET STATE + ACTIVE SCENARIO PATCH PLAN"
    elif market_status == "PARTIAL" or active_status == "PARTIAL" or context_status == "PARTIAL":
        prompt11 = "Prompt 11 = LOCAL MARKET STATE + ACTIVE SCENARIO HARDENING PATCH PLAN"
    else:
        prompt11 = "Prompt 11 = LOCAL CONDITIONAL EDGE MATRIX AUDIT"

    regime_dist = dist_from_field(market_rows, "regime")
    trend_dist = dist_from_field(market_rows, "trend")

    result = {
        "generated_at_utc": now.isoformat(),
        "sources": {
            "market_state": str(market_path.relative_to(ROOT)),
            "scenario": str(scenario_path.relative_to(ROOT)),
            "setup": str(setup_path.relative_to(ROOT)),
        },
        "record_counts": {
            "market_state": len(market_rows),
            "scenario": len(scenario_rows),
            "setup": len(setup_rows),
        },
        "field_evidence": {
            "market_state": market_field_stats,
            "scenario": scenario_field_stats,
        },
        "computed": {
            "active_scenario_records": active_record_count,
            "branch_only_scenario_records": branch_only_count,
            "regime_unique_count": len(regime_dist),
            "trend_unique_count": len(trend_dist),
            "active_scenario_unique_count": len(active_values) + len(selected_values) + len(dominant_values),
            "scenario_confidence_distribution": scenario_conf_values.most_common(20),
            "market_state_to_scenario_linkage_count": len(market_to_scenario),
            "scenario_to_setup_linkage_count": len(scenario_to_setup),
            "market_state_latest_timestamp": market_latest,
            "scenario_latest_timestamp": scenario_latest,
            "setup_latest_timestamp": setup_latest,
            "regime_distribution_top": regime_dist.most_common(10),
            "trend_distribution_top": trend_dist.most_common(10),
        },
        "checks": checks,
        "risk_codes": sorted(risk_codes),
        "judgement": {
            "market_state": market_status,
            "active_scenario": active_status,
            "context_aware_readiness": context_status,
        },
        "prompt_11_recommendation": prompt11,
        "latest_fields": {
            "market_state": sorted(market_rows[-1].keys()) if market_rows else [],
            "scenario": sorted(scenario_rows[-1].keys()) if scenario_rows else [],
            "setup": sorted(setup_rows[-1].keys()) if setup_rows else [],
        },
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def fbool(b: bool) -> str:
        return "YES" if b else "NO"

    market_rows_md = []
    for f in MARKET_FIELDS:
        d = market_field_stats[f]
        st = "PASS" if d["found"] else "KANITLANAMADI"
        market_rows_md.append(
            f"{f} | {fbool(d['found'])} | {d['source_file']} | {d['unique_values']} | {d['latest_timestamp'] or 'KANITLANAMADI'} | {st}"
        )

    scenario_rows_md = []
    for f in SCENARIO_FIELDS:
        d = scenario_field_stats[f]
        st = "PASS" if d["found"] else "KANITLANAMADI"
        scenario_rows_md.append(
            f"{f} | {fbool(d['found'])} | {d['source_file']} | {d['unique_values']} | {d['latest_timestamp'] or 'KANITLANAMADI'} | {st}"
        )

    risk_md = []
    for rc in sorted(risk_codes):
        sev = "HIGH" if rc.startswith("NO_") or "MISSING" in rc else "MEDIUM"
        risk_md.append(f"{rc} | JSON evidence available | {sev} | Patch/hardening gerekli")

    md = f"""# VPS MARKET STATE + ACTIVE SCENARIO REALITY AUDIT REPORT

## 1. Net Hüküm
Market State:
{market_status}

Active Scenario:
{active_status}

Context-Aware Readiness:
{context_status}

## 2. Market State Evidence
Field | Found? | Source File | Unique Values | Latest Timestamp | Status
---|---|---|---:|---|---
{chr(10).join(market_rows_md)}

## 3. Scenario Evidence
Field | Found? | Source File | Unique Values | Latest Timestamp | Status
---|---|---|---:|---|---
{chr(10).join(scenario_rows_md)}

## 4. Branch vs Active Scenario
Type | Count | Evidence | Risk
---|---:|---|---
active_scenario bulunan kayıt | {active_record_count} | active_scenario/selected_scenario/dominant_scenario alan taraması | {"LOW" if active_record_count > 0 else "HIGH"}
branch-only scenario kayıt | {branch_only_count} | bullish+bearish+neutral var, active seçimi yok | {"BRANCH_ONLY_SCENARIO_RISK" if branch_only_count > 0 else "LOW"}

## 5. Market State → Scenario → Setup Link
Link | Traceable Count | Evidence | Status
---|---:|---|---
market_state → scenario | {len(market_to_scenario)} | context_id kesişimi | {"PASS" if len(market_to_scenario) > 0 else "FAIL"}
scenario → setup | {len(scenario_to_setup)} | context_id kesişimi | {"PASS" if len(scenario_to_setup) > 0 else "FAIL"}

## 6. Critical Risks
Risk Code | Evidence | Severity | Required Fix
---|---|---|---
{chr(10).join(risk_md) if risk_md else "KANITLANAMADI | KANITLANAMADI | LOW | monitor"}

## 7. Prompt 11 Recommendation
{prompt11}

## 8. Evidence Notes
- market_state source: `{market_path.relative_to(ROOT)}`, lines={len(market_rows)}, latest_fields={",".join(sorted(market_rows[-1].keys())[:32]) if market_rows else "KANITLANAMADI"}, last_ts={market_latest or "KANITLANAMADI"}
- scenario source: `{scenario_path.relative_to(ROOT)}`, lines={len(scenario_rows)}, latest_fields={",".join(sorted(scenario_rows[-1].keys())[:32]) if scenario_rows else "KANITLANAMADI"}, last_ts={scenario_latest or "KANITLANAMADI"}
- setup source: `{setup_path.relative_to(ROOT)}`, lines={len(setup_rows)}, latest_fields={",".join(sorted(setup_rows[-1].keys())[:32]) if setup_rows else "KANITLANAMADI"}, last_ts={setup_latest or "KANITLANAMADI"}
- regime distribution (top): {regime_dist.most_common(5) if regime_dist else "KANITLANAMADI"}
- trend distribution (top): {trend_dist.most_common(5) if trend_dist else "KANITLANAMADI"}
- scenario_confidence distribution (top): {scenario_conf_values.most_common(5) if scenario_conf_values else "KANITLANAMADI"}
"""
    OUT_MD.write_text(md, encoding="utf-8")
    OUT_REC.write_text(prompt11 + "\n", encoding="utf-8")

    print(f"Wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote: {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote: {OUT_REC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
