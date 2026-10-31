"""Helm commodities venue on MetaApi (MT4/MT5). Paper first.

This sits beside the Revolut X venue and does not change it.

* Paper mode (``HELM_METAAPI_MODE=paper``, the default) opens rows in the
  ``metaapipaperposition`` ledger at the live bid/ask. No broker order.
* Live mode (``HELM_METAAPI_MODE=live``) sends a market order with mandatory
  stop-loss and take-profit, and only after: TradeIdea Approved + ApprovalEvent,
  per-idea ``leveraged_ok`` acknowledgement, lots <= HELM_METAAPI_MAX_LOTS,
  allowed symbol, and account margin level >= 300%.

MT4/MT5 brokers sell leveraged CFDs, not spot. Guardian always says so.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from api.models.metaapi import MetaApiIdea, MetaApiPaperPosition
from api.models.trade import ApprovalEvent, ExecutionTicket, TradeIdea, TradeIdeaVersion
from api.services import metaapi_client as mc

logger = logging.getLogger(__name__)

VENUE = "metaapi"
USER_ID = "seed_user"
MIN_MARGIN_LEVEL_PCT = 300.0
DEFAULT_SYMBOLS = ("XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD")
# Typical MT contract sizes. Brokers differ; override with HELM_METAAPI_CONTRACT_SIZES.
DEFAULT_CONTRACT_SIZES = {"XAUUSD": 100.0, "XAGUSD": 5000.0, "XBRUSD": 1000.0, "XTIUSD": 1000.0}
CFD_WARNING = (
    "MetaApi trades through an MT4/MT5 broker. These are leveraged CFDs, not spot: "
    "you do not own the commodity, losses can exceed the margin posted, and overnight swap is charged. "
    "This breaks Helm's spot-only rule, so each idea needs its own leveraged_ok acknowledgement."
)


class MetaApiVenueError(Exception):
    status_code = 400


class MetaApiVenueNotFound(MetaApiVenueError):
    status_code = 404


# ── config ──────────────────────────────────────────────────────────────────

def mode() -> str:
    m = (os.getenv("HELM_METAAPI_MODE") or "paper").strip().lower()
    return "live" if m == "live" else "paper"


def max_lots() -> float:
    try:
        return max(0.0, float(os.getenv("HELM_METAAPI_MAX_LOTS") or 0.01))
    except ValueError:
        return 0.01


def allowed_symbols() -> list[str]:
    raw = os.getenv("HELM_METAAPI_ALLOWED_SYMBOLS")
    if not raw:
        return list(DEFAULT_SYMBOLS)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def swap_rate_per_night() -> float:
    """Fraction of notional charged per night held (estimate). Default 0.02%."""
    try:
        return float(os.getenv("HELM_METAAPI_SWAP_PCT_PER_NIGHT") or 0.0002)
    except ValueError:
        return 0.0002


def contract_size(symbol: str) -> float:
    sizes = dict(DEFAULT_CONTRACT_SIZES)
    raw = os.getenv("HELM_METAAPI_CONTRACT_SIZES")  # e.g. XAUUSD=100,XAGUSD=5000
    if raw:
        for part in raw.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    sizes[k.strip().upper()] = float(v)
                except ValueError:
                    pass
    return sizes.get(symbol.upper(), 1.0)


def status() -> dict:
    """Public config. Never includes the token or account id."""
    return {
        "venue": VENUE,
        "configured": mc.configured(),
        "mode": mode(),
        "live_orders": mode() == "live",
        "max_lots": max_lots(),
        "allowed_symbols": allowed_symbols(),
        "min_margin_level_pct": MIN_MARGIN_LEVEL_PCT,
        "swap_pct_per_night": swap_rate_per_night(),
        "warning": CFD_WARNING,
    }


# ── helpers ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _bid_ask(quote: dict) -> tuple[float, float]:
    bid = float(quote.get("bid") or 0)
    ask = float(quote.get("ask") or 0)
    if not bid and not ask:
        raise MetaApiVenueError("Quote has no bid/ask")
    return (bid or ask), (ask or bid)


async def _quote(symbol: str, quotes: Optional[dict] = None) -> dict:
    if quotes and symbol in quotes:
        return quotes[symbol]
    return await mc.get_current_price(symbol)


def meta_for(db: Session, trade_id: int) -> Optional[MetaApiIdea]:
    return db.exec(select(MetaApiIdea).where(MetaApiIdea.trade_idea_id == trade_id)).first()


def is_metaapi_idea(db: Session, trade_id: int) -> bool:
    return meta_for(db, trade_id) is not None


# ── Guardian ────────────────────────────────────────────────────────────────

def guardian_check(
    trade: TradeIdea,
    meta: Optional[MetaApiIdea],
    *,
    account: Optional[dict] = None,
    live: bool = False,
) -> dict:
    """Venue checks on top of the generic Guardian. ``issues`` block; ``warnings`` don't."""
    issues: list[str] = []
    warnings = [CFD_WARNING]
    if meta is None:
        issues.append("Not a MetaApi idea")
        return {"passed": False, "issues": issues, "warnings": warnings}
    sym = (meta.symbol or "").upper()
    if sym not in allowed_symbols():
        issues.append(f"{sym} is not in HELM_METAAPI_ALLOWED_SYMBOLS")
    direction = (trade.direction or "").upper()
    if direction not in ("LONG", "SHORT"):
        issues.append("Direction must be LONG or SHORT")
    if not trade.stop_price or not trade.target_price:
        issues.append("Stop-loss and take-profit are mandatory")
    elif direction == "LONG" and not (trade.stop_price < trade.entry_price < trade.target_price):
        issues.append("LONG needs stop < entry < target")
    elif direction == "SHORT" and not (trade.target_price < trade.entry_price < trade.stop_price):
        issues.append("SHORT needs target < entry < stop")
    if meta.lots <= 0 or meta.lots > max_lots() + 1e-9:
        issues.append(f"Lots {meta.lots} outside 0 < lots <= HELM_METAAPI_MAX_LOTS ({max_lots()})")
    if live:
        if not meta.leveraged_ok:
            issues.append("Leveraged CFD not acknowledged for this idea (leveraged_ok is false)")
        if account is None:
            issues.append("Account information unavailable; cannot check margin level")
        else:
            margin = float(account.get("margin") or 0)
            level = account.get("marginLevel")
            if margin > 0 and (level is None or float(level) < MIN_MARGIN_LEVEL_PCT):
                issues.append(f"Margin level {level}% is below {MIN_MARGIN_LEVEL_PCT:.0f}%")
            if float(account.get("equity") or 0) <= 0:
                issues.append("Account equity is zero")
    return {"passed": not issues, "issues": issues, "warnings": warnings}


