# NOVA SIMPLE ROBUST ENGINE v1

Standalone paper-only file-based MVP trading intelligence system.

## PHASE 6 — Trade Plan & Decision Gate

Produces a real-evidence-based trade plan and a decision gate verdict from PHASE 5 Setup Candidate + Entry Trigger output.

Answers:
- Is there a valid entry with structural stop and liquidity destination?
- What is the entry model (RETEST / BREAKOUT / RECLAIM / REJECTION / CONTINUATION)?
- What are the exact entry, SL, TP1, TP2, and invalidation levels?
- What is the RR to each target (computed from price levels, never from fixed templates)?
- Should a paper trade be allowed, waited on, or blocked?

Rules enforced:
- TP only from liquidity destination (nearest_liquidity_above/below, range high/low). Fixed-RR TP is forbidden.
- SL only from logical structural invalidation (structural low/high, sweep level, absorption level).
- `real_trade_allowed` is always `false`. No private API. No real orders.
- ALLOW_PAPER only when entry, SL, TP1, invalidation and RR are all valid.
- Template risk score detects degenerate / formulaic outputs and triggers BLOCK.

Run:
```
python -m src.trade_decision.run_trade_decision_engine
```

Outputs:
- `state/trade_decision/latest_trade_decision.json`
- `state/trade_decision/trade_decision_engine_state.json`
- `data/live/trade_decision_events.jsonl`
- `reports/trade_decision/trade_decision_latest_report.md`

Key fields: `decision_status`, `side`, `entry_model`, `entry_price`, `stop_loss`, `take_profit_1`, `rr_to_tp1`, `plan_quality`, `risk_grade`, `decision_confidence`.
Feeds next: PHASE_7_PAPER_LIFECYCLE_OUTCOME_TRUTH, PHASE_8_CONDITIONAL_EDGE_MATRIX, PHASE_10_NOVA_BRAIN_SNAPSHOT.
No real trade permissions emitted. Paper only.

---

## PHASE 4 — Flow Confirmation & Post-Liquidity Reaction

Context-only engine that measures real price reaction after a liquidity event (sweep/trap/absorption).

Answers:
- Was liquidity taken?
- Continuation, reversal, rejection or reclaim after sweep?
- Absorption detected?
- Buyers/sellers trapped?
- Real breakout or failed breakout?
- Does flow confirm the active scenario?

Run:
```
python -m src.flow_reaction.run_flow_reaction_engine
```

Outputs:
- `state/flow_reaction/latest_flow_reaction.json`
- `state/flow_reaction/flow_reaction_engine_state.json`
- `data/live/flow_reaction_events.jsonl`
- `reports/flow_reaction/flow_reaction_latest_report.md`

Key fields: `flow_confirmation`, `post_liquidity_reaction`, `absorption_state`, `trap_state`, `reaction_bias`, `reaction_confidence`.
Feeds next: PHASE_5, PHASE_8, PHASE_10.
No entry/SL/TP/trade permissions emitted.

## PHASE 5 — Setup Candidate & Entry Trigger

Context-only engine that classifies setup candidates and entry trigger eligibility.

Produces:
- 12 setup candidate types (continuation, reversal, range, compression, trap, reclaim, rejection)
- Setup direction (LONG/SHORT/NEUTRAL/NO_TRADE)
- Setup quality (A/B/C)
- Setup confidence (0.0–1.0)
- 6 entry trigger statuses (READY/NEAR/WAIT/INVALID/CONFLICTED/UNKNOWN)
- Entry trigger quality (HIGH/MEDIUM/LOW)
- Entry trigger confidence (0.0–1.0)

Run:
```
python -m src.setup_entry.run_setup_entry_engine
```

Outputs:
- `state/setup_entry/latest_setup_entry.json`
- `state/setup_entry/setup_entry_engine_state.json`
- `data/live/setup_entry_events.jsonl`
- `reports/setup_entry/setup_entry_latest_report.md`

Uses inputs: Market State + Active Scenario + Flow Reaction + Liquidity/Structure/Candle context.
Feeds next: PHASE_6 (Trade Plan), PHASE_8, PHASE_10.
No entry prices, SL/TP, trade plan, or trade permissions emitted.

## S29 - Setup Classifier V2

