"""Run S26A Full Chain Truth Audit."""

from __future__ import annotations

from src.simple.full_chain_truth_audit import run_full_chain_truth_audit


def main() -> None:
    result = run_full_chain_truth_audit()
    print(f"block_id              : {result['block_id']}")
    print(f"system_running_status : {result['system_running_status']}")
    print(f"data_flowing          : {result['raw_data_audit']['data_flowing']}")
    print(f"live_flow_events      : {result['raw_data_audit']['live_flow_event_count']}")
    print(f"1s_evidence_produced  : {result['one_second_bucket_audit']['one_second_evidence_produced']}")
    print(f"candle_1m_available   : {result['candle_dna_audit']['candle_1m_available']}")
    print(f"setup_context_count   : {result['setup_candidate_audit']['setup_context_count']}")
    print(f"tradeable_count       : {result['setup_candidate_audit']['tradeable_count']}")
    print(f"plan_ready_count      : {result['trade_plan_audit']['PLAN_READY']}")
    print(f"allow_paper_count     : {result['decision_gate_audit']['ALLOW_PAPER']}")
    print(f"telegram_sent_count   : {result['telegram_signal_audit']['SENT']}")
    print(f"lifecycle_count       : {result['lifecycle_audit']['lifecycle_record_count']}")
    print(f"TP1/TP2/SL            : {result['outcome_audit']['TP1']}/{result['outcome_audit']['TP2']}/{result['outcome_audit']['SL']}")
    print(f"bottleneck_summary    : {result['bottleneck_summary']}")
    print(f"no_signal_reason      : {result['no_signal_reason']}")
    print(f"recommended_next_fix  : {result['recommended_next_fix']}")
    print(f"final_answer          : {result['final_answer']}")
    print(f"safe_to_open_real_trade: {result['execution_safety']['safe_to_open_real_trade']}")


if __name__ == "__main__":
    main()
