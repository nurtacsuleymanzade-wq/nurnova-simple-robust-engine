"""
NurNova — Surekli dongu runner v4.
Her 30 saniyede bir pipeline calistirir ve ozet gosterir.
Durdurmak icin: Ctrl+C
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: pathlib.Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def run_once() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "src.simple.run_local_full_pipeline"],
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return {"error": result.stderr or result.stdout or "bos cikti"}


def print_summary(data: dict, cycle: int) -> None:
    ts = utc_now()
    print(f"\n{'='*60}")
    print(f"  DONGU #{cycle}  |  {ts}")
    print(f"{'='*60}")

    if "error" in data:
        print(f"  HATA: {data['error'][:300]}")
        return

    es = data.get("execution_summary", {})
    dq = data.get("data_quality", {})

    ctx_id = data.get("context_id", "?")
    sync_st = data.get("sync_status", "?")
    print(f"  Context  : {ctx_id}")
    print(f"  Sync     : {sync_st}")
    print(f"  Pipeline : {es.get('pipeline_status', '?')}")
    print(f"  Bloklar  : {es.get('blocks_passed', 0)}/{es.get('blocks_total', 0)} PASSED")
    print(f"  Veri     : {dq.get('level', '?')} (skor={dq.get('score', 0)})")

    for blk in data.get("block_results", []):
        if blk.get("status") not in ("PASSED",):
            print(f"  [{blk['status']}] {blk['block_id']}")

    # --- Fiyat (market_truth icinden) ---
    mt = _read_json(STATE_DIR / "latest_market_truth.json")
    price = None
    if mt:
        price = (mt.get("market_truth") or {}).get("current_price")
        if price is None:
            price = mt.get("current_price")
    print(f"  Fiyat    : {price or '?'} USDT")

    # --- Setup candidate ---
    sc = _read_json(STATE_DIR / "latest_setup_candidate.json")
    if sc:
        src_mode  = (sc.get("source") or {}).get("source_mode", "?")
        cand      = sc.get("setup_candidate") or {}
        direction = cand.get("setup_direction", "?")
        grade     = cand.get("setup_grade", "?")
        status    = cand.get("setup_status", "?")
        score     = cand.get("raw_setup_score", "?")
        align     = (sc.get("evidence_alignment") or {}).get("alignment_label", "?")
        risk      = (sc.get("risk") or {}).get("setup_risk_label", "?")
        print(f"  Setup    : {status} | {direction} | Grade={grade} | skor={score} | {align} | risk={risk} | src={src_mode}")
    else:
        print(f"  Setup    : (dosya yok)")

    # --- Model Registry ---
    mreg = _read_json(STATE_DIR / "latest_model_registry.json")
    if mreg:
        consensus = mreg.get("consensus_direction", "?")
        n_signals = mreg.get("active_model_count", 0)
        candle_q = mreg.get("candle_quality", "?")
        long_pct = mreg.get("long_probability_pct", 50)
        short_pct = mreg.get("short_probability_pct", 50)
        active_signals = mreg.get("active_signals", [])
        print(f"  Model    : CONSENSUS={consensus} | signals={n_signals} | candle={candle_q} | L={long_pct}% S={short_pct}%")
        if active_signals:
            for sig in active_signals:
                model_name = sig.get("model", "?")
                bias = sig.get("bias", "?")
                strength = float(sig.get("strength", 0) or 0)
                reason = sig.get("trigger_reason", "?")
                print(f"             [{model_name}] {bias} strength={strength:.1f} | {reason}")
    else:
        print("  Model    : (henuz yok)")

    # --- Trade Plan ---
    tp = _read_json(STATE_DIR / "latest_trade_plan.json")
    if tp:
        plan      = tp.get("trade_plan") or tp
        t_status  = plan.get("plan_status", plan.get("trade_plan_status", tp.get("decision_status", "?")))
        direction = plan.get("direction", plan.get("side", "?"))
        entry     = plan.get("entry_price", "?")
        sl        = plan.get("stop_loss", "?")
        tp1v      = plan.get("tp1", "?")
        rr        = plan.get("rr_tp1", plan.get("rr", "?"))
        veto_reason = plan.get("model_veto_reason")
        if veto_reason:
            print(f"  Plan     : {t_status} | {veto_reason}")
        else:
            print(f"  Plan     : {t_status} | {direction} | entry={entry} sl={sl} tp1={tp1v} RR={rr}")
    else:
        print(f"  Plan     : (dosya yok)")

    # --- Paper lifecycle ---
    paper = _read_json(STATE_DIR / "latest_paper_lifecycle.json")
    if paper:
        lc_status = paper.get("lifecycle_status", "?")
        side      = paper.get("side", paper.get("direction", "?"))
        entry     = paper.get("entry_price", "?")
        tp1v      = paper.get("tp1", "?")
        sl        = paper.get("stop_loss", "?")
        tp1_hit   = paper.get("tp1_hit", "?")
        sl_hit    = paper.get("stop_hit", "?")
        unreal_r  = paper.get("unrealized_r", "?")
        print(f"  Paper    : {lc_status} | {side} | entry={entry} tp1={tp1v} sl={sl}")
        print(f"             tp1_hit={tp1_hit} | sl_hit={sl_hit} | R={unreal_r}")
    else:
        print(f"  Paper    : (dosya yok)")

    # --- Edge stats ---
    edge = _read_json(STATE_DIR / "latest_edge_stats.json")
    if edge:
        winrate  = edge.get("overall_winrate_pct", edge.get("winrate_pct", "?"))
        samples  = edge.get("total_closed", edge.get("sample_count", "?"))
        e_status = edge.get("edge_learning_status", edge.get("status", "?"))
        best_dir = edge.get("best_direction", "?")
        print(f"  Edge     : winrate={winrate}% | ornekler={samples} | {e_status} | en_iyi={best_dir}")
    else:
        print(f"  Edge     : (DEGRADED)")

    # --- Kapanan trade ---
    for fname in ("paper_outcome.jsonl", "closed_paper_outcomes.jsonl"):
        closed_path = DATA_DIR / fname
        if closed_path.exists():
            try:
                lines = [l for l in closed_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                print(f"  Kapanan  : {len(lines)} trade")
            except Exception:
                pass
            break

    print(f"{'='*60}")


def main() -> None:
    interval = 30
    cycle = 0

    print("NurNova Pipeline Dongu Basliyor... (v4)")
    print(f"Proje: {ROOT}")
    print(f"Her {interval} saniyede bir calisacak.")
    print("Durdurmak icin Ctrl+C\n")

    while True:
        cycle += 1
        try:
            data = run_once()
            print_summary(data, cycle)
        except KeyboardInterrupt:
            print("\nDongu durduruldu.")
            break
        except Exception as ex:
            print(f"\n[HATA] Dongu #{cycle}: {ex}")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nDongu durduruldu.")
            break


if __name__ == "__main__":
    main()
