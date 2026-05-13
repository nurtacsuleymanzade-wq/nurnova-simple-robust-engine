# NOVA EDGE LOOP AUDIT

Audit date: 2026-05-13  
Repo: `nurnova-simple-robust-engine`  
Mode: read-only audit, no code changes

## Executive Summary

Bu repo 30 saniyelik loop ile veri ve çok sayıda ara state üretiyor, fakat aktif zincir gerçek edge öğrenimine ulaşmıyor. Kırılma noktası tek bir yerde değil; zincir aynı anda üç farklı problem yüzünden kopuyor:

1. Aktif S15→S22 zinciri, eski S6/S7/S8/S9 zinciriyle yan yana yaşıyor ve state katmanında legacy/fake sample dosyaları bırakıyor.
2. Aktif trade zinciri setup identity, setup family ve model lineage taşımıyor; bu yüzden lifecycle ve edge öğrenimi setup/model bazlı bağ kuramıyor.
3. S20 paper lifecycle fiilen hiç başlamıyor; sonuç olarak S21 sürekli `NO_LIFECYCLE`, S22 sürekli `NO_EDGE_CLAIM` üretiyor.

Bu haliyle sistem bir “edge loop” değil, bir “snapshot/report loop”. Veri var, bağlanmış ve kapanan trade yok; kapanan trade yoksa outcome yok; outcome yoksa edge yok.

---

## 1. Repo Dosya Haritası

### Ana yapı

- `src/`: 98 Python dosyası
- `tests/`: 51 Python test dosyası
- `state/`: 80 state dosyası
- `data/`: 39 data/history dosyası
- `logs/`: 1 log dosyası
- `reports/`: stage report markdown çıktıları
- `exports/`: legacy/export veri setleri
- `run_loop.py`: repo root loop runner
- `src/simple/run_loop.py`: ikinci loop runner
- `src/simple/local_pipeline_runner.py`: gerçek pipeline orchestrator
- `src/simple/run_local_full_pipeline.py`: pipeline wrapper

### `src/simple/` kritik dosyalar

- Aktif zincir:
  - `flow_to_setup_context_engine.py`
  - `scenario_entry_trigger_engine.py`
  - `trade_plan_engine.py`
  - `decision_gate_engine.py`
  - `telegram_paper_alert_engine.py`
  - `paper_lifecycle_tracker.py`
  - `outcome_monitor.py`
  - `edge_matrix_v2.py`
  - `model_registry.py`
- Legacy zincir:
  - `setup_candidate_engine.py`
  - `trade_plan_decision_engine.py`
  - `paper_outcome_tracker.py`
  - `edge_stats_engine.py`
- Ek model katmanı:
  - `absorption_reversal_engine.py`
  - `delta_absorption_failure_engine.py`
  - `failed_continuation_reversal_engine.py`
  - `candle_quality_engine.py`
- Ayrı sınıflandırma/araştırma hattı:
  - `setup_classifier_v2.py`
  - `sample_accumulation_edge_review.py`

### `state/simple/` kritik dosyalar

- Aktif zincir latest state:
  - `latest_setup_context.json`
  - `latest_scenario_trigger.json`
  - `latest_trade_plan.json`
  - `latest_decision_gate.json`
  - `latest_paper_lifecycle.json`
  - `latest_outcome_monitor.json`
  - `latest_edge_matrix_v2.json`
  - `latest_model_registry.json`
- Legacy state halen mevcut:
  - `latest_decision.json`
  - `latest_outcome.json`
  - `latest_edge_stats.json`
- Pipeline summary:
  - `latest_local_pipeline_run.json`

### `data/simple/` kritik history dosyaları

- Aktif zincir:
  - `setup_context_history.jsonl`
  - `scenario_trigger_history.jsonl`
  - `trade_plan_history.jsonl`
  - `decision_gate_history.jsonl`
  - `paper_lifecycle_history.jsonl`
  - `outcome_monitor_history.jsonl`
  - `edge_matrix_v2_history.jsonl`
  - `model_registry_history.jsonl`
- Legacy/yan hat:
  - `paper_outcome.jsonl`
  - `trade_plan_decision.jsonl`

### `logs/`

- `logs/simple/production_observer.log`

### `docs/`

- Audit öncesi `docs/` klasörü yoktu.

### Runner / loop / scheduler / service dosyaları

- `run_loop.py`
- `src/simple/run_loop.py`
- `src/simple/local_pipeline_runner.py`
- `src/simple/run_local_full_pipeline.py`
- `src/simple/replay_sample_runner.py`
- `src/simple/production_observer.py`
- `src/simple/vps_observer.py`
- `src/simple/vps_health_monitor.py`
- `src/simple/live_ws_runtime.py`

### Pattern arama sonucu

- `S15/S16/S17/S18/S20/S22`: aktif zincirde mevcut
- `setup_family`: sadece `setup_classifier_v2.py` ve `sample_accumulation_edge_review.py` tarafında var
- `model_id`: aktif zincirde bulunmadı
- `lifecycle_id`: S20/S21/testlerde var
- `NO_SETUP`: legacy S6/S7 hattında kuvvetli şekilde var
- `NO_LIFECYCLE`: aktif S20/S21/S22 hattında yoğun şekilde var

---

## 2. 30 Saniyelik Loop’un Gerçek Çalışma Zinciri

### Ana loop giriş noktası

30 saniyelik loop iki ayrı dosyada var:

- `run_loop.py`
- `src/simple/run_loop.py`

İkisi de `subprocess.run([sys.executable, "-m", "src.simple.run_local_full_pipeline"])` çağırıyor. Gerçek stage zincirini başlatan fonksiyon:

- `src/simple/local_pipeline_runner.py`
- Fonksiyon: `run_pipeline(symbol: str, source_mode: str = "LIVE")`

### Stage sırası

`local_pipeline_runner.py` içindeki `_STAGES` sırası:

1. S1 market truth
2. S2 1s evidence
3. S3 hybrid candle DNA
4. S4 quality weight
5. S5 liquidity structure
6. S6 setup candidate
7. S27 depth liquidity memory
8. S27B wall lifecycle
9. S13 flow evidence
10. S14 flow persistence
11. S15 flow to setup context
12. AR01
13. DAF
14. FCR
15. CQE
16. MODEL_REGISTRY
17. S16 scenario trigger
18. S17 trade plan
19. S18 decision gate
20. S20 paper lifecycle
21. S21 outcome monitor
22. S22 edge matrix
23. S10 simple brain report

### Producer → Output → Consumer

