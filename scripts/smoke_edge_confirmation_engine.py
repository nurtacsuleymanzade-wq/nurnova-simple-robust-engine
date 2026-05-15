from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.model_survival_registry import (  # noqa: E402
    REGISTRY_PATH,
    get_active_models,
    get_quarantined_models,
    is_model_active,
    is_model_quarantined,
    load_model_survival_registry,
    update_model_survival_report,
)
from src.edge.edge_learning_report import run_edge_learning_report  # noqa: E402
from src.edge.edge_query_engine import run_edge_query_engine  # noqa: E402
from src.edge.elite_context_detector import detect_elite_continuation_context  # noqa: E402
from src.edge.tp_condition_dna_engine import run_tp_condition_dna_engine  # noqa: E402
from src.edge.zone_engine import run_zone_engine  # noqa: E402
from src.simple.telegram_research_reporter import telegram_elite_filter  # noqa: E402


def _status(ok: bool, detail: Any = None) -> dict[str, Any]:
    return {"ok": bool(ok), "detail": detail}


def main() -> None:
    results: dict[str, Any] = {"working_directory": str(ROOT), "registry_path": str(REGISTRY_PATH)}
    registry = load_model_survival_registry()
    active = get_active_models()
    quarantined = get_quarantined_models()
    results["registry_loads"] = _status(registry.get("_registry_status") == "LOADED", registry.get("_registry_status"))
    results["quarantined_model_blocked"] = _status(is_model_quarantined("FCR_LONG"))
    results["active_model_allowed"] = _status(is_model_active("MTF_ALIGNMENT_LONG"))
    survival_report = update_model_survival_report(
        location="SMOKE_EDGE_CONFIRMATION_ENGINE",
        allowed_count=1,
        blocked_items=[{"model_id": "FCR_LONG", "blocked_location": "SMOKE_EDGE_CONFIRMATION_ENGINE"}],
        registry=registry,
    )
    results["model_survival_report_file"] = _status((ROOT / "state/simple/epoch_v2/latest_model_survival_report.json").exists(), survival_report.get("registry_status"))

    synthetic_context = {
        "conditions": [
            "COND_STRUCTURE_BULLISH",
            "COND_REGIME_MOMENTUM",
            "COND_BUYERS_ATTACKING",
            "COND_NEAR_LIQUIDITY_ABOVE",
            "COND_ATR_EXPANDING",
        ],
        "symbol": "BTCUSDT",
    }
    elite = detect_elite_continuation_context(
        synthetic_context,
        {"clusters": [{"dominant_model_id": "MTF_ALIGNMENT_LONG"}]},
        {"source_models": [{"model_id": "IB01_LONG"}], "direction": "LONG"},
    )
    results["elite_context_detected"] = _status(elite.get("context_type") == "ELITE_CONTINUATION_CONTEXT", elite)

    tp_dna = run_tp_condition_dna_engine(max_tail_rows=500)
    results["tp_condition_dna_file"] = _status((ROOT / "state/simple/epoch_v2/latest_tp_condition_dna.json").exists(), (tp_dna.get("data_quality") or {}).get("missing_inputs"))

    zone = run_zone_engine()
    results["zone_context_file"] = _status((ROOT / "state/simple/latest_zone_context.json").exists(), (zone.get("data_quality") or {}).get("missing_inputs"))

    edge_query = run_edge_query_engine()
    results["edge_query_report_file"] = _status((ROOT / "state/simple/epoch_v2/latest_edge_query_report.json").exists(), (edge_query.get("data_quality") or {}).get("missing_inputs"))

    blocked, blocked_reason = telegram_elite_filter({"context_type": "ELITE_CONTINUATION_CONTEXT", "model_id": "FCR_LONG"})
    allowed, allowed_reason = telegram_elite_filter({"context_type": "ELITE_CONTINUATION_CONTEXT", "model_id": "MTF_ALIGNMENT_LONG"})
    results["telegram_blocks_quarantined_model"] = _status(blocked is False and blocked_reason == "MODEL_SURVIVAL_REGISTRY_BLOCK", blocked_reason)
    results["telegram_allows_elite_context"] = _status(allowed is True and allowed_reason == "ELITE_CONTINUATION_CONTEXT", allowed_reason)

    dashboard = run_edge_learning_report()
    results["edge_learning_dashboard_file"] = _status((ROOT / "state/simple/epoch_v2/latest_edge_learning_dashboard.json").exists(), dashboard.get("data_quality"))
    results["active_models"] = active
    results["quarantined_models"] = quarantined
    results["overall_ok"] = all(value.get("ok") for value in results.values() if isinstance(value, dict) and "ok" in value)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
