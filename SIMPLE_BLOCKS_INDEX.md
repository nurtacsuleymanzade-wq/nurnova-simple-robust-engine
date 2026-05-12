# SIMPLE BLOCKS INDEX — NOVA SIMPLE ROBUST ENGINE v1

## Block Chain

```
S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9 → S10
```

## Block Definitions

| Block | Name                         | Input                  | Output                        | feeds_next |
|-------|------------------------------|------------------------|-------------------------------|------------|
| S0    | Simple Constitution          | —                      | SIMPLE_*.md, folder structure | S1         |
| S1    | Official Market Truth        | Binance 1M candle      | s1_market_truth.json          | S2         |
| S2    | Lightweight 1S Evidence      | 1S tick feed           | s2_1s_evidence.json           | S3         |
| S3    | Hybrid Candle DNA            | S1 + S2                | s3_candle_dna.json            | S4         |
| S4    | Quality Weight Engine        | S1 + S2 + S3           | s4_quality_weight.json        | S5         |
| S5    | Liquidity + Structure Context| S1 + S4                | s5_liquidity_context.json     | S6         |
| S6    | Scenario + Setup Candidate   | S3 + S4 + S5           | s6_setup_candidate.json       | S7         |
| S7    | Trade Plan + Decision Gate   | S6 + S5 + S4           | s7_trade_plan.json            | S8         |
| S8    | Paper Outcome Tracker        | S7 + official candle   | s8_outcome.json               | S9         |
| S9    | Edge Stats                   | S8 (eligible trades)   | s9_edge_stats.json            | S10        |
| S10   | Simple Brain Report          | S1–S9                  | simple_brain_latest_report.md | TERMINAL   |

## State Files (state/simple/)

- `s1_market_truth.json`
- `s2_1s_evidence.json`
- `s3_candle_dna.json`
- `s4_quality_weight.json`
- `s5_liquidity_context.json`
- `s6_setup_candidate.json`
- `s7_trade_plan.json`
- `s8_outcome.json`
- `s9_edge_stats.json`
- `latest_simple_brain.json`

## Report Files (reports/simple/)

- `simple_brain_latest_report.md`

## Source Modules (src/simple/)

- `s1_market_truth.py`
- `s2_1s_evidence.py`
- `s3_candle_dna.py`
- `s4_quality_weight.py`
- `s5_liquidity_context.py`
- `s6_setup_candidate.py`
- `s7_trade_plan.py`
- `s8_outcome_tracker.py`
- `s9_edge_stats.py`
- `s10_brain_report.py`

## Test Files (tests/simple/)

- `test_s1.py` … `test_s10.py`
- `run_fake_sample.py`

## Key Rules Per Block

**S1** — is_official_binance_1m must be true. No self-built OHLC override.

**S2** — missing_seconds reduces confidence. Does not block the pipeline.

**S3** — dna_open/high/low/close must mirror official S1 OHLC exactly.

**S4** — quality_weight is a float score, not a pass/fail gate. Pipeline continues at any score.

**S5** — structure_bias drives scenario evaluation in S6.

**S6** — produces setup_candidate bool and setup_type. No trade decision here.

**S7** — produces paper_decision. safe_to_open_real_trade = false always.

**S8** — outcome validation_source = "official_candle_high_low" always.

**S9** — filters to edge_eligible=true trades only before computing stats.

**S10** — read-only aggregation. Creates no new decisions. Updates no upstream state.
