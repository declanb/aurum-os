"""
Scout Agent — autonomous AI trade advisor that polls market data every N minutes,
generates recommendations through a selected trader lens, and auto-approves
high-confidence setups that match your personal edge.

Usage:
    python -m api.services.scout_agent \
        --playbook wyckoff \
        --symbols BTC-USD,ETH-USD,SOL-USD \
        --poll-minutes 15

The agent:
  1. Registers itself in the agent registry.
  2. Every N minutes:
     - Fetches AI recommendations (via ai_advisor).
     - Scores each against personal edge + auto-approve thresholds.
     - Creates + auto-approves TradeIdeas for winners (if not already claimed by profit_hunter).
  3. Logs to /tmp/scout_agent.log.
  4. Honors global pause flag and daily caps.
  5. Heartbeats every 60s.

Safety:
  - Refuses to auto-approve symbols already claimed by profit_hunter.
  - Checks EUR balance before attempting any approval.
  - Enforces daily cap (AUTO_APPROVE_MAX_PER_DAY).
  - Clean shutdown on SIGINT/SIGTERM (unregisters).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from api.core.config import settings
from api.core.db import engine
from api.services import agent_registry, ai_advisor, auto_approver
from api.services.personal_edge import compute_edge_fingerprint

# Logging setup
log_path = Path("/tmp/scout_agent.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("scout_agent")

AGENT_ID = "scout"
running = True


def _signal_handler(sig, frame):
    global running
    logger.info("Received signal %s, shutting down...", sig)
    running = False


async def scout_loop(playbook_id: str, symbols: list[str], poll_minutes: int) -> None:
    """Main agent loop."""
    global running
    
    # Register
    agent_registry.register(
        AGENT_ID,
        symbol=None,  # scout doesn't claim a specific symbol
        metadata={
            "playbook": playbook_id,
            "symbols": symbols,
            "poll_minutes": poll_minutes,
        },
    )
    logger.info("Scout agent started (playbook=%s, symbols=%s, poll=%dm)", playbook_id, symbols, poll_minutes)
    
    iteration = 0
    heartbeat_counter = 0
    
    try:
        while running:
            iteration += 1
            heartbeat_counter += 1
            
            # Heartbeat every ~60s (poll loop is much longer, so we do it per iteration)
            if heartbeat_counter >= 1:
                agent_registry.heartbeat(AGENT_ID)
                heartbeat_counter = 0
            
            # Check global pause
            if agent_registry.is_paused():
                logger.info("[Iter %d] Global pause active, skipping", iteration)
                await asyncio.sleep(60)
                continue
            
            # Check if auto-approve is enabled (scout still runs + stages either way)
            if not settings.AURUM_AUTO_APPROVE:
                logger.info("[Iter %d] AURUM_AUTO_APPROVE=False — will stage recs only, no auto-approval", iteration)
            
            logger.info("[Iter %d] ──── SCOUT RUN ────", iteration)
            
            # Fetch personal edge from DB
            try:
                with Session(engine) as session:
                    edge = compute_edge_fingerprint(session, user_id=None)
            except Exception as exc:
                logger.warning("Edge fingerprint unavailable: %s", exc)
                edge = None
            
            # Generate recommendations
            try:
                recs = await ai_advisor.generate_recommendations(
                    symbols=symbols,
                    max_recommendations=len(symbols),
                    playbook_id=playbook_id,
                    edge_fingerprint=edge,
                )
                logger.info("Generated %d recommendation(s)", len(recs))
            except Exception as exc:
                logger.error("Failed to generate recommendations: %s", exc)
                recs = []
            
            # Evaluate each
            approved_count = 0
            staged_count = 0
            for rec in recs:
                symbol = rec.get("symbol")

                # Pre-gate: don't act on symbols already claimed by another agent (e.g. profit_hunter)
                if agent_registry.is_symbol_claimed(symbol):
                    logger.info("  %s: SKIP (already claimed by another agent)", symbol)
                    continue

                # Always stage the rec into the approval queue so the human can see it.
                try:
                    with Session(engine) as session:
                        staged, stage_msg, staged_id = auto_approver.stage_recommendation(session, rec)
                        if staged:
                            logger.info("  %s: 📋 STAGED #%s (%s)", symbol, staged_id, stage_msg)
                            staged_count += 1
                        else:
                            logger.info("  %s: not staged (%s)", symbol, stage_msg)
                except Exception as exc:
                    logger.error("  %s: ERROR staging rec: %s", symbol, exc)

                # Then attempt auto-approve (flips status to Approved if all gates pass)
                eligible, reason = auto_approver.evaluate(rec, edge)
                if not eligible:
                    logger.info("  %s: AUTO-APPROVE skipped (%s)", symbol, reason)
                    continue

                try:
                    with Session(engine) as session:
                        approved, msg, trade_id = auto_approver.try_auto_approve(session, rec, edge)
                        if approved:
                            logger.info("  %s: ✅ AUTO-APPROVED trade #%s (%s)", symbol, trade_id, msg)
                            approved_count += 1
                        else:
                            logger.info("  %s: ❌ AUTO-APPROVE blocked (%s)", symbol, msg)
                except Exception as exc:
                    logger.error("  %s: ERROR during auto-approve: %s", symbol, exc)

            logger.info("[Iter %d] Staged %d, auto-approved %d", iteration, staged_count, approved_count)
            
            # Sleep until next poll
            logger.info("[Iter %d] Sleeping for %d minutes...\n", iteration, poll_minutes)
            
            # Sleep in chunks so we can respond to signals quickly
            for _ in range(poll_minutes * 60):
                if not running:
                    break
                await asyncio.sleep(1)
    
    finally:
        # Clean shutdown
        agent_registry.unregister(AGENT_ID)
        logger.info("Scout agent stopped")


def main():
    parser = argparse.ArgumentParser(description="Aurum Scout Agent — autonomous AI trade advisor")
    parser.add_argument("--playbook", default="trend_follower", help="Trader lens (wyckoff, ict_smc, trend_follower, macro, livermore, mean_reversion)")
    parser.add_argument("--symbols", default="BTC-USD,ETH-USD,SOL-USD", help="Comma-separated symbols to monitor")
    parser.add_argument("--poll-minutes", type=int, default=15, help="Poll interval in minutes")
    
    args = parser.parse_args()
    
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    
    if not symbols:
        logger.error("No symbols provided")
        sys.exit(1)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    # Run the loop
    try:
        asyncio.run(scout_loop(args.playbook, symbols, args.poll_minutes))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logger.exception("Scout agent crashed: %s", exc)
        agent_registry.unregister(AGENT_ID)
        sys.exit(1)


if __name__ == "__main__":
    main()
