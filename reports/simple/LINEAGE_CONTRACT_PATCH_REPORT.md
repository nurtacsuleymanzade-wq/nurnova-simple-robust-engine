# LINEAGE CONTRACT PATCH REPORT

## Changed files
- src/simple/lineage_event_logger.py
- src/simple/setup_candidate_engine.py
- src/simple/signal_event_consolidator.py
- src/simple/contract_driven_trade_plan_engine.py
- src/simple/contract_decision_gate.py
- src/simple/paper_trade_factory.py
- src/simple/research_paper_lifecycle_engine.py
- src/edge/true_outcome_engine.py
- src/simple/research_edge_matrix_engine.py
- tools/lineage_audit.py

## New event logs
- data/simple/epoch_v2/signal_events_clean.jsonl
- data/simple/epoch_v2/trade_plan_events.jsonl
- data/simple/epoch_v2/decision_events.jsonl
- data/simple/epoch_v2/paper_trade_open_events.jsonl
- data/simple/epoch_v2/paper_trade_close_events.jsonl
- data/simple/epoch_v2/outcome_events.jsonl
- data/simple/epoch_v2/edge_events.jsonl
- data/simple/epoch_v2/lineage_events.jsonl

## New ID chain
setup_id -> signal_id -> plan_id -> decision_id -> paper_trade_id -> lifecycle_id -> outcome_id -> edge_event_id

## Snapshot files role
- Existing snapshot/history files remain as snapshot/replay outputs and were not deleted.
- Snapshot lines are not treated as canonical trade events.

## New event files role
- Each new file stores one real event per line.
- `paper_trade_open_events.jsonl`, `paper_trade_close_events.jsonl`, and `outcome_events.jsonl` are deduplicated by `paper_trade_id` in writer flow.

## Hard blocks
- `contract_decision_gate` now sets `execution_permission` and blocks open on:
  - STRUCTURE_DIRECTION_CONFLICT
  - ENTRY_SL_TP_MISSING
  - SIGNAL_ID_MISSING
  - PLAN_ID_MISSING
  - RR_LOW_METADATA_ONLY
  - DATA_QUALITY_METADATA_ONLY
  - SETUP_ID_MISSING
  - DECISION_ID_MISSING
- `paper_trade_factory` opens only when `execution_permission == ALLOW_OPEN`.

## Metadata-only behavior
- Metadata-only or downgraded decisions now map to `BLOCK_OPEN` or `METADATA_ONLY_NO_OPEN` and do not open paper trades.

## Lineage audit result
```json
{
  "setup count": 0,
  "signal event count": 0,
  "trade plan event count": 0,
  "decision event count": 0,
  "paper open event count": 0,
  "paper close event count": 0,
  "outcome event count": 0,
  "edge event count": 0,
  "full lineage count": 0,
  "broken at setup->signal": 0,
  "broken at signal->plan": 0,
  "broken at plan->decision": 0,
  "broken at decision->paper_open": 0,
  "broken at paper_open->outcome": 0,
  "broken at outcome->edge": 0,
  "trade_open_without_plan": false,
  "outcome_traceable_to_setup": true,
  "edge_only_from_closed_outcomes": true,
  "invariant setup>=signal>=plan>=decision>=paper_open>=outcome>=edge": true
}
```

## Remaining risks
- Some legacy producers still emit records without full lineage IDs; event logs enforce chain only for patched path.
- Historical snapshot-based metrics may differ from event-based metrics until enough new event data accumulates.
