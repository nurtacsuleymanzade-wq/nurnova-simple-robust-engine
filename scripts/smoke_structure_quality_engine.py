from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.edge.structure_quality_engine import build_structure_quality_from_payloads, run_structure_quality_engine
from src.simple.research_runtime import load_json


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _payloads() -> dict:
    return {
        "market_structure": {
            "1m": {
                "tf": "1m",
                "structure_label": "HH",
                "trend_state": "BULLISH",
                "last_swing_high": 105.0,
                "last_swing_low": 100.0,
                "bos_detected": True,
                "choch_detected": False,
                "mss_detected": True,
                "data_quality": {"level": "HIGH", "sample_count": 30},
            },
            "5m": {
                "tf": "5m",
                "structure_label": "LH",
                "trend_state": "BEARISH",
                "last_swing_high": 106.0,
                "last_swing_low": 99.0,
                "bos_detected": False,
                "choch_detected": True,
                "mss_detected": False,
                "data_quality": {"level": "HIGH", "sample_count": 24},
            },
            "1h": {
                "tf": "1h",
                "structure_label": "EQH",
                "trend_state": "RANGE",
                "last_swing_high": 108.0,
                "last_swing_low": 98.0,
                "bos_detected": False,
                "choch_detected": False,
                "mss_detected": False,
                "data_quality": {"level": "HIGH", "sample_count": 40},
            },
            "4h": {
                "tf": "4h",
                "structure_label": "EQL",
                "trend_state": "RANGE",
                "last_swing_high": 110.0,
                "last_swing_low": 96.0,
                "bos_detected": False,
                "choch_detected": False,
                "mss_detected": False,
                "data_quality": {"level": "HIGH", "sample_count": 40},
            },
        },
        "mtf_candle_dna": {
            "1m": {"close": 106.5, "atr_14": 1.0},
            "5m": {"close": 97.5, "atr_14": 1.5},
            "1h": {"close": 107.0, "atr_14": 2.0},
            "4h": {"close": 97.0, "atr_14": 2.5},
        },
        "liquidity_map": {
            "detected_levels": [
                {"price": 105.0, "bucket": "NEAR", "liquidity_type": "untested_high", "strength": "HIGH"},
                {"price": 99.0, "bucket": "NEAR", "liquidity_type": "untested_low", "strength": "HIGH"},
            ]
        },
        "interpretation": {"interpretation_text": "Failed breakout and reclaim after sweep with absorption.", "structure_summary": "Structure remains range-bound with no accepted directional break."},
        "three_scenarios": {"scenario_label": "compression", "reason_codes": ["FAILED_BREAKOUT"]},
        "unified_context": {"symbol": "BTCUSDT", "current_price": 104.0},
        "volume_profile": {"windows": {"30m": {"poc": {"mid_price": 104.0}, "vah": 106.0, "val": 100.0, "vamid": 103.0}}},
        "zone_context": {"zones": [{"zone_type": "DISCOUNT_ZONE", "mid_price": 100.0}, {"zone_type": "REAL_LVN_ZONE", "mid_price": 106.0}]},
    }


def main() -> None:
    built = build_structure_quality_from_payloads(_payloads(), {"market_structure_history": [{}] * 12})
    event_types = {event.get("structure_type") for event in built.get("structure_events") or []}
    combos = {item.get("label") for item in built.get("structure_liquidity_zone_combos") or []}
    _assert("BOS_BULLISH" in event_types, "Synthetic BOS missing")
    _assert("CHOCH_BEARISH" in event_types, "Synthetic CHOCH missing")
    _assert(bool(built.get("range_quality")), "Range quality missing")
    _assert(bool(built.get("htf_decision_zones")), "HTF decision quality missing")
    _assert(any((event.get("fakeout_risk") or "") in {"HIGH", "MEDIUM", "LOW"} for event in built.get("structure_events") or []), "Fake breakout risk missing")
    _assert(any(label in combos for label in {"SWEEP_THEN_RECLAIM", "STRUCTURE_BREAK_WITHOUT_FOLLOWTHROUGH", "BOS_INTO_LIQUIDITY_POOL"}), "Structure combo missing")
    output = run_structure_quality_engine()
    _assert((ROOT / "state/simple/latest_structure_quality.json").exists(), "latest structure quality state missing")
    _assert((ROOT / "reports/simple/epoch_v2/latest_structure_quality_report.md").exists(), "structure quality report missing")
    state = load_json(ROOT / "state/simple/latest_structure_quality.json") or {}
    _assert(state.get("execution_safety", {}).get("live_order_sent") is False, "Engine must remain passive")
    print("STRUCTURE_QUALITY_ENGINE_OK")
    print("BOS_SCORE_OK")
    print("CHOCH_SCORE_OK")
    print("RANGE_QUALITY_OK")
    print("HTF_DECISION_OK")
    print("FAKE_BREAKOUT_OK")
    print("STRUCTURE_ZONE_COMBO_OK")
    print("PASSIVE_MODE_OK")
    print(json.dumps({"event_count": len(output.get("structure_events") or []), "range_quality": (output.get("range_quality") or {}).get("range_quality_band")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
