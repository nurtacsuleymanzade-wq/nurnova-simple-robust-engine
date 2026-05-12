"""S11 Replay Sample Runner — NOVA SIMPLE ROBUST ENGINE v1.

Runs the S1→S10 pipeline logic repeatedly with deterministic synthetic
scenarios and accumulates structured research samples. Research only.
Does not change S1-S10 logic, send real orders, or use private API.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

BLOCK_ID = "S11_REPLAY_SAMPLE_RUNNER"
FEEDS_NEXT = {"next_blocks": ["S11_1_LOCAL_PIPELINE_RUNNER"]}

DEFAULT_SEED = 42
_BASE_PRICE = 105000.0

_CANDLE_DIRECTIONS = ["BULLISH", "BEARISH", "DOJI"]
_EVIDENCE_LABELS = ["LONG_PRESSURE", "SHORT_PRESSURE", "NEUTRAL"]
_STRUCTURE_BIASES = ["bullish", "bearish", "neutral"]
_SETUP_TYPES_LONG = ["LONG_CONTINUATION", "LONG_REVERSAL", "LONG_BREAKOUT"]
_SETUP_TYPES_SHORT = ["SHORT_CONTINUATION", "SHORT_REVERSAL", "SHORT_BREAKDOWN"]
_SETUP_GRADES = ["A", "B", "C"]

_GRADE_WIN_PROB = {"A": 0.62, "B": 0.50, "C": 0.38}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_scenario(rng: random.Random, sample_id: int, symbol: str, seed: int) -> dict[str, Any]:
    candle_dir = rng.choice(_CANDLE_DIRECTIONS)
    evidence = rng.choice(_EVIDENCE_LABELS)
    quality = round(rng.uniform(0.4, 1.0), 4)
    structure = rng.choice(_STRUCTURE_BIASES)

    bullish = sum([candle_dir == "BULLISH", evidence == "LONG_PRESSURE", structure == "bullish"])
    bearish = sum([candle_dir == "BEARISH", evidence == "SHORT_PRESSURE", structure == "bearish"])

    if bullish >= 2 and quality >= 0.5:
        setup_dir = "LONG"
        setup_type = rng.choice(_SETUP_TYPES_LONG)
        setup_grade = rng.choice(_SETUP_GRADES)
        has_setup = True
    elif bearish >= 2 and quality >= 0.5:
        setup_dir = "SHORT"
        setup_type = rng.choice(_SETUP_TYPES_SHORT)
        setup_grade = rng.choice(_SETUP_GRADES)
        has_setup = True
    else:
        setup_dir = "NONE"
        setup_type = "NO_SETUP"
        setup_grade = "NONE"
        has_setup = False

    scenario_block = {
        "candle_direction": candle_dir,
        "evidence_label": evidence,
        "quality_weight": quality,
        "structure_bias": structure,
        "setup_type": setup_type,
        "setup_direction": setup_dir,
        "setup_grade": setup_grade,
    }

    if not has_setup:
        return {
            "sample_id": sample_id,
            "seed": seed,
            "symbol": symbol,
            "scenario": scenario_block,
            "decision": {
                "paper_decision": "NO_TRADE",
                "entry_price": None,
                "stop_loss": None,
                "tp1": None,
                "tp2": None,
                "rr_tp1": None,
                "rr_tp2": None,
            },
            "outcome": {
                "outcome": "NO_TRADE",
                "realized_rr": None,
                "edge_eligible": False,
            },
        }

    price = round(_BASE_PRICE + rng.uniform(-5000.0, 5000.0), 1)
    stop_dist = round(rng.uniform(200.0, 1000.0), 1)
    tp1_dist = round(stop_dist * rng.uniform(0.5, 1.0), 1)
    tp2_dist = round(stop_dist * rng.uniform(1.5, 3.0), 1)

    if setup_dir == "LONG":
        entry = price
        stop_loss = round(price - stop_dist, 1)
        tp1 = round(price + tp1_dist, 1)
        tp2 = round(price + tp2_dist, 1)
    else:
        entry = price
        stop_loss = round(price + stop_dist, 1)
        tp1 = round(price - tp1_dist, 1)
        tp2 = round(price - tp2_dist, 1)

    rr_tp1 = round(tp1_dist / stop_dist, 4)
    rr_tp2 = round(tp2_dist / stop_dist, 4)

    base_prob = _GRADE_WIN_PROB.get(setup_grade, 0.50)
    adjusted_prob = base_prob * quality
    roll = rng.random()

    if roll < adjusted_prob * 0.6:
        outcome = "WIN_TP2"
        realized_rr = rr_tp2
        edge_eligible = True
    elif roll < adjusted_prob:
        outcome = "WIN_TP1"
        realized_rr = rr_tp1
        edge_eligible = True
    elif roll < adjusted_prob + (1.0 - adjusted_prob) * 0.85:
        outcome = "LOSS"
        realized_rr = -1.0
        edge_eligible = True
    else:
        outcome = "AMBIGUOUS"
        realized_rr = None
        edge_eligible = False

    return {
        "sample_id": sample_id,
        "seed": seed,
        "symbol": symbol,
        "scenario": scenario_block,
        "decision": {
            "paper_decision": setup_dir,
            "entry_price": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rr_tp1": rr_tp1,
            "rr_tp2": rr_tp2,
        },
        "outcome": {
            "outcome": outcome,
            "realized_rr": realized_rr,
            "edge_eligible": edge_eligible,
        },
    }


def _compute_batch_stats(samples: list[dict[str, Any]]) -> dict[str, Any]:
    trades_opened = [s for s in samples if s["decision"]["paper_decision"] != "NO_TRADE"]
    no_trade_count = len(samples) - len(trades_opened)
    eligible = [s for s in trades_opened if s["outcome"]["edge_eligible"]]
    wins = [s for s in eligible if s["outcome"]["outcome"] in {"WIN_TP1", "WIN_TP2"}]
    losses = [s for s in eligible if s["outcome"]["outcome"] == "LOSS"]
    ambiguous = [s for s in trades_opened if s["outcome"]["outcome"] == "AMBIGUOUS"]

    edge_eligible_count = len(eligible)
    win_count = len(wins)
    loss_count = len(losses)

    win_rate = round(win_count / edge_eligible_count, 4) if edge_eligible_count > 0 else None
    rr_vals = [s["outcome"]["realized_rr"] for s in eligible if s["outcome"]["realized_rr"] is not None]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 4) if rr_vals else None
    edge_score = round(win_rate * avg_rr, 4) if (win_rate is not None and avg_rr is not None) else None

    return {
        "total_samples": len(samples),
        "trades_opened": len(trades_opened),
        "no_trade_count": no_trade_count,
        "edge_eligible_count": edge_eligible_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "ambiguous_count": len(ambiguous),
        "win_rate": win_rate,
        "avg_rr_realized": avg_rr,
        "edge_score": edge_score,
    }


def _build_data_quality(batch_stats: dict[str, Any]) -> dict[str, Any]:
    n = batch_stats["edge_eligible_count"]
    if n == 0:
        return {"score": 0.0, "level": "CRITICAL", "issues": ["NO_EDGE_ELIGIBLE_SAMPLES"]}
    if n < 10:
        return {"score": 0.3, "level": "LOW", "issues": ["SAMPLE_SIZE_SMALL"]}
    if n < 30:
        return {"score": 0.6, "level": "MEDIUM", "issues": []}
    return {"score": 1.0, "level": "HIGH", "issues": []}


def _build_reason_codes(source_mode: str, seed: int, batch_stats: dict[str, Any], dq: dict[str, Any]) -> list[str]:
    codes: list[str] = [
        f"SOURCE_{source_mode}",
        f"SEED_{seed}",
        f"TOTAL_SAMPLES_{batch_stats['total_samples']}",
        f"TRADES_OPENED_{batch_stats['trades_opened']}",
        f"EDGE_ELIGIBLE_{batch_stats['edge_eligible_count']}",
        f"WIN_COUNT_{batch_stats['win_count']}",
        f"LOSS_COUNT_{batch_stats['loss_count']}",
    ]
    wr = batch_stats["win_rate"]
    codes.append(f"WIN_RATE_{wr}" if wr is not None else "WIN_RATE_NULL")
    es = batch_stats["edge_score"]
    codes.append(f"EDGE_SCORE_{es}" if es is not None else "EDGE_SCORE_NULL")
    codes.append(f"DATA_QUALITY_{dq['level']}")
    codes.append("RESEARCH_ONLY")
    codes.append("SAFE_TO_OPEN_REAL_TRADE_FALSE")
    return codes


def run_batch(symbol: str, n_samples: int = 50, seed: int = DEFAULT_SEED) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate n_samples deterministic synthetic pipeline scenarios.

    Returns (samples, summary). summary follows the standard JSON contract.
    """
    rng = random.Random(seed)
    samples = [_generate_scenario(rng, i, symbol, seed) for i in range(n_samples)]

    batch_stats = _compute_batch_stats(samples)
    dq = _build_data_quality(batch_stats)
    reason_codes = _build_reason_codes("BATCH_REPLAY", seed, batch_stats, dq)

    summary = {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {
            "source_mode": "BATCH_REPLAY",
            "seed": seed,
            "samples_requested": n_samples,
        },
        "run_config": {
            "seed": seed,
            "samples_requested": n_samples,
            "samples_generated": len(samples),
        },
        "batch_stats": batch_stats,
        "data_quality": dq,
        "reason_codes": reason_codes,
        "feeds_next": FEEDS_NEXT,
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
            "research_only": True,
        },
    }
    return samples, summary


def run_fake_sample(symbol: str, n_samples: int = 50, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Fake-sample entry point — deterministic, no live data."""
    samples, summary = run_batch(symbol, n_samples, seed)
    summary["source"]["source_mode"] = "FAKE_SAMPLE"
    summary["reason_codes"][0] = "SOURCE_FAKE_SAMPLE"
    return summary
