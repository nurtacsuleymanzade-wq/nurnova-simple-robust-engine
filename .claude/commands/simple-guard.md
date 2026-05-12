Guard check.

Verify:
- changed files are inside allowed paths
- forbidden files were not touched
- no private API was added
- no live trading code was added
- runtime JSON files have required contract fields
- S10 safe_to_open_real_trade is false if S10 exists

Report pass/fail.
Do not modify files.
