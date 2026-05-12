# SIMPLE ARCHITECTURE — NOVA SIMPLE ROBUST ENGINE v1

## System Identity

This is a standalone, paper-only, file-based, testable MVP trading intelligence system.

It is NOT:
- NurNova Final advanced core
- Market Maker Perspective
- Smart Money Perspective
- Perspective Merger
- Live trading system

## Core Architecture Axioms

### A1 — Official Candle Truth
Official Binance 1M candle = OHLC truth.
Self-built candles may supplement but must never override official OHLC values.

### A2 — 1S Evidence Role
1S data = internal flow summary only.
It informs confidence scoring, not candle construction.

### A3 — Quality Weighting, Not Panic Blocking
Quality Weight is not a hard gate.
Small and medium data issues reduce confidence scores.
The system continues processing at reduced confidence.
Repair mode triggers only on serious or systemic mismatch.

### A4 — Missing Seconds Policy
Missing seconds do not automatically block the system.
They reduce the confidence weight of the affected candle.

### A5 — Setup vs Decision Separation
S6 produces setup candidate only — no trade decision.
S7 produces trade plan and paper decision only — no setup logic.

### A6 — Outcome Validation
S8 must validate TP/SL outcomes using official candle high/low, not estimated price.

### A7 — Edge Learning Filter
S9 learns only from trades where edge_eligible = true.
Trades with edge_eligible = false are excluded from edge statistics.

### A8 — Safe Trade Lock
safe_to_open_real_trade must always be false.
This system is paper-only. No real order execution is permitted.

### A9 — Report Does Not Decide
S10 produces Simple Brain Report only.
S10 must not create new decisions or modify state.

## Folder Structure

```
src/simple/        — implementation modules (S0-S10)
state/simple/      — runtime JSON state files
data/simple/       — input data (candles, 1S feed)
reports/simple/    — output reports
tests/simple/      — test runners and fake sample scripts
```

## Final Output Targets

- `state/simple/latest_simple_brain.json`
- `reports/simple/simple_brain_latest_report.md`

## Block Chain

S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9 → S10

Each block feeds the next. No block may skip a predecessor.
