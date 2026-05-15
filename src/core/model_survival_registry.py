from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "state" / "simple" / "epoch_v2" / "model_survival_registry.json"
REPORT_PATH = ROOT / "state" / "simple" / "epoch_v2" / "latest_model_survival_report.json"
BLOCK_REASON = "MODEL_SURVIVAL_REGISTRY_BLOCK"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _model_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(
            item.get("model_id")
            or item.get("dominant_model_id")
            or item.get("primary_model")
            or ((item.get("paper_representative") or {}).get("model_id") if isinstance(item.get("paper_representative"), dict) else "")
            or ""
        )
    return str(item or "")


def load_model_survival_registry() -> dict[str, Any]:
    try:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("registry root is not an object")
        payload["_registry_status"] = "LOADED"
        return payload
    except Exception as exc:
        return {
            "mode": "FAIL_OPEN",
            "active_models": [],
            "quarantined_models": [],
            "_registry_status": f"FAIL_OPEN:{type(exc).__name__}",
            "_fail_open": True,
        }


def get_active_models() -> list[str]:
    return [str(item) for item in (load_model_survival_registry().get("active_models") or [])]


def get_quarantined_models() -> list[str]:
    return [str(item) for item in (load_model_survival_registry().get("quarantined_models") or [])]


def is_model_active(model_id: Any) -> bool:
    registry = load_model_survival_registry()
    if registry.get("_fail_open"):
        return True
    return str(model_id or "") in {str(item) for item in registry.get("active_models") or []}


def is_model_quarantined(model_id: Any) -> bool:
    registry = load_model_survival_registry()
    if registry.get("_fail_open"):
        return False
    return str(model_id or "") in {str(item) for item in registry.get("quarantined_models") or []}


def filter_active_models(items: Iterable[Any]) -> list[Any]:
    registry = load_model_survival_registry()
    if registry.get("_fail_open"):
        return list(items)
    active = {str(item) for item in registry.get("active_models") or []}
    quarantined = {str(item) for item in registry.get("quarantined_models") or []}
    filtered: list[Any] = []
    for item in items:
        model_id = _model_id(item)
        if model_id in quarantined:
            continue
        if active and model_id and model_id not in active:
            continue
        filtered.append(item)
    return filtered


def annotate_block(item: dict[str, Any]) -> dict[str, Any]:
    blocked = dict(item)
    reason_codes = [str(value) for value in blocked.get("reason_codes") or []]
    if BLOCK_REASON not in reason_codes:
        reason_codes.append(BLOCK_REASON)
    blocked["reason_codes"] = reason_codes
    blocked["model_survival_registry_blocked"] = True
    return blocked


def split_active_quarantined(items: Iterable[dict[str, Any]], location: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = load_model_survival_registry()
    if registry.get("_fail_open"):
        return list(items), []
    active_models = {str(item) for item in registry.get("active_models") or []}
    quarantined_models = {str(item) for item in registry.get("quarantined_models") or []}
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in items:
        model_id = _model_id(item)
        if model_id in quarantined_models or (active_models and model_id and model_id not in active_models):
            blocked_item = annotate_block(item)
            blocked_item["blocked_location"] = location
            blocked.append(blocked_item)
            continue
        allowed.append(item)
    return allowed, blocked


def update_model_survival_report(
    *,
    location: str,
    allowed_count: int,
    blocked_items: Iterable[dict[str, Any]],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_model_survival_registry()
    previous: dict[str, Any] = {}
    try:
        previous = json.loads(REPORT_PATH.read_text(encoding="utf-8")) if REPORT_PATH.exists() else {}
    except Exception:
        previous = {}
    blocked_list = list(blocked_items)
    blocked_by_model = Counter(previous.get("blocked_by_model") or {})
    blocked_locations = Counter(previous.get("blocked_locations") or {})
    for item in blocked_list:
        blocked_by_model[_model_id(item) or "UNKNOWN"] += 1
        blocked_locations[str(item.get("blocked_location") or location)] += 1
    output = {
        "timestamp_utc": _utc_now(),
        "block_id": "MODEL_SURVIVAL_REGISTRY",
        "active_models": [str(item) for item in registry.get("active_models") or []],
        "quarantined_models": [str(item) for item in registry.get("quarantined_models") or []],
        "allowed_events_count": int(previous.get("allowed_events_count") or 0) + int(allowed_count),
        "blocked_events_count": int(previous.get("blocked_events_count") or 0) + len(blocked_list),
        "blocked_by_model": dict(blocked_by_model),
        "blocked_locations": dict(blocked_locations),
        "registry_status": registry.get("_registry_status") or "LOADED",
        "execution_safety": {
            "safe_to_open_real_trade": False,
            "private_api_used": False,
            "live_order_sent": False,
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REPORT_PATH.with_suffix(REPORT_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(REPORT_PATH)
    return output
