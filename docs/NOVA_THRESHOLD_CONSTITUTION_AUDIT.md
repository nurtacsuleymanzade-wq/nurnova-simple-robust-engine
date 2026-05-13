# NOVA THRESHOLD CONSTITUTION AUDIT

Scope: `src/simple/**/*.py`, with emphasis on `flow_evidence_engine.py`, `flow_persistence_engine.py`, `flow_to_setup_context_engine.py`, `scenario_entry_trigger_engine.py`, `trade_plan_engine.py`, `decision_gate_engine.py`, `model_registry.py`, `absorption_reversal_engine.py`, `delta_absorption_failure_engine.py`, `failed_continuation_reversal_engine.py`, `candle_quality_engine.py`, `paper_lifecycle_tracker.py`, `outcome_monitor.py`, `edge_matrix_v2.py`.

Method: code read + latest state inspection + last-100 history sampling where available.

## Master Threshold Table

| ID | File | Function | Variable | Value | Type | Purpose | Blocks what? | Enables what? | Downstream impact | Source | Risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TH-001 | `src/simple/flow_evidence_engine.py` | `_delta_score`, `_aggression_score`, `_pressure_score` | score normalizer | `ratio * 10.0`, clamp `[-10.0, 10.0]` | NORMALIZER | Convert raw flow imbalance into bounded score | Extreme raw inputs from dominating | Comparable S13 signals | Drives evidence label, confidence, S14 persistence inputs | HARDCODED | MEDIUM |
| TH-002 | `src/simple/flow_evidence_engine.py` | `_pressure_label` | dominant pressure | `>= 3.0`, `<= -3.0` | SCORE_THRESHOLD | Decide dominant buyers/sellers | Neutral classification below threshold | Strong directional pressure labels | Feeds AR01, DAF, setup context | HARDCODED | MEDIUM |
| TH-003 | `src/simple/flow_evidence_engine.py` | `_pressure_label` | neutral pressure | `abs(score) < 1.5` | SCORE_THRESHOLD | Suppress weak pressure | Directional label on low pressure | Neutral state | Reduces early directional propagation | HARDCODED | LOW |
| TH-004 | `src/simple/flow_evidence_engine.py` | `_evidence_label` | strong evidence | `>= 6.0`, `<= -6.0` | SCORE_THRESHOLD | Mark strong flow conviction | Strong labels if score not high enough | `STRONG_LONG_FLOW`, `STRONG_SHORT_FLOW` | Major input to S15/S16 logic | HARDCODED | HIGH |
| TH-005 | `src/simple/flow_evidence_engine.py` | `_evidence_label` | early evidence | `>= 2.0`, `<= -2.0` | SCORE_THRESHOLD | Mark early directional flow | Early directional label if score too weak | `EARLY_LONG_FLOW`, `EARLY_SHORT_FLOW` | Allows weaker setup paths | HARDCODED | MEDIUM |
| TH-006 | `src/simple/flow_evidence_engine.py` | `_confidence` | confidence divisor | `/ 30.0` | NORMALIZER | Compress 3 absolute scores into `[0,1]` | Inflated confidence | Bounded evidence confidence | Impacts S13 data quality and downstream trust | HARDCODED | LOW |
| TH-007 | `src/simple/flow_persistence_engine.py` | `_compute_window` | directional count threshold | `score > 1.0`, `score < -1.0` | SCORE_THRESHOLD | Count meaningful positive/negative evidence inside windows | Noise from near-zero evidence | Window consistency | Feeds persistence label and continuation quality | HARDCODED | MEDIUM |
| TH-008 | `src/simple/flow_persistence_engine.py` | `_persistence_label` | 5m long/short | `avg_5m > 2.0` or `< -2.0` and `consistency > 0.6` | ACTIVATION_THRESHOLD | Detect 5m persistent direction | Persistence on weak or inconsistent flow | `BUILDING_*`, `SUSTAINED_*` paths | Critical upstream for S15/S16 | HARDCODED | HIGH |
| TH-009 | `src/simple/flow_persistence_engine.py` | `_persistence_label` | 15m long/short | `sample_count > 10` and `avg_15m > 1.5` or `< -1.5` | ACTIVATION_THRESHOLD | Confirm broader direction | 15m confirmation on thin history | Stronger continuation states | Affects continuation quality and decay logic | HARDCODED | MEDIUM |
| TH-010 | `src/simple/flow_persistence_engine.py` | `_persistence_label` | sustained momentum | `30s > 3.0` with valid 5m direction | ACTIVATION_THRESHOLD | Require immediate momentum for sustained label | Sustained classification without strong 30s | `SUSTAINED_*` states | Strongly affects S15/S16 confidence path | HARDCODED | HIGH |
| TH-011 | `src/simple/flow_persistence_engine.py` | `_direction_label` | directional cutoffs | `> 1.0`, `< -1.0` | SCORE_THRESHOLD | Convert persistence score into direction label | Direction on weak persistence | Long/short persistence label | Used by S16 and narrative output | HARDCODED | LOW |
| TH-012 | `src/simple/flow_persistence_engine.py` | `_continuation_quality` | sustained quality | `15m sample >= 10` and `15m consistency >= 0.70` | CONFIDENCE_THRESHOLD | Upgrade sustained trend quality | `SUSTAINED` status on low-consistency 15m | `SUSTAINED` continuation | Raises S15/S16 confidence if mapping matches | HARDCODED | MEDIUM |
| TH-013 | `src/simple/flow_persistence_engine.py` | `_continuation_quality` | moderate quality | `15m consistency >= 0.55` | CONFIDENCE_THRESHOLD | Mid-grade continuation if not sustained | Moderate classification below 0.55 | `MODERATE` continuation | Impacts S15/S16 weights | HARDCODED | MEDIUM |
| TH-014 | `src/simple/flow_persistence_engine.py` | `_decay_risk` | decay trigger | `abs(30s) < abs(15m) - 2.0` | VETO_THRESHOLD | Detect loss of immediate momentum | Clean continuation | `decay_risk = True` | Penalizes S16 trigger strength and fakeout risk | HARDCODED | HIGH |
| TH-015 | `src/simple/flow_persistence_engine.py` | `_data_quality` | sample quality | `>=25 => OK`, `>=10 => REDUCED`, `>=3 => LOW`, else `INSUFFICIENT` | QUALITY_THRESHOLD | Grade persistence reliability by 30s sample count | High-quality persistence on thin sample | Better DQ downstream | Feeds S15/S16/S17/S18 gating | HARDCODED | HIGH |
| TH-016 | `src/simple/flow_persistence_engine.py` | `_persistence_score` | window weights | `0.1 * 30s + 0.3 * 5m + 0.6 * 15m`, clamp `[-10,10]` | NORMALIZER | Favor broader context over immediate blips | 30s-only persistence dominance | Stable persistence score | Central to S15/S16 directional context | HARDCODED | MEDIUM |
| TH-017 | `src/simple/flow_to_setup_context_engine.py` | `_context_score` | evidence/persistence weights | `0.6`, `0.4`, clamp `[-10.0, 10.0]` | NORMALIZER | Blend raw evidence and persistence into setup score | Single-source dominance | Setup direction and strength | Primary S15 numeric backbone | HARDCODED | HIGH |
| TH-018 | `src/simple/flow_to_setup_context_engine.py` | `_direction_bias` | direction cutoff | `> 1.5`, `< -1.5` | SCORE_THRESHOLD | Convert setup score into `LONG/SHORT/NEUTRAL` | Weak direction becoming actionable | Direction bias | Drives S16 scenario direction | HARDCODED | HIGH |
| TH-019 | `src/simple/flow_to_setup_context_engine.py` | `_context_confidence` | continuation weights | `STRONG=1.0`, `MODERATE=0.75`, `WEAK=0.50`, `NONE=0.25`, fallback `0.25` | FALLBACK | Weight setup confidence by continuation quality | Strong continuation if enum mismatches | Higher confidence when mapping matches | Silent failure if S14 emits `SUSTAINED/BUILDING` | HARDCODED | CRITICAL |
| TH-020 | `src/simple/flow_to_setup_context_engine.py` | `_setup_context_label` | no-trade confidence cutoff | `confidence < 0.30` | CONFIDENCE_THRESHOLD | Early reject weak context | Any scenario path | `NO_TRADE_CONTEXT` | Kills S16/S17/S18/S20/S21/S22 chain | HARDCODED | CRITICAL |
| TH-021 | `src/simple/flow_to_setup_context_engine.py` | `_setup_context_label` | strong setup | `score >= 5.0` or `<= -5.0` and `confidence >= 0.60` | ACTIVATION_THRESHOLD | Require both directional score and confidence for tradeable setup labels | Strong setup label on weaker score/conf | `STRONG_LONG_CONTEXT`, `STRONG_SHORT_CONTEXT` | Required by tradeable path | HARDCODED | HIGH |
| TH-022 | `src/simple/flow_to_setup_context_engine.py` | `_tradeable` | tradeable gate | `dq in {OK,HIGH}`, `confidence >= 0.60`, not `CHOPPY_FLOW`, directional, strong context label | GATING_THRESHOLD | Decide whether S15 marks context tradeable | Tradeable state on low quality or weak setup | `tradeable = True` | First hard gate before S16/S17 | HARDCODED | CRITICAL |
| TH-023 | `src/simple/flow_to_setup_context_engine.py` | `_data_quality` | setup DQ score bands | `>= 0.85`, `>= 0.60`, `>= 0.30`, else | QUALITY_THRESHOLD | Grade S15 setup data quality | Better DQ label below bands | `OK/REDUCED/LOW/MISSING` | Affects S15 tradeable and downstream gating | HARDCODED | HIGH |
| TH-024 | `src/simple/flow_to_setup_context_engine.py` | `_confidence_to_probability` | probability formula | `50.0 + confidence * 45.0`, clamp `[50.0,95.0]` | NORMALIZER | Translate confidence into operator probability | Probability inflation | Signal eligibility and class | Operator summary and potential downstream use | HARDCODED | MEDIUM |
| TH-025 | `src/simple/flow_to_setup_context_engine.py` | `_confidence_to_probability` | continuation adjustments | `SUSTAINED +5.0`, `BUILDING +2.0`, `MODERATE +1.0`, `FADING -5.0` | SCORE_THRESHOLD | Bias signal probability by persistence regime | Flat probability across regimes | Higher/lower signal quality | Influences `signal_class` and eligibility | HARDCODED | MEDIUM |
| TH-026 | `src/simple/flow_to_setup_context_engine.py` | `_confidence_to_probability` | signal class bands | `A_PLUS >= 85`, `A >= 75`, `B >= 65`, `C >= 60` | CONFIDENCE_THRESHOLD | Convert probability into discrete operator class | Better class below threshold | Signal class and `signal_eligible` | Affects narrative and readiness perception | HARDCODED | MEDIUM |
| TH-027 | `src/simple/scenario_entry_trigger_engine.py` | `_scenario_score` | score weights | `0.5 * setup + 0.3 * persistence + 0.2 * evidence`, clamp `[-10,10]` | NORMALIZER | Build scenario directional score | Overweighting any one upstream source | Scenario label + downstream direction | Main S16 score backbone | HARDCODED | HIGH |
| TH-028 | `src/simple/scenario_entry_trigger_engine.py` | `_scenario_label` | breakout attempt | strong long/short evidence and not sustained same side and `setup_score >= 4.0` or `<= -4.0` | ACTIVATION_THRESHOLD | Detect possible breakout attempt | Breakout scenario on weaker context | `BREAKOUT_ATTEMPT` | Can lead to entry readiness | HARDCODED | HIGH |
| TH-029 | `src/simple/scenario_entry_trigger_engine.py` | `_trigger_strength` | weight blend | `confidence*0.5 + score_w*0.3 + cont_w*0.2` | NORMALIZER | Convert setup quality into trigger strength | Excessive trigger strength from one source | Trigger progression | Used by S16 ready gate and S17 stop sizing | HARDCODED | HIGH |
| TH-030 | `src/simple/scenario_entry_trigger_engine.py` | `_trigger_strength` | decay/flip penalties | `*0.65` if decay, `*0.55` if flip | VETO_THRESHOLD | Penalize fragile trigger | High trigger despite decay/flip risk | Conservative readiness | Strongly suppresses entry signals | HARDCODED | HIGH |
| TH-031 | `src/simple/scenario_entry_trigger_engine.py` | `_trigger_state` | ready/wait cutoffs | `READY` if `confidence >= 0.70` and `trigger_strength >= 0.70` and DQ ok/high and not choppy; `WAIT` if `>= 0.50` | TRIGGER_THRESHOLD | Decide if scenario is actionable | Ready path on weaker context | `READY_FOR_ENTRY` | Required for PLAN_READY and ALLOW_PAPER | HARDCODED | CRITICAL |
| TH-032 | `src/simple/scenario_entry_trigger_engine.py` | `_probabilities` | probability fallback | `move=0.33`, `mean=0.33`, `fakeout=0.34` | FALLBACK | Return sane distribution when data missing | Crashes on missing context | Output continuity | Silent neutralization if upstream broken | HARDCODED | MEDIUM |
| TH-033 | `src/simple/scenario_entry_trigger_engine.py` | `_probabilities` | fakeout adjustments | `flip +0.35`, `decay +0.25`, `failed breakout +0.30`, `breakout attempt +0.15`, `choppy +0.40`, `move_p *= 0.4`, clamp `fakeout <= 0.95`, `move_p = remaining * 0.7` | SCORE_THRESHOLD | Heuristic rebalance between move/mean/fakeout | Overconfident move probability | More cautious scenario probabilities | Operator-facing but also diagnostic | HARDCODED | MEDIUM |
| TH-034 | `src/simple/scenario_entry_trigger_engine.py` | `compute_scenario_trigger` | model override | opposite consensus and `model_strength > 60.0`; aligned score boost `*1.2` | VETO_THRESHOLD | Let model layer override or confirm setup | Original setup direction | `MODEL_*_OVERRIDE` or higher setup score | Changes scenario direction and trigger path | HARDCODED | HIGH |
| TH-035 | `src/simple/trade_plan_engine.py` | module constants | stop distance limits | `MIN_STOP_PCT = 0.0015`, `MAX_STOP_PCT = 0.0080` | SAFETY_LIMIT | Bound stop size between 0.15% and 0.80% | Too-tight or too-wide stop | Stable stop sizing | Controls RR and plan viability | HARDCODED | HIGH |
| TH-036 | `src/simple/trade_plan_engine.py` | `_stop_pct` | stop interpolation | base from trigger strength, then `* (1.05 - 0.10 * confidence)` | NORMALIZER | Tighten stops on stronger triggers/confidence | Excessively loose stops | Better RR on high-confidence setups | Impacts `entry/sl/tp` and plan grade | HARDCODED | MEDIUM |
| TH-037 | `src/simple/trade_plan_engine.py` | `_levels_from_structure` | structural offsets | long SL `bid_wall * 0.9995`, short SL `ask_wall * 1.0005`, long TP1 cap `ask_wall * 0.9998`, short TP1 floor `bid_wall * 1.0002` | SAFETY_LIMIT | Keep structural levels slightly inside/outside walls | Exact wall prints causing false fills | More realistic paper levels | Impacts realized RR and fill assumptions | HARDCODED | HIGH |
| TH-038 | `src/simple/trade_plan_engine.py` | `_levels_from_stop_pct`, fallback paths | TP multiples | `TP1 = 1.5R`, `TP2 = 2.5R` | RR_THRESHOLD | Define target ladder | Lower RR plans | Profit target construction | Feeds RR tests and decision gate | HARDCODED | HIGH |
| TH-039 | `src/simple/trade_plan_engine.py` | module constants | minimum RR | `MIN_RR_TP1 = 1.5`, `MIN_RR_TP2 = 2.0` | RR_THRESHOLD | Require baseline risk/reward | `PLAN_READY` on poor RR | Watch/invalid plan only | Rechecked in S18 | HARDCODED | HIGH |
| TH-040 | `src/simple/trade_plan_engine.py` | `_grade_from_rr` | plan grade composite | `rr2*0.45 + trigger*0.30 + conf*0.25` | NORMALIZER | Grade plan quality beyond pure RR | Higher grade without overall quality | `A_PLUS/A/B/C` | Operator trust and plan ranking | HARDCODED | MEDIUM |
| TH-041 | `src/simple/trade_plan_engine.py` | `_grade_from_rr` | grade bands | `A_PLUS >= 1.45 and rr2 >= 2.5`, `A >= 1.20 and rr2 >= 2.0`, `B >= 0.95` | RR_THRESHOLD | Discrete trade plan grading | Better grade on weaker RR | Higher confidence plan labels | Affects decision narrative | HARDCODED | MEDIUM |
| TH-042 | `src/simple/trade_plan_engine.py` | `_quality_score` | quality composite | `rr_norm=((rr1+rr2)/6.0)*0.4 + trigger*0.3 + confidence*0.2 + dq*0.1` | NORMALIZER | Produce overall trade plan quality | Inflated quality from one metric | Bounded plan quality score | Supports plan status narrative | HARDCODED | MEDIUM |
| TH-043 | `src/simple/trade_plan_engine.py` | `compute_trade_plan` | no-actionable guard | `NO_SCENARIO`, `trigger != READY_FOR_ENTRY`, `ready_for_entry = false`, `NO_TRADE_CONTEXT`, `tradeable = false`, neutral model with `active_model_count == 0`, low/critical/invalid DQ | GATING_THRESHOLD | Prevent fake actionable plan | Real plan fields on weak context | `NO_ACTIONABLE_PLAN` or `WATCH_ONLY` | Fixes misleading plan issue | HARDCODED | CRITICAL |
| TH-044 | `src/simple/trade_plan_engine.py` | `compute_trade_plan` | model veto | opposite consensus and `model_strength > 65.0` | VETO_THRESHOLD | Let strong model cancel plan | Plan continuation against strong model | `plan_status = INVALID` | Hard block candidate for S18 | HARDCODED | HIGH |
| TH-045 | `src/simple/decision_gate_engine.py` | module constants | minimum RR | `MIN_RR_TP1 = 1.5`, `MIN_RR_TP2 = 2.0` | RR_THRESHOLD | Re-enforce plan RR minimums | `ALLOW_PAPER` on weak RR | Decision confidence | Duplicates S17 plan gate | HARDCODED | HIGH |
| TH-046 | `src/simple/decision_gate_engine.py` | `compute_decision_gate` | plan validity checklist | requires `plan_status == PLAN_READY`, `entry/sl/tp1` non-null, `ready_for_entry = true`, `trigger_state == READY_FOR_ENTRY`, setup family not `NO_SETUP/NO_TRADE_CONTEXT`, non-empty reason codes | GATING_THRESHOLD | Ensure only fully-formed plans pass | ALLOW on partial plans | `ALLOW_PAPER` possibility | Strong S18 enforcement | HARDCODED | CRITICAL |
| TH-047 | `src/simple/decision_gate_engine.py` | `compute_decision_gate` | model no-signal block | `consensus = NEUTRAL` and `active_model_count == 0` | VETO_THRESHOLD | Block trades without any model conviction | ALLOW in neutral/no-model regime | Conservative no-trade outcome | Directly kills S20/S21/S22 chain | HARDCODED | HIGH |
| TH-048 | `src/simple/decision_gate_engine.py` | `compute_decision_gate` | data quality block | `dq in {INVALID, MISSING}` hard block, `LOW` warning | QUALITY_THRESHOLD | Prevent execution on broken inputs | ALLOW on bad data | Cleaner paper lifecycle input | Can downgrade or kill downstream chain | HARDCODED | HIGH |
| TH-049 | `src/simple/decision_gate_engine.py` | `compute_decision_gate` | depth veto | `sweep_risk == IMMINENT`, `wall_conclusion == LIKELY_SPOOF` | VETO_THRESHOLD | Hard risk control from depth/wall state | ALLOW against imminent sweep/spoof | Safety block | Frequent blocker in history | HARDCODED | HIGH |
| TH-050 | `src/simple/decision_gate_engine.py` | `_decision_grade` | gate grade composite | `rr2*0.4 + trigger*0.35 + dq*0.25`; `A_PLUS >= 1.55 and rr2 >= 2.5`, `A >= 1.30 and rr2 >= 2.0`, `B >= 1.05` | NORMALIZER | Grade allowed decision quality | Higher decision grade on weak evidence | Operator confidence after gate | Reporting layer only after allow | HARDCODED | MEDIUM |
| TH-051 | `src/simple/model_registry.py` | `run_model_registry` | consensus cutoff | `LONG if > 55.0`, `SHORT if > 55.0`, else neutral | CONSENSUS_THRESHOLD | Avoid consensus on weak split | Directional model call at 50/50 | `consensus_direction` | Used in S16/S17/S18 | HARDCODED | MEDIUM |
| TH-052 | `src/simple/model_registry.py` | `_data_quality` | model output count bands | `4 => OK`, `>=2 => REDUCED`, `1 => LOW`, `0 => MISSING` | QUALITY_THRESHOLD | Grade registry completeness | High DQ with partial models | Registry trust | Can warn or block later | HARDCODED | MEDIUM |
| TH-053 | `src/simple/model_registry.py` | `run_model_registry` | neutral default | `50.0 / 50.0` if no signals | FALLBACK | Stable output when no active signals | Divide-by-zero / missing consensus | `NEUTRAL` registry output | Can silently normalize dead models | FALLBACK | HIGH |
| TH-054 | `src/simple/absorption_reversal_engine.py` | `run_absorption_reversal_engine` | aggressor side | `pressure_score > 2.0`, `< -2.0` | ACTIVATION_THRESHOLD | Determine who is pushing | Absorption logic on weak pressure | `BUYERS/SELLERS` aggressor | Needed for AR01 activation | HARDCODED | MEDIUM |
| TH-055 | `src/simple/absorption_reversal_engine.py` | `run_absorption_reversal_engine` | absorption detect | buyers + `evidence_score < 1.0`; sellers + `evidence_score > -1.0` | ACTIVATION_THRESHOLD | Detect aggressive side being absorbed | AR01 activation | `absorption_detected = true` | May add reversal signal to registry | HARDCODED | HIGH |
| TH-056 | `src/simple/absorption_reversal_engine.py` | `run_absorption_reversal_engine` | trap/reversal formulas | `trap = abs(pressure)*10`, clamp `[0,100]`; `reversal = trap * 0.85` | NORMALIZER | Convert aggression into reversal probability | Values outside 0-100 | Comparable AR01 signal strength | Feeds registry strengths | HARDCODED | MEDIUM |
| TH-057 | `src/simple/absorption_reversal_engine.py` | `run_absorption_reversal_engine` | absorption strength formula | `abs(pressure)*8 + abs(aggression)*3 + abs(delta)*3 + mismatch*12` | NORMALIZER | Quantify absorption severity | Weak strength under mismatch | Stronger reason codes and signal severity | Registry diagnostic strength | HARDCODED | MEDIUM |
| TH-058 | `src/simple/absorption_reversal_engine.py` | `run_absorption_reversal_engine` | trap risk labels | `>= 70 high`, `>= 40 medium` | SCORE_THRESHOLD | Map trap probability to reason codes | High-risk labels on lower values | Human-readable risk | Reporting only | HARDCODED | LOW |
| TH-059 | `src/simple/delta_absorption_failure_engine.py` | `run_delta_absorption_failure_engine` | delta divergence | `abs(delta_score) - abs(evidence_score) > 2.0` | ACTIVATION_THRESHOLD | Detect wasted delta | DAF activation on small mismatch | `delta_divergence = true` | Registry signal candidate | HARDCODED | HIGH |
| TH-060 | `src/simple/delta_absorption_failure_engine.py` | `run_delta_absorption_failure_engine` | failed side rules | buyers fail if `delta_score > 2.0` and `evidence_score < 0.5`; sellers fail if `< -2.0` and `> -0.5` | ACTIVATION_THRESHOLD | Decide reversal side after delta failure | DAF bias on ambiguous mismatch | `reversal_bias` | Registry directional signal | HARDCODED | HIGH |
| TH-061 | `src/simple/delta_absorption_failure_engine.py` | `run_delta_absorption_failure_engine` | context bonuses | `30s abs < 1.0 => +15`, `5m abs < 1.5 => +10`, `consistency < 0.55 => +10`, opposite sign => `+20` | SCORE_THRESHOLD | Intensify failure strength when delta is wasted in weak context | Understated DAF strength | Higher signal strength | Registry weighting | HARDCODED | MEDIUM |
| TH-062 | `src/simple/delta_absorption_failure_engine.py` | `run_delta_absorption_failure_engine` | failure strength | `divergence * 20 + bonuses`, clamp `[0,100]` | NORMALIZER | Normalize DAF severity | Out-of-range strengths | Comparable registry weighting | Affects consensus percentages | HARDCODED | MEDIUM |
| TH-063 | `src/simple/delta_absorption_failure_engine.py` | `_data_quality` | DAF DQ bands | `>= 0.85`, `>= 0.60`, `> 0`, else | QUALITY_THRESHOLD | Grade DAF input completeness | High DQ with poor inputs | DAF trust | Reporting and possible downstream trust | HARDCODED | LOW |
| TH-064 | `src/simple/failed_continuation_reversal_engine.py` | `run_failed_continuation_reversal_engine` | continuation failed | had momentum and opposite 30s direction or decay/flip risk | ACTIVATION_THRESHOLD | Detect trapped continuation | FCR activation on ordinary pullback | `continuation_failed` | Registry signal candidate | HARDCODED | HIGH |
| TH-065 | `src/simple/failed_continuation_reversal_engine.py` | `run_failed_continuation_reversal_engine` | reversal ready | long momentum with `30s avg < -1.0`; short with `> 1.0` | ACTIVATION_THRESHOLD | Require actual opposite push before reversal-ready | Reversal-ready flag | Stronger trap confirmation | Registry/detail output | HARDCODED | MEDIUM |
| TH-066 | `src/simple/failed_continuation_reversal_engine.py` | `run_failed_continuation_reversal_engine` | trap strength weights | continuation quality weights `24/18/15/10/5`, `abs(5m)*6`, `abs(30s)*8`, `decay +18`, `flip +22`, clamp `[0,100]` | NORMALIZER | Quantify failed continuation severity | Weak strength despite strong reversal | Strong registry signal | Consensus weighting | HARDCODED | MEDIUM |
| TH-067 | `src/simple/candle_quality_engine.py` | `run_candle_quality_engine` | wick threshold | `upper_wick_ratio > 0.6`, `lower_wick_ratio > 0.6` | ACTIVATION_THRESHOLD | Detect wick rejection/fake move geometry | Fake-move logic on small wick | Fake move suspicion | CQE output in registry | HARDCODED | MEDIUM |
| TH-068 | `src/simple/candle_quality_engine.py` | `run_candle_quality_engine` | fake move weights | wick `+40`, delta misaligned `+30`, body `< 0.2 => +20`, 60s contradiction `+10`, clamp `[0,100]` | NORMALIZER | Aggregate fake-move risk | Understated fake probability | `FAKE_MOVE` path | Candle quality in registry summary | HARDCODED | MEDIUM |
| TH-069 | `src/simple/candle_quality_engine.py` | `run_candle_quality_engine` | quality cutoffs | strong if `fake < 20` and aligned and `body_ratio > 0.5`; fake if `> 60` | SCORE_THRESHOLD | Classify candle quality | Strong/fake labels below thresholds | `STRONG_BULLISH/STRONG_BEARISH/FAKE_MOVE/WEAK_*` | Registry candle output | HARDCODED | MEDIUM |
| TH-070 | `src/simple/candle_quality_engine.py` | `_data_quality` | CQE DQ bands | `>= 0.85`, `>= 0.60`, `> 0`, else | QUALITY_THRESHOLD | Grade CQE input completeness | Better DQ on weak inputs | CQE trust | Registry reporting | HARDCODED | LOW |
| TH-071 | `src/simple/paper_lifecycle_tracker.py` | `run_paper_lifecycle_tracker` | lifecycle open gate | `decision == ALLOW_PAPER` and alert status in `SENT/DRY_RUN_READY` | GATING_THRESHOLD | Prevent lifecycle start before gate approval | Paper trade opening on block/watch | Lifecycle `OPEN` | Required for outcomes and edge | HARDCODED | CRITICAL |
| TH-072 | `src/simple/paper_lifecycle_tracker.py` | lifecycle initialization | missing price downgrade | if any of `entry/sl/tp1/tp2` missing, `dq_score = min(score, 0.4)` | QUALITY_THRESHOLD | Flag malformed lifecycle | High DQ on partial trade | Lower lifecycle quality | Limits trust in paper lifecycle | HARDCODED | MEDIUM |
| TH-073 | `src/simple/paper_lifecycle_tracker.py` | lifecycle initialization | lifecycle DQ bands | `>= 0.8 HIGH`, `>= 0.5 MEDIUM`, `>= 0.2 LOW`, else `CRITICAL` | QUALITY_THRESHOLD | Grade lifecycle integrity | Higher lifecycle quality on broken state | DQ status | Reporting, maybe future gating | HARDCODED | LOW |
| TH-074 | `src/simple/paper_lifecycle_tracker.py` | lifecycle close logic | realized loss | stop hit => `realized_rr = -1.0` | DEFAULT_VALUE | Standardize stop-loss outcome | Variable loss encoding | Comparable edge stats | Feeds outcome and edge | HARDCODED | LOW |
| TH-075 | `src/simple/outcome_monitor.py` | `_calc_r` | valid risk | `risk > 0` required | SAFETY_LIMIT | Prevent divide-by-zero or inverted RR math | R-calculation on invalid lifecycle | Valid realized R | Needed for usable closed outcomes | HARDCODED | MEDIUM |
| TH-076 | `src/simple/edge_matrix_v2.py` | module constants | minimum sample | `MIN_REQUIRED_SAMPLE = 30` | QUALITY_THRESHOLD | Forbid edge claims on tiny sample | Usable edge on too little data | `RESEARCH_ONLY` / stronger states only later | Final S22 gate | HARDCODED | HIGH |
| TH-077 | `src/simple/edge_matrix_v2.py` | module constants | robust sample | `ROBUST_SAMPLE_THRESHOLD = 100` | QUALITY_THRESHOLD | Separate robust from early edge claims | `VALIDATED_EDGE` too early | Higher confidence edge states | Final edge confidence | HARDCODED | MEDIUM |
| TH-078 | `src/simple/edge_matrix_v2.py` | module constants | sample bands | `20`, `50`, `100`, `200` | DEFAULT_VALUE | Intended sample taxonomy | Nothing directly; partly descriptive | Confidence banding | Some are currently descriptive more than enforced | HARDCODED | LOW |
| TH-079 | `src/simple/edge_matrix_v2.py` | `_edge_quality` | winrate/expectancy gate | robust path requires `usable_closed >= 100`, `winrate >= 0.5`, `expectancy > 0`; weaker positive expectancy paths below that | ACTIVATION_THRESHOLD | Only claim edge when sample and expectancy are sufficient | Strong edge claim on weak stats | `PROMISING_EDGE`, `VALIDATED_EDGE`, etc. | Final reported edge quality | HARDCODED | HIGH |
| TH-080 | `src/simple/edge_matrix_v2.py` | `_data_quality` | edge DQ bands | `usable=0 => 0.1 LOW`, `<30 => 0.3 LOW`, `<100 => 0.6 MEDIUM`, else `1.0 HIGH` | QUALITY_THRESHOLD | Grade trust in edge matrix output | High DQ on no sample | Honest edge confidence | Reporting and operator trust | HARDCODED | MEDIUM |

