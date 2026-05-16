from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from src.simple.contract_decision_gate import OUTPUT_PATH, run_contract_decision_gate
from src.simple.research_runtime import write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Contract Decision Gate")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    try:
        result = run_contract_decision_gate(symbol=args.symbol, fake_sample=args.fake_sample)
    except Exception as exc:
        result = {
            "timestamp_utc": _utc_now(),
            "block_id": "CONTRACT_DECISION_GATE",
            "symbol": args.symbol,
            "source": {"source_mode": "STATE_FILE"},
            "mode": "EXPLORATION_ALLOW_MODE",
            "data_quality": "INVALID",
            "decision_status": "BLOCK",
            "direction": "NEUTRAL",
            "contract_id": None,
            "setup_family": None,
            "alignment": {
                "structure_aligned": False,
                "regime_aligned": False,
                "liquidity_aligned": False,
                "rr_valid": False,
                "data_quality_valid": False,
                "session_aligned": False,
            },
            "metadata": {
                "regime": None,
                "structure_bias": None,
                "liquidity_bias": None,
                "rr1": None,
                "rr2": None,
                "session_downgrade": False,
                "regime_alignment_note": None,
                "liquidity_alignment_note": None,
            },
            "block_reasons": ["RUNNER_EXCEPTION"],
            "allow_reasons": [],
            "downgrade_reasons": ["SOURCE_FILE_MISSING"],
            "confidence": 0.0,
            "reason_codes": ["RUNNER_EXCEPTION", "SOURCE_FILE_MISSING", f"EXC_{str(exc)[:80]}", "DECISION_BLOCK"],
            "feeds_next": ["PAPER_LIFECYCLE", "OUTCOME_TRACKER", "EDGE_MATRIX"],
        }
        write_json(OUTPUT_PATH, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("CONTRACT_DECISION_GATE READY")


if __name__ == "__main__":
    main()
