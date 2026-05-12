"""
NurNova Telegram Notifier
=========================
B + C kombinasyonu:
- Her 15 dakikada sistem raporu
- Sinyal gelince detayli alert
- Trade kapaninca sonuc mesaji
- Sistem sorunu olunca uyari

Kullanim:
  python telegram_notifier.py

Env variables (zorunlu):
  TELEGRAM_BOT_TOKEN=xxxx
  TELEGRAM_CHAT_ID=xxxx

Env variables (opsiyonel):
  NURNOVA_STATUS_INTERVAL=900   # kac saniyede bir durum raporu (default 900=15dk)
  NURNOVA_LOOP_INTERVAL=30      # pipeline dongu suresi (default 30s)
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

ROOT      = pathlib.Path(__file__).resolve().parent
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR  = ROOT / "data" / "simple"

# ------------------------------------------------------------------ #
# Config
# ------------------------------------------------------------------ #

BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")
STATUS_INTERVAL = int(os.environ.get("NURNOVA_STATUS_INTERVAL", "900"))  # 15 dk
LOOP_INTERVAL   = int(os.environ.get("NURNOVA_LOOP_INTERVAL", "30"))


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_hhmm() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


def _read_json(path: pathlib.Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _fmt_price(v) -> str:
    if v is None or v == "?":
        return "—"
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return str(v)


def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return str(v)


def send_telegram(text: str) -> bool:
    """Telegram'a mesaj gonder. True = basarili."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[TG] BOT_TOKEN veya CHAT_ID eksik — mesaj gonderilmedi")
        return False
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id":    CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[TG] Gonderim hatasi: {e}")
        return False


# ------------------------------------------------------------------ #
# Mesaj formatları
# ------------------------------------------------------------------ #

