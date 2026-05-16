from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.research_runtime import current_runtime_context, write_json
from src.simple.setup_contract_registry import load_setup_contract_registry

BLOCK_ID = "SETUP_CONTRACT_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple/epoch_v2")

MARKET_STRUCTURE_V2_PATH = STATE_DIR / "latest_market_structure_v2.json"
REGIME_PATH = STATE_DIR / "latest_regime_classifier.json"
LIQUIDITY_PATH = STATE_DIR / "latest_liquidity_structure.json"
SETUP_CANDIDATE_PATH = STATE_DIR / "latest_setup_candidate.json"
SETUP_FAMILY_ACTIVATION_PATH = STATE_DIR / "latest_setup_family_activation.json"

OUTPUT_PATH = STATE_DIR / "latest_setup_contract.json"
HISTORY_PATH = DATA_DIR / "setup_contract_history.jsonl"

FEEDS_NEXT = ["TRADE_PLAN_ENGINE", "DECISION_GATE", "PAPER_LIFECYCLE"]


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


def _structure_conflict(structure_bias: str, direction: str) -> bool:
    if structure_bias == "LONG" and direction == "SHORT":
        return True
    if structure_bias == "SHORT" and direction == "LONG":
        return True
    return False


def _session_now_utc() -> str:
    hour = datetime.now(timezone.utc).hour
    if 7 <= hour <= 15:
        return "LONDON"
    if 13 <= hour <= 21:
        return "NEW_YORK"
    return "OFF_SESSION"