| Producer | Output file | Consumer | Note |
|---|---|---|---|
| `context_sync_engine.py` | `state/simple/latest_context_sync.json` | `local_pipeline_runner`, S17, S18, S20 | `context_id` taşır |
| `run_s1_market_truth.py` | `state/simple/latest_market_truth.json` | CQE, S17 | |
| `run_s2_1s_evidence.py` | `state/simple/latest_1s_evidence.json` | S3, S6 | |
| `run_s3_hybrid_candle_dna.py` | `state/simple/latest_hybrid_candle_dna.json` | S6 | |
| `quality_weight_engine.py` | `state/simple/latest_quality_weight.json` | S6 | |
| `liquidity_structure_engine.py` | `state/simple/latest_liquidity_structure.json` | S6 | |
| `setup_candidate_engine.py` | `state/simple/latest_setup_candidate.json` | S20 only | Active S17/S18 zincirine gitmiyor, partial orphan |
| `run_s27_depth_liquidity_memory.py` | `state/simple/latest_depth_liquidity_memory.json` | S17, S18, S20 | |
| `run_s27b_wall_lifecycle.py` | `state/simple/latest_wall_lifecycle.json` | S18, S20 | |
| `flow_evidence_engine.py` | `state/simple/latest_flow_evidence.json` | S15, AR01, DAF, CQE, S17, S18 | |
| `flow_persistence_engine.py` | `state/simple/latest_flow_persistence.json` | S15, DAF, FCR, S16, S17, S18 | |
| `flow_to_setup_context_engine.py` | `state/simple/latest_setup_context.json` | S16, S17, S18, S21 snapshot | Aktif setup kaynağı |
| `absorption_reversal_engine.py` | `state/simple/latest_ar01.json` | MODEL_REGISTRY | |
| `delta_absorption_failure_engine.py` | `state/simple/latest_daf.json` | MODEL_REGISTRY | |
| `failed_continuation_reversal_engine.py` | `state/simple/latest_fcr.json` | MODEL_REGISTRY | |
| `candle_quality_engine.py` | `state/simple/latest_cqe.json` | MODEL_REGISTRY | |
| `model_registry.py` | `state/simple/latest_model_registry.json` | S16, S18, `src/simple/run_loop.py` | Root `run_loop.py` okumuyor |
| `scenario_entry_trigger_engine.py` | `state/simple/latest_scenario_trigger.json` | S17, S18, S20, S21 snapshot | |
| `trade_plan_engine.py` | `state/simple/latest_trade_plan.json` | S18, S19, S20, S21 snapshot, run loops | |
| `decision_gate_engine.py` | `state/simple/latest_decision_gate.json` | S19, S20, S21 snapshot | |
| `telegram_paper_alert_engine.py` | `state/simple/latest_telegram_paper_alert.json` | S20 | |
| `paper_lifecycle_tracker.py` | `state/simple/latest_paper_lifecycle.json` | S21, followup notifier | |
| `outcome_monitor.py` | `state/simple/latest_outcome_monitor.json` | S22 | |
| `edge_matrix_v2.py` | `state/simple/latest_edge_matrix_v2.json` | `simple_brain_v2.py` | Operator loop edge satırında kullanılmıyor |
| `simple_brain_report_engine.py` | `state/simple/latest_simple_brain.json` | terminal/reporting | |

### Orphan outputlar

- `state/simple/latest_setup_candidate.json`
  - Active S15→S22 zincirinde setup gating için kullanılmıyor.
  - S20 bunu sadece lineage snapshot için okuyor.
- `state/simple/latest_decision.json`
  - Legacy S7 çıktısı.
  - Aktif zincir okumuyor.
- `state/simple/latest_outcome.json`
  - Legacy S8 çıktısı.
  - Aktif zincir okumuyor.
- `state/simple/latest_edge_stats.json`
  - Legacy S9 çıktısı.
  - Aktif öğrenme zinciri değil, ama loop özetinde hâlâ okunuyor.

### Missing inputlar

- `setup_family`, `setup_id`, `model_id`
  - Aktif S15→S22 zinciri boyunca üretilmiyor.
  - S22 bu alanlarla edge öğrenemez.
- `closed_outcomes_with_lineage.jsonl`
  - S21 yalnız `outcome_status == CLOSED` olduğunda append ediyor.
  - Mevcut canlı akışta closed outcome yok; dosya pratikte boş/işlevsiz.

---

## 3. Blok Durum Analizi

## S15_FLOW_TO_SETUP_CONTEXT

File: `src/simple/flow_to_setup_context_engine.py`  
Input: `latest_flow_state.json`, `latest_flow_evidence.json`, `latest_flow_persistence.json`  
Output: `state/simple/latest_setup_context.json`  
Reads: S13 + S14  
Writes: setup context + history  
Key fields:

- `setup_context_label`
- `setup_context_score`
- `direction_bias`
- `confidence`
- `tradeable`
- `probability_summary`
- `data_quality`

Status logic:

- Ayrı `status` alanı yok.
- Pratik status `setup_context_label` ve `tradeable` ile okunuyor.

Failure/degraded reasons:

- `confidence < 0.30` ise `NO_TRADE_CONTEXT`
- `decay_risk` veya `flip_risk` varsa `NO_TRADE_CONTEXT`
- `combined_dq_score < 0.6` ise `data_quality.level = LOW`

Consumers:

- S16, S17, S18, S21 snapshot

Risk:

- Burada `direction_bias = LONG/SHORT` korunurken `tradeable = false` olabilir.
- Bu çift durum S16/S17’de trade yönü üretmeye devam ediyor.

## DAF_DELTA_ABSORPTION_FAILURE

File: `src/simple/delta_absorption_failure_engine.py`  
Input: `latest_flow_evidence.json`, `latest_flow_persistence.json`  
Output: `state/simple/latest_daf.json`  
Reads: S13 + S14  
Writes: DAF state + history  
Key fields:

- `delta_divergence`
- `divergence_score`
- `aggressive_side_failed`
- `reversal_bias`
- `failure_strength`
- `timeframe`
- `candle_close_time`

Status logic:

- Ayrı `status` alanı yok.
- Pipeline tarafında `data_quality.level = LOW` ise `DEGRADED`.

Failure/degraded reasons:

- DQ skoru S13/S14 ortalamasından geliyor.
- Son state: `delta_divergence = false`, ama `data_quality.level = LOW`, bu yüzden pipeline `DEGRADED`.

Consumers:

- MODEL_REGISTRY

Risk:

- Signal yokken bile low DQ nedeniyle degraded.
- `data_quality` burada availability değil semantic certainty ölçüyor; operator tarafında “engine bozuk” gibi görünebilir.

