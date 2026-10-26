"""
Vercel Cron Jobs — stateless, serverless agent endpoints.

Scout is invoked by Vercel Cron and stages TradeIdeas for human approval.
The hunt route can sell positions; it is not registered in vercel.json.

Cost protection:
- AURUM_AGENTS_ENABLED env var = global kill switch
- Rate limiting per-cron to prevent runaway invocations
- gpt-4o-mini by default (10x cheaper than gpt-4o)
- Movement detection to skip unnecessary AI calls
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from sqlmodel import Session, select

from api.core.config import settings
from api.core.db import engine
from api.models.trade import TradeIdea as Trade
from api.services import ai_advisor, auto_approver, revolut_x_client as rx
from api.services.personal_edge import compute_edge_fingerprint

router = APIRouter(tags=["cron"])
logger = logging.getLogger(__name__)

# Rate limiting: track last execution time per cron
_last_run: dict[str, datetime] = {}

def _check_rate_limit(cron_name: str, min_interval_seconds: int) -> bool:
    """Returns True if enough time has passed since last run, False to skip."""
    now = datetime.now(timezone.utc)
    last = _last_run.get(cron_name)
    if last and (now - last).total_seconds() < min_interval_seconds:
        return False
    _last_run[cron_name] = now
    return True


def _verify_cron_secret(authorization: Optional[str]) -> None:
    """Vercel cron jobs send Authorization: Bearer <secret>. Verify it."""
    if not settings.CRON_SECRET:
        return  # No secret configured = allow (local dev mode)
    
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid Authorization format")
    
    token = authorization[7:]  # strip "Bearer "
    if token != settings.CRON_SECRET:
        raise HTTPException(403, "Invalid cron secret")


@router.get("/cron/scout")
async def scout_tick(authorization: Optional[str] = Header(None)):
    """
    AI Scout — polls market data and stages trade recommendations for approval.

    Vercel cron calls this every 15 minutes (root vercel.json). With
    AURUM_AUTO_APPROVE off, each idea is stored as Ready for Approval.
    Declan signs it on the Approvals page, which writes an ApprovalEvent,
    then clicks Execute. This handler never places a broker order.
    """
    _verify_cron_secret(authorization)
    
    # Global kill switch
    if not settings.AURUM_AGENTS_ENABLED:
        return {"status": "disabled", "reason": "AURUM_AGENTS_ENABLED=false"}
    
    # Just under the */15 schedule so a warm instance still accepts the next
    # tick, while a double-fire inside the same window is skipped.
    if not _check_rate_limit("scout", min_interval_seconds=14 * 60):
        return {"status": "skipped", "reason": "rate_limited"}
    
    logger.info("──── SCOUT TICK (cron) ────")
    
    # Config from env
    symbols = [s.strip().upper() for s in settings.SCOUT_SYMBOLS.split(",") if s.strip()]
    playbook = settings.SCOUT_PLAYBOOK or "trend_follower"
    
    if not symbols:
        return {"status": "error", "reason": "SCOUT_SYMBOLS not configured"}
    
    # Fetch personal edge
    edge = None
    try:
        with Session(engine) as session:
            edge = compute_edge_fingerprint(session, user_id=None)
    except Exception as exc:
        logger.warning(f"Edge fingerprint unavailable: {exc}")
    
    # Generate recommendations (with gpt-4o-mini)
    recs = []
    try:
        recs = await ai_advisor.generate_recommendations(
            symbols=symbols,
            max_recommendations=len(symbols),
            playbook_id=playbook,
            edge_fingerprint=edge,
        )
        logger.info(f"Generated {len(recs)} recommendation(s)")
    except Exception as exc:
        logger.error(f"AI advisor failed: {exc}")
        return {"status": "error", "reason": str(exc), "recommendations": 0}
    
    # Always stage for the Approvals page. Auto-approve is optional and
    # still does not send a broker order (Execute requires an ApprovalEvent).
    staged_count = 0
    staged_trade_ids: list[int] = []
    approved_count = 0
    approved_symbols = []

    for rec in recs:
        symbol = rec.get("symbol")

        try:
            with Session(engine) as session:
                staged, stage_msg, trade_id = auto_approver.stage_recommendation(session, rec)
                if staged:
                    logger.info(f"  {symbol}: STAGED #{trade_id} ({stage_msg})")
                    staged_count += 1
                    if trade_id is not None:
                        staged_trade_ids.append(trade_id)
                else:
                    logger.info(f"  {symbol}: not staged ({stage_msg})")
        except Exception as exc:
            logger.error(f"  {symbol}: ERROR staging recommendation: {exc}")

        if not settings.AURUM_AUTO_APPROVE:
            logger.info(f"  {symbol}: waiting for Approvals (AURUM_AUTO_APPROVE off)")
            continue

        eligible, reason = auto_approver.evaluate(rec, edge)
        if not eligible:
            logger.info(f"  {symbol}: NOT ELIGIBLE ({reason})")
            continue

        try:
            with Session(engine) as session:
                approved, msg, trade_id = auto_approver.try_auto_approve(session, rec, edge)
                if approved:
                    logger.info(f"  {symbol}: AUTO-APPROVED #{trade_id} ({msg})")
                    approved_count += 1
                    approved_symbols.append(symbol)
                else:
                    logger.info(f"  {symbol}: BLOCKED ({msg})")
        except Exception as exc:
            logger.error(f"  {symbol}: ERROR during auto-approve: {exc}")

    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recommendations": len(recs),
        "staged": staged_count,
        "staged_trade_ids": staged_trade_ids,
        "approved": approved_count,
        "approved_symbols": approved_symbols,
        "auto_approve": bool(settings.AURUM_AUTO_APPROVE),
    }


@router.get("/cron/hunt")
async def hunt_tick(authorization: Optional[str] = Header(None)):
    """
    Profit Hunter — checks open positions and sells when a profit target is hit.

    This route places market sells with no ApprovalEvent. It is left off
    vercel.json so production cron cannot auto-execute exits. Close positions
    from Approvals → Execute, which requires a signed ApprovalEvent.
    """
    _verify_cron_secret(authorization)
    
    # Global kill switch
    if not settings.AURUM_AGENTS_ENABLED:
        return {"status": "disabled", "reason": "AURUM_AGENTS_ENABLED=false"}
    
    # Rate limit
    if not _check_rate_limit("hunt", min_interval_seconds=110):  # 110s min
        return {"status": "skipped", "reason": "rate_limited"}
    
    logger.info("──── HUNT TICK (cron) ────")
    
    # Fetch open positions from DB
    positions = []
    try:
        with Session(engine) as session:
            positions = session.exec(
                select(Trade).where(Trade.status == "open")
            ).all()
    except Exception as exc:
        logger.error(f"Failed to fetch positions: {exc}")
        return {"status": "error", "reason": str(exc)}
    
    if not positions:
        return {"status": "success", "positions_checked": 0, "positions_closed": 0}
    
    logger.info(f"Checking {len(positions)} open position(s)")
    
    closed_count = 0
    closed_symbols = []
    
    for pos in positions:
        symbol = pos.symbol
        base = symbol.split("-")[0] if "-" in symbol else symbol.split("/")[0]
        
        # Get current bid
        try:
            ticker = await rx.get_ticker(symbol)
            if isinstance(ticker, list) and ticker:
                t = ticker[0]
            elif isinstance(ticker, dict) and "data" in ticker:
                t = ticker["data"][0] if ticker["data"] else None
            else:
                t = ticker
            
            if not t:
                logger.warning(f"  {symbol}: No ticker data")
                continue
            
            bid = float(t.get("bid", 0))
            if bid <= 0:
                logger.warning(f"  {symbol}: Invalid bid={bid}")
                continue
            
        except Exception as exc:
            logger.warning(f"  {symbol}: Ticker fetch failed: {exc}")
            continue
        
        # Compute P&L
        TAKER_FEE = 0.0009
        qty = float(pos.quantity or 0)
        cost = float(pos.entry_price or 0) * qty
        
        sale_gross = qty * bid
        sale_net = sale_gross * (1 - TAKER_FEE)
        pnl = sale_net - cost
        
        target_profit = float(pos.target_profit or 0)
        
        logger.info(f"  {symbol}: bid=€{bid:.6f} P&L=€{pnl:+.4f} target=€{target_profit:+.4f}")
        
        # Check if profit target hit
        if pnl >= target_profit:
            logger.info(f"  {symbol}: 🚀 PROFIT THRESHOLD HIT — SELLING")
            
            try:
                # Place market sell
                result = await rx.place_order(
                    symbol=symbol,
                    side="sell",
                    qty=qty,
                    market=True,
                )
                
                order = result.get("data") if isinstance(result, dict) and "data" in result else result
                if isinstance(order, list) and order:
                    order = order[0]
                
                order_id = order.get("venue_order_id") or order.get("id")
                state = order.get("state")
                
                logger.info(f"  {symbol}: ✅ SELL ORDER {order_id} (state={state})")
                
                # Update position in DB
                with Session(engine) as session:
                    db_pos = session.get(Trade, pos.id)
                    if db_pos:
                        db_pos.status = "closed"
                        db_pos.exit_price = bid
                        db_pos.exit_time = datetime.now(timezone.utc)
                        db_pos.realized_pnl = pnl
                        session.add(db_pos)
                        session.commit()
                
                closed_count += 1
                closed_symbols.append(symbol)
                
            except Exception as exc:
                logger.error(f"  {symbol}: SELL FAILED: {exc}")
    
    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions_checked": len(positions),
        "positions_closed": closed_count,
        "closed_symbols": closed_symbols,
    }
