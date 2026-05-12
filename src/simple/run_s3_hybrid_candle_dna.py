"""Run S3 Hybrid Candle DNA — CLI entry point.

DUZELTME v2: 
- Kendi 1m mumunu aggTrade bucket'larından üretir (current_kline_1m)
- Binance resmi kline ile karşılaştırır (latest_closed_kline_1m)
- İkisini Hybrid olarak birleştirir ve tutarsızlık varsa işaretler
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from src.simple.hybrid_candle_dna_engine import build_dna, run_fake_sample

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
REPORTS_DIR = ROOT / "reports" / "simple"

MARKET_TRUTH_PATH = STATE_DIR / "latest_market_truth.json"
EVIDENCE_PATH = STATE_DIR / "latest_1s_evidence.json"
FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"


def _ensure_dirs() -> None:
    for d in (STATE_DIR, DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_json(path: pathlib.Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _build_candle_from_kline(kline: dict) -> dict | None:
    """Binance kline verisinden candle dict uret."""
    try:
        return {
            "open":   float(kline["open"]),
            "high":   float(kline["high"]),
            "low":    float(kline["low"]),
            "close":  float(kline["close"]),
            "volume": float(kline["volume"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _build_candle_from_price(price: float) -> dict:
    """Tek fiyat noktasindan minimal candle — fallback."""
    return {
        "open":   price,
        "high":   price,
        "low":    price,
        "close":  price,
        "volume": 0.0,
    }


def _check_kline_consistency(
    own_candle: dict | None,
    binance_kline: dict | None,
) -> dict:
    """
    Kendi ürettiğimiz mum ile Binance kline'ını karşılaştır.
    close fiyatı arasındaki fark yüzde olarak hesaplanır.
    """
    if own_candle is None or binance_kline is None:
        return {
            "available": False,
            "close_diff_pct": None,
            "consistency_label": "UNKNOWN",
            "note": "One or both candles missing."
        }

    own_close = float(own_candle.get("close", 0.0))
    binance_close = float(binance_kline.get("close", own_close))

    if binance_close == 0.0:
        return {
            "available": False,
            "close_diff_pct": None,
            "consistency_label": "UNKNOWN",
            "note": "Binance close is zero."
        }

    diff_pct = abs(own_close - binance_close) / binance_close * 100.0

    if diff_pct <= 0.01:
        label = "CONSISTENT"
    elif diff_pct <= 0.1:
        label = "MINOR_DIFF"
    elif diff_pct <= 0.5:
        label = "NOTABLE_DIFF"
    else:
        label = "MAJOR_DIFF"

    return {
        "available": True,
        "own_close": round(own_close, 4),
        "binance_close": round(binance_close, 4),
        "close_diff_pct": round(diff_pct, 6),
        "consistency_label": label,
        "note": f"Own={own_close:.2f} vs Binance={binance_close:.2f} diff={diff_pct:.4f}%"
    }


def _extract_evidence_for_dna(ev: dict) -> dict | None:
    """S2 evidence'tan DNA icin gereken alanlari cek."""
    try:
        inner = ev["evidence"]
        tf = ev["trade_flow"]
        return {
            "evidence_label":   inner["evidence_label"],
            "evidence_score":   inner["evidence_score"],
            "evidence_strength": inner["evidence_strength"],
            "micro_winner":     inner["micro_winner"],
            "delta_ratio":      tf["delta_ratio"],
            "confidence_adjusted": inner.get("confidence_adjusted", False),
        }
    except (KeyError, TypeError):
        return None


