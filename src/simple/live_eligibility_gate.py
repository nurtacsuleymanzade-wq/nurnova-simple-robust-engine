from __future__ import annotations

import json
from pathlib import Path

from src.simple.research_runtime import current_runtime_context, load_json, safe_float, stamp_payload, write_json

BLOCK_ID = "LIVE_ELIGIBILITY_GATE_DIAGNOSTIC"
STATE_DIR = Path("state/simple")
OUTPUT_PATH = STATE_DIR / "latest_live_eligibility_gate.json"
PROMOTION_PATH = STATE_DIR / "latest_model_promotion.json"
SYNC_PATH = STATE_DIR / "latest_context_sync.json"


def run_live_eligibility_gate() -> dict:
    context = current_runtime_context()
    promotion = load_json(PROMOTION_PATH) or {}
    sync = load_json(SYNC_PATH) or {}
    candidates = list(promotion.get("live_eligible_diagnostic_only") or [])
    eligible = []
    blocked = []
    reasons = []

    for model in candidates:
        block_reasons = []
        if int(model.get("sample_size") or 0) < 300:
            block_reasons.append("sample_size_below_300")
        if (safe_float(model.get("expectancy")) or 0.0) <= 0.15:
            block_reasons.append("expectancy_below_threshold")
        if (safe_float(model.get("profit_factor")) or 0.0) <= 1.2:
            block_reasons.append("profit_factor_below_threshold")
        if (safe_float(model.get("max_drawdown_r")) or 999.0) > 3.0:
            block_reasons.append("max_drawdown_r_unacceptable")
        if sync.get("sync_status") == "SYNC_BROKEN":
            block_reasons.append("runtime_sync_broken")
        if block_reasons:
            blocked.append({"model": model, "reasons": block_reasons})
            reasons.extend(block_reasons)
        else:
            eligible.append(model)

    payload = stamp_payload(
        {
            "symbol": "BTCUSDT",
            "block_id": BLOCK_ID,
            "source": {"source_mode": "MODEL_PROMOTION_GATE"},
            "live_enabled": False,
            "live_order_sent": False,
            "private_api_used": False,
            "eligible_diagnostic_models": eligible,
            "blocked_models": blocked,
            "eligible_diag": bool(eligible),
            "active_chain_ok": bool(sync.get("active_chain_ok")),
            "blocking_reasons": sorted(set(reasons)),
            "execution_safety": {
                "live_order_sent": False,
                "private_api_used": False,
            },
            "reason_codes": ["DIAGNOSTIC_ONLY", f"CANDIDATES_{len(candidates)}"],
            "data_quality": {"level": "HIGH" if promotion else "LOW", "missing_inputs": [] if promotion else ["latest_model_promotion"]},
            "feeds_next": [],
        },
        BLOCK_ID,
        "BTCUSDT",
        context,
    )
    write_json(OUTPUT_PATH, payload)
    return payload


def main() -> None:
    print(json.dumps(run_live_eligibility_gate(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
