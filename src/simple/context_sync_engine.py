"""Context Sync Engine — NOVA SIMPLE ROBUST ENGINE v1.

Her pipeline calismasinda:
1. Benzersiz context_id uretir (tum bloklar bunu tasir)
2. Tum input dosyalarin yasini kontrol eder
3. Eski/stale dosyalari isaretler
4. Lineage zinciri kurar

Bu engine pipeline'in en basinda calisir.
Hicbir veri uretmez, hicbir trade acmaz.
Sadece "bu pipeline calistirmasinin tum bloklar
ayni zaman penceresine mi ait?" sorusuna cevap verir.

safe_to_open_real_trade always False.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Kac saniyeden eski dosya STALE sayilir?
MAX_AGE_FRESH_S  =  30   # 0-30s  → FRESH
MAX_AGE_RECENT_S = 120   # 31-120s → RECENT
MAX_AGE_STALE_S  = 300   # 121-300s → STALE
# 300s+ → VERY_STALE → blogu gecersiz say

# Kritik bloklar: bunlar STALE olursa pipeline durdurulmali
CRITICAL_BLOCKS = {
    "flow_state",
    "flow_evidence",
    "flow_persistence",
    "market_truth",
}

# Tum input dosyalari
INPUT_FILES = {
    "market_truth":      Path("state/simple/latest_market_truth.json"),
    "flow_state":        Path("state/simple/latest_flow_state.json"),
    "flow_evidence":     Path("state/simple/latest_flow_evidence.json"),
    "flow_persistence":  Path("state/simple/latest_flow_persistence.json"),
    "setup_context":     Path("state/simple/latest_setup_context.json"),
    "setup_candidate":   Path("state/simple/latest_setup_candidate.json"),
    "scenario_trigger":  Path("state/simple/latest_scenario_trigger.json"),
    "trade_plan":        Path("state/simple/latest_trade_plan.json"),
    "hybrid_candle_dna": Path("state/simple/latest_hybrid_candle_dna.json"),
    "depth_memory":      Path("state/simple/latest_depth_liquidity_memory.json"),
    "1s_evidence":       Path("state/simple/latest_1s_evidence.json"),
}

OUTPUT_PATH = Path("state/simple/latest_context_sync.json")
S0_STATE_PATH = Path("state/simple/s0_context_sync_state.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def _age_seconds(ts_str: str | None, now: datetime) -> float | None:
    dt = _parse_ts(ts_str)
    if dt is None:
        return None
    try:
        return max(0.0, (now - dt).total_seconds())
    except Exception:
        return None


def _freshness_label(age_s: float | None) -> str:
    if age_s is None:
        return "UNKNOWN"
    if age_s <= MAX_AGE_FRESH_S:
        return "FRESH"
    if age_s <= MAX_AGE_RECENT_S:
        return "RECENT"
    if age_s <= MAX_AGE_STALE_S:
        return "STALE"
    return "VERY_STALE"


def _generate_context_id(now: datetime) -> str:
    """
    Benzersiz context_id.
    Format: CTX_BTCUSDT_YYYYMMDD_HHMMSS_HASH4
    Hash: son 4 karakter benzersizlik icin.
    """
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    hash4 = hashlib.md5(ts_str.encode()).hexdigest()[:4].upper()
    return f"CTX_BTCUSDT_{ts_str}_{hash4}"


def _check_all_inputs(now: datetime) -> dict[str, Any]:
    """Tum input dosyalari kontrol et."""
    results = {}
    stale_critical = []
    stale_non_critical = []
    missing = []

    for name, path in INPUT_FILES.items():
        data = _load_json(path)

        if data is None:
            results[name] = {
                "path":       str(path),
                "exists":     False,
                "age_s":      None,
                "freshness":  "MISSING",
                "timestamp":  None,
                "is_critical": name in CRITICAL_BLOCKS,
            }
            if name in CRITICAL_BLOCKS:
                missing.append(name)
            continue

        ts = data.get("timestamp_utc")
        age_s = _age_seconds(ts, now)
        freshness = _freshness_label(age_s)

        results[name] = {
            "path":        str(path),
            "exists":      True,
            "age_s":       round(age_s, 1) if age_s is not None else None,
            "freshness":   freshness,
            "timestamp":   ts,
            "is_critical": name in CRITICAL_BLOCKS,
        }

        if freshness in ("STALE", "VERY_STALE"):
            if name in CRITICAL_BLOCKS:
                stale_critical.append(name)
            else:
                stale_non_critical.append(name)

    return {
        "inputs":              results,
        "stale_critical":      stale_critical,
        "stale_non_critical":  stale_non_critical,
        "missing_critical":    missing,
    }


def _determine_sync_status(check: dict[str, Any]) -> str:
    """
    Pipeline bu context_id ile guvenle calisabilir mi?

    SYNC_OK:       Tum kritik dosyalar FRESH veya RECENT
    SYNC_DEGRADED: Bazi kritik dosyalar STALE ama calisiyor
    SYNC_BROKEN:   Kritik dosya VERY_STALE veya MISSING
    """
    missing    = check["missing_critical"]
    stale_crit = check["stale_critical"]

    if missing:
        return "SYNC_BROKEN"

    # Very_stale kontrolu
    for name in CRITICAL_BLOCKS:
        item = check["inputs"].get(name, {})
        if item.get("freshness") == "VERY_STALE":
            return "SYNC_BROKEN"

    if stale_crit:
        return "SYNC_DEGRADED"

    return "SYNC_OK"


def _find_oldest_critical(check: dict[str, Any]) -> dict[str, Any]:
    """Kritik bloklar arasinda en eski hangisi?"""
    oldest_age  = -1.0
    oldest_name = None
    oldest_ts   = None

    for name in CRITICAL_BLOCKS:
        item = check["inputs"].get(name, {})
        age = item.get("age_s")
        if age is not None and age > oldest_age:
            oldest_age  = age
            oldest_name = name
            oldest_ts   = item.get("timestamp")

    return {
        "name":       oldest_name,
        "age_s":      round(oldest_age, 1) if oldest_age >= 0 else None,
        "timestamp":  oldest_ts,
    }


def _build_lineage_anchor(
    context_id: str,
    check: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """
    Her trade zinciri bu anchor'dan baslayacak.
    Hangi context_id altinda hangi inputlar kullanildi?
    """
    return {
        "context_id":     context_id,
        "pipeline_start": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_snapshot": {
            name: {
                "timestamp": item.get("timestamp"),
                "age_s":     item.get("age_s"),
                "freshness": item.get("freshness"),
            }
            for name, item in check["inputs"].items()
            if item.get("exists")
        },
    }


def run_context_sync() -> dict[str, Any]:
    """Ana fonksiyon. Pipeline basinda cagrilir."""
    now        = _now_dt()
    context_id = _generate_context_id(now)
    check      = _check_all_inputs(now)
    sync_status = _determine_sync_status(check)
    oldest     = _find_oldest_critical(check)
    lineage    = _build_lineage_anchor(context_id, check, now)

    # Reason codes
    reason_codes = [
        f"CONTEXT_ID_{context_id}",
        f"SYNC_STATUS_{sync_status}",
        f"SYMBOL_BTCUSDT",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
    ]
    if check["stale_critical"]:
        reason_codes.append(f"STALE_CRITICAL_{','.join(check['stale_critical'])}")
    if check["missing_critical"]:
        reason_codes.append(f"MISSING_CRITICAL_{','.join(check['missing_critical'])}")
    if check["stale_non_critical"]:
        reason_codes.append(f"STALE_NON_CRITICAL_{len(check['stale_non_critical'])}_BLOCKS")

    result = {
        "timestamp_utc":   _utc_now(),
        "block_id":        "S0_CONTEXT_SYNC",
        "context_id":      context_id,
        "symbol":          "BTCUSDT",

        "sync_status":     sync_status,
        "pipeline_ready":  sync_status in ("SYNC_OK", "SYNC_DEGRADED"),

        "input_check":     check,
        "oldest_critical": oldest,
        "lineage_anchor":  lineage,

        "summary": {
            "total_inputs":          len(INPUT_FILES),
            "fresh_count":           sum(1 for v in check["inputs"].values()
                                        if v.get("freshness") == "FRESH"),
            "recent_count":          sum(1 for v in check["inputs"].values()
                                        if v.get("freshness") == "RECENT"),
            "stale_count":           sum(1 for v in check["inputs"].values()
                                        if v.get("freshness") == "STALE"),
            "very_stale_count":      sum(1 for v in check["inputs"].values()
                                        if v.get("freshness") == "VERY_STALE"),
            "missing_count":         sum(1 for v in check["inputs"].values()
                                        if not v.get("exists")),
            "stale_critical_count":  len(check["stale_critical"]),
            "missing_critical_count": len(check["missing_critical"]),
        },

        "reason_codes": reason_codes,
        "data_quality": {
            "level": "HIGH"   if sync_status == "SYNC_OK"       else
                     "MEDIUM" if sync_status == "SYNC_DEGRADED"  else "LOW",
            "score": 1.0      if sync_status == "SYNC_OK"       else
                     0.6      if sync_status == "SYNC_DEGRADED"  else 0.2,
            "issues": (check["stale_critical"] + check["missing_critical"]),
        },
        "feeds_next": {
            "next_blocks": ["S1_MARKET_TRUTH", "S2_EVIDENCE", "S3_CANDLE_DNA"],
            "note": "context_id must be passed to all downstream blocks",
        },
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used":        False,
            "live_order_sent":         False,
        },
    }

    # Dosyalara yaz
    _write(OUTPUT_PATH, result)
    _write(S0_STATE_PATH, {
        "timestamp_utc":  _utc_now(),
        "context_id":     context_id,
        "sync_status":    sync_status,
        "pipeline_ready": result["pipeline_ready"],
        "oldest_critical_age_s": oldest.get("age_s"),
    })

    return result


def _write(path: Path, data: dict) -> None:
    import os, tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_current_context_id() -> str | None:
    """
    Diger bloklar bu fonksiyonu cagirarak
    mevcut context_id'yi alabilir.
    """
    data = _load_json(OUTPUT_PATH)
    if data:
        return data.get("context_id")
    return None


def is_pipeline_ready() -> bool:
    """Pipeline calismaya hazir mi?"""
    data = _load_json(OUTPUT_PATH)
    if data:
        return bool(data.get("pipeline_ready", False))
    return False


def main() -> None:
    result = run_context_sync()

    # Konsol ozeti
    s = result["summary"]
    print(f"\n{'='*55}")
    print(f"  CONTEXT SYNC — {result['context_id']}")
    print(f"{'='*55}")
    print(f"  Sync Status  : {result['sync_status']}")
    print(f"  Ready        : {result['pipeline_ready']}")
    print(f"  Fresh        : {s['fresh_count']} / Recent: {s['recent_count']}")
    print(f"  Stale        : {s['stale_count']} / Very Stale: {s['very_stale_count']}")
    print(f"  Missing      : {s['missing_count']}")
    if result['input_check']['stale_critical']:
        print(f"  ⚠ Stale crit : {result['input_check']['stale_critical']}")
    if result['input_check']['missing_critical']:
        print(f"  ✗ Missing    : {result['input_check']['missing_critical']}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
