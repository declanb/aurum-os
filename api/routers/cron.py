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

from api.services import helm_strategy
from api.core.config import settings
from api.core.db import engine
from api.models.trade import ExitBracket, TradeIdea as Trade
from api.services import agent_registry, ai_advisor, auto_approver, revolut_x_client as rx
from api.services.exit_bracket import (
    ACTIVE_STATUSES,
    ensure_brackets,
    extract_bid,
    monitor_brackets,
)
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
    AI Scout — polls market data, stages TradeIdeas for approval; auto-approves only when enabled.
    
    Triggered by Vercel cron every 30 minutes.
    Cost: ~$0.04/day OpenAI (gpt-4o-mini, 8 symbols × 48 runs).
    """
    _verify_cron_secret(authorization)
    
    # Global kill switch
    if not settings.AURUM_AGENTS_ENABLED:
        return {"status": "disabled", "reason": "AURUM_AGENTS_ENABLED=false"}

    # Same pause flag the local fleet honors. Stops new ideas; does not place orders.
    if agent_registry.is_paused():
        agent_registry.record_action("scout", "Paused — cron pass skipped. No ideas staged.")
        return {"status": "paused", "reason": "AURUM_AGENTS_PAUSED or registry pause"}
    
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
    
    # Stage every rec for human approval. Optionally auto-approve when enabled.
    # NEVER place broker orders from this cron — execute stays a manual click.
    approved_count = 0
    approved_symbols = []
    staged_count = 0
    staged_ids = []
    skipped = []

    # Helm conviction cap: stage the highest-confidence ideas first.
    recs = helm_strategy.rank_recs(recs)
    for rec in recs:
        symbol = rec.get("symbol")

        # Skip if already have an open TradeIdea/position for this symbol
        # (In serverless, we can't use agent_registry, so check DB instead)
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
                    skipped.append({"symbol": symbol, "reason": "open_position"})
                    continue
        except Exception as exc:
            logger.warning(f"  {symbol}: DB check failed: {exc}")
            skipped.append({"symbol": symbol, "reason": f"db_check:{exc}"})
            continue

        # Always stage into Approvals when auto-approve is off (or regardless,
        # matching local scout_agent). stage_recommendation is idempotent.
        try:
            with Session(engine) as session:
                staged, stage_msg, staged_id = auto_approver.stage_recommendation(session, rec)
                if staged:
                    logger.info(f"  {symbol}: 📋 STAGED #{staged_id} ({stage_msg})")
                    staged_count += 1
                    staged_ids.append(staged_id)
                else:
                    logger.info(f"  {symbol}: not staged ({stage_msg})")
                    skipped.append({"symbol": symbol, "reason": stage_msg})
        except Exception as exc:
            logger.error(f"  {symbol}: ERROR staging rec: {exc}")
            skipped.append({"symbol": symbol, "reason": f"stage_error:{exc}"})
            continue

        # Auto-approve only when the master switch is on (still no broker order)
        if not settings.AURUM_AUTO_APPROVE:
            continue

        eligible, reason = auto_approver.evaluate(rec, edge)
        if not eligible:
            logger.info(f"  {symbol}: AUTO-APPROVE skipped ({reason})")
            continue

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

    agent_registry.record_action(
        "scout",
        f"Cron pass staged {staged_count}, auto-approved {approved_count}.",
    )
    agent_registry.record_action(
        "recommender",
        f"Ranked {len(recs)} setup(s) on the cron pass.",
    )
    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recommendations": len(recs),
        "staged": staged_count,
        "staged_ids": staged_ids,
        "approved": approved_count,
        "approved_symbols": approved_symbols,
        "skipped": skipped[:20],
        "auto_approve": bool(settings.AURUM_AUTO_APPROVE),
    }


@router.get("/cron/hunt")
async def hunt_tick(authorization: Optional[str] = Header(None)):
    """
    Helm exit monitor — hard stop, take-profit, and trailing ratchet.

    Live mode creates a Ready-for-Approval EXIT idea. It does not place a
    broker order. Paper mode (PAPER_TRADING=1) auto-approves and simulates
    the sell. Still gated by AURUM_AGENTS_ENABLED.

    The same tick records Helm profit notifications (first green, take-profit
    waiting, profitable fill). Those rows are not broker orders. On Vercel
    Hobby this cron runs once a day; the open app also scans while it is on screen.
    """
    _verify_cron_secret(authorization)

    # Global kill switch
    if not settings.AURUM_AGENTS_ENABLED:
        return {"status": "disabled", "reason": "AURUM_AGENTS_ENABLED=false"}

    # Same pause flag as scout. A paused fleet must not even propose exits.
    # Profit pings are a separate read: they do not propose or send a sell.
    if agent_registry.is_paused():
        agent_registry.record_action("exit_brackets", "Paused — exit check skipped. No EXIT idea staged.")
        profit = {"created": 0, "source": "rate_limited"}
        if _check_rate_limit("hunt_profit", 110):
            profit = await _record_profit_notifications()
        return {
            "status": "paused",
            "reason": "AURUM_AGENTS_PAUSED or registry pause",
            "profit_notifications": profit,
        }

    # Rate limit
    if not _check_rate_limit("hunt", min_interval_seconds=110):  # 110s min
        return {"status": "skipped", "reason": "rate_limited"}

    logger.info("──── HUNT TICK (exit brackets) ────")

    symbols: list[str] = []
    try:
        with Session(engine) as session:
            ensure_brackets(session)
            session.commit()
            rows = session.exec(
                select(ExitBracket).where(ExitBracket.status.in_(ACTIVE_STATUSES))  # type: ignore[attr-defined]
            ).all()
            symbols = sorted({row.symbol for row in rows if row.symbol})
    except Exception as exc:
        logger.error("Failed to list exit brackets: %s", exc)
        return {"status": "error", "reason": str(exc)}

    bids: dict[str, float] = {}
    for symbol in symbols:
        try:
            bid = extract_bid(await rx.get_ticker(symbol))
        except Exception as exc:  # noqa: BLE001
            logger.warning("  %s: ticker fetch failed: %s", symbol, exc)
            continue
        if bid is None:
            logger.warning("  %s: no bid", symbol)
            continue
        bids[symbol] = bid

    summary = None
    monitor_error = None
    try:
        with Session(engine) as session:
            summary = await monitor_brackets(
                session,
                bids,
                paper=settings.PAPER_TRADING,
            )
    except Exception as exc:
        logger.error("Exit monitor failed: %s", exc)
        monitor_error = str(exc)

    profit = await _record_profit_notifications(bids)
    if monitor_error or summary is None:
        return {"status": "error", "reason": monitor_error or "exit monitor failed", "profit_notifications": profit}

    logger.info(
        "Hunt mode=%s checked=%s proposed=%s paper_closed=%s broker_orders=%s profit_pings=%s",
        summary["mode"],
        summary["checked"],
        len(summary["proposed"]),
        len(summary["paper_closed"]),
        summary["broker_orders_placed"],
        profit.get("created"),
    )
    agent_registry.record_action(
        "exit_brackets",
        (
            f"Checked {summary.get('checked', 0)} bracket(s). "
            f"EXIT ideas proposed: {len(summary.get('proposed') or [])}."
        ),
    )
    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profit_notifications": profit,
        **summary,
    }


async def _record_profit_notifications(bids: Optional[dict] = None) -> dict:
    """Persist Helm profit pings from live holdings or the bids already fetched.

    Never places, cancels, or modifies a broker order.
    """
    from api.services.profit_notifications import scan_profits

    try:
        with Session(engine) as session:
            return await scan_profits(session, bids=bids)
    except Exception as exc:
        logger.warning("Profit notification scan failed: %s", type(exc).__name__)
        return {"created": 0, "source": "error"}
