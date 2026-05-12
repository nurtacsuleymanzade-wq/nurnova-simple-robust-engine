"""S12-B Flow Collector — NOVA SIMPLE ROBUST ENGINE v1.

DUZELTME v2: kline_1m + depth20 event'leri de islenir.
- aggTrade    → 1s bucket (buy/sell flow)
- bookTicker  → anlık bid/ask
- kline_1m    → Binance resmi 1dk mum
- depth20     → order book derinliği, duvarlar, sweep riski

No live websocket. No private API. No orders.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.simple.ws_agg_trade_collector    import parse_agg_trade
from src.simple.ws_book_ticker_collector  import parse_book_ticker
from src.simple.ws_depth_collector        import parse_depth20
from src.simple.flow_bucket_builder       import build_bucket
from src.simple.raw_flow_event_logger     import append_flow_event
from src.simple.latest_flow_state_writer  import write_latest_flow_state
from src.simple.latest_depth_state_writer import write_latest_depth_state


DEPTH_JSONL_PATH  = Path("data/simple/live_depth_events.jsonl")
DEPTH_STATE_PATH  = Path("state/simple/latest_depth_state.json")


def _second_key(ts_ms: int) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_kline(raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        if raw.get("e") != "kline":
            return None
        k = raw["k"]
        return {
            "timestamp_utc": _utc_now(),
            "stream":        "kline_1m",
            "symbol":        str(raw.get("s", "")),
            "open_time_ms":  int(k["t"]),
            "close_time_ms": int(k["T"]),
            "open":          float(k["o"]),
            "high":          float(k["h"]),
            "low":           float(k["l"]),
            "close":         float(k["c"]),
            "volume":        float(k["v"]),
            "is_closed":     bool(k["x"]),
            "interval":      str(k.get("i", "1m")),
        }
    except (KeyError, TypeError, ValueError):
        return None


class FlowCollector:
    """Stateful 1-second flow collector for a single symbol."""

    def __init__(
        self,
        symbol:      str,
        jsonl_path:  str | Path,
        state_path:  str | Path,
    ) -> None:
        self.symbol     = symbol
        self.jsonl_path = Path(jsonl_path)
        self.state_path = Path(state_path)

        self._trades:           list[dict[str, Any]] = []
        self._last_book_ticker: dict[str, Any] | None = None
        self._current_second:   str | None = None
        self._malformed_count   = 0
        self._consecutive_empty = 0

        # Kline state
        self._current_kline:       dict[str, Any] | None = None
        self._latest_closed_kline: dict[str, Any] | None = None

        # Depth state
        self._latest_depth:  dict[str, Any] | None = None
        self._depth_count    = 0

        self._counters: dict[str, int] = {
            "agg_trade_events":     0,
            "book_ticker_events":   0,
            "kline_events":         0,
            "kline_closed_events":  0,
            "depth_events":         0,
            "malformed_events":     0,
            "buckets_built":        0,
        }

        self._last_quality_level = "OK"
        self._last_quality_score = 1.0

    def ingest(self, raw: dict[str, Any]) -> None:
        event_type = raw.get("e")
        stream_tag = raw.get("_stream", "")

        # --- depth20 ---
        if stream_tag == "depth20" or (
            "bids" in raw and "asks" in raw and event_type is None
        ):
            parsed = parse_depth20(raw, self.symbol)
            if parsed:
                self._counters["depth_events"] += 1
                self._depth_count += 1
                self._latest_depth = parsed

                # Depth JSONL'e yaz (ayrı dosya)
                DEPTH_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
                with DEPTH_JSONL_PATH.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(parsed, ensure_ascii=False) + "\n")

                # Depth state'i güncelle
                write_latest_depth_state(
                    path=DEPTH_STATE_PATH,
                    latest_depth=parsed,
                    event_count=self._depth_count,
                )
            else:
                self._malformed_count += 1
                self._counters["malformed_events"] += 1
            return

        # --- aggTrade ---
        if event_type == "aggTrade":
            parsed = parse_agg_trade(raw)
            if parsed is None:
                self._malformed_count += 1
                self._counters["malformed_events"] += 1
                append_flow_event(self.jsonl_path, {"raw": raw, "malformed": True})
                return

            self._counters["agg_trade_events"] += 1
            append_flow_event(self.jsonl_path, parsed)

            ts_ms  = int(raw.get("T", raw.get("E", 0)))
            second = _second_key(ts_ms)

            if self._current_second is None:
                self._current_second = second

            if second != self._current_second:
                self._flush_bucket(self._current_second)
                self._current_second = second
                self._trades         = []
                self._malformed_count = 0

            self._trades.append(parsed)

        # --- bookTicker ---
        elif event_type == "bookTicker" or ("b" in raw and "a" in raw and "s" in raw):
            parsed = parse_book_ticker(raw)
            if parsed is None:
                self._malformed_count += 1
                self._counters["malformed_events"] += 1
                append_flow_event(self.jsonl_path, {"raw": raw, "malformed": True})
                return
            self._counters["book_ticker_events"] += 1
            self._last_book_ticker = parsed
            append_flow_event(self.jsonl_path, parsed)

        # --- kline ---
        elif event_type == "kline":
            parsed = _parse_kline(raw)
            if parsed is None:
                self._malformed_count += 1
                self._counters["malformed_events"] += 1
                return

            self._counters["kline_events"] += 1
            self._current_kline = parsed

            if parsed["is_closed"]:
                self._counters["kline_closed_events"] += 1
                self._latest_closed_kline = parsed
                append_flow_event(self.jsonl_path, {**parsed, "event": "KLINE_CLOSED"})

        else:
            self._malformed_count += 1
            self._counters["malformed_events"] += 1
            append_flow_event(self.jsonl_path, {"raw": raw, "malformed": True})

    def flush(self) -> dict[str, Any] | None:
        if self._current_second is not None:
            return self._flush_bucket(self._current_second)
        return None

    def _flush_bucket(self, bucket_second: str) -> dict[str, Any]:
        if not self._trades:
            self._consecutive_empty += 1
        else:
            self._consecutive_empty = 0

        bucket = build_bucket(
            symbol=self.symbol,
            bucket_second=bucket_second,
            trades=self._trades,
            last_book_ticker=self._last_book_ticker,
            ws_agg_trade_connected=True,
            ws_book_ticker_connected=True,
            malformed_count=self._malformed_count,
            age_seconds=0.0,
            consecutive_empty_seconds=self._consecutive_empty,
        )

        self._counters["buckets_built"] += 1
        self._last_quality_level = bucket["data_quality"]["level"]
        self._last_quality_score = bucket["data_quality"]["score"]

        write_latest_flow_state(
            path=self.state_path,
            latest_bucket=bucket,
            quality_level=self._last_quality_level,
            quality_score=self._last_quality_score,
            event_counters=dict(self._counters),
            current_kline=self._current_kline,
            latest_closed_kline=self._latest_closed_kline,
        )

        return bucket