## S16_SCENARIO_ENTRY_TRIGGER

File: `src/simple/scenario_entry_trigger_engine.py`  
Input: `latest_setup_context.json`, `latest_flow_state.json`, `latest_flow_evidence.json`, `latest_flow_persistence.json`, `latest_model_registry.json`  
Output: `state/simple/latest_scenario_trigger.json`  
Reads: S15 + S13 + S14 + MODEL_REGISTRY  
Writes: scenario trigger + history  
Key fields:

- `scenario_label`
- `direction_bias`
- `trigger_state`
- `trigger_strength`
- `ready_for_entry`
- `model_integration`
- `timeframe`
- `candle_close_time`

Status logic:

- Ayrı `status` alanı yok.
- Operasyonel status `trigger_state`.

Failure/degraded reasons:

- Upstream `data_quality` olduğu gibi taşınıyor.
- Current state: `setup_context_label = NO_TRADE_CONTEXT` olmasına rağmen `scenario_label = BREAKOUT_ATTEMPT`.

Consumers:

- S17, S18, S20, S21 snapshot

Risk:

- Kodda `BREAKOUT_ATTEMPT` kuralı `evidence_label` ve `setup_score` üzerinden çalışıyor; `NO_TRADE_CONTEXT` bunu engellemiyor.
- Bu, zincirin ilk mantık kırılması.

## S17_TRADE_PLAN_ENGINE

File: `src/simple/trade_plan_engine.py`  
Input: `latest_scenario_trigger.json`, `latest_setup_context.json`, `latest_flow_state.json`, `latest_flow_evidence.json`, `latest_flow_persistence.json`, `latest_market_truth.json`, `latest_model_registry.json`, `latest_depth_liquidity_memory.json`, `latest_context_sync.json`  
Output: `state/simple/latest_trade_plan.json`  
Reads: S16 merkezli; S15/S13/S14/S1/context/depth/model destek  
Writes: trade plan + history  
Key fields:

- `plan_status`
- `side`
- `entry_price`
- `stop_loss`
- `tp1`, `tp2`
- `rr_tp1`, `rr_tp2`
- `model_veto`
- `timeframe`
- `candle_close_time`

Status logic:

- `NO_PLAN`
- `WATCH_ONLY`
- `PLAN_READY`
- `INVALID`

Failure/degraded reasons:

- `dq_level not in ("OK","HIGH")` ise `WATCH_ONLY`, ama yine de entry/sl/tp üretir
- `ready_for_entry == false` ise `WATCH_ONLY`, ama yine de entry/sl/tp üretir
- Model ters yönde ve güçlü ise `INVALID`

Consumers:

- S18, S19, S20, S21 snapshot, loop summary

Risk:

- “No setup / weak trigger / low quality” durumunda bile numerik trade plan üretiyor.
- Bu, ekranda “plan var” yanılsaması yaratıyor.

## S18_DECISION_GATE

File: `src/simple/decision_gate_engine.py`  
Input: `latest_trade_plan.json`, `latest_scenario_trigger.json`, `latest_setup_context.json`, `latest_flow_state.json`, `latest_flow_evidence.json`, `latest_flow_persistence.json`, `latest_model_registry.json`, `latest_depth_liquidity_memory.json`, `latest_wall_lifecycle.json`, `latest_context_sync.json`  
Output: `state/simple/latest_decision_gate.json`  
Reads: S17 merkezli  
Writes: decision gate + history  
Key fields:

- `decision`
- `decision_status`
- `block_reasons`
- `warning_reasons`
- `selected_side`
- `selected_entry`
- `allowed_for_paper_lifecycle`
- `gate_checks`

Status logic:

- `ALLOW_PAPER`
- `WATCH`
- `BLOCK`

Failure/degraded reasons:

- `dq_level = LOW` yalnız warning
- `rr below threshold` yalnız warning
- `plan_status != PLAN_READY` warning
- `depth_veto` block
- `model_veto` block

Consumers:

- S19, S20, S21 snapshot

Risk:

- Gate gerçek enforcement yapıyor.
- Ama S6 `NO_SETUP` veya missing setup lineage hakkında hiçbir fikri yok.

## S20_PAPER_LIFECYCLE_TRACKER

File: `src/simple/paper_lifecycle_tracker.py`  
Input: `latest_decision_gate.json`, `latest_trade_plan.json`, `latest_telegram_paper_alert.json`, `latest_flow_state.json`, prior `latest_paper_lifecycle.json`, `latest_context_sync.json`, `latest_scenario_trigger.json`, `latest_setup_candidate.json`, `latest_depth_liquidity_memory.json`, `latest_wall_lifecycle.json`  
Output: `state/simple/latest_paper_lifecycle.json`  
Reads: S18 + S19  
Writes: lifecycle + history  
Key fields:

- `lifecycle_id`
- `lifecycle_status`
- `entry_touched`
- `tp1_hit`
- `tp2_hit`
- `stop_hit`
- `max_favorable_excursion_r`
- `max_adverse_excursion_r`
- `lineage`

Status logic:

- `NO_LIFECYCLE`
- `NOT_STARTED`
- `OPEN`
- `ACTIVE`
- `TP1_HIT`
- `TP2_HIT`
- `SL_HIT`
- `INVALIDATED`

Failure/degraded reasons:

- `decision != ALLOW_PAPER` veya alert blocked/skipped ise doğrudan `_no_lifecycle()`
- Current state: `DECISION_NOT_ALLOWED_FOR_PAPER`

Consumers:

- S21

Risk:

- Lifecycle continuity kodu var, ama hiç başlatılamadığı için pratikte ölü.
- `setup_candidate` okunuyor ama sadece lineage kırıntısı için; aktif setup zinciri ile tutarlı değil.

## S22_EDGE_MATRIX_V2

File: `src/simple/edge_matrix_v2.py`  
Input: `data/simple/outcome_monitor_history.jsonl`, `state/simple/latest_outcome_monitor.json`  
Output: `state/simple/latest_edge_matrix_v2.json`  
Reads: S21 geçmişi  
Writes: edge matrix + history  
Key fields:

- `sample_summary`
- `overall_stats`
- `by_setup_context`
- `by_scenario_label`
- `by_decision`
- `by_setup_grade`
- `edge_quality`

Status logic:

- `sample_status`
- `edge_status`

Failure/degraded reasons:

- `usable_closed_records = 0` ise `NO_EDGE_CLAIM`
- Current state: `total_records=161`, `no_lifecycle_records=161`, `usable_closed_records=0`

Consumers:

- `simple_brain_v2.py`

