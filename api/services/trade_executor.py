"""
Trade execution service — place, modify, and close orders
on the Vantage MT5 account via MetaApi.
"""

import logging
from typing import Optional
from api.services.vantage_client import get_connection

logger = logging.getLogger(__name__)


async def execute_trade(
    symbol: str,
    direction: str,
    volume: float,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    comment: str = "AURUM OS",
) -> dict:
    """
    Execute a trade on the Vantage MT5 account.
    
    If entry_price is None or 0, executes as a market order.
    Otherwise places a pending limit order.
    
    Args:
        symbol: Trading symbol (e.g. XAUUSD)
        direction: "LONG" or "SHORT" 
        volume: Lot size
        entry_price: Optional price for limit order
        stop_loss: Stop loss price
        take_profit: Take profit price
        comment: Order comment/label
    
    Returns:
        MetaApi trade result dict with orderId, etc.
    """
    connection = await get_connection()
    
    trade_params = {
        "symbol": symbol,
        "volume": volume,
        "comment": comment,
    }
    
    if stop_loss:
        trade_params["stopLoss"] = stop_loss
    if take_profit:
        trade_params["takeProfit"] = take_profit
    
    is_market = not entry_price or entry_price == 0
    
    if direction.upper() == "LONG":
        if is_market:
            result = await connection.create_market_buy_order(**trade_params)
        else:
            trade_params["openPrice"] = entry_price
            result = await connection.create_limit_buy_order(**trade_params)
    elif direction.upper() == "SHORT":
        if is_market:
            result = await connection.create_market_sell_order(**trade_params)
        else:
            trade_params["openPrice"] = entry_price
            result = await connection.create_limit_sell_order(**trade_params)
    else:
        raise ValueError(f"Invalid direction: {direction}. Must be LONG or SHORT.")
    
    logger.info(
        "Trade executed: %s %s %s vol=%s — result: %s",
        direction, symbol, "MARKET" if is_market else f"LIMIT@{entry_price}",
        volume, result
    )
    
    return {
        "success": result.get("stringCode") == "TRADE_RETCODE_DONE",
        "order_id": result.get("orderId"),
        "string_code": result.get("stringCode"),
        "numeric_code": result.get("numericCode"),
        "message": result.get("message", ""),
    }


async def get_positions() -> list[dict]:
    """Get all open positions on the account."""
    connection = await get_connection()
    positions = await connection.get_positions()
    
    return [
        {
            "id": p.get("id"),
            "symbol": p.get("symbol"),
            "type": p.get("type"),  # POSITION_TYPE_BUY or POSITION_TYPE_SELL
            "direction": "LONG" if p.get("type") == "POSITION_TYPE_BUY" else "SHORT",
            "volume": p.get("volume"),
            "open_price": p.get("openPrice"),
            "current_price": p.get("currentPrice"),
            "stop_loss": p.get("stopLoss"),
            "take_profit": p.get("takeProfit"),
            "profit": p.get("profit"),
            "swap": p.get("swap", 0),
            "commission": p.get("commission", 0),
            "comment": p.get("comment", ""),
            "open_time": p.get("time"),
        }
        for p in (positions or [])
    ]


async def get_orders() -> list[dict]:
    """Get all pending orders on the account."""
    connection = await get_connection()
    orders = await connection.get_orders()
    
    return [
        {
            "id": o.get("id"),
            "symbol": o.get("symbol"),
            "type": o.get("type"),
            "volume": o.get("volume"),
            "open_price": o.get("openPrice"),
            "stop_loss": o.get("stopLoss"),
            "take_profit": o.get("takeProfit"),
            "comment": o.get("comment", ""),
            "time": o.get("time"),
        }
        for o in (orders or [])
    ]


async def close_position(position_id: str) -> dict:
    """Close a specific open position by its ID."""
    connection = await get_connection()
    result = await connection.close_position(position_id)
    
    logger.info("Position %s close result: %s", position_id, result)
    
    return {
        "success": result.get("stringCode") == "TRADE_RETCODE_DONE",
        "string_code": result.get("stringCode"),
        "numeric_code": result.get("numericCode"),
        "message": result.get("message", ""),
    }


async def modify_position(
    position_id: str,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> dict:
    """Modify SL/TP on an open position."""
    connection = await get_connection()
    result = await connection.modify_position(
        position_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    
    logger.info("Position %s modify result: %s", position_id, result)
    
    return {
        "success": result.get("stringCode") == "TRADE_RETCODE_DONE",
        "string_code": result.get("stringCode"),
        "numeric_code": result.get("numericCode"),
        "message": result.get("message", ""),
    }
