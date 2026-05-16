from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from src.simple.research_runtime import write_json
from src.simple.setup_contract_engine import OUTPUT_PATH, run_setup_contract_engine


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Setup Contract Engine")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    try:
        result = run_setup_contract_engine(symbol=args.symbol, fake_sample=args.fake_sample)
    except Exception as exc:
        result = {
            "timestamp_utc": _utc_now(),
            "block_id": "SETUP_CONTRACT_ENGINE",
            "symbol": args.symbol,
            "data_quality": "INVALID",
            "contract_status": "INVALID",
            "selected_contract": None,
            "eligible_contracts": [],
            "blocked_contracts": [],
            "directional_bias": "NEUTRAL",
            "regime": "UNKNOWN",
            "structure_bias": "UNKNOWN",
            "confidence": 0.0,
            "session_downgrade": False,
            "regime_alignment": "UNKNOWN",
            "liquidity_alignment": "UNKNOWN",
            "reason_codes": ["RUNNER_EXCEPTION", "SOURCE_FILE_MISSING", f"EXC_{str(exc)[:80]}"],
            "feeds_next": ["TRADE_PLAN_ENGINE", "DECISION_GATE", "PAPER_LIFECYCLE"],
        }
        write_json(OUTPUT_PATH, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("SETUP_CONTRACT_ENGINE READY")


if __name__ == "__main__":
    main()
