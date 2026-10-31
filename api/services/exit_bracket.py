"""Helm exit brackets — strategy-layer stop, target, and trailing ratchet.

Revolut X spot has no native attached stop-loss or take-profit. A filled spot
LONG is protected here, not on the order.

Rule (spot LONG only)
---------------------
R = fill_price - initial_stop. Trailing is off when R <= 0.

* Hard stop: bid <= effective stop, and the effective stop is still the
  original stop. Action ``hard_stop``.
* Trailing ratchet: once the bid high-water reaches fill + 1R, the stop
  moves to high-water - 1R. It only steps when the new level is at least
  0.25R above the current stop. It never moves down and never under the
  original stop. A later breach of that raised stop is ``trailing_stop``.
* Take-profit: bid >= target_price, checked after the stop so a gap through
  the stop protects capital first. Action ``take_profit``.

The mark used is the bid (what a market sell can receive).

Live vs paper
-------------
A trigger on a live account creates a ``direction="EXIT"`` TradeIdea in
``Ready for Approval``. Nothing is sent to the broker until a human records
an ApprovalEvent and executes that idea.

When ``PAPER_TRADING`` is on, the same idea is auto-approved (ApprovalEvent
included) and the sell is simulated. The monitor never places a live order.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from api.core.config import settings
from api.models.trade import (
    ApprovalEvent,
    ExecutionTicket,
    ExitBracket,
    TradeIdea,
    TradeIdeaVersion,
)

logger = logging.getLogger(__name__)

# Conservative trailing ratchet. See module docstring and docs/helm-exit-brackets.md.
ARM_R = 1.0
TRAIL_DISTANCE_R = 1.0
RATCHET_STEP_R = 0.25
REJECT_COOLDOWN = timedelta(minutes=15)

ACTIVE_STATUSES = ("armed", "exit_proposed", "closing")
EXIT_QUEUE_USER_ID = "seed_user"  # same approvals queue as the trade routers

RULE_TEXT = (
    "Spot LONG only. Hard stop when bid is at or through stop_price. "
    "Take-profit when bid is at or through target_price. "
    "Trailing ratchet arms after the bid high-water reaches one R above the fill "
    "(R = fill - initial stop), then trails one R behind that high-water. "
    "The stop steps only when the new level is at least 0.25R higher, never down, "
    "and never below the original stop. "
    "Live triggers become a Ready-for-Approval EXIT idea; the broker sell waits for "
    "an ApprovalEvent plus execute. PAPER_TRADING=1 auto-approves and simulates the sell."
)


@dataclass(frozen=True)
class BracketEvaluation:
    action: str  # hold | hard_stop | take_profit | trailing_stop
    stop_price: float
    high_water_price: float
    trail_armed: bool
    risk_per_unit: float


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_profit_notify(fn_name: str, session: Session, bracket: ExitBracket, price: Optional[float]) -> None:
    """Record a Helm profit ping without blocking the exit proposal or fill.

    A notification failure must not roll back the EXIT idea or the ticket.
    This does not place a broker order.
    """
    try:
        from api.services import profit_notifications

        getattr(profit_notifications, fn_name)(session, bracket, price)
    except Exception:
        logger.exception("Helm profit notification (%s) failed for bracket #%s", fn_name, bracket.id)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def extract_bid(ticker) -> Optional[float]:
    """Pull a positive bid out of the shapes Revolut X ticker calls return."""
    if isinstance(ticker, list) and ticker:
        row = ticker[0]
    elif isinstance(ticker, dict) and "data" in ticker:
        data = ticker["data"]
        if isinstance(data, list):
            row = data[0] if data else None
        else:
            row = data
    else:
        row = ticker
    if not isinstance(row, dict):
        return None
    try:
        bid = float(row.get("bid") or 0)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(bid) or bid <= 0:
        return None
    return bid


def evaluate_long_bracket(
    *,
    entry_price: float,
    initial_stop: float,
    stop_price: float,
    target_price: float,
    high_water: float,
    bid: float,
) -> BracketEvaluation:
    """Pure stop / target / ratchet decision for one spot LONG. No I/O."""
    try:
        entry = float(entry_price)
        initial = float(initial_stop)
        stop = float(stop_price)
        target = float(target_price)
        high = float(high_water)
        px = float(bid)
    except (TypeError, ValueError):
        return BracketEvaluation("hold", float(stop_price or 0), float(high_water or 0), False, 0.0)

    if not all(math.isfinite(n) for n in (entry, initial, stop, target, high, px)):
        return BracketEvaluation("hold", stop, high, False, entry - initial)

    risk = entry - initial
    if px <= 0:
        return BracketEvaluation("hold", stop, high, stop > initial + 1e-9, risk)

    if px > high:
        high = px

    trail_armed = False
    if risk > 0 and high + 1e-9 >= entry + ARM_R * risk:
        trail_armed = True
        candidate = high - TRAIL_DISTANCE_R * risk
        if candidate < initial:
            candidate = initial
        step = RATCHET_STEP_R * risk
        if candidate > stop and (candidate - stop) + 1e-9 >= step:
            stop = candidate

    if stop < initial:
        stop = initial

    if px <= stop:
        action = "trailing_stop" if stop > initial + 1e-9 else "hard_stop"
    elif px >= target:
        action = "take_profit"
    else:
        action = "hold"

    return BracketEvaluation(
        action=action,
        stop_price=stop,
        high_water_price=high,
        trail_armed=trail_armed or stop > initial + 1e-9,
        risk_per_unit=risk,
    )


def _snapshot_hash(trade: TradeIdea) -> str:
    """Same snapshot the approvals router hashes, so paper and human events match."""
    snapshot = {
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "stop_price": trade.stop_price,
        "target_price": trade.target_price,
        "thesis": trade.thesis,
        "invalidation_notes": trade.invalidation_notes,
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:16]


def default_levels(trade: TradeIdea, fill_price: float) -> tuple[Optional[float], Optional[float]]:
    """Stop and target for a new bracket.

    Helm's symmetric rule (HELM_TP_PCT / HELM_SL_PCT, net of fees) is the
    default for new REVX ideas: scout ideas, and any LONG idea missing a level,
    get +TP / -SL rebased on the actual fill. Other ideas keep their own levels.
    """
    from api.services import helm_strategy

    stop = trade.stop_price
    target = trade.target_price
    missing = not stop or stop <= 0 or not target or target <= 0
    scout = (trade.thesis or "").startswith(helm_strategy.SCOUT_TAG)
    if settings.HELM_SYMMETRIC_BRACKETS and fill_price > 0 and (missing or scout):
        return helm_strategy.bracket_levels(fill_price)
    return stop, target


def arm_bracket(session: Session, ticket: ExecutionTicket, trade: TradeIdea) -> Optional[ExitBracket]:
    """Arm a bracket for a filled spot LONG. Returns the existing row if present.

    Shorts are refused. Missing fill, stop, or target is refused.
    """
    if (trade.direction or "").upper() != "LONG":
        logger.info("Exit bracket skipped for trade #%s direction=%s", trade.id, trade.direction)
        return None
    if (ticket.side or "").lower() != "buy":
        return None
    if not ticket.id or not ticket.fill_qty or ticket.fill_qty <= 0:
        return None
    if not ticket.fill_price or ticket.fill_price <= 0:
        return None
    if trade.status in {"Closed", "Cancelled"}:
        return None
    stop_level, target_level = default_levels(trade, float(ticket.fill_price))
    if not stop_level or stop_level <= 0 or not target_level or target_level <= 0:
        return None

    existing = session.exec(
        select(ExitBracket).where(ExitBracket.entry_ticket_id == ticket.id)
    ).first()
    if existing:
        return existing

    now = utcnow()
    bracket = ExitBracket(
        entry_ticket_id=ticket.id,
        trade_idea_id=trade.id,  # type: ignore[arg-type]
        symbol=trade.symbol,
        direction="LONG",
        qty=float(ticket.fill_qty),
        entry_price=float(ticket.fill_price),
        initial_stop_price=float(stop_level),
        stop_price=float(stop_level),
        target_price=float(target_level),
        high_water_price=float(ticket.fill_price),
        trail_armed=False,
        status="armed",
        created_at=now,
        updated_at=now,
    )
    session.add(bracket)
    session.flush()
    logger.info(
        "Armed exit bracket #%s %s qty=%s stop=%s target=%s",
        bracket.id, bracket.symbol, bracket.qty, bracket.stop_price, bracket.target_price,
    )
    return bracket


def ensure_brackets(session: Session) -> int:
    """Arm brackets for filled LONG buys that do not have one yet. Returns how many were new."""
    tickets = session.exec(
        select(ExecutionTicket).where(ExecutionTicket.side == "buy")
    ).all()
    created = 0
    for ticket in tickets:
        if ticket.adapter_status not in {"Filled", "PaperFilled"}:
            continue
        if not ticket.approval_event_id or not ticket.fill_qty or not ticket.fill_price:
            continue
        already = session.exec(
            select(ExitBracket).where(ExitBracket.entry_ticket_id == ticket.id)
        ).first()
        if already:
            continue
        approval = session.get(ApprovalEvent, ticket.approval_event_id)
        if not approval:
            continue
        trade = session.get(TradeIdea, approval.trade_idea_id)
        if not trade:
            continue
        before = ticket.id
        bracket = arm_bracket(session, ticket, trade)
        if bracket and bracket.entry_ticket_id == before and bracket.id:
            # arm_bracket returns an existing row too; only count a fresh insert
            # by checking it was flushed without a prior row. `already` covered that.
            created += 1
    return created


def bracket_for_exit_trade(session: Session, trade_id: int) -> Optional[ExitBracket]:
    return session.exec(
        select(ExitBracket).where(ExitBracket.exit_trade_idea_id == trade_id)
    ).first()


def _exit_idea(session: Session, bracket: ExitBracket) -> Optional[TradeIdea]:
    if not bracket.exit_trade_idea_id:
        return None
    return session.get(TradeIdea, bracket.exit_trade_idea_id)


def _has_approval(session: Session, trade_id: int) -> bool:
    return (
        session.exec(
            select(ApprovalEvent).where(ApprovalEvent.trade_idea_id == trade_id)
        ).first()
        is not None
    )


def _add_version(session: Session, trade: TradeIdea) -> TradeIdeaVersion:
    version = TradeIdeaVersion(
        user_id=trade.user_id,
        symbol=trade.symbol,
        direction=trade.direction,
        entry_price=trade.entry_price,
        stop_price=trade.stop_price,
        target_price=trade.target_price,
        thesis=trade.thesis,
        invalidation_notes=trade.invalidation_notes,
        trade_idea_id=trade.id,  # type: ignore[arg-type]
        version_number=1,
    )
    session.add(version)
    session.flush()
    return version


def _propose_exit(session: Session, bracket: ExitBracket, bid: float, reason: str) -> TradeIdea:
    thesis = (
        f"[EXIT {reason}] Helm bracket proposes a market sell of {bracket.qty} {bracket.symbol}. "
        f"Bid {bid:.8g} hit {reason.replace('_', ' ')}. "
        f"Fill {bracket.entry_price:.8g}, effective stop {bracket.stop_price:.8g}, "
        f"initial stop {bracket.initial_stop_price:.8g}, target {bracket.target_price:.8g}. "
        "Approve, then execute, to sell the spot long. Reject to keep it open."
    )
    invalidation = (
        "Reject to keep the long open. Helm will not send a broker order from this signal. "
        "A new exit idea is created only after price clears this trigger and the cooldown elapses."
    )
    now = utcnow()
    idea = TradeIdea(
        user_id=EXIT_QUEUE_USER_ID,
        symbol=bracket.symbol,
        direction="EXIT",
        entry_price=float(bid),
        stop_price=float(bracket.stop_price),
        target_price=float(bracket.target_price),
        thesis=thesis,
        invalidation_notes=invalidation,
        status="Ready for Approval",
        created_at=now,
        updated_at=now,
    )
    session.add(idea)
    session.flush()
    _add_version(session, idea)
    bracket.exit_trade_idea_id = idea.id
    bracket.status = "exit_proposed"
    bracket.exit_reason = reason
    bracket.last_trigger = reason
    bracket.pending_clear = False
    bracket.updated_at = now
    session.add(bracket)
    session.flush()
    logger.info(
        "Proposed EXIT idea #%s for bracket #%s %s reason=%s",
        idea.id, bracket.id, bracket.symbol, reason,
    )
    if reason == "take_profit":
        _safe_profit_notify("notify_take_profit", session, bracket, bid)
    return idea


def mark_exit_filled(
    session: Session,
    bracket: ExitBracket,
    exit_trade: TradeIdea,
    *,
    adapter_status: str,
    fill_price: Optional[float],
    paper: bool,
) -> None:
    """Update bracket + ideas after an exit order result is known."""
    now = utcnow()
    filled = adapter_status in {"Filled", "PaperFilled"}
    if filled:
        bracket.status = "paper_closed" if paper or adapter_status == "PaperFilled" else "closed"
        bracket.closed_at = now
        if fill_price:
            bracket.last_price = float(fill_price)
        exit_trade.status = "Closed"
        entry = session.get(TradeIdea, bracket.trade_idea_id)
        if entry and entry.status not in {"Cancelled"}:
            entry.status = "Closed"
            entry.updated_at = now
            session.add(entry)
        _safe_profit_notify("notify_exit_filled", session, bracket, fill_price or bracket.last_price)
    elif adapter_status in {"Open", "PartiallyFilled", "PaperOpen"}:
        bracket.status = "closing"
        exit_trade.status = "Sent"
    else:
        exit_trade.status = "Needs Work"
    exit_trade.updated_at = now
    bracket.updated_at = now
    session.add(exit_trade)
    session.add(bracket)


def _mark_rejected(bracket: ExitBracket, now: datetime) -> None:
    bracket.status = "armed"
    bracket.pending_clear = True
    bracket.cooldown_until = now + REJECT_COOLDOWN
    if not bracket.last_trigger:
        bracket.last_trigger = bracket.exit_reason
    bracket.updated_at = now


def _cleared(bracket: ExitBracket, bid: float) -> bool:
    trigger = bracket.last_trigger or bracket.exit_reason
    if trigger == "take_profit":
        return bid < float(bracket.target_price)
    return bid > float(bracket.stop_price)


def _cooldown_active(bracket: ExitBracket, now: datetime) -> bool:
    until = _aware(bracket.cooldown_until)
    return bool(until and until > now)


def _reconcile(session: Session, bracket: ExitBracket, now: datetime) -> Optional[str]:
    """Fold the linked exit idea's status back onto the bracket.

    Returns an action when the tick must not open a new proposal, or None when
    evaluation should continue.
    """
    if bracket.status == "closing":
        idea = _exit_idea(session, bracket)
        if idea and idea.status == "Closed":
            bracket.status = "closed"
            bracket.closed_at = bracket.closed_at or now
            return "closed"
        return "closing"

    if bracket.status != "exit_proposed":
        return None

    idea = _exit_idea(session, bracket)
    if idea is None:
        bracket.status = "armed"
        return None

    if idea.status == "Closed":
        bracket.status = "closed"
        bracket.closed_at = bracket.closed_at or now
        return "closed"
    if idea.status == "Sent":
        bracket.status = "closing"
        return "closing"
    if idea.status == "Approved":
        return "awaiting_execute"
    if idea.status == "Ready for Approval":
        return "awaiting_approval"

    if idea.status in {"Needs Work", "Cancelled", "Draft"}:
        if _has_approval(session, idea.id):  # type: ignore[arg-type]
            # Approved once, then execute failed. Leave it for a human retry.
            return "awaiting_retry"
        if idea.status != "Cancelled":
            idea.status = "Cancelled"
            idea.updated_at = now
            session.add(idea)
        _mark_rejected(bracket, now)
        return None

    return "awaiting_approval"


def _apply_view(bracket: ExitBracket, view: BracketEvaluation, bid: float) -> bool:
    before = float(bracket.stop_price)
    bracket.stop_price = view.stop_price
    bracket.high_water_price = view.high_water_price
    bracket.trail_armed = view.trail_armed
    bracket.last_price = bid
    bracket.updated_at = utcnow()
    return view.stop_price > before + 1e-9


async def _default_paper_seller(*, symbol: str, qty: float, comment: str, client_order_id: str) -> dict:
    """Simulated sell. Refuses to run unless paper mode is on — no live broker write."""
    if not settings.PAPER_TRADING:
        raise RuntimeError("signal monitor refused a live broker sell")
    from api.services import trade_executor

    return await trade_executor.execute_trade(
        symbol=symbol,
        direction="LONG",
        side="sell",
        volume=qty,
        comment=comment,
        client_order_id=client_order_id,
    )


async def _paper_close(session: Session, bracket: ExitBracket, bid: float, reason: str, seller) -> dict:
    idea = _propose_exit(session, bracket, bid, reason)
    version = session.exec(
        select(TradeIdeaVersion)
        .where(TradeIdeaVersion.trade_idea_id == idea.id)
        .order_by(TradeIdeaVersion.version_number.desc())
    ).first()
    if version is None:
        version = _add_version(session, idea)
    event = ApprovalEvent(
        trade_idea_id=idea.id,  # type: ignore[arg-type]
        version_id=version.id,  # type: ignore[arg-type]
        user_id=EXIT_QUEUE_USER_ID,
        snapshot_hash=_snapshot_hash(idea),
    )
    session.add(event)
    idea.status = "Approved"
    idea.updated_at = utcnow()
    session.add(idea)
    session.flush()

    result = await seller(
        symbol=bracket.symbol,
        qty=bracket.qty,
        comment=f"AURUM-EXIT#{bracket.id}",
        client_order_id=f"AURUM-EXIT-{bracket.id}-{event.id or idea.id}",
    )
    from api.services.trade_executor import paper_fill_from_result

    resolved = paper_fill_from_result(result) or {}
    filled = bool(result.get("success") and resolved.get("filled"))
    ticket = ExecutionTicket(
        approval_event_id=event.id,
        adapter_status=resolved.get("adapter_status") or ("PaperFilled" if filled else "Rejected"),
        provider_response=str(result),
        broker_order_id=result.get("order_id"),
        symbol=bracket.symbol,
        side="sell",
        fill_qty=resolved.get("fill_qty") or (bracket.qty if filled else None),
        fill_price=resolved.get("fill_price") or (bid if filled else None),
        fees_eur=resolved.get("fees_eur") if resolved.get("fees_eur") is not None else 0.0,
        filled_at=utcnow() if filled else None,
    )
    session.add(ticket)
    if filled:
        mark_exit_filled(
            session,
            bracket,
            idea,
            adapter_status=ticket.adapter_status,
            fill_price=ticket.fill_price,
            paper=True,
        )
        return {
            "action": "paper_closed",
            "bracket_id": bracket.id,
            "symbol": bracket.symbol,
            "reason": reason,
            "exit_trade_idea_id": idea.id,
            "order_id": result.get("order_id"),
        }

    idea.status = "Cancelled"
    idea.updated_at = utcnow()
    session.add(idea)
    _mark_rejected(bracket, utcnow())
    session.add(bracket)
    logger.warning("Paper exit failed for bracket #%s: %s", bracket.id, result)
    return {
        "action": "paper_failed",
        "bracket_id": bracket.id,
        "symbol": bracket.symbol,
        "reason": reason,
        "exit_trade_idea_id": idea.id,
    }


async def tick_bracket(
    session: Session,
    bracket: ExitBracket,
    bid: Optional[float],
    *,
    paper: bool,
    seller=None,
) -> dict:
    """One monitor pass for a single bracket. Does not commit."""
    now = utcnow()
    bracket.last_checked_at = now
    gate = _reconcile(session, bracket, now)
    if gate:
        session.add(bracket)
        return {
            "action": gate,
            "bracket_id": bracket.id,
            "symbol": bracket.symbol,
            "ratcheted": False,
            "status": bracket.status,
        }

    if bid is None or bid <= 0:
        session.add(bracket)
        return {
            "action": "skipped",
            "bracket_id": bracket.id,
            "symbol": bracket.symbol,
            "reason": "no_bid",
            "ratcheted": False,
        }

    view = evaluate_long_bracket(
        entry_price=bracket.entry_price,
        initial_stop=bracket.initial_stop_price,
        stop_price=bracket.stop_price,
        target_price=bracket.target_price,
        high_water=bracket.high_water_price,
        bid=bid,
    )
    ratcheted = _apply_view(bracket, view, bid)

    if view.action == "hold":
        if bracket.pending_clear and _cleared(bracket, bid):
            bracket.pending_clear = False
        session.add(bracket)
        return {
            "action": "hold",
            "bracket_id": bracket.id,
            "symbol": bracket.symbol,
            "ratcheted": ratcheted,
            "stop_price": bracket.stop_price,
            "trail_armed": bracket.trail_armed,
        }

    if bracket.pending_clear:
        session.add(bracket)
        return {
            "action": "suppressed",
            "bracket_id": bracket.id,
            "symbol": bracket.symbol,
            "reason": "pending_clear",
            "ratcheted": ratcheted,
        }
    if _cooldown_active(bracket, now):
        session.add(bracket)
        return {
            "action": "cooldown",
            "bracket_id": bracket.id,
            "symbol": bracket.symbol,
            "reason": view.action,
            "ratcheted": ratcheted,
        }

    if paper:
        outcome = await _paper_close(session, bracket, bid, view.action, seller or _default_paper_seller)
        outcome["ratcheted"] = ratcheted
        return outcome

    idea = _propose_exit(session, bracket, bid, view.action)
    return {
        "action": "proposed",
        "bracket_id": bracket.id,
        "symbol": bracket.symbol,
        "reason": view.action,
        "exit_trade_idea_id": idea.id,
        "ratcheted": ratcheted,
    }


def _lookup_bid(bids: dict, symbol: str) -> Optional[float]:
    if symbol in bids:
        return bids[symbol]
    return bids.get(symbol.upper())


async def monitor_brackets(
    session: Session,
    bids: dict,
    *,
    paper: bool,
    seller=None,
) -> dict:
    """Arm missing brackets, then evaluate each active one.

    ``paper`` is honored only when settings.PAPER_TRADING is also on, so a
    caller cannot ask the monitor to place a live sell.
    """
    effective_paper = bool(paper and settings.PAPER_TRADING)
    ensure_brackets(session)
    session.commit()

    ids = [
        b.id
        for b in session.exec(
            select(ExitBracket).where(ExitBracket.status.in_(ACTIVE_STATUSES))  # type: ignore[attr-defined]
        ).all()
        if b.id is not None
    ]
    outcomes: list[dict] = []
    for bracket_id in ids:
        bracket = session.get(ExitBracket, bracket_id)
        if bracket is None or bracket.status not in ACTIVE_STATUSES:
            continue
        try:
            outcome = await tick_bracket(
                session,
                bracket,
                _lookup_bid(bids, bracket.symbol),
                paper=effective_paper,
                seller=seller,
            )
            session.commit()
            outcomes.append(outcome)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            logger.exception("Exit bracket #%s tick failed", bracket_id)
            outcomes.append({
                "action": "error",
                "bracket_id": bracket_id,
                "error": str(exc),
            })

    summary = {
        "mode": "paper" if effective_paper else "live",
        "checked": len(outcomes),
        "proposed": [o for o in outcomes if o.get("action") == "proposed"],
        "paper_closed": [o for o in outcomes if o.get("action") == "paper_closed"],
        "held": sum(1 for o in outcomes if o.get("action") == "hold"),
        "suppressed": sum(
            1
            for o in outcomes
            if o.get("action") in {
                "suppressed",
                "cooldown",
                "awaiting_approval",
                "awaiting_execute",
                "awaiting_retry",
                "closing",
            }
        ),
        "ratcheted": sum(1 for o in outcomes if o.get("ratcheted")),
        "skipped": sum(1 for o in outcomes if o.get("action") == "skipped"),
        "errors": [o for o in outcomes if o.get("action") == "error"],
        # The monitor does not place live broker orders. Paper fills are simulated.
        "broker_orders_placed": 0,
        "outcomes": outcomes,
    }
    return summary


def bracket_to_dict(session: Session, bracket: ExitBracket) -> dict:
    exit_status = None
    if bracket.exit_trade_idea_id:
        idea = session.get(TradeIdea, bracket.exit_trade_idea_id)
        exit_status = idea.status if idea else None
    return {
        "id": bracket.id,
        "entry_ticket_id": bracket.entry_ticket_id,
        "trade_idea_id": bracket.trade_idea_id,
        "exit_trade_idea_id": bracket.exit_trade_idea_id,
        "exit_trade_status": exit_status,
        "symbol": bracket.symbol,
        "direction": bracket.direction,
        "qty": bracket.qty,
        "entry_price": bracket.entry_price,
        "initial_stop_price": bracket.initial_stop_price,
        "stop_price": bracket.stop_price,
        "target_price": bracket.target_price,
        "high_water_price": bracket.high_water_price,
        "trail_armed": bracket.trail_armed,
        "status": bracket.status,
        "exit_reason": bracket.exit_reason,
        "last_price": bracket.last_price,
        "last_trigger": bracket.last_trigger,
        "pending_clear": bracket.pending_clear,
        "cooldown_until": bracket.cooldown_until.isoformat() if bracket.cooldown_until else None,
        "last_checked_at": bracket.last_checked_at.isoformat() if bracket.last_checked_at else None,
        "closed_at": bracket.closed_at.isoformat() if bracket.closed_at else None,
    }


def _prefer_bracket(candidate: ExitBracket, current: ExitBracket) -> bool:
    rank = {"exit_proposed": 3, "closing": 2, "armed": 1}
    cand_rank = rank.get(candidate.status, 0)
    curr_rank = rank.get(current.status, 0)
    if cand_rank != curr_rank:
        return cand_rank > curr_rank
    return (candidate.id or 0) > (current.id or 0)


def open_brackets_by_symbol(session: Session) -> dict[str, dict]:
    rows = session.exec(
        select(ExitBracket).where(ExitBracket.status.in_(ACTIVE_STATUSES))  # type: ignore[attr-defined]
    ).all()
    best: dict[str, ExitBracket] = {}
    for row in rows:
        key = (row.symbol or "").upper()
        current = best.get(key)
        if current is None or _prefer_bracket(row, current):
            best[key] = row
    return {key: bracket_to_dict(session, row) for key, row in best.items()}


def list_brackets(session: Session, status: Optional[str] = None) -> list[ExitBracket]:
    query = select(ExitBracket).order_by(ExitBracket.updated_at.desc())  # type: ignore[attr-defined]
    if status:
        query = query.where(ExitBracket.status == status)
    return list(session.exec(query).all())
