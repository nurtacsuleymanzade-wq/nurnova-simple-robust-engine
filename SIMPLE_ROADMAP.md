# SIMPLE ROADMAP — NOVA SIMPLE ROBUST ENGINE v1

## Phase 0 — Constitution (S0)

- [x] Define architecture axioms
- [x] Define runtime JSON contracts
- [x] Define blocks index
- [x] Define acceptance criteria
- [x] Create required folder structure
- [x] Write README

## Phase 1 — Data Layer (S1, S2, S3)

- [ ] S1: Official Market Truth — fetch/load Binance 1M candle
- [ ] S2: Lightweight 1S Evidence — parse 1S tick summary
- [ ] S3: Hybrid Candle DNA — compute candle morphology from official OHLC

## Phase 2 — Quality and Context (S4, S5)

- [ ] S4: Quality Weight Engine — score data quality, produce weight
- [ ] S5: Liquidity + Structure Context — identify support/resistance/bias

## Phase 3 — Setup and Decision (S6, S7)

- [ ] S6: Scenario + Setup Candidate — evaluate setup conditions
- [ ] S7: Trade Plan + Decision Gate — produce paper trade decision

## Phase 4 — Learning Layer (S8, S9)

- [ ] S8: Paper Outcome Tracker — validate TP/SL against official candle
- [ ] S9: Edge Stats — accumulate win rate and RR from eligible trades

## Phase 5 — Report (S10)

- [ ] S10: Simple Brain Report — produce final status report

## Constraints

- Paper only. No live trading. No real order execution.
- safe_to_open_real_trade = false always.
- No mixing with Market Maker, Smart Money, or NurNova Final repos.
- Each phase must pass its acceptance criteria before moving to the next.