Read-only setup classifier that combines S13/S14/S15/S16/S22/S26B/S27/S28
context into `L1-L5` / `S1-S5` setup classes, grades, blockers, and readiness.
It does not create entry prices, orders, lifecycle, or Telegram signals.

Run:
```
python -m src.simple.run_s29_setup_classifier_v2
```

Outputs:
- `state/simple/latest_setup_classifier_v2.json`
- `state/simple/s29_setup_classifier_v2_state.json`
- `data/simple/setup_classifier_v2_history.jsonl`
- `reports/simple/s29_setup_classifier_v2_latest_report.md`

`safe_to_open_real_trade=false` always. Runs inside S24 after S28.

## S30 - Sample Accumulation + Edge Review

Read-only research layer that accumulates real paper outcomes and reviews edge
across setup classes, families, grades, sides, decisions, and market-condition
tags. It never fabricates samples and never places trades.

Run:
```
python -m src.simple.run_s30_sample_accumulation_edge_review
```

Outputs:
- `state/simple/latest_sample_accumulation_edge_review.json`
- `state/simple/s30_sample_accumulation_edge_review_state.json`
- `data/simple/sample_accumulation_edge_review_history.jsonl`
- `reports/simple/s30_sample_accumulation_edge_review_latest_report.md`

`safe_to_open_real_trade=false` always. Runs inside S24 after S22 and S29.

## S28 — Market Structure V2

Read-only multi-timeframe market structure engine. Produces objective 1m/5m/15m structure context:
HH/HL/LH/LL sequences, BOS, CHoCH, range high/low, equal highs/lows, liquidity sweep and reclaim.
Aligns with S13 flow evidence and S27 liquidity memory. Feeds setup classifier v2.

Run:
```
python -m src.simple.run_s28_market_structure_v2
```

Outputs:
- state/simple/latest_market_structure_v2.json
- state/simple/s28_market_structure_v2_state.json
- data/simple/market_structure_v2_history.jsonl
- reports/simple/s28_market_structure_v2_latest_report.md

safe_to_open_real_trade is always false.

## S26 — Explainability / Failure Chain Report

Read-only diagnostic engine. Answers why Telegram signals did not happen and where the pipeline blocked.

Run:
```
python -m src.simple.run_s26_explainability
```

Outputs:
- state/simple/latest_explainability_report.json
- state/simple/s26_explainability_state.json
- data/simple/explainability_history.jsonl
- reports/simple/s26_explainability_latest_report.md

Answers: Why no signal? Which stage blocked? What to fix next? Is Telegram configured? Is it safe?
safe_to_open_real_trade is always false.

This repository is separate from:
- NurNova Final advanced core
- Market Maker Perspective
- Smart Money Perspective

Use Claude Code with CLAUDE.md and .claude/commands.

## S6 — Scenario + Setup Candidate

Builds a scenario label and setup candidate from S1–S5 context. Produces setup
candidate only — no entry, stop, TP, RR, decision, paper trade, or edge fields.

Run fake sample:

```
python -m src.simple.run_s6_setup_candidate --fake-sample --symbol BTCUSDT
```

Outputs:
- `state/simple/latest_setup_candidate.json`
- `state/simple/s6_setup_candidate_state.json`
- `data/simple/setup_candidate.jsonl`
- `reports/simple/s6_setup_candidate_latest_report.md`

Feeds next: `S7_TRADE_PLAN_DECISION_GATE`.

## S7 — Trade Plan + Decision Gate

Converts a valid S6 setup candidate into a paper-only trade plan and decision gate
result. Never opens real trades. `safe_to_open_real_trade` is always false.

Run fake sample:

```
python -m src.simple.run_s7_trade_plan_decision --fake-sample --symbol BTCUSDT
```

Outputs:
- `state/simple/latest_decision.json`
- `state/simple/s7_trade_plan_decision_state.json`
- `data/simple/trade_plan_decision.jsonl`
- `reports/simple/s7_trade_plan_decision_latest_report.md`

Feeds next: `S8_PAPER_OUTCOME_TRACKER`.

## S8 — Paper Outcome Tracker

Evaluates a S7 paper trade plan against the official Binance 1M candle high/low to
determine outcome. Never calculates winrate, expectancy, or edge stats.
`check_method` is always `OFFICIAL_CANDLE_HIGH_LOW`. `safe_to_open_real_trade` is
always false. If both TP and stop are touched in the same candle → `AMBIGUOUS`,
`edge_eligible=false`.

