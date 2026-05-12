"""Run S9 Edge Stats — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.edge_stats_engine import build_edge_stats, run_fake_sample, parse_s8_record

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_records(symbol: str) -> list[dict]:
    path = DATA_DIR / "paper_outcome.jsonl"
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if raw.get("symbol") != symbol:
                continue
            parsed = parse_s8_record(raw)
            if parsed is not None:
                records.append(parsed)
    return records


def _write_outputs(es: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_edge_stats.json").write_text(
        json.dumps(es, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s9_edge_stats_state.json").write_text(
        json.dumps(es, indent=2), encoding="utf-8"
    )

    si = es["sample_info"]
    dq = es["data_quality"]
    lines = [
        f"# S9 Edge Stats — {es['symbol']}",
        "",
        f"**Timestamp:** {es['timestamp_utc']}",
        f"**Source Mode:** {es['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Sample Info",
        f"- Total Records Read: {si['total_records_read']}",
        f"- Edge Eligible: {si['edge_eligible_count']}",
        f"- Excluded: {si['excluded_count']}",
        "",
        "## Edge Stats",
        f"- edge_eligible_count: {es['edge_eligible_count']}",
        f"- win_count: {es['win_count']}",
        f"- loss_count: {es['loss_count']}",
        f"- win_rate: {es['win_rate']}",
        f"- avg_rr_realized: {es['avg_rr_realized']}",
        f"- edge_score: {es['edge_score']}",
        "",
        "## Data Quality",
        f"- Level: {dq['level']}",
        f"- Score: {dq['score']}",
        f"- Issues: {dq['issues']}",
        "",
        "## Reason Codes",
        *[f"- {code}" for code in es["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in es["feeds_next"]["next_blocks"]],
    ]
    (REPORTS_DIR / "s9_edge_stats_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S9 Edge Stats")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        es = run_fake_sample(args.symbol)
    else:
        records = _load_records(args.symbol)
        es = build_edge_stats(args.symbol, records, "STATE_FILE")

    _write_outputs(es)
    print(json.dumps(es, indent=2))


if __name__ == "__main__":
    main()
