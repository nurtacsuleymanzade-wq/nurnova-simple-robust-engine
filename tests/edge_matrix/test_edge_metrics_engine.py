from __future__ import annotations

from src.edge_matrix.edge_metrics_engine import calculate_edge_row_metrics


def _row(records: list[dict]) -> dict:
    return {
        "group_key": {"pattern": "RANGE_LONG_SETUP", "side": "LONG"},
        "records": records,
        "source_outcome_ids": [record["outcome_id"] for record in records],
        "source_paper_trade_ids": [record["paper_trade_id"] for record in records],
        "reason_codes": [],
    }


def _record(idx: int, *, fate: str, r: float, dq: str = "OK") -> dict:
    return {
        "outcome_id": f"OUT_{idx}",
        "paper_trade_id": f"PPR_{idx}",
        "trade_fate": fate,
        "r_multiple": r,
        "data_quality": dq,
        "close_reason": fate,
        "reason_codes": [f"RC_{idx}"],
    }


def test_winrate_is_calculated_correctly() -> None:
    result = calculate_edge_row_metrics(
        _row([
            _record(1, fate="TP1_HIT", r=1.0),
            _record(2, fate="SL_HIT", r=-1.0),
        ])
    )
    assert result["winrate"] == 0.5


def test_expectancy_r_is_calculated_correctly() -> None:
    result = calculate_edge_row_metrics(
        _row([
            _record(1, fate="TP2_HIT", r=2.0),
            _record(2, fate="SL_HIT", r=-1.0),
        ])
    )
    assert result["expectancy_r"] == 0.5


def test_profit_factor_is_calculated_correctly() -> None:
    result = calculate_edge_row_metrics(
        _row([
            _record(1, fate="TP2_HIT", r=2.0),
            _record(2, fate="SL_HIT", r=-1.0),
        ])
    )
    assert result["profit_factor"] == 2.0


def test_sample_size_below_10_is_insufficient() -> None:
    result = calculate_edge_row_metrics(_row([_record(1, fate="TP1_HIT", r=1.0)]))
    assert result["edge_status"] == "INSUFFICIENT_SAMPLE"


def test_positive_expectancy_becomes_watchlist() -> None:
    records = [_record(i, fate="TP1_HIT", r=1.0) for i in range(1, 11)]
    result = calculate_edge_row_metrics(_row(records))
    assert result["edge_status"] == "WATCHLIST_EDGE"


def test_strong_metrics_become_strong_edge_candidate() -> None:
    records = [_record(i, fate="TP2_HIT", r=1.0) for i in range(1, 51)] + [_record(999, fate="SL_HIT", r=-1.0)]
    result = calculate_edge_row_metrics(_row(records))
    assert result["edge_status"] == "STRONG_EDGE_CANDIDATE"


def test_negative_expectancy_becomes_negative_edge() -> None:
    records = [_record(i, fate="SL_HIT", r=-1.0) for i in range(1, 11)]
    result = calculate_edge_row_metrics(_row(records))
    assert result["edge_status"] == "NEGATIVE_EDGE"


def test_empty_input_produces_no_data() -> None:
    result = calculate_edge_row_metrics(_row([]))
    assert result["edge_status"] == "NO_DATA"


def test_deterministic_edge_row_id_stays_stable() -> None:
    records = [_record(1, fate="TP1_HIT", r=1.0)]
    first = calculate_edge_row_metrics(_row(records))
    second = calculate_edge_row_metrics(_row(records))
    assert first["edge_row_id"] == second["edge_row_id"]