Run fake sample:

```
python -m src.simple.run_s8_paper_outcome --fake-sample --symbol BTCUSDT
```

Outputs:
- `state/simple/latest_paper_outcome.json`
- `state/simple/s8_paper_outcome_state.json`
- `data/simple/paper_outcome.jsonl`
- `reports/simple/s8_paper_outcome_latest_report.md`

Feeds next: `S9_EDGE_STATS`.

## S11.2 — Sample Schema Validator

Validates `data/simple/replay_samples.jsonl` structure integrity. Checks required
fields, enum values, null critical fields, RR numeric validity, `edge_eligible` type,
timestamp format, and malformed JSONL rows. Guards future VPS/live research data
from silently corrupting the edge dataset.

Run validator:

```
python -m src.simple.run_sample_schema_validator
```

Outputs:
- `state/simple/latest_schema_validation.json`
- `reports/simple/schema_validation_latest_report.md`

Feeds next: `S11_REPLAY_SAMPLE_RUNNER`.

## S11.3 — Research Dataset Exporter

Exports `data/simple/replay_samples.jsonl` into structured research datasets for
quant research, analytics, and VPS accumulation workflows. Derives flat research
rows with scenario, setup, quality, decision, outcome, and brain fields. Research
only. No live trading, no private API.

Run exporter:

```
python -m src.simple.run_research_dataset_exporter --symbol BTCUSDT
```

Outputs:
- `exports/simple/research_dataset.csv`
- `exports/simple/research_dataset_summary.json`

Export fields: `timestamp_utc`, `scenario_type`, `setup_type`, `setup_status`,
`quality_label`, `decision`, `paper_outcome`, `realized_rr`, `edge_eligible`,
`brain_status`, `brain_mode`.

Feeds next: `QUANT_RESEARCH_PIPELINE`.

## S11.4 — Pre-VPS Readiness Report

Audits local state to determine readiness for long-running VPS observation mode.
Evaluates S1–S11 state file existence, replay sample availability, schema validation
status, edge stats, simple brain status, local pipeline runner status, deterministic
fake sample support, test suite coverage, and live-trading safety invariants.
Research only. `safe_to_open_real_trade` is always false.

Run audit:

```
python -m src.simple.run_pre_vps_readiness_report
```

Outputs:
- `state/simple/latest_pre_vps_readiness.json`
- `reports/simple/pre_vps_readiness_latest_report.md`

Final fields: `vps_ready`, `readiness_score`, `critical_missing_items`, `warnings`,
`recommended_next_step`, `safe_to_open_real_trade=false`.

---

## S14 — Flow Persistence Engine

Detects whether 1S flow evidence is sustained, fading, flipping, or noisy across time windows.

```bash
python -m src.simple.run_s14_flow_persistence
```

Inputs:
- `data/simple/flow_evidence.jsonl`
- `state/simple/latest_flow_evidence.json`

Outputs:
- `state/simple/latest_flow_persistence.json`
- `state/simple/s14_flow_persistence_state.json`
- `data/simple/flow_persistence.jsonl`
- `reports/simple/s14_flow_persistence_latest_report.md`

Windows: `last_5s`, `last_15s`, `last_30s` — each with `sample_count`, `avg_evidence_score`,
`positive_count`, `negative_count`, `neutral_count`, `dominant_label`, `direction_consistency`, `confidence_avg`.

persistence_label: `SUSTAINED_LONG_PRESSURE`, `SUSTAINED_SHORT_PRESSURE`, `FADING_LONG_PRESSURE`,
`FADING_SHORT_PRESSURE`, `CHOPPY_FLOW`, `INSUFFICIENT_HISTORY`, `NO_VALID_FLOW`.

direction_label: `LONG`, `SHORT`, `NEUTRAL`, `UNKNOWN`.
continuation_quality: `STRONG`, `MODERATE`, `WEAK`, `NONE`.

`safe_to_open_real_trade=false` always. No entry, no SL, no TP, no live orders.
Feeds next: `S15_FLOW_TO_SETUP_CONTEXT`.

## S15 — Flow-to-Setup Context Engine

Combines S13 flow evidence and S14 flow persistence into a single structured setup context.
Determines whether flow conditions are strong enough to be considered tradeable context.
No entry, no TP/SL, no RR, no real orders. Context classification only.

```bash
python -m src.simple.run_s15_flow_to_setup_context
```

