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


def _cooldown_key(symbol: str, cluster: dict[str, Any]) -> str:
    cluster_family = str(cluster.get("cluster_family") or cluster.get("model_family") or "UNKNOWN")
    direction = str(cluster.get("direction") or "UNKNOWN")
    zone = _safe_float(cluster.get("entry_zone_bucket"))
    zone_text = "UNKNOWN" if zone is None else f"{zone:.8f}"
    return f"{symbol}|{cluster_family}|{direction}|{zone_text}"


def _opposite_key(symbol: str, cluster: dict[str, Any]) -> str:
    cluster_family = str(cluster.get("cluster_family") or cluster.get("model_family") or "UNKNOWN")
    direction = "SHORT" if str(cluster.get("direction") or "").upper() == "LONG" else "LONG"
    zone = _safe_float(cluster.get("entry_zone_bucket"))
    zone_text = "UNKNOWN" if zone is None else f"{zone:.8f}"
    return f"{symbol}|{cluster_family}|{direction}|{zone_text}"


def _trade_key(symbol: str, trade: dict[str, Any]) -> str:
    existing = str(trade.get("cooldown_key") or "")
    if existing:
        return existing
    family = str(trade.get("model_family") or ((trade.get("source_cluster") or {}).get("cluster_family")) or "UNKNOWN")
    direction = str(trade.get("direction") or "UNKNOWN")
    zone = _safe_float(trade.get("entry")) or _safe_float((trade.get("source_cluster") or {}).get("entry_zone_bucket"))
    zone_text = "UNKNOWN" if zone is None else f"{zone:.8f}"
    return f"{symbol}|{family}|{direction}|{zone_text}"


def _load_recent_trade_events() -> dict[str, dict[str, datetime | None]]:
    events: dict[str, dict[str, datetime | None]] = {}
    if not LIFECYCLE_HISTORY_PATH.exists():
        return events
    try:
        lines = [line for line in LIFECYCLE_HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return events
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        symbol = str(payload.get("symbol") or "BTCUSDT")
        for trade in payload.get("new_trades_opened") or []:
            key = _trade_key(symbol, trade)
            events.setdefault(key, {})["last_opened"] = _parse_ts(trade.get("opened_at"))
        for trade in payload.get("trades_closed_this_loop") or []:
            key = _trade_key(symbol, trade)
            events.setdefault(key, {})["last_closed"] = _parse_ts(trade.get("closed_at"))
    return events


def run_model_cooldown_engine() -> dict[str, Any]:
    clusters_payload = _load_json(CLUSTERS_PATH) or {}
    clusters = list(clusters_payload.get("clusters") or [])
    symbol = str(clusters_payload.get("symbol") or "BTCUSDT")
    now_dt = datetime.now(timezone.utc)
    events = _load_recent_trade_events()

    allowed_clusters: list[dict[str, Any]] = []
    blocked_clusters: list[dict[str, Any]] = []
    for cluster in clusters:
        enriched = dict(cluster)
        cooldown_key = _cooldown_key(symbol, enriched)
        opposite_key = _opposite_key(symbol, enriched)
        record = events.get(cooldown_key) or {}
        opposite_record = events.get(opposite_key) or {}
        last_opened = record.get("last_opened")
        last_closed = record.get("last_closed")
        cooldown_remaining = 0
        cooldown_reason = ""

        if last_opened is not None:
            elapsed = int((now_dt - last_opened).total_seconds())
            if elapsed < DEFAULT_COOLDOWN_SECONDS:
                cooldown_remaining = DEFAULT_COOLDOWN_SECONDS - max(0, elapsed)
                cooldown_reason = "MODEL_COOLDOWN_ACTIVE"

        if not cooldown_reason and last_closed is not None:
            elapsed = int((now_dt - last_closed).total_seconds())
            if elapsed < POST_CLOSE_COOLDOWN_SECONDS:
                cooldown_remaining = POST_CLOSE_COOLDOWN_SECONDS - max(0, elapsed)
                cooldown_reason = "MODEL_RECENTLY_CLOSED"

        reason_codes = list(enriched.get("reason_codes") or [])
        if opposite_record.get("last_opened") is not None or opposite_record.get("last_closed") is not None:
            reason_codes.append("OPPOSITE_DIRECTION_CLUSTER")

        enriched["cooldown_key"] = cooldown_key
        enriched["paper_allowed_after_cooldown"] = cooldown_reason == ""
        enriched["cooldown_remaining_seconds"] = cooldown_remaining
        enriched["cooldown_reason"] = cooldown_reason
        enriched["reason_codes"] = sorted(set(reason_codes))

        representative = dict(enriched.get("paper_representative") or {})
        representative["cooldown_key"] = cooldown_key
        representative["paper_allowed_after_cooldown"] = enriched["paper_allowed_after_cooldown"]
        representative["cooldown_remaining_seconds"] = cooldown_remaining
        representative["cooldown_reason"] = cooldown_reason
        enriched["paper_representative"] = representative

        if enriched["paper_allowed_after_cooldown"]:
            allowed_clusters.append(enriched)
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
        "blocked_clusters": blocked_clusters,
        "summary": {
            "input_clusters": len(clusters),
            "allowed_count": len(allowed_clusters),
            "blocked_count": len(blocked_clusters),
        },
        "reason_codes": [
            f"INPUT_CLUSTERS_{len(clusters)}",
            f"ALLOWED_{len(allowed_clusters)}",
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
