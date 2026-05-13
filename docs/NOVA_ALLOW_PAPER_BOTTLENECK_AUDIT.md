# NOVA ALLOW PAPER BOTTLENECK AUDIT

## 1. Current Live State

| Stage | Current status | Direction | Score/confidence | Blocking reason |
|---|---|---|---|---|
| S15 Setup Context | `NO_TRADE_CONTEXT`, `tradeable=false` | `LONG` | `setup_context_score=10.0`, `confidence=0.25` | `context_reason=No trade context: low_confidence=0.25` |
| MODEL_REGISTRY | `active_model_count=0`, `consensus_direction=NEUTRAL` | `NEUTRAL` | `L=50.0%`, `S=50.0%`, `candle=WEAK_DOJI` | No active AR01/DAF/FCR signal |
| S16 Scenario Trigger | `NO_SCENARIO`, `NO_TRIGGER`, `ready_for_entry=false` | actionable `NEUTRAL`, diagnostic `LONG` | `scenario_score=0.0`, `trigger_strength=0.0` | `BLOCKED_BY_NO_TRADE_CONTEXT` |
| S17 Trade Plan | `NO_ACTIONABLE_PLAN` | `NEUTRAL` | `plan_quality_score=0.0` | `BLOCKED_BY_NO_TRADE_CONTEXT`, `BLOCKED_BY_NEUTRAL_MODEL_CONSENSUS` |
| S18 Decision Gate | `BLOCK` | `NEUTRAL` | `decision_score=0.4`, `final_grade=BLOCKED` | `DEPTH_VETO_SWEEP_RISK_IMMINENT`, `SIDE_NOT_DIRECTIONAL_NEUTRAL`, `RR_INVALID`, `SETUP_FAMILY_INVALID_NO_TRADE_CONTEXT`, `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL` |
| S20 Paper Lifecycle | `NO_LIFECYCLE` | `NEUTRAL` | `lifecycle_id=null` | `DECISION_NOT_ALLOWED_FOR_PAPER` |
| S21 Outcome | `NO_OUTCOME`, `NO_LIFECYCLE` | `NEUTRAL` | `realized_r=null` | `NO_LIFECYCLE_PRESENT` |
| S22 Edge | `NO_EDGE_CLAIM` | `N/A` | `usable_closed_records=0` | `NO_CLOSED_RESOLVED_SAMPLES` |

Current live evidence is not weak. `latest_flow_evidence.json` shows `evidence_score=10.0`, `evidence_label=STRONG_LONG_PRESSURE`, `confidence=1.0`. `latest_flow_persistence.json` shows `persistence_score=10.0`, `persistence_label=SUSTAINED_LONG_PRESSURE`, `continuation_quality=SUSTAINED`, `direction_consistency=1.0`. The chain still dies at S15.

## 2. S15 TRADEABLE TRUE ŞARTLARI

S15:

Function: `compute_setup_context()`, with gating in `_setup_context_label()`, `_context_confidence()`, `_tradeable()`

Required inputs:
- `latest_flow_evidence.json`: `evidence_score`, `evidence_label`, `confidence`, `data_quality`
- `latest_flow_persistence.json`: `persistence_score`, `persistence_label`, `continuation_quality`, `decay_risk`, `flip_risk`, `data_quality`

Tradeable true conditions:
- `dq_level in ("OK", "HIGH")`
- `confidence >= 0.60`
- `persistence_label != "CHOPPY_FLOW"`
- `direction_bias in ("LONG", "SHORT")`
- `setup_context_label in ("STRONG_LONG_CONTEXT", "STRONG_SHORT_CONTEXT")`

Current values:
- Evidence: `STRONG_LONG_PRESSURE`, `evidence_score=10.0`, `confidence=1.0`
- Persistence: `SUSTAINED_LONG_PRESSURE`, `continuation_quality=SUSTAINED`, `persistence_score=10.0`
- Output: `setup_context_label=NO_TRADE_CONTEXT`, `tradeable=false`, `confidence=0.25`

Why blocked:
- `_setup_context_label()` hard-sets `NO_TRADE_CONTEXT` when `confidence < 0.30`
- `_context_confidence()` computes `evidence_confidence * continuation_weight * dq_score`
- `_CONT_WEIGHTS` only defines `STRONG`, `MODERATE`, `WEAK`, `NONE`
- S14 emits `continuation_quality="SUSTAINED"` and `rg` on `flow_persistence_engine.py` shows it can also emit `BUILDING`
- Because `SUSTAINED` is missing from `_CONT_WEIGHTS`, S15 falls back to `0.25`
- With current inputs that becomes `1.0 * 0.25 * 1.0 = 0.25`, which immediately forces `NO_TRADE_CONTEXT`

