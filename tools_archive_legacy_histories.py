from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.simple.research_epoch import ACTIVE_EPOCH_ID, EPOCH_DATA_DIR, EPOCH_STATE_DIR, ensure_epoch_dirs
from src.simple.jsonl_tail_reader import safe_write_json_atomic

ROOT = Path(__file__).resolve().parent
ARCHIVE_ROOT = ROOT / "archive"
DATA_DIR = ROOT / "data" / "simple"
STATE_DIR = ROOT / "state" / "simple"

LEGACY_FILES = [
    DATA_DIR / "research_paper_lifecycle_history.jsonl",
    DATA_DIR / "paper_trade_factory_history.jsonl",
    DATA_DIR / "research_edge_matrix_history.jsonl",
    DATA_DIR / "model_hunter_history.jsonl",
    DATA_DIR / "model_clusters_history.jsonl",
    DATA_DIR / "model_definitions_history.jsonl",
    DATA_DIR / "decision_gate_history.jsonl",
    STATE_DIR / "latest_research_paper_lifecycle.json",
    STATE_DIR / "latest_research_edge_matrix.json",
    STATE_DIR / "latest_telegram_report.json",
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run() -> dict:
    archive_path = ARCHIVE_ROOT / f"legacy_history_{_utc_stamp()}"
    archived: list[str] = []
    archive_path.mkdir(parents=True, exist_ok=True)

    for path in LEGACY_FILES:
        if not path.exists():
            continue
        relative = path.relative_to(ROOT)
        target = archive_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        archived.append(str(relative).replace("\\", "/"))

    ensure_epoch_dirs()
    reset_payload = {
        "archive_path": str(archive_path.relative_to(ROOT)).replace("\\", "/"),
        "epoch_id": ACTIVE_EPOCH_ID,
        "reset_reason": "FINAL_CLEAN_EPOCH_RESET",
        "legacy_files_archived": archived,
        "live_order_sent": False,
        "private_api_used": False,
    }
    safe_write_json_atomic(EPOCH_STATE_DIR / "latest_epoch_reset.json", reset_payload)
    result = {
        "archive_path": reset_payload["archive_path"],
        "epoch_id": ACTIVE_EPOCH_ID,
        "legacy_files_archived": archived,
        "epoch_data_dir": str(EPOCH_DATA_DIR.relative_to(ROOT)).replace("\\", "/"),
        "epoch_state_dir": str(EPOCH_STATE_DIR.relative_to(ROOT)).replace("\\", "/"),
        "live_order_sent": False,
        "private_api_used": False,
    }
    return result


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
