"""
Vantage broker endpoints — account info, live prices, positions, and trade execution.
All endpoints are async and use the MetaApi connection to Vantage MT5.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlmodel import Session

from api.core.db import get_session
from api.models.trade import TradeIdea, ExecutionTicket, ApprovalEvent
from api.services import market_data, trade_executor
from api.services.vantage_client import get_connection_status

router = APIRouter(prefix="/vantage", tags=["vantage-broker"])


# ── Schemas ──────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    volume: float = 0.01  # Default minimum lot size
    use_market: bool = True  # True = market order, False = limit at trade's entry_price

class ModifyRequest(BaseModel):
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


# ── Connection ───────────────────────────────────────────────────────────

@router.get("/status")
async def broker_status():
    """Check if the MetaApi connection to Vantage MT5 is alive."""
    status = await get_connection_status()
    return status


# ── Account Info ─────────────────────────────────────────────────────────

@router.get("/account")
async def account_info():
    """Live account information — balance, equity, margin, leverage."""
    try:
        info = await market_data.get_account_info()
        return info
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch account info: {e}")


# ── Market Data ──────────────────────────────────────────────────────────

@router.get("/price/{symbol}")
async def live_price(symbol: str = "XAUUSD"):
    """Current bid/ask/spread for a symbol."""
    try:
        price = await market_data.get_price(symbol)
        return price
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch price: {e}")


@router.get("/candles/{symbol}")
async def historical_candles(symbol: str = "XAUUSD", timeframe: str = "1h", count: int = 100):
    """Historical OHLCV candles. Timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mn."""
    try:
        candles = await market_data.get_candles(symbol, timeframe, count)
        return {"symbol": symbol, "timeframe": timeframe, "count": len(candles), "candles": candles}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch candles: {e}")


@router.get("/symbol/{symbol}")
async def symbol_spec(symbol: str = "XAUUSD"):
    """Get symbol specification (contract size, min/max lot, etc.)."""
    try:
        spec = await market_data.get_symbol_specification(symbol)
        if not spec:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        return spec
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch symbol spec: {e}")


# ── Positions & Orders ───────────────────────────────────────────────────

@router.get("/positions")
async def open_positions():
    """List all open positions on the Vantage account."""
    try:
        positions = await trade_executor.get_positions()
        return {"count": len(positions), "positions": positions}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch positions: {e}")


@router.get("/orders")
async def pending_orders():
    """List all pending orders on the Vantage account."""
    try:
        orders = await trade_executor.get_orders()
        return {"count": len(orders), "orders": orders}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch orders: {e}")


# ── Trade Execution ──────────────────────────────────────────────────────

@router.post("/execute/{trade_id}")
async def execute_trade(
    trade_id: int,
    request: ExecuteRequest,
    session: Session = Depends(get_session),
):
    """
    Execute an approved TradeIdea as a live order on Vantage MT5.
    
    Only trades with status "Approved" can be executed.
    Creates an ExecutionTicket to track the broker response.
    """
    # 1. Validate the trade exists and is approved
    trade = session.get(TradeIdea, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade idea not found")
    if trade.status != "Approved":
        raise HTTPException(
            status_code=400,
            detail=f"Trade must be Approved to execute. Current status: {trade.status}"
        )
    
    # 2. Find the approval event for the execution ticket
    from sqlmodel import select
    approval = session.exec(
        select(ApprovalEvent)
        .where(ApprovalEvent.trade_idea_id == trade_id)
        .order_by(ApprovalEvent.timestamp.desc())
    ).first()
    
    if not approval:
        raise HTTPException(status_code=400, detail="No approval event found for this trade")
    
    # 3. Execute the trade on Vantage
    try:
        entry_price = None if request.use_market else trade.entry_price
        result = await trade_executor.execute_trade(
            symbol=trade.symbol,
            direction=trade.direction,
            volume=request.volume,
            entry_price=entry_price,
            stop_loss=trade.stop_price,
            take_profit=trade.target_price,
            comment=f"AURUM#{trade.id}",
        )
    except Exception as e:
        # Record the failure
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
    
    # 4. Record the execution ticket
    ticket = ExecutionTicket(
        approval_event_id=approval.id,
        adapter_status="Filled" if result["success"] else "Rejected",
        provider_response=str(result),
    )
    session.add(ticket)
    
    # 5. Update trade status
    if result["success"]:
        trade.status = "Sent"
    else:
        trade.status = "Needs Work"
    session.add(trade)
    session.commit()
    
    return {
        "trade_id": trade_id,
        "execution": result,
        "ticket_status": ticket.adapter_status,
        "trade_status": trade.status,
    }


# ── Position Management ──────────────────────────────────────────────────

@router.post("/close/{position_id}")
async def close_position(position_id: str):
    """Close an open position by its MT5 position ID."""
    try:
        result = await trade_executor.close_position(position_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to close position: {e}")


@router.patch("/modify/{position_id}")
async def modify_position(position_id: str, request: ModifyRequest):
    """Modify SL/TP on an open position."""
    if request.stop_loss is None and request.take_profit is None:
        raise HTTPException(status_code=400, detail="At least one of stop_loss or take_profit must be provided")
    try:
        result = await trade_executor.modify_position(
            position_id,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to modify position: {e}")