def build_setup_contract_state(
    symbol: str = "BTCUSDT",
    structure_payload: dict[str, Any] | None = None,
    regime_payload: dict[str, Any] | None = None,
    liquidity_payload: dict[str, Any] | None = None,
    setup_candidate_payload: dict[str, Any] | None = None,
    setup_family_activation_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    structure = structure_payload if structure_payload is not None else _load_json(MARKET_STRUCTURE_V2_PATH)
    regime = regime_payload if regime_payload is not None else _load_json(REGIME_PATH)
    liquidity = liquidity_payload if liquidity_payload is not None else _load_json(LIQUIDITY_PATH)
    _ = setup_candidate_payload if setup_candidate_payload is not None else _load_json(SETUP_CANDIDATE_PATH)
    _ = setup_family_activation_payload if setup_family_activation_payload is not None else _load_json(SETUP_FAMILY_ACTIVATION_PATH)

    reason_codes: list[str] = []
    if structure is None:
        return {
            "timestamp_utc": _utc_now(),
            "block_id": BLOCK_ID,
            "symbol": symbol,
            "data_quality": "INVALID",
            "contract_status": "NOT_READY",
            "selected_contract": None,
            "eligible_contracts": [],
            "blocked_contracts": [],
            "directional_bias": "NEUTRAL",
            "regime": "UNKNOWN",
            "structure_bias": "UNKNOWN",
            "confidence": 0.0,
            "session_downgrade": False,
            "regime_alignment": "UNKNOWN",
            "liquidity_alignment": "UNKNOWN",
            "reason_codes": ["STRUCTURE_SOURCE_MISSING"],
            "feeds_next": FEEDS_NEXT,
        }

    structure_status = str(structure.get("structure_status", "NOT_READY")).upper()
    structure_bias = str(structure.get("structure_bias", "NEUTRAL")).upper()
    if structure_status != "READY":
        return {
            "timestamp_utc": _utc_now(),
            "block_id": BLOCK_ID,
            "symbol": symbol,
            "data_quality": "DEGRADED",
            "contract_status": "NOT_READY",
            "selected_contract": None,
            "eligible_contracts": [],
            "blocked_contracts": [],
            "directional_bias": "NEUTRAL",
            "regime": "UNKNOWN",
            "structure_bias": structure_bias,
            "confidence": 0.0,
            "session_downgrade": False,
            "regime_alignment": "UNKNOWN",
            "liquidity_alignment": "UNKNOWN",
            "reason_codes": ["STRUCTURE_NOT_READY"],
            "feeds_next": FEEDS_NEXT,
        }

    regime_status = str((regime or {}).get("regime_status", "NOT_READY")).upper()
    primary_regime = str((regime or {}).get("primary_regime", "UNKNOWN")).upper()
    directional_bias = str((regime or {}).get("directional_bias", structure_bias)).upper()
    liquidity_context = str((liquidity or {}).get("liquidity_sweep_status", "UNKNOWN")).upper()

    contracts = load_setup_contract_registry()
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    session_name = _session_now_utc()
    session_downgrade = False

    for contract in contracts:
        direction = str(contract.get("direction", "NEUTRAL")).upper()
        if _structure_conflict(structure_bias, direction):
            blocked.append({
                "contract_id": contract["contract_id"],
                "setup_family": contract["setup_family"],
                "direction": direction,
                "reason": "STRUCTURE_DIRECTION_CONFLICT",
            })
            continue

        score = 0.55
        regime_alignment = "UNKNOWN"
        if regime_status != "READY":
            reason_codes.append("REGIME_NOT_READY_METADATA_ONLY")
            score -= 0.05
        else:
            allowed = set(str(x).upper() for x in contract.get("allowed_regimes", []))
            if primary_regime in allowed:
                regime_alignment = "ALIGNED"
                score += 0.15
            else:
                regime_alignment = "MISALIGNED"
                reason_codes.append("REGIME_MISALIGNED_METADATA_ONLY")
                score -= 0.1

        liq_req = [str(x).upper() for x in contract.get("required_liquidity_context", [])]
        liquidity_alignment = "UNKNOWN"
        if liquidity is not None:
            liquidity_alignment = "ALIGNED" if ("ANY" in liq_req or any(r in liquidity_context for r in liq_req)) else "MISALIGNED"
            if liquidity_alignment == "MISALIGNED":
                reason_codes.append("LIQUIDITY_MISALIGNED_METADATA_ONLY")
                score -= 0.08

        allowed_sessions = contract["session_policy"]["allowed_sessions"]
        if session_name not in allowed_sessions:
            session_downgrade = True
            reason_codes.append("OFF_SESSION_DOWNGRADE")
            score -= 0.08

        row = {
            "contract_id": contract["contract_id"],
            "setup_family": contract["setup_family"],
            "direction": direction,
            "score": round(max(0.0, min(1.0, score)), 3),
            "regime_alignment": regime_alignment,
            "liquidity_alignment": liquidity_alignment,
        }
        eligible.append(row)

    eligible = sorted(eligible, key=lambda x: x["score"], reverse=True)
    selected = eligible[0] if eligible else None
    status = "READY" if selected else "NO_VALID_CONTRACT"
    dq = "OK" if status == "READY" else "DEGRADED"

    return {
        "timestamp_utc": _utc_now(),
        "block_id": BLOCK_ID,
        "symbol": symbol,
        "data_quality": dq,
        "contract_status": status,
        "selected_contract": selected,
        "eligible_contracts": eligible,
        "blocked_contracts": blocked,
        "directional_bias": directional_bias if directional_bias in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL",
        "regime": primary_regime,
        "structure_bias": structure_bias,
        "confidence": round(selected["score"], 3) if selected else 0.0,
        "session_downgrade": session_downgrade,
        "regime_alignment": selected["regime_alignment"] if selected else "UNKNOWN",
        "liquidity_alignment": selected["liquidity_alignment"] if selected else "UNKNOWN",
        "reason_codes": sorted(set(reason_codes)) or ["CONTRACT_SELECTION_COMPLETED"],
        "feeds_next": FEEDS_NEXT,
    }


def _fake_structure(symbol: str) -> dict[str, Any]:
    return {"symbol": symbol, "structure_status": "READY", "structure_bias": "LONG"}


def _fake_regime(symbol: str) -> dict[str, Any]:
    return {"symbol": symbol, "regime_status": "READY", "primary_regime": "TREND", "directional_bias": "LONG"}


def run_setup_contract_engine(symbol: str = "BTCUSDT", fake_sample: bool = False) -> dict[str, Any]:
    context = current_runtime_context(symbol)
    payload = build_setup_contract_state(
        symbol=symbol,
        structure_payload=_fake_structure(symbol) if fake_sample else None,
        regime_payload=_fake_regime(symbol) if fake_sample else None,
    )
    payload["context_id"] = context.get("context_id")
    payload["loop_id"] = context.get("loop_id")
    write_json(OUTPUT_PATH, payload)
    _append_jsonl(HISTORY_PATH, payload)
    return payload