## 1. FALLBACK VALUES

| Fallback | File | Why it exists | Trigger condition | Silent failure risk | Audit note |
|---|---|---|---|---|---|
| `continuation_weights.get(label, 0.25)` | `flow_to_setup_context_engine.py` | Unknown continuation labels still return a confidence weight | Any label outside `STRONG/MODERATE/WEAK/NONE` | CRITICAL | S14 emits `SUSTAINED` and `BUILDING`; S15 treats both as `0.25`. This is the most dangerous silent fallback in the system. |
| `continuation_weights.get(label, 0.25)` | `scenario_entry_trigger_engine.py` | Unknown continuation labels still produce trigger strength | Any unmapped continuation label | HIGH | Same mismatch risk, now directly damping `trigger_strength`. |
| `move=0.33, mean=0.33, fakeout=0.34` | `scenario_entry_trigger_engine.py` | Safe probability output when upstream missing | Missing/invalid scenario context | MEDIUM | Good for output continuity, bad if mistaken for meaningful forecast. |
| `long_pct=50.0, short_pct=50.0` | `model_registry.py` | Neutral probabilities when no active model | `active_signals == []` | HIGH | Can hide a dead model layer behind a stable neutral output. |
| `data_quality score = 0.0/0.1/0.3/...` | multiple | Always emit a DQ score | Missing or insufficient input | MEDIUM | Good for schema stability, but downstream often reads only label not raw score. |
| `identity.setup_family = NO_SETUP`, `model_name = NO_MODEL` | S20/S21 lineage defaults | Preserve lineage shape even on no-trade | Missing identity chain | LOW | Safe and useful; not the main issue. |
| `selected_entry = null`, `selected_rr = 0.0` | `decision_gate_engine.py` | Blocked trades should not expose execution prices | Decision not allowed | LOW | Correct safety fallback. |
| `realized_rr = -1.0` on SL | `paper_lifecycle_tracker.py` | Standardize loss outcome | Stop-loss hit | LOW | Reasonable fixed convention. |
| `edge_score = 0.0`, `NO_EDGE_CLAIM` | `edge_matrix_v2.py` | Stable edge output with no usable sample | `usable_closed_records == 0` | LOW | Correct conservative fallback. |

