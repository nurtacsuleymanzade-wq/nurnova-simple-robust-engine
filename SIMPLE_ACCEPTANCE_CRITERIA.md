# SIMPLE ACCEPTANCE CRITERIA — NOVA SIMPLE ROBUST ENGINE v1

## Global Criteria (apply to every block)

| # | Criterion                                                        | Pass Condition                              |
|---|------------------------------------------------------------------|---------------------------------------------|
| G1| python -m compileall src passes                                  | Zero compile errors                         |
| G2| pytest tests/simple/ passes                                      | Zero test failures                          |
| G3| Fake sample runner produces output files                         | Required output files exist after run       |
| G4| JSON contract fields present                                     | All required fields exist in output JSON    |
| G5| reason_codes not empty                                           | List has at least one string entry          |
| G6| No forbidden files modified                                      | .env, secrets, private API files untouched  |
| G7| safe_to_open_real_trade = false                                  | Field present and value is false            |

## S0 — Simple Constitution

| # | Criterion                            | Pass Condition                                    |
|---|--------------------------------------|---------------------------------------------------|
| S0-1 | SIMPLE_ARCHITECTURE.md exists    | File present at repo root                         |
| S0-2 | SIMPLE_CONTRACTS.md exists       | File present at repo root                         |
| S0-3 | SIMPLE_ROADMAP.md exists         | File present at repo root                         |
| S0-4 | SIMPLE_BLOCKS_INDEX.md exists    | File present at repo root                         |
| S0-5 | SIMPLE_ACCEPTANCE_CRITERIA.md exists | File present at repo root                     |
| S0-6 | src/simple/ folder exists        | Directory present                                 |
| S0-7 | state/simple/ folder exists      | Directory present                                 |
| S0-8 | data/simple/ folder exists       | Directory present                                 |
| S0-9 | reports/simple/ folder exists    | Directory present                                 |
| S0-10| tests/simple/ folder exists      | Directory present                                 |

## S1 — Official Market Truth

| # | Criterion                                    | Pass Condition                         |
|---|----------------------------------------------|----------------------------------------|
| S1-1 | is_official_binance_1m = true           | Field present and true                 |
| S1-2 | OHLC values are floats > 0              | candle_open/high/low/close all > 0     |
| S1-3 | candle_high >= candle_open, close       | High is the highest value              |
| S1-4 | candle_low <= candle_open, close        | Low is the lowest value                |
| S1-5 | candle_timestamp_ms is int              | Valid millisecond timestamp            |

## S2 — Lightweight 1S Evidence

| # | Criterion                                          | Pass Condition                    |
|---|----------------------------------------------------|-----------------------------------|
| S2-1 | missing_seconds reduces confidence, not blocks | confidence_adjusted = true if missing_seconds > 0 |
| S2-2 | buy_pressure + sell_pressure <= 1.0            | Sum constraint satisfied           |
| S2-3 | tick_count >= 0                                | Non-negative integer               |

## S3 — Hybrid Candle DNA

| # | Criterion                                            | Pass Condition                          |
|---|------------------------------------------------------|-----------------------------------------|
| S3-1 | dna OHLC mirrors S1 official OHLC exactly       | dna_open == s1.candle_open, etc.        |
| S3-2 | body_ratio + wick_upper_ratio + wick_lower_ratio approx 1.0 | Ratios sum to ~1.0         |
| S3-3 | candle_type is a non-empty string               | e.g. "bullish_marubozu", "doji"         |

## S4 — Quality Weight Engine

| # | Criterion                                    | Pass Condition                              |
|---|----------------------------------------------|---------------------------------------------|
| S4-1 | quality_weight is float 0.0–1.0         | In range                                    |
| S4-2 | Pipeline does not stop at any score     | feeds_next is set regardless of quality     |
| S4-3 | quality_level matches score ranges      | HIGH >= 0.8, MEDIUM >= 0.5, LOW >= 0.2     |

## S5 — Liquidity + Structure Context

| # | Criterion                              | Pass Condition                                    |
|---|----------------------------------------|---------------------------------------------------|
| S5-1 | structure_bias is valid string    | "bullish", "bearish", or "neutral"                |
| S5-2 | liquidity_notes is a list         | May be empty list                                 |

## S6 — Scenario + Setup Candidate

| # | Criterion                                | Pass Condition                                  |
|---|------------------------------------------|-------------------------------------------------|
| S6-1 | setup_candidate is bool             | True or False                                   |
| S6-2 | No trade decision produced          | paper_decision field absent from S6 output      |

## S7 — Trade Plan + Decision Gate

| # | Criterion                                        | Pass Condition                            |
|---|--------------------------------------------------|-------------------------------------------|
| S7-1 | paper_decision is valid enum              | "LONG", "SHORT", or "NO_TRADE"            |
| S7-2 | safe_to_open_real_trade = false           | Always false                              |
| S7-3 | NO_TRADE when: invalid quality, low RR, unclear direction, invalid stop/target, missing price | block_reason set |

## S8 — Paper Outcome Tracker

| # | Criterion                                      | Pass Condition                                  |
|---|------------------------------------------------|-------------------------------------------------|
| S8-1 | validation_source = "official_candle_high_low" | Exact string match                         |
| S8-2 | outcome is valid enum                     | "TP_HIT", "SL_HIT", "PENDING", "EXPIRED", "NO_TRADE" |
| S8-3 | edge_eligible is bool                     | True or False                                   |

## S9 — Edge Stats

| # | Criterion                                          | Pass Condition                         |
|---|----------------------------------------------------|----------------------------------------|
| S9-1 | Only edge_eligible=true trades counted        | edge_eligible_count matches filter     |
| S9-2 | win_rate = win_count / edge_eligible_count    | Correct calculation or null if 0       |

## S10 — Simple Brain Report

| # | Criterion                                          | Pass Condition                              |
|---|----------------------------------------------------|---------------------------------------------|
| S10-1 | report file created at reports/simple/        | simple_brain_latest_report.md exists        |
| S10-2 | latest_simple_brain.json created at state/simple/ | File exists with all required fields   |
| S10-3 | safe_to_open_real_trade = false               | Always false                                |
| S10-4 | No new decisions created                      | S10 output contains no paper_decision field |
| S10-5 | No upstream state modified                    | S1–S9 state files unchanged after S10 run  |

## READY Gate

Print `NUR NOVA SIMPLE S0 READY` only if all S0-1 through S0-10 criteria pass.
Do not print READY for any subsequent block unless all G1–G7 global criteria also pass.