Inputs:
- `state/simple/latest_flow_state.json`
- `state/simple/latest_flow_evidence.json`
- `state/simple/latest_flow_persistence.json`

Outputs:
- `state/simple/latest_setup_context.json`
- `state/simple/s15_setup_context_state.json`
- `data/simple/setup_context_history.jsonl`
- `reports/simple/s15_setup_context_latest_report.md`

setup_context_label: `STRONG_LONG_CONTEXT`, `WEAK_LONG_CONTEXT`, `STRONG_SHORT_CONTEXT`,
`WEAK_SHORT_CONTEXT`, `NEUTRAL_CONTEXT`, `CHOPPY_CONTEXT`, `NO_TRADE_CONTEXT`, `INSUFFICIENT_CONTEXT`.

direction_bias: `LONG`, `SHORT`, `NEUTRAL`, `UNKNOWN`.

setup_context_score: -10 to +10. Positive = long context, negative = short context.

tradeable=true only when: quality OK, confidence >= 0.60, persistence not choppy,
direction_bias LONG or SHORT, label STRONG_LONG_CONTEXT or STRONG_SHORT_CONTEXT.

`safe_to_open_real_trade=false` always. No entry, no SL, no TP, no live orders.
Feeds next: `S16_SCENARIO_ENTRY_TRIGGER`.

## S16 — Scenario + Entry Trigger Engine

Transforms tradeable setup context into a scenario candidate and entry-readiness state.
Does NOT generate entry price, TP, SL, RR, orders, or Telegram. Decides only:
"Is the market ready enough for entry consideration?"

```bash
python -m src.simple.run_s16_scenario_entry_trigger
```

Inputs:
- `state/simple/latest_setup_context.json`
- `state/simple/latest_flow_state.json`
- `state/simple/latest_flow_evidence.json`
- `state/simple/latest_flow_persistence.json`

Outputs:
- `state/simple/latest_scenario_trigger.json`
- `state/simple/s16_scenario_trigger_state.json`
- `data/simple/scenario_trigger_history.jsonl`
- `reports/simple/s16_latest_report.md`

scenario_label: `LONG_CONTINUATION`, `SHORT_CONTINUATION`, `LONG_REVERSAL`, `SHORT_REVERSAL`,
`BREAKOUT_ATTEMPT`, `FAILED_BREAKOUT`, `CHOPPY_RANGE`, `NO_SCENARIO`, `INSUFFICIENT_DATA`.

trigger_state: `READY_FOR_ENTRY`, `WAIT_FOR_CONFIRMATION`, `WEAK_TRIGGER`,
`CONFLICTED_TRIGGER`, `NO_TRIGGER`.

market_regime: `TRENDING`, `REVERSAL`, `RANGING`, `CHOPPY`, `UNKNOWN`.

ready_for_entry=true only when: tradeable=true, confidence >= 0.70, trigger_strength >= 0.70,
quality OK, persistence not choppy, direction_bias LONG or SHORT.

`safe_to_open_real_trade=false` always. No entry, no SL, no TP, no orders, no Telegram.
Feeds next: `S17_TRADE_PLAN_ENGINE`.

## S17 — Trade Plan Engine (paper-only)

Transforms S16 `READY_FOR_ENTRY` scenario triggers into a structured **paper-only**
trade plan candidate. No order execution, no private API, no Telegram.

Inputs:
- `state/simple/latest_scenario_trigger.json`
- `state/simple/latest_setup_context.json`
- `state/simple/latest_flow_state.json`
- `state/simple/latest_flow_evidence.json`
- `state/simple/latest_flow_persistence.json`

Outputs:
- `state/simple/latest_trade_plan.json`
- `state/simple/s17_trade_plan_state.json`
- `data/simple/trade_plan_history.jsonl`
- `reports/simple/s17_trade_plan_latest_report.md`

`plan_status`: `PLAN_READY`, `WATCH_ONLY`, `NO_PLAN`, `INVALID`.
`plan_grade`: `A_PLUS`, `A`, `B`, `C`, `WATCH`, `NO_PLAN`.
`side`: `LONG`, `SHORT`, `NEUTRAL`, `UNKNOWN`.

