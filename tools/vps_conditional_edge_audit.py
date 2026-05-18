#!/usr/bin/env python3
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "reports" / "vps_conditional_edge_audit.json"
OUT_MD = ROOT / "reports" / "vps_conditional_edge_audit_report.md"
OUT_REC = ROOT / "reports" / "vps_prompt_13_recommendation.md"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
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


def walk_key(obj: Any, key: str) -> list[Any]:
    vals: list[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                vals.append(v)
            vals.extend(walk_key(v, key))
    elif isinstance(obj, list):
        for it in obj:
            vals.extend(walk_key(it, key))
    return vals


def str_value(v: Any) -> str | None:
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, dict):
        for k in ["value", "label", "state", "regime", "trend", "name", "type"]:
            x = v.get(k)
            if isinstance(x, (str, int, float, bool)):
                return str(x)
    return None


def has_field(rows: list[dict[str, Any]], key: str) -> bool:
    return any(walk_key(r, key) for r in rows)


def unique_count(rows: list[dict[str, Any]], key: str) -> int:
    s: set[str] = set()
    for r in rows:
        for v in walk_key(r, key):
            sv = str_value(v)
            if sv:
                s.add(sv)
    return len(s)


def latest_ts(rows: list[dict[str, Any]]) -> str | None:
    for r in reversed(rows):
        ts = r.get("timestamp_utc") or r.get("timestamp")
        if ts:
            return ts
    return None


