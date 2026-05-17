from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, write_json
from src.simple.lineage_event_logger import append_event, lineage_record, stable_id

BLOCK_ID = "CONTRACT_DECISION_GATE"
MODE = "EXPLORATION_ALLOW_MODE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple/epoch_v2")

CONTRACT_TRADE_PLAN_PATH = STATE_DIR / "latest_contract_trade_plan.json"
SETUP_CONTRACT_PATH = STATE_DIR / "latest_setup_contract.json"
MARKET_STRUCTURE_V2_PATH = STATE_DIR / "latest_market_structure_v2.json"
REGIME_PATH = STATE_DIR / "latest_regime_classifier.json"
LIQUIDITY_PATH = STATE_DIR / "latest_liquidity_structure.json"
QUALITY_WEIGHT_PATH = STATE_DIR / "latest_quality_weight.json"

OUTPUT_PATH = STATE_DIR / "latest_contract_decision_gate.json"
HISTORY_PATH = DATA_DIR / "contract_decision_gate_history.jsonl"

FEEDS_NEXT = ["PAPER_LIFECYCLE", "OUTCOME_TRACKER", "EDGE_MATRIX"]
HARD_BLOCK_REASONS = {
    "STRUCTURE_DIRECTION_CONFLICT",
    "ENTRY_SL_TP_MISSING",
    "SIGNAL_ID_MISSING",
    "PLAN_ID_MISSING",
    "RR_LOW_METADATA_ONLY",
    "DATA_QUALITY_METADATA_ONLY",
    "SETUP_ID_MISSING",
    "DECISION_ID_MISSING",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def build_contract_decision_gate(
    symbol: str = "BTCUSDT",
    trade_plan_payload: dict[str, Any] | None = None,
    setup_contract_payload: dict[str, Any] | None = None,
    structure_payload: dict[str, Any] | None = None,
    regime_payload: dict[str, Any] | None = None,
    liquidity_payload: dict[str, Any] | None = None,
    quality_weight_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trade_plan = trade_plan_payload if trade_plan_payload is not None else _load_json(CONTRACT_TRADE_PLAN_PATH)
    setup_contract = setup_contract_payload if setup_contract_payload is not None else _load_json(SETUP_CONTRACT_PATH)
    structure = structure_payload if structure_payload is not None else _load_json(MARKET_STRUCTURE_V2_PATH)
    regime = regime_payload if regime_payload is not None else _load_json(REGIME_PATH)
    liquidity = liquidity_payload if liquidity_payload is not None else _load_json(LIQUIDITY_PATH)
    quality = quality_weight_payload if quality_weight_payload is not None else _load_json(QUALITY_WEIGHT_PATH)

    if trade_plan is None:
        return {
            "timestamp_utc": _utc_now(),
            "block_id": BLOCK_ID,
            "symbol": symbol,
            "source": {"source_mode": "STATE_FILE"},
            "mode": MODE,
            "data_quality": "DEGRADED",
            "decision_status": "BLOCK",
            "direction": "NEUTRAL",
            "contract_id": None,
            "setup_family": None,
            "alignment": {
                "structure_aligned": False,
                "regime_aligned": False,
                "liquidity_aligned": False,
                "rr_valid": False,
                "data_quality_valid": False,
                "session_aligned": False,
            },
            "metadata": {
                "regime": None,
                "structure_bias": None,
                "liquidity_bias": None,
                "rr1": None,
                "rr2": None,
                "session_downgrade": False,
                "regime_alignment_note": None,
                "liquidity_alignment_note": None,
            },
            "block_reasons": [],
            "allow_reasons": [],
            "downgrade_reasons": ["TRADE_PLAN_MISSING"],
            "confidence": 0.0,
            "reason_codes": ["TRADE_PLAN_MISSING", "DECISION_BLOCK"],
            "feeds_next": FEEDS_NEXT,
        }

    direction = str(trade_plan.get("direction", "NEUTRAL")).upper()
    setup_id = str(trade_plan.get("setup_id") or "")
    signal_id = str(trade_plan.get("signal_id") or "")
    plan_id = str(trade_plan.get("plan_id") or "")
    entry = _as_float(trade_plan.get("entry"))
    stop_loss = _as_float(trade_plan.get("stop_loss"))
    tp1 = _as_float(trade_plan.get("tp1"))
    rr1 = _as_float(trade_plan.get("rr1"))
    rr2 = _as_float(trade_plan.get("rr2"))
    structure_bias = str((structure or {}).get("structure_bias", "UNKNOWN")).upper()
    regime_alignment = str(trade_plan.get("regime_alignment", "UNKNOWN")).upper()
    liquidity_alignment = str(trade_plan.get("liquidity_alignment", "UNKNOWN")).upper()
    regime_name = str((regime or {}).get("primary_regime", "UNKNOWN")).upper()
    liq_bias = str((liquidity or {}).get("liquidity_bias", "UNKNOWN")).upper()
    session_downgrade = bool(trade_plan.get("session_downgrade", False) or (setup_contract or {}).get("session_downgrade", False))
    plan_status = str(trade_plan.get("plan_status", "NO_PLAN")).upper()

    structure_aligned = not (
        (structure_bias == "SHORT" and direction == "LONG") or (structure_bias == "LONG" and direction == "SHORT")
    )
    rr_valid = (rr1 is not None and rr1 >= 1.2) and (rr2 is not None and rr2 >= 1.5)
    dq_text = str((quality or {}).get("data_quality", (quality or {}).get("quality_label", "UNKNOWN"))).upper()
    data_quality_valid = dq_text in {"OK", "HIGH", "MEDIUM"}
    session_aligned = not session_downgrade

    block_reasons: list[str] = []
    allow_reasons: list[str] = []
    downgrade_reasons: list[str] = []
    reason_codes: list[str] = []
    confidence = float(trade_plan.get("plan_confidence", 0.5) or 0.5)

    if not structure_aligned:
        block_reasons.append("STRUCTURE_DIRECTION_CONFLICT")
    if entry is None or stop_loss is None or tp1 is None:
        block_reasons.append("ENTRY_SL_TP_MISSING")
    if not setup_id:
        block_reasons.append("SETUP_ID_MISSING")
    if not signal_id:
        block_reasons.append("SIGNAL_ID_MISSING")
    if not plan_id:
        block_reasons.append("PLAN_ID_MISSING")

    if block_reasons:
        decision = "BLOCK"
        dq = "INVALID" if "STRUCTURE_DIRECTION_CONFLICT" in block_reasons else "DEGRADED"
        confidence = 0.0
    else:
        if plan_status in {"PLAN_READY", "NO_PLAN", "NOT_READY", "INVALID"} and direction in {"LONG", "SHORT"} and entry is not None and stop_loss is not None and tp1 is not None:
            decision = "ALLOW_PAPER"
            allow_reasons.append("EXPLORATION_ALLOW_ACTIVE")
            allow_reasons.append("HARD_BLOCK_CONDITIONS_NOT_TRIGGERED")
        else:
            decision = "WAIT"
            downgrade_reasons.append("PLAN_NOT_USABLE_YET")
            confidence *= 0.7
        dq = "OK"

    regime_aligned = regime_alignment == "ALIGNED"
    liquidity_aligned = liquidity_alignment == "ALIGNED"
    if regime_alignment == "MISALIGNED":
        downgrade_reasons.append("REGIME_MISALIGNED_METADATA_ONLY")
        reason_codes.append("REGIME_MISALIGNED_METADATA_ONLY")
        confidence *= 0.9
    if liquidity_alignment == "MISALIGNED":
        downgrade_reasons.append("LIQUIDITY_MISALIGNED_METADATA_ONLY")
        reason_codes.append("LIQUIDITY_MISALIGNED_METADATA_ONLY")
        confidence *= 0.9
    if not rr_valid:
        downgrade_reasons.append("RR_LOW_METADATA_ONLY")
        reason_codes.append("RR_LOW_METADATA_ONLY")
        confidence *= 0.9
    if session_downgrade:
        downgrade_reasons.append("OFF_SESSION_DOWNGRADE")
        reason_codes.append("OFF_SESSION_DOWNGRADE")
        confidence *= 0.9
    if not data_quality_valid:
        downgrade_reasons.append("DATA_QUALITY_METADATA_ONLY")
        reason_codes.append("DATA_QUALITY_METADATA_ONLY")
        confidence *= 0.95

    reason_codes.extend(block_reasons)
    reason_codes.extend(allow_reasons)
    reason_codes.extend(downgrade_reasons)
    reason_codes.append(f"DECISION_{decision}")

    execution_permission = "ALLOW_OPEN"
    if any(reason in HARD_BLOCK_REASONS for reason in (block_reasons + downgrade_reasons + reason_codes)):
        execution_permission = "BLOCK_OPEN"
    elif decision != "ALLOW_PAPER":
        execution_permission = "METADATA_ONLY_NO_OPEN"
    decision_id = stable_id("DEC", symbol, setup_id, signal_id, plan_id, _utc_now())

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "record_type": "decision",
        "decision_id": decision_id,
        "parent_id": plan_id or signal_id or setup_id or None,
        "setup_id": setup_id or None,
        "signal_id": signal_id or None,
        "plan_id": plan_id or None,
        "symbol": str(trade_plan.get("symbol") or symbol),
        "source": {"source_mode": "STATE_FILE"},
        "mode": MODE,
        "data_quality": dq,
        "decision_status": decision,
        "execution_permission": execution_permission,
        "direction": direction if direction in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL",
        "contract_id": trade_plan.get("contract_id"),
        "setup_family": trade_plan.get("setup_family"),
        "alignment": {
            "structure_aligned": structure_aligned,
            "regime_aligned": regime_aligned,
            "liquidity_aligned": liquidity_aligned,
            "rr_valid": rr_valid,
            "data_quality_valid": data_quality_valid,
            "session_aligned": session_aligned,
        },
        "metadata": {
            "regime": regime_name,
            "structure_bias": structure_bias,
            "liquidity_bias": liq_bias,
            "rr1": rr1,
            "rr2": rr2,
            "session_downgrade": session_downgrade,
            "regime_alignment_note": "REGIME_MISALIGNED_METADATA_ONLY" if regime_alignment == "MISALIGNED" else None,
            "liquidity_alignment_note": "LIQUIDITY_MISALIGNED_METADATA_ONLY" if liquidity_alignment == "MISALIGNED" else None,
        },
        "block_reasons": block_reasons,
        "allow_reasons": allow_reasons,
        "downgrade_reasons": downgrade_reasons,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "reason_codes": sorted(set(reason_codes)),
        "feeds_next": FEEDS_NEXT,
    }


def _fake_trade_plan(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "plan_status": "PLAN_READY",
        "direction": "LONG",
        "contract_id": "SC003",
        "setup_family": "TREND_CONTINUATION_LONG",
        "entry": 100.0,
        "stop_loss": 99.0,
        "tp1": 101.2,
        "tp2": 101.8,
        "rr1": 1.2,
        "rr2": 1.8,
        "plan_confidence": 0.72,
        "session_downgrade": False,
        "regime_alignment": "ALIGNED",
        "liquidity_alignment": "ALIGNED",
    }


def _fake_structure(symbol: str) -> dict[str, Any]:
    return {"symbol": symbol, "structure_bias": "LONG"}


def run_contract_decision_gate(symbol: str = "BTCUSDT", fake_sample: bool = False) -> dict[str, Any]:
    context = current_runtime_context(symbol)
    payload = build_contract_decision_gate(
        symbol=symbol,
        trade_plan_payload=_fake_trade_plan(symbol) if fake_sample else None,
        structure_payload=_fake_structure(symbol) if fake_sample else None,
    )
    payload["context_id"] = context.get("context_id")
    payload["loop_id"] = context.get("loop_id")
    write_json(OUTPUT_PATH, payload)
    _append_jsonl(HISTORY_PATH, payload)
    if payload.get("decision_id"):
        append_event(
            "decision_events.jsonl",
            lineage_record(
                record_type="decision_event",
                event_id=str(payload.get("decision_id")),
                parent_id=str(payload.get("plan_id") or ""),
                setup_id=str(payload.get("setup_id") or ""),
                signal_id=str(payload.get("signal_id") or ""),
                plan_id=str(payload.get("plan_id") or ""),
                decision_id=str(payload.get("decision_id") or ""),
                context_id=context.get("context_id"),
                loop_id=context.get("loop_id"),
                reason_codes=list(payload.get("reason_codes") or []),
                blocked_by=list(payload.get("block_reasons") or []) + list(payload.get("downgrade_reasons") or []),
                feeds_next=["paper_trade_open_events"],
                extra={"execution_permission": payload.get("execution_permission"), "decision_status": payload.get("decision_status")},
            ),
        )
    return payload