Price logic:
- LONG → `stop_loss < entry_price < tp1 <= tp2`.
- SHORT → `stop_loss > entry_price > tp1 >= tp2`.
- `invalidation_price` is aligned with `stop_loss`.
- `rr_tp1` and `rr_tp2` are derived from actual prices, not templates.
- `rr_tp1 < 1.0` or `rr_tp2 < 1.5` downgrades plan to `WATCH_ONLY`.
- Zero/malformed stop distance or contradictory direction → `INVALID`.

`safe_to_open_real_trade=false` always. No real orders, no Telegram, no private API.
Feeds next: `S18_DECISION_GATE`.

## S18 — Decision Gate (paper-only)

Evaluates S17 trade plan and produces a paper-only decision: `ALLOW_PAPER`, `WATCH`, or `BLOCK`.
No order execution, no private API, no Telegram.

Inputs:
- `state/simple/latest_trade_plan.json`
- `state/simple/latest_scenario_trigger.json`
- `state/simple/latest_setup_context.json`
- `state/simple/latest_flow_state.json`
- `state/simple/latest_flow_evidence.json`
- `state/simple/latest_flow_persistence.json`

Outputs:
- `state/simple/latest_decision_gate.json`
- `state/simple/s18_decision_gate_state.json`
- `data/simple/decision_gate_history.jsonl`
- `reports/simple/s18_decision_gate_latest_report.md`

`decision`: `ALLOW_PAPER`, `WATCH`, `BLOCK`.
`decision_status`: `PASSED`, `WATCH_ONLY`, `BLOCKED`, `INVALID`.

Gate checks (all reported): `input_available`, `plan_ready`, `side_valid`,
`price_logic_valid`, `rr_valid`, `rr_threshold_valid`, `data_quality_valid`,
`trigger_ready`, `safety_valid`, `reasons_present`.

`ALLOW_PAPER` only if all gates pass: S17 `PLAN_READY`, directional side, valid
price logic, `rr_tp1 >= 1.0`, `rr_tp2 >= 1.5`, DQ OK/HIGH, S16 ready_for_entry,
safe flags, non-empty plan reasons. `BLOCK` on contradictions, unsafe flags,
missing inputs, or invalid plan. `WATCH` for soft failures.

`safe_to_open_real_trade=false` always. No Telegram, no private API, no real orders.
Feeds next: `S19_TELEGRAM_PAPER_ALERT`.

## S19 — Telegram Paper Alert

Paper-only alert formatter. Reads S18 Decision Gate output. Prepares a
Telegram-formatted message for `ALLOW_PAPER`, skips on `WATCH`, blocks on
`BLOCK`. Default mode is `DRY_RUN` — no network call is made. `SEND` mode
requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from environment; if
missing the engine returns `INVALID` without crashing.

Inputs:
- `state/simple/latest_decision_gate.json`
- `state/simple/latest_trade_plan.json`
- `state/simple/latest_scenario_trigger.json`
- `state/simple/latest_setup_context.json`

Outputs:
- `state/simple/latest_telegram_paper_alert.json`
- `state/simple/s19_telegram_paper_alert_state.json`
- `data/simple/telegram_paper_alert_history.jsonl`
- `reports/simple/s19_telegram_paper_alert_latest_report.md`

`alert_status`: `SENT`, `DRY_RUN_READY`, `SKIPPED`, `BLOCKED`, `INVALID`.
`telegram_mode`: `DRY_RUN`, `SEND`.

Message includes: `PAPER ONLY / REAL TRADE DISABLED`, symbol, side, entry,
SL, TP1, TP2, RR, grade, decision, reason summary, and
`safe_to_open_real_trade=false`.

This block does NOT open real trades, does NOT call Binance private API, and
does NOT execute orders. `safe_to_open_real_trade=false`,
`private_api_used=false`, `live_order_sent=false` always.
Feeds next: `S20_PAPER_LIFECYCLE_TRACKER`.

## S20 — Paper Lifecycle Tracker

Paper-only lifecycle state tracker. Reads S18 Decision Gate, S17 Trade Plan,
S19 Telegram Paper Alert, and S12 Latest Flow State. Creates a lifecycle only
when S18 `decision=ALLOW_PAPER` and S19 `alert_status` is `SENT` or
`DRY_RUN_READY`. Otherwise emits `NO_LIFECYCLE`.

Tracks: entry touch, TP1/TP2/SL hits, invalidation, unrealized/realized R,
MFE/MAE (R units), and append-only lifecycle events. `lifecycle_id` is
deterministic from timestamp + symbol + side + entry. Missing market price
degrades safely to `NOT_STARTED`/`DEGRADED` rather than crashing.

