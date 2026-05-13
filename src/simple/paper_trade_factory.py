"""Paper Trade Factory for model instances."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "PAPER_TRADE_FACTORY"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_paper_trade_factory.json"
HISTORY_PATH = DATA_DIR / "paper_trade_factory_history.jsonl"

MODEL_HUNTER_PATH = STATE_DIR / "latest_model_hunter.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
LIQUIDITY_PATH = STATE_DIR / "latest_liquidity_map.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
ATR_PATH = STATE_DIR / "latest_atr_state.json"


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


def _current_price(observation: dict[str, Any], dna: dict[str, Any]) -> float | None:
    price = _safe_float(((observation.get("market_snapshot") or {}).get("price")))
    if price is not None:
        return price
    return _safe_float((((dna.get("1m") or {}).get("close"))))


def _paper_trade_id(model_instance_id: str, entry: float | None) -> str:
    raw = f"{model_instance_id}|{entry}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _target_reference(direction: str, entry: float, liquidity: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for level in liquidity.get("detected_levels") or []:
        price = _safe_float(level.get("price"))
        if price is None:
            continue
        if direction == "LONG" and price <= entry:
            continue
        if direction == "SHORT" and price >= entry:
            continue
        if best is None:
            best = level
            continue
        best_price = _safe_float(best.get("price"))
        if best_price is None:
            best = level
            continue
        if direction == "LONG" and price < best_price:
            best = level
        if direction == "SHORT" and price > best_price:
            best = level
    return best


def run_paper_trade_factory() -> dict[str, Any]:
    hunter = _load_json(MODEL_HUNTER_PATH) or {}
    observation = _load_json(OBSERVATION_PATH) or {}
    dna = _load_json(DNA_PATH) or {}
    liquidity = _load_json(LIQUIDITY_PATH) or {}
    business_zone = _load_json(BUSINESS_ZONE_PATH) or {}
    atr = _load_json(ATR_PATH) or {}

    current_price = _current_price(observation, dna)
    atr_1m = _safe_float(((atr.get("1m") or {}).get("atr_14")))
    detected_models = list(hunter.get("detected_models") or [])
    trades: list[dict[str, Any]] = []

    for model_instance in detected_models:
        direction = str(model_instance.get("direction"))
        if direction not in ("LONG", "SHORT"):
            continue
        entry = current_price
        invalid_reason = None
        reason_codes: list[str] = []
        if entry is None or entry <= 0:
            invalid_reason = "INVALID_ENTRY_PRICE"
        if atr_1m is not None and atr_1m > 0:
            risk_distance = max(atr_1m, entry * 0.001) if entry is not None else None
        else:
            risk_distance = entry * 0.002 if entry is not None else None
            reason_codes.append("FALLBACK_STOP_DISTANCE_USED")
        if entry is None or risk_distance is None or risk_distance <= 0:
            invalid_reason = invalid_reason or "RISK_DISTANCE_INVALID"

        stop_loss = None
        tp1 = None
        tp2 = None
        rr_tp1 = None
        rr_tp2 = None
        if invalid_reason is None and entry is not None and risk_distance is not None:
            if direction == "LONG":
                stop_loss = round(entry - risk_distance, 8)
                tp1 = round(entry + 1.5 * risk_distance, 8)
                tp2 = round(entry + 2.5 * risk_distance, 8)
            else:
                stop_loss = round(entry + risk_distance, 8)
                tp1 = round(entry - 1.5 * risk_distance, 8)
                tp2 = round(entry - 2.5 * risk_distance, 8)
            rr_tp1 = 1.5
            rr_tp2 = 2.5

        target_ref = _target_reference(direction, entry or 0.0, liquidity) if entry is not None else None
        trade = {
            "paper_trade_id": _paper_trade_id(str(model_instance.get("model_instance_id")), entry),
            "model_instance_id": model_instance.get("model_instance_id"),
            "model_id": model_instance.get("model_id"),
            "model_family": model_instance.get("model_family"),
            "direction": direction,
            "quality": model_instance.get("quality"),
            "match_score": model_instance.get("match_score"),
            "entry": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rr_tp1": rr_tp1,
            "rr_tp2": rr_tp2,
            "risk_distance": risk_distance,
            "target_reference": target_ref,
            "opened_at": _utc_now(),
            "max_holding_seconds": 1800,
            "status": "INVALID" if invalid_reason else "OPEN_CANDIDATE",
            "invalid_reason": invalid_reason,
            "reason_codes": reason_codes,
            "source_model_instance": model_instance,
            "source_business_zone_ref": business_zone.get("timestamp_utc"),
        }
        trades.append(trade)

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(observation.get("symbol") or hunter.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "MODEL_INSTANCE_TO_PAPER_FACTORY",
        },
        "paper_trades": trades,
        "summary": {
            "candidate_models": len(detected_models),
            "paper_trade_candidates": len([trade for trade in trades if trade.get("status") == "OPEN_CANDIDATE"]),
            "invalid_candidates": len([trade for trade in trades if trade.get("status") == "INVALID"]),
        },
        "reason_codes": [
            f"PAPER_TRADES_{len(trades)}",
            "LOW_QUALITY_MODELS_ALLOWED",
            "NO_LIVE_EXECUTION",
            "NO_PRIVATE_API",
            "PAPER_ONLY",
        ],
        "data_quality": {
            "level": "HIGH" if hunter else "LOW",
            "missing_inputs": [name for name, payload in {
                "latest_model_hunter": hunter,
                "latest_observation_factory": observation,
                "latest_mtf_candle_dna": dna,
                "latest_liquidity_map": liquidity,
                "latest_business_zone": business_zone,
                "latest_atr_state": atr,
            }.items() if not payload],
        },
        "feeds_next": [
            "RESEARCH_PAPER_LIFECYCLE_ENGINE",
            "RESEARCH_EDGE_MATRIX_ENGINE",
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
    print(json.dumps(run_paper_trade_factory(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
