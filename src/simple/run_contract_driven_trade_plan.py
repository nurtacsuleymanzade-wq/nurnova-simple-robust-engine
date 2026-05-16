from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from src.simple.contract_driven_trade_plan_engine import OUTPUT_PATH, run_contract_driven_trade_plan
from src.simple.research_runtime import write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Contract-Driven Trade Plan Engine")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    try:
        result = run_contract_driven_trade_plan(symbol=args.symbol, fake_sample=args.fake_sample)
    except Exception as exc:
        result = {
            "timestamp_utc": _utc_now(),
            "block_id": "CONTRACT_DRIVEN_TRADE_PLAN",
            "symbol": args.symbol,
            "source": {"source_mode": "STATE_FILE"},
            "data_quality": "INVALID",
            "plan_status": "INVALID",
            "contract_id": None,
            "setup_family": None,
            "direction": "NEUTRAL",
            "entry": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "rr1": None,
            "rr2": None,
            "risk_distance": None,
            "reward_distance_1": None,
            "reward_distance_2": None,
            "entry_model": None,
            "sl_model": None,
            "tp_model": None,
            "invalidation_level": None,
            "destination_level_1": None,
            "destination_level_2": None,
            "plan_confidence": 0.0,
            "session_downgrade": False,
            "regime_alignment": "UNKNOWN",
            "liquidity_alignment": "UNKNOWN",
            "reason_codes": ["RUNNER_EXCEPTION", "SOURCE_FILE_MISSING", f"EXC_{str(exc)[:80]}"],
            "feeds_next": ["DECISION_GATE", "PAPER_LIFECYCLE", "OUTCOME_TRACKER"],
        }
        write_json(OUTPUT_PATH, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("CONTRACT_DRIVEN_TRADE_PLAN READY")


if __name__ == "__main__":
    main()
