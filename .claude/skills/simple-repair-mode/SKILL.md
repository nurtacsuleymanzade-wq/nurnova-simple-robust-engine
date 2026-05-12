---
name: simple-repair-mode
description: Use when a NOVA SIMPLE block fails tests, runner validation, JSON contract audit, or file generation.
---

# Simple Repair Mode

Use this skill only after a failure.

## Repair Rules

1. Do not rewrite unrelated files.
2. Do not expand scope.
3. Fix the smallest failing unit.
4. Preserve existing contracts.
5. Re-run the failing command.
6. Re-run full block validation.
7. Do not print READY until fixed.

## Repair Diagnosis

For every failure, identify:

- failing command
- failing file
- failing function or schema
- exact reason
- minimal patch
- validation result

## Forbidden During Repair

Do not:
- create new architecture
- add live trading
- add private API
- add Market Maker / Smart Money / Final code
- modify unrelated block files
- skip tests

## Output

Report:
- root cause
- files changed
- tests re-run
- result
- next action
