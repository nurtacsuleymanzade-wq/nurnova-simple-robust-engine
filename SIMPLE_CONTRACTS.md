# SIMPLE CONTRACTS — NOVA SIMPLE ROBUST ENGINE v1

## Runtime JSON Contract

Every runtime JSON output produced by any block (S1–S10) must include these fields:

| Field           | Type   | Description                                      |
|-----------------|--------|--------------------------------------------------|
| timestamp_utc   | string | ISO 8601 UTC timestamp of block execution        |
| block_id        | string | Identifier of the block (e.g. "S1", "S7")        |
| symbol          | string | Trading pair (e.g. "BTCUSDT")                    |
| source          | string | Data source identifier (e.g. "binance_1m")       |
| data_quality    | object | Quality assessment of input data                 |
| reason_codes    | list   | Non-empty list of string reason codes            |
| feeds_next      | string | Block ID this output feeds (or "TERMINAL")       |

`reason_codes` must never be an empty list.

## data_quality Object Contract

```json
{
  "score": 0.0,
  "level": "HIGH | MEDIUM | LOW | CRITICAL",
  "issues": []
}
```

- score: float 0.0–1.0
- level: one of HIGH, MEDIUM, LOW, CRITICAL
- issues: list of issue strings (may be empty if no issues)

## Block-Specific Contracts

### S1 — Official Market Truth
Required additional fields:
- candle_open, candle_high, candle_low, candle_close (float)
- candle_volume (float)
- candle_timestamp_ms (int)
- is_official_binance_1m (bool, must be true)

### S2 — Lightweight 1S Evidence
Required additional fields:
- tick_count (int)
- buy_pressure (float 0.0–1.0)
- sell_pressure (float 0.0–1.0)
- missing_seconds (int)
- confidence_adjusted (bool)

### S3 — Hybrid Candle DNA
Required additional fields:
- dna_open, dna_high, dna_low, dna_close (float, mirrors official OHLC)
- body_ratio (float)
- wick_upper_ratio (float)
- wick_lower_ratio (float)
- candle_type (string)

### S4 — Quality Weight Engine
Required additional fields:
- quality_weight (float 0.0–1.0)
- quality_passed (bool)
- quality_level (string)

### S5 — Liquidity + Structure Context
Required additional fields:
- nearest_support (float or null)
- nearest_resistance (float or null)
- structure_bias (string: "bullish" | "bearish" | "neutral")
- liquidity_notes (list of strings)

### S6 — Scenario + Setup Candidate
Required additional fields:
- setup_candidate (bool)
- setup_type (string or null)
- scenario_notes (list of strings)

### S7 — Trade Plan + Decision Gate
Required additional fields:
- paper_decision (string: "LONG" | "SHORT" | "NO_TRADE")
- entry_price (float or null)
- stop_loss (float or null)
- take_profit (float or null)
- risk_reward_ratio (float or null)
- safe_to_open_real_trade (bool, must always be false)
- block_reason (string or null)

### S8 — Paper Outcome Tracker
Required additional fields:
- outcome (string: "TP_HIT" | "SL_HIT" | "PENDING" | "EXPIRED" | "NO_TRADE")
- validation_source (string: "official_candle_high_low")
- edge_eligible (bool)
- pnl_pct (float or null)

### S9 — Edge Stats
Required additional fields:
- edge_eligible_count (int)
- win_count (int)
- loss_count (int)
- win_rate (float or null)
- avg_rr_realized (float or null)
- edge_score (float or null)

### S10 — Simple Brain Report
Required additional fields:
- report_path (string)
- system_health (string: "OK" | "DEGRADED" | "CRITICAL")
- safe_to_open_real_trade (bool, must always be false)

## Invariants

1. safe_to_open_real_trade is always false. No exceptions.
2. reason_codes is never an empty list.
3. S8 outcome validation source is always "official_candle_high_low".
4. S9 edge stats use only edge_eligible=true trades.
5. S10 does not create new decisions or modify upstream state.
