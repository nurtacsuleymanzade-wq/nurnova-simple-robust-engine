"""Model Hunter Engine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.model_condition_library import evaluate_condition

BLOCK_ID = "MODEL_HUNTER_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_model_hunter.json"
HISTORY_PATH = DATA_DIR / "model_hunter_history.jsonl"

MODEL_DEFINITIONS_PATH = STATE_DIR / "latest_model_definitions.json"
OBSERVATION_PATH = STATE_DIR / "latest_observation_factory.json"
DNA_PATH = STATE_DIR / "latest_mtf_candle_dna.json"
STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
LIQUIDITY_PATH = STATE_DIR / "latest_liquidity_map.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
SCENARIOS_PATH = STATE_DIR / "latest_three_scenarios.json"
BUSINESS_ZONE_PATH = STATE_DIR / "latest_business_zone.json"
REGIME_PATH = STATE_DIR / "latest_market_regime.json"
INTENT_PATH = STATE_DIR / "latest_intent_analysis.json"
POSITIONING_PATH = STATE_DIR / "latest_positioning_context.json"
UNIFIED_CONTEXT_PATH = STATE_DIR / "latest_unified_context.json"
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


def _quality_level(score: float) -> str:
    if score >= 0.85:
        return "A_PLUS"
    if score >= 0.70:
        return "HIGH"
    if score >= 0.50:
        return "MEDIUM"
    if score >= 0.30:
        return "LOW"
    return "UNKNOWN"


def _build_state_bundle() -> dict[str, Any]:
    return {
        "observation": _load_json(OBSERVATION_PATH) or {},
        "dna": _load_json(DNA_PATH) or {},
        "structure": _load_json(STRUCTURE_PATH) or {},
        "liquidity": _load_json(LIQUIDITY_PATH) or {},
        "interpretation": _load_json(INTERPRETATION_PATH) or {},
        "scenarios": _load_json(SCENARIOS_PATH) or {},
        "business_zone": _load_json(BUSINESS_ZONE_PATH) or {},
        "regime": _load_json(REGIME_PATH) or {},
        "intent": _load_json(INTENT_PATH) or {},
        "positioning": _load_json(POSITIONING_PATH) or {},
        "unified_context": _load_json(UNIFIED_CONTEXT_PATH) or {},
        "atr": _load_json(ATR_PATH) or {},
    }


def _score_group(condition_ids: list[str], state: dict[str, Any]) -> tuple[float, dict[str, dict[str, Any]]]:
    if not condition_ids:
        return 0.0, {}
    results = {condition_id: evaluate_condition(condition_id, state) for condition_id in condition_ids}
    matched = sum(1 for result in results.values() if result.get("status") == "MATCHED")
    return round(matched / len(condition_ids), 4), results


def _flatten_evidence(results: dict[str, dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for condition_id, result in results.items():
        if result.get("status") == "MATCHED":
            entries = result.get("evidence") or []
            if entries:
                evidence.append(f"{condition_id}: {entries[0]}")
    return evidence


def _flatten_contradictions(results: dict[str, dict[str, Any]]) -> list[str]:
    contradictions: list[str] = []
    for condition_id, result in results.items():
        if result.get("status") == "MATCHED":
            contradictions.append(condition_id)
    return contradictions


def _instance_id(model_id: str, direction: str, symbol: str, state: dict[str, Any]) -> str:
    obs_ts = str((state.get("observation") or {}).get("timestamp_utc") or "")
    dna_ts = str((state.get("dna") or {}).get("timestamp_utc") or "")
    raw = f"{symbol}|{model_id}|{direction}|{obs_ts}|{dna_ts}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _source_state_refs(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "observation": (state.get("observation") or {}).get("timestamp_utc"),
        "dna": (state.get("dna") or {}).get("timestamp_utc"),
        "structure": (state.get("structure") or {}).get("timestamp_utc"),
        "liquidity": (state.get("liquidity") or {}).get("timestamp_utc"),
        "interpretation": (state.get("interpretation") or {}).get("timestamp_utc"),
        "business_zone": (state.get("business_zone") or {}).get("timestamp_utc"),
        "regime": (state.get("regime") or {}).get("timestamp_utc"),
        "intent": (state.get("intent") or {}).get("timestamp_utc"),
        "unified_context": (state.get("unified_context") or {}).get("timestamp_utc"),
    }


def _matched_list(results: dict[str, dict[str, Any]], status: str) -> list[str]:
    return [condition_id for condition_id, result in results.items() if result.get("status") == status]


def run_model_hunter_engine() -> dict[str, Any]:
    definitions_payload = _load_json(MODEL_DEFINITIONS_PATH) or {}
    models = list(definitions_payload.get("models") or [])
    state = _build_state_bundle()
    symbol = str((state.get("observation") or {}).get("symbol") or "BTCUSDT")
    missing_inputs = [name for name, payload in state.items() if not payload]

    detected_models: list[dict[str, Any]] = []
    no_trade_models: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for model in models:
        groups = model.get("condition_groups") or {}
        weights = model.get("condition_weights") or {}
        core_score, core_results = _score_group(groups.get("core") or [], state)
        confirmation_score, confirmation_results = _score_group(groups.get("confirmation") or [], state)
        optional_score, optional_results = _score_group(groups.get("optional") or [], state)
        invalidation_score, invalidation_results = _score_group(groups.get("invalidation") or [], state)

        final_score = (
            float(weights.get("core", 0.5)) * core_score
            + float(weights.get("confirmation", 0.3)) * confirmation_score
            + float(weights.get("optional", 0.2)) * optional_score
            - float(weights.get("invalidation_penalty", 0.25)) * invalidation_score
        )
        final_score = round(max(0.0, min(1.0, final_score)), 4)
        quality = _quality_level(final_score)

        condition_results = {}
        condition_results.update(core_results)
        condition_results.update(confirmation_results)
        condition_results.update(optional_results)
        condition_results.update(invalidation_results)

        instance = {
            "model_instance_id": _instance_id(str(model.get("model_id")), str(model.get("direction")), symbol, state),
            "timestamp_utc": _utc_now(),
            "symbol": symbol,
            "model_id": model.get("model_id"),
            "model_family": model.get("model_family"),
            "direction": model.get("direction"),
            "quality": quality,
            "condition_score": final_score,
            "match_score": final_score,
            "core_score": core_score,
            "confirmation_score": confirmation_score,
            "optional_score": optional_score,
            "invalidation_score": invalidation_score,
            "matched_conditions": _matched_list(condition_results, "MATCHED"),
            "missing_conditions": _matched_list(condition_results, "MISSING"),
            "unknown_conditions": _matched_list(condition_results, "UNKNOWN"),
            "contradicting_conditions": _flatten_contradictions(invalidation_results),
            "condition_results": condition_results,
            "supporting_evidence": _flatten_evidence(condition_results),
            "contradicting_evidence": _flatten_evidence(invalidation_results),
            "entry_logic": model.get("entry_logic"),
            "stop_logic": model.get("stop_logic"),
            "target_logic": model.get("target_logic"),
            "timeframe_behavior": model.get("timeframe_behavior") or {},
            "timeframe_focus": ["1m", "5m", "15m"],
            "is_research_trade_allowed": bool(model.get("opens_paper_trade")) and str(model.get("direction")) in ("LONG", "SHORT") and final_score >= 0.30,
            "source_state_refs": _source_state_refs(state),
        }

        dedup_key = (
            str(instance["model_id"]),
            str(instance["direction"]),
            str((state.get("observation") or {}).get("timestamp_utc") or instance["timestamp_utc"])[:16],
        )
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        if str(model.get("model_family")) == "NO_TRADE":
            if final_score >= 0.30:
                no_trade_models.append(instance)
            continue

        if final_score >= 0.30 and str(model.get("direction")) in ("LONG", "SHORT") and bool(model.get("opens_paper_trade")):
            detected_models.append(instance)

    top_model = max(detected_models, key=lambda item: item.get("match_score", 0.0), default=None)
    output = {
        "timestamp_utc": _utc_now(),
        "symbol": symbol,
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "MODEL_DEFINITION_EVALUATION",
        },
        "detected_models": detected_models,
        "no_trade_models": no_trade_models,
        "summary": {
            "definitions_total": len(models),
            "detected_count": len(detected_models),
            "no_trade_count": len(no_trade_models),
            "top_model_id": top_model.get("model_id") if top_model else None,
            "top_model_quality": top_model.get("quality") if top_model else None,
            "top_model_score": top_model.get("match_score") if top_model else None,
        },
        "reason_codes": [
            f"DETECTED_{len(detected_models)}",
            f"NO_TRADE_{len(no_trade_models)}",
            "LOW_QUALITY_MODELS_ALLOWED",
            "NO_FAKE_DATA",
            "SAFE_TO_OPEN_REAL_TRADE_FALSE",
            "NO_PRIVATE_API",
            "PAPER_ONLY_RESEARCH",
        ],
        "data_quality": {
            "level": "HIGH" if models else "LOW",
            "missing_inputs": missing_inputs + ([] if models else ["latest_model_definitions"]),
        },
        "feeds_next": [
            "PAPER_TRADE_FACTORY",
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
    print(json.dumps(run_model_hunter_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