Fallback verdict:

- The dangerous fallbacks are not the neutral/default outputs themselves.
- The dangerous fallback is any fallback that silently downgrades strong upstream states into weak scores.
- The single worst example is the continuation-weight fallback `0.25` in S15 and S16.

## 2. DEAD THRESHOLDS

History sample used: last 100 records where file length allowed. `model_registry_history.jsonl` had fewer than 100 rows, so its count is on the available tail.

| Threshold | Trigger Count | Never Triggered? | Stage |
|---|---|---|---|
| `S15 confidence >= 0.30` | `0 / 100` | Yes | S15 |
| `S15 confidence >= 0.60` | `0 / 100` | Yes | S15 |
| `tradeable == true` | `0 / 100` | Yes | S15 |
| `active_model_count > 0` | `0 / 57` | Yes | MODEL_REGISTRY |
| `trigger_strength >= 0.50` | `0 / 100` | Yes | S16 |
| `trigger_strength >= 0.70` | `0 / 100` | Yes | S16 |
| `ready_for_entry == true` | `0 / 100` | Yes | S16 |
| `plan_status == PLAN_READY` | `0 / 100` | Yes | S17 |
| `plan_status == WATCH_ONLY` | `45 / 100` | No | S17 |
| `rr_tp1 >= 1.5` | `17 / 100` | No | S17 |
| `rr_tp2 >= 2.0` | `45 / 100` | No | S17 |
| `decision == ALLOW_PAPER` | `0 / 100` | Yes | S18 |
| `decision == WATCH` | `36 / 100` | No | S18 |
| `block_reasons contains DEPTH_VETO_SWEEP_RISK_IMMINENT` | `63 / 100` | No | S18 |
| `lifecycle_status in {OPEN, ACTIVE, CLOSED}` | `0 / 100` | Yes | S20 |
| `outcome_status == CLOSED` | `0 / 100` | Yes | S21 |
| `usable_closed_records > 0` | `0 / 100` | Yes | S22 |

