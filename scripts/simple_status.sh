#!/usr/bin/env bash
# simple_status.sh — Print NurNova Simple Observer diagnostics

set -euo pipefail

SERVICE_NAME="nurnova-simple-observer"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "============================================================"
echo " NurNova Simple Robust Engine v1 — Observer Status"
echo "============================================================"
echo ""

echo "--- systemctl status ---"
systemctl status "${SERVICE_NAME}" --no-pager || true
echo ""

echo "--- Latest Production Observer State ---"
STATE_FILE="${REPO_ROOT}/state/simple/latest_production_observer.json"
if [ -f "${STATE_FILE}" ]; then
    cat "${STATE_FILE}"
else
    echo "(state file not found: ${STATE_FILE})"
fi
echo ""

echo "--- S26A Full Chain Truth Audit ---"
S26A_FILE="${REPO_ROOT}/state/simple/latest_full_chain_truth_audit.json"
S26A_REPORT="${REPO_ROOT}/reports/simple/s26a_full_chain_truth_audit_latest_report.md"
if [ -f "${S26A_FILE}" ]; then
    echo "Report path         : ${S26A_REPORT}"
    _py() { python3 -c "import json,sys; d=json.load(open('${S26A_FILE}')); print($1)" 2>/dev/null || echo '?'; }
    echo "final_answer        : $(_py "d.get('final_answer','?')")"
    echo "data_flowing        : $(_py "d.get('raw_data_audit',{}).get('data_flowing','?')")"
    echo "no_signal_reason    : $(_py "d.get('no_signal_reason','?')")"
    echo "block_stage         : $(_py "d.get('block_stage','?')")"
    echo "setup_ctx_count     : $(_py "d.get('setup_candidate_audit',{}).get('setup_context_count','?')")"
    echo "PLAN_READY_count    : $(_py "d.get('trade_plan_audit',{}).get('PLAN_READY','?')")"
    echo "ALLOW_PAPER_count   : $(_py "d.get('decision_gate_audit',{}).get('ALLOW_PAPER','?')")"
    echo "TG_SENT_count       : $(_py "d.get('telegram_signal_audit',{}).get('SENT','?')")"
    echo "lifecycle_count     : $(_py "d.get('lifecycle_audit',{}).get('lifecycle_record_count','?')")"
    echo "TP1/TP2/SL          : $(_py "str(d.get('outcome_audit',{}).get('TP1','?'))+'/'+str(d.get('outcome_audit',{}).get('TP2','?'))+'/'+str(d.get('outcome_audit',{}).get('SL','?'))")"
    echo "recommended_next_fix: $(_py "d.get('recommended_next_fix','?')")"
else
    echo "(S26A audit file not found: ${S26A_FILE})"
fi
echo ""

echo "--- S26B Live Flow Quality Audit ---"
S26B_FILE="${REPO_ROOT}/state/simple/latest_live_flow_quality_audit.json"
S26B_REPORT="${REPO_ROOT}/reports/simple/s26b_live_flow_quality_audit_latest_report.md"
if [ -f "${S26B_FILE}" ]; then
    echo "Report path              : ${S26B_REPORT}"
    _py26b() { python3 -c "import json,sys; d=json.load(open('${S26B_FILE}')); print($1)" 2>/dev/null || echo '?'; }
    echo "events_per_minute        : $(_py26b "d.get('events_per_minute','?')")"
    echo "buckets_per_minute       : $(_py26b "d.get('buckets_per_minute','?')")"
    echo "latest_event_age_seconds : $(_py26b "d.get('latest_event_age_seconds','?')")"
    echo "quality_label            : $(_py26b "d.get('quality_label','?')")"
    echo "bottleneck               : $(_py26b "d.get('bottleneck','?')")"
    echo "final_answer             : $(_py26b "d.get('final_answer','?')")"
    echo "recommended_next_fix     : $(_py26b "d.get('recommended_next_fix','?')")"
else
    echo "(S26B audit file not found: ${S26B_FILE})"
fi
echo ""

