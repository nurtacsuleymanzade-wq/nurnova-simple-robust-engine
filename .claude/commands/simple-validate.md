Run full Simple Engine validation.

Commands:
python -m compileall src
python -m pytest -q tests/simple

Then run:
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

Check required files:
state/simple/latest_market_truth.json
state/simple/latest_1s_evidence.json
state/simple/latest_hybrid_candle_dna.json
state/simple/latest_quality_weight.json
state/simple/latest_liquidity_structure.json
state/simple/latest_setup_candidate.json
state/simple/latest_decision.json
state/simple/latest_outcome.json
state/simple/latest_edge_stats.json
state/simple/latest_simple_brain.json
reports/simple/simple_brain_latest_report.md

Confirm safe_to_open_real_trade is false in S10 if present.
