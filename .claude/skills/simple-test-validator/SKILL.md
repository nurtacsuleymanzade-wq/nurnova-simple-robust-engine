---
name: simple-test-validator
description: Use to run compileall, pytest, fake-sample runners, and final validation for NOVA SIMPLE ROBUST ENGINE v1.
---

# Simple Test Validator

Use this skill whenever validation is needed.

## Per-Block Validation

Run:

python -m compileall src

Run relevant pytest:

python -m pytest -q tests/simple/<test_file>.py

Run relevant runner:

python -m src.simple.<runner> --fake-sample --symbol BTCUSDT

## Full Validation

Run:

python -m compileall src
python -m pytest -q tests/simple

Then run S1-S10 fake-sample runners in order:

python -m src.simple.run_s1_market_truth --fake-sample --symbol BTCUSDT
python -m src.simple.run_s2_1s_evidence --fake-sample --symbol BTCUSDT
python -m src.simple.run_s3_hybrid_candle_dna --fake-sample --symbol BTCUSDT
python -m src.simple.run_s4_quality_weight --fake-sample --symbol BTCUSDT
python -m src.simple.run_s5_liquidity_structure --fake-sample --symbol BTCUSDT
python -m src.simple.run_s6_setup_candidate --fake-sample --symbol BTCUSDT
python -m src.simple.run_s7_trade_plan_decision --fake-sample --symbol BTCUSDT
python -m src.simple.run_s8_paper_outcome --fake-sample --symbol BTCUSDT
python -m src.simple.run_s9_edge_stats --fake-sample --symbol BTCUSDT
python -m src.simple.run_s10_simple_brain --fake-sample --symbol BTCUSDT

## Final Required Files

Check:
- state/simple/latest_market_truth.json
- state/simple/latest_1s_evidence.json
- state/simple/latest_hybrid_candle_dna.json
- state/simple/latest_quality_weight.json
- state/simple/latest_liquidity_structure.json
- state/simple/latest_setup_candidate.json
- state/simple/latest_decision.json
- state/simple/latest_outcome.json
- state/simple/latest_edge_stats.json
- state/simple/latest_simple_brain.json
- reports/simple/simple_brain_latest_report.md

## Output

Report:
- commands run
- pass/fail
- generated files
- errors if any
- next safe action
