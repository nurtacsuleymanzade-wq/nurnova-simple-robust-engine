from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.simple.telegram_research_reporter as reporter  # noqa: E402


def main() -> None:
    event = {
        "timestamp_utc": "2026-05-15T00:10:20Z",
        "event_id": "EVT_SMOKE",
        "paper_trade_id": "PT_SMOKE",
        "context_id": "CTX_SMOKE",
        "loop_id": 77,
        "signal_grade": "A_PLUS",
        "primary_setup": "CONTINUATION",
        "primary_model": "MTF_ALIGNMENT_LONG",
        "supporting_models": ["IB01_LONG"],
        "direction": "LONG",
        "primary_tf": "5m",
        "trigger_tf": "1m",
        "context_tf": "15m",
        "structure_tf": "1h",
        "expected_hold_label": "15m-90m",
        "entry": 100.0,
        "stop_loss": 98.0,
        "tp1": 103.0,
        "tp2": 106.0,
        "rr1": 1.5,
        "rr2": 3.0,
    }
    elite = {"context_type": "ELITE_CONTINUATION_CONTEXT", "conditions": ["COND_STRUCTURE_BULLISH", "COND_ATR_EXPANDING"]}
    dna = {"tp_edge_conditions": [{"condition": "COND_STRUCTURE_BULLISH", "tp_count": 3}]}
    zone = {
        "zones": [
            {
                "zone_type": "LIQUIDITY_POOL_ZONE",
                "approximation_level": "APPROX",
                "zone_meaning": "Stop cluster or resting liquidity concentration.",
            }
        ]
    }
    signal_text, meta = reporter.render_elite_signal_message(event, elite, dna, zone, {"timestamp_utc": "2026-05-15T00:00:00Z"}, {"timestamp_utc": "2026-05-15T00:00:01Z"})
    assert "NURNOVA ELITE SIGNAL" in signal_text
    assert "Signal Birth Time UTC: 2026-05-15T00:10:20Z" in signal_text
    assert "Signal Birth Time Local UTC+4: 2026-05-15 04:10:20 UTC+4" in signal_text
    assert "Event ID: EVT_SMOKE" in signal_text
    assert "status: TRACKING_STARTED" in signal_text
    assert "LIQUIDITY_POOL_ZONE" in signal_text

    closed_tp = dict(event, close_reason="TP1_HIT", closed_at_utc="2026-05-15T00:30:20Z", exit_price=103.0, r_result=1.5, mfe=3.2, mae=-0.4, hold_seconds=1200, zone_context=zone["zones"])
    closed_sl = dict(event, close_reason="SL_HIT", closed_at_utc="2026-05-15T00:20:20Z", exit_price=98.0, r_result=-1.0, mfe=0.5, mae=-2.0, hold_seconds=600, zone_context=zone["zones"])
    tp_text = reporter.render_lifecycle_followup_message(closed_tp, dna, zone)
    sl_text = reporter.render_lifecycle_followup_message(closed_sl, dna, zone)
    assert "NURNOVA TP1 HIT" in tp_text
    assert "NURNOVA SL HIT" in sl_text
    assert "Closed Time UTC+4: 2026-05-15 04:30:20 UTC+4" in tp_text
    assert "Paper Trade ID: PT_SMOKE" in tp_text

    original_load_json = reporter.load_json

    def fake_load_json(path):
        text = str(path)
        if text.endswith("latest_edge_learning_dashboard.json"):
            return {
                "active_models": ["MTF_ALIGNMENT_LONG"],
                "quarantined_models": ["FCR_LONG"],
                "best_model": {"key": "FCR_LONG", "avg_r": 1.0},
                "worst_model": {"key": "FCR_LONG", "avg_r": -1.0},
                "elite_context_count": 1,
                "tp1_count": 1,
                "tp2_count": 0,
                "sl_count": 1,
                "expired_count": 0,
                "winrate": 0.5,
                "expectancy": 0.25,
                "best_zone": {"key": "LIQUIDITY_POOL_ZONE"},
                "worst_zone": {},
                "best_condition_dna": {"condition": "COND_STRUCTURE_BULLISH"},
                "worst_condition_dna": {},
                "best_timeframe_combo": {"key": "5m/15m"},
            }
        if text.endswith("latest_model_survival_report.json"):
            return {"active_models": ["MTF_ALIGNMENT_LONG"], "quarantined_models": ["FCR_LONG"]}
        if text.endswith("latest_zone_context.json"):
            return zone
        if text.endswith("latest_tp_condition_dna.json") or text.endswith("latest_edge_query_report.json"):
            return {}
        return original_load_json(path)

    reporter.load_json = fake_load_json
    try:
        report_text, payload = reporter._summary_message({}, {"summary": {"open": 1}}, {"summary": {"closed_count": 2}}, {}, {}, {})
    finally:
        reporter.load_json = original_load_json
    assert "NURNOVA EDGE LEARNING REPORT" in report_text
    assert "NURNOVA EDGE REPORT 15M" not in report_text
    assert "Best Active Model: SAMPLE_BUILDING" in report_text
    assert "Best Active Model: FCR_LONG" not in report_text

    print("TELEGRAM_MESSAGE_CONTRACT_OK")
    print("SIGNAL_TIME_OK")
    print("UTC4_TIME_OK")
    print("FOLLOWUP_TP_SL_OK")
    print("OLD_EDGE_REPORT_DISABLED_OK")
    print("QUARANTINED_BEST_MODEL_BLOCKED_OK")
    print("ZONE_CONTEXT_ENRICHMENT_OK")
    print("---ELITE_SIGNAL_EXAMPLE---")
    print(signal_text)
    print("---TP_FOLLOWUP_EXAMPLE---")
    print(tp_text)
    print("---EDGE_REPORT_EXAMPLE---")
    print(report_text)


if __name__ == "__main__":
    main()
