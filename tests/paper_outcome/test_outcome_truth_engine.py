from __future__ import annotations

from src.paper_outcome.outcome_truth_engine import evaluate_outcome_truth
from src.paper_outcome.paper_lifecycle_engine import build_paper_lifecycle


def _decision(
    *,
    side: str = "LONG",
    tp1: float = 110.0,
    tp2: float | None = 120.0,
    invalidation: float | None = None,
) -> dict:
    return {
        "timestamp_utc": "2026-05-18T00:00:00Z",
        "symbol": "BTCUSDT",
        "trade_plan_id": "TPN_1",
        "decision_id": "DEC_1",
        "lineage_id": "LIN_DECISION",
        "setup_candidate_id": "SETUP_1",
        "entry_trigger_id": "ENTRY_1",
        "decision_status": "ALLOW_PAPER",
        "side": side,
        "entry_price": 100.0 if side == "LONG" else 100.0,
        "stop_loss": 90.0 if side == "LONG" else 110.0,
        "take_profit_1": tp1 if side == "LONG" else 90.0,
        "take_profit_2": tp2 if side == "LONG" else (80.0 if tp2 is not None else None),
        "invalidation_level": invalidation if invalidation is not None else (89.0 if side == "LONG" else 111.0),
    }


def _record(ts: str, low: float, high: float) -> dict:
    return {"timestamp_utc": ts, "symbol": "BTCUSDT", "low": low, "high": high}


def _evaluate(decision: dict, records: list[dict], *, as_of: str = "2026-05-18T00:10:00Z", timeout_minutes: int = 60) -> dict:
    lifecycle = build_paper_lifecycle(decision, timestamp_utc="2026-05-18T00:00:00Z")
    return evaluate_outcome_truth(lifecycle, records, as_of_timestamp_utc=as_of, timeout_minutes=timeout_minutes)


def test_long_tp1_hit_outcome() -> None:
    result = _evaluate(_decision(tp2=None), [_record("2026-05-18T00:01:00Z", 99.0, 111.0)])
    assert result["trade_fate"] == "TP1_HIT"
    assert result["is_closed_outcome"] is True
    assert result["edge_eligible"] is True


def test_long_sl_hit_outcome() -> None:
    result = _evaluate(_decision(), [_record("2026-05-18T00:01:00Z", 89.0, 101.0)])
    assert result["trade_fate"] == "SL_HIT"
    assert result["edge_eligible"] is True


def test_short_tp1_hit_outcome() -> None:
    result = _evaluate(_decision(side="SHORT", tp2=None), [_record("2026-05-18T00:01:00Z", 89.0, 101.0)])
    assert result["trade_fate"] == "TP1_HIT"
    assert result["is_closed_outcome"] is True


def test_short_sl_hit_outcome() -> None:
    result = _evaluate(_decision(side="SHORT"), [_record("2026-05-18T00:01:00Z", 99.0, 111.0)])
    assert result["trade_fate"] == "SL_HIT"
    assert result["edge_eligible"] is True


def test_entry_without_touching_entry_is_not_edge_eligible() -> None:
    result = _evaluate(_decision(), [{"timestamp_utc": "2026-05-18T00:01:00Z", "symbol": "BTCUSDT", "price": 120.0}])
    assert result["trade_fate"] == "NO_ENTRY_TOUCH"
    assert result["edge_eligible"] is False


def test_invalidated_before_entry_is_produced() -> None:
    result = _evaluate(_decision(), [_record("2026-05-18T00:01:00Z", 88.0, 88.0)])
    assert result["trade_fate"] == "INVALIDATED_BEFORE_ENTRY"
    assert result["edge_eligible"] is False


def test_invalidated_after_entry_is_produced() -> None:
    result = _evaluate(
        _decision(invalidation=95.0),
        [
            _record("2026-05-18T00:01:00Z", 99.0, 101.0),
            _record("2026-05-18T00:02:00Z", 94.0, 96.0),
        ],
    )
    assert result["trade_fate"] == "INVALIDATED_AFTER_ENTRY"
    assert result["is_closed_outcome"] is True
    assert result["edge_eligible"] is True


def test_tp1_then_sl_produces_partial_outcome() -> None:
    result = _evaluate(
        _decision(tp1=108.0, tp2=130.0),
        [
            _record("2026-05-18T00:01:00Z", 99.0, 101.0),
            _record("2026-05-18T00:02:00Z", 100.0, 108.5),
            _record("2026-05-18T00:03:00Z", 89.0, 99.0),
        ],
    )
    assert result["trade_fate"] == "PARTIAL_LOSS"
    assert result["edge_eligible"] is True


def test_timeout_is_diagnostic_and_not_edge_eligible() -> None:
    result = _evaluate(
        _decision(),
        [_record("2026-05-18T00:01:00Z", 99.0, 101.0)],
        as_of="2026-05-18T02:10:00Z",
        timeout_minutes=1,
    )
    assert result["trade_fate"] == "DIAGNOSTIC_TIMEOUT"
    assert result["edge_eligible"] is False


def test_no_entry_touch_is_not_edge_eligible() -> None:
    result = _evaluate(_decision(), [], as_of="2026-05-18T00:10:00Z")
    assert result["trade_fate"] == "NO_ENTRY_TOUCH"
    assert result["edge_eligible"] is False


def test_closed_outcome_is_edge_eligible() -> None:
    result = _evaluate(_decision(tp2=None), [_record("2026-05-18T00:01:00Z", 99.0, 111.0)])
    assert result["is_closed_outcome"] is True
    assert result["edge_eligible"] is True
