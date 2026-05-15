from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.edge.elite_context_detector import detect_elite_continuation_context  # noqa: E402
from src.edge.zone_engine import build_zone_context_from_payloads, run_zone_engine  # noqa: E402


def _payloads(current_price: float | None = 40.0) -> dict:
    return {
        "market_truth": {"timestamp_utc": "2026-05-15T00:00:00Z", "price": current_price, "symbol": "BTCUSDT"},
        "one_s_evidence": {},
        "hybrid_candle_dna": {},
        "mtf_candle_dna": {},
        "market_structure": {"range_low": 0.0, "range_high": 100.0},
        "liquidity_map": {},
        "interpretation": {},
        "business_zone": {"poc": 50.0, "hvn": 45.0, "lvn": 70.0},
        "market_regime": {},
        "intent_analysis": {},
        "depth_liquidity_memory": {},
        "wall_lifecycle": {},
        "unified_context": {"current_price": current_price, "symbol": "BTCUSDT"},
        "atr_state": {},
        "three_scenarios": {},
        "flow_evidence": {},
        "flow_persistence": {},
    }


def _zone_types(result: dict) -> set[str]:
    return {str(zone.get("zone_type")) for zone in result.get("zones") or []}


def main() -> None:
    discount = build_zone_context_from_payloads(_payloads(25.0))
    premium = build_zone_context_from_payloads(_payloads(75.0))
    equilibrium = build_zone_context_from_payloads(_payloads(50.0))
    assert "DISCOUNT_ZONE" in _zone_types(discount)
    assert "PREMIUM_ZONE" in _zone_types(premium)
    assert "EQUILIBRIUM_ZONE" in _zone_types(equilibrium)

    profile_zones = [zone for zone in discount.get("zones") or [] if zone.get("zone_type") in {"APPROX_POC_ZONE", "APPROX_HVN_ZONE", "APPROX_LVN_ZONE"}]
    assert profile_zones
    assert all(zone.get("approximation_level") == "APPROX" for zone in profile_zones)

    missing = build_zone_context_from_payloads({key: {} for key in _payloads(None)})
    diagnostic = [zone for zone in missing.get("zones") or [] if zone.get("approximation_level") == "DIAGNOSTIC"]
    assert diagnostic
    assert any("ZONE_SOURCE_INSUFFICIENT" in (zone.get("reason_codes") or []) for zone in diagnostic)

    elite = detect_elite_continuation_context(
        {
            "conditions": [
                "COND_STRUCTURE_BULLISH",
                "COND_REGIME_MOMENTUM",
                "COND_BUYERS_ATTACKING",
                "COND_NEAR_LIQUIDITY_ABOVE",
                "COND_ATR_EXPANDING",
            ],
            "zone_context": discount,
        },
        {"clusters": [{"dominant_model_id": "MTF_ALIGNMENT_LONG"}]},
        {"direction": "LONG"},
    )
    assert elite.get("context_type") == "ELITE_CONTINUATION_CONTEXT"

    output = run_zone_engine()
    assert (ROOT / "state/simple/latest_zone_context.json").exists()
    assert (ROOT / "state/simple/epoch_v2/latest_zone_context.json").exists()
    assert (ROOT / "data/simple/zone_context_history.jsonl").exists()
    assert (ROOT / "data/simple/epoch_v2/zone_context_history.jsonl").exists()
    assert (ROOT / "reports/simple/epoch_v2/latest_zone_context_report.md").exists()
    assert output.get("passive_mode") is True
    assert output.get("execution_safety", {}).get("live_order_sent") is False

    print("ZONE_CONTEXT_ENGINE_OK")
    print("PASSIVE_MODE_OK")
    print("APPROX_PROFILE_ZONES_OK")
    print("DIAGNOSTIC_ZONES_OK")
    print(json.dumps({"zone_count": (output.get("summary") or {}).get("zone_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
