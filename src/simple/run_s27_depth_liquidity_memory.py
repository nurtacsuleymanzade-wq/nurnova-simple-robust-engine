"""Run S27 Depth Liquidity Memory — CLI entry point.

Okur: state/simple/latest_depth_state.json
Uretir: state/simple/latest_depth_liquidity_memory.json
        data/simple/depth_liquidity_memory_history.jsonl
        reports/simple/s27_depth_liquidity_memory_latest_report.md

Bu blok pipeline icerisinde S15/S16'dan ONCE calisir.
Ciktisi senaryo ve entry trigger motorlarina "duvar nerede" bilgisi saglar.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT      = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR  = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"

DEPTH_STATE_PATH = STATE_DIR / "latest_depth_state.json"
OUTPUT_PATH      = STATE_DIR / "latest_depth_liquidity_memory.json"
JSONL_PATH       = DATA_DIR  / "depth_liquidity_memory_history.jsonl"
REPORT_PATH      = REPORTS_DIR / "s27_depth_liquidity_memory_latest_report.md"


def _load_json(path: pathlib.Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def build_depth_memory() -> dict:
    depth_state = _load_json(DEPTH_STATE_PATH)
    depth       = depth_state.get("latest_depth", {})

    if not depth:
        result = {
            "timestamp_utc":     _utc_now(),
            "block_id":          "S27_DEPTH_LIQUIDITY_MEMORY",
            "symbol":            "BTCUSDT",
            "source":            {"source_mode": "NO_DEPTH_DATA"},
            "available":         False,
            "bid_wall":          {"has_wall": False, "wall_price": None, "wall_strength": 0.0},
            "ask_wall":          {"has_wall": False, "wall_price": None, "wall_strength": 0.0},
            "imbalance":         {"imbalance_label": "UNKNOWN", "dominant_side": "NEUTRAL"},
            "sweep_risk":        {"sweep_risk": "UNKNOWN"},
            "mid_price":         None,
            "liquidity_bias":    "NEUTRAL",
            "draw_on_liquidity": "UNKNOWN",
            "reason_codes":      ["NO_DEPTH_DATA", "SAFE_TO_OPEN_REAL_TRADE_FALSE"],
            "data_quality":      {"level": "MISSING", "score": 0.0},
            "feeds_next":        {"next_blocks": ["S15_FLOW_TO_SETUP_CONTEXT", "S16_SCENARIO_ENTRY_TRIGGER"]},
            "execution_safety":  {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False},
        }
        return result

    bid_cluster  = depth.get("bid_cluster", {})
    ask_cluster  = depth.get("ask_cluster", {})
    imbalance    = depth.get("imbalance", {})
    sweep        = depth.get("sweep_risk", {})
    mid_price    = depth.get("mid_price")

    # Likidite yonu: hangi taraf agir?
    dominant = imbalance.get("dominant_side", "NEUTRAL")
    if dominant == "BID":
        liquidity_bias    = "LONG"   # bid baskisi → fiyat yukari cekiliyor
        draw_on_liquidity = "ABOVE"  # ask tarafindaki likiditeye dogru
    elif dominant == "ASK":
        liquidity_bias    = "SHORT"
        draw_on_liquidity = "BELOW"
    else:
        liquidity_bias    = "NEUTRAL"
        draw_on_liquidity = "BOTH"

    # Duvar mesafe bilgisi (SL referansi icin)
    bid_wall_price = bid_cluster.get("wall_price")
    ask_wall_price = ask_cluster.get("wall_price")

    reason_codes = [
        f"SYMBOL_BTCUSDT",
        f"IMBALANCE_{imbalance.get('imbalance_label', 'UNKNOWN')}",
        f"SWEEP_{sweep.get('sweep_risk', 'UNKNOWN')}",
        f"LIQUIDITY_BIAS_{liquidity_bias}",
        "SOURCE_LIVE_DEPTH",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]

    if bid_cluster.get("has_wall"):
        reason_codes.append("BID_WALL_DETECTED")
    if ask_cluster.get("has_wall"):
        reason_codes.append("ASK_WALL_DETECTED")
    if sweep.get("sweep_risk") in ("IMMINENT", "HIGH"):
        reason_codes.append("SWEEP_RISK_HIGH")

    result = {
        "timestamp_utc": _utc_now(),
        "block_id":      "S27_DEPTH_LIQUIDITY_MEMORY",
        "symbol":        "BTCUSDT",
        "source":        {"source_mode": "LIVE_DEPTH"},
        "available":     True,
        "mid_price":     mid_price,

        "bid_wall": {
            "has_wall":      bid_cluster.get("has_wall", False),
            "wall_price":    bid_cluster.get("wall_price"),
            "wall_notional": bid_cluster.get("wall_notional"),
            "wall_strength": bid_cluster.get("wall_strength", 0.0),
            "total_notional": bid_cluster.get("total_notional", 0.0),
        },
        "ask_wall": {
            "has_wall":      ask_cluster.get("has_wall", False),
            "wall_price":    ask_cluster.get("wall_price"),
            "wall_notional": ask_cluster.get("wall_notional"),
            "wall_strength": ask_cluster.get("wall_strength", 0.0),
            "total_notional": ask_cluster.get("total_notional", 0.0),
        },

        "imbalance":         imbalance,
        "sweep_risk":        sweep,
        "liquidity_bias":    liquidity_bias,
        "draw_on_liquidity": draw_on_liquidity,

        # SL referansi: en yakin duvar fiyatlari
        "structural_sl_reference": {
            "long_sl_reference":  bid_wall_price,  # long icin SL: bid duvarin altı
            "short_sl_reference": ask_wall_price,  # short icin SL: ask duvarin ustu
            "note": "SL buradan hesaplanmali, yuzde bazli degil"
        },

        "reason_codes":  reason_codes,
        "data_quality":  {"level": "OK", "score": 1.0, "issues": []},
        "feeds_next":    {"next_blocks": ["S15_FLOW_TO_SETUP_CONTEXT", "S16_SCENARIO_ENTRY_TRIGGER"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used":        False,
            "live_order_sent":         False,
        },
    }

    return result


def main() -> None:
    result = build_depth_memory()

    _write(OUTPUT_PATH, result)

    # JSONL'e ekle
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False) + "\n")

    # Rapor
    d = result
    bw = d["bid_wall"]
    aw = d["ask_wall"]
    sw = d["sweep_risk"]
    lines = [
        f"# S27 Depth Liquidity Memory — BTCUSDT",
        f"",
        f"**Timestamp:** {d['timestamp_utc']}",
        f"**Available:** {d['available']}",
        f"**Mid Price:** {d['mid_price']}",
        f"",
        f"## Bid Wall",
        f"- Has Wall: {bw['has_wall']}",
        f"- Wall Price: {bw['wall_price']}",
        f"- Wall Strength: {bw['wall_strength']}x avg",
        f"",
        f"## Ask Wall",
        f"- Has Wall: {aw['has_wall']}",
        f"- Wall Price: {aw['wall_price']}",
        f"- Wall Strength: {aw['wall_strength']}x avg",
        f"",
        f"## Liquidity",
        f"- Imbalance: {d['imbalance'].get('imbalance_label')}",
        f"- Bias: {d['liquidity_bias']}",
        f"- Draw On: {d['draw_on_liquidity']}",
        f"- Sweep Risk: {sw.get('sweep_risk')} (side={sw.get('nearest_wall_side')}, dist={sw.get('distance_pct')}%)",
        f"",
        f"## SL Reference",
        f"- Long SL ref: {d['structural_sl_reference']['long_sl_reference']}",
        f"- Short SL ref: {d['structural_sl_reference']['short_sl_reference']}",
        f"",
        f"## Reason Codes",
        *[f"- {rc}" for rc in d["reason_codes"]],
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