def _write_outputs(dna: dict) -> None:
    _ensure_dirs()

    (STATE_DIR / "latest_hybrid_candle_dna.json").write_text(
        json.dumps(dna, indent=2), encoding="utf-8"
    )
    (STATE_DIR / "s3_hybrid_candle_dna_state.json").write_text(
        json.dumps(dna, indent=2), encoding="utf-8"
    )

    with (DATA_DIR / "hybrid_candle_dna.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dna) + "\n")

    sh  = dna["shape"]
    ci  = dna["candle_intent"]
    fvp = dna["flow_vs_price"]
    dq  = dna["data_quality"]

    # Kline consistency bilgisi varsa rapora ekle
    kc = dna.get("kline_consistency", {})

    lines = [
        f"# S3 Hybrid Candle DNA — {dna['symbol']}",
        "",
        f"**Timestamp:** {dna['timestamp_utc']}",
        f"**Source Mode:** {dna['source']['source_mode']}",
        f"**Data Quality:** {dq['level']} (score={dq['score']})",
        "",
        "## Shape",
        f"- Direction: {sh['candle_direction']}",
        f"- Shape: {sh['shape_label']}",
        f"- Body %: {sh['body_pct']}",
        f"- Upper Wick %: {sh['upper_wick_pct']}",
        f"- Lower Wick %: {sh['lower_wick_pct']}",
        "",
        "## Candle Intent",
        f"- Label: {ci['intent_label']}",
        f"- Score: {ci['intent_score']}",
        f"- Strength: {ci['intent_strength']}",
        "",
        "## Flow vs Price",
        f"- Alignment: {fvp['alignment']}",
        f"- Explanation: {fvp['explanation']}",
        "",
        "## Kline Consistency",
        f"- Available: {kc.get('available', False)}",
        f"- Consistency: {kc.get('consistency_label', 'N/A')}",
        f"- Note: {kc.get('note', 'N/A')}",
        "",
        "## Reason Codes",
        *[f"- {rc}" for rc in dna["reason_codes"]],
    ]
    (REPORTS_DIR / "s3_hybrid_candle_dna_latest_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run S3 Hybrid Candle DNA")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    if args.fake_sample:
        dna = run_fake_sample(args.symbol)
        _write_outputs(dna)
        print(json.dumps(dna, indent=2))
        return

    # --- Gercek veri modu ---
    mt   = _load_json(MARKET_TRUTH_PATH)
    ev   = _load_json(EVIDENCE_PATH)
    flow = _load_json(FLOW_STATE_PATH)

    # 1. Binance kline'indan candle al
    # Once kapanmis mumu dene (daha guvenilir OHLC)
    # Sonra suanda birikmekte olan mumu dene
    binance_closed_kline = flow.get("latest_closed_kline_1m")
    binance_current_kline = flow.get("current_kline_1m")

    # Hangi kline'i kullanacagiz?
    # Kapanmis varsa onu kullan (tam OHLC), yoksa birikmekte olani kullan
    kline_for_candle = binance_closed_kline or binance_current_kline
    candle = _build_candle_from_kline(kline_for_candle) if kline_for_candle else None

    # Kline yoksa market truth fiyatindan fallback candle uret
    if candle is None and mt:
        try:
            price = mt["market_truth"]["current_price"]
            if price:
                candle = _build_candle_from_price(float(price))
        except (KeyError, TypeError):
            pass

    # 2. Evidence al
    evidence = _extract_evidence_for_dna(ev) if ev else None

    # 3. Kline tutarlilik kontrolu
    # Kendi bucket'larimizdan olusturulacak "own candle" burada candle'in kendisi
    # Ama gerçek karşılaştırma: current kline (kendi aggTrade'lerimizden) vs closed kline (Binance resmi)
    kline_consistency = _check_kline_consistency(
        own_candle=_build_candle_from_kline(binance_current_kline) if binance_current_kline else None,
        binance_kline=_build_candle_from_kline(binance_closed_kline) if binance_closed_kline else None,
    )

    # 4. Source mode belirle
    if binance_closed_kline:
        source = "BINANCE_CLOSED_KLINE"
    elif binance_current_kline:
        source = "BINANCE_CURRENT_KLINE"
    elif candle:
        source = "MARKET_TRUTH_FALLBACK"
    else:
        source = "NO_DATA"

    # 5. Quality scores
    s1_dq = mt.get("data_quality", {}).get("score", 0.5) if mt else 0.0
    s2_dq = ev.get("data_quality", {}).get("score", None) if ev else None

    # 6. DNA uret
    dna = build_dna(
        args.symbol, candle, evidence, source,
        s1_dq_score=s1_dq,
        s2_dq_score=s2_dq,
    )

    # 7. Kline consistency'i DNA'ya ekle
    dna["kline_consistency"] = kline_consistency
    dna["kline_source"] = {
        "closed_kline_available": binance_closed_kline is not None,
        "current_kline_available": binance_current_kline is not None,
        "used_source": source,
    }

    # 8. Reason code'a kline bilgisi ekle
    dna["reason_codes"].append(f"KLINE_{kline_consistency['consistency_label']}")
    if binance_closed_kline:
        dna["reason_codes"].append("BINANCE_CLOSED_KLINE_USED")
    elif binance_current_kline:
        dna["reason_codes"].append("BINANCE_CURRENT_KLINE_USED")
    else:
        dna["reason_codes"].append("KLINE_NOT_AVAILABLE")

    _write_outputs(dna)
    print(json.dumps(dna, indent=2))


if __name__ == "__main__":
    main()
