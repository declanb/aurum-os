"""
Market data service — live prices, candles, and account information
via the MetaApi RPC connection to Vantage MT5.
"""

import logging
from typing import Optional
from api.services.vantage_client import get_connection

logger = logging.getLogger(__name__)


async def get_price(symbol: str = "XAUUSD") -> dict:
    """
    Get the current bid/ask/spread for a symbol.
    Returns: { symbol, bid, ask, spread, time }
    """
    connection = await get_connection()
    price = await connection.get_symbol_price(symbol)
    return {
        "symbol": symbol,
        "bid": price.get("bid"),
        "ask": price.get("ask"),
        "spread": round((price.get("ask", 0) - price.get("bid", 0)), 5),
        "time": price.get("time"),
    }


async def get_candles(
    symbol: str = "XAUUSD",
    timeframe: str = "1h",
    count: int = 100,
) -> list[dict]:
    """
    Get historical OHLCV candles.
    
    Timeframe options: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mn
    Returns list of { time, open, high, low, close, tickVolume }
    """
    connection = await get_connection()
    candles = await connection.get_candle(symbol, timeframe, count)
    
    return [
        {
            "time": c.get("time"),
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "tick_volume": c.get("tickVolume", 0),
        }
        for c in (candles or [])
    ]


async def get_account_info() -> dict:
    """
    Get live account information from Vantage MT5.
    Returns: { balance, equity, margin, freeMargin, leverage, currency, ... }
    """
    connection = await get_connection()
    info = await connection.get_account_information()
    return {
        "balance": info.get("balance"),
        "equity": info.get("equity"),
        "margin": info.get("margin"),
        "free_margin": info.get("freeMargin"),
        "leverage": info.get("leverage"),
        "currency": info.get("currency", "USD"),
        "broker": info.get("broker", "Vantage"),
        "server": info.get("server", ""),
        "name": info.get("name", ""),
        "platform": info.get("platform", "mt5"),
    }


async def get_symbol_specification(symbol: str = "XAUUSD") -> Optional[dict]:
    """
    Get the symbol specification (contract size, min lot, max lot, etc.).
    """
    connection = await get_connection()
    spec = await connection.get_symbol_specification(symbol)
    if not spec:
        return None
    return {
        "symbol": symbol,
        "description": spec.get("description", ""),
        "contract_size": spec.get("contractSize"),
        "min_volume": spec.get("minVolume"),
        "max_volume": spec.get("maxVolume"),
        "volume_step": spec.get("volumeStep"),
        "digits": spec.get("digits"),
        "trade_mode": spec.get("tradeMode"),
    }
