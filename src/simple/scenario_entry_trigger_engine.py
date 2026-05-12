"""S16 — Scenario + Entry Trigger Engine. Converts setup context into scenario and entry-readiness state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")
REPORTS_DIR = Path("reports/simple")

SETUP_CONTEXT_PATH = STATE_DIR / "latest_setup_context.json"
FLOW_STATE_PATH = STATE_DIR / "latest_flow_state.json"
EVIDENCE_PATH = STATE_DIR / "latest_flow_evidence.json"
PERSISTENCE_PATH = STATE_DIR / "latest_flow_persistence.json"
MODEL_REGISTRY_PATH = STATE_DIR / "latest_model_registry.json"

SCENARIO_TRIGGER_PATH = STATE_DIR / "latest_scenario_trigger.json"
S16_STATE_PATH = STATE_DIR / "s16_scenario_trigger_state.json"
SCENARIO_TRIGGER_LOG_PATH = DATA_DIR / "scenario_trigger_history.jsonl"
REPORT_PATH = REPORTS_DIR / "s16_latest_report.md"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _scenario_label(
    setup_label: str,
    evidence_label: str,
    persistence_label: str,
    direction_bias: str,
    decay_risk: bool,
    flip_risk: bool,
    setup_score: float,
    confidence: float,
) -> str:
    if setup_label == "INSUFFICIENT_CONTEXT":
        return "INSUFFICIENT_DATA"

    if setup_label == "CHOPPY_CONTEXT" or persistence_label == "CHOPPY_FLOW":
        return "CHOPPY_RANGE"

    # Failed breakout: strong evidence but fading + decay
    if persistence_label in ("FADING_LONG_PRESSURE", "FADING_SHORT_PRESSURE") and decay_risk:
        return "FAILED_BREAKOUT"

    # Reversal: flip detected (e.g., persistence was short but evidence is now long)
    if flip_risk:
        if direction_bias == "LONG" and persistence_label in ("SUSTAINED_SHORT_PRESSURE", "FADING_SHORT_PRESSURE"):
            return "LONG_REVERSAL"
        if direction_bias == "SHORT" and persistence_label in ("SUSTAINED_LONG_PRESSURE", "FADING_LONG_PRESSURE"):
            return "SHORT_REVERSAL"

    # Breakout attempt: strong evidence but persistence not yet sustained
    if evidence_label == "STRONG_LONG_PRESSURE" and persistence_label not in ("SUSTAINED_LONG_PRESSURE",) and setup_score >= 4.0:
        return "BREAKOUT_ATTEMPT"
    if evidence_label == "STRONG_SHORT_PRESSURE" and persistence_label not in ("SUSTAINED_SHORT_PRESSURE",) and setup_score <= -4.0:
        return "BREAKOUT_ATTEMPT"

    # Continuation: setup label is strong + persistence sustained
    if setup_label == "STRONG_LONG_CONTEXT" and persistence_label == "SUSTAINED_LONG_PRESSURE":
        return "LONG_CONTINUATION"
    if setup_label == "STRONG_SHORT_CONTEXT" and persistence_label == "SUSTAINED_SHORT_PRESSURE":
        return "SHORT_CONTINUATION"

    if setup_label == "WEAK_LONG_CONTEXT" and persistence_label == "SUSTAINED_LONG_PRESSURE":
        return "LONG_CONTINUATION"
    if setup_label == "WEAK_SHORT_CONTEXT" and persistence_label == "SUSTAINED_SHORT_PRESSURE":
        return "SHORT_CONTINUATION"

    if setup_label == "NEUTRAL_CONTEXT":
        return "NO_SCENARIO"

    if setup_label == "NO_TRADE_CONTEXT":
        return "NO_SCENARIO"

    return "NO_SCENARIO"


def _market_regime(
    persistence_label: str,
    scenario_label: str,
    flip_risk: bool,
    direction_bias: str,
    input_status: str,
) -> str:
    if input_status == "MISSING" or scenario_label == "INSUFFICIENT_DATA":
        return "UNKNOWN"
    if scenario_label in ("CHOPPY_RANGE",) or persistence_label == "CHOPPY_FLOW":
        return "CHOPPY"
    if scenario_label in ("LONG_REVERSAL", "SHORT_REVERSAL") or flip_risk:
        return "REVERSAL"
    if scenario_label in ("LONG_CONTINUATION", "SHORT_CONTINUATION", "BREAKOUT_ATTEMPT"):
        return "TRENDING"
    if direction_bias == "NEUTRAL":
        return "RANGING"
    return "RANGING"


def _scenario_score(setup_score: float, persistence_score: float, evidence_score: float) -> float:
    raw = 0.5 * setup_score + 0.3 * persistence_score + 0.2 * evidence_score
    return _clamp(round(raw, 4), -10.0, 10.0)


def _apply_model_consensus(
    setup_score: float,
    direction_bias: str,
    model_registry: dict[str, Any] | None,
) -> tuple[float, str]:
    if direction_bias not in ("LONG", "SHORT") or not model_registry:
        return setup_score, "MODEL_NEUTRAL"

    consensus = model_registry.get("consensus_direction", "NEUTRAL")
    active_count = int(model_registry.get("active_model_count", 0) or 0)
    if active_count == 0 or consensus not in ("LONG", "SHORT"):
        return setup_score, "MODEL_NEUTRAL"

    if consensus == direction_bias:
        adjusted = setup_score + 1.0 if direction_bias == "LONG" else setup_score - 1.0
        return _clamp(adjusted, -10.0, 10.0), "MODEL_ALIGNED"

    adjusted = setup_score - 1.5 if direction_bias == "LONG" else setup_score + 1.5
    return _clamp(adjusted, -10.0, 10.0), "MODEL_CONFLICT"


def _trigger_strength(
    confidence: float,
    setup_score: float,
    continuation_quality: str,
    decay_risk: bool,
    flip_risk: bool,
) -> float:
    cont_weights = {"STRONG": 1.0, "MODERATE": 0.75, "WEAK": 0.5, "NONE": 0.25}
    cont_w = cont_weights.get(continuation_quality, 0.25)
    score_w = min(abs(setup_score) / 10.0, 1.0)
    base = (confidence * 0.5) + (score_w * 0.3) + (cont_w * 0.2)
    if decay_risk:
        base *= 0.65
    if flip_risk:
        base *= 0.55
    return _clamp(round(base, 4), 0.0, 1.0)


def _trigger_state(
    scenario_label: str,
    setup_label: str,
    direction_bias: str,
    tradeable: bool,
    confidence: float,
    trigger_strength: float,
    decay_risk: bool,
    flip_risk: bool,
    dq_level: str,
    persistence_label: str,
    input_status: str,
) -> str:
    if input_status == "MISSING" or scenario_label == "INSUFFICIENT_DATA":
        return "NO_TRIGGER"

    if flip_risk and decay_risk:
        return "CONFLICTED_TRIGGER"

    if scenario_label in ("FAILED_BREAKOUT",) or persistence_label == "CHOPPY_FLOW":
        return "NO_TRIGGER" if scenario_label != "FAILED_BREAKOUT" else "CONFLICTED_TRIGGER"

    if scenario_label == "CHOPPY_RANGE":
        return "NO_TRIGGER"

    if scenario_label == "NO_SCENARIO" or direction_bias == "NEUTRAL":
        return "NO_TRIGGER"

    if flip_risk:
        return "CONFLICTED_TRIGGER"

    quality_ok = dq_level in ("OK", "HIGH")

    if (
        tradeable
        and confidence >= 0.70
        and trigger_strength >= 0.70
        and quality_ok
        and persistence_label not in ("CHOPPY_FLOW",)
        and direction_bias in ("LONG", "SHORT")
    ):
        return "READY_FOR_ENTRY"

    if trigger_strength >= 0.50:
        return "WAIT_FOR_CONFIRMATION"

    return "WEAK_TRIGGER"


def _probabilities(
    trigger_strength: float,
    decay_risk: bool,
    flip_risk: bool,
    scenario_label: str,
) -> tuple[float, float, float]:
    if scenario_label == "INSUFFICIENT_DATA":
        return 0.33, 0.33, 0.34

    move_p = trigger_strength
    fakeout_p = 0.0
    if flip_risk:
        fakeout_p += 0.35
    if decay_risk:
        fakeout_p += 0.25
    if scenario_label == "FAILED_BREAKOUT":
        fakeout_p += 0.30
    if scenario_label == "BREAKOUT_ATTEMPT":
        fakeout_p += 0.15
    if scenario_label == "CHOPPY_RANGE":
        fakeout_p += 0.40
        move_p *= 0.4

    fakeout_p = _clamp(fakeout_p, 0.0, 0.95)

    remaining = 1.0 - fakeout_p
    if move_p > remaining:
        move_p = remaining * 0.7
    move_p = _clamp(move_p, 0.0, remaining)
    failure_p = _clamp(1.0 - move_p - fakeout_p, 0.0, 1.0)

    total = move_p + failure_p + fakeout_p
    if total > 0:
        move_p = round(move_p / total, 4)
        failure_p = round(failure_p / total, 4)
        fakeout_p = round(fakeout_p / total, 4)
    drift = round(1.0 - (move_p + failure_p + fakeout_p), 4)
    failure_p = round(failure_p + drift, 4)

    return move_p, failure_p, fakeout_p


def _ready_for_entry(
    trigger_state: str,
    tradeable: bool,
    confidence: float,
    trigger_strength: float,
    dq_level: str,
    persistence_label: str,
    direction_bias: str,
) -> bool:
    return (
        trigger_state == "READY_FOR_ENTRY"
        and tradeable
        and confidence >= 0.70
        and trigger_strength >= 0.70
        and dq_level in ("OK", "HIGH")
        and persistence_label not in ("CHOPPY_FLOW",)
        and direction_bias in ("LONG", "SHORT")
    )


def _trigger_reason(
    scenario_label: str,
    trigger_state: str,
    decay_risk: bool,
    flip_risk: bool,
    confidence: float,
    trigger_strength: float,
) -> str:
    if trigger_state == "READY_FOR_ENTRY":
        return f"Scenario {scenario_label} with sufficient confidence={confidence} and trigger_strength={trigger_strength}."
    if trigger_state == "WAIT_FOR_CONFIRMATION":
        return f"Scenario {scenario_label} promising but trigger_strength={trigger_strength} below entry threshold."
    if trigger_state == "WEAK_TRIGGER":
        return f"Scenario {scenario_label} present but trigger_strength={trigger_strength} is weak."
    if trigger_state == "CONFLICTED_TRIGGER":
        parts = []
        if flip_risk:
            parts.append("flip_risk")
        if decay_risk:
            parts.append("decay_risk")
        return "Conflicting signals: " + (", ".join(parts) if parts else "structural conflict")
    return f"No actionable trigger for scenario {scenario_label}."


def compute_scenario_trigger(
    setup_context: dict[str, Any] | None,
    flow_state: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    persistence: dict[str, Any] | None,
    model_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ts = _now_utc()
    reason_codes: list[str] = []
    input_status = "OK"

    missing = []
    if setup_context is None:
        missing.append("SETUP_CONTEXT_MISSING")
    if evidence is None:
        missing.append("EVIDENCE_MISSING")
    if persistence is None:
        missing.append("PERSISTENCE_MISSING")

    if setup_context is None or (evidence is None and persistence is None):
        input_status = "MISSING"
        reason_codes.extend(missing)

    setup_context = setup_context or {}
    evidence = evidence or {}
    persistence = persistence or {}

    symbol = (
        setup_context.get("symbol")
        or evidence.get("symbol")
        or persistence.get("symbol")
        or "UNKNOWN"
    )
    source = setup_context.get("block_id") or "S15_FLOW_TO_SETUP_CONTEXT"

    setup_label = setup_context.get("setup_context_label", "INSUFFICIENT_CONTEXT")
    setup_score = float(setup_context.get("setup_context_score", 0.0))
    direction_bias = setup_context.get("direction_bias", "UNKNOWN")
    context_confidence = float(setup_context.get("confidence", 0.0))
    tradeable_context = bool(setup_context.get("tradeable", False))
    setup_dq = setup_context.get("data_quality", {})
    dq_level = setup_dq.get("level", "MISSING")
    dq_score = float(setup_dq.get("score", 0.0))

    evidence_label = evidence.get("evidence_label", "NEUTRAL_FLOW")
    evidence_score = float(evidence.get("evidence_score", 0.0))

    persistence_label = persistence.get("persistence_label", "NO_VALID_FLOW")
    persistence_score = float(persistence.get("persistence_score", 0.0))
    continuation_quality = persistence.get("continuation_quality", "NONE")
    decay_risk = bool(persistence.get("decay_risk", False))
    flip_risk = bool(persistence.get("flip_risk", False))
    adjusted_setup_score, model_alignment = _apply_model_consensus(
        setup_score, direction_bias, model_registry
    )

    if input_status == "MISSING":
        setup_label = "INSUFFICIENT_CONTEXT"
        direction_bias = "UNKNOWN"
        adjusted_setup_score = 0.0

    scenario_label = _scenario_label(
        setup_label, evidence_label, persistence_label,
        direction_bias, decay_risk, flip_risk, adjusted_setup_score, context_confidence,
    )

    scenario_score = _scenario_score(adjusted_setup_score, persistence_score, evidence_score)

    trigger_strength = _trigger_strength(
        context_confidence, setup_score, continuation_quality, decay_risk, flip_risk
    )

    trigger_state = _trigger_state(
        scenario_label, setup_label, direction_bias, tradeable_context,
        context_confidence, trigger_strength, decay_risk, flip_risk,
        dq_level, persistence_label, input_status,
    )

    move_p, failure_p, fakeout_p = _probabilities(
        trigger_strength, decay_risk, flip_risk, scenario_label
    )

    market_regime = _market_regime(
        persistence_label, scenario_label, flip_risk, direction_bias, input_status
    )

    trigger_confidence = _clamp(round(context_confidence * trigger_strength, 4), 0.0, 1.0)

    ready = _ready_for_entry(
        trigger_state, tradeable_context, context_confidence, trigger_strength,
        dq_level, persistence_label, direction_bias,
    )

    tradeable = ready

    trigger_reason = _trigger_reason(
        scenario_label, trigger_state, decay_risk, flip_risk,
        context_confidence, trigger_strength,
    )

    reason_codes += [
        f"SYMBOL_{symbol}",
        f"SETUP_{setup_label}",
        f"SCENARIO_{scenario_label}",
        f"TRIGGER_{trigger_state}",
        f"DIRECTION_{direction_bias}",
        f"REGIME_{market_regime}",
        model_alignment,
        f"DQ_{dq_level}",
        "SAFE_TO_OPEN_REAL_TRADE_FALSE",
        "NO_PRIVATE_API",
        "NO_TELEGRAM",
        "NO_ORDER_EXECUTION",
    ]
    if decay_risk:
        reason_codes.append("DECAY_RISK_DETECTED")
    if flip_risk:
        reason_codes.append("FLIP_RISK_DETECTED")
    if not ready:
        reason_codes.append("NOT_READY_FOR_ENTRY")

    return {
        "timestamp_utc": ts,
        "block_id": "S16_SCENARIO_ENTRY_TRIGGER",
        "symbol": symbol,
        "source": source,
        "scenario_label": scenario_label,
        "scenario_score": scenario_score,
        "direction_bias": direction_bias,
        "trigger_state": trigger_state,
        "trigger_strength": trigger_strength,
        "trigger_confidence": trigger_confidence,
        "trigger_reason": trigger_reason,
        "estimated_move_probability": move_p,
        "estimated_failure_probability": failure_p,
        "estimated_fakeout_probability": fakeout_p,
        "market_regime": market_regime,
        "tradeable": tradeable,
        "ready_for_entry": ready,
        "data_quality": {"level": dq_level, "score": dq_score},
        "reason_codes": reason_codes,
        "feeds_next": {"next_blocks": ["S17_TRADE_PLAN_ENGINE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def no_valid_output(reason: str) -> dict[str, Any]:
    ts = _now_utc()
    return {
        "timestamp_utc": ts,
        "block_id": "S16_SCENARIO_ENTRY_TRIGGER",
        "symbol": "UNKNOWN",
        "source": "NONE",
        "scenario_label": "INSUFFICIENT_DATA",
        "scenario_score": 0.0,
        "direction_bias": "UNKNOWN",
        "trigger_state": "NO_TRIGGER",
        "trigger_strength": 0.0,
        "trigger_confidence": 0.0,
        "trigger_reason": "Input files missing — cannot determine scenario.",
        "estimated_move_probability": 0.33,
        "estimated_failure_probability": 0.33,
        "estimated_fakeout_probability": 0.34,
        "market_regime": "UNKNOWN",
        "tradeable": False,
        "ready_for_entry": False,
        "data_quality": {"level": "MISSING", "score": 0.0},
        "reason_codes": [
            "INSUFFICIENT_DATA",
            reason,
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "NO_TELEGRAM",
            "NO_ORDER_EXECUTION",
        ],
        "feeds_next": {"next_blocks": ["S17_TRADE_PLAN_ENGINE"]},
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }


def run_scenario_entry_trigger_engine() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    setup_context = _load_json(SETUP_CONTEXT_PATH)
    flow_state = _load_json(FLOW_STATE_PATH)
    evidence = _load_json(EVIDENCE_PATH)
    persistence = _load_json(PERSISTENCE_PATH)
    model_registry = _load_json(MODEL_REGISTRY_PATH)

    if setup_context is None and evidence is None and persistence is None:
        result = no_valid_output("ALL_INPUTS_MISSING")
    else:
        try:
            result = compute_scenario_trigger(
                setup_context, flow_state, evidence, persistence, model_registry
            )
        except Exception:
            result = no_valid_output("COMPUTE_ERROR")

    SCENARIO_TRIGGER_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s16_state = {
        "timestamp_utc": result["timestamp_utc"],
        "block_id": "S16_SCENARIO_TRIGGER_STATE",
        "last_scenario_label": result["scenario_label"],
        "last_trigger_state": result["trigger_state"],
        "last_scenario_score": result["scenario_score"],
        "last_trigger_strength": result["trigger_strength"],
        "last_ready_for_entry": result["ready_for_entry"],
        "runs": 1,
    }
    S16_STATE_PATH.write_text(json.dumps(s16_state, indent=2), encoding="utf-8")

    with SCENARIO_TRIGGER_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    _write_report(result)

    return result


def _write_report(r: dict[str, Any]) -> None:
    lines = [
        "# S16 Scenario + Entry Trigger — Latest Report",
        "",
        f"**Timestamp:** {r['timestamp_utc']}",
        f"**Symbol:** {r['symbol']}",
        f"**Scenario Label:** {r['scenario_label']}",
        f"**Scenario Score:** {r['scenario_score']}",
        f"**Direction Bias:** {r['direction_bias']}",
        f"**Trigger State:** {r['trigger_state']}",
        f"**Trigger Strength:** {r['trigger_strength']}",
        f"**Trigger Confidence:** {r['trigger_confidence']}",
        f"**Trigger Reason:** {r['trigger_reason']}",
        f"**Move Probability:** {r['estimated_move_probability']}",
        f"**Failure Probability:** {r['estimated_failure_probability']}",
        f"**Fakeout Probability:** {r['estimated_fakeout_probability']}",
        f"**Market Regime:** {r['market_regime']}",
        f"**Tradeable:** {r['tradeable']}",
        f"**Ready For Entry:** {r['ready_for_entry']}",
        f"**Data Quality:** {r['data_quality']['level']} ({r['data_quality']['score']})",
        f"**Reason Codes:** {', '.join(r['reason_codes'])}",
        f"**Feeds Next:** {', '.join(r['feeds_next']['next_blocks'])}",
        f"**Safe To Open Real Trade:** {r['execution_safety']['safe_to_open_real_trade']}",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