Son 20 kayıt:
- `tradeable=true`: `0/20`
- `setup_context_label=NO_TRADE_CONTEXT`: `20/20`
- `data_quality`: `OK` or `REDUCED` in all 20; current live state is `OK`
- Confidence range: `0.175` to `0.25`

Why blocked summary:
- This is not a weak-market read.
- This is a field-mapping mismatch between S14 enum values and S15 weight keys.

Minimum fix candidate:
- Safest first fix is not lowering thresholds.
- First align S15 confidence weighting with actual S14 values: `SUSTAINED` and `BUILDING`.

## 3. MODEL_REGISTRY ACTIVE_MODEL_COUNT > 0 ŞARTLARI

`model_registry.py` reads:
- `latest_ar01.json`
- `latest_daf.json`
- `latest_fcr.json`
- `latest_cqe.json`

`active_model_count` logic:
- Counts AR01 only if `absorption_detected=true` and `reversal_bias in ("LONG","SHORT")`
- Counts DAF only if `delta_divergence=true` and `reversal_bias in ("LONG","SHORT")`
- Counts FCR only if `continuation_failed=true`
- CQE is not counted as an active signal at all. It only contributes `candle_quality`

Consensus logic:
- Sum `LONG` signal strengths and `SHORT` signal strengths
- `LONG` if `long_pct > 55`
- `SHORT` if `short_pct > 55`
- else `NEUTRAL`

Son 20 kayıt:
- `active_model_count > 0`: `0/20`
- `consensus_direction=NEUTRAL`: `20/20`

AR01:

Input files: `latest_flow_evidence.json`

Activation condition:
- `pressure_score > 2.0` and `evidence_score < 1.0` for buyer absorption
- `pressure_score < -2.0` and `evidence_score > -1.0` for seller absorption

Current last values:
- `aggressor_side=BUYERS`
- `trap_probability=100.0`
- `reversal_probability=0.0`
- `absorption_detected=false`

Why not active:
- Evidence is fully aligned with aggression: `pressure_score=10.0`, `evidence_score=10.0`
- That is continuation, not absorption

Threshold risk:
- Lowering this would create fake reversal traps during clean continuation

Minimum fix candidate:
- Do not loosen AR01 to force activity
- Treat AR01 as a veto/reversal detector, not a required positive confirmer

DAF:

Input files: `latest_flow_evidence.json`, `latest_flow_persistence.json`

Activation condition:
- `divergence = abs(delta_score) - abs(evidence_score) > 2.0`
- plus signed delta failure condition

Current last values:
- `delta_divergence=false`
- `divergence_score=0.0`
- `aggressive_side_failed=NONE`

Why not active:
- `delta_score=10.0` and `evidence_score=10.0` are perfectly aligned
- No wasted delta exists

Threshold risk:
- Lowering this would turn normal aligned trend into fake reversal signals

Minimum fix candidate:
- Do not loosen DAF to manufacture active models

FCR:

Input files: `latest_flow_persistence.json`

Activation condition:
- `had_momentum=true`
- and `last_30s dominant_label` opposite to momentum, or `decay_risk`, or `flip_risk`

Current last values:
- `had_momentum=true`
- `continuation_failed=false`
- `trap_strength=0.0`

Why not active:
- Momentum is still continuing
- `last_30s dominant_label=LONG`
- `decay_risk=false`
- `flip_risk=false`

Threshold risk:
- Lowering this would mark healthy continuation as failed continuation

Minimum fix candidate:
- Keep FCR strict
- Do not require FCR-like reversal detectors for every entry

CQE:

Input files: `latest_market_truth.json`, `latest_flow_evidence.json`, `latest_flow_persistence.json`

Activation condition:
- CQE has no activation path into `active_model_count`
- It only publishes `candle_quality`

Current last values:
- `candle_quality=WEAK_DOJI`
- `fake_move_probability=50.0`

Why not active:
- By design, registry never counts CQE as an active signal

Threshold risk:
- None. This is a registry design choice, not a threshold

Minimum fix candidate:
- If CQE is intended to be the fourth confirmer, registry must count it explicitly
- If not, `active_model_count` should not be treated as mandatory entry confirmation

Model summary:
- The registry is not missing signals that should have been counted.
- The model outputs themselves are inactive.
- More importantly, the three counted models are all reversal/failure/trap detectors.
- Clean continuation setups can pass S15/S16/S17 and still show `active_model_count=0` forever.

