"""Reconciled Revolut X spot holdings: balances, fills, and live bids.

This is the same payload ``GET /api/revolut-x/positions/live`` returns.
Profit notifications reuse ``sale_pnl`` so a ping matches the My Trade screen.
"""

from __future__ import annotations

import logging

from sqlalchemy import desc
from sqlmodel import Session, select

from api.models.trade import ExecutionTicket
from api.services import market_data
from api.services.exit_bracket import open_brackets_by_symbol

logger = logging.getLogger(__name__)

# Sell-side taker fee. My Trade unrealised PnL uses this on the bid.
TAKER_FEE = 0.0009


class LivePositionsError(RuntimeError):
    """Broker account read failed. The router surfaces this as HTTP 503."""


def sale_pnl(qty: float, mark: float, cost_eur: float | None) -> tuple[float | None, float | None]:
    """Net PnL after the sell-side taker fee. None when price or cost is missing."""
    current = qty * mark * (1 - TAKER_FEE) if mark else 0.0
    if cost_eur is None or not current:
        return None, None
    pnl = current - cost_eur
    pct = (pnl / cost_eur * 100) if cost_eur else None
    return pnl, pct


async def build_live_positions(session: Session) -> dict:
    """Broker balances joined to the latest buy fill and a live bid.

    A zero balance is not a position. Missing tickers leave PnL empty rather
    than inventing a price.
    """
    try:
        acc = await market_data.get_account_info()
    except Exception as exc:
        raise LivePositionsError(f"Failed to fetch account: {exc}") from exc

    balances = (acc or {}).get("balances") or []
    cash_eur = next(
        (float(b.get("balance") or 0) for b in balances if (b.get("currency") or "").upper() == "EUR"),
        0.0,
    )
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

    symbols = [f"{h['currency']}-EUR" for h in held]
    ticker_map: dict = {}
    if symbols:
        try:
            tickers = await market_data.get_tickers(symbols)
            for ticker in tickers or []:
                sym = (ticker.get("symbol") or "").replace("/", "-").upper()
                ticker_map[sym] = ticker
        except Exception as exc:
            logger.warning("Live position tickers unavailable (%s)", type(exc).__name__)
            ticker_map = {}

    tickets = session.exec(
        select(ExecutionTicket)
        .where(ExecutionTicket.side == "buy")
        .where(ExecutionTicket.fill_qty != None)  # noqa: E711
        .order_by(desc(ExecutionTicket.filled_at), desc(ExecutionTicket.id))
    ).all()

    ticket_by_symbol: dict = {}
    for ticket in tickets:
        if not ticket.symbol:
            continue
        sym = ticket.symbol.upper()
        if sym not in ticket_by_symbol:
            ticket_by_symbol[sym] = ticket

    exit_by_symbol = open_brackets_by_symbol(session)

    positions: list = []
    for holding in held:
        sym = f"{holding['currency']}-EUR"
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

        current_value = holding["qty"] * bid * (1 - TAKER_FEE) if bid else 0.0
        pnl, pnl_pct = sale_pnl(holding["qty"], bid, cost_eur)

        positions.append({
            "symbol": sym,
            "asset": holding["currency"],
            "qty": holding["qty"],
            "available": holding["available"],
            "staked": holding["staked"],
            "reserved": holding["reserved"],
            "tradeable": holding["available"] > 0,
            "is_staked": holding["staked"] > 0 and holding["available"] == 0,
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
            "entry_ticket_id": ticket.id if ticket else None,
            "exit": exit_by_symbol.get(sym),
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
