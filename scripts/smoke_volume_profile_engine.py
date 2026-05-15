from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.edge.volume_profile_engine import build_volume_profile_from_samples, run_volume_profile_engine
from src.edge.zone_engine import build_zone_context_from_payloads
from src.simple.research_runtime import load_json


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    synthetic = [
        {"timestamp": __import__("datetime").datetime(2026, 5, 15, 0, 0, tzinfo=__import__("datetime").timezone.utc), "price": 100.0, "volume": 2.0, "source": "TRADE_VOLUME"},
        {"timestamp": __import__("datetime").datetime(2026, 5, 15, 0, 1, tzinfo=__import__("datetime").timezone.utc), "price": 100.0, "volume": 3.0, "source": "TRADE_VOLUME"},
        {"timestamp": __import__("datetime").datetime(2026, 5, 15, 0, 2, tzinfo=__import__("datetime").timezone.utc), "price": 101.0, "volume": 1.0, "source": "TRADE_VOLUME"},
        {"timestamp": __import__("datetime").datetime(2026, 5, 15, 0, 3, tzinfo=__import__("datetime").timezone.utc), "price": 103.0, "volume": 0.2, "source": "TRADE_VOLUME"},
        {"timestamp": __import__("datetime").datetime(2026, 5, 15, 0, 4, tzinfo=__import__("datetime").timezone.utc), "price": 100.0, "volume": 2.5, "source": "TRADE_VOLUME"},
        {"timestamp": __import__("datetime").datetime(2026, 5, 15, 0, 5, tzinfo=__import__("datetime").timezone.utc), "price": 102.0, "volume": 2.0, "source": "TRADE_VOLUME"},
    ]
    synthetic_profile = build_volume_profile_from_samples(synthetic, symbol="BTCUSDT")
    profile_30m = synthetic_profile["windows"]["30m"]
    poc = profile_30m["poc"]
    _assert(synthetic_profile["profile_status"] == "OK", "Synthetic trade-volume profile should be OK")
    _assert(abs((poc.get("mid_price") or 0.0) - 100.5) < 0.6, "POC mid should center around the most traded price bin")
    _assert(bool(profile_30m["hvn_zones"]), "HVN cluster missing")
    _assert(bool(profile_30m["lvn_zones"]), "LVN gap missing")
    _assert(profile_30m["vah"] is not None and profile_30m["val"] is not None, "Value area missing")
    diagnostic = build_volume_profile_from_samples([], symbol="BTCUSDT")
    _assert(diagnostic["profile_status"] == "INSUFFICIENT_DATA", "Insufficient data should stay diagnostic")
    payloads = {
        "market_truth": {},
        "one_s_evidence": {},
        "hybrid_candle_dna": {},
        "mtf_candle_dna": {},
        "market_structure": {},
        "liquidity_map": {},
        "interpretation": {},
        "business_zone": {"poc": 99.0, "hvn": 99.5, "lvn": 98.5},
        "market_regime": {},
        "intent_analysis": {},
        "depth_liquidity_memory": {},
        "wall_lifecycle": {},
        "unified_context": {},
        "atr_state": {},
        "three_scenarios": {},
        "flow_evidence": {},
        "flow_persistence": {},
        "volume_profile": synthetic_profile,
    }
    zone_context = build_zone_context_from_payloads(payloads)
    zone_types = {zone.get("zone_type") for zone in zone_context.get("zones") or []}
    _assert("REAL_POC_ZONE" in zone_types, "Zone engine did not upgrade to real POC zone")
    _assert("APPROX_POC_ZONE" not in zone_types, "Approximate POC should be replaced when real profile is OK")
    output = run_volume_profile_engine()
    _assert(Path(ROOT / "state/simple/latest_volume_profile.json").exists(), "latest_volume_profile.json missing")
    _assert(Path(ROOT / "reports/simple/epoch_v2/latest_volume_profile_report.md").exists(), "volume profile report missing")
    profile_state = load_json(ROOT / "state/simple/latest_volume_profile.json") or {}
    _assert(profile_state.get("execution_safety", {}).get("live_order_sent") is False, "Profile engine must stay passive")
    print("REAL_VOLUME_PROFILE_ENGINE_OK")
    print("POC_OK")
    print("HVN_OK")
    print("LVN_OK")
    print("VALUE_AREA_OK")
    print("INSUFFICIENT_DATA_OK")
    print("ZONE_UPGRADE_OK")
    print("PASSIVE_MODE_OK")
    print(json.dumps({"profile_status": output.get("profile_status"), "windows": list((output.get("windows") or {}).keys())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