# ── ideas ───────────────────────────────────────────────────────────────────

def create_idea(
    db: Session,
    *,
    symbol: str,
    direction: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    thesis: str,
    invalidation_notes: str,
    lots: Optional[float] = None,
    source: str = "manual",
) -> tuple[TradeIdea, MetaApiIdea]:
    sym = symbol.upper()
    if sym not in allowed_symbols():
        raise MetaApiVenueError(f"{sym} is not an allowed MetaApi symbol")
    lots = max_lots() if lots is None else float(lots)
    if lots <= 0 or lots > max_lots() + 1e-9:
        raise MetaApiVenueError(f"Lots must be > 0 and <= {max_lots()}")
    trade = TradeIdea(
        user_id=USER_ID,
        symbol=sym,
        direction=direction.upper(),
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        thesis=thesis,
        invalidation_notes=invalidation_notes,
        status="Ready for Approval",
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    db.add(
        TradeIdeaVersion(
            user_id=USER_ID,
            symbol=sym,
            direction=trade.direction,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            thesis=thesis,
            invalidation_notes=invalidation_notes,
            status=trade.status,
            trade_idea_id=trade.id,
            version_number=1,
        )
    )
    meta = MetaApiIdea(trade_idea_id=trade.id, symbol=sym, lots=lots, source=source)
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return trade, meta


def acknowledge_leverage(db: Session, trade_id: int, leveraged_ok: bool) -> MetaApiIdea:
    meta = meta_for(db, trade_id)
    if meta is None:
        raise MetaApiVenueNotFound("MetaApi idea not found")
    meta.leveraged_ok = bool(leveraged_ok)
    meta.leveraged_ack_at = _now() if leveraged_ok else None
    meta.updated_at = _now()
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


def list_ideas(db: Session) -> list[dict]:
    rows = db.exec(select(MetaApiIdea).order_by(MetaApiIdea.id.desc())).all()
    out = []
    for meta in rows:
        trade = db.get(TradeIdea, meta.trade_idea_id)
        if trade is None:
            continue
        out.append(
            {
                "trade_idea_id": trade.id,
                "venue": VENUE,
                "symbol": meta.symbol,
                "direction": trade.direction,
                "entry_price": trade.entry_price,
                "stop_price": trade.stop_price,
                "target_price": trade.target_price,
                "thesis": trade.thesis,
                "status": trade.status,
                "lots": meta.lots,
                "leveraged_ok": meta.leveraged_ok,
                "source": meta.source,
                "guardian": guardian_check(trade, meta),
            }
        )
    return out


# ── scout ───────────────────────────────────────────────────────────────────

def _closes(candles: list[dict]) -> list[float]:
    return [float(c["close"]) for c in candles if c.get("close") is not None]


def _atr(candles: list[dict], n: int = 14) -> float:
    trs = []
    prev = None
    for c in candles:
        h, l, cl = float(c["high"]), float(c["low"]), float(c["close"])
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        trs.append(tr)
        prev = cl
    tail = trs[-n:]
    return sum(tail) / len(tail) if tail else 0.0


def signal_from_candles(symbol: str, candles: list[dict]) -> Optional[dict]:
    """SMA20 trend + slope, ATR-sized bracket (1.5 ATR stop, 3 ATR target, R:R 2)."""
    closes = _closes(candles)
    if len(closes) < 25:
        return None
    sma = sum(closes[-20:]) / 20
    sma_prev = sum(closes[-25:-5]) / 20
    last = closes[-1]
    atr = _atr(candles)
    if atr <= 0 or not math.isfinite(atr):
        return None
    if last > sma and sma > sma_prev:
        direction, stop, target = "LONG", last - 1.5 * atr, last + 3 * atr
    elif last < sma and sma < sma_prev:
        direction, stop, target = "SHORT", last + 1.5 * atr, last - 3 * atr
    else:
        return None
    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": round(last, 5),
        "stop_price": round(stop, 5),
        "target_price": round(target, 5),
        "thesis": (
            f"Helm commodities scout: {symbol} {direction}. Last {last:.4f} vs SMA20 {sma:.4f} "
            f"(slope {'up' if sma > sma_prev else 'down'}); ATR14 {atr:.4f}. Leveraged CFD via MetaApi."
        ),
        "invalidation_notes": f"Close back through SMA20 ({sma:.4f}) or stop at {stop:.4f}.",
    }


