from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from src.simple.contract_edge_matrix_engine import OUTPUT_PATH, run_contract_edge_matrix_engine
from src.simple.research_runtime import write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Contract Edge Matrix Engine")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    try:
        result = run_contract_edge_matrix_engine(symbol=args.symbol, fake_sample=args.fake_sample)
    except Exception as exc:
        result = {
            "timestamp_utc": _utc_now(),
            "block_id": "CONTRACT_EDGE_MATRIX",
            "symbol": args.symbol,
            "source": {"source_mode": "EPOCH_HISTORY_ANALYSIS"},
            "data_quality": "DEGRADED",
            "sample_mode": "FAST_SAMPLE_MODE",
            "sample_summary": {
                "closed_count": 0,
                "wins": 0,
                "losses": 0,
                "winrate": 0.0,
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "legacy_sample_count": 0,
                "contract_sample_count": 0,
            },
            "by_contract": [],
            "by_regime": [],
            "by_contract_regime": [],
            "early_signals": [],
            "tradeable_candidates": [],
            "blocked_candidates": [],
            "estimated_paper_trades_per_day": 0.0,
            "next_action": "KEEP_SAMPLING",
            "lineage_preview": {
                "contract_id": None,
                "setup_family": None,
                "direction": None,
                "primary_regime": None,
                "structure_bias": None,
                "liquidity_bias": None,
                "rr1": None,
                "rr2": None,
            },
            "reason_codes": ["NO_CLOSED_SAMPLES", "RUNNER_EXCEPTION", "SOURCE_FILE_MISSING", f"EXC_{str(exc)[:80]}"],
            "feeds_next": ["NOVA_BRAIN_REPORT", "DECISION_GATE"],
        }
        write_json(OUTPUT_PATH, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("CONTRACT_EDGE_MATRIX READY")


if __name__ == "__main__":
    main()
