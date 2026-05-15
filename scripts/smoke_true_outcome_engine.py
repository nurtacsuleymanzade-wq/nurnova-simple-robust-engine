from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.edge.true_outcome_engine import build_true_edge_dataset, replay_trade_outcome, run_true_outcome_engine  # noqa: E402
from src.simple.telegram_research_reporter import render_lifecycle_followup_message  # noqa: E402


def candles(*rows):
    return [
        {"timestamp_utc": ts, "open": o, "high": h, "low": l, "close": c}
        for ts, o, h, l, c in rows
    ]


def base_trade(**overrides):
    trade = {
        "paper_trade_id": "PT_TRUE_SMOKE",
        "event_id": "EVT_TRUE_SMOKE",
        "model_id": "MTF_ALIGNMENT_LONG",
        "setup_family": "CONTINUATION",
        "direction": "LONG",
        "entry": 100.0,
        "stop_loss": 98.0,
        "tp1": 103.0,
        "tp2": 105.0,
        "opened_at_utc": "2026-05-15T00:00:00Z",
        "expected_hold_minutes": 10,
        "primary_tf": "5m",
        "trigger_tf": "1m",
        "context_tf": "15m",
        "structure_tf": "1h",
        "plan_style": "TEST",
    }
    trade.update(overrides)
    return trade


def main() -> None:
    entry_touch = replay_trade_outcome(
        base_trade(),
        candles(("2026-05-15T00:01:00Z", 101, 102, 99.5, 101), ("2026-05-15T00:02:00Z", 101, 103.2, 100, 103)),
    )
    assert entry_touch["entry_touched"] is True
    assert entry_touch["outcome_status"] == "TP1_HIT"

    tp2 = replay_trade_outcome(base_trade(), candles(("2026-05-15T00:01:00Z", 100, 105.5, 99.5, 105)))
    assert tp2["outcome_status"] == "TP2_HIT"

    sl = replay_trade_outcome(base_trade(), candles(("2026-05-15T00:01:00Z", 100, 101, 97.5, 98)))
    assert sl["outcome_status"] == "SL_HIT"

    expired = replay_trade_outcome(base_trade(), candles(("2026-05-15T00:01:00Z", 100, 101, 99.5, 100.5), ("2026-05-15T00:11:00Z", 100.5, 101, 99, 100)))
    assert expired["outcome_status"] == "EXPIRED"

    order = replay_trade_outcome(base_trade(), candles(("2026-05-15T00:01:00Z", 100, 102, 99.5, 101), ("2026-05-15T00:02:00Z", 101, 103.5, 100.5, 103)))
    assert order["first_hit"] == "TP1_HIT"

    assert tp2["mfe"] > 0
    assert sl["mae"] > 0
    assert tp2["realized_r"] == 2.5
    assert sl["realized_r"] == -1.0

    dataset = build_true_edge_dataset([tp2, sl, expired], {"zones": [{"zone_type": "LIQUIDITY_POOL_ZONE"}]}, {"tp_edge_conditions": [{"condition": "COND_STRUCTURE_BULLISH"}]})
    assert dataset["summary"]["row_count"] == 3

    tp_msg = render_lifecycle_followup_message(tp2, {"tp_edge_conditions": [{"condition": "COND_STRUCTURE_BULLISH"}]}, {"zones": [{"zone_type": "LIQUIDITY_POOL_ZONE", "approximation_level": "APPROX", "zone_meaning": "Stop cluster"}]})
    sl_msg = render_lifecycle_followup_message(sl, {"tp_edge_conditions": [{"condition": "COND_STRUCTURE_BULLISH"}]}, {"zones": [{"zone_type": "LIQUIDITY_POOL_ZONE", "approximation_level": "APPROX", "zone_meaning": "Stop cluster"}]})
    assert "NURNOVA TP2 HIT" in tp_msg
    assert "NURNOVA SL HIT" in sl_msg

    output = run_true_outcome_engine()
    assert (ROOT / "state/simple/epoch_v2/latest_true_outcome.json").exists()
    assert (ROOT / "state/simple/epoch_v2/latest_true_edge_dataset.json").exists()
    assert (ROOT / "reports/simple/epoch_v2/latest_true_outcome_report.md").exists()
    assert output.get("execution_safety", {}).get("live_order_sent") is False

    print("TRUE_OUTCOME_ENGINE_OK")
    print("ENTRY_TOUCH_OK")
    print("TP_SL_ORDER_OK")
    print("EXPIRED_OK")
    print("MFE_MAE_OK")
    print("REALIZED_R_OK")
    print("TRUE_EDGE_DATASET_OK")
    print("TELEGRAM_FOLLOWUP_OK")
    print("PASSIVE_MODE_OK")
    print("---TP_FOLLOWUP_EXAMPLE---")
    print(tp_msg)
    print("---SL_FOLLOWUP_EXAMPLE---")
    print(sl_msg)


if __name__ == "__main__":
    main()
