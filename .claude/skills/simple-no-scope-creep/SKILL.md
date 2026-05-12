---
name: simple-no-scope-creep
description: Use whenever Claude may be tempted to add extra modules, live trading, private APIs, MCP, hooks, Market Maker, Smart Money, or NurNova Final code into the Simple repo.
---

# Simple No Scope Creep

This repository implements only NOVA SIMPLE ROBUST ENGINE v1.

## Hard Stops

Do not add:
- live trading
- real order execution
- private Binance API
- account balance access
- Market Maker Perspective
- Smart Money Perspective
- NurNova Final advanced core
- Perspective Merger
- MCP
- hooks
- Obsidian
- managed agents
- dashboard UI
- database migration
- over-engineered services

## Current Target

Only build:

S0-S10 Simple Robust Engine.

## If User Asks For More

If the user asks for Market Maker, Smart Money, Final Core, Admin Layer, or live trading:
- say it belongs to a separate repo or later phase
- do not implement it in this repo
- keep Simple repo clean

## Output Rule

Always prefer:
- simplest working file-based MVP
- fake-sample validation
- paper-only output
- clear JSON contracts
