from __future__ import annotations

import json
from pathlib import Path

from src.simple.research_epoch import ACTIVE_EPOCH_ID, EPOCH_DATA_DIR, EPOCH_STATE_DIR
from src.simple.research_runtime import load_json

ROOT = Path(__file__).resolve().parent


def run() -> dict:
    reset = load_json(EPOCH_STATE_DIR / "latest_epoch_reset.json") or {}
    lifecycle = load_json(EPOCH_STATE_DIR / "latest_research_paper_lifecycle.json") or {}
    accounting = load_json(EPOCH_STATE_DIR / "latest_outcome_accounting.json") or {}
    edge = load_json(EPOCH_STATE_DIR / "latest_research_edge_matrix.json") or {}
    telegram = load_json(EPOCH_STATE_DIR / "latest_telegram_report.json") or {}

    summary = accounting.get("summary") or {}
    files = sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in list(EPOCH_DATA_DIR.glob("*")) + list(EPOCH_STATE_DIR.glob("*"))
        if path.is_file()
    )
    payload = {
        "epoch_id": ACTIVE_EPOCH_ID,
        "archive_status": bool(reset),
        "epoch_v2_files": files,
        "open_trades": int((lifecycle.get("summary") or {}).get("open") or len(lifecycle.get("open_trades") or [])),
        "closed_trades": int(summary.get("closed_count") or 0),
        "clean_samples": int(summary.get("clean_sample_count") or 0),
        "invalid_samples": int(summary.get("invalid_sample_count") or 0),
        "duplicate_paper_trade_id_count": int(summary.get("duplicate_paper_trade_id_count") or 0),
        "missing_timeframe_count": int((lifecycle.get("quality_counters") or {}).get("missing_timeframe_count") or 0),
        "missing_rr_count": int((lifecycle.get("quality_counters") or {}).get("missing_rr_count") or 0),
        "wins": int(summary.get("wins") or 0),
        "losses": int(summary.get("losses") or 0),
        "expired": int(summary.get("expired") or 0),
        "winrate": summary.get("winrate"),
        "avg_r": summary.get("avg_r"),
        "edge_status": edge.get("edge_status") or "NO_CLEAN_SAMPLES",
        "telegram_source": ((telegram.get("source") or {}).get("source_mode")) or "UNKNOWN",
        "safety_status": {
            "live_order_sent": False,
            "private_api_used": False,
            "accounting_status": accounting.get("accounting_status") or "MISSING",
        },
        "status": "CLEAN_EPOCH_READY",
    }
    return payload


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
