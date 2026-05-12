"""Run S11.1 Local Full Pipeline — CLI entry point.

Usage:
    python -m src.simple.run_local_full_pipeline --fake-sample --symbol BTCUSDT

Outputs:
    state/simple/latest_local_pipeline_run.json
    reports/simple/local_pipeline_latest_report.md
"""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.local_pipeline_runner import run_pipeline

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _build_report(summary: dict) -> str:
    es = summary["execution_summary"]
    dq = summary["data_quality"]
    safety = summary["execution_safety"]
    results = summary["block_results"]

    lines = [
        f"# S11.1 Local Full Pipeline — {summary['symbol']}",
        "",
        f"**Timestamp:** {summary['timestamp_utc']}",
        f"**Source Mode:** {summary['source']['source_mode']}",
        f"**Pipeline Status:** {es['pipeline_status']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Execution Summary",
        f"- Blocks Total: {es['blocks_total']}",
        f"- Blocks Passed: {es['blocks_passed']}",
        f"- Blocks Failed: {es['blocks_failed']}",
        f"- Stop Reason: {es['stop_reason'] or 'None'}",
        "",
        "## Block Results",
    ]

    for r in results:
        status = r["status"]
        err = f" | error={r['error']}" if r["error"] else ""
        lines.append(f"- [{status}] {r['block_id']} ({r['runtime_ms']} ms){err}")

    lines += [
        "",
        "## Execution Safety",
        f"- safe_to_open_real_trade: {safety['safe_to_open_real_trade']}",
        f"- private_api_used: {safety['private_api_used']}",
        f"- live_order_sent: {safety['live_order_sent']}",
        "",
        "## Reason Codes",
        *[f"- {c}" for c in summary["reason_codes"]],
    ]
    return "\n".join(lines) + "\n"


def _write_outputs(summary: dict) -> None:
    _ensure_dirs()
    (STATE_DIR / "latest_local_pipeline_run.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (REPORTS_DIR / "local_pipeline_latest_report.md").write_text(
        _build_report(summary), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S11.1 Local Full Pipeline")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    source_mode = "FAKE_SAMPLE" if args.fake_sample else "LIVE"
    summary = run_pipeline(args.symbol, source_mode=source_mode)

    _write_outputs(summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
