"""Run S10 Simple Brain Report — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.simple_brain_report_engine import build_brain_report, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"

_STATE_FILES = {
    "s1": "latest_market_truth.json",
    "s2": "latest_1s_evidence.json",
    "s3": "latest_hybrid_candle_dna.json",
    "s4": "latest_quality_weight.json",
    "s5": "latest_liquidity_structure.json",
    "s6": "latest_setup_candidate.json",
    "s7": "latest_decision.json",
    "s8": "latest_outcome.json",
    "s9": "latest_edge_stats.json",
}


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_inputs() -> dict:
    inputs: dict = {}
    for key, filename in _STATE_FILES.items():
        path = STATE_DIR / filename
        if not path.exists():
            inputs[key] = None
            continue
        try:
            inputs[key] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            inputs[key] = None
    return inputs


def _build_report_text(br: dict) -> str:
    inp = br["input_status"]
    ms = br["market_snapshot"]
    qs = br["quality_snapshot"]
    ss = br["setup_snapshot"]
    ds = br["decision_snapshot"]
    pos = br["paper_outcome_snapshot"]
    es = br["edge_snapshot"]
    dq = br["data_quality"]

    lines = [
        f"# Simple Brain Report — {br['symbol']}",
        "",
        f"**Timestamp:** {br['timestamp_utc']}",
        f"**Source Mode:** {br['source']['source_mode']}",
        f"**System Health:** {br['system_health']}",
        f"**Brain Status:** {br['brain_status']}",
        f"**Brain Mode:** {br['brain_mode']}",
        f"**Primary Next Action:** {br['primary_next_action']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Input Status",
        f"- Blocks Available: {inp['blocks_available']} / {inp['blocks_total']}",
        f"- Missing Blocks: {inp['missing_blocks'] or 'none'}",
        "",
        "## Market Snapshot",
    ]
    if ms.get("available"):
        lines += [
            f"- Mid Price: {ms.get('mid_price')}",
            f"- High: {ms.get('high')}  Low: {ms.get('low')}  Close: {ms.get('close')}",
            f"- Candle Direction: {ms.get('candle_direction')}",
            f"- Evidence: {ms.get('evidence_label')} ({ms.get('evidence_strength')})",
            f"- Candle Intent: {ms.get('candle_intent')}",
        ]
    else:
        lines.append("- UNAVAILABLE")

    lines += ["", "## Quality Snapshot"]
    if qs.get("available"):
        lines += [
            f"- Quality Weight: {qs.get('quality_weight')}",
            f"- Label: {qs.get('quality_label')}",
            f"- Confidence Policy: {qs.get('confidence_policy')}",
            f"- Decision Quality Mode: {qs.get('decision_quality_mode')}",
        ]
    else:
        lines.append("- UNAVAILABLE")

    lines += ["", "## Setup Snapshot"]
    if ss.get("available"):
        lines += [
            f"- Setup Type: {ss.get('setup_type')}",
            f"- Direction: {ss.get('setup_direction')}",
            f"- Grade: {ss.get('setup_grade')}",
            f"- Status: {ss.get('setup_status')}",
            f"- Scenario: {ss.get('scenario_type')}",
            f"- Nearest Support: {ss.get('nearest_support')}",
            f"- Nearest Resistance: {ss.get('nearest_resistance')}",
            f"- Structure Bias: {ss.get('structure_bias')}",
        ]
    else:
        lines.append("- UNAVAILABLE")

    lines += ["", "## Decision Snapshot"]
    if ds.get("available"):
        lines += [
            f"- Decision: {ds.get('decision')}",
            f"- Reason: {ds.get('decision_reason')}",
            f"- Direction: {ds.get('trade_direction')}",
            f"- Entry: {ds.get('entry_price')}",
            f"- Stop Loss: {ds.get('stop_loss')}",
            f"- TP1: {ds.get('tp1')}  TP2: {ds.get('tp2')}",
            f"- RR TP1: {ds.get('rr_tp1')}  RR TP2: {ds.get('rr_tp2')}",
        ]
    else:
        lines.append("- UNAVAILABLE")

    lines += ["", "## Paper Outcome Snapshot"]
    if pos.get("available"):
        lines += [
            f"- Outcome: {pos.get('outcome')}",
            f"- Realized RR: {pos.get('realized_rr')}",
            f"- Trade Status: {pos.get('trade_status')}",
            f"- Edge Eligible: {pos.get('edge_eligible')}",
        ]
    else:
        lines.append("- UNAVAILABLE")

    lines += ["", "## Edge Snapshot"]
    if es.get("available"):
        lines += [
            f"- Edge Eligible Count: {es.get('edge_eligible_count')}",
            f"- Win Count: {es.get('win_count')}  Loss Count: {es.get('loss_count')}",
            f"- Win Rate: {es.get('win_rate')}",
            f"- Avg RR Realized: {es.get('avg_rr_realized')}",
            f"- Edge Score: {es.get('edge_score')}",
            f"- Sample Quality: {es.get('sample_quality')}",
        ]
    else:
        lines.append("- UNAVAILABLE")

    lines += [
        "",
        "## Execution Safety",
        f"- safe_to_open_real_trade: {br['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {br['execution_safety']['private_api_used']}",
        f"- live_order_sent: {br['execution_safety']['live_order_sent']}",
        "",
        "## Reason Codes",
        *[f"- {code}" for code in br["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in br["feeds_next"]["next_blocks"]],
    ]
    return "\n".join(lines) + "\n"


def _write_outputs(br: dict) -> None:
    _ensure_dirs()

    report_file = REPORTS_DIR / "simple_brain_latest_report.md"

    (STATE_DIR / "latest_simple_brain.json").write_text(
        json.dumps(br, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s10_simple_brain_state.json").write_text(
        json.dumps(br, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "simple_brain.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(br) + "\n")

    report_file.write_text(_build_report_text(br), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S10 Simple Brain Report")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    report_path = str(REPORTS_DIR / "simple_brain_latest_report.md")

    if args.fake_sample:
        from src.simple.simple_brain_report_engine import _FAKE_INPUTS
        br = build_brain_report(args.symbol, _FAKE_INPUTS, "FAKE_SAMPLE", report_path)
    else:
        inputs = _load_inputs()
        br = build_brain_report(args.symbol, inputs, "STATE_FILE", report_path)

    _write_outputs(br)
    print(json.dumps(br, indent=2))


if __name__ == "__main__":
    main()
