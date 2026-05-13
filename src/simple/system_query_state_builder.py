from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, load_json, stamp_payload, write_json

BLOCK_ID = "SYSTEM_QUERY_STATE_BUILDER"
STATE_DIR = Path("state/simple")
OUTPUT_PATH = STATE_DIR / "latest_system_query_state.json"


def _qa(question: str, answer: str) -> dict[str, str]:
    return {"question": question, "answer": answer}


def run_system_query_state_builder() -> dict[str, Any]:
    context = current_runtime_context()
    sync = load_json(STATE_DIR / "latest_context_sync.json") or {}
    observation = load_json(STATE_DIR / "latest_observation_factory.json") or {}
    setup = load_json(STATE_DIR / "latest_setup_family_activation.json") or {}
    paper_factory = load_json(STATE_DIR / "latest_paper_trade_factory.json") or {}
    lifecycle = load_json(STATE_DIR / "latest_research_paper_lifecycle.json") or {}
    edge = load_json(STATE_DIR / "latest_research_edge_matrix.json") or {}
    feedback = load_json(STATE_DIR / "latest_model_feedback.json") or {}
    promotion = load_json(STATE_DIR / "latest_model_promotion.json") or {}
    live_gate = load_json(STATE_DIR / "latest_live_eligibility_gate.json") or {}
    audit = load_json(STATE_DIR / "latest_system_audit.json") or {}

    paper_safety = paper_factory.get("paper_safety") or {}
    edge_summary = edge.get("summary") or {}
    feedback_summary = feedback.get("summary") or {}
    promotion_summary = promotion.get("promotion_summary") or {}
    audit_warnings = audit.get("warnings") or []
    audit_critical = audit.get("critical_issues") or []
    blocking_reasons = setup.get("blocking_reasons") or []
    bottleneck = (
        audit_critical[0]
        if audit_critical
        else blocking_reasons[0]
        if blocking_reasons
        else "CLEAN_SAMPLE_ACCUMULATION"
        if int(edge_summary.get("clean_sample_count") or 0) < 20
        else "NONE"
    )

    payload = stamp_payload(
        {
            "symbol": str(context.get("symbol") or "BTCUSDT"),
            "block_id": BLOCK_ID,
            "source": {"source_mode": "QUERYABLE_SYSTEM_SUMMARY"},
            "current_market_state": {
                "price": ((observation.get("market_snapshot") or {}).get("price")),
                "delta": ((observation.get("aggression") or {}).get("delta")),
                "spread": ((observation.get("market_snapshot") or {}).get("spread")),
            },
            "current_setup_activation": {
                "dominant_setup_family": setup.get("dominant_setup_family"),
                "direction": setup.get("direction"),
                "activation_band": setup.get("activation_band"),
                "activation_score": setup.get("activation_score"),
                "ready_for_paper_research": setup.get("ready_for_paper_research"),
                "blocking_reasons": blocking_reasons,
            },
            "current_paper_status": lifecycle.get("summary") or {},
            "current_edge_status": {
                "edge_status": edge.get("edge_status"),
                "clean_sample_count": edge_summary.get("clean_sample_count"),
                "best_model_id": edge_summary.get("best_model_id"),
                "best_expectancy": edge_summary.get("best_expectancy"),
            },
            "current_promotion_status": promotion_summary,
            "current_live_gate_status": {
                "live_enabled": live_gate.get("live_enabled", False),
                "eligible_diag": live_gate.get("eligible_diag", False),
                "blocked_models": len(live_gate.get("blocked_models") or []),
            },
            "current_system_health": {
                "system_status": audit.get("system_status", "UNKNOWN"),
                "score_100": audit.get("score_100"),
                "critical_issues": audit_critical,
                "warnings": audit_warnings,
            },
            "top_questions_and_answers": [
                _qa("Is the system running?", "YES" if context.get("context_id") else "NO"),
                _qa("Is active chain OK?", "YES" if sync.get("active_chain_ok") else "NO"),
                _qa("Why did paper trade open?", ",".join(setup.get("activation_reasons") or ["NO_PAPER_ACTIVATION"])[:200] if setup else "NO_ACTIVATION_STATE"),
                _qa("Why did paper trade not open?", ",".join(blocking_reasons or ["NO_BLOCK"])[:200]),
                _qa("Was any trade blocked by direction conflict?", "YES" if (paper_safety.get("blocked_by_context_direction_conflict", 0) or paper_safety.get("blocked_by_model_family_direction_conflict", 0)) else "NO"),
                _qa("Why did edge not learn yet?", "CLEAN_SAMPLE_COUNT_BELOW_20" if int(edge_summary.get("clean_sample_count") or 0) < 20 else "EDGE_CAN_LEARN"),
                _qa("Which models are best?", str(feedback_summary.get("best") or edge_summary.get("best_model_id") or "UNKNOWN")),
                _qa("Which models need more samples?", str(len(feedback.get("models_needing_more_samples") or []))),
                _qa("Is live trading enabled?", "NO"),
                _qa("What is the current bottleneck?", bottleneck),
            ],
            "query_ready": True,
            "bottleneck": bottleneck,
            "reason_codes": [
                "QUERY_READY_TRUE",
                f"BOTTLENECK_{bottleneck}",
            ],
            "data_quality": {
                "level": "HIGH" if audit and sync else "MEDIUM",
                "missing_inputs": [
                    name
                    for name, payload in {
                        "latest_context_sync": sync,
                        "latest_setup_family_activation": setup,
                        "latest_research_paper_lifecycle": lifecycle,
                        "latest_research_edge_matrix": edge,
                        "latest_system_audit": audit,
                    }.items()
                    if not payload
                ],
            },
            "feeds_next": ["S0_CONTEXT_SYNC_POST_VALIDATION"],
            "execution_safety": {
                "safe_to_open_real_trade": False,
                "private_api_used": False,
                "live_order_sent": False,
            },
        },
        BLOCK_ID,
        str(context.get("symbol") or "BTCUSDT"),
        context,
    )
    write_json(OUTPUT_PATH, payload)
    return payload


def main() -> None:
    print(json.dumps(run_system_query_state_builder(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
