"""Helm paper copy book.

Revolut X has no native copy-trading API. This module paper-mirrors signals
a copy trader would chase:

* LONG EUR ``TradeIdea`` rows already staged by scout (Ready for Approval or
  Approved). The idea is read. Its status, Guardian result, and approval row
  are left alone.
* Top 24h EUR gainers on the ticker read, when the payload actually carries
  a percent change or an open and a last.

Fills are virtual. Marks use the bid when a ticker has one, matching the
exit-bracket mark. Optional stop and target fields use the same bid checks
as ``evaluate_long_bracket`` and, when both levels are valid, the same
trailing ratchet. Any-green closes a paper long once sell-side P&L is
positive. Nothing in this module submits, cancels, or amends a broker order.

Symbol storage matches the rest of Helm: ``UNI/EUR`` from a ticker becomes
``UNI-EUR`` on the row. Spot EUR pairs only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from api.core.config import settings
from api.models.copy_book import CopyPosition, CopySession
from api.models.trade import ExecutionTicket, TradeIdea
from api.services import market_data
from api.services.exit_bracket import evaluate_long_bracket
from api.services.live_positions import TAKER_FEE, sale_pnl

logger = logging.getLogger(__name__)

COPY_NOTE = (
    "Paper copy book. Revolut X has no native copy-trading API. "
    "Signals are scout TradeIdeas and EUR ticker gainers, mirrored on a virtual book. "
    "This path never places, cancels, or modifies a live order."
)

NAME_CAP_FRACTION = 0.25
MIN_NOTIONAL_EUR = 1.0
FEE_MODEL = "sell_taker_0.09pct"
SIGNAL_STATUSES = ("Ready for Approval", "Approved")


class CopyBookError(ValueError):
    """The paper book refused the request. No broker call was involved."""


class CopyBookConflict(CopyBookError):
    def __init__(self, message: str, session_id: int):
        super().__init__(message)
        self.session_id = session_id


class CopyBookRefused(CopyBookError):
    """Caller tried to leave the paper path."""


@dataclass(frozen=True)
class CopySignal:
    symbol: str
    source: str
    reason: str
    trade_idea_id: Optional[int]
    buy_price: float
    stop_price: Optional[float]
    target_price: Optional[float]


@dataclass(frozen=True)
class ExitDecision:
    action: str
    stop_price: Optional[float]
    high_water_price: float


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt: Optional[datetime]) -> Optional[str]:
    aware = _aware(dt)
    return aware.isoformat() if aware else None


def _money(value: float) -> float:
    return round(float(value), 8)


def to_db_symbol(symbol: str) -> str:
    """``UNI/EUR`` and ``UNI-EUR`` both become ``UNI-EUR``."""
    return (symbol or "").strip().upper().replace("/", "-").replace("_", "-").replace(" ", "")


def is_eur_spot(symbol: str) -> bool:
    text = to_db_symbol(symbol)
    if text.count("-") != 1:
        return False
    base, quote = text.split("-")
    return bool(base) and base.isalnum() and quote == "EUR" and base != "EUR"


def _pos_float(value) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num <= 0:
        return None
    return num


def paper_buy_price(row: dict) -> Optional[float]:
    """Paper buy at mid, else the average of bid and ask, else last."""
    if not isinstance(row, dict):
        return None
    mid = _pos_float(row.get("mid"))
    if mid:
        return mid
    bid = _pos_float(row.get("bid"))
    ask = _pos_float(row.get("ask"))
    if bid and ask:
        return (bid + ask) / 2.0
    for key in ("last", "last_price", "price"):
        last = _pos_float(row.get(key))
        if last:
            return last
    return None


def paper_sell_mark(row: dict) -> Optional[float]:
    """Mark a paper long at the bid, the price a market sell can receive."""
    if not isinstance(row, dict):
        return None
    bid = _pos_float(row.get("bid"))
    if bid:
        return bid
    return paper_buy_price(row)


def protective_levels(
    fill: float,
    stop: Optional[float],
    target: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Keep a stop only when it sits under the fill, and a target only above it."""
    stop_ok = None
    target_ok = None
    stop_num = _pos_float(stop)
    target_num = _pos_float(target)
    if stop_num is not None and stop_num < fill:
        stop_ok = stop_num
    if target_num is not None and target_num > fill:
        target_ok = target_num
    return stop_ok, target_ok


