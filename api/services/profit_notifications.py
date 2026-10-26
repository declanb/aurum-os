"""Helm profit notifications.

A held Revolut X spot long can ping three times, and not on every poll:

* ``in_profit:{position}`` — the first time unrealised PnL is above zero.
  Crossing back through zero does not ping again.
* ``take_profit:idea:{id}`` — once when that take-profit EXIT idea exists
  (created, or still Ready / Approved / Sent / Needs Work). A later idea,
  after a reject and a fresh proposal, is a new ping. The same idea is not.
* ``exit_filled:bracket:{id}`` — once when that bracket's exit fill is
  profitable. A loss-making stop-out is silent. Fills older than 36 hours
  are not backfilled.

``position`` is ``bracket:{id}`` when an exit bracket is armed, else
``ticket:{id}``, else ``order:{broker_order_id}``, else ``held:{SYMBOL}``.
A new fill (new ticket or bracket) can ping again.

PnL uses the same sell-side taker fee as My Trade. These rows never place,
cancel, or modify a broker order. A sell still needs an ApprovalEvent and
a human Execute click.

Writers:
* ``GET /api/cron/hunt`` (Hobby schedule is once a day; catch-up when the
  app is closed). A paused fleet still records pings and does not propose exits.
* ``POST /api/notifications/scan`` from the open Helm app, about once a minute.
* ``GET /api/revolut-x/positions/live`` (My Trade already polls this).

``GET /api/notifications`` and ``GET /api/notifications/events`` only read.
Pass ``since_id`` for a room bot; results are then oldest-first.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.models.trade import ExitBracket, ProfitNotification, TradeIdea
from api.services.live_positions import build_live_positions, sale_pnl

logger = logging.getLogger(__name__)

MILESTONE_LOOKBACK = timedelta(hours=36)
OPEN_EXIT_STATUSES = {"Ready for Approval", "Approved", "Sent", "Needs Work"}
CLOSED_BRACKET_STATUSES = {"closed", "paper_closed"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _as_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def position_key(
    *,
    symbol: str,
    bracket_id: Optional[int] = None,
    ticket_id: Optional[int] = None,
    broker_order_id: Optional[str] = None,
) -> str:
    if bracket_id:
        return f"bracket:{int(bracket_id)}"
    if ticket_id:
        return f"ticket:{int(ticket_id)}"
    if broker_order_id:
        return f"order:{broker_order_id}"
    return f"held:{(symbol or '').upper()}"


def format_pnl(pnl: Optional[float], pct: Optional[float]) -> str:
    """Euro amount, with 4 decimals under €1 so a small green flip is visible."""
    if pnl is None:
        return ""
    digits = 4 if abs(pnl) < 1 else 2
    text = f"€{pnl:+.{digits}f}"
    if pct is not None:
        text += f" ({pct:+.2f}%)"
    return text


def _copy(kind: str, symbol: str, pnl: Optional[float], pct: Optional[float]) -> tuple[str, str]:
    money = format_pnl(pnl, pct)
    if kind == "in_profit":
        return (
            f"{symbol} in profit",
            f"Helm: unrealised {money}. The spot long stays open until you approve a sell.",
        )
    if kind == "take_profit":
        where = f" at {money}" if money else ""
        return (
            f"{symbol} target hit",
            f"Helm: take-profit is waiting in Approvals{where}. No sell is sent until you execute.",
        )
    return (
        f"{symbol} profit booked",
        f"Helm: exit filled {money}.",
    )


def _record(
    session: Session,
    *,
    dedupe_key: str,
    kind: str,
    symbol: str,
    position_key_value: str,
    pnl_eur: Optional[float],
    pnl_pct: Optional[float],
    qty: Optional[float],
    entry_price: Optional[float],
    mark_price: Optional[float],
) -> Optional[ProfitNotification]:
    existing = session.exec(
        select(ProfitNotification).where(ProfitNotification.dedupe_key == dedupe_key)
    ).first()
    if existing:
        return None
    title, body = _copy(kind, symbol, pnl_eur, pnl_pct)
    row = ProfitNotification(
        dedupe_key=dedupe_key,
        kind=kind,
        symbol=symbol,
        position_key=position_key_value,
        pnl_eur=pnl_eur,
        pnl_pct=pnl_pct,
        qty=qty,
        entry_price=entry_price,
        mark_price=mark_price,
        title=title,
        body=body,
        created_at=utcnow(),
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        try:
            session.expunge(row)
        except Exception:
            pass
        return None
    return row


def _position_identity(position: dict) -> str:
    exit_info = position.get("exit") or {}
    bracket_id = exit_info.get("id") if isinstance(exit_info, dict) else None
    return position_key(
        symbol=position.get("symbol") or "",
        bracket_id=bracket_id,
        ticket_id=position.get("entry_ticket_id"),
        broker_order_id=position.get("broker_order_id"),
    )


def record_open_positions(session: Session, positions: list) -> list[ProfitNotification]:
    """Ping once per open position the first time unrealised PnL is above zero."""
    created: list[ProfitNotification] = []
    for position in positions or []:
        if not isinstance(position, dict):
            continue
        symbol = (position.get("symbol") or "").upper()
        qty = _as_float(position.get("qty"))
        pnl = _as_float(position.get("pnl_eur"))
        if not symbol or qty is None or qty <= 0 or pnl is None or pnl <= 0:
            continue
        row = _record(
            session,
            dedupe_key=f"in_profit:{_position_identity(position)}",
            kind="in_profit",
            symbol=symbol,
            position_key_value=_position_identity(position),
            pnl_eur=pnl,
            pnl_pct=_as_float(position.get("pnl_pct")),
            qty=qty,
            entry_price=_as_float(position.get("entry_price")),
            mark_price=_as_float(position.get("bid") if position.get("bid") is not None else position.get("mark_price")),
        )
        if row:
            created.append(row)
    return created


def record_bracket_marks(session: Session, bids: dict) -> list[ProfitNotification]:
    """Unrealised pings from armed brackets when the live account read failed."""
    from api.services.exit_bracket import ACTIVE_STATUSES

    rows = session.exec(
        select(ExitBracket).where(ExitBracket.status.in_(ACTIVE_STATUSES))  # type: ignore[attr-defined]
    ).all()
    positions = []
    for bracket in rows:
        bid = None
        if isinstance(bids, dict):
            bid = bids.get(bracket.symbol)
            if bid is None:
                bid = bids.get((bracket.symbol or "").upper())
        mark = _as_float(bid)
        if mark is None or mark <= 0 or not bracket.qty or not bracket.entry_price:
            continue
        cost = float(bracket.qty) * float(bracket.entry_price)
        pnl, pct = sale_pnl(float(bracket.qty), mark, cost)
        positions.append({
            "symbol": bracket.symbol,
            "qty": bracket.qty,
            "entry_price": bracket.entry_price,
            "bid": mark,
            "pnl_eur": pnl,
            "pnl_pct": pct,
            "exit": {"id": bracket.id},
            "entry_ticket_id": bracket.entry_ticket_id,
            "broker_order_id": None,
        })
    return record_open_positions(session, positions)


def notify_take_profit(session: Session, bracket: ExitBracket, bid: float) -> Optional[ProfitNotification]:
    """One ping per take-profit EXIT idea. Does not commit and does not sell."""
    if not bracket.id or not bracket.exit_trade_idea_id:
        return None
    mark = _as_float(bid)
    pnl, pct = (None, None)
    if mark and bracket.qty and bracket.entry_price:
        pnl, pct = sale_pnl(float(bracket.qty), mark, float(bracket.qty) * float(bracket.entry_price))
    return _record(
        session,
        dedupe_key=f"take_profit:idea:{bracket.exit_trade_idea_id}",
        kind="take_profit",
        symbol=(bracket.symbol or "").upper(),
        position_key_value=f"bracket:{bracket.id}",
        pnl_eur=pnl,
        pnl_pct=pct,
        qty=_as_float(bracket.qty),
        entry_price=_as_float(bracket.entry_price),
        mark_price=mark,
    )


def notify_exit_filled(
    session: Session,
    bracket: ExitBracket,
    fill_price: Optional[float],
) -> Optional[ProfitNotification]:
    """One ping when a closed bracket's exit fill is actually profitable."""
    if not bracket.id or bracket.status not in CLOSED_BRACKET_STATUSES:
        return None
    mark = _as_float(fill_price)
    if mark is None or mark <= 0 or not bracket.qty or not bracket.entry_price:
        return None
    pnl, pct = sale_pnl(float(bracket.qty), mark, float(bracket.qty) * float(bracket.entry_price))
    if pnl is None or pnl <= 0:
        return None
    return _record(
        session,
        dedupe_key=f"exit_filled:bracket:{bracket.id}",
        kind="exit_filled",
        symbol=(bracket.symbol or "").upper(),
        position_key_value=f"bracket:{bracket.id}",
        pnl_eur=pnl,
        pnl_pct=pct,
        qty=_as_float(bracket.qty),
        entry_price=_as_float(bracket.entry_price),
        mark_price=mark,
    )


