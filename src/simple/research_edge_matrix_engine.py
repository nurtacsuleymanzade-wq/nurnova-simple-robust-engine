"""Research Edge Matrix Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCK_ID = "RESEARCH_EDGE_MATRIX_ENGINE"
STATE_DIR = Path("state/simple")
DATA_DIR = Path("data/simple")

OUTPUT_PATH = STATE_DIR / "latest_research_edge_matrix.json"
HISTORY_PATH = DATA_DIR / "research_edge_matrix_history.jsonl"
LIFECYCLE_HISTORY_PATH = DATA_DIR / "research_paper_lifecycle_history.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _maturity(sample_size: int) -> str:
    if sample_size < 10:
        return "SAMPLE_BUILDING"
    if sample_size < 30:
        return "EARLY_READ"
    if sample_size < 100:
        return "RESEARCH_EDGE"
    return "VALIDATED_CANDIDATE"


def _load_closed_trades() -> list[dict[str, Any]]:
    if not LIFECYCLE_HISTORY_PATH.exists():
        return []
    try:
        lines = [line for line in LIFECYCLE_HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return []
    closed_by_id: dict[str, dict[str, Any]] = {}
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        for trade in payload.get("closed_trades") or []:
            trade_id = str(trade.get("paper_trade_id") or "")
            if trade_id:
                closed_by_id[trade_id] = trade
    return list(closed_by_id.values())


def _group_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    sample_size = len(items)
    wins = sum(1 for item in items if str(item.get("status")) in ("TP1_HIT", "TP2_HIT"))
    losses = sum(1 for item in items if str(item.get("status")) == "SL_HIT")
    expired = sum(1 for item in items if str(item.get("status")) == "EXPIRED")
    winrate = round(wins / sample_size, 4) if sample_size else None
    r_values = [_safe_float(item.get("realized_r")) for item in items if _safe_float(item.get("realized_r")) is not None]
    expectancy = round(sum(r_values) / len(r_values), 4) if r_values else None
    mfe_values = [_safe_float(item.get("mfe")) or 0.0 for item in items]
    mae_values = [_safe_float(item.get("mae")) or 0.0 for item in items]
    return {
        "sample_size": sample_size,
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "winrate": winrate,
        "avg_r": expectancy,
        "expectancy": expectancy,
        "avg_mfe": round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else None,
        "avg_mae": round(sum(mae_values) / len(mae_values), 4) if mae_values else None,
        "maturity": _maturity(sample_size),
    }


def run_research_edge_matrix_engine() -> dict[str, Any]:
    closed_trades = _load_closed_trades()
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    cluster_grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = {}

    for trade in closed_trades:
        base_key = (
            str(trade.get("model_id") or "UNKNOWN"),
            str(trade.get("model_family") or "UNKNOWN"),
            str(trade.get("direction") or "UNKNOWN"),
            str(trade.get("quality") or "UNKNOWN"),
        )
        grouped.setdefault(base_key, []).append(trade)

        cluster = trade.get("source_cluster") or {}
        cluster_key = (
            str(trade.get("model_id") or "UNKNOWN"),
            str(trade.get("model_family") or "UNKNOWN"),
            str(trade.get("direction") or "UNKNOWN"),
            str(trade.get("quality") or "UNKNOWN"),
            str(cluster.get("cluster_family") or trade.get("model_family") or "UNKNOWN"),
            str(trade.get("dominant_model_id") or cluster.get("dominant_model_id") or trade.get("model_id") or "UNKNOWN"),
        )
        cluster_grouped.setdefault(cluster_key, []).append(trade)

    groups_output: list[dict[str, Any]] = []
    for (model_id, model_family, direction, quality), items in grouped.items():
        cluster_family = str(((items[0].get("source_cluster") or {}).get("cluster_family")) or model_family)
        dominant_model_id = str(items[0].get("dominant_model_id") or model_id)
        cluster_metrics = _group_metrics([
            trade for trade in closed_trades
            if str(((trade.get("source_cluster") or {}).get("cluster_family")) or trade.get("model_family") or "UNKNOWN") == cluster_family
            and str(trade.get("dominant_model_id") or trade.get("model_id") or "UNKNOWN") == dominant_model_id
        ])
        groups_output.append({
            "model_id": model_id,
            "model_family": model_family,
            "direction": direction,
            "quality": quality,
            **_group_metrics(items),
            "cluster_family": cluster_family,
            "dominant_model_id": dominant_model_id,
            "cluster_sample_size": cluster_metrics.get("sample_size"),
            "cluster_winrate": cluster_metrics.get("winrate"),
            "cluster_expectancy": cluster_metrics.get("expectancy"),
        })

    cluster_groups_output: list[dict[str, Any]] = []
    for (model_id, model_family, direction, quality, cluster_family, dominant_model_id), items in cluster_grouped.items():
        cluster_groups_output.append({
            "model_id": model_id,
            "model_family": model_family,
            "direction": direction,
            "quality": quality,
            "cluster_family": cluster_family,
            "dominant_model_id": dominant_model_id,
            **_group_metrics(items),
        })

    groups_output.sort(
        key=lambda item: (
            item.get("expectancy") if item.get("expectancy") is not None else -9999,
            item.get("sample_size", 0),
        ),
        reverse=True,
    )
    cluster_groups_output.sort(
        key=lambda item: (
            item.get("expectancy") if item.get("expectancy") is not None else -9999,
            item.get("sample_size", 0),
        ),
        reverse=True,
    )
    best_group = groups_output[0] if groups_output else None
    best_cluster_group = cluster_groups_output[0] if cluster_groups_output else None

    output = {
        "timestamp_utc": _utc_now(),
        "symbol": "BTCUSDT",
        "block_id": BLOCK_ID,
        "source": {
            "source_mode": "RESEARCH_PAPER_LIFECYCLE_HISTORY",
        },
        "groups": groups_output,
        "cluster_groups": cluster_groups_output,
        "summary": {
            "group_count": len(groups_output),
            "cluster_group_count": len(cluster_groups_output),
            "closed_trade_count": len(closed_trades),
            "best_model_id": best_group.get("model_id") if best_group else None,
            "best_sample_size": best_group.get("sample_size") if best_group else 0,
            "best_winrate": best_group.get("winrate") if best_group else None,
            "best_expectancy": best_group.get("expectancy") if best_group else None,
            "best_maturity": best_group.get("maturity") if best_group else None,
            "best_cluster_family": best_cluster_group.get("cluster_family") if best_cluster_group else None,
            "best_dominant_model_id": best_cluster_group.get("dominant_model_id") if best_cluster_group else None,
        },
        "reason_codes": [
            f"CLOSED_TRADES_{len(closed_trades)}",
            f"GROUPS_{len(groups_output)}",
            f"CLUSTER_GROUPS_{len(cluster_groups_output)}",
            "NO_LIVE_EXECUTION",
            "NO_PRIVATE_API",
            "PAPER_ONLY",
        ],
        "data_quality": {
            "level": "HIGH" if closed_trades else "LOW",
            "missing_inputs": [] if LIFECYCLE_HISTORY_PATH.exists() else ["research_paper_lifecycle_history"],
        },
        "feeds_next": [
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
    print(json.dumps(run_research_edge_matrix_engine(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