def _status_report() -> str:
    """Her 15 dakikada bir gonderilen sistem ozeti."""
    mt   = _read_json(STATE_DIR / "latest_market_truth.json")
    sc   = _read_json(STATE_DIR / "latest_setup_context.json")
    tp   = _read_json(STATE_DIR / "latest_trade_plan.json")
    dg   = _read_json(STATE_DIR / "latest_decision_gate.json")
    pl   = _read_json(STATE_DIR / "latest_paper_lifecycle.json")
    dep  = _read_json(STATE_DIR / "latest_depth_liquidity_memory.json")
    wl   = _read_json(STATE_DIR / "latest_wall_lifecycle.json")
    fp   = _read_json(STATE_DIR / "latest_flow_persistence.json")
    sync = _read_json(STATE_DIR / "latest_context_sync.json")
    em   = _read_json(STATE_DIR / "latest_edge_matrix_v2.json")

    price = _fmt_price(_read_json(STATE_DIR / "latest_market_truth.json")
                       .get("market_truth", {}).get("current_price"))

    # Olasilik
    prob  = sc.get("probability_summary", {})
    lp    = _fmt_pct(prob.get("long_probability_pct"))
    sp    = _fmt_pct(prob.get("short_probability_pct"))
    sig   = prob.get("signal_class", "—")
    elig  = prob.get("signal_eligible", False)
    sig_icon = "🟡" if elig else "⚪"

    # Persistence
    pers_label = fp.get("persistence_label", "—")
    cont_qual  = fp.get("continuation_quality", "—")

    # Wall
    bid_w = dep.get("bid_wall", {})
    ask_w = dep.get("ask_wall", {})
    sweep = dep.get("sweep_risk", {}).get("sweep_risk", "—")
    liq_bias = dep.get("liquidity_bias", "—")
    sweep_icon = "⚠️" if sweep in ("IMMINENT", "HIGH") else "✅"

    # Acik trade
    lc_status = pl.get("lifecycle_status", "NO_LIFECYCLE")
    open_side  = pl.get("side", "—")
    open_entry = _fmt_price(pl.get("entry_price"))
    open_r     = pl.get("unrealized_r")
    open_r_str = f"{float(open_r):+.2f}R" if open_r is not None else "—"

    # Sync
    sync_status = sync.get("sync_status", "—")
    sync_icon   = "✅" if sync_status == "SYNC_OK" else "⚠️"

    # Edge
    em_overall  = em.get("overall", {})
    win_rate    = em_overall.get("win_rate")
    total_closed = em_overall.get("total_closed", 0)
    wr_str = f"{win_rate*100:.1f}%" if win_rate is not None else "veri yok"

    lines = [
        f"📊 <b>NURNOVA — {_utc_hhmm()}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"BTC      : <b>{price} USDT</b>",
        f"Olasılık : 🟢 LONG {lp} / SHORT {sp}",
        f"Sinyal   : {sig_icon} {sig}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Persistence : {pers_label}",
        f"Devamlılık  : {cont_qual}",
        f"Likidite    : {liq_bias} | Sweep: {sweep_icon} {sweep}",
    ]

    if bid_w.get("has_wall"):
        lines.append(f"BID Duvar   : {_fmt_price(bid_w.get('wall_price'))} ({bid_w.get('wall_strength', 0):.1f}x)")
    if ask_w.get("has_wall"):
        lines.append(f"ASK Duvar   : {_fmt_price(ask_w.get('wall_price'))} ({ask_w.get('wall_strength', 0):.1f}x)")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if lc_status not in ("NO_LIFECYCLE", "CLOSED", None, ""):
        lines.append(f"Açık trade  : {open_side} @ {open_entry} | R={open_r_str}")
    else:
        lines.append("Açık trade  : YOK")

    lines += [
        f"Edge        : {wr_str} ({total_closed} trade)",
        f"Pipeline    : {sync_icon} {sync_status}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    return "\n".join(lines)


def _signal_alert(tp: dict, sc: dict, dep: dict, wl: dict) -> str:
    """Sinyal gelince gonderilen detayli mesaj."""
    side  = tp.get("side", "?")
    entry = _fmt_price(tp.get("entry_price"))
    sl    = _fmt_price(tp.get("stop_loss"))
    tp1   = _fmt_price(tp.get("tp1"))
    tp2   = _fmt_price(tp.get("tp2"))
    rr1   = tp.get("rr_tp1", 0)
    grade = tp.get("plan_grade", "?")

    prob = sc.get("probability_summary", {})
    lp   = _fmt_pct(prob.get("long_probability_pct"))
    sp2  = _fmt_pct(prob.get("short_probability_pct"))
    sig  = prob.get("signal_class", "?")

    bid_w = dep.get("bid_wall", {})
    ask_w = dep.get("ask_wall", {})
    sweep = dep.get("sweep_risk", {}).get("sweep_risk", "?")
    liq   = dep.get("liquidity_bias", "?")

    wl_intel = wl.get("liquidity_intelligence", {})
    wall_conc = wl_intel.get("dominant_conclusion", "?")

    side_icon = "🟢" if side == "LONG" else "🔴"

    # SL yuzde
    try:
        ep = float(tp.get("entry_price", 0))
        sl_v = float(tp.get("stop_loss", 0))
        sl_pct = abs(ep - sl_v) / ep * 100
        sl_pct_str = f"-{sl_pct:.2f}%"
    except Exception:
        sl_pct_str = "?"

    lines = [
        f"{side_icon} <b>{side} SİNYAL — BTCUSDT</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Fiyat    : <b>{entry} USDT</b>",
        f"Entry    : {entry}",
        f"SL       : {sl} ({sl_pct_str})",
        f"TP1      : {tp1}",
        f"TP2      : {tp2}",
        f"RR       : {rr1:.1f}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Sınıf    : {sig} ({lp} LONG / {sp2} SHORT)",
        f"Plan     : Grade {grade}",
        f"Likidite : {liq} | Sweep: {sweep}",
        f"Duvar    : {wall_conc}",
    ]

    if bid_w.get("has_wall"):
        lines.append(f"BID Duvar: {_fmt_price(bid_w.get('wall_price'))} ({bid_w.get('wall_strength', 0):.1f}x)")
    if ask_w.get("has_wall"):
        lines.append(f"ASK Duvar: {_fmt_price(ask_w.get('wall_price'))} ({ask_w.get('wall_strength', 0):.1f}x)")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "📋 Paper trade acildi",
    ]

    return "\n".join(lines)


def _trade_closed_alert(outcome: dict) -> str:
    """Trade kapaninca gonderilen mesaj."""
    outcome_label = outcome.get("outcome", "?")
    final_r  = outcome.get("final_r", 0)
    hold_sec = outcome.get("hold_time_seconds")
    mfe      = outcome.get("mfe_r", 0)
    mae      = outcome.get("mae_r", 0)
    lineage  = outcome.get("lineage", {})
    scenario = lineage.get("source_scenario", "?")
    grade    = lineage.get("source_setup_grade", "?")
    side     = outcome.get("side", "?")

    if outcome_label == "TP1_HIT":
        icon = "✅"
        title = "TP1 HIT"
    elif outcome_label == "SL_HIT":
        icon = "❌"
        title = "STOP HIT"
    else:
        icon = "⏰"
        title = "EXPIRED"

    hold_str = "?"
    if hold_sec:
        m = int(hold_sec // 60)
        s = int(hold_sec % 60)
        hold_str = f"{m}dk {s}s"

    lines = [
        f"{icon} <b>PAPER TRADE KAPANDI</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Sonuc    : <b>{title}</b>",
        f"Yön      : {side}",
        f"R        : {float(final_r):+.2f}R",
        f"Tutuldu  : {hold_str}",
        f"MFE      : +{float(mfe):.2f}R",
        f"MAE      : -{float(mae):.2f}R",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Senaryo  : {scenario}",
        f"Grade    : {grade}",
    ]

    return "\n".join(lines)


def _system_alert(message: str) -> str:
    return f"⚠️ <b>NURNOVA SİSTEM UYARISI</b>\n{message}"


# ------------------------------------------------------------------ #
# State izleme
# ------------------------------------------------------------------ #

def _load_state_file() -> dict:
    p = STATE_DIR / "telegram_notifier_state.json"
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "last_status_ts":      0.0,
        "last_lifecycle_id":   None,
        "last_outcome_id":     None,
        "last_plan_status":    None,
        "last_sync_ok":        True,
    }