## 4. S16 READY_FOR_ENTRY ŞARTLARI

S16:

Function: `compute_scenario_trigger()`

Ready conditions:
- `trigger_state == "READY_FOR_ENTRY"`
- `tradeable_context == true`
- `confidence >= 0.70`
- `trigger_strength >= 0.70`
- `dq_level in ("OK","HIGH")`
- `persistence_label != "CHOPPY_FLOW"`
- `direction_bias in ("LONG","SHORT")`

NO_SCENARIO conditions:
- `setup_label == "NO_TRADE_CONTEXT"`
- `setup_label == "NEUTRAL_CONTEXT"`
- default fallthrough in `_scenario_label()`

BREAKOUT_ATTEMPT conditions:
- strong evidence long/short
- persistence not yet sustained
- setup score threshold met

Current values:
- `setup_context_label=NO_TRADE_CONTEXT`
- `direction_bias=LONG` upstream, but actionable direction becomes `NEUTRAL`
- `scenario_label=NO_SCENARIO`
- `trigger_state=NO_TRIGGER`
- `ready_for_entry=false`

Son 20 kayıt:
- `ready_for_entry=true`: `0/20`
- `scenario_label=NO_SCENARIO`: `20/20`
- `trigger_state=NO_TRIGGER`: `20/20`

Why blocked:
- S16 is not the first failure
- It inherits S15’s `NO_TRADE_CONTEXT` and deliberately shuts down actionable scenarios

Minimum fix candidate:
- Do not loosen S16 first
- Fix S15 confidence mapping first, then re-evaluate whether S16 still blocks

## 5. S17 PLAN_READY ŞARTLARI

S17:

Function: `compute_trade_plan()`

PLAN_READY conditions:
- `scenario_trigger` exists
- `ref_price` exists
- `side in ("LONG","SHORT")`
- `dq_level in ("OK","HIGH")`
- `ready_for_entry=true`
- `trigger_state=="READY_FOR_ENTRY"`
- valid stop/target direction
- `rr_tp1 >= 1.5`
- `rr_tp2 >= 2.0`
- no model veto

WATCH_ONLY conditions:
- degraded `data_quality`
- trigger not ready
- low RR

NO_ACTIONABLE_PLAN conditions:
- `scenario_label == "NO_SCENARIO"`
- `setup_label == "NO_TRADE_CONTEXT"`
- `not setup_tradeable` in that path
- model registry present with `NEUTRAL + 0 signals` in that same no-trade path

Entry/SL/TP real fields:
- Real fields are filled during normal `WATCH_ONLY` and `PLAN_READY` branches
- They are nullified only when S17 enters `NO_ACTIONABLE_PLAN`

Preview plan:
- `preview_plan` is written only if a directional preview existed before nullification
- Current live state has `preview_plan=null` because S16 already neutralized the side

Model consensus neutral:
- In current code, neutral model blocks only inside the no-trade path
- It is not a general S17 hard block

Data quality LOW:
- S17 downgrades to `WATCH_ONLY`

Son 20 kayıt:
- `PLAN_READY`: `0/20`
- `plan_status=NO_ACTIONABLE_PLAN`: `20/20`

Current values:
- `plan_status=NO_ACTIONABLE_PLAN`
- `side=NEUTRAL`
- `entry_price=null`
- `stop_loss=null`
- `tp1=null`
- `tp2=null`

Why blocked:
- S17 is blocked by upstream `NO_SCENARIO`
- It is not the root cause

Minimum fix candidate:
- Do not loosen RR or stop logic before S15/S18 are fixed

## 6. S18 ALLOW_PAPER ŞARTLARI

S18:

Function: `compute_decision_gate()`

ALLOW_PAPER checklist:
- `input_available`
- `plan_status == PLAN_READY`
- `side_valid`
- `price_logic_valid`
- `rr_valid`
- `rr_threshold_valid`
- `data_quality_valid`
- `trigger_ready`
- `safety_valid`
- `reasons_present`
- no `block_reasons`

BLOCK conditions include:
- `PLAN_STATUS_INVALID`
- non-directional side
- price logic contradiction
- invalid RR
- invalid or missing DQ
- unsafe flags
- empty reason codes
- invalid setup family when identity exists
- `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL`
- `DEPTH_VETO_*`

WATCH conditions:
- no hard block
- but plan not ready, trigger not ready, or RR below threshold

