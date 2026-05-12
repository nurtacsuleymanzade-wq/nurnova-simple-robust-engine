"""Run S7 Trade Plan + Decision Gate — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.trade_plan_decision_engine import build_trade_plan_decision, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_inputs() -> tuple:
    s1_path = STATE_DIR / "latest_market_truth.json"
    s4_path = STATE_DIR / "latest_quality_weight.json"
    s5_path = STATE_DIR / "latest_liquidity_structure.json"
    s6_path = STATE_DIR / "latest_setup_candidate.json"

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
                "nearest_support": raw["nearest_support"],
                "nearest_resistance": raw["nearest_resistance"],
                "structure_bias": raw["structure"]["structure_bias"],
            }
        except (KeyError, json.JSONDecodeError):
            s5 = None

    s6 = None
    if s6_path.exists():
        try:
            raw = json.loads(s6_path.read_text(encoding="utf-8"))
            sc = raw["setup_candidate"]
            s6 = {
                "available": True,
                "setup_type": sc["setup_type"],
                "setup_direction": sc["setup_direction"],
                "setup_grade": sc["setup_grade"],
                "setup_status": sc["setup_status"],
                "quality_adjusted_setup_score": sc["quality_adjusted_setup_score"],
            }
        except (KeyError, json.JSONDecodeError):
            s6 = None

    return s1, s4, s5, s6


def _write_outputs(td: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_decision.json").write_text(
        json.dumps(td, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s7_trade_plan_decision_state.json").write_text(
        json.dumps(td, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "trade_plan_decision.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(td) + "\n")

    inp = td["input_status"]
    sr = td["setup_reference"]
    tp = td["trade_plan"]
    rr = td["risk_reward"]
    dg = td["decision_gate"]
    qc = td["quality_context"]
    es = td["execution_safety"]
    dq = td["data_quality"]
    lines = [
        f"# S7 Trade Plan + Decision Gate — {td['symbol']}",
        "",
        f"**Timestamp:** {td['timestamp_utc']}",
        f"**Source Mode:** {td['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Input Status",
        f"- Market Truth: {inp['market_truth_available']}",
        f"- Quality Weight: {inp['quality_weight_available']}",
        f"- Liquidity/Structure: {inp['liquidity_structure_available']}",
        f"- Setup Candidate: {inp['setup_candidate_available']}",
        f"- Missing: {inp['missing_inputs']}",
        "",
        "## Setup Reference (from S6)",
        f"- Type: {sr['setup_type']}",
        f"- Direction: {sr['setup_direction']}",
        f"- Grade: {sr['setup_grade']}",
        f"- Status: {sr['setup_status']}",
        f"- QA Score: {sr['quality_adjusted_setup_score']}",
        "",
        "## Trade Plan",
        f"- Direction: {tp['trade_direction']}",
        f"- Entry: {tp['entry_price']}",
        f"- Stop Loss: {tp['stop_loss']}",
        f"- TP1: {tp['tp1']}",
        f"- TP2: {tp['tp2']}",
        f"- Invalidation: {tp['invalidation_price']}",
        f"- Plan Status: {tp['plan_status']}",
        "",
        "## Risk / Reward",
        f"- Risk Abs: {rr['risk_abs']}",
        f"- Reward TP1: {rr['reward_tp1_abs']}",
        f"- Reward TP2: {rr['reward_tp2_abs']}",
        f"- RR TP1: {rr['rr_tp1']}",
        f"- RR TP2: {rr['rr_tp2']}",
        f"- RR Label: {rr['rr_label']}",
        "",
        "## Decision Gate",
        f"- Decision: {dg['decision']}",
        f"- Reason: {dg['decision_reason']}",
        f"- Paper Eligible: {dg['paper_eligible']}",
        f"- Edge Eligible If Closes: {dg['edge_eligible_if_outcome_closes']}",
        "",
        "## Quality Context",
        f"- Inherited Weight: {qc['inherited_quality_weight']}",
        f"- Inherited Label: {qc['inherited_quality_label']}",
        f"- Quality Adjusted Decision Score: {qc['quality_adjusted_decision_score']}",
        "",
        "## Execution Safety",
        f"- safe_to_open_real_trade: {es['safe_to_open_real_trade']}",
        f"- private_api_used: {es['private_api_used']}",
        f"- live_order_sent: {es['live_order_sent']}",
        "",
        "## Reason Codes",
        *[f"- {code}" for code in td["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in td["feeds_next"]["next_blocks"]],
    ]
    (REPORTS_DIR / "s7_trade_plan_decision_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S7 Trade Plan + Decision Gate")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        td = run_fake_sample(args.symbol)
    else:
        s1, s4, s5, s6 = _load_inputs()
        td = build_trade_plan_decision(args.symbol, s1, s4, s5, s6, "STATE_FILE")

    _write_outputs(td)
    print(json.dumps(td, indent=2))


if __name__ == "__main__":
    main()
