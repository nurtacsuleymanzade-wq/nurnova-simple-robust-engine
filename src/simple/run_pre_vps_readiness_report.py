"""Run S11.4 Pre-VPS Readiness Report — CLI entry point.

Usage:
    python -m src.simple.run_pre_vps_readiness_report

Outputs:
    state/simple/latest_pre_vps_readiness.json
    reports/simple/pre_vps_readiness_latest_report.md
"""

from __future__ import annotations

import json
import pathlib

from src.simple.pre_vps_readiness_report import run_readiness_audit

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _build_report(result: dict) -> str:
    safety = result["execution_safety"]
    lines = [
        f"# S11.4 Pre-VPS Readiness Report — {result['symbol']}",
        "",
        f"**Timestamp:** {result['timestamp_utc']}",
        f"**VPS Ready:** {result['vps_ready']}",
        f"**Readiness Score:** {result['readiness_score']}",
        f"**Recommended Next Step:** {result['recommended_next_step']}",
        "",
        "## Check Results",
    ]
    for check in result["check_results"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- [{status}] {check['check']}")
        for item in check["critical_items"]:
            lines.append(f"  - CRITICAL: {item}")
        for w in check["warnings"]:
            lines.append(f"  - WARNING: {w}")

    lines += [
        "",
        "## Critical Missing Items",
    ]
    if result["critical_missing_items"]:
        for item in result["critical_missing_items"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines += [
        "",
        "## Warnings",
    ]
    if result["warnings"]:
        for w in result["warnings"]:
            lines.append(f"- {w}")
    else:
        lines.append("- None")

    lines += [
        "",
        "## Execution Safety",
        f"- safe_to_open_real_trade: {safety['safe_to_open_real_trade']}",
        f"- private_api_used: {safety['private_api_used']}",
        f"- live_order_sent: {safety['live_order_sent']}",
        f"- research_only: {safety['research_only']}",
        "",
        "## Reason Codes",
        *[f"- {c}" for c in result["reason_codes"]],
    ]
    return "\n".join(lines) + "\n"


def _write_outputs(result: dict) -> None:
    _ensure_dirs()
    (STATE_DIR / "latest_pre_vps_readiness.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (REPORTS_DIR / "pre_vps_readiness_latest_report.md").write_text(
        _build_report(result), encoding="utf-8"
    )


def main() -> None:
    result = run_readiness_audit("BTCUSDT")
    _write_outputs(result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
