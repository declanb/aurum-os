"""Paper copy-book HTTP surface.

Overnight watchers poll these routes. They read scout TradeIdeas and public
tickers, then update a virtual book. They do not approve an idea and they do
not submit a broker order. Deployment protection on the app is unchanged.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.core.db import get_session
from api.services.copy_book import (
    CopyBookConflict,
    CopyBookError,
    CopyBookRefused,
    close_position,
    resolve_session,
    snapshot,
    start_session,
    stop_session,
    tick_session,
)

router = APIRouter(prefix="/copy", tags=["copy-book"])


class StartBody(BaseModel):
    bankroll_eur: Optional[float] = None
    position_pct: Optional[float] = None
    max_notional_eur: Optional[float] = None
    max_positions: Optional[int] = None
    any_green: Optional[bool] = None
    strategy: Optional[str] = None  # symmetric unless any_green=true
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None
    max_new_per_day: Optional[int] = None
    position_eur: Optional[float] = None
    sources: Optional[list[str] | str] = None
    gainer_limit: Optional[int] = None
    lookback_hours: float = 24.0
    dry_run: bool = True


class TickBody(BaseModel):
    session_id: Optional[int] = None
    quotes: Optional[list[dict[str, Any]]] = None


class StopBody(BaseModel):
    session_id: Optional[int] = None
    flatten: bool = True
    quotes: Optional[list[dict[str, Any]]] = None


class CloseBody(BaseModel):
    quotes: Optional[list[dict[str, Any]]] = None


def _http_error(exc: CopyBookError) -> HTTPException:
    if isinstance(exc, CopyBookConflict):
        return HTTPException(status_code=409, detail={"message": str(exc), "session_id": exc.session_id})
    status = 400 if isinstance(exc, CopyBookRefused) or isinstance(exc, CopyBookError) else 400
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/status")
def copy_status(session_id: Optional[int] = None, db: Session = Depends(get_session)):
    """Running session, else the latest one. Always says live orders are off.

    ``summary`` carries realised, open, win rate, avg win/loss, and fees.
    """
    return snapshot(db, resolve_session(db, session_id))


@router.get("/session")
def copy_session(session_id: Optional[int] = None, db: Session = Depends(get_session)):
    return snapshot(db, resolve_session(db, session_id))


@router.post("/session")
def open_copy_session(body: Optional[StartBody] = None, db: Session = Depends(get_session)):
    """Start a dry-run. An empty body starts Helm's symmetric strategy:
    EUR 200 bank (HELM_COPY_BANKROLL_EUR), EUR 50 per position, scout's top
    ideas, +3% / -3% net brackets, at most 2 new positions a day."""
    payload = body or StartBody()
    try:
        book = start_session(
            db,
            bankroll_eur=payload.bankroll_eur,
            position_pct=payload.position_pct,
            max_notional_eur=payload.max_notional_eur,
            max_positions=payload.max_positions,
            any_green=payload.any_green,
            sources=payload.sources,
            gainer_limit=payload.gainer_limit,
            lookback_hours=payload.lookback_hours,
            strategy=payload.strategy,
            tp_pct=payload.tp_pct,
            sl_pct=payload.sl_pct,
            max_new_per_day=payload.max_new_per_day,
            position_eur=payload.position_eur,
            dry_run=payload.dry_run,
        )
    except CopyBookError as exc:
        raise _http_error(exc) from exc
    return snapshot(db, book)


@router.post("/tick")
async def copy_tick(body: Optional[TickBody] = None, db: Session = Depends(get_session)):
    """One paper poll: mark, exit, then paper-buy. Quotes are optional marks."""
    payload = body or TickBody()
    try:
        return await tick_session(db, payload.session_id, quotes=payload.quotes)
    except CopyBookError as exc:
        raise _http_error(exc) from exc


@router.post("/stop")
async def copy_stop(body: Optional[StopBody] = None, db: Session = Depends(get_session)):
    payload = body or StopBody()
    try:
        return await stop_session(
            db,
            payload.session_id,
            quotes=payload.quotes,
            flatten=payload.flatten,
        )
    except CopyBookError as exc:
        raise _http_error(exc) from exc


@router.get("/positions")
def copy_positions(
    session_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_session),
):
    if status not in (None, "", "open", "closed"):
        raise HTTPException(status_code=400, detail="status must be open or closed")
    book = resolve_session(db, session_id)
    picture = snapshot(db, book)
    rows = []
    if status in (None, "", "open"):
        rows.extend(picture["open_positions"])
    if status in (None, "", "closed"):
        rows.extend(picture["closed_trades"])
    return {
        "dry_run": True,
        "live_orders": False,
        "session_id": None if picture["session"] is None else picture["session"]["id"],
        "positions": rows,
    }


@router.post("/positions/{position_id}/close")
async def copy_close(position_id: int, body: Optional[CloseBody] = None, db: Session = Depends(get_session)):
    payload = body or CloseBody()
    try:
        return await close_position(db, position_id, quotes=payload.quotes)
    except CopyBookError as exc:
        raise _http_error(exc) from exc