async def run_scout(db: Session, candles_by_symbol: Optional[dict[str, list[dict]]] = None) -> dict:
    """Stage TradeIdeas (venue=metaapi) for approval. Never executes."""
    staged, skipped = [], []
    for sym in allowed_symbols():
        open_idea = db.exec(
            select(MetaApiIdea, TradeIdea)
            .where(MetaApiIdea.trade_idea_id == TradeIdea.id)
            .where(MetaApiIdea.symbol == sym)
            .where(TradeIdea.status.in_(["Ready for Approval", "Approved"]))
        ).first()
        if open_idea:
            skipped.append({"symbol": sym, "reason": "idea already pending"})
            continue
        try:
            candles = (candles_by_symbol or {}).get(sym)
            if candles is None:
                candles = await mc.get_candles(sym, "1h", 100)
        except mc.MetaApiError as exc:
            skipped.append({"symbol": sym, "reason": str(exc)})
            continue
        sig = signal_from_candles(sym, candles or [])
        if not sig:
            skipped.append({"symbol": sym, "reason": "no trend signal"})
            continue
        trade, meta = create_idea(db, source="scout", **sig)
        staged.append({"trade_idea_id": trade.id, "symbol": sym, "direction": trade.direction, "lots": meta.lots})
    return {"venue": VENUE, "staged": staged, "skipped": skipped, "live_orders": False}


# ── paper ledger ────────────────────────────────────────────────────────────

