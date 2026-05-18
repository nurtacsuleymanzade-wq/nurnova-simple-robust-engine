"""
NurNova Telegram Notifier - 15 Dakikalik Rapor
"""
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

BOT_TOKEN = "8732866487:AAGqzunUcjh5ApuIjIoFNdCToULPkP5zOKQ"
CHAT_ID = "899309281"
BASE = Path("/root/nurnova-simple-robust-engine")
EPOCH_STATE = BASE / "state/simple/epoch_v2"
STATE = BASE / "state/simple"
SEEN_FILE = STATE / "notifier_state.json"

def send(msg: str):
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"[TELEGRAM ERR] {e}")

def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except:
        return {}

def load_state() -> dict:
    try:
        return json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {}
    except:
        return {}

def save_state(s: dict):
    SEEN_FILE.write_text(json.dumps(s, indent=2))

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def is_service_active(svc):
    try:
        out = subprocess.run(f"systemctl is-active {svc}", shell=True,
                           capture_output=True, text=True).stdout.strip()
        return out == "active"
    except:
        return False

def get_pipeline_age():
    try:
        d = load_json(STATE / "latest_local_pipeline_run.json")
        ts = d.get("timestamp_utc") or ""
        if not ts:
            return 999
        last = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds()
    except:
        return 999