Dead-threshold verdict:

- The practical dead zone starts at S15, not S18.
- S16, S17, S18, S20, S21, S22 are mostly dead because S15 never exits `NO_TRADE_CONTEXT`.
- `active_model_count > 0` is also dead in the sampled history, so the model layer is not rescuing S15.

## 3. CHAIN KILLERS

| Killer Threshold | Immediate Effect | Full Downstream Kill Chain | Severity |
|---|---|---|---|
| `continuation_weight fallback = 0.25` on unmapped `SUSTAINED/BUILDING` | S15 confidence collapses | `low confidence -> NO_TRADE_CONTEXT -> NO_SCENARIO -> NO_ACTIONABLE_PLAN -> BLOCK -> NO_LIFECYCLE -> NO_OUTCOME -> NO_EDGE_CLAIM` | CRITICAL |
| `S15 confidence < 0.30` | `setup_context_label = NO_TRADE_CONTEXT` | `NO_TRADE_CONTEXT -> S16 hard guard -> S17 no actionable plan -> S18 block/watch -> no lifecycle -> no outcome -> no edge` | CRITICAL |
| `S15 confidence < 0.60` or `dq != OK/HIGH` | `tradeable = false` | `not tradeable -> NO_SCENARIO or weak trigger -> no plan -> block -> no lifecycle` | CRITICAL |
| `S16 confidence < 0.70` or `trigger_strength < 0.70` | `ready_for_entry = false` | `not ready -> PLAN_READY impossible -> ALLOW_PAPER impossible -> lifecycle impossible` | HIGH |
| `S17 rr_tp1 < 1.5` or `rr_tp2 < 2.0` | `WATCH_ONLY` or invalid plan | `no plan ready -> S18 block/watch -> no lifecycle` | HIGH |
| `MODEL_REGISTRY active_model_count == 0 and consensus = NEUTRAL` | S17 and S18 veto path | `neutral/no model -> no actionable plan -> block -> no lifecycle -> no outcome` | HIGH |
| `depth sweep risk = IMMINENT` | S18 hard block | `BLOCK -> NO_LIFECYCLE -> NO_OUTCOME -> NO_EDGE` | HIGH |
| `usable_closed_records < 30` | S22 refuses edge claim | `RESEARCH_ONLY/NO_EDGE_CLAIM` | MEDIUM |