def _swap(pos: MetaApiPaperPosition, now: datetime) -> float:
    nights = max(0, (now.date() - _aware(pos.opened_at).date()).days)
    return round(nights * pos.swap_rate_per_night * pos.entry_price * pos.lots * pos.contract_size, 4)


def _pnl(pos: MetaApiPaperPosition, exit_px: float, swap: float) -> float:
    sign = 1.0 if pos.direction == "LONG" else -1.0
    return round(sign * (exit_px - pos.entry_price) * pos.lots * pos.contract_size - swap, 4)


def _view(pos: MetaApiPaperPosition) -> dict:
    d = pos.model_dump()
    for k in ("opened_at", "closed_at", "updated_at", "last_marked_at"):
        if d.get(k):
            d[k] = _aware(d[k]).isoformat()
    d["currency"] = "USD"
    return d


async def open_paper(db: Session, trade: TradeIdea, meta: MetaApiIdea, quotes: Optional[dict] = None) -> dict:
    bid, ask = _bid_ask(await _quote(meta.symbol, quotes))
    direction = trade.direction.upper()
    entry = ask if direction == "LONG" else bid  # pay the spread on entry
    cs = contract_size(meta.symbol)
    pos = MetaApiPaperPosition(
        trade_idea_id=trade.id,
        symbol=meta.symbol,
        direction=direction,
        lots=meta.lots,
        contract_size=cs,
        entry_price=entry,
        stop_price=trade.stop_price,
        target_price=trade.target_price,
        spread_cost=round((ask - bid) * meta.lots * cs, 4),
        swap_rate_per_night=swap_rate_per_night(),
    )
    db.add(pos)
    trade.status = "Executed"
    trade.updated_at = _now()
    db.add(trade)
    db.commit()
    db.refresh(pos)
    return {"mode": "paper", "live_orders": False, "position": _view(pos)}


async def mark_paper(db: Session, quotes: Optional[dict] = None) -> dict:
    """Mark open paper positions at the exit side; close on SL/TP touch."""
    now = _now()
    out, closed = [], []
    for pos in db.exec(select(MetaApiPaperPosition).where(MetaApiPaperPosition.status == "open")).all():
        try:
            bid, ask = _bid_ask(await _quote(pos.symbol, quotes))
        except (mc.MetaApiError, MetaApiVenueError) as exc:
            out.append({"id": pos.id, "symbol": pos.symbol, "error": str(exc)})
            continue
        mark = bid if pos.direction == "LONG" else ask
        swap = _swap(pos, now)
        hit = None
        if pos.direction == "LONG":
            if mark <= pos.stop_price:
                hit, mark = "stop", pos.stop_price
            elif mark >= pos.target_price:
                hit, mark = "target", pos.target_price
        else:
            if mark >= pos.stop_price:
                hit, mark = "stop", pos.stop_price
            elif mark <= pos.target_price:
                hit, mark = "target", pos.target_price
        pos.swap_estimate = swap
        pos.last_mark = mark
        pos.last_marked_at = now
        pos.unrealized_pnl = _pnl(pos, mark, swap)
        if hit:
            pos.status = "closed"
            pos.exit_price = mark
            pos.realized_pnl = pos.unrealized_pnl
            pos.unrealized_pnl = 0.0
            pos.exit_reason = hit
            pos.closed_at = now
            closed.append(pos.id)
        pos.updated_at = now
        db.add(pos)
        out.append(_view(pos))
    db.commit()
    return {"mode": "paper", "marked": out, "closed": closed}


async def close_paper(db: Session, position_id: int, quotes: Optional[dict] = None) -> dict:
    pos = db.get(MetaApiPaperPosition, position_id)
    if pos is None:
        raise MetaApiVenueNotFound("Paper position not found")
    if pos.status != "open":
        raise MetaApiVenueError("Position already closed")
    bid, ask = _bid_ask(await _quote(pos.symbol, quotes))
    now = _now()
    px = bid if pos.direction == "LONG" else ask
    pos.swap_estimate = _swap(pos, now)
    pos.exit_price = px
    pos.last_mark = px
    pos.realized_pnl = _pnl(pos, px, pos.swap_estimate)
    pos.unrealized_pnl = 0.0
    pos.exit_reason = "manual"
    pos.status = "closed"
    pos.closed_at = now
    pos.updated_at = now
    db.add(pos)
    db.commit()
    return {"mode": "paper", "position": _view(pos)}


