Implement S0 Simple Constitution only.

Allowed files:
- SIMPLE_ARCHITECTURE.md
- SIMPLE_CONTRACTS.md
- SIMPLE_ROADMAP.md
- SIMPLE_BLOCKS_INDEX.md
- SIMPLE_ACCEPTANCE_CRITERIA.md
- README.md
- src/simple/
- state/simple/
- data/simple/
- reports/simple/
- tests/simple/

Rules:
- Do not write engine code.
- Do not create S1-S10 implementation files.
- Do not use private API.
- Do not create live trading code.

S0 must define:
- Official Binance 1M candle = OHLC truth.
- 1S evidence = internal flow summary only.
- Quality Weight is not hard gate.
- Missing seconds reduce confidence, not automatically block.
- Outcome must use official candle high/low.
- Edge uses only edge_eligible=true trades.
- safe_to_open_real_trade always false.

Validate:
- Required SIMPLE_*.md files exist.
- Required folders exist.

Only print this if all acceptance criteria pass:

NUR NOVA SIMPLE S0 READY