Risk:

- `setup_family` ve `model_id` ile gruplayamıyor.
- Operator loop bu dosyayı edge satırında bile kullanmıyor; legacy `latest_edge_stats.json` okunuyor.

---

## 4. Screenshot’taki Çelişkilerin Kaynağı

### 1. Pipeline COMPLETE ama birçok blok DEGRADED

- Dosya: `src/simple/local_pipeline_runner.py`
- Fonksiyon: `_classify_status`, `run_pipeline`
- Kod özeti:
  - `pipeline_status = "COMPLETE"` default
  - Sadece kritik exception olursa stop eder
  - `data_quality.level in ("LOW","CRITICAL","INVALID")` ise block `DEGRADED`
- Sebep:
  - “COMPLETE” çalışma tamamlandı demek; “PASSED” kalite yüksek demek değil.
- Minimum düzeltme noktası:
  - Pipeline summary’de `complete_with_degraded` ayrımı yapılmalı.

### 2. Bloklar 24/23 PASSED görünüyor. Bu sayı nasıl oluşuyor?

- Dosya: `src/simple/local_pipeline_runner.py`
- Fonksiyon: `run_pipeline`
- Kod özeti:
  - `blocks_total = len(_STAGES)` = 23
  - Ama S0 context sync `blocks_passed` sayısına ekleniyor
- Sebep:
  - S0 sayılıyor, ama total’e dahil değil.
- Minimum düzeltme noktası:
  - Ya `blocks_total += 1`, ya da S0 ayrı gösterilmeli.

### 3. Setup = NO_SETUP / UNKNOWN ama Plan = SHORT/LONG entry/sl/tp üretiyor

- Dosya: `src/simple/trade_plan_engine.py`
- Fonksiyon: `compute_trade_plan`
- Kod özeti:
  - `dq low` ise `WATCH_ONLY` ama entry/sl/tp hesapla
  - `ready_for_entry false` ise yine entry/sl/tp hesapla
- Sebep:
  - Plan readiness ile plan geometry birbirinden ayrılmış; sistem “actionable trade” ile “indicative levels”i aynı JSON’da taşıyor.
- Minimum düzeltme noktası:
  - `WATCH_ONLY` veya upstream `tradeable=false` ise numeric plan alanları null olmalı veya ayrı preview alanlarına taşınmalı.

### 4. CONSENSUS=NEUTRAL L=50% S=50% ama SHORT/LONG plan oluşuyor

- Dosya: `src/simple/trade_plan_engine.py`
- Fonksiyon: `compute_trade_plan`
- Kod özeti:
  - `side`, `scenario_trigger.direction_bias` üzerinden geliyor
  - Model neutral ise veto yok, block yok
- Sebep:
  - Model registry sadece veto/override katmanı; primary direction S16’dan geliyor.
- Minimum düzeltme noktası:
  - Model neutral iken trade readiness en azından `WATCH_ONLY` zorlamalı.

### 5. Model = CONSENSUS=NEUTRAL signals=0 candle=WEAK_DOJI ama trade plan SHORT/LONG

- Dosya: `src/simple/model_registry.py`, `src/simple/trade_plan_engine.py`
- Sebep:
  - Model katmanı “no opinion” verdiğinde trade katmanı bağımsız çalışmaya devam ediyor.
- Minimum düzeltme noktası:
  - Neutral/no-signal model durumunda explicit downgrade veya no-trade policy gerekir.

### 6. Paper = NO_LIFECYCLE ama plan var

- Dosya: `src/simple/paper_lifecycle_tracker.py`
- Fonksiyon: `_allowed_for_lifecycle`, `compute_paper_lifecycle`
- Kod özeti:
  - S20 sadece `decision == ALLOW_PAPER` ve `alert_status in ("SENT","DRY_RUN_READY")` ise lifecycle açıyor
- Sebep:
  - Plan var olmak lifecycle açmaya yetmiyor.
- Minimum düzeltme noktası:
  - Operator özetinde “plan exists but not lifecycle-eligible” açık yazılmalı.

### 7. Edge = DEGRADED. Bunun gerçek nedeni ne?

- Dosya: `src/simple/edge_matrix_v2.py`
- Fonksiyon: `build_edge_matrix`
- Kod özeti:
  - `usable_closed_records = 0`
  - `edge_status = NO_EDGE_CLAIM`
- Sebep:
  - 161 kaydın tamamı `NO_LIFECYCLE`.
- Minimum düzeltme noktası:
  - Önce S20/S21 gerçek kapanan trade üretmeli.

### 8. DATA_QUALITY HIGH skor=1.0 olmasına rağmen DAF ve setup zinciri neden DEGRADED?

- Dosya: `src/simple/model_registry.py`, `src/simple/flow_to_setup_context_engine.py`, `src/simple/delta_absorption_failure_engine.py`
- Sebep:
  - `MODEL_REGISTRY.data_quality = 1.0` yalnız model output availability ölçüyor.
  - S15 ve DAF kendi semantic quality skorlarını kullanıyor.
- Minimum düzeltme noktası:
  - `data_quality` sözleşmesi availability vs semantic confidence olarak ayrılmalı.

### 9. S18_DECISION_GATE gerçekten gate gibi mi çalışıyor, yoksa sadece rapor mu yazıyor?

- Dosya: `src/simple/decision_gate_engine.py`
- Fonksiyon: `compute_decision_gate`
- Kod özeti:
  - `decision == BLOCK` ise selected entry/SL/TP null oluyor
  - `allowed_for_paper_lifecycle = decision == ALLOW_PAPER`
- Sebep:
  - Gate gerçek enforcement yapıyor.
- Minimum düzeltme noktası:
  - Yok; asıl sorun gate öncesi plan/state kirliliği.

### 10. S22_EDGE_MATRIX_V2 hangi outcome verisini okuyor, gerçekten model/setup bazlı edge hesaplıyor mu?

- Dosya: `src/simple/edge_matrix_v2.py`
- Fonksiyon: `load_outcome_records`, `_classify_record`, `build_edge_matrix`
- Kod özeti:
  - `data/simple/outcome_monitor_history.jsonl` okuyor
  - Gruplama: `setup_context_label`, `scenario_label`, `decision`, `setup_grade`, `liquidity_bias`, `wall_conclusion`
- Sebep:
  - `setup_family` ve `model_id` active records içinde yok; bu yüzden model/setup family edge yok.
- Minimum düzeltme noktası:
  - Lifecycle/outcome zincirine `setup_family`, `setup_id`, `model_id` taşınmalı.

---

## 5. Setup / Model / Family Zinciri