def ledger(db: Session) -> dict:
    rows = db.exec(select(MetaApiPaperPosition).order_by(MetaApiPaperPosition.id.desc())).all()
    open_rows = [_view(p) for p in rows if p.status == "open"]
    closed_rows = [_view(p) for p in rows if p.status == "closed"]
    return {
        "currency": "USD",
        "open": open_rows,
        "closed": closed_rows,
        "unrealized_pnl": round(sum(p["unrealized_pnl"] or 0 for p in open_rows), 2),
        "realized_pnl": round(sum(p["realized_pnl"] or 0 for p in closed_rows), 2),
    }


# ── execute (HITL) ──────────────────────────────────────────────────────────

def _snapshot_hash(trade: TradeIdea) -> str:
    snap = {
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "stop_price": trade.stop_price,
        "target_price": trade.target_price,
        "thesis": trade.thesis,
        "invalidation_notes": trade.invalidation_notes,
    }
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()[:16]


async def execute(db: Session, trade_id: int, quotes: Optional[dict] = None) -> dict:
    trade = db.get(TradeIdea, trade_id)
    if trade is None:
        raise MetaApiVenueNotFound("Trade idea not found")
    meta = meta_for(db, trade_id)
    if meta is None:
        raise MetaApiVenueError("Not a MetaApi idea; use the Revolut X execute route")
    if trade.status != "Approved":
        raise MetaApiVenueError(f"Trade must be Approved to execute. Current status: {trade.status}")
    approval = db.exec(
        select(ApprovalEvent)
        .where(ApprovalEvent.trade_idea_id == trade_id)
        .order_by(ApprovalEvent.timestamp.desc())
    ).first()
    if approval is None:
        raise MetaApiVenueError("No approval event found for this trade")
    if approval.snapshot_hash != _snapshot_hash(trade):
        raise MetaApiVenueError("Idea changed after approval; re-approve")

    if mode() != "live":
        verdict = guardian_check(trade, meta, live=False)
        if not verdict["passed"]:
            raise MetaApiVenueError("; ".join(verdict["issues"]))
        result = await open_paper(db, trade, meta, quotes)
        result["guardian"] = verdict
        return result

    if not mc.configured():
        raise MetaApiVenueError("Live mode needs METAAPI_TOKEN and METAAPI_ACCOUNT_ID")
    account = await mc.get_account_information()
    verdict = guardian_check(trade, meta, account=account, live=True)
    if not verdict["passed"]:
        raise MetaApiVenueError("; ".join(verdict["issues"]))
    ticket = ExecutionTicket(
        approval_event_id=approval.id,
        symbol=meta.symbol,
        side="buy" if trade.direction.upper() == "LONG" else "sell",
        adapter_status="Pending",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    try:
        resp = await mc.place_market_order(
            symbol=meta.symbol,
            direction=trade.direction,
            volume=meta.lots,
            stop_loss=trade.stop_price,
            take_profit=trade.target_price,
            client_id=f"HELM-{trade.id}-{approval.id}",
        )
    except mc.MetaApiError as exc:
        ticket.adapter_status = "Failed"
        ticket.provider_response = mc.redact(exc)
        db.add(ticket)
        db.commit()
        raise MetaApiVenueError(f"MetaApi order failed: {mc.redact(exc)}") from None
    ticket.adapter_status = "Submitted" if resp.get("numericCode", 0) in (0, 10008, 10009) else "Rejected"
    ticket.broker_order_id = str(resp.get("orderId") or resp.get("positionId") or "") or None
    ticket.provider_response = mc.redact(json.dumps(resp)[:1000])
    ticket.fill_qty = meta.lots
    db.add(ticket)
    if ticket.adapter_status == "Submitted":
        trade.status = "Executed"
        trade.updated_at = _now()
        db.add(trade)
    db.commit()
    return {
        "mode": "live",
        "live_orders": True,
        "ticket_id": ticket.id,
        "adapter_status": ticket.adapter_status,
        "broker_order_id": ticket.broker_order_id,
        "guardian": verdict,
    }