LONG hit logic: `entry_touched` when `current_price >= entry`; tp when
`current_price >= tp`; stop when `current_price <= stop_loss`.
SHORT hit logic: mirror — `<=` for entry/tp, `>=` for stop.

Inputs:
- `state/simple/latest_decision_gate.json`
- `state/simple/latest_trade_plan.json`
- `state/simple/latest_telegram_paper_alert.json`
- `state/simple/latest_flow_state.json`

Outputs:
- `state/simple/latest_paper_lifecycle.json`
- `state/simple/s20_paper_lifecycle_state.json`
- `data/simple/paper_lifecycle_history.jsonl` (append-only)
- `reports/simple/s20_paper_lifecycle_latest_report.md`

`lifecycle_status`: `NOT_STARTED`, `OPEN`, `ACTIVE`, `TP1_HIT`, `TP2_HIT`,
`SL_HIT`, `INVALIDATED`, `CLOSED`, `NO_LIFECYCLE`.

This block does NOT open real trades, does NOT use Binance private API, and
does NOT execute orders. `safe_to_open_real_trade=false`,
`private_api_used=false`, `live_order_sent=false` always.
Feeds next: `S21_OUTCOME_MONITOR`.

## S21 — Outcome Monitor (Paper Only)

Converts S20 paper lifecycle state into a clean paper outcome record for
future Edge Matrix learning. This block does NOT open real trades, does NOT
use Binance private API, does NOT send Telegram alerts, and does NOT execute
orders.

`outcome_status` values: `OPEN`, `CLOSED`, `NO_OUTCOME`, `INVALID`.
`outcome_result` values: `TP1`, `TP2`, `SL`, `INVALIDATED`, `STILL_OPEN`,
`NO_LIFECYCLE`, `UNKNOWN`. No `TIMEOUT` class.

Mapping from `lifecycle_status`:
- `TP2_HIT` or `CLOSED+tp2` → `outcome_result=TP2`, `outcome_status=CLOSED`
- `TP1_HIT` → `outcome_result=TP1`, `outcome_status=OPEN` (TP2 still active);
  `CLOSED+tp1` only → `outcome_status=CLOSED`
- `SL_HIT` → `outcome_result=SL`, `outcome_status=CLOSED`
- `INVALIDATED` → `outcome_result=INVALIDATED`, `outcome_status=CLOSED`
- `OPEN`/`ACTIVE`/`NOT_STARTED` → `outcome_result=STILL_OPEN`, `outcome_status=OPEN`
- `NO_LIFECYCLE` / missing → `outcome_result=NO_LIFECYCLE`, `outcome_status=NO_OUTCOME`

Snapshots of `setup_context`, `scenario_trigger`, `decision_gate`, and
`trade_plan` are preserved for edge learning. `realized_r`/`mfe_r`/`mae_r`
are copied from lifecycle or safely computed.

Inputs:
- `state/simple/latest_paper_lifecycle.json`
- `state/simple/latest_trade_plan.json`
- `state/simple/latest_decision_gate.json`
- `state/simple/latest_setup_context.json`
- `state/simple/latest_scenario_trigger.json`

Outputs:
- `state/simple/latest_outcome_monitor.json`
- `state/simple/s21_outcome_monitor_state.json`
- `data/simple/outcome_monitor_history.jsonl` (append-only)
- `reports/simple/s21_outcome_monitor_latest_report.md`

`safe_to_open_real_trade=false`, `private_api_used=false`,
`live_order_sent=false` always. Feeds next: `S22_EDGE_MATRIX_V2`.

## S22 — Edge Matrix v2

Paper-only learning block. Reads closed paper outcome records from
`data/simple/outcome_monitor_history.jsonl` and `state/simple/latest_outcome_monitor.json`
and produces grouped statistics (by side, grade, setup context, scenario, decision)
plus an `edge_quality` summary (status, score, confidence, caution_reason).

Rules:
- Only CLOSED records count toward `win_rate` and `expectancy_r`.
- `STILL_OPEN` and `NO_LIFECYCLE` are excluded from win/loss counts.
- TP1 and TP2 are wins; SL is a loss; INVALIDATED is neither.
- Minimum sample of 30 usable closed records to leave `NO_EDGE_CLAIM`/`RESEARCH_ONLY`.
- `VALIDATED_EDGE` requires >= 100 usable closed records with positive expectancy.
- Missing grouping fields default to `UNKNOWN` (no crash).