def _recent(moment: Optional[datetime], now: datetime) -> bool:
    aware = _aware(moment)
    if aware is None:
        return False
    return now - aware <= MILESTONE_LOOKBACK


def scan_exit_milestones(session: Session, now: Optional[datetime] = None) -> list[ProfitNotification]:
    """Backstop for take-profit ideas still in the queue and recent profitable fills.

    The propose / fill hooks are the timely path. This catches a ping that
    those hooks missed, without replaying old closed trades.
    """
    now = now or utcnow()
    created: list[ProfitNotification] = []
    brackets = session.exec(select(ExitBracket)).all()
    for bracket in brackets:
        idea = None
        if bracket.exit_trade_idea_id:
            idea = session.get(TradeIdea, bracket.exit_trade_idea_id)
        if (
            bracket.exit_reason == "take_profit"
            and idea is not None
            and idea.status in OPEN_EXIT_STATUSES
        ):
            mark = _as_float(bracket.last_price) or _as_float(idea.entry_price) or 0.0
            row = notify_take_profit(session, bracket, mark)
            if row:
                created.append(row)
        if bracket.status in CLOSED_BRACKET_STATUSES and _recent(bracket.closed_at or bracket.updated_at, now):
            row = notify_exit_filled(session, bracket, bracket.last_price)
            if row:
                created.append(row)
    return created