echo "--- S26 Explainability Report ---"
EXPLAIN_FILE="${REPO_ROOT}/state/simple/latest_explainability_report.json"
EXPLAIN_MD="${REPO_ROOT}/reports/simple/s26_explainability_latest_report.md"
if [ -f "${EXPLAIN_FILE}" ]; then
    echo "Report path : ${EXPLAIN_MD}"
    echo "final_answer        : $(python3 -c "import json,sys; d=json.load(open('${EXPLAIN_FILE}')); print(d.get('final_answer','?'))" 2>/dev/null || echo '?')"
    echo "no_signal_reason    : $(python3 -c "import json,sys; d=json.load(open('${EXPLAIN_FILE}')); print(d.get('no_signal_reason','?'))" 2>/dev/null || echo '?')"
    echo "block_stage         : $(python3 -c "import json,sys; d=json.load(open('${EXPLAIN_FILE}')); print(d.get('block_stage','?'))" 2>/dev/null || echo '?')"
    echo "recommended_next_fix: $(python3 -c "import json,sys; d=json.load(open('${EXPLAIN_FILE}')); print(d.get('recommended_next_fix','?'))" 2>/dev/null || echo '?')"
else
    echo "(explainability report not found: ${EXPLAIN_FILE})"
fi
echo ""

echo "--- S27 Depth / Liquidity Memory ---"
S27_FILE="${REPO_ROOT}/state/simple/latest_depth_liquidity_memory.json"
S27_REPORT="${REPO_ROOT}/reports/simple/s27_depth_liquidity_memory_latest_report.md"
if [ -f "${S27_FILE}" ]; then
    echo "Report path              : ${S27_REPORT}"
    _py27() { python3 -c "import json,sys; d=json.load(open('${S27_FILE}')); print($1)" 2>/dev/null || echo '?'; }
    echo "depth_available          : $(_py27 "d.get('depth_available','?')")"
    echo "fallback_used            : $(_py27 "d.get('fallback_used','?')")"
    echo "liquidity_memory_status  : $(_py27 "d.get('liquidity_memory_status','?')")"
    echo "bid_wall_status          : $(_py27 "d.get('bid_wall_state',{}).get('wall_status','?')")"
    echo "ask_wall_status          : $(_py27 "d.get('ask_wall_state',{}).get('wall_status','?')")"
    echo "liquidity_bias           : $(_py27 "d.get('liquidity_bias','?')")"
    _depth_avail=$(_py27 "d.get('depth_available','?')")
    if [ "${_depth_avail}" = "False" ]; then
        echo "recommended_next_fix     : Feed live_depth_events.jsonl from depth WebSocket (bids/asks snapshots)"
    fi
else
    echo "(S27 state file not found: ${S27_FILE})"
    echo "recommended_next_fix     : Run python -m src.simple.run_s27_depth_liquidity_memory"
fi
echo ""

echo "--- S28 Market Structure V2 ---"
S28_FILE="${REPO_ROOT}/state/simple/latest_market_structure_v2.json"
S28_REPORT="${REPO_ROOT}/reports/simple/s28_market_structure_v2_latest_report.md"
if [ -f "${S28_FILE}" ]; then
    echo "Report path          : ${S28_REPORT}"
    _py28() { python3 -c "import json,sys; d=json.load(open('${S28_FILE}')); print($1)" 2>/dev/null || echo '?'; }
    echo "structure_bias       : $(_py28 "d.get('structure_bias','?')")"
    echo "structure_strength   : $(_py28 "d.get('structure_strength','?')")"
    echo "1m_bias              : $(_py28 "d.get('timeframe_states',{}).get('1m',{}).get('bias','?')")"
    echo "5m_bias              : $(_py28 "d.get('timeframe_states',{}).get('5m',{}).get('bias','?')")"
    echo "15m_bias             : $(_py28 "d.get('timeframe_states',{}).get('15m',{}).get('bias','?')")"
    echo "bos_status           : $(_py28 "d.get('bos_status','?')")"
    echo "choch_status         : $(_py28 "d.get('choch_status','?')")"
    echo "sweep_status         : $(_py28 "d.get('liquidity_sweep_status','?')")"
    echo "setup_readiness_hint : $(_py28 "d.get('setup_readiness_hint','?')")"
    _missing=$(_py28 "d.get('missing_requirements',['?'])[0]")
    if [ "${_missing}" != "NONE" ]; then
        echo "recommended_next_fix : Feed candle data — missing: ${_missing}"
    else
        echo "recommended_next_fix : Structure engine operational"
    fi
else
    echo "(S28 state file not found: ${S28_FILE})"
    echo "recommended_next_fix : Run python -m src.simple.run_s28_market_structure_v2"
fi
echo ""

