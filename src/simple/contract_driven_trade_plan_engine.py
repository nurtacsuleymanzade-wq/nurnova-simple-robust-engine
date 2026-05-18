from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, write_json
from src.simple.setup_contract_registry import load_setup_contract_registry
from src.simple.lineage_event_logger import append_event, lineage_record, stable_id
from src.simple.research_epoch import epoch_state_path

BLOCK_ID = "CONTRACT_DRIVEN_TRADE_PLAN"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple/epoch_v2")

SETUP_CONTRACT_PATH = STATE_DIR / "latest_setup_contract.json"
MARKET_STRUCTURE_V2_PATH = STATE_DIR / "latest_market_structure_v2.json"
REGIME_PATH = STATE_DIR / "latest_regime_classifier.json"
LIQUIDITY_PATH = STATE_DIR / "latest_liquidity_structure.json"
SETUP_CANDIDATE_PATH = STATE_DIR / "latest_setup_candidate.json"
DEPTH_MEMORY_PATH = STATE_DIR / "latest_depth_memory.json"
VOLUME_PROFILE_PATH = STATE_DIR / "latest_volume_profile.json"
SIGNAL_EVENT_PATH = epoch_state_path("latest_signal_event.json")

OUTPUT_PATH = STATE_DIR / "latest_contract_trade_plan.json"
HISTORY_PATH = DATA_DIR / "contract_trade_plan_history.jsonl"

FEEDS_NEXT = ["DECISION_GATE", "PAPER_LIFECYCLE", "OUTCOME_TRACKER"]
SAFETY = {"safe_to_open_real_trade": False, "private_api_used": False, "live_order_sent": False}


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
        x = float(v)
        return x
    except Exception:
        return None


