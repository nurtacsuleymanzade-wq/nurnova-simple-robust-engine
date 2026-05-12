# S2 Lightweight 1S Evidence

Implement only this block.

Allowed files:
src/simple/lightweight_1s_evidence_engine.py, src/simple/run_s2_1s_evidence.py, tests/simple/test_lightweight_1s_evidence_engine.py
README.md small section only.

Validation:
python -m compileall src
python -m pytest -q tests/simple/test_lightweight_1s_evidence_engine.py
python -m src.simple.run_s2_1s_evidence --fake-sample --symbol BTCUSDT

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

NUR NOVA SIMPLE S2 READY