Inputs:
- `data/simple/outcome_monitor_history.jsonl`
- `state/simple/latest_outcome_monitor.json`
- optional: `state/simple/latest_setup_context.json`,
  `state/simple/latest_scenario_trigger.json`,
  `state/simple/latest_decision_gate.json`,
  `state/simple/latest_trade_plan.json`

Outputs:
- `state/simple/latest_edge_matrix_v2.json`
- `state/simple/s22_edge_matrix_v2_state.json`
- `data/simple/edge_matrix_v2_history.jsonl` (append-only)
- `reports/simple/s22_edge_matrix_v2_latest_report.md`

`safe_to_open_real_trade=false`, `private_api_used=false`,
`live_order_sent=false` always. No Binance private API, no order execution,
no Telegram. Feeds next: `S23_SIMPLE_BRAIN_V2`.

## S23 — Simple Brain v2

Read-only market intelligence report layer that aggregates the full S12-S22
chain into a single brain report. **No** order execution, **no** private API,
**no** Telegram sending, **no** new trade plan, **no** Decision Gate override,
**no** edge claim derivation.

Inputs (state/simple): `latest_flow_state.json`, `latest_flow_evidence.json`,
`latest_flow_persistence.json`, `latest_setup_context.json`,
`latest_scenario_trigger.json`, `latest_trade_plan.json`,
`latest_decision_gate.json`, `latest_telegram_paper_alert.json`,
`latest_paper_lifecycle.json`, `latest_outcome_monitor.json`,
`latest_edge_matrix_v2.json`.

Outputs:
- `state/simple/latest_simple_brain_v2.json`
- `state/simple/s23_simple_brain_v2_state.json`
- `data/simple/simple_brain_v2_history.jsonl`
- `reports/simple/simple_brain_v2_latest_report.md`

`brain_status` ∈ {READY, RESEARCH_READY, DEGRADED, BLOCKED, INSUFFICIENT_DATA}.
`brain_mode` ∈ {OBSERVER_MODE, RESEARCH_MODE, PAPER_ALERT_MODE,
SAMPLE_ACCUMULATION_MODE, NO_TRADE_MODE}.

If S22 edge_status is NO_EDGE_CLAIM/RESEARCH_ONLY, brain_mode does not imply
live readiness. If S18 decision is BLOCK, `primary_next_action` explains why
no paper alert should be trusted. `safe_to_open_real_trade=false`,
`private_api_used=false`, `live_order_sent=false` always.
Feeds next: `S24_VPS_SYSTEMD_24_7_PRODUCTION_OBSERVER`.

### S25 Telegram Follow-up Notifier

