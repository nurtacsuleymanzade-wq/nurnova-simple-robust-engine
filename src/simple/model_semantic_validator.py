"""Semantic validation gate for model hunter output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MODEL_SEMANTIC_VALIDATOR"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

INPUT_PATH = STATE_DIR / "latest_model_hunter.json"
CLUSTERS_PATH = STATE_DIR / "latest_model_clusters.json"
OUTPUT_PATH = STATE_DIR / "latest_model_semantic_validation.json"
HISTORY_PATH = DATA_DIR / "model_semantic_validation_history.jsonl"

_CONTINUATION_FAMILIES = {
    "VOLATILITY_EXPANSION_CONTINUATION",
    "MOMENTUM_CONTINUATION",
    "ACCEPTANCE_BREAKOUT",
    "INITIATIVE_BREAKOUT",
    "MTF_ALIGNMENT",
}

_TRAP_TOKENS = {
    "TRAP",
    "TRAPPED",
    "FAKE",
    "STOP_RUN",
    "SWEEP",
    "ABSORPTION",
    "FAILED_BREAKOUT",
}

_CONTINUATION_TOKENS = {
    "CONTINUATION",
    "BREAKOUT",
    "INITIATIVE",
    "MOMENTUM",
    "MTF_ALIGNMENT",
    "VOLATILITY_EXPANSION",
    "ACCEPTANCE",
    "REAL_",
}


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


def _is_reversal_family(model_id: str, model_family: str) -> bool:
    text = f"{model_id} {model_family}".upper()
    tokens = {
        "REVERSAL",
        "TRAP",
        "FAILED",
        "ROTATION",
        "ABSORPTION",
        "PREMIUM_DISCOUNT",
        "STOP_RUN",
    }
    return any(token in text for token in tokens)


def _is_continuation_family(model: dict[str, Any]) -> bool:
    text = f"{model.get('model_id', '')} {model.get('model_family', '')}".upper()
    return any(token in text for token in _CONTINUATION_FAMILIES)


def _matched_conditions(model: dict[str, Any]) -> set[str]:
    return {str(item).upper() for item in (model.get("matched_conditions") or [])}


def _condition_text(model: dict[str, Any], matched: set[str]) -> str:
    evidence: list[str] = []
    for result in (model.get("condition_results") or {}).values():
        if not isinstance(result, dict):
            continue
        evidence.extend(str(item) for item in (result.get("evidence") or []))
        evidence.extend(str(item) for item in (result.get("reason_codes") or []))
    return " ".join([
        str(model.get("model_id") or ""),
        str(model.get("model_family") or ""),
        str(model.get("dominant_context") or ""),
        " ".join(matched),
        " ".join(evidence),
    ]).upper()


def _has_supporting_evidence(model: dict[str, Any], matched: set[str]) -> bool:
    if matched:
        return True
    for key in ("condition_score", "match_score", "core_score", "confirmation_score"):
        score = _safe_float(model.get(key))
        if score is not None and score > 0:
            return True
    return False


def _trap_continuation_overlap(model: dict[str, Any], matched: set[str]) -> bool:
    if not _is_continuation_family(model):
        return False
    text = _condition_text(model, matched)
    has_trap = any(token in text for token in _TRAP_TOKENS)
    has_continuation = any(token in text for token in _CONTINUATION_TOKENS)
    return has_trap and has_continuation


def _dominant_validated_cluster_direction() -> str:
    clusters_payload = _load_json(CLUSTERS_PATH) or {}
    clusters = [
        cluster
        for cluster in (clusters_payload.get("clusters") or [])
        if str(cluster.get("direction") or "").upper() in {"LONG", "SHORT"}
    ]
    if not clusters:
        return "NEUTRAL"
    best = max(clusters, key=lambda item: _safe_float(item.get("cluster_score")) or 0.0)
    return str(best.get("direction") or "NEUTRAL").upper()


def _dominant_context(model: dict[str, Any], matched: set[str]) -> str:
    family = str(model.get("model_family") or "UNKNOWN").upper()
    if "TRAP" in family or any("TRAPPED" in item or "TRAP" in item for item in matched):
        return "TRAP_REVERSAL"
    if "SWEEP" in family or any("SWEEP" in item for item in matched):
        return "LIQUIDITY_SWEEP"
    if "ABSORPTION" in family or any("ABSORPTION" in item for item in matched):
        return "ABSORPTION"
    if "ROTATION" in family or any("VALUE" in item or "ROTATION" in item for item in matched):
        return "ROTATION"
    if "CONTINUATION" in family or any("REAL_" in item or "MOMENTUM" in item for item in matched):
        return "CONTINUATION"
    return family or "UNKNOWN"


def _detect_evidence_mismatch(condition_id: str, result: dict[str, Any]) -> list[str]:
    text = " | ".join(str(item) for item in (result.get("evidence") or [])).upper()
    mismatches: list[str] = []
    if condition_id == "COND_REAL_BULLISH" and "CANDLE_TRUTH=REAL_BEARISH" in text:
        mismatches.append("COND_REAL_BULLISH_EVIDENCE_CONTRADICTION")
    if condition_id == "COND_REAL_BEARISH" and "CANDLE_TRUTH=REAL_BULLISH" in text:
        mismatches.append("COND_REAL_BEARISH_EVIDENCE_CONTRADICTION")
    if condition_id == "COND_FAKE_BULLISH" and "CANDLE_TRUTH=REAL_BEARISH" in text:
        mismatches.append("COND_FAKE_BULLISH_EVIDENCE_CONTRADICTION")
    if condition_id == "COND_FAKE_BEARISH" and "CANDLE_TRUTH=REAL_BULLISH" in text:
        mismatches.append("COND_FAKE_BEARISH_EVIDENCE_CONTRADICTION")
    return mismatches


def _pair_contradictions(matched: set[str]) -> list[str]:
    contradictions: list[str] = []
    pairs = [
        ("COND_REAL_BULLISH", "COND_REAL_BEARISH", "REAL_BULL_BEAR_CONTRADICTION"),
        ("COND_FAKE_BULLISH", "COND_REAL_BULLISH", "FAKE_REAL_BULLISH_CONTRADICTION"),
        ("COND_FAKE_BEARISH", "COND_REAL_BEARISH", "FAKE_REAL_BEARISH_CONTRADICTION"),
        ("COND_STRUCTURE_BULLISH", "COND_STRUCTURE_BEARISH", "STRUCTURE_BULL_BEAR_CONTRADICTION"),
        ("COND_REGIME_MOMENTUM", "COND_REGIME_BALANCE", "REGIME_MOMENTUM_BALANCE_CONTRADICTION"),
    ]
    for left, right, code in pairs:
        if left in matched and right in matched:
            contradictions.append(code)
    return contradictions


def _directional_conflict(model: dict[str, Any], matched: set[str]) -> str | None:
    bullish = {
        "COND_REAL_BULLISH",
        "COND_STRUCTURE_BULLISH",
        "COND_POSITIVE_DELTA",
        "COND_BUYERS_ATTACKING",
        "COND_BULLISH_SCENARIO_AVAILABLE",
    }
    bearish = {
        "COND_REAL_BEARISH",
        "COND_STRUCTURE_BEARISH",
        "COND_NEGATIVE_DELTA",
        "COND_SELLERS_ATTACKING",
        "COND_BEARISH_SCENARIO_AVAILABLE",
    }
    bullish_count = len(matched & bullish)
    bearish_count = len(matched & bearish)
    direction = str(model.get("direction") or "UNKNOWN").upper()
    if _is_reversal_family(str(model.get("model_id") or ""), str(model.get("model_family") or "")):
        return None
    if direction == "LONG" and bearish_count > bullish_count:
        return "LONG_DIRECTION_DEPENDS_ON_BEARISH_CONTINUATION"
    if direction == "SHORT" and bullish_count > bearish_count:
        return "SHORT_DIRECTION_DEPENDS_ON_BULLISH_CONTINUATION"
    return None


def _coherence_score(
    semantic_error_count: int,
    contradiction_count: int,
    invalidation_score: float,
    direction_conflict: bool,
) -> float:
    score = 1.0
    score -= min(0.45, semantic_error_count * 0.25)
    score -= min(0.35, contradiction_count * 0.18)
    if invalidation_score >= 0.5:
        score -= 0.3
    if direction_conflict:
        score -= 0.2
    return round(max(0.0, min(1.0, score)), 4)


def _validated_record(
    model: dict[str, Any],
    dominant_cluster_direction: str,
    data_quality_level: str,
) -> dict[str, Any]:
    matched = _matched_conditions(model)
    condition_results = model.get("condition_results") or {}
    semantic_errors: list[str] = []
    for condition_id, result in condition_results.items():
        semantic_errors.extend(_detect_evidence_mismatch(str(condition_id).upper(), result or {}))

    contradictions = _pair_contradictions(matched)
    direction_conflict = _directional_conflict(model, matched)
    if direction_conflict:
        contradictions.append(direction_conflict)

    invalidation_score = _safe_float(model.get("invalidation_score")) or 0.0
    block_reasons: list[str] = []
    risk_tags: list[str] = []
    penalty_score = 0.0
    direct_cluster_direction_conflict = (
        dominant_cluster_direction in {"LONG", "SHORT"}
        and str(model.get("direction") or "").upper() in {"LONG", "SHORT"}
        and str(model.get("direction") or "").upper() != dominant_cluster_direction
    )
    zero_supporting_evidence = not _has_supporting_evidence(model, matched)
    explicit_invalidation_matched = invalidation_score >= 0.5
    data_quality_invalid = str(model.get("data_quality") or data_quality_level or "").upper() == "INVALID"
    mixed_researchable = _trap_continuation_overlap(model, matched)

    if invalidation_score >= 0.5:
        block_reasons.append("INVALIDATION_DOMINANT")
    if direct_cluster_direction_conflict:
        block_reasons.append(f"DOMINANT_CLUSTER_DIRECTION_{dominant_cluster_direction}_CONTRADICTS_MODEL")
    if zero_supporting_evidence:
        block_reasons.append("ZERO_SUPPORTING_EVIDENCE")
    if data_quality_invalid:
        block_reasons.append("DATA_QUALITY_INVALID")
    if semantic_errors:
        risk_tags.append("SEMANTIC_EVIDENCE_MISMATCH_SOFT")
        penalty_score += 0.10
    severe_contradictions = [item for item in contradictions if "CONTRADICTION" in item or "DEPENDS_ON" in item]
    if severe_contradictions:
        if mixed_researchable:
            risk_tags.extend(severe_contradictions)
        else:
            risk_tags.extend(severe_contradictions)
            penalty_score += 0.10
    if mixed_researchable:
        risk_tags.append("TRAP_CONTINUATION_OVERLAP")
        penalty_score += 0.15

    coherence_score = _coherence_score(
        semantic_error_count=len(semantic_errors),
        contradiction_count=len(contradictions),
        invalidation_score=invalidation_score,
        direction_conflict=direction_conflict is not None,
    )
    paper_allowed = not block_reasons
    if paper_allowed and mixed_researchable:
        semantic_status = "MIXED_BUT_RESEARCHABLE"
    elif paper_allowed and coherence_score >= 0.75:
        semantic_status = "VALID"
    elif paper_allowed:
        semantic_status = "WARNING"
    else:
        semantic_status = "BLOCKED"

    return {
        "model_instance_id": model.get("model_instance_id"),
        "timestamp_utc": model.get("timestamp_utc"),
        "symbol": model.get("symbol"),
        "model_id": model.get("model_id"),
        "model_family": model.get("model_family"),
        "direction": model.get("direction"),
        "quality": model.get("quality"),
        "match_score": model.get("match_score"),
        "invalidation_score": invalidation_score,
        "matched_conditions": list(model.get("matched_conditions") or []),
        "dominant_context": _dominant_context(model, matched),
        "semantic_status": semantic_status,
        "paper_allowed": paper_allowed,
        "risk_tags": sorted(set(risk_tags)),
        "penalty_score": round(penalty_score, 4),
        "semantic_errors": semantic_errors,
        "contradictions": contradictions,
        "block_reasons": block_reasons,
        "coherence_score": coherence_score,
        "source_model_instance": model,
    }


def run_model_semantic_validator() -> dict[str, Any]:
    hunter = _load_json(INPUT_PATH) or {}
    detected_models = list(hunter.get("detected_models") or [])
    dominant_cluster_direction = _dominant_validated_cluster_direction()
    data_quality_level = str((hunter.get("data_quality") or {}).get("level") or "HIGH").upper()
    validated_models: list[dict[str, Any]] = []
    blocked_models: list[dict[str, Any]] = []
    semantic_error_count = 0
    contradiction_count = 0
    mixed_count = 0

    for model in detected_models:
        record = _validated_record(model, dominant_cluster_direction, data_quality_level)
        semantic_error_count += len(record.get("semantic_errors") or [])
        contradiction_count += len(record.get("contradictions") or [])
        if record.get("paper_allowed"):
            validated_models.append(record)
            if record.get("semantic_status") == "MIXED_BUT_RESEARCHABLE":
                mixed_count += 1
        else:
            blocked_models.append(record)

    hunter_semantic_health = str(hunter.get("semantic_health") or "PASS")
    if hunter_semantic_health != "PASS" or semantic_error_count > 0:
        semantic_health = "FAIL"
    elif contradiction_count > 0 or blocked_models:
        semantic_health = "WARN"
    else:
        semantic_health = "PASS"

    reason_codes = [
        f"INPUT_DETECTED_{len(detected_models)}",
        f"VALIDATED_{len(validated_models)}",
        f"BLOCKED_{len(blocked_models)}",
        f"SEMANTIC_ERRORS_{semantic_error_count}",
        f"CONTRADICTIONS_{contradiction_count}",
    ]
    if hunter_semantic_health != "PASS":
        reason_codes.append("CONDITION_LIBRARY_SELFTEST_FAILED")

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": str(hunter.get("symbol") or "BTCUSDT"),
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "MODEL_HUNTER_SEMANTIC_VALIDATION",
        },
        "semantic_health": semantic_health,
        "validated_models": validated_models,
        "blocked_models": blocked_models,
        "summary": {
            "input_detected": len(detected_models),
            "validated_count": len(validated_models),
            "mixed_count": mixed_count,
            "blocked_count": len(blocked_models),
            "hard_blocked_count": len(blocked_models),
            "semantic_error_count": semantic_error_count,
            "contradiction_count": contradiction_count,
        },
        "reason_codes": reason_codes,
        "data_quality": {
            "level": "HIGH" if hunter else "LOW",
            "missing_inputs": [] if hunter else ["latest_model_hunter"],
        },
        "feeds_next": [
            "MODEL_CLUSTER_ENGINE",
            "MODEL_COOLDOWN_ENGINE",
            "PAPER_TRADE_FACTORY",
            "RESEARCH_PAPER_LIFECYCLE_ENGINE",
            "RESEARCH_EDGE_MATRIX_ENGINE",
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
    print(json.dumps(run_model_semantic_validator(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
