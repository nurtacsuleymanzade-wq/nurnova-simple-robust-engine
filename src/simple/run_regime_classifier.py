from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from src.simple.regime_classifier_engine import OUTPUT_PATH, run_regime_classifier_engine
from src.simple.research_runtime import write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Regime Classifier state engine")
    parser.add_argument("--fake-sample", action="store_true")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    try:
        result = run_regime_classifier_engine(symbol=args.symbol, fake_sample=args.fake_sample)
    except Exception as exc:
        result = {
            "timestamp_utc": _utc_now(),
            "block_id": "REGIME_CLASSIFIER",
            "symbol": args.symbol,
            "data_quality": "INVALID",
            "regime_status": "INVALID",
            "primary_regime": "UNKNOWN",
            "directional_bias": "NEUTRAL",
            "volatility_state": "UNKNOWN",
            "trend_strength": 0.0,
            "range_strength": 0.0,
            "compression_score": 0.0,
            "expansion_score": 0.0,
            "reversal_risk": 0.0,
            "allowed_setup_families": [],
            "blocked_setup_families": [],
            "confidence": 0.0,
            "reason_codes": ["RUNNER_EXCEPTION", "SOURCE_FILE_MISSING", f"EXC_{str(exc)[:80]}"],
            "metadata_only": True,
            "source": {"source_mode": "STATE_FILE"},
            "feeds_next": ["SETUP_CONTRACT_ENGINE", "TRADE_PLAN_ENGINE", "DECISION_GATE", "EDGE_MATRIX"],
        }
        write_json(OUTPUT_PATH, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("REGIME_CLASSIFIER READY")


if __name__ == "__main__":
    main()
