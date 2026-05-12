---
name: simple-block-builder
description: Use when implementing any S0-S10 block of NOVA SIMPLE ROBUST ENGINE v1. It defines the safe block implementation workflow.
---

# Simple Block Builder

Use this skill for S0-S10 implementation.

## Block Workflow

For every block:

1. Read CLAUDE.md.
2. Identify active block: S0, S1, S2, ..., S10.
3. Use only the allowed files for that block.
4. Do not touch unrelated files.
5. Implement deterministic fake-sample support.
6. Write tests.
7. Run validation.
8. Only print READY if all acceptance criteria pass.

## Required Validation

Always run:

python -m compileall src

Then run the relevant pytest:

python -m pytest -q tests/simple/<test_file>.py

Then run the relevant fake-sample runner:

python -m src.simple.<runner> --fake-sample --symbol BTCUSDT

## READY Rule

Never print READY if:
- compileall fails
- pytest fails
- runner fails
- required output files are missing
- reason_codes are empty
- required JSON contract fields are missing
- forbidden files were modified

## Block Critique Mapping

S0 fixes: missing constitution / scope creep.
S1 fixes: official truth missing.
S2 fixes: over-heavy sub-second footprint.
S3 fixes: self-built candle over-trust.
S4 fixes: panic DEGRADED behavior.
S5 fixes: premature SMC complexity.
S6 fixes: setup/decision mixing.
S7 fixes: hard gate / poor RR decision.
S8 fixes: false outcome learning.
S9 fixes: polluted edge statistics.
S10 fixes: no single brain/status report.

## Stop Rule

After finishing one block, stop and report.
Do not automatically proceed to the next block unless the user explicitly asks.