## 4. DUPLICATED LOGIC

| Logic | Files | Duplicate Count | Risk |
|---|---|---|---|
| Confidence gating | `flow_to_setup_context_engine.py`, `scenario_entry_trigger_engine.py`, `trade_plan_engine.py`, `decision_gate_engine.py` | 4 | HIGH |
| Data-quality gating | `flow_to_setup_context_engine.py`, `scenario_entry_trigger_engine.py`, `trade_plan_engine.py`, `decision_gate_engine.py`, model engines | 5+ | HIGH |
| RR minimums `1.5 / 2.0` | `trade_plan_engine.py`, `decision_gate_engine.py` | 2 | MEDIUM |
| Neutral/no-model veto | `trade_plan_engine.py`, `decision_gate_engine.py` | 2 | MEDIUM |
| Continuation weight mapping | `flow_to_setup_context_engine.py`, `scenario_entry_trigger_engine.py` | 2 | CRITICAL |
| Score clamping to `[-10,10]` | S13, S14, S15, S16 | 4 | LOW |
| Grade-band heuristics | `flow_to_setup_context_engine.py`, `trade_plan_engine.py`, `decision_gate_engine.py`, `edge_matrix_v2.py` | 4 | MEDIUM |

Duplicate-logic verdict:

- Duplicate safety checks are acceptable when they are identical and intentional.
- Duplicate heuristics become dangerous when they drift.
- The continuation-weight duplication is the worst one because both copies share the same fallback defect.

