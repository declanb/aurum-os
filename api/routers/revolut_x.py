"""
Revolut X broker endpoints \u2014 account, market data, orders, and trade execution.

All write paths go through Guardian + ApprovalEvent. The underlying transport
is the `revx` CLI invoked by api.services.revolut_x_client.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from sqlmodel import Session, select

from api.core.config import settings
from api.core.db import get_session
from api.models.trade import TradeIdea, ExecutionTicket, ApprovalEvent
from api.services import market_data, trade_executor
from api.services.revolut_x_client import get_status

router = APIRouter(prefix="/revolut-x", tags=["revolut-x-broker"])


# \u2500\u2500 Schemas \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class ExecuteRequest(BaseModel):
    volume: float = 0.0001  # Base-asset qty (e.g. BTC). Ignored if quote_eur is set.
    quote_eur: Optional[float] = None  # Spend this many EUR (preferred for €-budget trading)
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


@router.get("/positions/live")
async def live_positions(session: Session = Depends(get_session)):
    """Reconciled positions: broker balances ⨝ DB ExecutionTicket fills ⨝ live tickers.

    This is the single source of truth for "what am I actually holding right now".
    - Broker balance > 0 is the gate (no balance → no position, regardless of DB).
    - DB tickets supply entry_price / cost_eur / fees.
    - Tickers supply live bid/ask for P&L.
    """
    # 1. Live balances
    try:
        acc = await market_data.get_account_info()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch account: {e}")

    balances = (acc or {}).get("balances") or []
    cash_eur = next((float(b.get("balance") or 0) for b in balances if (b.get("currency") or "").upper() == "EUR"), 0.0)
    held = [
        {
            "currency": (b.get("currency") or "").upper(),
            "qty": float(b.get("balance") or 0),
            "available": float(b.get("available") or 0),
            "staked": float(b.get("staked") or 0),
            "reserved": float(b.get("reserved") or 0),
        }
        for b in balances
        if (b.get("currency") or "").upper() != "EUR" and float(b.get("balance") or 0) > 0
    ]

    # 2. Live tickers for held symbols (assume <ASSET>-EUR pairing on Revolut X)
    symbols = [f"{h['currency']}-EUR" for h in held]
    ticker_map: dict = {}
    if symbols:
        try:
            tickers = await market_data.get_tickers(symbols)
            for t in tickers or []:
                sym = (t.get("symbol") or "").replace("/", "-").upper()
                ticker_map[sym] = t
        except Exception as e:
            # Don't fail the whole call — surface empty tickers instead
            ticker_map = {}

    # 3. DB tickets — get latest BUY fill per symbol with fill_qty > 0
    from sqlalchemy import desc
    tickets = session.exec(
        select(ExecutionTicket)
        .where(ExecutionTicket.side == "buy")
        .where(ExecutionTicket.fill_qty != None)  # noqa: E711
        .order_by(desc(ExecutionTicket.filled_at), desc(ExecutionTicket.id))
    ).all()

    ticket_by_symbol: dict = {}
    for t in tickets:
        if not t.symbol:
            continue
        sym = t.symbol.upper()
        if sym not in ticket_by_symbol:
            ticket_by_symbol[sym] = t

    TAKER_FEE = 0.0009

    positions: list = []
    for h in held:
        sym = f"{h['currency']}-EUR"
        ticker = ticker_map.get(sym) or {}
        bid = float(ticker.get("bid") or 0)
        ask = float(ticker.get("ask") or 0)

        ticket = ticket_by_symbol.get(sym)
        entry_price = float(ticket.fill_price) if (ticket and ticket.fill_price) else None
        cost_eur = (
            float(ticket.fill_qty) * float(ticket.fill_price)
            if (ticket and ticket.fill_qty and ticket.fill_price)
            else None
        )
        fees_eur = float(ticket.fees_eur) if (ticket and ticket.fees_eur) else 0.0
        broker_order_id = ticket.broker_order_id if ticket else None

        current_value = h["qty"] * bid * (1 - TAKER_FEE) if bid else 0.0
        pnl = (current_value - cost_eur) if (cost_eur is not None and current_value) else None
        pnl_pct = (pnl / cost_eur * 100) if (pnl is not None and cost_eur) else None

        positions.append({
            "symbol": sym,
            "asset": h["currency"],
            "qty": h["qty"],
            "available": h["available"],
            "staked": h["staked"],
            "reserved": h["reserved"],
            "tradeable": h["available"] > 0,
            "is_staked": h["staked"] > 0 and h["available"] == 0,
            "bid": bid,
            "ask": ask,
            "entry_price": entry_price,
            "cost_eur": cost_eur,
            "fees_eur": fees_eur,
            "current_value_eur": current_value,
            "pnl_eur": pnl,
            "pnl_pct": pnl_pct,
            "has_db_record": ticket is not None,
            "broker_order_id": broker_order_id,
        })

    total_value = sum(p["current_value_eur"] for p in positions)
    total_cost = sum((p["cost_eur"] or 0) for p in positions)
    total_pnl = sum((p["pnl_eur"] or 0) for p in positions if p["pnl_eur"] is not None)

    return {
        "cash_eur": cash_eur,
        "positions_value_eur": total_value,
        "total_account_eur": cash_eur + total_value,
        "invested_eur": total_cost,
        "total_pnl_eur": total_pnl,
        "positions": positions,
        "count": len(positions),
        "unmatched_count": sum(1 for p in positions if not p["has_db_record"]),
    }


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
            quote_eur=request.quote_eur,
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
        broker_order_id=result.get("order_id"),
        symbol=trade.symbol,
        side="buy" if trade.direction.upper() == "LONG" else "sell",
    )

    # If the broker accepted the order, poll for fill data so the DB matches reality
    fill_summary: Optional[dict] = None
    if result["success"] and result.get("order_id"):
        try:
            fill_summary = await trade_executor.poll_for_fill(result["order_id"])
            ticket.fill_qty = fill_summary.get("fill_qty") or None
            ticket.fill_price = fill_summary.get("fill_price") or None
            ticket.fees_eur = fill_summary.get("fees_eur") or None
            fstate = fill_summary.get("state") or ""
            if fstate == "FILLED":
                ticket.adapter_status = "Filled"
                ticket.filled_at = datetime.now(timezone.utc)
            elif fstate == "PARTIALLY_FILLED":
                ticket.adapter_status = "PartiallyFilled"
            elif fstate in {"CANCELLED", "REJECTED", "EXPIRED"}:
                ticket.adapter_status = fstate.title()
            elif fstate in {"NEW", "OPEN", "PENDING", "ACCEPTED"}:
                ticket.adapter_status = "Open"
        except Exception as poll_exc:  # noqa: BLE001
            # Don't fail the request just because polling errored — the order is placed
            ticket.provider_response = f"{ticket.provider_response}\nfill_poll_error: {poll_exc}"

    session.add(ticket)

    # Only flip to "Sent" when we have evidence of a real fill
    if ticket.adapter_status == "Filled":
        trade.status = "Sent"
    elif ticket.adapter_status in {"PartiallyFilled", "Open"}:
        trade.status = "Sent"  # broker accepted; surface in UI as in-flight
    else:
        trade.status = "Needs Work"
    session.add(trade)
    session.commit()
    session.refresh(ticket)

    return {
        "trade_id": trade_id,
        "execution": result,
        "fill": fill_summary,
        "ticket": {
            "id": ticket.id,
            "status": ticket.adapter_status,
            "broker_order_id": ticket.broker_order_id,
            "symbol": ticket.symbol,
            "side": ticket.side,
            "fill_qty": ticket.fill_qty,
            "fill_price": ticket.fill_price,
            "fees_eur": ticket.fees_eur,
            "filled_at": ticket.filled_at.isoformat() if ticket.filled_at else None,
        },
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
