# NOVA SIMPLE ROBUST ENGINE v1 — CLAUDE PROJECT MEMORY

## Project Identity

This repository is ONLY for:

NOVA SIMPLE ROBUST ENGINE v1

This is a standalone, paper-only, file-based, testable MVP trading intelligence system.

This repository is NOT for:
- NurNova Final advanced core
- Market Maker Perspective
- Smart Money Perspective
- Perspective Merger
- live trading
- private Binance API
- real order execution

Those systems must remain separate repositories.

## Active Repository

C:\Users\Nurtac\projects\nurnova-workspace\nurnova-simple-robust-engine

## System Goal

Build a working MVP that produces:

- official market truth
- lightweight 1S evidence
- hybrid candle DNA
- quality weight
- liquidity/structure context
- setup candidate
- paper decision
- paper outcome
- edge stats
- simple brain report

Final target files:

state/simple/latest_simple_brain.json
reports/simple/simple_brain_latest_report.md

## Implementation Chain

S0 — Simple Constitution  
S1 — Official Market Truth  
S2 — Lightweight 1S Evidence  
S3 — Hybrid Candle DNA  
S4 — Quality Weight Engine  
S5 — Liquidity + Structure Context  
S6 — Scenario + Setup Candidate  
S7 — Trade Plan + Decision Gate  
S8 — Paper Outcome Tracker  
S9 — Edge Stats  
S10 — Simple Brain Report  

## Critical Architecture Decisions

- Official Binance 1M candle = OHLC truth.
- 1S evidence = internal flow summary only.
- Self-built candle must not override official OHLC truth.
- Missing seconds do not automatically block the system.
- Quality Weight is not a hard gate.
- Small and medium data issues reduce confidence, not stop the system.
- Repair mode only triggers on serious or systemic mismatch.
- Decision blocks only on invalid quality, low RR, unclear direction, invalid stop/target, or missing price.
- S6 produces setup candidate only.
- S7 produces trade plan and paper decision only.
- S8 validates TP/SL outcome with official candle high/low.
- S9 learns only from edge_eligible=true outcomes.
- S10 reports the whole system status and must not create new decisions.
- safe_to_open_real_trade must always be false.

## Required Runtime JSON Contract

Every runtime JSON output must include:

- timestamp_utc
- block_id
- symbol
- source
- data_quality
- reason_codes
- feeds_next

reason_codes must not be empty.

## Allowed Paths

Claude may work only inside:

- src/simple/
- state/simple/
- data/simple/
- reports/simple/
- tests/simple/
- SIMPLE_*.md
- README.md

## Forbidden

Do not create or modify:

- .env
- .env.*
- secrets/**
- credentials
- private API files
- real trading code
- live order execution code
- Market Maker repo code
- Smart Money repo code
- NurNova Final advanced repo code
- Perspective Merger code
- MCP config
- hooks
- Obsidian vault files
- managed agent infrastructure

## Testing Rule

Do not print READY unless:

- python -m compileall src passes
- relevant pytest passes
- relevant fake-sample runner passes
- required output files are created
- JSON contract fields exist
- reason_codes are not empty
- no forbidden files were modified

## Known Critiques Converted Into System Rules

1. Previous systems mixed too many ideas.
   Rule: This repo implements only Simple Robust Engine.

2. Previous systems trusted self-built candles too much.
   Rule: Official Binance 1M candle is OHLC truth.

3. Previous systems degraded too aggressively.
   Rule: Use quality weighting, not panic blocking.

4. Previous systems mixed setup with decision.
   Rule: S6 setup candidate and S7 decision must stay separate.

5. Previous systems risked false outcome learning.
   Rule: S8 validates TP/SL with official candle high/low.

6. Previous systems polluted edge stats.
   Rule: S9 uses only edge_eligible=true trades.

7. Previous systems lacked one clear status report.
   Rule: S10 produces Simple Brain Report.

8. Previous work mixed repos.
   Rule: Simple, Final, Market Maker, Smart Money must stay separate.

## Claude Usage Policy

Use:
- CLAUDE.md memory
- project slash commands
- subagents
- /clear only between completed major blocks
- extended thinking only for planning/audit

Do not use now:
- MCP
- hooks
- Obsidian
- managed agents
- caveman / stack-all unclear modes
- 30-file context dumping

## Current Next Step

Run:

/simple-s0

Then stop and report the result.