def _save_state_file(state: dict) -> None:
    p = STATE_DIR / "telegram_notifier_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _run_pipeline() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "src.simple.run_local_full_pipeline"],
        capture_output=True, text=True,
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return {"error": result.stderr or "bos cikti"}


# ------------------------------------------------------------------ #
# Ana dongu
# ------------------------------------------------------------------ #

def main() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print("HATA: TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID env variable'lari gerekli")
        print("Ornek: export TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy")
        sys.exit(1)

    print(f"NurNova Telegram Notifier basliyor...")
    print(f"Status raporu: her {STATUS_INTERVAL//60} dakika")
    print(f"Pipeline dongu: her {LOOP_INTERVAL} saniye")
    print("Ctrl+C ile durdur\n")

    # Baslangic mesaji
    send_telegram("🚀 <b>NurNova baslatildi</b>\nSistem izleme aktif.")

    state = _load_state_file()
    cycle = 0

    while True:
        cycle += 1
        now = time.monotonic()

        try:
            # Pipeline calistir
            pipeline_data = _run_pipeline()

            # --- Sistem uyarisi ---
            sync = _read_json(STATE_DIR / "latest_context_sync.json")
            sync_status = sync.get("sync_status", "UNKNOWN")
            if sync_status == "SYNC_BROKEN" and state["last_sync_ok"]:
                send_telegram(_system_alert(f"SYNC_BROKEN — pipeline veri tutarsizligi tespit edildi"))
                state["last_sync_ok"] = False
            elif sync_status == "SYNC_OK":
                state["last_sync_ok"] = True

            # --- Sinyal alert ---
            tp = _read_json(STATE_DIR / "latest_trade_plan.json")
            dg = _read_json(STATE_DIR / "latest_decision_gate.json")
            plan_status = tp.get("plan_status", "NO_PLAN")
            decision    = dg.get("decision", "BLOCKED")
            lifecycle_id = _read_json(STATE_DIR / "latest_paper_lifecycle.json").get("lifecycle_id")

            # Yeni trade acildiysa
            if (lifecycle_id and
                lifecycle_id != state["last_lifecycle_id"] and
                decision == "PAPER_OPEN"):
                sc  = _read_json(STATE_DIR / "latest_setup_context.json")
                dep = _read_json(STATE_DIR / "latest_depth_liquidity_memory.json")
                wl  = _read_json(STATE_DIR / "latest_wall_lifecycle.json")
                send_telegram(_signal_alert(tp, sc, dep, wl))
                state["last_lifecycle_id"] = lifecycle_id

            # --- Trade kapanma alert ---
            outcome = _read_json(STATE_DIR / "latest_outcome_tracker.json")
            outcome_id = outcome.get("outcome_event_id")
            outcome_label = outcome.get("outcome", "OPEN")

            if (outcome_id and
                outcome_id != state["last_outcome_id"] and
                outcome_label in ("TP1_HIT", "SL_HIT", "EXPIRED")):
                send_telegram(_trade_closed_alert(outcome))
                state["last_outcome_id"] = outcome_id

            # --- 15 dakikalik durum raporu ---
            if (now - state["last_status_ts"]) >= STATUS_INTERVAL:
                send_telegram(_status_report())
                state["last_status_ts"] = now
                print(f"[{_utc_hhmm()}] Durum raporu gonderildi")

            state["last_plan_status"] = plan_status
            _save_state_file(state)

            # Konsol ozeti
            price_raw = (_read_json(STATE_DIR / "latest_market_truth.json")
                         .get("market_truth", {}).get("current_price", "?"))
            prob = _read_json(STATE_DIR / "latest_setup_context.json").get("probability_summary", {})
            lp   = prob.get("long_probability_pct", "?")
            sig  = prob.get("signal_class", "?")
            print(f"[{_utc_hhmm()}] Dongu #{cycle} | BTC={_fmt_price(price_raw)} | "
                  f"LONG={lp}% | {sig} | {sync_status}")

        except KeyboardInterrupt:
            print("\nDongu durduruldu.")
            send_telegram("🛑 <b>NurNova durduruldu</b>")
            break
        except Exception as ex:
            print(f"[HATA] Dongu #{cycle}: {ex}")

        try:
            time.sleep(LOOP_INTERVAL)
        except KeyboardInterrupt:
            print("\nDongu durduruldu.")
            send_telegram("🛑 <b>NurNova durduruldu</b>")
            break


if __name__ == "__main__":
    main()