### Alan taraması

| Field | Active chain? | Nerede var | Durum |
|---|---|---|---|
| `setup_id` | Hayır | active chain’de yok | Missing |
| `setup_family` | Hayır | `setup_classifier_v2.py`, `sample_accumulation_edge_review.py` | Active chain’e bağlı değil |
| `model_id` | Hayır | active chain’de yok | Missing |
| `model_name` | Kısmen | MODEL_REGISTRY active signal içinde `model` | Downstream taşınmıyor |
| `signal_family` | Hayır | active chain’de yok | Missing |
| `candidate_id` | Hayır | active chain’de yok | Missing |
| `lifecycle_id` | Evet | S20/S21 | Mevcut loop’ta sürekli `null` |
| `context_id` | Evet | S0, S17, S18, S20 lineage | Taşınıyor |
| `reason_codes` | Evet | tüm aktif bloklarda | Var |
| `entry/sl/tp/rr` | Evet | S17, S18 snapshot, S20 | Var |
| `outcome` | Evet | S21, S22 | Ama `NO_LIFECYCLE` |

### Taşıma tablosu

| Stage | Carrier file | setup_id | setup_family | model_id | lifecycle_id | context_id | entry/sl/tp | outcome |
|---|---|---|---|---|---|---|---|---|
| Setup candidate | `latest_setup_candidate.json` | No | No | No | No | No | No | No |
| Trade plan | `latest_trade_plan.json` | No | No | No | No | Yes | Yes | No |
| Decision gate | `latest_decision_gate.json` | No | No | No | No | Yes | Selected refs only | No |
| Paper lifecycle | `latest_paper_lifecycle.json` | No | No | No | Yes but current `null` | Yes | Yes when open | No |
| Outcome monitor | `latest_outcome_monitor.json` | No | No | No | Yes but current `null` | Lineage snapshot only | Snapshot only | Yes |
| Edge matrix | `latest_edge_matrix_v2.json` | No | No | No | Aggregated | No | Aggregated only | Yes |

### Kırılan zincir

İstenen zincir:

`setup_candidate -> trade_plan_history -> decision_gate -> paper_lifecycle_history -> outcome_monitor -> edge_matrix_v2`

Gerçekte olan:

- `setup_candidate` active trade plan’e bağlanmıyor
- trade plan `setup_family/model_id/setup_id` taşımıyor
- paper lifecycle bu alanları alamıyor
- outcome monitor yalnız snapshot ve eksik lineage taşıyor
- edge matrix setup/model family bazlı öğrenemiyor

Sonuç: identity continuity yok.

---

## 6. Lifecycle Continuity Analizi

### Mevcut gerçek durum

- Açık trade var mı?
  - Son state’te hayır.
- OPEN trade bir sonraki loop’ta takip ediliyor mu?
  - Kod bunu destekliyor.
  - Pratikte lifecycle hiç başlamadığı için çalışmıyor.
- Aynı setup her loop’ta yeniden mi doğuyor?
  - Evet, çünkü persistent `setup_id` yok.
- `lifecycle_id` nasıl üretiliyor?
  - `sha1(ts|symbol|side|entry)[:16]`
- `lifecycle_id = None` sebebi?
  - `_no_lifecycle()` path’i.
  - Ana neden: `decision != ALLOW_PAPER`.
- TP/SL takibi hangi dosyada?
  - `paper_lifecycle_tracker.py`
- MAE/MFE takip ediliyor mu?
  - Kodda evet.
  - Pratikte açık lifecycle olmadığı için anlamlı veri yok.
- Trade CLOSED olunca nereye yazılıyor?
  - S21 `outcome_monitor_history.jsonl` ve closed ise `closed_outcomes_with_lineage.jsonl`
- Outcome edge matrix’e gidiyor mu?
  - Evet, ama current records `NO_LIFECYCLE`.

### Kopuk halka

S18 `ALLOW_PAPER` üretmeden S20 başlamıyor. S20 başlamadan S21 closed outcome üretemiyor. S21 closed outcome üretmeden S22 edge öğrenemiyor.

### Minimum düzeltme yeri

- Öncelik S17/S18 değil, onlardan önce identity ve lifecycle eligibility kontratları.
- Trade preview ile trade lifecycle birbirinden ayrılmalı.

---

## 7. Decision Gate Denetimi

### ALLOW koşulları

S18 `ALLOW_PAPER` için hepsi gerekli:

- `plan_status == PLAN_READY`
- directional side
- price logic valid
- rr valid
- rr thresholds valid
- data quality valid
- trigger ready
- safety valid
- reason codes present

### BLOCK koşulları

- trade plan missing
- plan invalid
- model veto
- depth veto
- price logic contradiction
- invalid/missing data quality

### WATCH koşulları

- Plan directional ama tam hazır değilse
- RR eşik altıysa
- DQ low ise
- Trigger ready değilse

### Sorulara kısa cevap

- `NO_SETUP` varken trade izin veriyor mu?
  - Active zincirde S6 `NO_SETUP` hiç okunmuyor.
  - Dolayısıyla fonksiyonel olarak evet, S6 `NO_SETUP` S18’i bloklamaz.
- `CONSENSUS=NEUTRAL` iken trade izin veriyor mu?
  - Evet. Sadece `NO_MODEL_SIGNAL` warning ekleniyor.
- `RR < minimum` ise blokluyor mu?
  - Hayır. `WATCH` veya upstream `WATCH_ONLY`.
- `data_quality = LOW/DEGRADED` ise blokluyor mu?
  - LOW ise genelde `WATCH`; INVALID/MISSING ise `BLOCK`.
- lifecycle yoksa blokluyor mu?
  - Hayır. lifecycle S18’in input’u değil.
- `setup_family/model_id` yoksa blokluyor mu?
  - Hayır; böyle check yok.

### Verdict

S18 enforcement yapıyor, ama setup identity veya edge lineage’i enforce etmiyor.

**DECISION GATE IS ENFORCING**, fakat **setup/identity integrity’yi enforce etmiyor**.

---

## 8. Edge Matrix Denetimi

### Okuduğu dosyalar

- `data/simple/outcome_monitor_history.jsonl`
- `state/simple/latest_outcome_monitor.json`

### Outcome kaynağı

- S21 `outcome_monitor.py`

### Paper lifecycle ile bağlı mı?

- Evet, S21 lifecycle’den outcome üretmeye çalışıyor.
- Fakat lifecycle `NO_LIFECYCLE` olduğu için edge girdisi boş kalıyor.

### Setup/model bazlı gruplama yapabiliyor mu?

