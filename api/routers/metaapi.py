"""Helm commodities venue (MetaApi MT4/MT5). Paper by default.

Reads are read-only. The only write to the broker is POST /execute/{id} in
live mode, behind Approve + leveraged_ok + Guardian + margin checks.
No route returns METAAPI_TOKEN or METAAPI_ACCOUNT_ID.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.core.db import get_session
from api.services import metaapi_client as mc
from api.services import metaapi_venue as venue

router = APIRouter(prefix="/metaapi", tags=["metaapi"])


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, venue.MetaApiVenueError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    return HTTPException(status_code=502, detail=mc.redact(exc))


def _symbol(symbol: str) -> str:
    sym = symbol.upper()
    if sym not in venue.allowed_symbols():
        raise HTTPException(status_code=400, detail=f"{sym} is not an allowed symbol")
    return sym


class QuotesBody(BaseModel):
    quotes: Optional[dict[str, dict]] = None  # {"XAUUSD": {"bid":..,"ask":..}}


class AckBody(BaseModel):
    leveraged_ok: bool


class IdeaBody(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    thesis: str
    invalidation_notes: str
    lots: Optional[float] = None


@router.get("/status")
def metaapi_status():
    return venue.status()


@router.get("/account")
async def metaapi_account():
    try:
        info = await mc.get_account_information()
    except mc.MetaApiError as exc:
        raise _err(exc) from None
    keys = ("broker", "currency", "server", "balance", "equity", "margin", "freeMargin", "marginLevel", "leverage", "platform", "type")
    return {k: info.get(k) for k in keys}


@router.get("/positions")
async def metaapi_positions():
    try:
        return await mc.get_positions()
    except mc.MetaApiError as exc:
        raise _err(exc) from None


@router.get("/price/{symbol}")
async def metaapi_price(symbol: str):
    try:
        return await mc.get_current_price(_symbol(symbol))
    except mc.MetaApiError as exc:
        raise _err(exc) from None


@router.get("/candles/{symbol}")
async def metaapi_candles(symbol: str, timeframe: str = "1h", limit: int = 100):
    try:
        return await mc.get_candles(_symbol(symbol), timeframe, min(max(limit, 1), 1000))
    except mc.MetaApiError as exc:
        raise _err(exc) from None


@router.get("/ideas")
def metaapi_ideas(db: Session = Depends(get_session)):
    return venue.list_ideas(db)


@router.post("/ideas")
def metaapi_create_idea(body: IdeaBody, db: Session = Depends(get_session)):
    try:
        trade, meta = venue.create_idea(db, source="manual", **body.model_dump())
    except venue.MetaApiVenueError as exc:
        raise _err(exc) from None
    return {"trade_idea_id": trade.id, "symbol": meta.symbol, "lots": meta.lots, "status": trade.status}


@router.post("/ideas/{trade_id}/ack")
def metaapi_ack(trade_id: int, body: AckBody, db: Session = Depends(get_session)):
    try:
        meta = venue.acknowledge_leverage(db, trade_id, body.leveraged_ok)
    except venue.MetaApiVenueError as exc:
        raise _err(exc) from None
    return {"trade_idea_id": trade_id, "leveraged_ok": meta.leveraged_ok}


@router.post("/scout")
async def metaapi_scout(db: Session = Depends(get_session)):
    return await venue.run_scout(db)


@router.post("/execute/{trade_id}")
async def metaapi_execute(trade_id: int, body: Optional[QuotesBody] = None, db: Session = Depends(get_session)):
    try:
        return await venue.execute(db, trade_id, quotes=(body.quotes if body else None))
    except (venue.MetaApiVenueError, mc.MetaApiError) as exc:
        raise _err(exc) from None


@router.get("/paper")
def metaapi_paper(db: Session = Depends(get_session)):
    return venue.ledger(db)


@router.post("/paper/mark")
async def metaapi_paper_mark(body: Optional[QuotesBody] = None, db: Session = Depends(get_session)):
    return await venue.mark_paper(db, quotes=(body.quotes if body else None))


@router.post("/paper/{position_id}/close")
async def metaapi_paper_close(position_id: int, body: Optional[QuotesBody] = None, db: Session = Depends(get_session)):
    try:
        return await venue.close_paper(db, position_id, quotes=(body.quotes if body else None))
    except (venue.MetaApiVenueError, mc.MetaApiError) as exc:
        raise _err(exc) from None
