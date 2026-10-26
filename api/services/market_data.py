"""
Market data service \u2014 wraps the Revolut X client to expose normalised
price, candle, account-info, and pair-spec dicts to the rest of Aurum OS.

The underlying transport is revolut_x_client: signed HTTP when env keys
are set, otherwise the `revx` CLI.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from api.services import revolut_x_client as rx

logger = logging.getLogger(__name__)


def _first(data: Any) -> Optional[dict]:
    """revx commands return a list even for single-item queries."""
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


async def get_price(symbol: str = "BTC-USD") -> dict:
    """Current bid/ask/spread for a Revolut X pair."""
    ticker = _first(await rx.get_ticker(symbol)) or {}
    bid = float(ticker.get("bid") or 0)
    ask = float(ticker.get("ask") or 0)
    last = float(ticker.get("last_price") or ticker.get("last") or ticker.get("mid") or 0) or None
    return {
        "symbol": ticker.get("symbol", symbol),
        "bid": bid,
        "ask": ask,
        "spread": round(ask - bid, 8) if bid and ask else 0.0,
        "last": last,
        "time": ticker.get("timestamp") or ticker.get("time"),
    }


async def get_candles(
    symbol: str = "BTC-USD",
    timeframe: str = "1h",
    count: int = 100,
) -> list[dict]:
    """OHLCV candles. Maps Aurum timeframes (1m,5m,15m,1h,4h,1d) to revx intervals."""
    interval_map = {
        "1m": "1", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "4h": "240", "1d": "D", "1w": "W",
    }
    interval = interval_map.get(timeframe, "60")
    raw = await rx.get_candles(symbol, interval=interval)
    candles = raw if isinstance(raw, list) else (raw.get("candles", []) if isinstance(raw, dict) else [])
    return [
        {
            "time": c.get("start") or c.get("timestamp") or c.get("time") or c.get("t"),
            "open": float(c.get("open") or c.get("o") or 0),
            "high": float(c.get("high") or c.get("h") or 0),
            "low": float(c.get("low") or c.get("l") or 0),
            "close": float(c.get("close") or c.get("c") or 0),
            "tick_volume": float(c.get("volume") or c.get("v") or 0),
        }
        for c in candles[-count:]
    ]


async def get_account_info() -> dict:
    """Aggregate balances across all currencies into an account snapshot."""
    balances = await rx.get_balances(include_zero=False)
    rows = balances if isinstance(balances, list) else []
    return {
        "balance": None,
        "equity": None,
        "margin": 0,
        "free_margin": None,
        "leverage": 1,  # Revolut X is spot, no leverage
        "currency": "MULTI",
        "broker": "Revolut X",
        "server": "revx.revolut.com",
        "name": "Revolut X Spot",
        "platform": "revolut-x",
        "balances": [
            {
                "currency": b.get("currency"),
                "available": float(b.get("available") or 0),
                "reserved": float(b.get("reserved") or 0),
                "staked": float(b.get("staked") or 0),
                "balance": float(b.get("total") or b.get("balance") or 0),
            }
            for b in rows
        ],
    }


async def get_orderbook(symbol: str = "BTC-USD", limit: int = 20) -> dict:
    """Top-of-book depth. Returns normalised {bids:[{price,size}], asks:[{price,size}]}."""
    raw = await rx.get_orderbook(symbol, limit=limit)
    book = raw if isinstance(raw, dict) else {}
    def _norm(side):
        return [
            {"price": float(lvl.get("price") or 0), "size": float(lvl.get("quantity") or lvl.get("size") or 0)}
            for lvl in (book.get(side) or [])
        ]
    return {"symbol": symbol, "bids": _norm("bids"), "asks": _norm("asks")}


# Percent-point keys a Revolut X ticker may carry. 1.5 means +1.5%.
# Absolute price-change fields are intentionally absent: treating them as
# percents would invent a move.
_CHANGE_PCT_KEYS = (
    "change_24h_pct",
    "price_change_percentage_24h",
    "price_change_pct_24h",
    "price_change_pct",
    "priceChangePercent",
    "change_percent",
    "change_percentage",
    "changePercent",
    "percentage_change",
    "pct_change",
    "change_pct",
)


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def change_24h_pct(row: Any) -> Optional[float]:
    """24h change in percent points from one ticker row.

    Uses an explicit percent field when the payload has one. Otherwise derives
    it from that same row's open and last (or mid). Returns None when the row
    does not contain enough information. Does not substitute a price.
    """
    if not isinstance(row, dict):
        return None
    for key in _CHANGE_PCT_KEYS:
        if key not in row:
            continue
        num = _optional_float(row.get(key))
        if num is not None:
            return num
    open_px = _optional_float(row.get("open"))
    if open_px is None:
        open_px = _optional_float(row.get("open_24h"))
    if open_px is None:
        open_px = _optional_float(row.get("open24h"))
    last = None
    for key in ("last_price", "last", "price", "mid"):
        last = _optional_float(row.get(key))
        if last is not None and last > 0:
            break
        last = None
    if open_px and open_px > 0 and last:
        return (last - open_px) / open_px * 100.0
    return None


async def get_tickers(symbols: Optional[list[str]] = None) -> list[dict]:
    """Multi-pair tickers for the market list.

    ``change_24h_pct`` is set only when the payload carries a percent change
    or an open and a last. Otherwise it is null.
    """
    raw = await rx.list_tickers(symbols)
    rows = raw if isinstance(raw, list) else []
    out = []
    for r in rows:
        bid = float(r.get("bid") or 0)
        ask = float(r.get("ask") or 0)
        last = float(r.get("last_price") or r.get("last") or r.get("mid") or 0)
        out.append({
            "symbol": r.get("symbol"),
            "bid": bid,
            "ask": ask,
            "last": last,
            "mid": float(r.get("mid") or 0) or (bid + ask) / 2 if bid and ask else last,
            "open": _optional_float(r.get("open") if r.get("open") not in (None, "") else r.get("open_24h")),
            "change_24h_pct": change_24h_pct(r),
        })
    return out


async def get_symbol_specification(symbol: str = "BTC-USD") -> Optional[dict]:
    """Pair specification (min order size, price increment, etc.)."""
    pair = _first(await rx.get_pair(symbol))
    if not pair:
        return None
    return {
        "symbol": pair.get("symbol", symbol),
        "description": f"{pair.get('base', '')}/{pair.get('quote', '')}",
        "base_currency": pair.get("base"),
        "quote_currency": pair.get("quote"),
        "min_volume": float(pair.get("min_order_size") or pair.get("minQuantity") or 0) or None,
        "max_volume": float(pair.get("max_order_size") or pair.get("maxQuantity") or 0) or None,
        "volume_step": float(pair.get("base_step") or pair.get("quantityIncrement") or 0) or None,
        "price_increment": float(pair.get("quote_step") or pair.get("priceIncrement") or 0) or None,
        "min_quote": float(pair.get("min_order_size_quote") or 0) or None,
        "status": pair.get("status"),
    }