- `setup_context_label`: evet
- `scenario_label`: evet
- `decision`: evet
- `setup_grade`: kısmen, ama current records `UNKNOWN`
- `setup_family`: hayır
- `model_id`: hayır

### Winrate/expectancy/MAE/MFE hesaplıyor mu?

- Kod seviyesinde evet.
- Mevcut veriyle hayır; usable closed sample yok.

### Required Field Tablosu

| Required Field | Exists? | Source | Missing Point |
|---|---|---|---|
| `outcome_status=CLOSED` | No | S21 | S20 lifecycle açılmıyor |
| `realized_r` | No live sample | S21 | Closed outcome yok |
| `mfe_r/mae_r` | Teknik olarak var | S20/S21 | Yaşayan lifecycle yok |
| `setup_family` | No | S29 only | Active chain taşımıyor |
| `model_id` | No | none | Üretilmiyor |
| `setup_id` | No | none | Üretilmiyor |
| `lifecycle_id` | Current `null` | S20 | `_no_lifecycle()` |
| `decision` | Yes | S18 snapshot | Var |
| `scenario_label` | Yes | S16 snapshot | Var |

### Edge neden DEGRADED?

- Gerçek neden: `NO_USABLE_CLOSED_RECORDS`
- Yan neden: lineage alanları eksik

---

## 9. Data Quality / DEGRADED Analizi

### Nerelerde DEGRADED set ediliyor?

- Pipeline tarafında: `local_pipeline_runner._classify_status()`
- Bir blok `data_quality.level in ("LOW","CRITICAL","INVALID")` ise `DEGRADED`

### Kritik anomali

- `MISSING` seviyesi `DEGRADED` sayılmıyor.
- Bu yüzden:
  - S20 `NO_LIFECYCLE` çıktısı pipeline’da `PASSED`
  - S21 `NO_OUTCOME` çıktısı pipeline’da `PASSED`

Bu, operatör için yanıltıcı.

### DATA_QUALITY HIGH olup downstream neden DEGRADED?

- Çünkü her blok kendi DQ mantığını kuruyor.
- `MODEL_REGISTRY` availability-based high.
- S15/S16/S17 semantic low.

### DEGRADED gate kararını etkiliyor mu?

- Dolaylı etkiliyor.
- S17/S18 LOW quality’de ALLOW vermiyor, ama her zaman BLOCK da etmiyor.
- Sonuç: sistem plan üretmeye devam ediyor, lifecycle üretmiyor.

---

## 10. Çıktı Şemaları: Son Örnekler

### Latest setup candidate

```json
{
  "block_id": "S6_SCENARIO_SETUP_CANDIDATE",
  "setup_candidate": {
    "setup_type": "RANGE_REACTION",
    "setup_direction": "NEUTRAL",
    "setup_grade": "WATCH",
    "setup_status": "WATCH_SETUP"
  },
  "feeds_next": {"next_blocks": ["S7_TRADE_PLAN_DECISION_GATE"]}
}
```

Analiz:

- Var: setup grade/status
- Eksik: `setup_id`, `setup_family`, `candidate_id`
- Kritik eksik: active S17/S18 chain bunu kullanmıyor

### Latest trade plan

```json
{
  "block_id": "S17_TRADE_PLAN_ENGINE",
  "plan_status": "WATCH_ONLY",
  "side": "LONG",
  "entry_price": 81162.41,
  "stop_loss": 80718.523,
  "tp1": 81828.2405,
  "tp2": 82272.1275,
  "model_veto": false
}
```

Analiz:

- Var: entry/sl/tp/rr
- Eksik: `setup_id`, `setup_family`, `model_id`
- Downstream için kritik: numerik plan var ama identity yok

### Latest decision gate

```json
{
  "block_id": "S18_DECISION_GATE",
  "decision": "BLOCK",
  "block_reasons": ["DEPTH_VETO_SWEEP_RISK_IMMINENT"],
  "warning_reasons": ["NO_MODEL_SIGNAL", "DATA_QUALITY_LOW", "TRIGGER_NOT_READY_WEAK_TRIGGER"]
}
```

Analiz:

- Gate çalışıyor
- Eksik: setup/model lineage check

### Latest paper lifecycle

```json
{
  "block_id": "S20_PAPER_LIFECYCLE_TRACKER",
  "lifecycle_id": null,
  "lifecycle_status": "NO_LIFECYCLE",
  "data_quality": {"level": "MISSING", "issues": ["DECISION_NOT_ALLOWED_FOR_PAPER"]}
}
```

Analiz:

- Edge öğrenimi için yetersiz
- Kapalı trade zinciri başlamıyor

### Latest outcome monitor

```json
{
  "block_id": "S21_OUTCOME_MONITOR",
  "outcome_status": "NO_OUTCOME",
  "outcome_result": "NO_LIFECYCLE",
  "trade_plan_snapshot": {"plan_status": "WATCH_ONLY", "side": "LONG"}
}
```

Analiz:

- Snapshot var
- Outcome yok
- Öğrenme verisi değil

### Latest edge matrix

```json
{
  "block_id": "S22_EDGE_MATRIX_V2",
  "sample_summary": {
    "total_records": 161,
    "closed_records": 0,
    "no_lifecycle_records": 161,
    "usable_closed_records": 0
  },
  "edge_quality": {
    "edge_status": "NO_EDGE_CLAIM",
    "caution_reason": "NO_CLOSED_RESOLVED_SAMPLES"
  }
}
```

Analiz:

- Matematik çalışıyor
- Veri yok
- Edge öğrenimine yetmiyor

### Latest model registry

```json
{
  "block_id": "MODEL_REGISTRY",
  "timeframe": "1m",
  "active_model_count": 0,
  "consensus_direction": "NEUTRAL",
  "candle_quality": "WEAK_DOJI"
}
```

Analiz:

- Timeframe var
- Model lineage var ama downstream kimlik olarak taşınmıyor

### Legacy state örnekleri

- `latest_decision.json`: `S7_TRADE_PLAN_DECISION_GATE`, source `FAKE_SAMPLE`
- `latest_outcome.json`: `S8_PAPER_OUTCOME_TRACKER`, source `FAKE_SAMPLE`
- `latest_edge_stats.json`: `S9_EDGE_STATS`, source `FAKE_SAMPLE`

Bu dosyalar mevcut repo gerçekliğinde state pollution yaratıyor.

---

## 11. Edge’ye Yaklaşmama Kök Nedeni

### Root Cause #1

Evidence:

- S15 `NO_TRADE_CONTEXT`
- S16 yine `BREAKOUT_ATTEMPT`
- S17 yine entry/sl/tp üretir