setup_family/model_id:
- `setup_family` is enforced
- `model_id` is not directly required
- but `model_registry` with `NEUTRAL + 0 signals` is a hard block

data_quality LOW:
- warning, not automatic block

RR düşük:
- warning, not automatic block

depth veto:
- hard block

model neutral:
- hard block if registry is provided and `active_model_count == 0`

Son 20 kayıt:
- `ALLOW_PAPER`: `0/20`
- `decision=BLOCK`: `20/20`

Most frequent block reasons in last 20:
- `DEPTH_VETO_SWEEP_RISK_IMMINENT`: `20`
- `SIDE_NOT_DIRECTIONAL_NEUTRAL`: `20`
- `RR_INVALID`: `20`
- `SETUP_FAMILY_INVALID_NO_TRADE_CONTEXT`: `20`
- `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL`: `20`

Current values:
- `decision=BLOCK`
- `decision_score=0.4`
- `data_quality=OK`

Why blocked:
- In current live data, S18 is downstream of the S15 failure
- Structurally, S18 also has a second blocker: it hard-blocks `NEUTRAL + 0 model signals`
- Because registry only counts reversal/failure models, that means many valid continuation setups can never reach `ALLOW_PAPER`

Minimum fix candidate:
- Safest S18 fix is to turn `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL` into a warning unless a model is actively vetoing the setup
- Keep `DEPTH_VETO_*` as a hard block until separately audited

## 7. S20 → S21 → S22 EDGE CHAIN

S20-S22:

Lifecycle open conditions:
- S20 requires `decision == ALLOW_PAPER`
- S20 also requires `alert_status in ("SENT", "DRY_RUN_READY")`
- This means S18 is necessary but not sufficient. S19 alert delivery must also succeed

Outcome close conditions:
- S21 becomes `CLOSED` only if lifecycle reaches `TP2_HIT`, `SL_HIT`, `INVALIDATED`, or an explicit `CLOSED` state with TP hit flags

Usable edge conditions:
- S22 counts `usable_closed_records` only for `CLOSED` records that resolve as win or loss

Current values:
- S20: `NO_LIFECYCLE`
- S21: `NO_OUTCOME / NO_LIFECYCLE`
- S22: `usable_closed_records=0`, `edge_status=NO_EDGE_CLAIM`

Son 20 kayıt:
- `OPEN/ACTIVE/CLOSED`: `0/20`
- `NO_LIFECYCLE`: `20/20`
- `NO_OUTCOME`: `20/20`
- `usable_closed_records`: `0` in every one of the last 20 snapshots

Why no usable edge:
- First blocker is S18 never reaching `ALLOW_PAPER`
- Secondary blocker is S20 also requiring a successful paper alert status

Minimum fix candidate:
- First create one clean `ALLOW_PAPER`
- Then verify S19 alert writes `SENT` or `DRY_RUN_READY`

## 8. BOTTLENECK RANKING

| Rank | Bottleneck | Stage | Evidence | Impact | Fix candidate |
|---|---|---|---|---|---|
| 1 | `continuation_quality` enum mismatch crushes confidence | S15 | Live inputs are `STRONG_LONG_PRESSURE + SUSTAINED_LONG_PRESSURE + DQ_OK`, but output is `confidence=0.25`, `NO_TRADE_CONTEXT`; S14 emits `SUSTAINED`, S15 weights do not define it | Prevents `tradeable=true`; kills S16/S17/S18 before any real setup can form | Map `SUSTAINED` and `BUILDING` in S15 confidence weights |
| 2 | Reversal-only model layer is treated as mandatory confirmation | MODEL_REGISTRY + S18 | Last 20 loops: `active_model_count=0` every time; current AR01/DAF/FCR outputs are all inactive during strong continuation | Even after S15 is fixed, continuation setups can still be blocked at S18 | Downgrade `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL` from block to warning unless a model actively vetoes |
| 3 | Depth veto is always present in current live snapshots | S18 | `DEPTH_VETO_SWEEP_RISK_IMMINENT` appears `20/20` in gate history | Can still stop `ALLOW_PAPER` after S15/model fixes | Audit depth memory separately before loosening |
| 4 | Lifecycle requires alert status too | S20 | Code requires both `ALLOW_PAPER` and `alert_status in ("SENT","DRY_RUN_READY")` | Even perfect S18 still will not create a lifecycle if S19 fails | Verify S19 after first `ALLOW_PAPER` |
| 5 | No closed lifecycle history | S21/S22 | `usable_closed_records=0`, `closed_records=0`, `NO_EDGE_CLAIM` | No edge learning possible | This resolves automatically only after the first real lifecycle opens and closes |