## 5. HEURISTIC VS DATA-DRIVEN

| Area | Threshold style | Data-driven? | Audit judgment |
|---|---|---|---|
| S13 flow evidence scores | Hardcoded ratios and clamps | No | Heuristic |
| S14 persistence labels | Hardcoded score and sample thresholds | No | Heuristic |
| S15 setup confidence/tradeable | Hardcoded confidence and DQ cutoffs | No | Heuristic |
| S16 trigger readiness | Hardcoded 0.70/0.50 readiness logic | No | Heuristic |
| S17 RR and stop sizing | Hardcoded RR minima and stop bands | No | Heuristic |
| S18 decision gate | Hardcoded veto and gating rules | No | Heuristic-first safety gate |
| Model engines AR01/DAF/FCR/CQE | Hardcoded activation thresholds | No | Heuristic |
| S22 edge matrix | Sample thresholds + realized expectancy | Partly | Only S22 uses outcomes directly; upstream thresholds remain non-learning |

Heuristic verdict:

- The threshold system is overwhelmingly heuristic-first.
- It is not outcome-driven upstream of S22.
- Edge learning does not tune S15-S18 thresholds today.
- The system is evidence-shaped, but not evidence-calibrated by realized outcomes.

## 6. THRESHOLD DEPENDENCY MAP