Impact:

- “No trade context” ile “trade preview” aynı loop içinde birlikte yaşıyor.

Minimum Fix:

- S16/S17’de `tradeable=false` veya `setup_context_label=NO_TRADE_CONTEXT` ise actionable plan zinciri kesilmeli.

### Root Cause #2

Evidence:

- Active chain’de `setup_id`, `setup_family`, `model_id` yok.
- `setup_family` sadece S29 hattında var.

Impact:

- Edge matrix setup/model bazlı öğrenemiyor.

Minimum Fix:

- Identity alanları S15/S16/S17/S20/S21/S22 zincirine taşınmalı.

### Root Cause #3

Evidence:

- S20 yalnız `ALLOW_PAPER + DRY_RUN_READY/SENT` ile lifecycle açıyor.
- Current state’te `lifecycle_id = null`, `NO_LIFECYCLE`
- S22’de `usable_closed_records = 0`

Impact:

- Outcome ve edge öğrenimi fiilen hiç başlamıyor.

Minimum Fix:

- S20 lifecycle creation kontratı ve preview/eligibility ayrımı netleştirilmeli.

### Root Cause #4

Evidence:

- `latest_setup_candidate.json` active plan zincirinde kullanılmıyor.
- `latest_decision.json`, `latest_outcome.json`, `latest_edge_stats.json` legacy fake sample dosyaları hâlâ mevcut.
- Loop edge satırı legacy `latest_edge_stats.json` okuyor.

Impact:

- Operatör aynı anda iki farklı sistemin state’ini görüyor.

Minimum Fix:

- Active ve legacy state/readers ayrılmalı; loop yalnız active zinciri göstermeli.

### Root Cause #5

Evidence:

- Pipeline `_classify_status` sadece `LOW/CRITICAL/INVALID` seviyelerini degraded sayıyor.
- `NO_LIFECYCLE` ve `NO_OUTCOME` `MISSING` olduğu halde pipeline’da `PASSED`.

Impact:

- Sistem health özeti gerçeği olduğundan daha iyi gösteriyor.

Minimum Fix:

- `MISSING` downstream öğrenme bloklarında degraded sayılmalı.

---

## 12. Minimum Patch Plan

Kod yazmıyorum; yalnız hedefli patch planı:

### Patch 1

Target file: `src/simple/scenario_entry_trigger_engine.py`  
Why: `NO_TRADE_CONTEXT` iken breakout senaryosu oluşuyor  
Change summary: `setup_context_label in ("NO_TRADE_CONTEXT","INSUFFICIENT_CONTEXT")` ise breakout/continuation üretimini bastır  
Expected output: `NO_SCENARIO` ve `NO_TRIGGER`  
Risk: Mevcut agresif preview sayısı düşer

### Patch 2

Target file: `src/simple/trade_plan_engine.py`  
Why: `WATCH_ONLY` durumda actionable fiyat seviyeleri üretiliyor  
Change summary: preview alanları ile actionable plan alanlarını ayır; `WATCH_ONLY` için `entry_price/stop_loss/tp*` null veya `preview_*` alanlarına taşı  
Expected output: Plan varmış gibi görünme sorunu biter  
Risk: mevcut UI/summary okuyucuları güncellenmeli

### Patch 3

Target file: `src/simple/decision_gate_engine.py`  
Why: S6 `NO_SETUP`, model neutral ve missing lineage gate tarafından enforce edilmiyor  
Change summary: `setup_family/setup_id/model_id` yoksa `WATCH` veya `BLOCK`; neutral consensus için stricter policy  
Expected output: identity’siz trade ALLOW olamaz  
Risk: kısa vadede ALLOW sayısı çok düşer

### Patch 4

Target file: `src/simple/setup_candidate_engine.py`, `src/simple/flow_to_setup_context_engine.py`, `src/simple/scenario_entry_trigger_engine.py`, `src/simple/trade_plan_engine.py`, `src/simple/paper_lifecycle_tracker.py`, `src/simple/outcome_monitor.py`  
Why: zincirde identity yok  
Change summary: `setup_id`, `setup_family`, `candidate_id`, `model_refs` taşı  
Expected output: setup→plan→lifecycle→outcome bağlanır  
Risk: sözleşme güncellemesi gerekir

### Patch 5

Target file: `src/simple/paper_lifecycle_tracker.py`  
Why: lifecycle continuity kağıt üstünde var, pratikte ölü  
Change summary: lifecycle eligibility ile preview planını ayır; aynı setup için persistent key kullan  
Expected output: `lifecycle_id` tekrar tekrar `null` olmaz  
Risk: state migration gerekir

### Patch 6

Target file: `src/simple/outcome_monitor.py`, `src/simple/edge_matrix_v2.py`  
Why: setup/model bazlı edge yok  
Change summary: outcome record içine `setup_id`, `setup_family`, `model_id`, `model_consensus`, `candidate_id` yaz; S22 bunlarla grupla  
Expected output: gerçek edge slicing başlar  
Risk: eski history kayıtları mixed schema olur

### Patch 7

Target file: `src/simple/local_pipeline_runner.py`  
Why: `24/23 PASSED` ve `NO_LIFECYCLE` rağmen pass sorunu  
Change summary: S0 ayrı say, `MISSING` seviyesini de lifecycle/outcome/edge için degraded kabul et  
Expected output: pipeline health gerçekçi görünür  
Risk: daha fazla degraded satırı çıkar

### Patch 8

Target file: `run_loop.py`, `src/simple/run_loop.py`  
Why: operator loop active S22 yerine legacy S9 edge stats okuyor  
Change summary: edge satırını `latest_edge_matrix_v2.json` üzerinden oku; legacy state göstermeyi bırak  
Expected output: terminal summary gerçek active zinciri yansıtır  
Risk: eski alışkanlıkla kıyaslanan metrikler değişir

---

## 13. Audit Sonu Özeti

## FINAL VERDICT

- Sistem şu an: gerçek zamanlı state üreten, ama persistent trade-learning loop kuramayan hibrit bir snapshot pipeline.
- Edge’ye yaklaşmamasının tek cümlelik sebebi: kapanan ve kimliği korunmuş trade lifecycle üretilmediği için outcome’dan edge’e geçecek öğrenme verisi oluşmuyor.
- İlk düzeltilmesi gereken dosya: `src/simple/trade_plan_engine.py`
- İlk patch: `WATCH_ONLY` ve `NO_TRADE_CONTEXT` durumunda actionable fiyat seviyelerini üretmeyi kesmek
- İkinci patch: setup/model identity alanlarını S15→S22 zincirine taşımak

