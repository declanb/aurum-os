"""Helm profit notifications. Read and mark-read never touch the broker.

``POST /scan`` re-reads live spot PnL and persists a ping if one is due.
It does not place, cancel, or modify an order.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from api.core.db import get_session
from api.services.profit_notifications import (
    list_notifications,
    mark_all_read,
    mark_read,
    scan_profits,
    to_dict,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)


def _list(
    session: Session,
    since_id: Optional[int],
    limit: int,
    unread_only: bool,
) -> dict:
    return list_notifications(session, since_id=since_id, limit=limit, unread_only=unread_only)


@router.get("")
@router.get("/")
@router.get("/events")
def list_profit_notifications(
    since_id: Optional[int] = None,
    limit: int = 30,
    unread_only: bool = False,
    session: Session = Depends(get_session),
):
    """Profit pings for the Helm app and for a room bot.

    Omit ``since_id`` for the newest-first list the phone UI uses.
    Pass ``since_id`` (the last id you have seen, or 0) to poll newer
    events oldest-first and advance a cursor. This handler does not
    call Revolut X.
    """
    return _list(session, since_id, limit, unread_only)


@router.post("/scan")
async def scan_profit_notifications(session: Session = Depends(get_session)):
    """Check live spot PnL and exit milestones, then return the notification list.

    Safe to call on a timer. The same position is stored once per milestone.
    """
    summary = await scan_profits(session)
    payload = list_notifications(session)
    payload["created"] = summary["created"]
    payload["source"] = summary["source"]
    return payload


@router.post("/read-all")
def read_all_profit_notifications(session: Session = Depends(get_session)):
    updated = mark_all_read(session)
    payload = list_notifications(session)
    payload["updated"] = updated
    return payload


@router.post("/{notification_id}/read")
def read_profit_notification(
    notification_id: int,
    session: Session = Depends(get_session),
):
    row = mark_read(session, notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return to_dict(row)