def main() -> None:
    now = datetime.now(timezone.utc)
    paths = {
        "contract_edge": ROOT / "data/simple/epoch_v2/contract_edge_matrix_history.jsonl",
        "research_edge": ROOT / "data/simple/epoch_v2/research_edge_matrix_history.jsonl",
        "true_edge_dataset": ROOT / "data/simple/epoch_v2/true_edge_dataset_history.jsonl",
        "outcome_accounting": ROOT / "data/simple/epoch_v2/outcome_accounting_history.jsonl",
        "true_outcome": ROOT / "data/simple/epoch_v2/true_outcome_history.jsonl",
        "paper_lifecycle": ROOT / "data/simple/epoch_v2/research_paper_lifecycle_history.jsonl",
        "paper_factory": ROOT / "data/simple/epoch_v2/paper_trade_factory_history.jsonl",
        "full_lineage": ROOT / "data/simple/epoch_v2/full_lineage_history.jsonl",
    }
    data = {k: load_jsonl(p) for k, p in paths.items()}

    contract_rows = data["contract_edge"]
    research_rows = data["research_edge"]
    true_ds_rows = data["true_edge_dataset"]
    outcome_rows = data["outcome_accounting"]
    true_outcome_rows = data["true_outcome"]
    paper_lifecycle_rows = data["paper_lifecycle"]
    paper_factory_rows = data["paper_factory"]

    outcome_closed_ids = set()
    for r in outcome_rows:
        for s in r.get("closed_samples") or []:
            if isinstance(s, dict):
                pid = s.get("paper_trade_id")
                if isinstance(pid, str) and pid:
                    outcome_closed_ids.add(pid)

    true_outcome_closed_ids = set()
    close_type_dist = Counter()
    result_r_count = 0
    pnl_count = 0
    for r in true_outcome_rows:
        for o in r.get("outcomes") or []:
            if not isinstance(o, dict):
                continue
            pid = o.get("paper_trade_id")
            if isinstance(pid, str) and pid:
                true_outcome_closed_ids.add(pid)
            ct = o.get("close_reason") or o.get("outcome_status")
            if isinstance(ct, str):
                close_type_dist[ct] += 1
            if o.get("realized_r") is not None or o.get("r_result") is not None:
                result_r_count += 1
            if o.get("pnl") is not None:
                pnl_count += 1

    true_ds_latest_rows = true_ds_rows[-1].get("rows") if true_ds_rows else []
    if not isinstance(true_ds_latest_rows, list):
        true_ds_latest_rows = []

    grouping_fields = ["pattern", "setup_family", "signal_type", "trend", "regime", "liquidity_state", "active_scenario"]
    grouping_presence = {f: has_field(true_ds_latest_rows, f) or has_field(research_rows, f) or has_field(contract_rows, f) for f in grouping_fields}
    grouping_unique = {f: max(unique_count(true_ds_latest_rows, f), unique_count(research_rows, f), unique_count(contract_rows, f)) for f in grouping_fields}

    # Build strict conditional key count from latest true_edge_dataset rows.
    conditional_keys = set()
    for row in true_ds_latest_rows:
        if not isinstance(row, dict):
            continue
        key_parts = []
        for f in grouping_fields:
            vv = walk_key(row, f)
            sv = str_value(vv[0]) if vv else None
            key_parts.append(sv)
        if all(key_parts):
            conditional_keys.add("|".join(key_parts))

    contract_last = contract_rows[-1] if contract_rows else {}
    research_last = research_rows[-1] if research_rows else {}
    contract_ss = contract_last.get("sample_summary") if isinstance(contract_last.get("sample_summary"), dict) else {}
    research_sm = research_last.get("summary") if isinstance(research_last.get("summary"), dict) else {}

    contract_legacy = contract_ss.get("legacy_sample_count")
    contract_closed = contract_ss.get("closed_count")
    snapshot_contamination = isinstance(contract_legacy, int) and isinstance(contract_closed, int) and contract_legacy >= contract_closed and contract_closed > 0

    contract_rc = contract_last.get("reason_codes") if isinstance(contract_last.get("reason_codes"), list) else []
    research_rc = research_last.get("reason_codes") if isinstance(research_last.get("reason_codes"), list) else []
    rc_text = " ".join([str(x) for x in contract_rc + research_rc]).upper()

    edge_reads_closed_outcomes = (
        isinstance(research_sm.get("closed_trade_count"), int)
        and research_sm.get("closed_trade_count", 0) > 0
        and "OUTCOME" in str(research_last.get("source", "")).upper()
    )
    edge_excludes_open_trades = not ("OPEN" in rc_text and "OPEN_TRADES" in rc_text)
    edge_excludes_snapshots = not snapshot_contamination
    edge_excludes_replay = "REPLAY" not in rc_text
    uses_paper_factory_summary = "PAPER_TRADE_FACTORY" in rc_text

    checks = {
        "edge_records_found": len(contract_rows) + len(research_rows),
        "closed_outcome_records_found": len(outcome_closed_ids),
        "edge_reads_closed_outcomes": edge_reads_closed_outcomes,
        "edge_excludes_open_trades": edge_excludes_open_trades,
        "edge_excludes_snapshots": edge_excludes_snapshots,
        "edge_excludes_replay": edge_excludes_replay,
        "pattern_used": grouping_presence["pattern"],
        "setup_family_used": grouping_presence["setup_family"],
        "signal_type_used": grouping_presence["signal_type"],
        "trend_used": grouping_presence["trend"],
        "regime_used": grouping_presence["regime"],
        "liquidity_state_used": grouping_presence["liquidity_state"],
        "active_scenario_used": grouping_presence["active_scenario"],
        "conditional_grouping_found": len(conditional_keys) > 0,
        "winrate_found": has_field(research_rows, "winrate") or has_field(contract_rows, "winrate"),
        "expectancy_found": has_field(research_rows, "expectancy") or has_field(contract_rows, "expectancy"),
        "profit_factor_found": has_field(contract_rows, "profit_factor") or has_field(research_rows, "profit_factor"),
        "sample_size_found": has_field(research_rows, "sample_size") or has_field(contract_rows, "sample_size"),
        "edge_status_found": has_field(research_rows, "edge_status") or has_field(contract_rows, "edge_status"),
        "snapshot_contamination_detected": snapshot_contamination,
    }

    risk_codes: set[str] = set()
    if checks["edge_records_found"] == 0:
        risk_codes.add("NO_EDGE_RECORDS")
    if checks["closed_outcome_records_found"] == 0:
        risk_codes.add("NO_CLOSED_OUTCOMES")
    if not checks["edge_reads_closed_outcomes"]:
        risk_codes.add("EDGE_NOT_CLOSED_ONLY")
    if not checks["edge_excludes_open_trades"]:
        risk_codes.add("EDGE_USES_OPEN_TRADES")
    if not checks["edge_excludes_snapshots"]:
        risk_codes.add("EDGE_USES_SNAPSHOT")
    if not checks["edge_excludes_replay"]:
        risk_codes.add("EDGE_USES_REPLAY")
    if not checks["pattern_used"]:
        risk_codes.add("PATTERN_NOT_USED")
    if not checks["trend_used"]:
        risk_codes.add("TREND_NOT_USED")
    if not checks["regime_used"]:
        risk_codes.add("REGIME_NOT_USED")
    if not checks["liquidity_state_used"]:
        risk_codes.add("LIQUIDITY_STATE_NOT_USED")
    if not checks["active_scenario_used"]:
        risk_codes.add("ACTIVE_SCENARIO_NOT_USED")
    if not checks["signal_type_used"]:
        risk_codes.add("SIGNAL_TYPE_NOT_USED")
    if not checks["conditional_grouping_found"]:
        risk_codes.add("CONDITIONAL_GROUPING_MISSING")
    if not checks["expectancy_found"]:
        risk_codes.add("EXPECTANCY_MISSING")
    if not checks["profit_factor_found"]:
        risk_codes.add("PROFIT_FACTOR_MISSING")
    if not checks["sample_size_found"]:
        risk_codes.add("SAMPLE_SIZE_MISSING")
    if not checks["edge_status_found"]:
        risk_codes.add("EDGE_STATUS_MISSING")
    if checks["closed_outcome_records_found"] < 100:
        risk_codes.add("LOW_SAMPLE_SIZE")

    conditional_judgement = "PASS"
    if any(
        x in risk_codes
        for x in [
            "NO_EDGE_RECORDS",
            "NO_CLOSED_OUTCOMES",
            "CONDITIONAL_GROUPING_MISSING",
            "PATTERN_NOT_USED",
            "TREND_NOT_USED",
            "REGIME_NOT_USED",
            "LIQUIDITY_STATE_NOT_USED",
            "ACTIVE_SCENARIO_NOT_USED",
            "SIGNAL_TYPE_NOT_USED",
        ]
    ):
        conditional_judgement = "FAIL"
    elif risk_codes:
        conditional_judgement = "PARTIAL"

    cleanliness_judgement = "PASS"
    if any(x in risk_codes for x in ["EDGE_USES_SNAPSHOT", "EDGE_USES_REPLAY", "EDGE_USES_OPEN_TRADES", "EDGE_NOT_CLOSED_ONLY"]):
        cleanliness_judgement = "FAIL"
    elif risk_codes:
        cleanliness_judgement = "PARTIAL"

    reliability_judgement = "PASS"
    if any(x in risk_codes for x in ["LOW_SAMPLE_SIZE", "SAMPLE_SIZE_MISSING", "EXPECTANCY_MISSING", "PROFIT_FACTOR_MISSING"]):
        reliability_judgement = "PARTIAL"
    if checks["closed_outcome_records_found"] == 0:
        reliability_judgement = "FAIL"

    if conditional_judgement == "FAIL":
        prompt13 = "Prompt 13 = LOCAL CONDITIONAL EDGE PATCH PLAN"
    elif conditional_judgement == "PARTIAL" or cleanliness_judgement == "PARTIAL" or reliability_judgement == "PARTIAL":
        prompt13 = "Prompt 13 = LOCAL EDGE HARDENING PATCH PLAN"
    else:
        prompt13 = "Prompt 13 = VPS FINAL LIVE HEALTH PRE-AUDIT"

    result = {
        "generated_at_utc": now.isoformat(),
        "sources": {k: str(v.relative_to(ROOT)) for k, v in paths.items()},
        "checks": checks,
        "risk_codes": sorted(risk_codes),
        "judgement": {
            "conditional_edge": conditional_judgement,
            "edge_cleanliness": cleanliness_judgement,
            "sample_reliability": reliability_judgement,
        },
        "evidence": {
            "rows": {k: len(v) for k, v in data.items()},
            "latest_timestamps": {k: latest_ts(v) for k, v in data.items()},
            "grouping_presence": grouping_presence,
            "grouping_unique_count": grouping_unique,
            "conditional_grouping_unique_count": len(conditional_keys),
            "closed_outcome_count_outcome_accounting": len(outcome_closed_ids),
            "closed_outcome_count_true_outcome": len(true_outcome_closed_ids),
            "close_type_distribution_top": close_type_dist.most_common(20),
            "result_r_count": result_r_count,
            "pnl_count": pnl_count,
            "contract_edge_last_fields": sorted(contract_last.keys()) if contract_last else [],
            "research_edge_last_fields": sorted(research_last.keys()) if research_last else [],
            "contract_sample_summary": contract_ss,
            "research_summary": research_sm,
            "snapshot_contamination_example": {
                "legacy_sample_count": contract_legacy,
                "closed_count": contract_closed,
                "reason_codes": contract_rc,
            },
            "uses_paper_factory_summary_signal": uses_paper_factory_summary,
        },
        "missing_before_final": [
            "pattern+trend+regime+liquidity_state+active_scenario+signal_type tam conditional key kanıtı",
            "edge->outcome per-trade mapping (paper_trade_id/outcome_id) edge katmanında",
            "active_scenario alanı VPS output katmanlarında",
            "trend/liquidity_state/signal_type açık alanları edge grouping içinde",
        ],
        "prompt_13_recommendation": prompt13,
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    source_rows = [
        f"contract_edge_matrix_history | {len(contract_rows)} | {'NO' if snapshot_contamination else 'KANITLANAMADI'} | {'YES' if snapshot_contamination else 'NO'} | sample_summary.legacy_sample_count={contract_legacy}, closed_count={contract_closed} | {'FAIL' if snapshot_contamination else 'PARTIAL'}",
        f"research_edge_matrix_history | {len(research_rows)} | {'YES' if edge_reads_closed_outcomes else 'KANITLANAMADI'} | NO | source_mode={research_last.get('source')} summary.closed_trade_count={research_sm.get('closed_trade_count')} | {'PASS' if edge_reads_closed_outcomes else 'PARTIAL'}",
    ]

    grouping_rows = []
    for f in ["pattern", "setup_family", "signal_type", "trend", "regime", "liquidity_state", "active_scenario"]:
        found = grouping_presence[f]
        grouping_rows.append(
            f"{f} | {'YES' if found else 'NO'} | {grouping_unique[f]} | true_edge_dataset/research_edge taraması | {'PASS' if found else 'FAIL'}"
        )

    metric_rows = [
        f"winrate | {'YES' if checks['winrate_found'] else 'NO'} | research.groups[].winrate / contract.sample_summary.winrate | {'PASS' if checks['winrate_found'] else 'FAIL'}",
        f"expectancy | {'YES' if checks['expectancy_found'] else 'NO'} | research.groups[].expectancy / contract.sample_summary.expectancy | {'PASS' if checks['expectancy_found'] else 'FAIL'}",
        f"profit_factor | {'YES' if checks['profit_factor_found'] else 'NO'} | contract.sample_summary.profit_factor | {'PASS' if checks['profit_factor_found'] else 'FAIL'}",
        f"sample_size | {'YES' if checks['sample_size_found'] else 'NO'} | research.groups[].sample_size | {'PASS' if checks['sample_size_found'] else 'FAIL'}",
        f"edge_status | {'YES' if checks['edge_status_found'] else 'NO'} | research.edge_status / groups[].edge_status | {'PASS' if checks['edge_status_found'] else 'FAIL'}",
    ]

    risk_rows = []
    for r in sorted(risk_codes):
        sev = "HIGH" if r.startswith("NO_") or "MISSING" in r or "NOT_USED" in r else "MEDIUM"
        risk_rows.append(f"{r} | JSON evidence available | {sev} | Patch/hardening gerekli")

    md = f"""# VPS CONDITIONAL EDGE REALITY AUDIT REPORT

## 1. Net Hüküm
Conditional Edge:
{conditional_judgement}

Edge Cleanliness:
{cleanliness_judgement}

Sample Reliability:
{reliability_judgement}

## 2. Edge Source Evidence
Source | Rows | Closed Only? | Snapshot Risk | Evidence | Status
---|---:|---|---|---|---
{chr(10).join(source_rows)}

## 3. Conditional Grouping Evidence
Field | Found? | Unique Count | Evidence | Status
---|---|---:|---|---
{chr(10).join(grouping_rows)}

## 4. Edge Metrics Evidence
Metric | Found? | Evidence | Status
---|---|---|---
{chr(10).join(metric_rows)}

## 5. Contamination Risks
Risk Code | Evidence | Severity | Required Fix
---|---|---|---
{chr(10).join(risk_rows) if risk_rows else "KANITLANAMADI | KANITLANAMADI | LOW | monitor"}

## 6. Prompt 13 Recommendation
{prompt13}

## 7. Evidence Notes
- outcome_accounting rows={len(outcome_rows)}, closed_outcome_count={len(outcome_closed_ids)}, latest_ts={latest_ts(outcome_rows) or "KANITLANAMADI"}
- true_outcome rows={len(true_outcome_rows)}, close_type_distribution_top={close_type_dist.most_common(5) if close_type_dist else "KANITLANAMADI"}
- latest contract edge fields={",".join(sorted(contract_last.keys())[:40]) if contract_last else "KANITLANAMADI"}
- latest research edge fields={",".join(sorted(research_last.keys())[:40]) if research_last else "KANITLANAMADI"}
- conditional grouping unique count (strict key: pattern+trend+regime+liquidity_state+active_scenario+signal_type)={len(conditional_keys)}
- snapshot contamination örneği: legacy_sample_count={contract_legacy}, closed_count={contract_closed}, reason_codes={contract_rc if contract_rc else "KANITLANAMADI"}
- Final öncesi eksikler: {", ".join(result["missing_before_final"])}
"""
    OUT_MD.write_text(md, encoding="utf-8")
    OUT_REC.write_text(prompt13 + "\n", encoding="utf-8")

    print(f"Wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote: {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote: {OUT_REC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
