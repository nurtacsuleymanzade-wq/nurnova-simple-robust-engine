"""Run S6 Scenario + Setup Candidate — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.setup_candidate_engine import build_setup_candidate, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_inputs() -> tuple:
    s1_path = STATE_DIR / "latest_market_truth.json"
    s2_path = STATE_DIR / "latest_1s_evidence.json"
    s3_path = STATE_DIR / "latest_hybrid_candle_dna.json"
    s4_path = STATE_DIR / "latest_quality_weight.json"
    s5_path = STATE_DIR / "latest_liquidity_structure.json"

    s1 = None
    if s1_path.exists():
        try:
            raw = json.loads(s1_path.read_text(encoding="utf-8"))
            s1 = {
                "available": True,
                "current_price": raw["market_truth"]["current_price"],
                "is_official_binance_1m": raw["official_candle"].get(
                    "is_official_binance_1m", False
                ),
            }
        except (KeyError, json.JSONDecodeError):
            s1 = None

    s2 = None
    if s2_path.exists():
        try:
            raw = json.loads(s2_path.read_text(encoding="utf-8"))
            s2 = {
                "available": True,
                "evidence_label": raw["evidence"]["evidence_label"],
                "micro_winner": raw["evidence"]["micro_winner"],
                "evidence_score": raw["evidence"]["evidence_score"],
            }
        except (KeyError, json.JSONDecodeError):
            s2 = None

    s3 = None
    if s3_path.exists():
        try:
            raw = json.loads(s3_path.read_text(encoding="utf-8"))
            s3 = {
                "available": True,
                "candle_direction": raw["shape"]["candle_direction"],
                "intent_label": raw["candle_intent"]["intent_label"],
                "intent_score": raw["candle_intent"]["intent_score"],
                "shape_label": raw["shape"]["shape_label"],
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

    s5 = None
    if s5_path.exists():
        try:
            raw = json.loads(s5_path.read_text(encoding="utf-8"))
            s5 = {
                "available": True,
                "structure_bias": raw["structure"]["structure_bias"],
                "structure_event": raw["structure"]["structure_event"],
                "structure_score": raw["structure"]["structure_score"],
                "draw_on_liquidity": raw["liquidity_bias"]["draw_on_liquidity"],
                "liquidity_context_label": raw["liquidity_bias"][
                    "liquidity_context_label"
                ],
                "liquidity_score": raw["liquidity_bias"]["liquidity_score"],
                "context_label": raw["simple_context"]["context_label"],
                "context_score": raw["simple_context"]["context_score"],
                "usable_for_setup_candidate": raw["simple_context"][
                    "usable_for_setup_candidate"
                ],
            }
        except (KeyError, json.JSONDecodeError):
            s5 = None

    return s1, s2, s3, s4, s5


def _write_outputs(sc: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_setup_candidate.json").write_text(
        json.dumps(sc, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s6_setup_candidate_state.json").write_text(
        json.dumps(sc, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "setup_candidate.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sc) + "\n")

    inp = sc["input_status"]
    sn = sc["scenario"]
    su = sc["setup_candidate"]
    ea = sc["evidence_alignment"]
    qc = sc["quality_context"]
    rk = sc["risk"]
    dq = sc["data_quality"]
    lines = [
        f"# S6 Scenario + Setup Candidate — {sc['symbol']}",
        "",
        f"**Timestamp:** {sc['timestamp_utc']}",
        f"**Source Mode:** {sc['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Input Status",
        f"- Market Truth: {inp['market_truth_available']}",
        f"- Evidence: {inp['evidence_available']}",
        f"- Hybrid Candle: {inp['hybrid_candle_available']}",
        f"- Quality Weight: {inp['quality_weight_available']}",
        f"- Liquidity/Structure: {inp['liquidity_structure_available']}",
        f"- Missing: {inp['missing_inputs']}",
        "",
        "## Scenario",
        f"- Type: {sn['scenario_type']}",
        f"- Direction: {sn['scenario_direction']}",
        f"- Score: {sn['scenario_score']}",
        f"- Label: {sn['scenario_label']}",
        f"- Reason: {sn['scenario_reason']}",
        "",
        "## Setup Candidate",
        f"- Type: {su['setup_type']}",
        f"- Direction: {su['setup_direction']}",
        f"- Raw Score: {su['raw_setup_score']}",
        f"- Quality Adjusted Score: {su['quality_adjusted_setup_score']}",
        f"- Grade: {su['setup_grade']}",
        f"- Status: {su['setup_status']}",
        f"- Reason: {su['setup_reason']}",
        "",
        "## Evidence Alignment",
        f"- Flow: {ea['flow_direction']}",
        f"- Candle Intent: {ea['candle_intent']}",
        f"- Structure Bias: {ea['structure_bias']}",
        f"- Liquidity Bias: {ea['liquidity_bias']}",
        f"- Alignment Label: {ea['alignment_label']}",
        f"- Alignment Score: {ea['alignment_score']}",
        "",
        "## Quality Context",
        f"- Inherited Weight: {qc['inherited_quality_weight']}",
        f"- Inherited Label: {qc['inherited_quality_label']}",
        f"- Allows Setup Candidate: {qc['quality_allows_setup_candidate']}",
        "",
        "## Risk",
        f"- Risk Label: {rk['setup_risk_label']}",
        f"- Trap Risk: {rk['trap_risk']}",
        f"- Conflict Risk: {rk['conflict_risk']}",
        f"- Reason: {rk['reason']}",
        "",
        "## Reason Codes",
        *[f"- {code}" for code in sc["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in sc["feeds_next"]["next_blocks"]],
    ]
    (REPORTS_DIR / "s6_setup_candidate_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S6 Scenario + Setup Candidate")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        sc = run_fake_sample(args.symbol)
    else:
        s1, s2, s3, s4, s5 = _load_inputs()
        sc = build_setup_candidate(args.symbol, s1, s2, s3, s4, s5, "STATE_FILE")

    _write_outputs(sc)
    print(json.dumps(sc, indent=2))


if __name__ == "__main__":
    main()