Bottleneck classification:
- Real market condition only: not supported by current live evidence
- Threshold too strict: partly, but not the first problem
- Input missing: no
- Field mapping broken: yes, at S15
- Data stale/bayat: likely secondary risk; S15 `candle_close_time` is stale, but current hard fail is already explained by the enum mismatch
- Model registry not counting: CQE is intentionally not counted; AR01/DAF/FCR are truly inactive
- Decision gate too strict: yes, structurally on neutral/no-signal model handling
- Lifecycle condition faulty: secondary only

## 9. RISK ANALİZİ

- Gevşetilmemesi gereken ilk şey S18 RR, trigger, or depth veto thresholds. That would increase fake trade risk immediately.
- Gevşetilmemesi gereken ikinci şey AR01/DAF/FCR thresholds. Those are reversal/trap detectors; making them easier to fire would fabricate model confirmation.
- Güvenli fix: align S15 confidence weighting to the actual S14 enum values. This corrects a mapping error without making the system more aggressive than intended.
- Görece güvenli ikinci fix: downgrade `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL` from hard block to warning when no active reversal model exists. That matches the actual role of the current model set.
- Tehlikeli fix: lowering `confidence < 0.30` and `tradeable >= 0.60` thresholds before fixing the enum mismatch. That would hide the real bug and encourage fake setups.
- Tehlikeli fix: forcing `active_model_count > 0` by counting weak CQE output or loosening reversal models.
- Kesinlikle yapılmamalı: “trade count artırmak için” S17 or S18 null plan fieldsini yeniden doldurmak. That would recreate the exact fake-trade behavior that was just removed.

## 10. FINAL VERDICT

1. İlk `ALLOW_PAPER` neden oluşmuyor?

`ALLOW_PAPER` oluşmuyor because S15 turns a very strong live continuation state into `NO_TRADE_CONTEXT` via a continuation-quality mapping bug, and S18 also hard-blocks any setup when the reversal-only model registry is neutral.

2. İlk kırılan halka hangi stage?

Current first broken link is S15.

3. S15 mi, model_registry mi, S16 mı, S17 mi, S18 mi ana blocker?

Primary live blocker is S15. Primary structural secondary blocker is `MODEL_REGISTRY + S18`.

4. En güvenli ilk patch nedir?

Map S14’s actual `continuation_quality` outputs, especially `SUSTAINED` and `BUILDING`, into S15’s `_CONT_WEIGHTS`.

5. En tehlikeli yanlış patch ne olur?

Lowering entry thresholds or forcing model activity before fixing the S15 mapping bug.

6. İlk `CLOSED_OUTCOME` için minimum ne eksik?

One real chain of `tradeable=true -> READY_FOR_ENTRY -> PLAN_READY -> ALLOW_PAPER`, plus a valid S19 paper alert so that S20 can actually open a lifecycle.

7. Sistem market koşulu olmadığı için mi trade vermiyor, yoksa mantık/threshold hatası yüzünden mi?

Current evidence points to logic/mapping and gating mismatch, not lack of market condition. Live data is strongly directional: `evidence_score=10.0`, `persistence_score=10.0`, `direction_consistency=1.0`.

8. Nova’ya gönderilecek en kritik 10 bilgi nedir?

1. Current live flow is strongly long, not neutral.
2. S15 still outputs `NO_TRADE_CONTEXT` because `confidence=0.25`.
3. That `0.25` comes from an enum mismatch: S14 emits `SUSTAINED`, S15 weights do not know `SUSTAINED`.
4. Last 20 loops produced `tradeable=true` exactly `0` times.
5. Last 20 loops produced `active_model_count>0` exactly `0` times.
6. AR01/DAF/FCR are inactive because current market is continuation, not absorption/divergence/failure.
7. CQE never contributes to `active_model_count` by design.
8. S18 hard-blocks `MODEL_CONSENSUS_NEUTRAL_NO_SIGNAL`, which makes reversal-only models a mandatory confirmer.
9. S20 also requires a successful paper alert status after `ALLOW_PAPER`.
10. No `CLOSED_OUTCOME` and no usable edge can exist until the first real `ALLOW_PAPER` lifecycle is opened and closed.

Final judgment:

The system is not currently failing because it cannot find a market. It is failing because a strong continuation market is being downgraded to `NO_TRADE_CONTEXT` at S15, and because S18 expects positive confirmation from a model layer that only detects reversal/failure conditions.
