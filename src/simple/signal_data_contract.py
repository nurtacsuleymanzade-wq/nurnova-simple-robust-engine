from __future__ import annotations

import json
from typing import Any

from src.simple.research_epoch import ACTIVE_EPOCH_ID, epoch_state_path
from src.simple.research_runtime import current_runtime_context, stamp_payload, write_json

BLOCK_ID = "SIGNAL_DATA_CONTRACT"
OUTPUT_PATH = epoch_state_path("latest_signal_data_contract.json")


CANONICAL_FIELD_OWNERSHIP: dict[str, dict[str, str]] = {
    "symbol": {
        "source": "runtime context / observation",
        "owner": "RUNTIME_CONTEXT / OBSERVATION_FACTORY",
    },
    "direction": {
        "source": "SETUP_FAMILY_ACTIVATION_ENGINE direction_resolution",
        "owner": "SETUP_FAMILY_ACTIVATION_ENGINE",
    },
    "setup_family": {
        "source": "latest_setup_family_activation",
        "owner": "SETUP_FAMILY_ACTIVATION_ENGINE",
    },
    "model_id": {
        "source": "MODEL_HUNTER_ENGINE / MODEL_CLUSTER_ENGINE selected model",
        "owner": "MODEL_CLUSTER_ENGINE",
    },
    "activation_score": {
        "source": "SETUP_FAMILY_ACTIVATION_ENGINE score_breakdown",
        "owner": "SETUP_FAMILY_ACTIVATION_ENGINE",
    },
    "activation_band": {
        "source": "activation_score thresholds",
        "owner": "SETUP_FAMILY_ACTIVATION_ENGINE",
    },
    "primary_tf": {"source": "TIMEFRAME_RESOLVER", "owner": "TIMEFRAME_RESOLVER"},
    "trigger_tf": {"source": "TIMEFRAME_RESOLVER", "owner": "TIMEFRAME_RESOLVER"},
    "context_tf": {"source": "TIMEFRAME_RESOLVER", "owner": "TIMEFRAME_RESOLVER"},
    "structure_tf": {"source": "TIMEFRAME_RESOLVER", "owner": "TIMEFRAME_RESOLVER"},
    "entry": {
        "source": "PAPER_TRADE_FACTORY using current price + plan style + RR profile",
        "owner": "PAPER_TRADE_FACTORY",
    },
    "stop_loss": {
        "source": "PAPER_TRADE_FACTORY using current price + plan style + RR profile",
        "owner": "PAPER_TRADE_FACTORY",
    },
    "tp1": {
        "source": "PAPER_TRADE_FACTORY using current price + plan style + RR profile",
        "owner": "PAPER_TRADE_FACTORY",
    },
    "tp2": {
        "source": "PAPER_TRADE_FACTORY using current price + plan style + RR profile",
        "owner": "PAPER_TRADE_FACTORY",
    },
    "rr1": {"source": "PAPER_TRADE_FACTORY calculation", "owner": "PAPER_TRADE_FACTORY"},
    "rr2": {"source": "PAPER_TRADE_FACTORY calculation", "owner": "PAPER_TRADE_FACTORY"},
    "risk_distance": {"source": "PAPER_TRADE_FACTORY calculation", "owner": "PAPER_TRADE_FACTORY"},
    "result": {"source": "RESEARCH_PAPER_LIFECYCLE_ENGINE", "owner": "RESEARCH_PAPER_LIFECYCLE_ENGINE"},
    "close_reason": {"source": "RESEARCH_PAPER_LIFECYCLE_ENGINE", "owner": "RESEARCH_PAPER_LIFECYCLE_ENGINE"},
    "r_result": {"source": "RESEARCH_PAPER_LIFECYCLE_ENGINE", "owner": "RESEARCH_PAPER_LIFECYCLE_ENGINE"},
    "mfe": {"source": "RESEARCH_PAPER_LIFECYCLE_ENGINE", "owner": "RESEARCH_PAPER_LIFECYCLE_ENGINE"},
    "mae": {"source": "RESEARCH_PAPER_LIFECYCLE_ENGINE", "owner": "RESEARCH_PAPER_LIFECYCLE_ENGINE"},
    "hold_seconds": {"source": "RESEARCH_PAPER_LIFECYCLE_ENGINE", "owner": "RESEARCH_PAPER_LIFECYCLE_ENGINE"},
    "wins": {"source": "OUTCOME_ACCOUNTING_ENGINE", "owner": "OUTCOME_ACCOUNTING_ENGINE"},
    "losses": {"source": "OUTCOME_ACCOUNTING_ENGINE", "owner": "OUTCOME_ACCOUNTING_ENGINE"},
    "expired": {"source": "OUTCOME_ACCOUNTING_ENGINE", "owner": "OUTCOME_ACCOUNTING_ENGINE"},
    "winrate": {"source": "OUTCOME_ACCOUNTING_ENGINE", "owner": "OUTCOME_ACCOUNTING_ENGINE"},
    "avg_r": {"source": "OUTCOME_ACCOUNTING_ENGINE", "owner": "OUTCOME_ACCOUNTING_ENGINE"},
    "edge_status": {"source": "RESEARCH_EDGE_MATRIX_ENGINE", "owner": "RESEARCH_EDGE_MATRIX_ENGINE"},
    "best_model": {"source": "RESEARCH_EDGE_MATRIX_ENGINE", "owner": "RESEARCH_EDGE_MATRIX_ENGINE"},
    "model_sample_count": {"source": "RESEARCH_EDGE_MATRIX_ENGINE", "owner": "RESEARCH_EDGE_MATRIX_ENGINE"},
}


def build_signal_data_contract() -> dict[str, Any]:
    context = current_runtime_context()
    output = stamp_payload(
        {
            "epoch_id": ACTIVE_EPOCH_ID,
            "source": {"source_mode": "EPOCH_V2_SSOT_CONSTITUTION"},
            "canonical_field_ownership": CANONICAL_FIELD_OWNERSHIP,
            "telegram_rendering_rule": "Telegram renders only canonical values and does not independently calculate winrate, RR, TP/SL, or edge.",
            "contract_status": "ACTIVE",
            "data_quality": {"level": "HIGH", "missing_inputs": []},
            "reason_codes": ["CANONICAL_SIGNAL_FIELD_OWNERSHIP_ACTIVE", "PAPER_ONLY", "NO_LIVE_EXECUTION", "NO_PRIVATE_API"],
            "feeds_next": ["SIGNAL_GRADE_ENGINE", "TELEGRAM_RESEARCH_REPORTER"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        context.get("symbol") or "BTCUSDT",
        context,
    )
    write_json(OUTPUT_PATH, output)
    return output


def run_signal_data_contract() -> dict[str, Any]:
    return build_signal_data_contract()


def main() -> None:
    print(json.dumps(build_signal_data_contract(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
