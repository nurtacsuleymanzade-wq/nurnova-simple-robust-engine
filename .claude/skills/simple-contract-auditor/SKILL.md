---
name: simple-contract-auditor
description: Use after every block implementation to verify NOVA SIMPLE runtime JSON contracts and required fields.
---

# Simple Contract Auditor

Audit every generated runtime JSON.

## Required Fields

Each runtime JSON must include:

- timestamp_utc
- block_id
- symbol
- source
- data_quality
- reason_codes
- feeds_next

## Required Rules

- reason_codes must not be empty.
- feeds_next must exist.
- data_quality must be one of:
  - OK
  - ACCEPTABLE
  - USABLE_DEGRADED
  - WEAK_BUT_USABLE
  - REPAIRABLE
  - INVALID

## Special S10 Rule

If S10 output exists:
- safe_to_open_real_trade must be false.

## Audit Output

Report:
- PASS / FAIL
- missing fields
- invalid fields
- files checked
- exact repair recommendation

Do not approve READY if required fields are missing.
