from __future__ import annotations

from typing import Any


def build_scenario_tree(
    future_paths: list[dict[str, Any]],
    dominant_path: dict[str, Any] | None,
) -> dict[str, Any]:
    dominant_path = dominant_path or {}
    branches: list[dict[str, Any]] = []
    label_map = {
        "BULLISH_CONTINUATION_PATH": "continuation succeeds",
        "BEARISH_CONTINUATION_PATH": "continuation succeeds",
        "RANGE_ROTATION_PATH": "rotation completes",
        "REVERSAL_PATH": "continuation fails",
        "FAKE_BREAKOUT_PATH": "fake breakout collapse",
        "LIQUIDITY_SWEEP_PATH": "liquidity sweep reversal",
        "HIGH_VOLATILITY_PATH": "high volatility expansion",
        "LOW_VOLATILITY_PATH": "low volatility drift",
        "UNKNOWN_PATH": "path unresolved",
    }
    for item in future_paths[:6]:
        branches.append(
            {
                "branch_id": f"BR_{item['path_id'][4:]}",
                "branch_label": label_map.get(item.get("scenario_path"), "alternative branch"),
                "scenario_path": item.get("scenario_path"),
                "probability": item.get("estimated_probability"),
                "probability_band": item.get("probability_band"),
                "risk_level": item.get("risk_level"),
                "expected_behavior": item.get("expected_behavior"),
            }
        )

    return {
        "branch_count": len(branches),
        "dominant_branch": branches[0] if branches else {},
        "root_context": {
            "dominant_path": dominant_path.get("scenario_path"),
            "dominant_probability": dominant_path.get("estimated_probability"),
        },
        "branches": branches,
    }