Nova’ya gönderilecek en kritik 10 bilgi:

1. Aktif trade zinciri S6 setup candidate’i gate için kullanmıyor.
2. `NO_TRADE_CONTEXT` iken S16 yine `BREAKOUT_ATTEMPT` üretebiliyor.
3. S17 `WATCH_ONLY` olsa bile entry/sl/tp üretiyor.
4. S18 gerçek gate, ama setup identity gate değil.
5. S20 yalnız `ALLOW_PAPER` durumunda lifecycle açıyor; current loop’ta hiç açılmıyor.
6. S21 bu yüzden sürekli `NO_LIFECYCLE`.
7. S22 bu yüzden `usable_closed_records = 0`, `NO_EDGE_CLAIM`.
8. `setup_id/setup_family/model_id` active zincirde yok.
9. Legacy fake sample dosyaları state katmanında hâlâ mevcut ve operator özetini kirletiyor.
10. Pipeline health sayacı ve degraded sınıflandırması operatöre gerçeği eksik gösteriyor.

---

## 14. Komut Çıktıları Özeti

Not: Ortam Windows olduğu için istenen `find`/`grep` komutlarının eşdeğeri olarak `Get-ChildItem` ve `rg` kullanıldı.

### `find . -maxdepth 4 -type f | sort` eşdeğeri özeti

Öne çıkan sonuçlar:

- Root:
  - `run_loop.py`
  - `README.md`
  - `SIMPLE_ARCHITECTURE.md`
- Active state:
  - `state/simple/latest_setup_context.json`
  - `state/simple/latest_scenario_trigger.json`
  - `state/simple/latest_trade_plan.json`
  - `state/simple/latest_decision_gate.json`
  - `state/simple/latest_paper_lifecycle.json`
  - `state/simple/latest_outcome_monitor.json`
  - `state/simple/latest_edge_matrix_v2.json`
- Legacy state:
  - `state/simple/latest_decision.json`
  - `state/simple/latest_outcome.json`
  - `state/simple/latest_edge_stats.json`
- Active data history:
  - `data/simple/trade_plan_history.jsonl`
  - `data/simple/decision_gate_history.jsonl`
  - `data/simple/paper_lifecycle_history.jsonl`
  - `data/simple/outcome_monitor_history.jsonl`
  - `data/simple/edge_matrix_v2_history.jsonl`

### Grep öne çıkan satırlar

```text
src/simple/local_pipeline_runner.py:45: ("src.simple.flow_to_setup_context_engine",   "NOARG",           "S15_FLOW_TO_SETUP_CONTEXT"),
src/simple/local_pipeline_runner.py:48: ("src.simple.delta_absorption_failure_engine","NOARG",           "DAF_DELTA_ABSORPTION_FAILURE"),
src/simple/local_pipeline_runner.py:53: ("src.simple.scenario_entry_trigger_engine",  "NOARG",           "S16_SCENARIO_ENTRY_TRIGGER"),
src/simple/local_pipeline_runner.py:54: ("src.simple.trade_plan_engine",              "NOARG",           "S17_TRADE_PLAN"),
src/simple/local_pipeline_runner.py:55: ("src.simple.decision_gate_engine",           "NOARG",           "S18_DECISION_GATE"),
src/simple/local_pipeline_runner.py:57: ("src.simple.paper_lifecycle_tracker",        "NOARG",           "S20_PAPER_LIFECYCLE"),
src/simple/local_pipeline_runner.py:59: ("src.simple.edge_matrix_v2",                 "NOARG",           "S22_EDGE_MATRIX"),

src/simple/flow_to_setup_context_engine.py:90: if persistence_label == "NO_VALID_FLOW": return "NO_TRADE_CONTEXT"
src/simple/flow_to_setup_context_engine.py:99: if confidence < 0.30: return "NO_TRADE_CONTEXT"

src/simple/scenario_entry_trigger_engine.py:71: if evidence_label == "STRONG_LONG_PRESSURE" ... return "BREAKOUT_ATTEMPT"
src/simple/scenario_entry_trigger_engine.py:90: if setup_label == "NO_TRADE_CONTEXT": return "NO_SCENARIO"
src/simple/scenario_entry_trigger_engine.py:378: if model_override: scenario_label = f"MODEL_{direction_bias}_OVERRIDE"

src/simple/trade_plan_engine.py:256: elif dq_level not in ("OK", "HIGH"): plan_status = "WATCH_ONLY"
src/simple/trade_plan_engine.py:259: entry_price = round(ref_price, 4)
src/simple/trade_plan_engine.py:278: elif not ready_for_entry or trigger_state != "READY_FOR_ENTRY": plan_status = "WATCH_ONLY"
src/simple/trade_plan_engine.py:281: entry_price = round(ref_price, 4)

src/simple/decision_gate_engine.py:93: warning_reasons.append("NO_MODEL_SIGNAL")
src/simple/decision_gate_engine.py:200: if model_veto: decision = "BLOCK"
src/simple/decision_gate_engine.py:220: decision = "ALLOW_PAPER"
src/simple/decision_gate_engine.py:223: decision = "WATCH"

src/simple/paper_lifecycle_tracker.py:91: return decision == "ALLOW_PAPER" and alert_status in ("SENT", "DRY_RUN_READY")
src/simple/paper_lifecycle_tracker.py:131: "lifecycle_id": None
src/simple/paper_lifecycle_tracker.py:132: "lifecycle_status": "NO_LIFECYCLE"

src/simple/outcome_monitor.py:260: if lifecycle_status == "NO_LIFECYCLE" or lifecycle_id is None:
src/simple/outcome_monitor.py:262: "NO_LIFECYCLE_PRESENT"

src/simple/edge_matrix_v2.py:20: OUTCOME_HISTORY_PATH = DATA_DIR / "outcome_monitor_history.jsonl"
src/simple/edge_matrix_v2.py:147: setup_grade = str(lineage.get("source_setup_grade") or "UNKNOWN")
src/simple/edge_matrix_v2.py:295: status = "NO_EDGE_CLAIM"

src/simple/setup_classifier_v2.py:721: "setup_family": setup_family if setup_status != "INSUFFICIENT_DATA" else "UNKNOWN"
src/simple/setup_classifier_v2.py:709: "next_blocks": ["S17_TRADE_PLAN_ENGINE", "S18_DECISION_GATE"]
```

---

## 15. Çalıştırma Sonu

Bu audit kapsamında yalnızca `docs/NOVA_EDGE_LOOP_AUDIT.md` oluşturuldu. Kod dosyaları değiştirilmedi.
