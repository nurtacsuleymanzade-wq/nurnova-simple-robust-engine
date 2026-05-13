"""Cooldown control for clustered paper-trade candidates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "MODEL_COOLDOWN_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

CLUSTERS_PATH = STATE_DIR / "latest_model_clusters.json"
MARKET_STRUCTURE_PATH = STATE_DIR / "latest_market_structure.json"
INTERPRETATION_PATH = STATE_DIR / "latest_interpretation.json"
LIFECYCLE_HISTORY_PATH = DATA_DIR / "research_paper_lifecycle_history.jsonl"
HISTORY_PATH = DATA_DIR / "model_cooldown_history.jsonl"
OUTPUT_PATH = STATE_DIR / "latest_model_cooldown.json"

DEFAULT_COOLDOWN_SECONDS = 180
POST_CLOSE_COOLDOWN_SECONDS = 60


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


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _clean_token(value: Any) -> str:
    text = str(value or "UNKNOWN").upper().replace("|", "/").strip()
    return text or "UNKNOWN"


def _cluster_family(cluster: dict[str, Any]) -> str:
    representative = cluster.get("paper_representative") or {}
    source_model = representative.get("source_model_instance") or {}
    return _clean_token(
        cluster.get("cluster_family")
        or cluster.get("model_family")
        or representative.get("model_family")
        or source_model.get("model_family")
    )


def _cluster_context_fields(
    symbol: str,
    cluster: dict[str, Any],
    market_structure: dict[str, Any],
    interpretation: dict[str, Any],
) -> dict[str, str]:
    representative = cluster.get("paper_representative") or {}
    source_model = representative.get("source_model_instance") or {}
    int_1m = interpretation.get("1m") or {}
    raw_context = int_1m.get("raw_context") or {}
    structure_1m = market_structure.get("1m") or {}
    return {
        "symbol": _clean_token(symbol),
        "model_family": _cluster_family(cluster),
        "direction": _clean_token(cluster.get("direction") or representative.get("direction") or source_model.get("direction")),
        "structure_label": _clean_token(
            cluster.get("structure_label")
            or representative.get("structure_label")
            or source_model.get("structure_label")
            or raw_context.get("structure")
            or structure_1m.get("structure_label")
        ),
        "candle_category": _clean_token(
            cluster.get("candle_category")
            or representative.get("candle_category")
            or source_model.get("candle_category")
            or raw_context.get("candle_category")
        ),
        "liquidity_event": _clean_token(
            cluster.get("liquidity_event")
            or representative.get("liquidity_event")
            or source_model.get("liquidity_event")
            or raw_context.get("liquidity_event")
        ),
    }


def _cooldown_key(fields: dict[str, str]) -> str:
    return "|".join(
        fields.get(name, "UNKNOWN")
        for name in (
            "symbol",
            "model_family",
            "direction",
            "structure_label",
            "candle_category",
            "liquidity_event",
        )
    )


def _broad_key(fields: dict[str, str]) -> str:
    return "|".join(fields.get(name, "UNKNOWN") for name in ("symbol", "model_family", "direction"))


def _context_signature(fields: dict[str, str]) -> str:
    return "|".join(fields.get(name, "UNKNOWN") for name in ("structure_label", "candle_category", "liquidity_event"))


def _trade_fields(symbol: str, trade: dict[str, Any]) -> dict[str, str]:
    existing_fields = trade.get("cooldown_granularity_fields") or {}
    if existing_fields:
        return {
            "symbol": _clean_token(existing_fields.get("symbol") or symbol),
            "model_family": _clean_token(existing_fields.get("model_family")),
            "direction": _clean_token(existing_fields.get("direction")),
            "structure_label": _clean_token(existing_fields.get("structure_label")),
            "candle_category": _clean_token(existing_fields.get("candle_category")),
            "liquidity_event": _clean_token(existing_fields.get("liquidity_event")),
        }

    existing = str(trade.get("cooldown_key") or "")
    if existing:
        parts = existing.split("|")
        if len(parts) >= 6:
            return {
                "symbol": _clean_token(parts[0]),
                "model_family": _clean_token(parts[1]),
                "direction": _clean_token(parts[2]),
                "structure_label": _clean_token(parts[3]),
                "candle_category": _clean_token(parts[4]),
                "liquidity_event": _clean_token(parts[5]),
            }
        if len(parts) >= 3:
            return {
                "symbol": _clean_token(parts[0]),
                "model_family": _clean_token(parts[1]),
                "direction": _clean_token(parts[2]),
                "structure_label": "UNKNOWN",
                "candle_category": "UNKNOWN",
                "liquidity_event": "UNKNOWN",
            }

    source_cluster = trade.get("source_cluster") or {}
    representative = source_cluster.get("paper_representative") or trade.get("source_model_instance") or {}
    family = str(trade.get("model_family") or ((trade.get("source_cluster") or {}).get("cluster_family")) or "UNKNOWN")
    return {
        "symbol": _clean_token(symbol),
        "model_family": _clean_token(family),
        "direction": _clean_token(trade.get("direction")),
        "structure_label": _clean_token(source_cluster.get("structure_label") or representative.get("structure_label")),
        "candle_category": _clean_token(source_cluster.get("candle_category") or representative.get("candle_category")),
        "liquidity_event": _clean_token(source_cluster.get("liquidity_event") or representative.get("liquidity_event")),
    }


def _load_recent_trade_events() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    exact_events: dict[str, dict[str, Any]] = {}
    broad_events: dict[str, dict[str, Any]] = {}
    if not LIFECYCLE_HISTORY_PATH.exists():
        return exact_events, broad_events
    try:
        lines = [line for line in LIFECYCLE_HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return exact_events, broad_events
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        symbol = str(payload.get("symbol") or "BTCUSDT")
        for trade in payload.get("new_trades_opened") or []:
            fields = _trade_fields(symbol, trade)
            key = _cooldown_key(fields)
            broad = _broad_key(fields)
            exact_events.setdefault(key, {})["last_opened"] = _parse_ts(trade.get("opened_at_utc") or trade.get("opened_at"))
            exact_events[key]["context_signature"] = _context_signature(fields)
            broad_events.setdefault(broad, {})["last_opened"] = _parse_ts(trade.get("opened_at_utc") or trade.get("opened_at"))
            broad_events[broad]["context_signature"] = _context_signature(fields)
            broad_events[broad]["cooldown_key"] = key
        for trade in payload.get("trades_closed_this_loop") or []:
            fields = _trade_fields(symbol, trade)
            key = _cooldown_key(fields)
            broad = _broad_key(fields)
            exact_events.setdefault(key, {})["last_closed"] = _parse_ts(trade.get("closed_at_utc") or trade.get("closed_at"))
            exact_events[key]["context_signature"] = _context_signature(fields)
            broad_events.setdefault(broad, {})["last_closed"] = _parse_ts(trade.get("closed_at_utc") or trade.get("closed_at"))
            broad_events[broad]["context_signature"] = _context_signature(fields)
            broad_events[broad]["cooldown_key"] = key
    return exact_events, broad_events


def _cooldown_state(record: dict[str, Any], now_dt: datetime) -> tuple[str, int]:
    last_opened = record.get("last_opened")
    last_closed = record.get("last_closed")
    if last_opened is not None:
        elapsed = int((now_dt - last_opened).total_seconds())
        if elapsed < DEFAULT_COOLDOWN_SECONDS:
            return "MODEL_COOLDOWN_ACTIVE", DEFAULT_COOLDOWN_SECONDS - max(0, elapsed)
    if last_closed is not None:
        elapsed = int((now_dt - last_closed).total_seconds())
        if elapsed < POST_CLOSE_COOLDOWN_SECONDS:
            return "MODEL_RECENTLY_CLOSED", POST_CLOSE_COOLDOWN_SECONDS - max(0, elapsed)
    return "", 0


def run_model_cooldown_engine() -> dict[str, Any]:
    clusters_payload = _load_json(CLUSTERS_PATH) or {}
    market_structure = _load_json(MARKET_STRUCTURE_PATH) or {}
    interpretation = _load_json(INTERPRETATION_PATH) or {}
    clusters = list(clusters_payload.get("clusters") or [])
    symbol = str(clusters_payload.get("symbol") or "BTCUSDT")
    now_dt = datetime.now(timezone.utc)
    exact_events, broad_events = _load_recent_trade_events()

    allowed_clusters: list[dict[str, Any]] = []
    soft_allowed_clusters: list[dict[str, Any]] = []
    blocked_clusters: list[dict[str, Any]] = []
    for cluster in clusters:
        enriched = dict(cluster)
        fields = _cluster_context_fields(symbol, enriched, market_structure, interpretation)
        cooldown_key = _cooldown_key(fields)
        broad_key = _broad_key(fields)
        context_signature = _context_signature(fields)
        record = exact_events.get(cooldown_key) or {}
        broad_record = broad_events.get(broad_key) or {}
        cooldown_reason, cooldown_remaining = _cooldown_state(record, now_dt)
        broad_reason, broad_remaining = _cooldown_state(broad_record, now_dt)
        cooldown_status = "ALLOWED"
        soft_allowed = False
        risk_tags = list(enriched.get("risk_tags") or [])

        if cooldown_reason:
            cooldown_status = "BLOCKED"
        elif broad_reason:
            previous_signature = str(broad_record.get("context_signature") or "UNKNOWN|UNKNOWN|UNKNOWN")
            current_has_context = context_signature != "UNKNOWN|UNKNOWN|UNKNOWN"
            if current_has_context and previous_signature != context_signature:
                cooldown_status = "SOFT_ALLOWED_CONTEXT_CHANGED"
                cooldown_reason = broad_reason
                cooldown_remaining = broad_remaining
                soft_allowed = True
                risk_tags.append("COOLDOWN_CONTEXT_CHANGED")
            else:
                cooldown_status = "BLOCKED"
                cooldown_reason = broad_reason
                cooldown_remaining = broad_remaining

        reason_codes = list(enriched.get("reason_codes") or [])
        if broad_record and not record:
            reason_codes.append("BROAD_CONTEXT_COOLDOWN_MATCH")

        enriched["cooldown_key"] = cooldown_key
        enriched["cooldown_granularity_fields"] = fields
        enriched["cooldown_status"] = cooldown_status
        enriched["paper_allowed_after_cooldown"] = cooldown_status in {"ALLOWED", "SOFT_ALLOWED_CONTEXT_CHANGED"}
        enriched["paper_allowed"] = enriched["paper_allowed_after_cooldown"]
        enriched["cooldown_remaining_seconds"] = cooldown_remaining
        enriched["cooldown_reason"] = cooldown_reason
        enriched["risk_tags"] = sorted(set(risk_tags))
        enriched["reason_codes"] = sorted(set(reason_codes))

        representative = dict(enriched.get("paper_representative") or {})
        representative["cooldown_key"] = cooldown_key
        representative["cooldown_granularity_fields"] = fields
        representative["cooldown_status"] = cooldown_status
        representative["paper_allowed_after_cooldown"] = enriched["paper_allowed_after_cooldown"]
        representative["paper_allowed"] = enriched["paper_allowed_after_cooldown"]
        representative["cooldown_remaining_seconds"] = cooldown_remaining
        representative["cooldown_reason"] = cooldown_reason
        representative["risk_tags"] = sorted(set([*(representative.get("risk_tags") or []), *risk_tags]))
        enriched["paper_representative"] = representative

        if enriched["paper_allowed_after_cooldown"]:
            allowed_clusters.append(enriched)
            if soft_allowed:
                soft_allowed_clusters.append(enriched)
        else:
            blocked_clusters.append(enriched)

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": symbol,
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "CLUSTER_COOLDOWN_CONTROL",
        },
        "allowed_clusters": allowed_clusters,
        "soft_allowed_clusters": soft_allowed_clusters,
        "blocked_clusters": blocked_clusters,
        "cooldown_allowed_count": len(allowed_clusters),
        "cooldown_soft_allowed_count": len(soft_allowed_clusters),
        "cooldown_blocked_count": len(blocked_clusters),
        "summary": {
            "input_clusters": len(clusters),
            "allowed_count": len(allowed_clusters),
            "soft_allowed_count": len(soft_allowed_clusters),
            "blocked_count": len(blocked_clusters),
            "cooldown_allowed_count": len(allowed_clusters),
            "cooldown_soft_allowed_count": len(soft_allowed_clusters),
            "cooldown_blocked_count": len(blocked_clusters),
        },
        "reason_codes": [
            f"INPUT_CLUSTERS_{len(clusters)}",
            f"ALLOWED_{len(allowed_clusters)}",
            f"SOFT_ALLOWED_{len(soft_allowed_clusters)}",
            f"BLOCKED_{len(blocked_clusters)}",
        ],
        "data_quality": {
            "level": "HIGH" if clusters_payload else "LOW",
            "missing_inputs": [name for name, payload in {
                "latest_model_clusters": clusters_payload,
                "research_paper_lifecycle_history": LIFECYCLE_HISTORY_PATH.exists(),
                "model_cooldown_history": HISTORY_PATH.exists(),
            }.items() if not payload],
        },
        "feeds_next": [
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
    print(json.dumps(run_model_cooldown_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
