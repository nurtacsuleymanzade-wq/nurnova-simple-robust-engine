from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any

from .edge_matrix_registry import EDGE_STATUSES, build_edge_row_id


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_counts(record: dict[str, Any]) -> tuple[bool, bool, bool, bool, bool]:
    fate = str(record.get("trade_fate") or "UNKNOWN").upper()
    r_value = _to_float(record.get("r_multiple"))
    is_partial_win = fate == "PARTIAL_WIN"
    is_partial_loss = fate == "PARTIAL_LOSS"
    is_breakeven = fate == "BREAKEVEN" or r_value == 0
    is_win = fate in {"TP1_HIT", "TP2_HIT", "PARTIAL_WIN"} or (r_value is not None and r_value > 0)
    is_loss = fate in {"SL_HIT", "PARTIAL_LOSS"} or (fate == "INVALIDATED_AFTER_ENTRY" and (r_value or 0.0) < 0)
    return is_win, is_loss, is_breakeven, is_partial_win, is_partial_loss


def _top_reason(records: list[dict[str, Any]], positive: bool) -> str | None:
    counts: Counter[str] = Counter()
    for record in records:
        r_value = _to_float(record.get("r_multiple"))
        if positive and not (r_value is not None and r_value > 0):
            continue
        if not positive and not (r_value is not None and r_value < 0):
            continue
        reason = record.get("close_reason")
        if reason not in (None, ""):
            counts[str(reason)] += 1
        else:
            for code in record.get("reason_codes") or []:
                counts[str(code)] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _confidence_band(sample_size: int) -> str:
    if sample_size >= 50:
        return "HIGH"
    if sample_size >= 20:
        return "MEDIUM"
    if sample_size > 0:
        return "LOW"
    return "UNKNOWN"


def _row_edge_status(
    *,
    sample_size: int,
    expectancy_r: float | None,
    winrate: float | None,
    profit_factor: float | None,
    degraded_count: int,
) -> str:
    if sample_size == 0:
        return "NO_DATA"
    if degraded_count > 0 and degraded_count / sample_size >= 0.4:
        return "DEGRADED_BY_DATA_QUALITY"
    if sample_size < 10:
        return "INSUFFICIENT_SAMPLE"
    if expectancy_r is None:
        return "INVALID"
    if sample_size >= 50 and expectancy_r > 0.5 and (profit_factor or 0.0) > 1.5:
        return "STRONG_EDGE_CANDIDATE"
    if sample_size >= 30 and expectancy_r > 0.25 and (winrate or 0.0) >= 0.45:
        return "TRADEABLE_EDGE_CANDIDATE"
    if expectancy_r < 0:
        return "NEGATIVE_EDGE"
    if abs(expectancy_r) <= 0.05:
        return "NEUTRAL_EDGE"
    if sample_size >= 10 and expectancy_r > 0:
        return "WATCHLIST_EDGE"
    return "INVALID"


def calculate_edge_row_metrics(row: dict[str, Any]) -> dict[str, Any]:
    records = list(row.get("records") or [])
    r_values = [_to_float(item.get("r_multiple")) for item in records if _to_float(item.get("r_multiple")) is not None]
    sample_size = len(records)

    win_count = 0
    loss_count = 0
    breakeven_count = 0
    partial_win_count = 0
    partial_loss_count = 0
    degraded_count = 0

    outcome_rank: list[tuple[float, str]] = []
    reason_codes = list(row.get("reason_codes") or [])
    gross_win_r = 0.0
    gross_loss_r = 0.0

    for record in records:
        is_win, is_loss, is_breakeven, is_partial_win, is_partial_loss = _classify_counts(record)
        r_value = _to_float(record.get("r_multiple"))
        if is_win:
            win_count += 1
        if is_loss:
            loss_count += 1
        if is_breakeven:
            breakeven_count += 1
        if is_partial_win:
            partial_win_count += 1
        if is_partial_loss:
            partial_loss_count += 1
        if str(record.get("data_quality") or "UNKNOWN").upper() in {"DEGRADED", "INVALID"}:
            degraded_count += 1
        if r_value is not None:
            outcome_rank.append((r_value, str(record.get("trade_fate") or "UNKNOWN")))
            if r_value > 0:
                gross_win_r += r_value
            elif r_value < 0:
                gross_loss_r += r_value

    winrate = round(win_count / sample_size, 4) if sample_size else None
    lossrate = round(loss_count / sample_size, 4) if sample_size else None
    avg_r = round(sum(r_values) / len(r_values), 4) if r_values else None
    median_r = round(float(median(r_values)), 4) if r_values else None
    expectancy_r = avg_r

    profit_factor = None
    if gross_loss_r < 0:
        profit_factor = round(gross_win_r / abs(gross_loss_r), 4)
    elif gross_win_r > 0:
        reason_codes.append("NO_LOSS_SAMPLE")

    max_win_r = round(max(r_values), 4) if r_values else None
    max_loss_r = round(min(r_values), 4) if r_values else None

    best_outcome = None
    worst_outcome = None
    if outcome_rank:
        best_outcome = max(outcome_rank, key=lambda item: item[0])[1]
        worst_outcome = min(outcome_rank, key=lambda item: item[0])[1]

    success_reason_top = _top_reason(records, positive=True)
    failure_reason_top = _top_reason(records, positive=False)
    confidence_band = _confidence_band(sample_size)
    edge_status = _row_edge_status(
        sample_size=sample_size,
        expectancy_r=expectancy_r,
        winrate=winrate,
        profit_factor=profit_factor,
        degraded_count=degraded_count,
    )
    assert edge_status in EDGE_STATUSES

    return {
        "edge_row_id": build_edge_row_id(row.get("group_key") or {}, row.get("source_outcome_ids") or []),
        "group_key": dict(row.get("group_key") or {}),
        "sample_size": sample_size,
        "win_count": win_count,
        "loss_count": loss_count,
        "breakeven_count": breakeven_count,
        "partial_win_count": partial_win_count,
        "partial_loss_count": partial_loss_count,
        "winrate": winrate,
        "lossrate": lossrate,
        "avg_r": avg_r,
        "median_r": median_r,
        "expectancy_r": expectancy_r,
        "profit_factor": profit_factor,
        "max_win_r": max_win_r,
        "max_loss_r": max_loss_r,
        "best_outcome": best_outcome,
        "worst_outcome": worst_outcome,
        "failure_reason_top": failure_reason_top,
        "success_reason_top": success_reason_top,
        "confidence_band": confidence_band,
        "edge_status": edge_status,
        "source_outcome_ids": list(row.get("source_outcome_ids") or []),
        "source_paper_trade_ids": list(row.get("source_paper_trade_ids") or []),
        "source_trade_fates": sorted({str(item.get("trade_fate") or "UNKNOWN") for item in records}),
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }


def calculate_all_edge_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [calculate_edge_row_metrics(row) for row in rows]
