from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.simple.jsonl_tail_reader import safe_write_json_atomic

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state" / "simple"
DATA_DIR = ROOT / "data" / "simple"
ARCHIVE_ROOT = ROOT / "archive"

MOVE_PATHS = [
    STATE_DIR / "latest_research_paper_lifecycle.json",
    STATE_DIR / "latest_paper_trade_factory.json",
    STATE_DIR / "latest_telegram_report.json",
    STATE_DIR / "telegram_reported_trades.json",
    STATE_DIR / "latest_pipeline_failure.json",
    DATA_DIR / "research_paper_lifecycle_history.jsonl",
    DATA_DIR / "paper_trade_factory_history.jsonl",
    DATA_DIR / "telegram_report_history.jsonl",
    DATA_DIR / "research_edge_matrix_history.jsonl",
]

RECREATE_STATE_PATHS = [
    STATE_DIR / "latest_research_paper_lifecycle.json",
    STATE_DIR / "latest_paper_trade_factory.json",
    STATE_DIR / "latest_research_edge_matrix.json",
    STATE_DIR / "latest_telegram_report.json",
    STATE_DIR / "telegram_reported_trades.json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def archive_dir_name() -> str:
    return datetime.now(timezone.utc).strftime("runtime_sanitize_%Y%m%d_%H%M%S")


def base_payload(archive_path: Path) -> dict:
    return {
        "sanitized_at_utc": utc_now(),
        "pre_sanitize_archive_path": archive_path.as_posix(),
        "summary": {
            "open": 0,
            "closed": 0,
            "invalid": 0,
            "tp": 0,
            "sl": 0,
            "expired": 0,
        },
        "open_trades": [],
        "recent_closed": [],
        "recent_invalid": [],
        "edge_status": "SAMPLE_BUILDING",
        "execution_safety": {
            "live_order_sent": False,
            "private_api_used": False,
        },
    }


def payload_for(path: Path, archive_path: Path) -> dict:
    payload = base_payload(archive_path)
    if path.name == "latest_paper_trade_factory.json":
        payload.update(
            {
                "newest_opened_this_loop": [],
                "current_open_summary": {
                    "existing_open_trades": 0,
                    "open_by_model_id": {},
                    "open_by_family_direction": {},
                },
                "paper_safety": {
                    "blocked_by_context_direction_conflict": 0,
                    "blocked_by_model_family_direction_conflict": 0,
                    "blocked_by_open_limit": 0,
                    "blocked_by_family_limit": 0,
                    "blocked_by_model_id_limit": 0,
                    "blocked_by_new_trade_cap": 0,
                    "allowed_research_band_counts": {},
                },
                "top_candidate_diagnostics": [],
            }
        )
    elif path.name == "latest_research_edge_matrix.json":
        payload.update(
            {
                "groups": [],
                "summary": {
                    "group_count": 0,
                    "closed_trade_count": 0,
                    "clean_sample_count": 0,
                    "best_model_id": None,
                    "best_sample_size": 0,
                    "best_expectancy": None,
                    "best_winrate": None,
                    "best_maturity": "INSUFFICIENT",
                    "best_context": None,
                },
            }
        )
    elif path.name == "latest_telegram_report.json":
        payload.update(
            {
                "status": "TELEGRAM_NOT_CONFIGURED",
                "message_count": 0,
                "sent_count": 0,
                "failed_count": 0,
                "not_configured_count": 0,
                "messages": [],
                "reason_codes": ["SANITIZED_BACKLOG_RESET"],
            }
        )
    elif path.name == "telegram_reported_trades.json":
        payload.update(
            {
                "reported_open_trade_ids": [],
                "reported_closed_trade_ids": [],
                "last_summary_sent_at_utc": None,
                "updated_at_utc": utc_now(),
            }
        )
    return payload


def run(apply_changes: bool) -> int:
    archive_path = ARCHIVE_ROOT / archive_dir_name()
    print(f"ARCHIVE_DIR {archive_path}")
    for path in MOVE_PATHS:
        if path.exists():
            destination = archive_path / path.relative_to(ROOT)
            print(f"MOVE {path} -> {destination}")
            if apply_changes:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(destination))
        else:
            print(f"SKIP_MISSING {path}")

    for path in RECREATE_STATE_PATHS:
        payload = payload_for(path, archive_path)
        print(f"RECREATE {path}")
        if apply_changes:
            safe_write_json_atomic(path, payload)
    if not apply_changes:
        print("DRY_RUN_ONLY")
    else:
        print("SANITIZE_APPLIED")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive heavy runtime state and recreate small clean snapshots.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(apply_changes=bool(args.apply)))


if __name__ == "__main__":
    main()
