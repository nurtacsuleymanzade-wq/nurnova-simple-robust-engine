# S3 Hybrid Candle DNA

Implement only this block.

Allowed files:
src/simple/hybrid_candle_dna_engine.py, src/simple/run_s3_hybrid_candle_dna.py, tests/simple/test_hybrid_candle_dna_engine.py
README.md small section only.

Validation:
python -m compileall src
python -m pytest -q tests/simple/test_hybrid_candle_dna_engine.py
python -m src.simple.run_s3_hybrid_candle_dna --fake-sample --symbol BTCUSDT

Rules:
- Stay inside this Simple Engine repo.
- Do not create live trading code.
- Do not use private Binance API.
- Do not add Market Maker / Smart Money / NurNova Final code.
- Every runtime JSON must include timestamp_utc, block_id, symbol, source, data_quality, reason_codes, feeds_next.
- reason_codes must not be empty.
- Use fake-sample validation.
- If implementation details are missing, ask user to paste the full block prompt for this block.

Only print this if all acceptance criteria pass:

NUR NOVA SIMPLE S3 READY
