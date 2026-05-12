"""Run S11.3 Research Dataset Exporter — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.research_dataset_exporter import (
    build_research_dataset,
    run_fake_sample,
    rows_to_csv,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "simple"
EXPORTS_DIR = ROOT / "exports" / "simple"


def _ensure_dirs() -> None:
    for d in (DATA_DIR, EXPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_raw_records(symbol: str) -> list[dict]:
    path = DATA_DIR / "replay_samples.jsonl"
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
            if raw.get("symbol") == symbol:
                records.append(raw)
    return records


def _write_outputs(rows: list[dict], summary: dict) -> None:
    _ensure_dirs()
    (EXPORTS_DIR / "research_dataset.csv").write_text(
        rows_to_csv(rows), encoding="utf-8"
    )
    (EXPORTS_DIR / "research_dataset_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S11.3 Research Dataset Exporter")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        rows, summary = run_fake_sample(args.symbol)
    else:
        raw_records = _load_raw_records(args.symbol)
        rows, summary = build_research_dataset(args.symbol, raw_records)

    _write_outputs(rows, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
