"""Run S4 Quality Weight Engine — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from src.simple.quality_weight_engine import build_quality_weight, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _write_outputs(qw: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_quality_weight.json").write_text(
        json.dumps(qw, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s4_quality_weight_state.json").write_text(
        json.dumps(qw, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "quality_weight.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(qw) + "\n")

    inp = qw["input_status"]
    comp = qw["quality_components"]
    qwf = qw["quality_weight"]
    dp = qw["decision_policy"]
    rp = qw["repair_policy"]
    ep = qw["edge_policy"]
    dq = qw["data_quality"]
    lines = [
        f"# S4 Quality Weight Engine — {qw['symbol']}",
        "",
        f"**Timestamp:** {qw['timestamp_utc']}",
        f"**Source Mode:** {qw['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Input Status",
        f"- Market Truth: {inp['market_truth_available']}",
        f"- 1S Evidence: {inp['one_second_evidence_available']}",
        f"- Hybrid Candle: {inp['hybrid_candle_available']}",
        f"- Missing: {inp['missing_inputs']}",
        "",
        "## Quality Components",
        f"- Market Truth Score: {comp['market_truth_score']}",
        f"- Evidence Score: {comp['evidence_score']}",
        f"- Hybrid Candle Score: {comp['hybrid_candle_score']}",
        f"- Coverage Score: {comp['coverage_score']}",
        f"- Consistency Score: {comp['consistency_score']}",
        f"- Final Quality Score: {comp['final_quality_score']}",
        "",
        "## Quality Weight",
        f"- Weight: {qwf['quality_weight']}",
        f"- Label: {qwf['quality_label']}",
        f"- Confidence Policy: {qwf['confidence_policy']}",
        "",
        "## Decision Policy",
        f"- Mode: {dp['decision_quality_mode']}",
        f"- Max Allowed: {dp['max_allowed_decision']}",
        "",
        "## Repair Policy",
        f"- Required: {rp['repair_required']}",
        f"- Action: {rp['repair_action']}",
        "",
        "## Edge Policy",
        f"- Eligible: {ep['edge_eligible_if_trade_opens']}",
        f"- Reason: {ep['edge_reason']}",
        "",
        "## Reason Codes",
        *[f"- {rc}" for rc in qw["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in qw["feeds_next"]["next_blocks"]],
    ]
    (REPORTS_DIR / "s4_quality_weight_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S4 Quality Weight Engine")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        qw = run_fake_sample(args.symbol)
    else:
        print("[S4] No live source configured. Use --fake-sample for testing.", file=sys.stderr)
        qw = build_quality_weight(args.symbol, None, None, None, "NO_DATA")

    _write_outputs(qw)
    print(json.dumps(qw, indent=2))


if __name__ == "__main__":
    main()
