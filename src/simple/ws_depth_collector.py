"""S12 depth20 websocket message parser — NOVA SIMPLE ROBUST ENGINE v1.

Parses raw Binance depth20 websocket messages into normalized dicts.
Extracts bid/ask clusters, wall detection, sweep risk.
No live websocket connection — pure parsing only.
No private API. No authentication. No orders.

Binance depth20 stream format (@depth20@100ms):
{
  "lastUpdateId": 123456,
  "bids": [["price", "qty"], ...],  # en iyi 20 bid, yuksekten dusuge
  "asks": [["price", "qty"], ...]   # en iyi 20 ask, dusukten yukse
}
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_levels(raw_levels: list) -> list[dict[str, float]]:
    """Parse [[price_str, qty_str], ...] into [{price, qty, notional}, ...]"""
    result = []
    for item in raw_levels:
        try:
            price = float(item[0])
            qty   = float(item[1])
            if price > 0 and qty > 0:
                result.append({
                    "price":    round(price, 8),
                    "qty":      round(qty, 8),
                    "notional": round(price * qty, 4),
                })
        except (IndexError, ValueError, TypeError):
            continue
    return result


def _cluster_analysis(levels: list[dict[str, float]]) -> dict[str, Any]:
    """
    Seviyeler arasında büyük kümeleri tespit et.
    Ortalama notional'ın 3x üstündekiler = potansiyel duvar.
    """
    if not levels:
        return {
            "total_notional": 0.0,
            "avg_notional":   0.0,
            "max_notional":   0.0,
            "wall_price":     None,
            "wall_notional":  None,
            "wall_strength":  0.0,
            "has_wall":       False,
            "level_count":    0,
        }

    notionals = [lv["notional"] for lv in levels]
    total     = sum(notionals)
    avg       = total / len(notionals)
    max_not   = max(notionals)

    # En büyük duvarı bul
    wall_price    = None
    wall_notional = 0.0
    for lv in levels:
        if lv["notional"] >= avg * 3.0 and lv["notional"] > wall_notional:
            wall_price    = lv["price"]
            wall_notional = lv["notional"]

    has_wall     = wall_price is not None
    wall_strength = round(wall_notional / avg, 2) if avg > 0 and has_wall else 0.0

    return {
        "total_notional": round(total, 2),
        "avg_notional":   round(avg, 2),
        "max_notional":   round(max_not, 2),
        "wall_price":     wall_price,
        "wall_notional":  round(wall_notional, 2) if has_wall else None,
        "wall_strength":  wall_strength,
        "has_wall":       has_wall,
        "level_count":    len(levels),
    }


def _sweep_risk(
    bid_wall: dict[str, Any],
    ask_wall: dict[str, Any],
    mid_price: float | None,
) -> dict[str, Any]:
    """
    Fiyat bir duvara yakın mı? Sweep (ani likidite silme) riski var mı?
    """
    if mid_price is None:
        return {"sweep_risk": "UNKNOWN", "nearest_wall_side": None, "distance_pct": None}

    risks = []

    if bid_wall["has_wall"] and bid_wall["wall_price"]:
        dist = abs(mid_price - bid_wall["wall_price"]) / mid_price * 100
        risks.append(("BID", dist, bid_wall["wall_strength"]))

    if ask_wall["has_wall"] and ask_wall["wall_price"]:
        dist = abs(ask_wall["wall_price"] - mid_price) / mid_price * 100
        risks.append(("ASK", dist, ask_wall["wall_strength"]))

    if not risks:
        return {"sweep_risk": "NO_WALL", "nearest_wall_side": None, "distance_pct": None}

    # En yakın duvar
    nearest = min(risks, key=lambda x: x[1])
    side, dist, strength = nearest

    if dist < 0.05:
        risk_label = "IMMINENT"
    elif dist < 0.15:
        risk_label = "HIGH"
    elif dist < 0.30:
        risk_label = "MODERATE"
    else:
        risk_label = "LOW"

    return {
        "sweep_risk":        risk_label,
        "nearest_wall_side": side,
        "distance_pct":      round(dist, 4),
        "wall_strength":     strength,
    }


def _imbalance(bid_total: float, ask_total: float) -> dict[str, Any]:
    """Bid vs ask toplam notional dengesi."""
    total = bid_total + ask_total
    if total == 0:
        return {"imbalance_ratio": 0.0, "dominant_side": "NEUTRAL", "imbalance_label": "NEUTRAL"}

    ratio = round((bid_total - ask_total) / total, 4)

    if ratio > 0.3:
        label = "STRONG_BID"
        dominant = "BID"
    elif ratio > 0.1:
        label = "MILD_BID"
        dominant = "BID"
    elif ratio < -0.3:
        label = "STRONG_ASK"
        dominant = "ASK"
    elif ratio < -0.1:
        label = "MILD_ASK"
        dominant = "ASK"
    else:
        label = "BALANCED"
        dominant = "NEUTRAL"

    return {
        "imbalance_ratio": ratio,
        "dominant_side":   dominant,
        "imbalance_label": label,
    }


def parse_depth20(raw: dict[str, Any], symbol: str = "BTCUSDT") -> dict[str, Any] | None:
    """
    Binance depth20@100ms event'ini isle.
    
    raw dict iki formatta gelebilir:
    1. Direkt: {"lastUpdateId": ..., "bids": [...], "asks": [...]}
    2. Combined stream: {"stream": "btcusdt@depth20@100ms", "data": {...}}
    """
    try:
        # Combined stream wrapper'ini soy
        data = raw.get("data", raw)

        bids_raw = data.get("bids", [])
        asks_raw = data.get("asks", [])

        if not bids_raw and not asks_raw:
            return None

        bids = _parse_levels(bids_raw)
        asks = _parse_levels(asks_raw)

        if not bids and not asks:
            return None

        # En iyi bid/ask
        best_bid = bids[0]["price"]  if bids else None
        best_ask = asks[0]["price"]  if asks else None
        mid_price = round((best_bid + best_ask) / 2, 8) if best_bid and best_ask else None

        # Küme analizi
        bid_cluster = _cluster_analysis(bids)
        ask_cluster = _cluster_analysis(asks)

        # Dengesizlik
        imbal = _imbalance(bid_cluster["total_notional"], ask_cluster["total_notional"])

        # Sweep riski
        sweep = _sweep_risk(bid_cluster, ask_cluster, mid_price)

        return {
            "timestamp_utc":   _utc_now(),
            "stream":          "depth20",
            "symbol":          symbol.upper(),
            "last_update_id":  data.get("lastUpdateId"),
            "best_bid":        best_bid,
            "best_ask":        best_ask,
            "mid_price":       mid_price,
            "spread":          round(best_ask - best_bid, 8) if best_bid and best_ask else None,

            "bid_levels":      bids[:5],   # sadece ilk 5 seviyeyi sakla
            "ask_levels":      asks[:5],

            "bid_cluster":     bid_cluster,
            "ask_cluster":     ask_cluster,
            "imbalance":       imbal,
            "sweep_risk":      sweep,

            "reason_codes": [
                f"SYMBOL_{symbol.upper()}",
                f"IMBALANCE_{imbal['imbalance_label']}",
                f"SWEEP_{sweep['sweep_risk']}",
                "SOURCE_LIVE_WS_REAL",
                "NO_PRIVATE_API",
            ],
        }

    except Exception:
        return None