def attach_profit_notifications(session: Session, positions: list) -> int:
    """Record open-position and exit pings. Commits only when a row is new.

    Failures are logged and swallowed so a position read still returns.
    """
    try:
        created = record_open_positions(session, positions)
        created.extend(scan_exit_milestones(session))
        if created:
            session.commit()
        return len(created)
    except Exception:
        logger.exception("Helm profit notification persist failed")
        session.rollback()
        return 0


async def scan_profits(session: Session, bids: Optional[dict] = None) -> dict:
    """Read live holdings (or bracket bids) and persist any new profit pings.

    Commits when it inserts. Does not place a broker order.
    """
    source = "live"
    try:
        payload = await build_live_positions(session)
        created = record_open_positions(session, payload.get("positions") or [])
    except Exception as exc:
        logger.warning("Live profit scan fell back to bracket marks (%s)", type(exc).__name__)
        session.rollback()
        source = "brackets"
        created = record_bracket_marks(session, bids or {})
    try:
        created.extend(scan_exit_milestones(session))
        if created:
            session.commit()
    except Exception:
        logger.exception("Helm profit milestone scan failed")
        session.rollback()
        return {"created": 0, "source": "error"}
    return {"created": len(created), "source": source}


def to_dict(row: ProfitNotification) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "symbol": row.symbol,
        "position_key": row.position_key,
        "pnl_eur": row.pnl_eur,
        "pnl_pct": row.pnl_pct,
        "qty": row.qty,
        "entry_price": row.entry_price,
        "mark_price": row.mark_price,
        "title": row.title,
        "body": row.body,
        "read": row.read_at is not None,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_notifications(
    session: Session,
    *,
    since_id: Optional[int] = None,
    limit: int = 30,
    unread_only: bool = False,
) -> dict:
    """Newest first, unless ``since_id`` is set (bot cursor, oldest first)."""
    capped = max(1, min(int(limit or 30), 100))
    query = select(ProfitNotification)
    if since_id is not None:
        query = query.where(ProfitNotification.id > since_id).order_by(ProfitNotification.id.asc())  # type: ignore[attr-defined]
    else:
        query = query.order_by(ProfitNotification.id.desc())  # type: ignore[attr-defined]
    if unread_only:
        query = query.where(ProfitNotification.read_at.is_(None))  # type: ignore[union-attr]
    rows = list(session.exec(query.limit(capped)).all())
    unread = session.exec(
        select(ProfitNotification).where(ProfitNotification.read_at.is_(None))  # type: ignore[union-attr]
    ).all()
    return {
        "count": len(rows),
        "unread_count": len(unread),
        "notifications": [to_dict(row) for row in rows],
    }


def mark_read(session: Session, notification_id: int) -> Optional[ProfitNotification]:
    row = session.get(ProfitNotification, notification_id)
    if row is None:
        return None
    if row.read_at is None:
        row.read_at = utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def mark_all_read(session: Session) -> int:
    rows = session.exec(
        select(ProfitNotification).where(ProfitNotification.read_at.is_(None))  # type: ignore[union-attr]
    ).all()
    now = utcnow()
    for row in rows:
        row.read_at = now
        session.add(row)
    if rows:
        session.commit()
    return len(rows)