| Threshold A | Direct dependency | Cascading result |
|---|---|---|
| `S14 continuation label` | feeds S15 continuation weight | enum mismatch can collapse S15 confidence |
| `S15 confidence < 0.30` | `setup_context_label = NO_TRADE_CONTEXT` | S16 scenario blocked |
| `S15 confidence < 0.60` | `tradeable = false` | S16 ready path practically dead |
| `S15 dq != OK/HIGH` | `tradeable = false` | S17 actionable plan blocked |
| `S16 trigger_strength < 0.50` | `trigger_state = WEAK_TRIGGER` | S17 no actionable plan |
| `S16 trigger_strength < 0.70` | `ready_for_entry = false` | S18 allow impossible |
| `S17 rr below 1.5 / 2.0` | `PLAN_READY` blocked | S18 ALLOW_PAPER blocked |
| `S17 model veto > 65` | `plan_status = INVALID` | S18 hard block |
| `S18 neutral/no-model` | hard block | S20 lifecycle impossible |
| `S18 depth veto` | hard block | S20/S21/S22 never receive live trade |
| `S20 no lifecycle` | no active trade | S21 no closed outcome |
| `S21 no closed outcome` | `usable_closed_records = 0` | S22 no edge claim |

Dependency verdict:

- The system does not have one isolated threshold problem.
- It has a cascade architecture where an early confidence failure disables every later stage.
- The first cascade trigger is S15.

