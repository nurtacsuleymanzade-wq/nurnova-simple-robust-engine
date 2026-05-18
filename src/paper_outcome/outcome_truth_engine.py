from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from .paper_outcome_registry import (
    CLOSED_EDGE_ELIGIBLE_FATES,
    NON_EDGE_FATES,
    build_outcome_id,
)


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _signed_r(side: str, entry: float, exit_price: float, risk: float) -> float | None:
    if risk <= 0:
        return None
    if side == "LONG":
        return round((exit_price - entry) / risk, 4)
    if side == "SHORT":
        return round((entry - exit_price) / risk, 4)
    return None


def _normalize_record(record: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    record_symbol = record.get("symbol")
    if record_symbol not in (None, "", symbol):
        return None

    timestamp = record.get("timestamp_utc") or record.get("generated_at_utc")
    ts = _parse_ts(timestamp)
    if ts is None:
        return None

    current = record.get("current_price")
    if current is None:
        current = record.get("price")
    if current is None:
        current = record.get("close")
    if current is None:
        current = record.get("candle_close")
    if current is None:
        current = record.get("official_close")

    explicit_high = record.get("high")
    if explicit_high is None:
        explicit_high = record.get("candle_high")
    if explicit_high is None:
        explicit_high = record.get("official_high")

    high = explicit_high
    if high is None:
        high = current

    explicit_low = record.get("low")
    if explicit_low is None:
        explicit_low = record.get("candle_low")
    if explicit_low is None:
        explicit_low = record.get("official_low")

    low = explicit_low
    if low is None:
        low = current

    if current is None and low is None and high is None:
        return None

    numbers = [value for value in (low, current, high) if isinstance(value, (int, float))]
    if not numbers:
        return None

    low_value = float(min(numbers))
    high_value = float(max(numbers))
    current_value = float(current) if isinstance(current, (int, float)) else float(numbers[-1])

    return {
        "timestamp_utc": _to_iso(ts),
        "timestamp_dt": ts,
        "low": low_value,
        "high": high_value,
        "current_price": current_value,
        "has_explicit_band": explicit_low is not None and explicit_high is not None,
        "source_file": record.get("source_file"),
        "raw": record,
    }


def normalize_price_path_records(
    records: list[dict[str, Any]] | None,
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        item = _normalize_record(record, symbol)
        if item is not None:
            normalized.append(item)
    normalized.sort(key=lambda item: item["timestamp_dt"])
    return normalized


def _touch_entry(side: str, record: dict[str, Any], entry_price: float) -> bool:
    if record.get("has_explicit_band"):
        return record["low"] <= entry_price <= record["high"]
    if side == "LONG":
        return record["low"] <= entry_price
    if side == "SHORT":
        return record["high"] >= entry_price
    return False


def _touch_tp(side: str, record: dict[str, Any], target_price: float | None) -> bool:
    if target_price is None:
        return False
    if side == "LONG":
        return record["high"] >= target_price
    if side == "SHORT":
        return record["low"] <= target_price
    return False


def _touch_sl(side: str, record: dict[str, Any], stop_loss: float) -> bool:
    if side == "LONG":
        return record["low"] <= stop_loss
    if side == "SHORT":
        return record["high"] >= stop_loss
    return False


def _touch_invalidation(side: str, record: dict[str, Any], invalidation_level: float) -> bool:
    if side == "LONG":
        return record["low"] <= invalidation_level
    if side == "SHORT":
        return record["high"] >= invalidation_level
    return False


def _close(
    payload: dict[str, Any],
    *,
    trade_fate: str,
    lifecycle_state: str,
    closed_at: str,
    close_reason: str,
    r_multiple: float | None,
) -> None:
    payload["trade_fate"] = trade_fate
    payload["lifecycle_state"] = lifecycle_state
    payload["closed_at"] = closed_at
    payload["close_reason"] = close_reason
    payload["r_multiple"] = r_multiple
    payload["is_closed_outcome"] = trade_fate in CLOSED_EDGE_ELIGIBLE_FATES
    payload["edge_eligible"] = trade_fate in CLOSED_EDGE_ELIGIBLE_FATES


def _dedupe_codes(payload: dict[str, Any]) -> None:
    payload["reason_codes"] = list(dict.fromkeys(payload.get("reason_codes") or []))
    payload["warnings"] = list(dict.fromkeys(payload.get("warnings") or []))


def evaluate_outcome_truth(
    lifecycle: dict[str, Any],
    price_path_records: list[dict[str, Any]] | None = None,
    *,
    as_of_timestamp_utc: str | None = None,
    timeout_minutes: int = 60,
) -> dict[str, Any]:
    payload = deepcopy(lifecycle)
    payload.setdefault("reason_codes", [])
    payload.setdefault("warnings", [])
    payload.setdefault("feeds_next", [])
    payload.setdefault("evidence", {})
    payload["evidence"].setdefault("trade_decision_evidence", {})
    payload["evidence"].setdefault("price_path_evidence", {})
    payload["evidence"].setdefault("entry_evidence", {})
    payload["evidence"].setdefault("tp_evidence", {})
    payload["evidence"].setdefault("sl_evidence", {})
    payload["evidence"].setdefault("invalidation_evidence", {})

    symbol = str(payload.get("symbol") or "BTCUSDT")
    side = str(payload.get("side") or "UNKNOWN").upper()
    decision_ts = _parse_ts(payload.get("_decision_timestamp_utc") or payload.get("timestamp_utc"))
    as_of_dt = _parse_ts(as_of_timestamp_utc) if as_of_timestamp_utc else decision_ts
    if as_of_dt is None:
        as_of_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)

    normalized = normalize_price_path_records(price_path_records, symbol=symbol)
    payload["evidence"]["price_path_evidence"] = {
        "record_count": len(normalized),
        "first_timestamp_utc": normalized[0]["timestamp_utc"] if normalized else None,
        "last_timestamp_utc": normalized[-1]["timestamp_utc"] if normalized else None,
        "source_files": sorted({str(item.get("source_file") or "") for item in normalized if item.get("source_file")}),
    }

    if payload.get("_allow_paper") is not True:
        payload["outcome_quality"] = "LOW"
        if not normalized:
            payload["data_quality"] = "ACCEPTABLE"
        payload["evidence"]["trade_decision_evidence"]["decision_status"] = payload.get("_decision_status")
        payload["outcome_id"] = build_outcome_id(
            paper_trade_id=payload.get("paper_trade_id"),
            trade_fate=payload.get("trade_fate"),
            closed_at=payload.get("closed_at"),
            evidence_seed=payload["evidence"]["price_path_evidence"],
        )
        _dedupe_codes(payload)
        return payload

    entry_price = payload.get("entry_price")
    stop_loss = payload.get("stop_loss")
    take_profit_1 = payload.get("take_profit_1")
    take_profit_2 = payload.get("take_profit_2")
    invalidation_level = payload.get("invalidation_level")

    if side not in ("LONG", "SHORT") or any(
        value is None for value in (entry_price, stop_loss, take_profit_1, invalidation_level)
    ):
        payload["lifecycle_state"] = "UNKNOWN"
        payload["trade_fate"] = "UNKNOWN"
        payload["outcome_quality"] = "INVALID"
        payload["data_quality"] = "INVALID"
        payload["close_reason"] = "ALLOW_PAPER_CORE_INPUTS_INVALID"
        payload["reason_codes"].append("ALLOW_PAPER_CORE_INPUTS_INVALID")
        payload["outcome_id"] = build_outcome_id(
            paper_trade_id=payload.get("paper_trade_id"),
            trade_fate=payload.get("trade_fate"),
            closed_at=payload.get("closed_at"),
            evidence_seed=payload["evidence"]["price_path_evidence"],
        )
        _dedupe_codes(payload)
        return payload

    risk = abs(float(entry_price) - float(stop_loss))
    timeout_at = decision_ts + timedelta(minutes=timeout_minutes) if decision_ts else as_of_dt

    entered = False
    tp1_touched = bool(payload.get("tp1_touched"))
    entry_record: dict[str, Any] | None = None
    tp1_record: dict[str, Any] | None = None
    tp2_record: dict[str, Any] | None = None
    sl_record: dict[str, Any] | None = None
    inv_record: dict[str, Any] | None = None

    for record in normalized:
        if decision_ts and record["timestamp_dt"] < decision_ts:
            continue

        entry_hit = _touch_entry(side, record, float(entry_price))
        tp1_hit = _touch_tp(side, record, float(take_profit_1))
        tp2_hit = _touch_tp(side, record, float(take_profit_2)) if take_profit_2 is not None else False
        sl_hit = _touch_sl(side, record, float(stop_loss))
        inv_hit = _touch_invalidation(side, record, float(invalidation_level))

        if not entered:
            if inv_hit and not entry_hit:
                payload["invalidation_touched"] = True
                inv_record = record
                payload["lifecycle_state"] = "INVALIDATED"
                payload["trade_fate"] = "INVALIDATED_BEFORE_ENTRY"
                payload["closed_at"] = record["timestamp_utc"]
                payload["close_reason"] = "INVALIDATION_BEFORE_ENTRY"
                payload["is_closed_outcome"] = False
                payload["edge_eligible"] = False
                break

            if entry_hit:
                entered = True
                entry_record = record
                payload["entry_touched"] = True
                payload["opened_at"] = record["timestamp_utc"]
                payload["lifecycle_state"] = "ENTRY_FILLED"
                payload["trade_fate"] = "ENTRY_FILLED"

                if tp1_hit:
                    tp1_touched = True
                    tp1_record = record
                    payload["tp1_touched"] = True
                    payload["trade_fate"] = "TP1_HIT"

                if tp2_hit and sl_hit:
                    payload["tp2_touched"] = True
                    payload["sl_touched"] = True
                    payload["trade_fate"] = "UNKNOWN"
                    payload["lifecycle_state"] = "UNKNOWN"
                    payload["close_reason"] = "AMBIGUOUS_TP2_AND_SL_SAME_RECORD"
                    payload["reason_codes"].append("AMBIGUOUS_TP2_AND_SL_SAME_RECORD")
                    break
                if tp2_hit:
                    payload["tp2_touched"] = True
                    tp2_record = record
                    _close(
                        payload,
                        trade_fate="TP2_HIT",
                        lifecycle_state="CLOSED",
                        closed_at=record["timestamp_utc"],
                        close_reason="TAKE_PROFIT_2_TOUCHED",
                        r_multiple=_signed_r(side, float(entry_price), float(take_profit_2), risk),
                    )
                    break
                if sl_hit:
                    payload["sl_touched"] = True
                    sl_record = record
                    _close(
                        payload,
                        trade_fate="SL_HIT",
                        lifecycle_state="CLOSED",
                        closed_at=record["timestamp_utc"],
                        close_reason="STOP_LOSS_TOUCHED",
                        r_multiple=-1.0 if risk > 0 else None,
                    )
                    break
                if inv_hit:
                    payload["invalidation_touched"] = True
                    inv_record = record
                    _close(
                        payload,
                        trade_fate="INVALIDATED_AFTER_ENTRY",
                        lifecycle_state="INVALIDATED",
                        closed_at=record["timestamp_utc"],
                        close_reason="INVALIDATION_AFTER_ENTRY",
                        r_multiple=_signed_r(side, float(entry_price), float(invalidation_level), risk),
                    )
                    break
                if tp1_hit and take_profit_2 is None:
                    _close(
                        payload,
                        trade_fate="TP1_HIT",
                        lifecycle_state="CLOSED",
                        closed_at=record["timestamp_utc"],
                        close_reason="TAKE_PROFIT_1_TOUCHED",
                        r_multiple=_signed_r(side, float(entry_price), float(take_profit_1), risk),
                    )
                    break

            continue

        if tp2_hit:
            payload["tp2_touched"] = True
            tp2_record = record
            _close(
                payload,
                trade_fate="TP2_HIT",
                lifecycle_state="CLOSED",
                closed_at=record["timestamp_utc"],
                close_reason="TAKE_PROFIT_2_TOUCHED",
                r_multiple=_signed_r(side, float(entry_price), float(take_profit_2), risk),
            )
            break

        if tp1_hit and not tp1_touched:
            tp1_touched = True
            tp1_record = record
            payload["tp1_touched"] = True
            payload["trade_fate"] = "TP1_HIT"
            if take_profit_2 is None:
                _close(
                    payload,
                    trade_fate="TP1_HIT",
                    lifecycle_state="CLOSED",
                    closed_at=record["timestamp_utc"],
                    close_reason="TAKE_PROFIT_1_TOUCHED",
                    r_multiple=_signed_r(side, float(entry_price), float(take_profit_1), risk),
                )
                break

        if sl_hit:
            payload["sl_touched"] = True
            sl_record = record
            if tp1_touched:
                tp1_r = _signed_r(side, float(entry_price), float(take_profit_1), risk)
                partial_r = round(((tp1_r or 0.0) * 0.5) + (-1.0 * 0.5), 4)
                trade_fate = "BREAKEVEN"
                if partial_r > 0:
                    trade_fate = "PARTIAL_WIN"
                elif partial_r < 0:
                    trade_fate = "PARTIAL_LOSS"
                _close(
                    payload,
                    trade_fate=trade_fate,
                    lifecycle_state="CLOSED",
                    closed_at=record["timestamp_utc"],
                    close_reason="TP1_THEN_STOP_LOSS",
                    r_multiple=partial_r,
                )
            else:
                _close(
                    payload,
                    trade_fate="SL_HIT",
                    lifecycle_state="CLOSED",
                    closed_at=record["timestamp_utc"],
                    close_reason="STOP_LOSS_TOUCHED",
                    r_multiple=-1.0 if risk > 0 else None,
                )
            break

        if inv_hit:
            payload["invalidation_touched"] = True
            inv_record = record
            if tp1_touched:
                tp1_r = _signed_r(side, float(entry_price), float(take_profit_1), risk)
                exit_r = _signed_r(side, float(entry_price), float(invalidation_level), risk)
                partial_r = round(((tp1_r or 0.0) * 0.5) + ((exit_r or 0.0) * 0.5), 4)
                trade_fate = "BREAKEVEN"
                if partial_r > 0:
                    trade_fate = "PARTIAL_WIN"
                elif partial_r < 0:
                    trade_fate = "PARTIAL_LOSS"
                _close(
                    payload,
                    trade_fate=trade_fate,
                    lifecycle_state="CLOSED",
                    closed_at=record["timestamp_utc"],
                    close_reason="TP1_THEN_INVALIDATION",
                    r_multiple=partial_r,
                )
            else:
                _close(
                    payload,
                    trade_fate="INVALIDATED_AFTER_ENTRY",
                    lifecycle_state="INVALIDATED",
                    closed_at=record["timestamp_utc"],
                    close_reason="INVALIDATION_AFTER_ENTRY",
                    r_multiple=_signed_r(side, float(entry_price), float(invalidation_level), risk),
                )
            break

    if payload["trade_fate"] in ("UNKNOWN", "ENTRY_FILLED", "NO_ENTRY_TOUCH", "TP1_HIT") and not payload["is_closed_outcome"]:
        if entered:
            if as_of_dt >= timeout_at:
                payload["lifecycle_state"] = "EXPIRED"
                payload["trade_fate"] = "DIAGNOSTIC_TIMEOUT"
                payload["closed_at"] = _to_iso(as_of_dt)
                payload["close_reason"] = "MAX_HOLD_TIMEOUT_REACHED"
                payload["edge_eligible"] = False
                payload["is_closed_outcome"] = False
            else:
                payload["lifecycle_state"] = "ENTRY_FILLED"
                if tp1_touched:
                    payload["trade_fate"] = "TP1_HIT"
                else:
                    payload["trade_fate"] = "ENTRY_FILLED"
        else:
            if as_of_dt >= timeout_at:
                payload["lifecycle_state"] = "EXPIRED"
                payload["trade_fate"] = "EXPIRED_NO_ENTRY"
                payload["closed_at"] = _to_iso(as_of_dt)
                payload["close_reason"] = "ENTRY_NOT_TOUCHED_BEFORE_TIMEOUT"
            else:
                payload["lifecycle_state"] = "WAITING_ENTRY"
                payload["trade_fate"] = "NO_ENTRY_TOUCH"

    if not normalized:
        payload["data_quality"] = "DEGRADED"
        if "NO_PRICE_PATH_EVIDENCE" not in payload["reason_codes"]:
            payload["reason_codes"].append("NO_PRICE_PATH_EVIDENCE")
    elif payload.get("data_quality") == "OK":
        payload["data_quality"] = "OK"

    if payload["trade_fate"] in CLOSED_EDGE_ELIGIBLE_FATES:
        payload["outcome_quality"] = "HIGH"
    elif payload["trade_fate"] in NON_EDGE_FATES:
        payload["outcome_quality"] = "MEDIUM" if normalized else "LOW"
    elif payload["trade_fate"] == "ENTRY_FILLED":
        payload["outcome_quality"] = "MEDIUM"
    else:
        payload["outcome_quality"] = "UNKNOWN"

    payload["evidence"]["entry_evidence"] = {
        "touched": payload.get("entry_touched", False),
        "touched_at": entry_record["timestamp_utc"] if entry_record else None,
        "record": entry_record["raw"] if entry_record else None,
    }
    payload["evidence"]["tp_evidence"] = {
        "tp1_touched": payload.get("tp1_touched", False),
        "tp1_touched_at": tp1_record["timestamp_utc"] if tp1_record else None,
        "tp2_touched": payload.get("tp2_touched", False),
        "tp2_touched_at": tp2_record["timestamp_utc"] if tp2_record else None,
    }
    payload["evidence"]["sl_evidence"] = {
        "sl_touched": payload.get("sl_touched", False),
        "touched_at": sl_record["timestamp_utc"] if sl_record else None,
        "record": sl_record["raw"] if sl_record else None,
    }
    payload["evidence"]["invalidation_evidence"] = {
        "invalidation_touched": payload.get("invalidation_touched", False),
        "touched_at": inv_record["timestamp_utc"] if inv_record else None,
        "record": inv_record["raw"] if inv_record else None,
    }

    payload["outcome_id"] = build_outcome_id(
        paper_trade_id=payload.get("paper_trade_id"),
        trade_fate=payload.get("trade_fate"),
        closed_at=payload.get("closed_at"),
        evidence_seed={
            "entry": payload["evidence"]["entry_evidence"],
            "tp": payload["evidence"]["tp_evidence"],
            "sl": payload["evidence"]["sl_evidence"],
            "invalidation": payload["evidence"]["invalidation_evidence"],
        },
    )
    _dedupe_codes(payload)
    return payload