def _status_payload(
    *,
    symbol: str,
    plan_status: str,
    reason_codes: list[str],
    setup_id: str | None = None,
    signal_id: str | None = None,
    data_quality: str = "DEGRADED",
    contract_id: str | None = None,
    setup_family: Any = None,
    direction: str = "NEUTRAL",
    entry: float | None = None,
    stop_loss: float | None = None,
    tp1: float | None = None,
    tp2: float | None = None,
    rr1: float | None = None,
    rr2: float | None = None,
    risk_distance: float | None = None,
    reward_distance_1: float | None = None,
    reward_distance_2: float | None = None,
    entry_model: Any = None,
    sl_model: Any = None,
    tp_model: Any = None,
    invalidation_level: float | None = None,
    destination_level_1: float | None = None,
    destination_level_2: float | None = None,
    plan_confidence: float = 0.0,
    session_downgrade: bool = False,
    regime_alignment: str = "UNKNOWN",
    liquidity_alignment: str = "UNKNOWN",
) -> dict[str, Any]:
    executable = plan_status == "PLAN_READY"
    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "source": {"source_mode": "STATE_FILE"},
        "data_quality": data_quality,
        "plan_status": plan_status,
        "setup_id": setup_id,
        "signal_id": signal_id,
        "contract_id": contract_id,
        "setup_family": setup_family,
        "direction": direction,
        "side": direction,
        "entry": round(entry, 4) if entry is not None else None,
        "entry_price": round(entry, 4) if entry is not None else None,
        "stop_loss": round(stop_loss, 4) if stop_loss is not None else None,
        "tp1": round(tp1, 4) if tp1 is not None else None,
        "tp2": round(tp2, 4) if tp2 is not None else None,
        "rr1": round(rr1, 4) if rr1 is not None else None,
        "rr2": round(rr2, 4) if rr2 is not None else None,
        "risk_distance": round(risk_distance, 6) if risk_distance is not None else None,
        "reward_distance_1": round(reward_distance_1, 6) if reward_distance_1 is not None else None,
        "reward_distance_2": round(reward_distance_2, 6) if reward_distance_2 is not None else None,
        "entry_model": entry_model,
        "sl_model": sl_model,
        "tp_model": tp_model,
        "invalidation_level": round(invalidation_level, 4) if invalidation_level is not None else None,
        "destination_level_1": round(destination_level_1, 4) if destination_level_1 is not None else None,
        "destination_level_2": round(destination_level_2, 4) if destination_level_2 is not None else None,
        "geometry_quality": "PAPER_EXECUTABLE" if executable else "NOT_EXECUTABLE",
        "paper_executable": executable,
        "real_trade_allowed": False,
        "plan_confidence": round(max(0.0, min(1.0, plan_confidence)), 3),
        "session_downgrade": session_downgrade,
        "regime_alignment": regime_alignment,
        "liquidity_alignment": liquidity_alignment,
        "reason_codes": sorted(set(reason_codes)),
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def _extract_prices(points: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for p in points:
        price = _as_float(p.get("price"))
        if price is not None:
            out.append(price)
    return out


def _entry_price(structure: dict[str, Any], setup_candidate: dict[str, Any] | None) -> float | None:
    for key in ("entry", "entry_price", "reference_price", "last_price"):
        v = _as_float((setup_candidate or {}).get(key))
        if v is not None:
            return v
    highs = _extract_prices(list(structure.get("swing_highs") or []))
    lows = _extract_prices(list(structure.get("swing_lows") or []))
    if highs and lows:
        return (highs[-1] + lows[-1]) / 2.0
    last_hh = _as_float(structure.get("last_hh"))
    last_hl = _as_float(structure.get("last_hl"))
    if last_hh is not None and last_hl is not None:
        return (last_hh + last_hl) / 2.0
    return None


def _geometry_valid(direction: str, entry: float, sl: float, tp1: float, tp2: float) -> bool:
    if direction == "LONG":
        return sl < entry < tp1 <= tp2
    if direction == "SHORT":
        return sl > entry > tp1 >= tp2
    return False


def _paper_geometry(direction: str, entry: float, sl: float | None, tp1: float | None, tp2: float | None) -> tuple[float, float, float, list[str]]:
    reasons: list[str] = []
    if sl is not None and tp1 is not None and tp2 is not None and _geometry_valid(direction, entry, sl, tp1, tp2):
        risk = entry - sl if direction == "LONG" else sl - entry
        rr1 = ((tp1 - entry) if direction == "LONG" else (entry - tp1)) / risk if risk > 0 else 0.0
        rr2 = ((tp2 - entry) if direction == "LONG" else (entry - tp2)) / risk if risk > 0 else 0.0
        if rr1 >= 1.2 and rr2 >= 1.5:
            return sl, tp1, tp2, reasons
        reasons.append("RR_GEOMETRY_REPAIRED_FOR_PAPER")
    else:
        reasons.append("PRICE_GEOMETRY_REPAIRED_FOR_PAPER")

    base_risk = abs(entry - sl) if sl is not None else 0.0
    risk = max(base_risk, entry * 0.001)
    if direction == "LONG":
        return entry - risk, entry + risk * 1.5, entry + risk * 2.0, reasons
    return entry + risk, entry - risk * 1.5, entry - risk * 2.0, reasons


def _contract_by_id(contract_id: str) -> dict[str, Any] | None:
    for c in load_setup_contract_registry():
        if str(c.get("contract_id")) == contract_id:
            return c
    return None


def _long_levels(
    entry: float, structure: dict[str, Any], liquidity: dict[str, Any] | None, volume_profile: dict[str, Any] | None
) -> tuple[float | None, float | None, float | None, list[str]]:
    reasons: list[str] = []
    swing_lows = _extract_prices(list(structure.get("swing_lows") or []))
    swing_highs = _extract_prices(list(structure.get("swing_highs") or []))
    eq_lows = [_as_float(x) for x in list(structure.get("equal_lows") or [])]
    eq_highs = [_as_float(x) for x in list(structure.get("equal_highs") or [])]
    eq_lows = [x for x in eq_lows if x is not None]
    eq_highs = [x for x in eq_highs if x is not None]

    sl_candidates: list[float] = []
    tp_candidates: list[float] = []

    sweep_low = _as_float((liquidity or {}).get("sweep_low"))
    last_hl = _as_float(structure.get("last_hl"))
    if sweep_low is not None and sweep_low < entry:
        sl_candidates.append(sweep_low * 0.9995)
    if last_hl is not None and last_hl < entry:
        sl_candidates.append(last_hl * 0.9995)
    sl_candidates.extend([x * 0.9995 for x in swing_lows if x < entry])
    sl_candidates.extend([x * 0.9995 for x in eq_lows if x < entry])

    tp_candidates.extend([x * 0.9995 for x in eq_highs if x > entry])
    tp_candidates.extend([x * 0.9995 for x in swing_highs if x > entry])
    liq_above = _as_float((liquidity or {}).get("liquidity_target_above"))
    if liq_above is not None and liq_above > entry:
        tp_candidates.append(liq_above * 0.9995)
    vp = volume_profile or {}
    for key in ("value_high", "poc", "naked_poc"):
        val = _as_float(vp.get(key))
        if val is not None and val > entry:
            tp_candidates.append(val * 0.9995)

    sl = max(sl_candidates) if sl_candidates else None
    tp1 = min(tp_candidates) if tp_candidates else None
    tp2 = None
    if tp1 is not None:
        higher = sorted([x for x in tp_candidates if x > tp1])
        tp2 = higher[0] if higher else None
    if sl is None:
        sl = entry * 0.995
        reasons.append("FALLBACK_SL_USED")
    if tp1 is None:
        risk = entry - sl
        tp1 = entry + risk * 1.2
        reasons.append("FALLBACK_TP_USED")
    if tp2 is None:
        risk = entry - sl
        tp2 = entry + risk * 1.5
        reasons.append("FALLBACK_TP_USED")
    return sl, tp1, tp2, reasons


def _short_levels(
    entry: float, structure: dict[str, Any], liquidity: dict[str, Any] | None, volume_profile: dict[str, Any] | None
) -> tuple[float | None, float | None, float | None, list[str]]:
    reasons: list[str] = []
    swing_lows = _extract_prices(list(structure.get("swing_lows") or []))
    swing_highs = _extract_prices(list(structure.get("swing_highs") or []))
    eq_lows = [_as_float(x) for x in list(structure.get("equal_lows") or [])]
    eq_highs = [_as_float(x) for x in list(structure.get("equal_highs") or [])]
    eq_lows = [x for x in eq_lows if x is not None]
    eq_highs = [x for x in eq_highs if x is not None]

    sl_candidates: list[float] = []
    tp_candidates: list[float] = []

    sweep_high = _as_float((liquidity or {}).get("sweep_high"))
    last_lh = _as_float(structure.get("last_lh"))
    if sweep_high is not None and sweep_high > entry:
        sl_candidates.append(sweep_high * 1.0005)
    if last_lh is not None and last_lh > entry:
        sl_candidates.append(last_lh * 1.0005)
    sl_candidates.extend([x * 1.0005 for x in swing_highs if x > entry])
    sl_candidates.extend([x * 1.0005 for x in eq_highs if x > entry])

    tp_candidates.extend([x * 1.0005 for x in eq_lows if x < entry])
    tp_candidates.extend([x * 1.0005 for x in swing_lows if x < entry])
    liq_below = _as_float((liquidity or {}).get("liquidity_target_below"))
    if liq_below is not None and liq_below < entry:
        tp_candidates.append(liq_below * 1.0005)
    vp = volume_profile or {}
    for key in ("value_low", "poc", "naked_poc"):
        val = _as_float(vp.get(key))
        if val is not None and val < entry:
            tp_candidates.append(val * 1.0005)

    sl = min(sl_candidates) if sl_candidates else None
    tp1 = max(tp_candidates) if tp_candidates else None
    tp2 = None
    if tp1 is not None:
        lower = sorted([x for x in tp_candidates if x < tp1], reverse=True)
        tp2 = lower[0] if lower else None
    if sl is None:
        sl = entry * 1.005
        reasons.append("FALLBACK_SL_USED")
    if tp1 is None:
        risk = sl - entry
        tp1 = entry - risk * 1.2
        reasons.append("FALLBACK_TP_USED")
    if tp2 is None:
        risk = sl - entry
        tp2 = entry - risk * 1.5
        reasons.append("FALLBACK_TP_USED")
    return sl, tp1, tp2, reasons


def build_contract_driven_trade_plan(
    symbol: str = "BTCUSDT",
    setup_contract_payload: dict[str, Any] | None = None,
    structure_payload: dict[str, Any] | None = None,
    regime_payload: dict[str, Any] | None = None,
    liquidity_payload: dict[str, Any] | None = None,
    setup_candidate_payload: dict[str, Any] | None = None,
    depth_memory_payload: dict[str, Any] | None = None,
    volume_profile_payload: dict[str, Any] | None = None,
    signal_event_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    setup_contract = setup_contract_payload if setup_contract_payload is not None else _load_json(SETUP_CONTRACT_PATH)
    structure = structure_payload if structure_payload is not None else _load_json(MARKET_STRUCTURE_V2_PATH)
    regime = regime_payload if regime_payload is not None else _load_json(REGIME_PATH)
    liquidity = liquidity_payload if liquidity_payload is not None else _load_json(LIQUIDITY_PATH)
    setup_candidate = setup_candidate_payload if setup_candidate_payload is not None else _load_json(SETUP_CANDIDATE_PATH)
    _ = depth_memory_payload if depth_memory_payload is not None else _load_json(DEPTH_MEMORY_PATH)
    volume_profile = volume_profile_payload if volume_profile_payload is not None else _load_json(VOLUME_PROFILE_PATH)
    signal_event = signal_event_payload if signal_event_payload is not None else _load_json(SIGNAL_EVENT_PATH)
    latest_signal = (signal_event or {}).get("latest_event") or {}
    signal_id = str(latest_signal.get("signal_id") or "")
    setup_id = str(latest_signal.get("setup_id") or (setup_candidate or {}).get("setup_id") or "")
    reason_codes: list[str] = []
    if signal_event:
        reason_codes.append("SIGNAL_EVENT_CANONICAL_EPOCH_V2")
    if not setup_id:
        return _status_payload(symbol=symbol, plan_status="NOT_READY", reason_codes=reason_codes + ["SETUP_ID_MISSING"])
    if not signal_id:
        return _status_payload(symbol=symbol, setup_id=setup_id, plan_status="NOT_READY", reason_codes=reason_codes + ["SIGNAL_ID_MISSING"])

    if structure is None or setup_contract is None:
        return _status_payload(symbol=symbol, setup_id=setup_id, signal_id=signal_id, plan_status="NOT_READY", data_quality="INVALID", reason_codes=reason_codes + ["CORE_INPUT_MISSING"])

    contract_status = str(setup_contract.get("contract_status", "NOT_READY")).upper()
    selected_contract = setup_contract.get("selected_contract")
    if contract_status != "READY" or not isinstance(selected_contract, dict):
        return _status_payload(
            symbol=symbol,
            setup_id=setup_id,
            signal_id=signal_id,
            plan_status="NOT_READY",
            reason_codes=reason_codes + ["CONTRACT_NOT_READY"],
            session_downgrade=bool(setup_contract.get("session_downgrade", False)),
        )

    contract_id = str(selected_contract.get("contract_id"))
    contract_full = _contract_by_id(contract_id)
    if contract_full is None:
        reason_codes.append("CONTRACT_REGISTRY_LOOKUP_FAILED")
        contract_full = {}
    direction = str(selected_contract.get("direction", "NEUTRAL")).upper()
    structure_bias = str(structure.get("structure_bias", "NEUTRAL")).upper()
    if (structure_bias == "LONG" and direction == "SHORT") or (structure_bias == "SHORT" and direction == "LONG"):
        return _status_payload(
            symbol=symbol,
            setup_id=setup_id,
            signal_id=signal_id,
            data_quality="INVALID",
            plan_status="INVALID",
            contract_id=contract_id,
            setup_family=selected_contract.get("setup_family"),
            direction=direction,
            entry_model=contract_full.get("entry_model"),
            sl_model=contract_full.get("sl_model"),
            tp_model=contract_full.get("tp_model"),
            session_downgrade=bool(setup_contract.get("session_downgrade", False)),
            regime_alignment=str(selected_contract.get("regime_alignment", "UNKNOWN")),
            liquidity_alignment=str(selected_contract.get("liquidity_alignment", "UNKNOWN")),
            reason_codes=reason_codes + ["STRUCTURE_DIRECTION_CONFLICT"],
        )

    entry = _entry_price(structure, setup_candidate)
    if entry is None:
        entry = _as_float((setup_candidate or {}).get("mid_price"))
    if entry is None:
        return _status_payload(
            symbol=symbol,
            setup_id=setup_id,
            signal_id=signal_id,
            plan_status="NO_PLAN",
            contract_id=contract_id,
            setup_family=selected_contract.get("setup_family"),
            direction=direction,
            entry_model=contract_full.get("entry_model"),
            sl_model=contract_full.get("sl_model"),
            tp_model=contract_full.get("tp_model"),
            session_downgrade=bool(setup_contract.get("session_downgrade", False)),
            regime_alignment=str(selected_contract.get("regime_alignment", "UNKNOWN")),
            liquidity_alignment=str(selected_contract.get("liquidity_alignment", "UNKNOWN")),
            reason_codes=reason_codes + ["ENTRY_UNAVAILABLE"],
        )

    if direction == "LONG":
        sl, tp1, tp2, level_reasons = _long_levels(entry, structure, liquidity, volume_profile)
    elif direction == "SHORT":
        sl, tp1, tp2, level_reasons = _short_levels(entry, structure, liquidity, volume_profile)
    else:
        sl, tp1, tp2, level_reasons = None, None, None, []
    reason_codes.extend(level_reasons)

    sl, tp1, tp2, geometry_reasons = _paper_geometry(direction, entry, sl, tp1, tp2)
    reason_codes.extend(geometry_reasons)

    if direction == "LONG":
        risk = entry - sl
        rew1 = tp1 - entry
        rew2 = tp2 - entry
    else:
        risk = sl - entry
        rew1 = entry - tp1
        rew2 = entry - tp2
    rr1 = rew1 / risk if risk > 0 else None
    rr2 = rew2 / risk if risk > 0 else None
    if rr1 is None or rr2 is None or risk <= 0 or not _geometry_valid(direction, entry, sl, tp1, tp2):
        return _status_payload(
            symbol=symbol,
            setup_id=setup_id,
            signal_id=signal_id,
            data_quality="INVALID",
            plan_status="NO_PLAN",
            contract_id=contract_id,
            setup_family=selected_contract.get("setup_family"),
            direction=direction,
            entry=entry,
            stop_loss=sl,
            tp1=tp1,
            tp2=tp2,
            entry_model=contract_full.get("entry_model"),
            sl_model=contract_full.get("sl_model"),
            tp_model=contract_full.get("tp_model"),
            invalidation_level=sl,
            destination_level_1=tp1,
            destination_level_2=tp2,
            session_downgrade=bool(setup_contract.get("session_downgrade", False)),
            regime_alignment=str(selected_contract.get("regime_alignment", "UNKNOWN")),
            liquidity_alignment=str(selected_contract.get("liquidity_alignment", "UNKNOWN")),
            reason_codes=reason_codes + ["RISK_DISTANCE_INVALID"],
        )

    min_rr1 = _as_float((contract_full.get("rr_policy") or {}).get("min_rr1")) or 1.2
    min_rr2 = _as_float((contract_full.get("rr_policy") or {}).get("min_rr2")) or 1.5
    confidence = _as_float(setup_contract.get("confidence")) or 0.55
    if rr1 < min_rr1 or rr2 < min_rr2:
        reason_codes.append("RR_LOW_METADATA_ONLY")
        confidence *= 0.85
    if str((regime or {}).get("regime_status", "NOT_READY")).upper() != "READY":
        reason_codes.append("REGIME_NOT_READY_METADATA_ONLY")
    if str(selected_contract.get("regime_alignment", "UNKNOWN")).upper() == "MISALIGNED":
        reason_codes.append("REGIME_MISALIGNED_METADATA_ONLY")
        confidence *= 0.9
    if str(selected_contract.get("liquidity_alignment", "UNKNOWN")).upper() == "MISALIGNED":
        reason_codes.append("LIQUIDITY_MISALIGNED_METADATA_ONLY")
        confidence *= 0.9
    if bool(setup_contract.get("session_downgrade", False)):
        reason_codes.append("OFF_SESSION_DOWNGRADE")
        confidence *= 0.9

    plan_id = stable_id("PLAN", symbol, setup_id, signal_id, _utc_now())
    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "record_type": "trade_plan",
        "plan_id": plan_id,
        "parent_id": signal_id,
        "setup_id": setup_id,
        "signal_id": signal_id,
        "parent_setup_id": setup_id,
        "parent_signal_id": signal_id,
        "symbol": symbol,
        "source": {"source_mode": "STATE_FILE"},
        "data_quality": "OK",
        "plan_status": "PLAN_READY",
        "contract_id": contract_id,
        "setup_family": selected_contract.get("setup_family"),
        "direction": direction,
        "side": direction,
        "entry": round(entry, 4),
        "entry_price": round(entry, 4),
        "stop_loss": round(sl, 4),
        "tp1": round(tp1, 4),
        "tp2": round(tp2, 4),
        "rr1": round(rr1, 4),
        "rr2": round(rr2, 4),
        "risk_distance": round(risk, 6),
        "reward_distance_1": round(rew1, 6),
        "reward_distance_2": round(rew2, 6),
        "entry_model": contract_full.get("entry_model"),
        "sl_model": contract_full.get("sl_model"),
        "tp_model": contract_full.get("tp_model"),
        "invalidation_level": round(sl, 4),
        "destination_level_1": round(tp1, 4),
        "destination_level_2": round(tp2, 4),
        "geometry_quality": "PAPER_EXECUTABLE",
        "paper_executable": True,
        "real_trade_allowed": False,
        "plan_confidence": round(max(0.0, min(1.0, confidence)), 3),
        "session_downgrade": bool(setup_contract.get("session_downgrade", False)),
        "regime_alignment": str(selected_contract.get("regime_alignment", "UNKNOWN")),
        "liquidity_alignment": str(selected_contract.get("liquidity_alignment", "UNKNOWN")),
        "reason_codes": sorted(set(reason_codes)) or ["CONTRACT_DRIVEN_PLAN_READY"],
        "feeds_next": FEEDS_NEXT,
        "execution_safety": dict(SAFETY),
    }


def _fake_structure(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "structure_status": "READY",
        "structure_bias": "LONG",
        "swing_highs": [{"price": 102.0}, {"price": 104.0}],
        "swing_lows": [{"price": 98.0}, {"price": 99.0}],
        "equal_highs": [103.5],
        "equal_lows": [98.5],
        "last_hl": 99.0,
        "last_lh": 103.0,
    }


def _fake_contract() -> dict[str, Any]:
    return {
        "contract_status": "READY",
        "selected_contract": {
            "contract_id": "SC003",
            "setup_family": "TREND_CONTINUATION_LONG",
            "direction": "LONG",
            "regime_alignment": "ALIGNED",
            "liquidity_alignment": "ALIGNED",
        },
        "confidence": 0.72,
        "session_downgrade": False,
    }


def run_contract_driven_trade_plan(symbol: str = "BTCUSDT", fake_sample: bool = False) -> dict[str, Any]:
    context = current_runtime_context(symbol)
    payload = build_contract_driven_trade_plan(
        symbol=symbol,
        setup_contract_payload=_fake_contract() if fake_sample else None,
        structure_payload=_fake_structure(symbol) if fake_sample else None,
        setup_candidate_payload={"entry_price": 100.0} if fake_sample else None,
        signal_event_payload={"latest_event": {"setup_id": "SETUP_FAKE", "signal_id": "SIG_FAKE"}} if fake_sample else None,
    )
    payload["context_id"] = context.get("context_id")
    payload["loop_id"] = context.get("loop_id")
    write_json(OUTPUT_PATH, payload)
    _append_jsonl(HISTORY_PATH, payload)
    if payload.get("plan_id"):
        append_event(
            "trade_plan_events.jsonl",
            lineage_record(
                record_type="trade_plan_event",
                event_id=str(payload.get("plan_id")),
                parent_id=str(payload.get("signal_id") or ""),
                setup_id=str(payload.get("setup_id") or ""),
                signal_id=str(payload.get("signal_id") or ""),
                plan_id=str(payload.get("plan_id") or ""),
                context_id=context.get("context_id"),
                loop_id=context.get("loop_id"),
                reason_codes=list(payload.get("reason_codes") or []),
                feeds_next=["decision_events"],
            ),
        )
    return payload
