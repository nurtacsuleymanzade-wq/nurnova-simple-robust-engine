"""Run S1 Official Market Truth — CLI entry point.

DUZELTME: latest_flow_state.json dosyasindan canli fiyat ve ticker okur.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from src.simple.market_truth_engine import build_truth, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"

FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_flow_state() -> dict:
    """latest_flow_state.json dosyasini oku."""
    try:
        if FLOW_STATE_PATH.exists():
            return json.loads(FLOW_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _extract_candle_and_ticker(flow: dict) -> tuple:
    """
    flow_state'den candle ve ticker yapi cikart.
    latest_bucket icindeki verileri kullanir.
    """
    bucket = flow.get("latest_bucket", {})
    if not bucket:
        return None, None

    last_price = bucket.get("last_price") or bucket.get("vwap")
    best_bid   = bucket.get("best_bid")
    best_ask   = bucket.get("best_ask")

    if not last_price:
        return None, None

    # Candle yapisi: market_truth_engine'in bekledigi format
    candle = {
        "open":          last_price,
        "high":          last_price,
        "low":           last_price,
        "close":         last_price,
        "volume":        bucket.get("total_volume", 0.0),
        "open_time_ms":  0,
        "close_time_ms": 0,
    }

    # Ticker yapisi
    if best_bid and best_ask:
        ticker = {
            "best_bid": best_bid,
            "best_ask": best_ask,
        }
    else:
        ticker = None

    return candle, ticker


def _write_outputs(truth: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_market_truth.json").write_text(
        json.dumps(truth, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s1_market_truth_state.json").write_text(
        json.dumps(truth, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "market_truth.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(truth) + "\n")

    dq   = truth["data_quality"]
    mt   = truth["market_truth"]
    cons = truth["consistency"]
    pt   = truth["price_truth"]

    lines = [
        f"# S1 Official Market Truth — {truth['symbol']}",
        "",
        f"**Timestamp:** {truth['timestamp_utc']}",
        f"**Source Mode:** {truth['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Price Truth",
        f"- Current Price: {mt['current_price']}",
        f"- Best Bid: {pt.get('best_bid')}",
        f"- Best Ask: {pt.get('best_ask')}",
        f"- Spread: {pt.get('spread')}",
        f"- High: {mt['official_high']}",
        f"- Low: {mt['official_low']}",
        f"- Close: {mt['official_close']}",
        "",
        "## Consistency",
        f"- Label: {cons['consistency_label']}",
        f"- Close vs Mid Diff %: {cons['close_vs_mid_diff_pct']}",
        "",
        "## Reason Codes",
        *[f"- {rc}" for rc in truth["reason_codes"]],
        "",
        "## Feeds Next",
        *[f"- {b}" for b in truth["feeds_next"]["next_blocks"]],
    ]
    (REPORTS_DIR / "s1_market_truth_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S1 Official Market Truth")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        truth = run_fake_sample(args.symbol)
    else:
        # Canli: flow state'den oku
        flow = _load_flow_state()
        if flow:
            candle, ticker = _extract_candle_and_ticker(flow)
            if candle:
                truth = build_truth(args.symbol, candle, ticker, "FLOW_STATE_LIVE")
            else:
                print("[S1] flow_state var ama fiyat yok — NO_DATA", file=sys.stderr)
                truth = build_truth(args.symbol, None, None, "NO_DATA")
        else:
            print("[S1] latest_flow_state.json yok — NO_DATA", file=sys.stderr)
            truth = build_truth(args.symbol, None, None, "NO_DATA")

    _write_outputs(truth)
    print(json.dumps(truth, indent=2))


if __name__ == "__main__":
    main()
