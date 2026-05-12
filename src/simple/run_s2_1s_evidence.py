"""Run S2 Lightweight 1S Evidence — CLI entry point.

DUZELTME: latest_flow_state.json'daki gercek trade verilerini okur.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from src.simple.lightweight_1s_evidence_engine import build_evidence, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"

FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_flow_state() -> dict:
    try:
        if FLOW_STATE_PATH.exists():
            return json.loads(FLOW_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _extract_ticks_from_flow(flow: dict) -> tuple[list, int]:
    """
    flow_state'deki latest_bucket'tan tick listesi uret.
    buy_volume ve sell_volume'u tek bir sentetik tick'e donustur.
    missing_seconds: bucket icinde kac saniye veri eksik — bilinmiyor, 0 kabul ediyoruz.
    """
    bucket = flow.get("latest_bucket", {})
    if not bucket:
        return [], 60

    buy_volume = float(bucket.get("buy_volume", 0.0))
    sell_volume = float(bucket.get("sell_volume", 0.0))
    last_price = float(bucket.get("last_price", 0.0) or bucket.get("vwap", 0.0))
    trade_count = int(bucket.get("trade_count", 0))
    buy_trade_count = int(bucket.get("buy_trade_count", 0))
    sell_trade_count = int(bucket.get("sell_trade_count", buy_trade_count))

    if last_price == 0.0 or (buy_volume == 0.0 and sell_volume == 0.0):
        return [], 60

    ticks = []

    # Buy volume'u buy tick'lerine dagit
    if buy_volume > 0.0 and buy_trade_count > 0:
        qty_per_trade = round(buy_volume / buy_trade_count, 8)
        for _ in range(buy_trade_count):
            ticks.append({"price": last_price, "side": "BUY", "qty": qty_per_trade})
    elif buy_volume > 0.0:
        ticks.append({"price": last_price, "side": "BUY", "qty": buy_volume})

    # Sell volume'u sell tick'lerine dagit
    if sell_volume > 0.0 and sell_trade_count > 0:
        qty_per_trade = round(sell_volume / sell_trade_count, 8)
        for _ in range(sell_trade_count):
            ticks.append({"price": last_price, "side": "SELL", "qty": qty_per_trade})
    elif sell_volume > 0.0:
        ticks.append({"price": last_price, "side": "SELL", "qty": sell_volume})

    # Buckets_built sayisina gore missing seconds tahmini
    buckets_built = flow.get("event_counters", {}).get("buckets_built", 0)
    missing_seconds = max(0, 60 - min(60, buckets_built)) if buckets_built < 60 else 0

    return ticks, missing_seconds


def _write_outputs(evidence: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_1s_evidence.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s2_1s_evidence_state.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "1s_evidence.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(evidence) + "\n")

    ev = evidence["evidence"]
    tf = evidence["trade_flow"]
    dq = evidence["data_quality"]
    lines = [
        f"# S2 Lightweight 1S Evidence — {evidence['symbol']}",
        "",
        f"**Timestamp:** {evidence['timestamp_utc']}",
        f"**Source Mode:** {evidence['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Evidence",
        f"- Score: {ev['evidence_score']}",
        f"- Label: {ev['evidence_label']}",
        f"- Strength: {ev['evidence_strength']}",
        f"- Micro Winner: {ev['micro_winner']}",
        "",
        "## Trade Flow",
        f"- Buy Volume: {tf['buy_volume']}",
        f"- Sell Volume: {tf['sell_volume']}",
        f"- Delta: {tf['delta']}",
        f"- Delta Ratio: {tf['delta_ratio']}",
        f"- Trade Count: {tf['trade_count']}",
        "",
        "## Reason Codes",
        *[f"- {rc}" for rc in evidence["reason_codes"]],
    ]
    (REPORTS_DIR / "s2_1s_evidence_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S2 Lightweight 1S Evidence")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        evidence = run_fake_sample(args.symbol)
    else:
        flow = _load_flow_state()
        if flow:
            ticks, missing_seconds = _extract_ticks_from_flow(flow)
            if ticks:
                evidence = build_evidence(
                    args.symbol, ticks, missing_seconds, "FLOW_STATE_LIVE"
                )
            else:
                print("[S2] flow_state var ama tick uretilemiyor", file=sys.stderr)
                evidence = build_evidence(args.symbol, [], 60, "NO_DATA")
        else:
            print("[S2] latest_flow_state.json yok", file=sys.stderr)
            evidence = build_evidence(args.symbol, [], 60, "NO_DATA")

    _write_outputs(evidence)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
