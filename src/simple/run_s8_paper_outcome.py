"""Run S8 Paper Outcome Tracker — CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib

from src.simple.paper_outcome_tracker import build_paper_outcome, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_inputs() -> tuple:
    s1_path = STATE_DIR / "latest_market_truth.json"
    s7_path = STATE_DIR / "latest_decision.json"

    s1 = None
    if s1_path.exists():
        try:
            raw = json.loads(s1_path.read_text(encoding="utf-8"))
            oc = raw["official_candle"]
            s1 = {
                "available": True,
                "official_high": float(oc["high"]),
                "official_low": float(oc["low"]),
                "official_close": float(oc["close"]),
                "is_official_binance_1m": bool(oc.get("is_official_binance_1m", False)),
            }
        except (KeyError, ValueError, json.JSONDecodeError):
            s1 = None

    s7 = None
    if s7_path.exists():
        try:
            raw = json.loads(s7_path.read_text(encoding="utf-8"))
            dg = raw["decision_gate"]
            tp = raw["trade_plan"]
            rr = raw["risk_reward"]
            s7 = {
                "available": True,
                "decision": str(dg["decision"]),
                "paper_eligible": bool(dg["paper_eligible"]),
                "edge_eligible_if_outcome_closes": bool(dg["edge_eligible_if_outcome_closes"]),
                "trade_direction": str(tp["trade_direction"]),
                "entry_price": tp["entry_price"],
                "stop_loss": tp["stop_loss"],
                "tp1": tp["tp1"],
                "tp2": tp["tp2"],
                "rr_tp1": rr["rr_tp1"],
                "rr_tp2": rr["rr_tp2"],
            }
        except (KeyError, json.JSONDecodeError):
            s7 = None

    return s1, s7


def _write_outputs(po: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_outcome.json").write_text(
        json.dumps(po, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s8_paper_outcome_state.json").write_text(
        json.dumps(po, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "paper_outcome.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(po) + "\n")

    inp = po["input_status"]
    dr = po["decision_reference"]
    oc = po["outcome_check"]
    lc = po["lifecycle"]
    r = po["result"]
    ee = po["edge_eligibility"]
    es = po["execution_safety"]
    dq = po["data_quality"]
    lines = [
        f"# S8 Paper Outcome Tracker — {po['symbol']}",
        "",
        f"**Timestamp:** {po['timestamp_utc']}",
        f"**Source Mode:** {po['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Input Status",
        f"- Market Truth: {inp['market_truth_available']}",
        f"- Decision: {inp['decision_available']}",
        f"- Missing: {inp['missing_inputs']}",
        "",
        "## Decision Reference (from S7)",
        f"- Decision: {dr['decision']}",
        f"- Paper Eligible: {dr['paper_eligible']}",
        f"- Direction: {dr['trade_direction']}",
        f"- Entry: {dr['entry_price']}",
        f"- Stop Loss: {dr['stop_loss']}",
        f"- TP1: {dr['tp1']}",
        f"- TP2: {dr['tp2']}",
        f"- RR TP1: {dr['rr_tp1']}",
        f"- RR TP2: {dr['rr_tp2']}",
        "",
        "## Outcome Check",
        f"- Official High: {oc['official_high']}",
        f"- Official Low: {oc['official_low']}",
        f"- Official Close: {oc['official_close']}",
        f"- Check Method: {oc['check_method']}",
        "",
        "## Lifecycle",
        f"- Trade Opened: {lc['trade_opened']}",
        f"- Trade Status: {lc['trade_status']}",
        "",
        "## Result",
        f"- Outcome: {r['outcome']}",
        f"- Reason: {r['outcome_reason']}",
        f"- TP1 Hit: {r['tp1_hit']}",
        f"- TP2 Hit: {r['tp2_hit']}",
        f"- Stop Hit: {r['stop_hit']}",
        f"- Ambiguous: {r['ambiguous_hit']}",
        f"- Realized RR: {r['realized_rr']}",
        "",
        "## Edge Eligibility",
        f"- edge_eligible: {ee['edge_eligible']}",
        f"- feeds_edge_stats: {ee['feeds_edge_stats']}",
        "",
        "## Execution Safety",
        f"- safe_to_open_real_trade: {es['safe_to_open_real_trade']}",
        f"- private_api_used: {es['private_api_used']}",
        f"- live_order_sent: {es['live_order_sent']}",
        "",
        "## Reason Codes",
        *[f"- {code}" for code in po["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in po["feeds_next"]["next_blocks"]],
    ]
    (REPORTS_DIR / "s8_paper_outcome_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S8 Paper Outcome Tracker")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        po = run_fake_sample(args.symbol)
    else:
        s1, s7 = _load_inputs()
        po = build_paper_outcome(args.symbol, s1, s7, "STATE_FILE")

    _write_outputs(po)
    print(json.dumps(po, indent=2))


if __name__ == "__main__":
    main()
