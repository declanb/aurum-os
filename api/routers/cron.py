"""
Vercel Cron Jobs — stateless, serverless agent endpoints.

These replace the long-running agent loops (scout_agent.py, profit_hunter.py)
with cron-triggered functions for 24/7 autonomous operation on Vercel.

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
    AI Scout — polls market data, generates trade recommendations, auto-approves winners.
    
    Triggered by Vercel cron every 30 minutes.
    Cost: ~$0.04/day OpenAI (gpt-4o-mini, 8 symbols × 48 runs).
    """
    _verify_cron_secret(authorization)
    
    # Global kill switch
    if not settings.AURUM_AGENTS_ENABLED:
        return {"status": "disabled", "reason": "AURUM_AGENTS_ENABLED=false"}
    
    # Rate limit (belt-and-suspenders)
    if not _check_rate_limit("scout", min_interval_seconds=25 * 60):  # 25min min
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
    
    # Auto-approve eligible
    approved_count = 0
    approved_symbols = []
    
    for rec in recs:
        symbol = rec.get("symbol")
        
        # Skip if already claimed
        # (In serverless, we can't use agent_registry, so check open positions in DB instead)
        try:
            with Session(engine) as session:
                existing = session.exec(
                    select(Trade).where(
                        Trade.symbol == symbol,
                        Trade.status == "open"
                    )
                ).first()
                if existing:
                    logger.info(f"  {symbol}: SKIP (already have open position)")
                    continue
        except Exception as exc:
            logger.warning(f"  {symbol}: DB check failed: {exc}")
            continue
        
        # Evaluate
        eligible, reason = auto_approver.evaluate(rec, edge)
        if not eligible:
            logger.info(f"  {symbol}: NOT ELIGIBLE ({reason})")
            continue
        
        # Auto-approve
        try:
            with Session(engine) as session:
                approved, msg, trade_id = auto_approver.try_auto_approve(session, rec, edge)
                if approved:
                    logger.info(f"  {symbol}: ✅ AUTO-APPROVED #{trade_id} ({msg})")
                    approved_count += 1
                    approved_symbols.append(symbol)
                else:
                    logger.info(f"  {symbol}: ❌ BLOCKED ({msg})")
        except Exception as exc:
            logger.error(f"  {symbol}: ERROR during auto-approve: {exc}")
    
    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recommendations": len(recs),
        "approved": approved_count,
        "approved_symbols": approved_symbols,
    }


@router.get("/cron/hunt")
async def hunt_tick(authorization: Optional[str] = Header(None)):
    """
    Profit Hunter — checks all open positions, sells when profit target hit.
    
    Triggered by Vercel cron every 2 minutes.
    Cost: ~$0.50/month Vercel compute (no LLM calls).
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