echo "--- S29 Setup Classifier V2 ---"
S29_FILE="${REPO_ROOT}/state/simple/latest_setup_classifier_v2.json"
S29_REPORT="${REPO_ROOT}/reports/simple/s29_setup_classifier_v2_latest_report.md"
if [ -f "${S29_FILE}" ]; then
    echo "latest S29 report path : ${S29_REPORT}"
    _py29() { python3 -c "import json,sys; d=json.load(open('${S29_FILE}')); print($1)" 2>/dev/null || echo '?'; }
    echo "setup_status           : $(_py29 "d.get('setup_status','?')")"
    echo "setup_class            : $(_py29 "d.get('setup_class','?')")"
    echo "setup_grade            : $(_py29 "d.get('setup_grade','?')")"
    echo "setup_score            : $(_py29 "d.get('setup_score','?')")"
    echo "setup_confidence       : $(_py29 "d.get('setup_confidence','?')")"
    echo "tradeability           : $(_py29 "d.get('tradeability','?')")"
    echo "top no_trade_reasons   : $(_py29 "(', '.join((d.get('no_trade_reasons') or [])[:3]))")"
    echo "closest_to_setup       : $(_py29 "d.get('closest_to_setup','?')")"
    echo "required_improvements  : $(_py29 "(', '.join((d.get('required_improvements') or [])[:3]))")"
else
    echo "(S29 state file not found: ${S29_FILE})"
    echo "recommended_next_fix   : Run python -m src.simple.run_s29_setup_classifier_v2"
fi
echo ""

echo "--- S30 Sample Accumulation + Edge Review ---"
S30_FILE="${REPO_ROOT}/state/simple/latest_sample_accumulation_edge_review.json"
S30_REPORT="${REPO_ROOT}/reports/simple/s30_sample_accumulation_edge_review_latest_report.md"
if [ -f "${S30_FILE}" ]; then
    echo "latest S30 report path : ${S30_REPORT}"
    _py30() { python3 -c "import json,sys; d=json.load(open('${S30_FILE}')); print($1)" 2>/dev/null || echo '?'; }
    echo "usable_closed_records  : $(_py30 "d.get('sample_summary',{}).get('usable_closed_records','?')")"
    echo "current_milestone      : $(_py30 "d.get('milestone_status',{}).get('current_milestone','?')")"
    echo "next_milestone_target  : $(_py30 "d.get('milestone_status',{}).get('next_milestone_target','?')")"
    echo "edge_status            : $(_py30 "d.get('edge_claim_policy',{}).get('edge_status','?')")"
    echo "edge_claim_allowed     : $(_py30 "d.get('edge_claim_policy',{}).get('edge_claim_allowed','?')")"
    echo "best observed group    : $(_py30 "((d.get('edge_candidates') or [{}])[0]).get('label','NONE')")"
    echo "worst observed group   : $(_py30 "((d.get('weak_or_negative_edges') or [{}])[0]).get('label','NONE')")"
    echo "collection_priority    : $(_py30 "(', '.join((d.get('collection_priority') or [])[:3]))")"
    echo "recommended_next_fix   : $(_py30 "d.get('recommended_next_fix','?')")"
else
    echo "(S30 state file not found: ${S30_FILE})"
    echo "recommended_next_fix   : Run python -m src.simple.run_s30_sample_accumulation_edge_review"
fi
echo ""

echo "--- Latest S25 Telegram Follow-up State ---"
FOLLOWUP_FILE="${REPO_ROOT}/state/simple/latest_telegram_followup.json"
if [ -f "${FOLLOWUP_FILE}" ]; then
    cat "${FOLLOWUP_FILE}"
else
    echo "(follow-up file not found: ${FOLLOWUP_FILE})"
fi
echo ""

echo "--- Latest Brain v2 Report Path ---"
REPORT_FILE="${REPO_ROOT}/reports/simple/simple_brain_v2_latest_report.md"
if [ -f "${REPORT_FILE}" ]; then
    echo "Report: ${REPORT_FILE}"
    head -20 "${REPORT_FILE}"
else
    echo "(report not found: ${REPORT_FILE})"
fi
echo ""

echo "--- Recent Journal Logs (last 20 lines) ---"
journalctl -u "${SERVICE_NAME}" -n 20 --no-pager || true
echo ""

echo "--- Disk Usage (state/ data/ logs/ reports/) ---"
for d in state data logs reports; do
    if [ -d "${REPO_ROOT}/${d}" ]; then
        du -sh "${REPO_ROOT}/${d}" 2>/dev/null || true
    fi
done
echo ""

echo "--- Process List (python observer) ---"
ps aux | grep "run_s24_production_observer" | grep -v grep || echo "(no observer process found)"
echo ""

echo "============================================================"
echo " End of Status"
echo "============================================================"
