"""Run S11 Replay Sample Runner — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.replay_sample_runner import run_batch, run_fake_sample, DEFAULT_SEED

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _build_report_text(summary: dict, samples: list[dict]) -> str:
    bs = summary["batch_stats"]
    dq = summary["data_quality"]
    rc = summary["run_config"]
    es_val = summary["execution_safety"]

    outcome_counts: dict[str, int] = {}
    for s in samples:
        oc = s["outcome"]["outcome"]
        outcome_counts[oc] = outcome_counts.get(oc, 0) + 1

    lines = [
        f"# S11 Replay Sample Runner — {summary['symbol']}",
        "",
        f"**Timestamp:** {summary['timestamp_utc']}",
        f"**Source Mode:** {summary['source']['source_mode']}",
        f"**Seed:** {rc['seed']}",
        f"**Samples Requested:** {rc['samples_requested']}",
        f"**Samples Generated:** {rc['samples_generated']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Batch Stats",
        f"- Total Samples: {bs['total_samples']}",
        f"- Trades Opened: {bs['trades_opened']}",
        f"- No Trade: {bs['no_trade_count']}",
        f"- Edge Eligible: {bs['edge_eligible_count']}",
        f"- Win Count: {bs['win_count']}",
        f"- Loss Count: {bs['loss_count']}",
        f"- Ambiguous: {bs['ambiguous_count']}",
        f"- Win Rate: {bs['win_rate']}",
        f"- Avg RR Realized: {bs['avg_rr_realized']}",
        f"- Edge Score: {bs['edge_score']}",
        "",
        "## Outcome Distribution",
        *[f"- {k}: {v}" for k, v in sorted(outcome_counts.items())],
        "",
        "## Execution Safety",
        f"- safe_to_open_real_trade: {es_val['safe_to_open_real_trade']}",
        f"- private_api_used: {es_val['private_api_used']}",
        f"- live_order_sent: {es_val['live_order_sent']}",
        f"- research_only: {es_val['research_only']}",
        "",
        "## Reason Codes",
        *[f"- {code}" for code in summary["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in summary["feeds_next"]["next_blocks"]],
    ]
    return "\n".join(lines) + "\n"


def _write_outputs(summary: dict, samples: list[dict]) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_replay_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s11_replay_samples_state.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "replay_samples.jsonl").open("a", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s) + "\n")

    (REPORTS_DIR / "s11_replay_samples_latest_report.md").write_text(
        _build_report_text(summary, samples), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S11 Replay Sample Runner")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    if args.fake_sample:
        samples, summary = run_batch(args.symbol, args.samples, args.seed)
        summary["source"]["source_mode"] = "FAKE_SAMPLE"
        summary["reason_codes"][0] = "SOURCE_FAKE_SAMPLE"
    else:
        samples, summary = run_batch(args.symbol, args.samples, args.seed)

    _write_outputs(summary, samples)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