def index_quotes(rows: Optional[list[dict]]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        symbol = to_db_symbol(str(row.get("symbol") or ""))
        if not symbol:
            continue
        indexed[symbol] = {**row, "symbol": symbol}
    return indexed


def rank_eur_gainers(rows: Optional[list[dict]], limit: int) -> list[dict]:
    """EUR spot pairs with a known positive 24h change, strongest first.

    Rows without a change are skipped. A missing change is not treated as zero.
    """
    if limit <= 0:
        return []
    ranked = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        symbol = to_db_symbol(str(row.get("symbol") or ""))
        if not is_eur_spot(symbol):
            continue
        change = market_data.change_24h_pct(row)
        price = paper_buy_price(row)
        if change is None or price is None or change <= 0:
            continue
        ranked.append({**row, "symbol": symbol, "change_24h_pct": change, "buy_price": price})
    ranked.sort(key=lambda item: (-item["change_24h_pct"], item["symbol"]))
    return ranked[:limit]


def decide_exit(pos: CopyPosition, mark: float, any_green: bool) -> ExitDecision:
    """Paper exit. Stop and target follow the exit-bracket bid checks.

    When both a protective stop and a target are stored, the trailing ratchet
    from ``evaluate_long_bracket`` updates the paper stop. Any-green runs only
    while that check says hold, so a stop still beats a small green print.
    """
    high = pos.high_water_price if pos.high_water_price and pos.high_water_price > 0 else pos.entry_price
    if mark > high:
        high = mark
    stop = pos.stop_price
    initial = pos.initial_stop_price
    target = pos.target_price
    bracket_ready = (
        initial is not None
        and stop is not None
        and target is not None
        and initial < pos.entry_price
        and target > pos.entry_price
    )
    if bracket_ready:
        view = evaluate_long_bracket(
            entry_price=pos.entry_price,
            initial_stop=float(initial),
            stop_price=float(stop),
            target_price=float(target),
            high_water=float(high),
            bid=float(mark),
        )
        if view.action != "hold":
            return ExitDecision(view.action, view.stop_price, view.high_water_price)
        stop = view.stop_price
        high = view.high_water_price
    else:
        if stop is not None and stop > 0 and mark <= stop:
            return ExitDecision("hard_stop", stop, high)
        if target is not None and target > 0 and mark >= target:
            return ExitDecision("take_profit", stop, high)

    if any_green:
        pnl, _pct = sale_pnl(pos.qty, mark, pos.entry_notional_eur)
        if pnl is not None and pnl > 0:
            return ExitDecision("any_green", stop, high)
    return ExitDecision("hold", stop, high)


def _assert_paper(book: CopySession) -> None:
    if not book.dry_run:
        raise CopyBookRefused(
            "Copy session is paper-only. Refusing to mark a row whose dry_run flag is not set."
        )


def _parse_sources(sources: Optional[list[str] | str]) -> str:
    if sources is None:
        parts = ["trade_ideas", "gainers"]
    elif isinstance(sources, str):
        parts = [part.strip() for part in sources.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in sources if str(part).strip()]
    if not parts:
        raise CopyBookError("sources must include trade_ideas, gainers, or both.")
    unknown = [part for part in parts if part not in {"trade_ideas", "gainers"}]
    if unknown:
        raise CopyBookError("sources must be trade_ideas and/or gainers.")
    return ",".join(dict.fromkeys(parts))


def _running(db: Session) -> Optional[CopySession]:
    return db.exec(
        select(CopySession).where(CopySession.status == "running").order_by(CopySession.id.desc())  # type: ignore[attr-defined]
    ).first()


def resolve_session(db: Session, session_id: Optional[int]) -> Optional[CopySession]:
    if session_id is not None:
        return db.get(CopySession, session_id)
    running = _running(db)
    if running:
        return running
    return db.exec(select(CopySession).order_by(CopySession.id.desc())).first()  # type: ignore[attr-defined]


def _positions(db: Session, session_id: int) -> list[CopyPosition]:
    return list(
        db.exec(
            select(CopyPosition)
            .where(CopyPosition.session_id == session_id)
            .order_by(CopyPosition.id.asc())  # type: ignore[attr-defined]
        ).all()
    )


def _position_dict(pos: CopyPosition, mark: Optional[float]) -> dict:
    unrealized = None
    unrealized_pct = None
    if pos.status == "open" and mark:
        unrealized, unrealized_pct = sale_pnl(pos.qty, mark, pos.entry_notional_eur)
    return {
        "id": pos.id,
        "session_id": pos.session_id,
        "symbol": pos.symbol,
        "status": pos.status,
        "direction": pos.direction,
        "qty": pos.qty,
        "entry_price": pos.entry_price,
        "entry_notional_eur": pos.entry_notional_eur,
        "opened_at": _iso(pos.opened_at),
        "signal_source": pos.signal_source,
        "signal_reason": pos.signal_reason,
        "trade_idea_id": pos.trade_idea_id,
        "initial_stop_price": pos.initial_stop_price,
        "stop_price": pos.stop_price,
        "target_price": pos.target_price,
        "high_water_price": pos.high_water_price,
        "last_mark": pos.last_mark,
        "mark": mark,
        "unrealized_pnl_eur": unrealized,
        "unrealized_pnl_pct": unrealized_pct,
        "exit_price": pos.exit_price,
        "exit_fee_eur": pos.exit_fee_eur,
        "exit_proceeds_eur": pos.exit_proceeds_eur,
        "realized_pnl_eur": pos.realized_pnl_eur,
        "exit_reason": pos.exit_reason,
        "closed_at": _iso(pos.closed_at),
    }


def _mtm_value(positions: list[CopyPosition], quotes: dict[str, dict]) -> float:
    total = 0.0
    for pos in positions:
        if pos.status != "open":
            continue
        row = quotes.get(pos.symbol)
        mark = paper_sell_mark(row) if row else None
        if mark is None:
            mark = pos.last_mark
        if mark:
            total += pos.qty * mark * (1.0 - TAKER_FEE)
        else:
            total += pos.entry_notional_eur
    return total


def snapshot(db: Session, book: Optional[CopySession], quotes: Optional[dict[str, dict]] = None) -> dict:
    """CLI-friendly session picture. ``live_orders`` is always false."""
    base = {
        "dry_run": True,
        "live_orders": False,
        "broker_writes": False,
        "active": False,
        "note": COPY_NOTE,
        "fee_model": FEE_MODEL,
        "session": None,
        "open_positions": [],
        "closed_trades": [],
    }
    if book is None:
        return base
    quotes = quotes or {}
    positions = _positions(db, book.id)  # type: ignore[arg-type]
    open_rows = []
    closed_rows = []
    unrealized = 0.0
    mtm_value = 0.0
    for pos in positions:
        if pos.status == "open":
            row = quotes.get(pos.symbol)
            fresh = paper_sell_mark(row) if row else None
            mark = fresh if fresh is not None else pos.last_mark
            open_rows.append(_position_dict(pos, mark))
            if mark:
                pnl, _pct = sale_pnl(pos.qty, mark, pos.entry_notional_eur)
                unrealized += pnl or 0.0
                mtm_value += pos.qty * mark * (1.0 - TAKER_FEE)
            else:
                mtm_value += pos.entry_notional_eur
        else:
            closed_rows.append(_position_dict(pos, pos.exit_price))
    equity = book.cash_eur + mtm_value
    base.update(
        {
            "dry_run": bool(book.dry_run),
            "active": book.status == "running" and bool(book.dry_run),
            "session": {
                "id": book.id,
                "status": book.status,
                "dry_run": bool(book.dry_run),
                "starting_bankroll_eur": book.starting_bankroll_eur,
                "cash_eur": book.cash_eur,
                "equity_eur": _money(equity),
                "realized_pnl_eur": book.realized_pnl_eur,
                "unrealized_pnl_eur": _money(unrealized),
                "session_pnl_eur": _money(equity - book.starting_bankroll_eur),
                "open_count": len(open_rows),
                "closed_count": len(closed_rows),
                "position_pct": book.position_pct,
                "max_notional_eur": book.max_notional_eur,
                "max_positions": book.max_positions,
                "any_green": book.any_green,
                "sources": [part for part in book.sources.split(",") if part],
                "gainer_limit": book.gainer_limit,
                "lookback_hours": book.lookback_hours,
                "started_at": _iso(book.started_at),
                "stopped_at": _iso(book.stopped_at),
                "last_tick_at": _iso(book.last_tick_at),
                "fee_model": FEE_MODEL,
            },
            "open_positions": open_rows,
            "closed_trades": closed_rows,
        }
    )
    return base


def start_session(
    db: Session,
    *,
    bankroll_eur: Optional[float] = None,
    position_pct: Optional[float] = None,
    max_notional_eur: Optional[float] = None,
    max_positions: Optional[int] = None,
    any_green: bool = True,
    sources: Optional[list[str] | str] = None,
    gainer_limit: Optional[int] = None,
    lookback_hours: float = 24.0,
    dry_run: bool = True,
    now: Optional[datetime] = None,
) -> CopySession:
    """Open a paper session. Refuses when another session is already running."""
    if dry_run is not True:
        raise CopyBookRefused(
            "Copy book stays on a paper path. dry_run cannot be turned off, and this module never submits a broker order."
        )
    running = _running(db)
    if running is not None:
        raise CopyBookConflict(
            f"Paper session #{running.id} is already running.",
            int(running.id),
        )

    bankroll = float(settings.HELM_COPY_BANKROLL_EUR if bankroll_eur is None else bankroll_eur)
    if not math.isfinite(bankroll) or bankroll <= 0 or bankroll > 1_000_000:
        raise CopyBookError("bankroll_eur must be a positive number up to 1000000.")
    pct = float(settings.HELM_COPY_POSITION_PCT if position_pct is None else position_pct)
    if not math.isfinite(pct) or pct <= 0 or pct > NAME_CAP_FRACTION:
        raise CopyBookError("position_pct must be greater than 0 and at most 0.25.")
    requested_cap = float(settings.HELM_COPY_MAX_NOTIONAL_EUR if max_notional_eur is None else max_notional_eur)
    if not math.isfinite(requested_cap) or requested_cap <= 0:
        raise CopyBookError("max_notional_eur must be positive.")
    cap = min(requested_cap, bankroll * NAME_CAP_FRACTION)
    count = int(settings.HELM_COPY_MAX_POSITIONS if max_positions is None else max_positions)
    if count < 1 or count > 20:
        raise CopyBookError("max_positions must be from 1 to 20.")
    gainers = int(settings.HELM_COPY_GAINER_LIMIT if gainer_limit is None else gainer_limit)
    if gainers < 0 or gainers > 20:
        raise CopyBookError("gainer_limit must be from 0 to 20.")
    if not math.isfinite(lookback_hours) or lookback_hours < 0 or lookback_hours > 24 * 14:
        raise CopyBookError("lookback_hours must be from 0 to 336.")

    moment = now or utcnow()
    book = CopySession(
        status="running",
        dry_run=True,
        starting_bankroll_eur=bankroll,
        cash_eur=bankroll,
        realized_pnl_eur=0.0,
        position_pct=pct,
        max_notional_eur=cap,
        max_positions=count,
        any_green=bool(any_green),
        sources=_parse_sources(sources),
        gainer_limit=gainers,
        lookback_hours=float(lookback_hours),
        note=COPY_NOTE,
        started_at=moment,
        created_at=moment,
        updated_at=moment,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    logger.info(
        "Paper copy session #%s started. bankroll=%s sources=%s dry_run=true",
        book.id,
        bankroll,
        book.sources,
    )
    return book


def _idea_is_fresh(idea: TradeIdea, book: CopySession, now: datetime) -> bool:
    created = _aware(idea.created_at)
    if created is None:
        return False
    if book.lookback_hours and book.lookback_hours > 0:
        since = now - timedelta(hours=float(book.lookback_hours))
    else:
        since = _aware(book.started_at) or now
    return created >= since


def _collect_signals(
    db: Session,
    book: CopySession,
    quote_rows: list[dict],
    quotes: dict[str, dict],
    taken_ids: set[int],
    now: datetime,
) -> tuple[list[CopySignal], list[dict]]:
    signals: list[CopySignal] = []
    skipped: list[dict] = []
    sources = set(book.sources.split(","))
    seen_symbols = {signal.symbol for signal in signals}

    if "trade_ideas" in sources:
        ideas = list(
            db.exec(
                select(TradeIdea).where(TradeIdea.direction == "LONG")  # type: ignore[attr-defined]
            ).all()
        )
        ideas.sort(key=lambda idea: _aware(idea.created_at) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        for idea in ideas:
            symbol = to_db_symbol(idea.symbol or "")
            if idea.id in taken_ids:
                continue
            if (idea.status or "") not in SIGNAL_STATUSES:
                continue
            if (idea.direction or "").upper() != "LONG":
                skipped.append({"symbol": symbol, "trade_idea_id": idea.id, "reason": "not_long"})
                continue
            if not is_eur_spot(symbol):
                skipped.append({"symbol": symbol or idea.symbol, "trade_idea_id": idea.id, "reason": "not_eur_spot"})
                continue
            if not _idea_is_fresh(idea, book, now):
                continue
            if symbol in seen_symbols:
                skipped.append({"symbol": symbol, "trade_idea_id": idea.id, "reason": "symbol_already_signaled"})
                continue
            row = quotes.get(symbol)
            price = paper_buy_price(row) if row else None
            if price is None:
                skipped.append({"symbol": symbol, "trade_idea_id": idea.id, "reason": "no_quote"})
                continue
            stop, target = protective_levels(price, idea.stop_price, idea.target_price)
            reason = f"TradeIdea #{idea.id} {idea.status}. {(idea.thesis or '').strip()}"
            signals.append(
                CopySignal(
                    symbol=symbol,
                    source="trade_idea",
                    reason=reason[:500],
                    trade_idea_id=idea.id,
                    buy_price=price,
                    stop_price=stop,
                    target_price=target,
                )
            )
            seen_symbols.add(symbol)

    if "gainers" in sources:
        for row in rank_eur_gainers(quote_rows, book.gainer_limit):
            symbol = row["symbol"]
            if symbol in seen_symbols:
                skipped.append({"symbol": symbol, "reason": "symbol_already_signaled"})
                continue
            change = row["change_24h_pct"]
            signals.append(
                CopySignal(
                    symbol=symbol,
                    source="gainer",
                    reason=(
                        f"EUR gainer {change:.2f}% over 24h on the Revolut X ticker. "
                        "Paper mirror only. REVX has no copy API."
                    ),
                    trade_idea_id=None,
                    buy_price=float(row["buy_price"]),
                    stop_price=None,
                    target_price=None,
                )
            )
            seen_symbols.add(symbol)
    return signals, skipped


def _size_notional(book: CopySession, equity: float) -> float:
    raw = min(equity * book.position_pct, book.max_notional_eur, book.cash_eur)
    notional = _money(raw)
    if notional > book.cash_eur:
        notional = _money(book.cash_eur)
    return notional


def _open_position(book: CopySession, signal: CopySignal, equity: float, now: datetime) -> Optional[CopyPosition]:
    if signal.source not in {"trade_idea", "gainer"}:
        raise CopyBookError("Unknown paper signal source.")
    if not is_eur_spot(signal.symbol):
        raise CopyBookRefused("Paper copy book accepts EUR spot pairs only.")
    notional = _size_notional(book, equity)
    if notional < MIN_NOTIONAL_EUR:
        return None
    qty = notional / signal.buy_price
    if not math.isfinite(qty) or qty <= 0:
        return None
    book.cash_eur = _money(book.cash_eur - notional)
    book.updated_at = now
    return CopyPosition(
        session_id=int(book.id),
        symbol=signal.symbol,
        status="open",
        direction="LONG",
        qty=qty,
        entry_price=signal.buy_price,
        entry_notional_eur=notional,
        entry_fee_eur=0.0,
        opened_at=now,
        signal_source=signal.source,
        signal_reason=signal.reason[:500],
        trade_idea_id=signal.trade_idea_id,
        initial_stop_price=signal.stop_price,
        stop_price=signal.stop_price,
        target_price=signal.target_price,
        high_water_price=signal.buy_price,
        last_mark=signal.buy_price,
        last_marked_at=now,
        updated_at=now,
    )


def _settle_close(book: CopySession, pos: CopyPosition, mark: float, reason: str, now: datetime) -> None:
    proceeds = pos.qty * mark * (1.0 - TAKER_FEE)
    pnl, _pct = sale_pnl(pos.qty, mark, pos.entry_notional_eur)
    pnl_value = float(pnl or 0.0)
    pos.status = "closed"
    pos.exit_price = mark
    pos.exit_fee_eur = pos.qty * mark * TAKER_FEE
    pos.exit_proceeds_eur = proceeds
    pos.realized_pnl_eur = pnl_value
    pos.exit_reason = reason
    pos.closed_at = now
    pos.last_mark = mark
    pos.last_marked_at = now
    pos.updated_at = now
    book.cash_eur = _money(book.cash_eur + proceeds)
    book.realized_pnl_eur = _money(book.realized_pnl_eur + pnl_value)
    book.updated_at = now


def _apply_mark(pos: CopyPosition, mark: float, book: CopySession, now: datetime) -> str:
    decision = decide_exit(pos, mark, book.any_green)
    pos.high_water_price = decision.high_water_price
    if decision.stop_price is not None:
        pos.stop_price = decision.stop_price
    pos.last_mark = mark
    pos.last_marked_at = now
    pos.updated_at = now
    if decision.action == "hold":
        return "hold"
    _settle_close(book, pos, mark, decision.action, now)
    return decision.action


async def _load_quotes(quotes: Optional[list[dict]]) -> tuple[list[dict], Optional[str]]:
    if quotes is not None:
        return list(quotes), None
    try:
        rows = await market_data.get_tickers(None)
    except Exception:
        logger.warning("Paper copy book ticker read failed (%s)", "ticker_read_failed")
        return [], "ticker read failed"
    return list(rows or []), None


async def tick_session(
    db: Session,
    session_id: Optional[int] = None,
    quotes: Optional[list[dict]] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Mark open paper positions, exit them, then paper-buy fresh signals.

    A new fill is not eligible to exit on the same tick. The next poll marks it.
    """
    book = resolve_session(db, session_id)
    if book is None:
        raise CopyBookError("No paper copy session.")
    if session_id is None and book.status != "running":
        raise CopyBookError("No running paper copy session.")
    if book.status != "running":
        raise CopyBookError(f"Session #{book.id} is {book.status}.")
    _assert_paper(book)

    moment = now or utcnow()
    quote_rows, quote_error = await _load_quotes(quotes)
    indexed = index_quotes(quote_rows)
    positions = _positions(db, int(book.id))
    opened: list[dict] = []
    closed: list[dict] = []
    held: list[dict] = []
    skipped: list[dict] = []

    for pos in positions:
        if pos.status != "open":
            continue
        mark = paper_sell_mark(indexed.get(pos.symbol) or {})
        if mark is None:
            held.append({"id": pos.id, "symbol": pos.symbol, "action": "unmarked"})
            continue
        action = _apply_mark(pos, mark, book, moment)
        if action == "hold":
            pnl, _pct = sale_pnl(pos.qty, mark, pos.entry_notional_eur)
            held.append({"id": pos.id, "symbol": pos.symbol, "action": "hold", "mark": mark, "unrealized_pnl_eur": pnl})
        else:
            closed.append(
                {
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "action": action,
                    "exit_price": pos.exit_price,
                    "realized_pnl_eur": pos.realized_pnl_eur,
                }
            )

    taken_ids = {pos.trade_idea_id for pos in positions if pos.trade_idea_id is not None}
    used_symbols = {pos.symbol for pos in positions}
    signals, signal_skips = _collect_signals(db, book, quote_rows, indexed, taken_ids, moment)
    skipped.extend(signal_skips)
    open_positions = [pos for pos in positions if pos.status == "open"]

    for signal in signals:
        if len(open_positions) >= book.max_positions:
            skipped.append({"symbol": signal.symbol, "trade_idea_id": signal.trade_idea_id, "reason": "max_positions"})
            continue
        if signal.symbol in used_symbols:
            skipped.append({"symbol": signal.symbol, "trade_idea_id": signal.trade_idea_id, "reason": "symbol_already_copied"})
            continue
        equity = book.cash_eur + _mtm_value(open_positions, indexed)
        pos = _open_position(book, signal, equity, moment)
        if pos is None:
            skipped.append({"symbol": signal.symbol, "trade_idea_id": signal.trade_idea_id, "reason": "notional_below_min"})
            continue
        db.add(pos)
        db.flush()
        open_positions.append(pos)
        positions.append(pos)
        used_symbols.add(pos.symbol)
        opened.append(
            {
                "id": pos.id,
                "symbol": pos.symbol,
                "qty": pos.qty,
                "entry_price": pos.entry_price,
                "entry_notional_eur": pos.entry_notional_eur,
                "signal_source": pos.signal_source,
                "trade_idea_id": pos.trade_idea_id,
            }
        )

    book.last_tick_at = moment
    book.updated_at = moment
    db.add(book)
    db.commit()
    db.refresh(book)
    payload = snapshot(db, book, indexed)
    payload["tick"] = {
        "opened": opened,
        "closed": closed,
        "held": held,
        "skipped": skipped,
        "quote_error": quote_error,
        "quote_count": len(indexed),
    }
    logger.info(
        "Paper copy session #%s tick opened=%s closed=%s held=%s",
        book.id,
        len(opened),
        len(closed),
        len(held),
    )
    return payload


async def stop_session(
    db: Session,
    session_id: Optional[int] = None,
    quotes: Optional[list[dict]] = None,
    flatten: bool = True,
    now: Optional[datetime] = None,
) -> dict:
    """Stop a paper session. Flattening sells the virtual coins at the mark."""
    book = resolve_session(db, session_id)
    if book is None:
        raise CopyBookError("No paper copy session.")
    _assert_paper(book)
    moment = now or utcnow()
    if book.status != "running":
        return snapshot(db, book)

    quote_error = None
    indexed: dict[str, dict] = {}
    if flatten:
        quote_rows, quote_error = await _load_quotes(quotes)
        indexed = index_quotes(quote_rows)
        for pos in _positions(db, int(book.id)):
            if pos.status != "open":
                continue
            fresh = paper_sell_mark(indexed.get(pos.symbol) or {})
            mark = fresh or (pos.last_mark if pos.last_mark and pos.last_mark > 0 else None) or pos.entry_price
            _apply_mark(pos, mark, book, moment)
            if pos.status == "open":
                # any-green / bracket said hold. Session stop still flattens.
                _settle_close(book, pos, mark, "session_stop", moment)
            elif pos.exit_reason not in {"hard_stop", "take_profit", "trailing_stop", "any_green"}:
                pos.exit_reason = "session_stop"

    book.status = "stopped"
    book.stopped_at = moment
    book.updated_at = moment
    db.add(book)
    db.commit()
    db.refresh(book)
    payload = snapshot(db, book, indexed)
    payload["tick"] = {"quote_error": quote_error, "flattened": flatten}
    logger.info("Paper copy session #%s stopped. flatten=%s", book.id, flatten)
    return payload


async def close_position(
    db: Session,
    position_id: int,
    quotes: Optional[list[dict]] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Paper-close one open copy position at the latest mark."""
    pos = db.get(CopyPosition, position_id)
    if pos is None:
        raise CopyBookError(f"Paper position #{position_id} was not found.")
    book = db.get(CopySession, pos.session_id)
    if book is None:
        raise CopyBookError("Paper session for that position was not found.")
    _assert_paper(book)
    if pos.status != "open":
        return snapshot(db, book)
    moment = now or utcnow()
    quote_rows, quote_error = await _load_quotes(quotes)
    indexed = index_quotes(quote_rows)
    mark = paper_sell_mark(indexed.get(pos.symbol) or {})
    if mark is None:
        raise CopyBookError(f"No mark for {pos.symbol}. Pass a quote or retry when tickers are available.")
    _settle_close(book, pos, mark, "manual", moment)
    book.updated_at = moment
    db.add(book)
    db.add(pos)
    db.commit()
    db.refresh(book)
    payload = snapshot(db, book, indexed)
    payload["tick"] = {"quote_error": quote_error, "closed_position_id": pos.id}
    return payload


def smoke() -> dict:
    """Open a paper long, mark it, and close it any-green. No network."""
    import api.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        book = start_session(
            db,
            bankroll_eur=200,
            position_pct=0.10,
            max_notional_eur=40,
            sources=["trade_ideas"],
            any_green=True,
            dry_run=True,
        )
        idea = TradeIdea(
            user_id="seed_user",
            symbol="UNI-EUR",
            direction="LONG",
            entry_price=2.0,
            stop_price=1.8,
            target_price=2.6,
            thesis="Paper smoke idea. Buyers held the range and the copy book only simulates the fill.",
            invalidation_notes="Invalidate under 1.80.",
            status="Ready for Approval",
        )
        db.add(idea)
        db.commit()
        first = asyncio.run(
            tick_session(
                db,
                book.id,
                quotes=[{"symbol": "UNI/EUR", "bid": 2.0, "ask": 2.0, "mid": 2.0, "last": 2.0}],
            )
        )
        if first["session"]["open_count"] != 1:
            raise RuntimeError("smoke did not open a paper position")
        if first["open_positions"][0]["symbol"] != "UNI-EUR":
            raise RuntimeError("smoke stored a symbol outside the DB convention")
        second = asyncio.run(
            tick_session(
                db,
                book.id,
                quotes=[{"symbol": "UNI-EUR", "bid": 2.1, "ask": 2.12, "mid": 2.11, "last": 2.11}],
            )
        )
        session_row = second["session"]
        if session_row["open_count"] != 0 or session_row["closed_count"] != 1:
            raise RuntimeError("smoke did not close the paper position on the higher mark")
        if session_row["realized_pnl_eur"] <= 0:
            raise RuntimeError("smoke expected a positive paper P&L")
        if second["live_orders"] is not False or second["dry_run"] is not True:
            raise RuntimeError("smoke left the paper path")
        if second["closed_trades"][0]["exit_reason"] != "any_green":
            raise RuntimeError("smoke expected an any-green paper exit")
        tickets = list(db.exec(select(ExecutionTicket)).all())
        if tickets:
            raise RuntimeError("smoke created a broker ticket")
        return second


def _print(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _cli_session() -> Session:
    from api.core.db import engine

    return Session(engine)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Helm paper copy book. Never submits a broker order.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start a dry-run session")
    start.add_argument("--bankroll", type=float, default=None)
    start.add_argument("--sources", default="trade_ideas,gainers")
    start.add_argument("--any-green", dest="any_green", action="store_true", default=True)
    start.add_argument("--no-any-green", dest="any_green", action="store_false")
    start.add_argument("--lookback-hours", type=float, default=24.0)

    tick = sub.add_parser("tick", help="Mark, exit, and paper-buy once")
    tick.add_argument("--session-id", type=int, default=None)

    status = sub.add_parser("status", help="Print the session, positions, and P&L")
    status.add_argument("--session-id", type=int, default=None)

    stop = sub.add_parser("stop", help="Stop the session and flatten paper positions")
    stop.add_argument("--session-id", type=int, default=None)
    stop.add_argument("--no-flatten", dest="flatten", action="store_false", default=True)

    sub.add_parser("smoke", help="In-memory open, mark, and close. No network.")

    args = parser.parse_args(argv)
    if args.command == "smoke":
        _print(smoke())
        return 0

    with _cli_session() as db:
        if args.command == "start":
            try:
                book = start_session(
                    db,
                    bankroll_eur=args.bankroll,
                    sources=args.sources,
                    any_green=args.any_green,
                    lookback_hours=args.lookback_hours,
                    dry_run=True,
                )
            except CopyBookError as exc:
                _print({"dry_run": True, "live_orders": False, "error": str(exc)})
                return 1
            _print(snapshot(db, book))
            return 0
        if args.command == "status":
            book = resolve_session(db, args.session_id)
            _print(snapshot(db, book))
            return 0
        if args.command == "tick":
            try:
                _print(asyncio.run(tick_session(db, args.session_id)))
            except CopyBookError as exc:
                _print({"dry_run": True, "live_orders": False, "error": str(exc)})
                return 1
            return 0
        if args.command == "stop":
            try:
                _print(asyncio.run(stop_session(db, args.session_id, flatten=args.flatten)))
            except CopyBookError as exc:
                _print({"dry_run": True, "live_orders": False, "error": str(exc)})
                return 1
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