def build_15min_report(state: dict) -> str:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=15)

    # Outcome accounting
    oc = load_json(EPOCH_STATE / "latest_outcome_accounting.json")
    summary = oc.get("summary", {})
    all_closed = oc.get("closed_samples") or []

    # Son 15 dakikada kapananlar
    recent_closed = []
    for s in all_closed:
        closed_at = s.get("closed_at_utc") or ""
        try:
            ct = datetime.strptime(closed_at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if ct >= window_start:
                recent_closed.append(s)
        except:
            pass

    # Son 15 dakikada açılanlar
    lc = load_json(EPOCH_STATE / "latest_research_paper_lifecycle.json")
    open_trades = lc.get("open_trades") or []
    recent_opened = []
    for t in open_trades:
        opened_at = t.get("opened_at_utc") or ""
        try:
            ot = datetime.strptime(opened_at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if ot >= window_start:
                recent_opened.append(t)
        except:
            pass

    # Tüm zamanlar istatistik
    total_closed = summary.get("closed_count", 0)
    total_wins = summary.get("wins", 0)
    total_losses = summary.get("losses", 0)
    total_tp = summary.get("tp_hits", 0)
    total_sl = summary.get("sl_hits", 0)
    total_expired = summary.get("expired", 0)
    winrate = summary.get("winrate", 0)
    clean = summary.get("clean_sample_count", 0)

    # Son 15 dk istatistik
    r15_tp = sum(1 for s in recent_closed if "TP" in str(s.get("close_reason","")).upper())
    r15_sl = sum(1 for s in recent_closed if "SL" in str(s.get("close_reason","")).upper())
    r15_exp = sum(1 for s in recent_closed if "TIMEOUT" in str(s.get("close_reason","")).upper() or "EXPIRED" in str(s.get("close_reason","")).upper())
    r15_r = [s.get("r_result") for s in recent_closed if s.get("r_result") is not None]
    avg_r = round(sum(r15_r) / len(r15_r), 2) if r15_r else None

    # Model dağılımı (tüm closed)
    model_counts = {}
    for s in all_closed:
        mid = s.get("model_id", "UNKNOWN")
        model_counts[mid] = model_counts.get(mid, 0) + 1
    top_models = sorted(model_counts.items(), key=lambda x: -x[1])[:5]

    # Setup family şu an
    sf = load_json(STATE / "latest_setup_family_activation.json")
    family = sf.get("dominant_setup_family", "?")
    direction = sf.get("direction", "?")
    score = sf.get("activation_score", 0)

    # Zincir sağlığı
    services = {
        "WS": "nurnova-ws.service",
        "Pipeline": "nurnova-pipeline.service",
        "Notifier": "nurnova-notifier.service",
        "Healer": "nurnova-healer.service",
    }
    svc_status = ""
    all_ok = True
    for name, svc in services.items():
        ok = is_service_active(svc)
        if not ok:
            all_ok = False
        svc_status += f"  {name}: {'✅' if ok else '❌'}\n"

    pipeline_age = get_pipeline_age()
    pipeline_ok = pipeline_age < 120
    chain_emoji = "✅" if all_ok and pipeline_ok else "⚠️"

    # Rapor oluştur
    lines = [
        f"📊 <b>NURNOVA 15 DAKİKA RAPORU</b>",
        f"🕐 {now.strftime('%H:%M')} UTC",
        f"",
        f"━━━ SON 15 DAKİKA ━━━",
        f"📂 Açılan: <b>{len(recent_opened)}</b> trade",
        f"📁 Kapanan: <b>{len(recent_closed)}</b> trade",
    ]

    if recent_closed:
        lines.append(f"  ✅ TP: {r15_tp} | ❌ SL: {r15_sl}")
        if avg_r is not None:
            lines.append(f"  Ort. R: <b>{avg_r:+.2f}R</b>")
        lines.append(f"")
        lines.append(f"<b>Kapanan Tradeler:</b>")
        for s in recent_closed[:5]:
            reason = s.get("close_reason") or "?"
            emoji = "✅" if "TP" in str(reason) else "❌"
            tf = s.get("primary_tf") or "?"
            hold = int((s.get("hold_seconds") or 0) // 60)
            r = s.get("r_result") or 0
            model = (s.get("model_id") or "?").replace("_LONG","").replace("_SHORT","")
            lines.append(f"  {emoji} {model} [{tf}] → {reason} {r:+.1f}R ({hold}dk)")

    if recent_opened:
        lines.append(f"")
        lines.append(f"<b>Açılan Tradeler:</b>")
        for t in recent_opened[:5]:
            d = "🟢" if t.get("direction") == "LONG" else "🔴"
            lines.append(f"  {d} {t.get('model_id','?')} | E:{t.get('entry','?')} SL:{t.get('stop_loss','?')} TP1:{t.get('tp1','?')}")

    lines += [
        f"",
        f"━━━ TÜM ZAMANLAR ━━━",
        f"Toplam kapanan: <b>{total_closed}</b>",
        f"TP: {total_tp} | SL: {total_sl} | Exp: {total_expired}",
        f"Winrate: <b>%{winrate*100:.1f}</b>",
        f"Clean sample: <b>{clean}</b>",
        f"",
        f"━━━ SETUP ━━━",
        f"Aile: <b>{family}</b> | Yön: <b>{direction}</b>",
        f"Score: {score}",
        f"Açık trade: {len(open_trades)}",
    ]

    if top_models:
        lines.append(f"")
        lines.append(f"<b>Top Modeller:</b>")
        for mid, cnt in top_models:
            lines.append(f"  {mid}: {cnt} sample")

    lines += [
        f"",
        f"━━━ ZİNCİR SAĞLIĞI {chain_emoji} ━━━",
        svc_status.rstrip(),
        f"  Pipeline: {'✅' if pipeline_ok else f'⚠️ {pipeline_age:.0f}s stale'}",
    ]

    return "\n".join(lines)

def main():
    print("[NOTIFIER] Başlatıldı")
    send("🚀 <b>NurNova Notifier Başlatıldı</b>\nHer 15 dakikada rapor gelecek.")

    state = load_state()

    while True:
        try:
            report = build_15min_report(state)
            send(report)
            save_state(state)
            print(f"[NOTIFIER] Rapor gönderildi {utc_now()}")
        except Exception as e:
            print(f"[NOTIFIER ERR] {e}")
            send(f"⚠️ Notifier hata: {e}")

        time.sleep(900)  # 15 dakika

if __name__ == "__main__":
    main()