S25 sends real Telegram follow-up notifications for paper lifecycle events only:
`ENTRY_TOUCHED`, `TP1_HIT`, `TP2_HIT`, `SL_HIT`, `INVALIDATED`, `CLOSED`.
It reads `latest_paper_lifecycle.json`, `latest_outcome_monitor.json`,
`latest_trade_plan.json`, and `latest_decision_gate.json`, writes
`latest_telegram_followup.json`, `s25_telegram_followup_state.json`,
`telegram_followup_history.jsonl`, and
`s25_telegram_followup_latest_report.md`, and deduplicates by
`lifecycle_id + event_type + status + timestamp/event_index` so the same
TP/SL/ENTRY event is not resent on every observer cycle. If
`TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is missing, it safely returns
`BLOCKED_MISSING_ENV`. Safety remains paper-only:
`safe_to_open_real_trade=false`, `private_api_used=false`,
`live_order_sent=false`.

### S26A Full Chain Truth Audit

S26A is a read-only diagnostic engine that traces the entire live system chain
from raw sub-second flow events through setup, decision, Telegram, lifecycle,
outcome, and edge. It answers 21 diagnostic questions brutally honestly and
identifies the earliest stage where the pipeline stops producing output.

Outputs: `state/simple/latest_full_chain_truth_audit.json`,
`state/simple/s26a_full_chain_truth_audit_state.json`,
`data/simple/full_chain_truth_audit_history.jsonl`,
`reports/simple/s26a_full_chain_truth_audit_latest_report.md`.

Key fields: `raw_data_audit` (event count, freshness, data_flowing),
`setup_candidate_audit` (tradeable_count), `trade_plan_audit` (PLAN_READY),
`decision_gate_audit` (ALLOW_PAPER), `telegram_signal_audit` (SENT),
`lifecycle_audit`, `outcome_audit` (TP1/TP2/SL), `bottleneck_summary`,
`no_signal_reason`, `recommended_next_fix`, `final_answer`.
Reports `NOT_IMPLEMENTED_OR_NOT_PRODUCED` for MTF, market structure, and
liquidity until those features are built. Never mutates pipeline state.
`safe_to_open_real_trade=false` always. Runs as S26A inside S24 observer cycle.

### S26B Live Flow Quality Audit

S26B is a read-only live flow quality engine that measures whether live data
is genuinely flowing and quantifies its quality. Tracks events_per_minute,
bucket_count, bucket_freshness, latest_event_age_seconds, missing_bucket_estimate,
empty_bucket_ratio, stale_data detection, JSONL growth, and observer loop health.

Quality labels: HIGH, OK, DEGRADED, STALE, NO_DATA.

Outputs: `state/simple/latest_live_flow_quality_audit.json`,
`state/simple/s26b_live_flow_quality_audit_state.json`,
`data/simple/live_flow_quality_audit_history.jsonl`,
`reports/simple/s26b_live_flow_quality_audit_latest_report.md`.

`safe_to_open_real_trade=false` always. Runs as S26B inside S24 observer cycle after S26A.


### S27 Depth / Liquidity Memory

S27 is a read-only liquidity memory layer that tracks order book wall lifecycle.
Detects bid/ask walls and assigns lifecycle status: APPEARED, STRENGTHENED, WEAKENED,
PULLED, ABSORBED, BROKEN. No fake signals. No real trades. No private API.

Preferred inputs: `data/simple/live_depth_events.jsonl`, `state/simple/latest_depth_state.json`.
Fallback: `data/simple/live_flow_events.jsonl`, `state/simple/latest_flow_state.json`.
Fallback produces weak hints only — never real wall claims.

Outputs: `state/simple/latest_depth_liquidity_memory.json`,
`state/simple/s27_depth_liquidity_memory_state.json`,
`data/simple/depth_liquidity_memory_history.jsonl`,
`reports/simple/s27_depth_liquidity_memory_latest_report.md`.

Key fields: `depth_available`, `fallback_used`, `liquidity_memory_status`,
`bid_wall_state`, `ask_wall_state`, `wall_events`, `liquidity_bias`, `confidence`.

`safe_to_open_real_trade=false` always. Runs as S27 inside S24 observer cycle after S26B.

## PHASE 1 — Causal Lineage Spine

Phase 1 adds an additive lineage audit layer without changing existing trading logic.

Run:
```bash
python -m src.lineage.run_lineage_audit
```

Core modules:
- `src/lineage/lineage_registry.py`
- `src/lineage/lineage_builder.py`
- `src/lineage/lineage_validator.py`
- `src/lineage/lineage_graph_engine.py`
- `src/lineage/run_lineage_audit.py`

Outputs:
- `state/lineage/latest_lineage_audit.json`
- `state/lineage/lineage_graph_state.json`
- `data/live/lineage_audit_events.jsonl`
- `reports/lineage/lineage_audit_latest_report.md`

## PHASE 2 — Market State Engine

Phase 2 adds a context-only market state layer with deterministic `market_state_id`
and lineage linkage. It does not create entry/SL/TP/trade decisions.

Run:
```bash
python -m src.market_state.run_market_state_engine
```

Outputs:
- `state/market_state/latest_market_state.json`
- `state/market_state/market_state_engine_state.json`
- `data/live/market_state_events.jsonl`
- `reports/market_state/market_state_latest_report.md`

## PHASE 3 — Active Scenario Engine

Phase 3 adds a context-only active scenario selector on top of market-state and
liquidity/structure/flow/reaction evidence. It does not create entry, SL/TP, or
execution decisions.

Run:
```bash
python -m src.active_scenario.run_active_scenario_engine
```

Outputs:
- `state/active_scenario/latest_active_scenario.json`
- `state/active_scenario/active_scenario_engine_state.json`
- `data/live/active_scenario_events.jsonl`
- `reports/active_scenario/active_scenario_latest_report.md`
