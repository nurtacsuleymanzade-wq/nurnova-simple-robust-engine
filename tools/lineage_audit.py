from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.simple.jsonl_tail_reader import read_jsonl_tail_objects
from src.simple.research_epoch import epoch_data_path


def _rows(name: str) -> list[dict]:
    path = epoch_data_path(name)
    return read_jsonl_tail_objects(path, max_lines=200000) if path.exists() else []


def main() -> None:
    setup_rows = _rows("signal_events_clean.jsonl")
    signal_rows = _rows("signal_events_clean.jsonl")
    plan_rows = _rows("trade_plan_events.jsonl")
    decision_rows = _rows("decision_events.jsonl")
    open_rows = _rows("paper_trade_open_events.jsonl")
    close_rows = _rows("paper_trade_close_events.jsonl")
    outcome_rows = _rows("outcome_events.jsonl")
    edge_rows = _rows("edge_events.jsonl")

    setup_ids = {str(r.get("setup_id") or "") for r in setup_rows if r.get("setup_id")}
    signal_ids = {str(r.get("signal_id") or "") for r in signal_rows if r.get("signal_id")}
    plan_ids = {str(r.get("plan_id") or "") for r in plan_rows if r.get("plan_id")}
    decision_ids = {str(r.get("decision_id") or "") for r in decision_rows if r.get("decision_id")}
    open_ids = {str(r.get("paper_trade_id") or "") for r in open_rows if r.get("paper_trade_id")}
    outcome_ids = {str(r.get("outcome_id") or "") for r in outcome_rows if r.get("outcome_id")}

    broken_setup_signal = sum(1 for r in signal_rows if str(r.get("setup_id") or "") not in setup_ids)
    broken_signal_plan = sum(1 for r in plan_rows if str(r.get("signal_id") or "") not in signal_ids)
    broken_plan_decision = sum(1 for r in decision_rows if str(r.get("plan_id") or "") not in plan_ids)
    broken_decision_open = sum(1 for r in open_rows if str(r.get("decision_id") or "") not in decision_ids)
    broken_open_outcome = sum(1 for r in outcome_rows if str(r.get("paper_trade_id") or "") not in open_ids)
    broken_outcome_edge = sum(1 for r in edge_rows if str(r.get("outcome_id") or "") not in outcome_ids)
    trade_without_plan = sum(1 for r in open_rows if not r.get("plan_id"))
    outcome_no_setup = sum(1 for r in outcome_rows if not r.get("setup_id"))
    edge_not_closed = sum(1 for r in edge_rows if str(r.get("outcome_status") or "").upper() not in {"TP1_HIT", "TP2_HIT", "SL_HIT", "EXPIRED"})

    full_lineage = sum(
        1
        for r in edge_rows
        if r.get("setup_id") and r.get("signal_id") and r.get("plan_id") and r.get("decision_id") and r.get("paper_trade_id") and r.get("outcome_id")
    )

    report = {
        "setup count": len(setup_ids),
        "signal event count": len(signal_rows),
        "trade plan event count": len(plan_rows),
        "decision event count": len(decision_rows),
        "paper open event count": len(open_rows),
        "paper close event count": len(close_rows),
        "outcome event count": len(outcome_rows),
        "edge event count": len(edge_rows),
        "full lineage count": full_lineage,
        "broken at setup->signal": broken_setup_signal,
        "broken at signal->plan": broken_signal_plan,
        "broken at plan->decision": broken_plan_decision,
        "broken at decision->paper_open": broken_decision_open,
        "broken at paper_open->outcome": broken_open_outcome,
        "broken at outcome->edge": broken_outcome_edge,
        "trade_open_without_plan": trade_without_plan > 0,
        "outcome_traceable_to_setup": outcome_no_setup == 0,
        "edge_only_from_closed_outcomes": edge_not_closed == 0,
        "invariant setup>=signal>=plan>=decision>=paper_open>=outcome>=edge": len(setup_ids) >= len(signal_rows) >= len(plan_rows) >= len(decision_rows) >= len(open_rows) >= len(outcome_rows) >= len(edge_rows),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
