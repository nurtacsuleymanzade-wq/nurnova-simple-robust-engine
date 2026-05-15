from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.edge.edge_io import write_json_atomic
from src.edge.edge_learning_dashboard import (
    DASHBOARD_PATH,
    EDGE_QUERY_PATH,
    MODEL_SURVIVAL_REPORT_PATH,
    REPORT_PATH,
    STRUCTURE_QUALITY_PATH,
    TP_DNA_PATH,
    TRUE_OUTCOME_PATH,
    VOLUME_PROFILE_PATH,
    ZONE_PATH,
    run_edge_learning_dashboard,
)


def _seed_inputs() -> None:
    write_json_atomic(
        TRUE_OUTCOME_PATH,
        {
            "timestamp_utc": "2026-05-15T00:00:00Z",
            "block_id": "TRUE_OUTCOME_ENGINE",
            "outcomes": [
                {"paper_trade_id": "PT1", "model_id": "MTF_ALIGNMENT_LONG", "setup_family": "A", "outcome_status": "TP2_HIT", "realized_r": 2.5, "entry_touched": True},
                {"paper_trade_id": "PT2", "model_id": "FCR_LONG", "setup_family": "B", "outcome_status": "SL_HIT", "realized_r": -1.0, "entry_touched": True},
                {"paper_trade_id": "PT3", "model_id": "MTF_ALIGNMENT_LONG", "setup_family": "A", "outcome_status": "ENTRY_NOT_TOUCHED", "realized_r": 0.0, "entry_touched": False},
            ],
        },
    )
    write_json_atomic(
        MODEL_SURVIVAL_REPORT_PATH,
        {
            "timestamp_utc": "2026-05-15T00:00:01Z",
            "active_models": ["MTF_ALIGNMENT_LONG"],
            "quarantined_models": ["FCR_LONG"],
        },
    )
    write_json_atomic(
        TP_DNA_PATH,
        {
            "timestamp_utc": "2026-05-15T00:00:02Z",
            "tp_edge_conditions": [{"condition": "COND_STRUCTURE_BULLISH", "tp_minus_sl": 3}],
            "sl_risk_conditions": [{"condition": "COND_WEAK_DELTA", "tp_minus_sl": -2}],
            "by_zone": {"DISCOUNT_ZONE": {"outcomes": {"tp": 3, "sl": 1, "avg_r": 1.1, "samples": 4}}},
        },
    )
    write_json_atomic(
        ZONE_PATH,
        {
            "timestamp_utc": "2026-05-15T00:00:03Z",
            "zones": [
                {"zone_type": "DISCOUNT_ZONE", "approximation_level": "EXACT"},
                {"zone_type": "LIQUIDITY_POOL_ZONE", "approximation_level": "APPROX"},
            ],
        },
    )
    write_json_atomic(
        VOLUME_PROFILE_PATH,
        {
            "timestamp_utc": "2026-05-15T00:00:04Z",
            "profile_status": "APPROX",
            "windows": {"30m": {"poc": {"price_low": 1, "price_high": 1}, "hvn_zones": [{"price_low": 1, "price_high": 2}], "lvn_zones": [{"price_low": 2, "price_high": 3}]}}
        },
    )
    write_json_atomic(
        STRUCTURE_QUALITY_PATH,
        {
            "timestamp_utc": "2026-05-15T00:00:05Z",
            "summary": {"structure_event_count": 3},
            "structure_events": [
                {"structure_type": "BOS_BULLISH", "quality_band": "HIGH_CONFIDENCE", "quality_score": 0.9},
                {"structure_type": "CHOCH_BEARISH", "quality_band": "LOW_CONFIDENCE", "quality_score": 0.2},
            ],
            "structure_liquidity_zone_combos": [{"combo_label": "BULLISH_STRUCTURE_AT_DISCOUNT"}],
        },
    )
    write_json_atomic(
        EDGE_QUERY_PATH,
        {
            "timestamp_utc": "2026-05-15T00:00:06Z",
            "by_timeframe": {"5m|1m|15m|15m": {"samples": 4, "outcomes": {"tp": 3, "sl": 1, "avg_r": 1.1}}},
            "questions": [{}, {}, {}, {}, {}, {"summary": {"no_trade_correct_rate": 0.75}}],
        },
    )


def main() -> None:
    _seed_inputs()
    dashboard = run_edge_learning_dashboard()
    report_text = REPORT_PATH.read_text(encoding="utf-8")

    assert dashboard.get("block_id") == "EDGE_LEARNING_DASHBOARD_V2"
    assert dashboard.get("summary", {}).get("total_true_samples") >= 1
    assert all((item.get("model_id") or "") != "FCR_LONG" for item in dashboard.get("best_active_models") or [])
    assert dashboard.get("best_active_models"), "missing best active models"
    assert dashboard.get("best_zones"), "missing zones"
    assert dashboard.get("best_volume_profile_zones"), "missing volume profile zones"
    assert dashboard.get("best_structure_quality"), "missing structure quality zones"
    assert "## 12. Telegram Watchlist" in report_text

    exec_safety = dashboard.get("execution_safety") or {}
    assert exec_safety.get("live_order_sent") is False
    assert exec_safety.get("private_api_used") is False

    print("EDGE_LEARNING_DASHBOARD_V2_OK")
    print("QUARANTINED_MODEL_EXCLUDED_OK")
    print("TRUE_OUTCOME_SUMMARY_OK")
    print("ZONE_SUMMARY_OK")
    print("VOLUME_PROFILE_SUMMARY_OK")
    print("STRUCTURE_QUALITY_SUMMARY_OK")
    print("MARKDOWN_REPORT_OK")
    print("PASSIVE_MODE_OK")
    print(json.dumps({"dashboard_path": str(DASHBOARD_PATH), "report_path": str(REPORT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
