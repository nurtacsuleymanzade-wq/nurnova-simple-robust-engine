"""Positioning Context Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "POSITIONING_CONTEXT_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_positioning_context.json"
HISTORY_PATH = DATA_DIR / "positioning_context_history.jsonl"

OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
MARKET_REGIME_PATH = STATE_DIR / "latest_market_regime.json"
LIQUIDITY_MAP_PATH = STATE_DIR / "latest_liquidity_map.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"

FUNDING_PATH = STATE_DIR / "latest_funding_state.json"
OPEN_INTEREST_PATH = STATE_DIR / "latest_open_interest_state.json"
LONG_SHORT_PATH = STATE_DIR / "latest_long_short_ratio_state.json"
BASIS_PATH = STATE_DIR / "latest_basis_state.json"
MACRO_RISK_PATH = STATE_DIR / "latest_macro_risk_state.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quality_level(score: float) -> str:
    if score <= 0.0:
        return "MISSING"
    if score >= 0.95:
        return "HIGH"
    if score >= 0.75:
        return "OK"
    if score >= 0.5:
        return "REDUCED"
    return "LOW"


def run_positioning_context_engine() -> dict[str, Any]:
    observation = _load_json(OBSERVATION_PATH) or {}
    market_regime = _load_json(MARKET_REGIME_PATH) or {}
    liquidity_map = _load_json(LIQUIDITY_MAP_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}

    funding_state = _load_json(FUNDING_PATH)
    oi_state = _load_json(OPEN_INTEREST_PATH)
    long_short_state = _load_json(LONG_SHORT_PATH)
    basis_state = _load_json(BASIS_PATH)
    macro_risk_state = _load_json(MACRO_RISK_PATH)

    missing_inputs: list[str] = []
    for name, payload in (
        ("latest_observation_factory", observation),
        ("latest_market_regime", market_regime),
        ("latest_liquidity_map", liquidity_map),
        ("latest_interpretation", interpretation),
    ):
        if not payload:
            missing_inputs.append(name)

    optional_missing: list[str] = []
    if funding_state is None:
        optional_missing.append("latest_funding_state")
    if oi_state is None:
        optional_missing.append("latest_open_interest_state")
    if long_short_state is None:
        optional_missing.append("latest_long_short_ratio_state")
    if basis_state is None:
        optional_missing.append("latest_basis_state")
    if macro_risk_state is None:
        optional_missing.append("latest_macro_risk_state")

    crowded_side = "UNKNOWN"
    squeeze_risk = "UNKNOWN"
    if long_short_state:
        ratio = _safe_float(long_short_state.get("long_short_ratio"))
        if ratio is not None:
            if ratio > 1.2:
                crowded_side = "LONG_CROWDED"
            elif ratio < 0.8:
                crowded_side = "SHORT_CROWDED"
            else:
                crowded_side = "BALANCED"
    regime_bias = str(market_regime.get("directional_bias", "UNKNOWN"))
    trapped_side = "UNKNOWN"
    war_reading = observation.get("war_reading") or {}
    if str(war_reading.get("who_attacked", "UNKNOWN")) == "BUYERS" and str(war_reading.get("who_won", "UNKNOWN")) == "SELLERS":
        trapped_side = "BUYERS_TRAPPED"
    elif str(war_reading.get("who_attacked", "UNKNOWN")) == "SELLERS" and str(war_reading.get("who_won", "UNKNOWN")) == "BUYERS":
        trapped_side = "SELLERS_TRAPPED"
    else:
        trapped_side = "NONE"

    cvd_state = str(((interpretation.get("1m") or {}).get("raw_context") or {}).get("cvd_state", "UNKNOWN"))
    cvd_trap = trapped_side != "NONE" and cvd_state in ("BUY_PRESSURE", "SELL_PRESSURE")

    if crowded_side == "LONG_CROWDED":
        squeeze_risk = "LONG_SQUEEZE_RISK"
    elif crowded_side == "SHORT_CROWDED":
        squeeze_risk = "SHORT_SQUEEZE_RISK"
    elif trapped_side == "BUYERS_TRAPPED":
        squeeze_risk = "LONG_SQUEEZE_RISK"
    elif trapped_side == "SELLERS_TRAPPED":
        squeeze_risk = "SHORT_SQUEEZE_RISK"
    elif regime_bias == "NEUTRAL":
        squeeze_risk = "NONE"

    funding_context = "MISSING"
    if funding_state:
        funding_value = _safe_float(funding_state.get("funding_rate"))
        if funding_value is not None:
            funding_context = "POSITIVE" if funding_value > 0 else "NEGATIVE" if funding_value < 0 else "NEUTRAL"

    basis_context = "MISSING"
    if basis_state:
        basis_value = _safe_float(basis_state.get("basis"))
        if basis_value is not None:
            basis_context = "PREMIUM" if basis_value > 0 else "DISCOUNT" if basis_value < 0 else "NEUTRAL"

    oi_context = "MISSING"
    if oi_state:
        oi_delta = _safe_float(oi_state.get("oi_delta"))
        if oi_delta is not None:
            oi_context = "OI_RISING" if oi_delta > 0 else "OI_FALLING"

    macro_risk = "MISSING"
    if macro_risk_state:
        macro_risk = str(macro_risk_state.get("macro_risk", "NEUTRAL"))

    score = 0.0
    if observation and market_regime and interpretation:
        score += 0.55
    if liquidity_map:
        score += 0.15
    if crowded_side != "UNKNOWN":
        score += 0.15
    if not optional_missing:
        score += 0.15

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(observation.get("symbol") or market_regime.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "POSITIONING_OPTIONAL_CONTEXT",
        },
        "positioning": {
            "crowded_side": crowded_side,
            "squeeze_risk": squeeze_risk,
            "funding_context": funding_context,
            "basis_context": basis_context,
            "oi_context": oi_context,
            "macro_risk": macro_risk,
        },
        "ltf_confirmation": {
            "cvd_trap": cvd_trap,
            "trap_context": trapped_side,
        },
        "reason_codes": [
            f"SYMBOL_{str(observation.get('symbol') or market_regime.get('symbol') or 'BTCUSDT')}",
            *[f"{name.upper()}_MISSING" for name in optional_missing],
            f"DQ_{_quality_level(score)}",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
        ],
        "data_quality": {
            "level": _quality_level(score),
            "missing_inputs": [*missing_inputs, *optional_missing],
        },
        "feeds_next": [
            "UNIFIED_CONTEXT_ENGINE",
            "S15_FLOW_TO_SETUP_CONTEXT",
        ],
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(HISTORY_PATH, output)
    return output


def main() -> None:
    print(json.dumps(run_positioning_context_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
