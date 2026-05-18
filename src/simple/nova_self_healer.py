"""
NurNova Self Healer
Her 5 dakikada bir:
- RAM kontrolü → yüksekse WS yeniden başlat
- Disk kontrolü → raw_events büyükse arşivle
- Servis kontrolü → ölmüşse yeniden başlat
- Pipeline sağlığı → stale ise yeniden başlat
"""
import os
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

BASE = Path("/root/nurnova-simple-robust-engine")
SERVICES = ["nurnova-ws.service", "nurnova-pipeline.service", "nurnova-notifier.service"]
MAX_RAW_EVENTS_MB = 200
MAX_WS_RAM_MB = 400
STALE_PIPELINE_SECONDS = 120

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[HEALER {ts}] {msg}")

def run(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()
    except:
        return ""

def get_service_ram_mb(service):
    out = run(f"systemctl show {service} --property=MemoryCurrent")
    try:
        val = int(out.split("=")[1])
        return val / 1024 / 1024
    except:
        return 0

def is_service_active(service):
    out = run(f"systemctl is-active {service}")
    return out == "active"

def restart_service(service):
    run(f"systemctl restart {service}")
    log(f"RESTARTED: {service}")

def archive_large_epoch_files():
    """epoch_v2 icindeki buyuk dosyalari temizle"""
    import os
    epoch_dir = BASE / "data/simple/epoch_v2"
    archive_dir = BASE / "archive"
    archive_dir.mkdir(exist_ok=True)
    
    # Tehlikeli buyuk dosyalar
    watch_files = [
        "zone_context_history.jsonl",
        "structure_quality_history.jsonl",
        "full_lineage_history.jsonl",
        "edge_query_report_history.jsonl",
        "research_paper_lifecycle_history.jsonl",
        "outcome_accounting_history.jsonl",
    ]
    
    for fname in watch_files:
        fpath = epoch_dir / fname
        if not fpath.exists():
            continue
        size_mb = fpath.stat().st_size / 1024 / 1024
        if size_mb > 50:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            fpath.rename(archive_dir / f"{fname}.{ts}.bak")
            fpath.touch()
            log(f"EPOCH FILE ARCHIVED: {fname} ({size_mb:.0f}MB)")

def archive_raw_events():
    path = BASE / "data/simple/raw_events.jsonl"
    if not path.exists():
        return
    size_mb = path.stat().st_size / 1024 / 1024
    if size_mb > MAX_RAW_EVENTS_MB:
        archive = BASE / "archive"
        archive.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        path.rename(archive / f"raw_events_{ts}.jsonl")
        log(f"ARCHIVED raw_events ({size_mb:.0f}MB)")
        restart_service("nurnova-ws.service")

def check_pipeline_stale():
    state = BASE / "state/simple/latest_local_pipeline_run.json"
    if not state.exists():
        return
    try:
        d = json.loads(state.read_text())
        ts = d.get("timestamp_utc") or d.get("ts")
        if not ts:
            return
        from datetime import datetime, timezone
        last = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last).total_seconds()
        if age > STALE_PIPELINE_SECONDS:
            log(f"PIPELINE STALE ({age:.0f}s) - restarting")
            restart_service("nurnova-pipeline.service")
    except Exception as e:
        log(f"STALE CHECK ERR: {e}")

def main():
    log("Self Healer başlatıldı")
    while True:
        try:
            # 1. Servis sağlığı
            for svc in SERVICES:
                if not is_service_active(svc):
                    log(f"SERVICE DOWN: {svc}")
                    restart_service(svc)
                    time.sleep(5)

            # 2. WS RAM kontrolü
            ws_ram = get_service_ram_mb("nurnova-ws.service")
            if ws_ram > MAX_WS_RAM_MB:
                log(f"WS RAM HIGH: {ws_ram:.0f}MB - restarting")
                archive_raw_events()
                restart_service("nurnova-ws.service")

            # 3. raw_events boyutu
            archive_raw_events()

            # 3b. Epoch dosyalari buyudumu?
            archive_large_epoch_files()

            # 4. Pipeline stale kontrolü - DEVRE DISI
            # check_pipeline_stale()

        except Exception as e:
            log(f"HEALER ERR: {e}")

        time.sleep(300)  # Her 5 dakika

if __name__ == "__main__":
    main()