## 7. FINAL VERDICT

### 1. Sistemin en tehlikeli magic number’ı nedir?

`0.25` continuation fallback weight in S15 and S16. It silently converts unmapped continuation states into weak confidence.

### 2. En tehlikeli fallback nedir?

`continuation_weights.get(label, 0.25)` because it is not visibly wrong in output schema but it kills the chain in practice.

### 3. En çok chain kill yapan threshold hangisi?

`S15 confidence < 0.30 -> NO_TRADE_CONTEXT`.

### 4. En gereksiz threshold hangisi?

`S22 SAMPLE_THRESHOLDS = {20, 50, 100, 200}` is partly decorative today; actual gating is mainly `30` and `100`.

### 5. En duplicate logic hangisi?

Confidence and DQ gating across S15, S16, S17, and S18.

### 6. Hangi thresholdlar outcome-driven değil?

Almost all thresholds from S13 through S18. They do not adapt from realized trade outcomes.

### 7. Hangi thresholdlar gerçek veri olmadan konulmuş görünüyor?

`S15 0.30/0.60 confidence`, `S16 0.70 ready`, `S17 1.5/2.0 RR`, `S18 neutral/no-model veto`, AR01/DAF/FCR activation cutoffs, CQE fake-move weights.

### 8. Hangi thresholdlar sistemi gereksiz boğuyor?

- S15 `confidence >= 0.60` for tradeable.
- S16 `confidence >= 0.70` and `trigger_strength >= 0.70`.
- S18 `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL` if the model layer is reversal-only and frequently inactive.

### 9. Hangi thresholdlar güvenlik için gerçekten gerekli?

- S17/S18 minimum RR floors.
- S18 hard block on missing/invalid data.
- S18 hard block on imminent sweep risk / likely spoof.
- S20 requiring `ALLOW_PAPER` before lifecycle open.
- S22 minimum sample requirement before claiming edge.

### 10. İlk kaldırılmaması gereken threshold hangisi?

`S18 depth veto` for imminent sweep/spoof risk.

### 11. İlk audit edilmesi gereken threshold hangisi?

S15 continuation weight fallback and the whole S15 confidence path.

### 12. Threshold sistemi şu an ne?

Heuristic-first, not outcome-driven.

### 13. Edge learning başlamadan threshold koymanın etkisi ne olmuş?

The system became over-governed before it produced a usable sample. It filters trades without feedback calibration, so dead paths stay dead.

### 14. Nova’ya gönderilecek en kritik 20 gerçeklik maddesi

1. S15 is the first real bottleneck, not S18.
2. The continuation-weight fallback `0.25` is likely suppressing both S15 confidence and S16 trigger strength.
3. S14 emits continuation states that S15/S16 do not map explicitly.
4. `confidence >= 0.30` never triggered in the last 100 S15 records sampled.
5. `tradeable == true` never triggered in the last 100 S15 records sampled.
6. `active_model_count > 0` never triggered in the available recent model history sampled.
7. `trigger_strength >= 0.50` never triggered in the last 100 S16 records sampled.
8. `ready_for_entry == true` never triggered in the last 100 S16 records sampled.
9. `PLAN_READY` never triggered in the last 100 S17 records sampled.
10. `ALLOW_PAPER` never triggered in the last 100 S18 records sampled.
11. `lifecycle OPEN/ACTIVE/CLOSED` never triggered in the last 100 S20 records sampled.
12. `usable_closed_records > 0` never triggered in the last 100 S22 records sampled.
13. S17 and S18 both enforce the same RR thresholds, so RR is double-gated.
14. Confidence and DQ are also multi-gated across four stages.
15. S18 neutral/no-model veto may be logically correct but is too absolute when models are often inactive.
16. S22 is conservative but not the main culprit; it is only reporting the absence of closed outcomes.
17. Most upstream thresholds are heuristic, not learned from outcomes.
18. The system is edge-blind upstream; no realized outcome is tuning early thresholds.
19. The current constitution prioritizes false-negative suppression over sample creation.
20. The first safe audit target is not “more trades”; it is the S15/S16 confidence constitution and enum mapping integrity.

## Bottom Line

The current threshold constitution is not failing because of one bad number in isolation. It is failing because a heuristic-first early-stage confidence regime is over-constrained, duplicated, and partly fed by a silent enum-mismatch fallback. That one structural weakness prevents the system from ever reaching the part of the loop where outcomes can teach anything back.
