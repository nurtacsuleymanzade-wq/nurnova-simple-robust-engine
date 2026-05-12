"""Run S5 Liquidity + Structure Context — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from src.simple.liquidity_structure_engine import build_liquidity_structure, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_inputs() -> tuple:
    s1_path = STATE_DIR / "latest_market_truth.json"
    s3_path = STATE_DIR / "latest_hybrid_candle_dna.json"
    s4_path = STATE_DIR / "latest_quality_weight.json"

    s1 = None
    if s1_path.exists():
        try:
            raw = json.loads(s1_path.read_text(encoding="utf-8"))
            s1 = {
                "available": True,
                "current_price": raw["market_truth"]["current_price"],
                "range_high": raw["official_candle"]["high"],
                "range_low": raw["official_candle"]["low"],
            }
        except (KeyError, json.JSONDecodeError):
            s1 = None

    s3 = None
    if s3_path.exists():
        try:
            raw = json.loads(s3_path.read_text(encoding="utf-8"))
            s3 = {
                "available": True,
                "candle_direction": raw["shape"]["candle_direction"],
                "body_pct": raw["shape"]["body_pct"],
                "upper_wick_pct": raw["shape"]["upper_wick_pct"],
                "lower_wick_pct": raw["shape"]["lower_wick_pct"],
                "shape_label": raw["shape"]["shape_label"],
                "intent_score": raw["candle_intent"]["intent_score"],
                "intent_label": raw["candle_intent"]["intent_label"],
            }
        except (KeyError, json.JSONDecodeError):
            s3 = None

    s4 = None
    if s4_path.exists():
        try:
            raw = json.loads(s4_path.read_text(encoding="utf-8"))
            s4 = {
                "available": True,
                "quality_weight": raw["quality_weight"]["quality_weight"],
                "quality_label": raw["quality_weight"]["quality_label"],
            }
        except (KeyError, json.JSONDecodeError):
            s4 = None

    return s1, s3, s4


def _write_outputs(ls: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_liquidity_structure.json").write_text(
        json.dumps(ls, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s5_liquidity_structure_state.json").write_text(
        json.dumps(ls, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "liquidity_structure.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ls) + "\n")

    inp = ls["input_status"]
    rng = ls["range_context"]
    st = ls["structure"]
    lb = ls["liquidity_bias"]
    ctx = ls["simple_context"]
    qc = ls["quality_context"]
    dq = ls["data_quality"]
    lines = [
        f"# S5 Liquidity + Structure Context — {ls['symbol']}",
        "",
        f"**Timestamp:** {ls['timestamp_utc']}",
        f"**Source Mode:** {ls['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Input Status",
        f"- Market Truth: {inp['market_truth_available']}",
        f"- Hybrid Candle: {inp['hybrid_candle_available']}",
        f"- Quality Weight: {inp['quality_weight_available']}",
        f"- Missing: {inp['missing_inputs']}",
        "",
        "## Range Context",
        f"- Current Price: {rng['current_price']}",
        f"- Range High: {rng['range_high']}",
        f"- Range Low: {rng['range_low']}",
        f"- Range Mid: {rng['range_mid']}",
        f"- Price Zone: {rng['price_zone']}",
        "",
        "## Structure",
        f"- Bias: {st['structure_bias']}",
        f"- Event: {st['structure_event']}",
        f"- Score: {st['structure_score']}",
        "",
        "## Liquidity Bias",
        f"- Draw On Liquidity: {lb['draw_on_liquidity']}",
        f"- Context Label: {lb['liquidity_context_label']}",
        f"- Liquidity Score: {lb['liquidity_score']}",
        "",
        "## Simple Context",
        f"- Label: {ctx['context_label']}",
        f"- Score: {ctx['context_score']}",
        f"- Usable For Setup: {ctx['usable_for_setup_candidate']}",
        "",
        "## Quality Context",
        f"- Inherited Quality Weight: {qc['inherited_quality_weight']}",
        f"- Quality Label: {qc['quality_label']}",
        f"- Quality Adjusted Score: {qc['quality_adjusted_context_score']}",
        "",
        "## Liquidity Notes",
        *[f"- {note}" for note in ls["liquidity_notes"]],
        "",
        "## Reason Codes",
        *[f"- {code}" for code in ls["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in ls["feeds_next"]["next_blocks"]],
    ]
    (REPORTS_DIR / "s5_liquidity_structure_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S5 Liquidity + Structure Context")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        ls = run_fake_sample(args.symbol)
    else:
        s1, s3, s4 = _load_inputs()
        ls = build_liquidity_structure(args.symbol, s1, s3, s4, "STATE_FILE")

    _write_outputs(ls)
    print(json.dumps(ls, indent=2))


if __name__ == "__main__":
    main()
