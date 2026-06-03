"""
Revolut X broker endpoints \u2014 account, market data, orders, and trade execution.

All write paths go through Guardian + ApprovalEvent. The underlying transport
is the `revx` CLI invoked by api.services.revolut_x_client.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlmodel import Session, select

from api.core.config import settings
from api.core.db import get_session
from api.models.trade import TradeIdea, ExecutionTicket, ApprovalEvent
from api.services import market_data, trade_executor
from api.services.revolut_x_client import get_status

router = APIRouter(prefix="/revolut-x", tags=["revolut-x-broker"])


# \u2500\u2500 Schemas \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class ExecuteRequest(BaseModel):
    volume: float = 0.0001  # Base-asset qty (e.g. BTC). Adjust per pair.
    use_market: bool = True  # True = market; False = limit at trade.entry_price
    post_only: bool = False


# \u2500\u2500 Connection \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@router.get("/status")
async def broker_status():
    """Check if `revx` CLI auth is healthy by hitting a benign read endpoint."""
    return await get_status()


# \u2500\u2500 Account Info \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@router.get("/account")
async def account_info():
    """Account snapshot \u2014 multi-currency balances on the Revolut X spot account."""
    try:
        return await market_data.get_account_info()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch account info: {e}")


# \u2500\u2500 Market Data \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@router.get("/price/{symbol}")
async def live_price(symbol: str = settings.REVOLUT_X_DEFAULT_PAIR):
    try:
        return await market_data.get_price(symbol)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch price: {e}")


@router.get("/candles/{symbol}")
async def historical_candles(
    symbol: str = settings.REVOLUT_X_DEFAULT_PAIR,
    timeframe: str = "1h",
    count: int = 100,
):
    """OHLCV candles. timeframe \u2208 {1m,5m,15m,30m,1h,4h,1d,1w}."""
    try:
        candles = await market_data.get_candles(symbol, timeframe, count)
        return {"symbol": symbol, "timeframe": timeframe, "count": len(candles), "candles": candles}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch candles: {e}")


@router.get("/symbol/{symbol}")
async def symbol_spec(symbol: str = settings.REVOLUT_X_DEFAULT_PAIR):
    try:
        spec = await market_data.get_symbol_specification(symbol)
        if not spec:
            raise HTTPException(status_code=404, detail=f"Pair {symbol} not found")
        return spec
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch pair spec: {e}")


@router.get("/orderbook/{symbol}")
async def orderbook(symbol: str = settings.REVOLUT_X_DEFAULT_PAIR, limit: int = 20):
    try:
        return await market_data.get_orderbook(symbol, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch order book: {e}")


@router.get("/tickers")
async def tickers(symbols: Optional[str] = None):
    """Comma-separated list of pairs e.g. ?symbols=BTC-USD,ETH-USD,SOL-USD"""
    try:
        sym_list = [s.strip() for s in symbols.split(",")] if symbols else None
        return await market_data.get_tickers(sym_list)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch tickers: {e}")


# \u2500\u2500 Positions & Orders \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@router.get("/positions")
async def open_positions():
    """Synthesised positions from non-zero crypto balances (spot exchange)."""
    try:
        positions = await trade_executor.get_positions()
        return {"count": len(positions), "positions": positions}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch positions: {e}")


@router.get("/orders")
async def pending_orders():
    try:
        orders = await trade_executor.get_orders()
        return {"count": len(orders), "orders": orders}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch orders: {e}")


# \u2500\u2500 Trade Execution \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@router.post("/execute/{trade_id}")
async def execute_trade(
    trade_id: int,
    request: ExecuteRequest,
    session: Session = Depends(get_session),
):
    """Execute an Approved TradeIdea on Revolut X. Requires an ApprovalEvent."""
    trade = session.get(TradeIdea, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade idea not found")
    if trade.status != "Approved":
        raise HTTPException(
            status_code=400,
            detail=f"Trade must be Approved to execute. Current status: {trade.status}",
        )

    approval = session.exec(
        select(ApprovalEvent)
        .where(ApprovalEvent.trade_idea_id == trade_id)
        .order_by(ApprovalEvent.timestamp.desc())
    ).first()
    if not approval:
        raise HTTPException(status_code=400, detail="No approval event found for this trade")

    try:
        entry_price = None if request.use_market else trade.entry_price
        result = await trade_executor.execute_trade(
            symbol=trade.symbol,
            direction=trade.direction,
            volume=request.volume,
            entry_price=entry_price,
            comment=f"AURUM#{trade.id}",
            post_only=request.post_only,
            client_order_id=f"AURUM-{trade.id}-{approval.id}",
        )
    except Exception as e:
        ticket = ExecutionTicket(
            approval_event_id=approval.id,
            adapter_status="Failed",
            provider_response=str(e),
        )
        session.add(ticket)
        trade.status = "Needs Work"
        session.add(trade)
        session.commit()
        raise HTTPException(status_code=503, detail=f"Trade execution failed: {e}")

    ticket = ExecutionTicket(
        approval_event_id=approval.id,
        adapter_status="Filled" if result["success"] else "Rejected",
        provider_response=str(result),
    )
    session.add(ticket)

    trade.status = "Sent" if result["success"] else "Needs Work"
    session.add(trade)
    session.commit()

    return {
        "trade_id": trade_id,
        "execution": result,
        "ticket_status": ticket.adapter_status,
        "trade_status": trade.status,
    }


# \u2500\u2500 Order Management \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@router.post("/close/{position_id}")
async def close_position(position_id: str):
    """Sell the full available balance of a base asset at market (e.g. position_id='BTC')."""
    try:
        return await trade_executor.close_position(position_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to close position: {e}")
