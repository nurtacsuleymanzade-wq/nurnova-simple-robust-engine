"""Run S11.2 Sample Schema Validator — CLI entry point."""

from __future__ import annotations

import json
import pathlib

from src.simple.sample_schema_validator import validate_file

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "data" / "simple" / "replay_samples.jsonl"
STATE_DIR = ROOT / "state" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _build_report_text(result: dict) -> str:
    vs = result["validation_summary"]
    dq = result["data_quality"]
    errors = result["errors"]

    lines = [
        f"# S11.2 Sample Schema Validator — {result['symbol']}",
        "",
        f"**Timestamp:** {result['timestamp_utc']}",
        f"**Source:** {result['source']['path']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Validation Summary",
        f"- Total Rows: {vs['total_rows']}",
        f"- Valid Rows: {vs['valid_rows']}",
        f"- Error Rows: {vs['error_rows']}",
        f"- Malformed Rows: {vs['malformed_rows']}",
        "",
    ]

    if errors:
        lines += ["## Errors", *[f"- {e}" for e in errors], ""]
    else:
        lines += ["## Errors", "- None", ""]

    lines += [
        "## Execution Safety",
        f"- safe_to_open_real_trade: {result['execution_safety']['safe_to_open_real_trade']}",
        f"- private_api_used: {result['execution_safety']['private_api_used']}",
        f"- live_order_sent: {result['execution_safety']['live_order_sent']}",
        f"- research_only: {result['execution_safety']['research_only']}",
        "",
        "## Reason Codes",
        *[f"- {c}" for c in result["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in result["feeds_next"]["next_blocks"]],
    ]
    return "\n".join(lines) + "\n"


def _write_outputs(result: dict) -> None:
    _ensure_dirs()
    (STATE_DIR / "latest_schema_validation.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (REPORTS_DIR / "schema_validation_latest_report.md").write_text(
        _build_report_text(result), encoding="utf-8"
    )


def main() -> None:
    result = validate_file(DATA_FILE)
    _write_outputs(result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
