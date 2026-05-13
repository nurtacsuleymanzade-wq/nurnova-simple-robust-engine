# CANONICAL DNA FACTORY POWERSHELL CLEANUP REPORT

Timestamp: 2026-05-13T02:59:25.830501Z
Target: src\simple\mtf_candle_dna_factory.py

## Duplicate Definitions Found

### constant: `ATR_STATE_PATH`
- REMOVE_SHADOWED: lines 27-27
- KEEP_LAST: lines 28-28

### function: `_apply_atr_state`
- REMOVE_SHADOWED: lines 138-166
- KEEP_LAST: lines 210-236


## Cleanup Rule

For duplicate top-level functions/constants, earlier shadowed definitions were removed and the last active Python definition was preserved.
This preserves current runtime behavior while removing merge-drift ambiguity.

## Removed Ranges

- Removed shadowed constant `ATR_STATE_PATH` at lines 27-27
- Removed shadowed function `_apply_atr_state` at lines 138-166