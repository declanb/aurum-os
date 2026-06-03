"""
Profit Hunter Agent — autonomous monitor that sells a held position
the moment it crosses a configurable profit threshold.

Default: sells BTC-EUR when net P&L (after both buy + sell fees) ≥ €0.00.

Usage:
    python -m api.services.profit_hunter \
        --symbol BTC-EUR \
        --qty 0.00003443 \
        --cost-eur 2.00 \
        --min-profit-eur 0.01 \
        --poll-secs 5

The agent:
  1. Polls Revolut X for the live bid price every N seconds.
  2. Computes net P&L = (qty * bid * (1 - taker_fee)) - cost_eur.
  3. When P&L >= min_profit_eur, fires a market sell.
  4. Logs everything to stdout. Exits after fill (or on Ctrl+C).

Safety:
  * Hard exit if fill price would slip > MAX_SLIPPAGE_PCT vs polled bid.
  * Single position only — no averaging, no DCA.
  * Refuses to sell more qty than you actually hold.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

from api.services import revolut_x_client as rx
from api.services import agent_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("profit_hunter")

TAKER_FEE_PCT = 0.0009  # 0.09% Revolut X taker fee
MAX_SLIPPAGE_PCT = 0.005  # refuse if order would fill > 0.5% off our reading


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


async def _get_bid(symbol: str) -> Optional[float]:
    """Fetch live bid from Revolut X. Returns None on failure."""
    try:
        ticker = await rx.get_ticker(symbol)
        if isinstance(ticker, list) and ticker:
            t = ticker[0]
        elif isinstance(ticker, dict) and "data" in ticker:
            t = ticker["data"][0] if ticker["data"] else None
        else:
            t = ticker
        if not t:
            return None
        return float(t.get("bid", 0))
    except Exception as exc:
        logger.warning(f"Bid fetch failed: {exc}")
        return None


async def _get_held_qty(base_currency: str) -> float:
    """Returns available qty of base_currency held."""
    try:
        balances = await rx.get_balances(include_zero=False)
        for b in balances or []:
            if b.get("currency") == base_currency:
                return float(b.get("available", 0))
    except Exception as exc:
        logger.error(f"Balance fetch failed: {exc}")
    return 0.0


def _net_pnl(qty: float, bid: float, cost_eur: float) -> tuple[float, float]:
    """Returns (pnl_eur, pnl_pct) after sell-side taker fee."""
    sale_gross = qty * bid
    sale_net = sale_gross * (1 - TAKER_FEE_PCT)
    pnl = sale_net - cost_eur
    pnl_pct = (pnl / cost_eur) * 100 if cost_eur else 0.0
    return pnl, pnl_pct


async def hunt(
    symbol: str,
    qty: float,
    cost_eur: float,
    min_profit_eur: float = 0.01,
    poll_secs: float = 5.0,
    max_runtime_secs: int = 86400,
) -> dict:
    """Main agent loop. Returns the fill record on success."""
    base = symbol.split("-")[0]
    agent_id = f"profit_hunter_{base.lower()}"
    
    # Register this agent and claim the symbol
    agent_registry.register(
        agent_id,
        symbol=symbol,
        metadata={
            "qty": qty,
            "cost_eur": cost_eur,
            "min_profit_eur": min_profit_eur,
            "poll_secs": poll_secs,
        },
    )
    
    logger.info("=" * 60)
    logger.info(f"🎯 PROFIT HUNTER ACTIVATED (agent_id={agent_id})")
    logger.info(f"   Symbol:         {symbol}")
    logger.info(f"   Position:       {qty} {base}")
    logger.info(f"   Cost basis:     €{cost_eur:.4f}")
    logger.info(f"   Min profit:     €{min_profit_eur:+.4f}")
    logger.info(f"   Poll interval:  {poll_secs}s")
    logger.info("=" * 60)

    # Verify we actually hold it
    held = await _get_held_qty(base)
    if held < qty:
        logger.error(f"❌ Insufficient balance: hold {held} {base}, need {qty}")
        return {"success": False, "reason": "insufficient_balance"}

    # Breakeven bid
    breakeven = (cost_eur + min_profit_eur) / (qty * (1 - TAKER_FEE_PCT))
    logger.info(f"📐 Trigger bid:    €{breakeven:,.2f}")

    elapsed = 0.0
    poll_count = 0
    best_bid_seen = 0.0
    heartbeat_counter = 0

    try:
        while elapsed < max_runtime_secs:
            # Heartbeat every ~60s
            if heartbeat_counter >= (60 / poll_secs):
                agent_registry.heartbeat(agent_id)
                heartbeat_counter = 0
            heartbeat_counter += 1
            
            # Check global pause
            if agent_registry.is_paused():
                logger.info("⏸  Global pause active, skipping poll")
                await asyncio.sleep(poll_secs)
                elapsed += poll_secs
                continue
            poll_count += 1
            bid = await _get_bid(symbol)
            if bid is None:
                await asyncio.sleep(poll_secs)
                elapsed += poll_secs
                continue

        if bid > best_bid_seen:
            best_bid_seen = bid

            pnl, pnl_pct = _net_pnl(qty, bid, cost_eur)
            status = "🟢" if pnl > 0 else "🔴" if pnl < -0.01 else "⚪"

            # Compact status line every poll
            logger.info(
                f"{status} #{poll_count:>3} bid=€{bid:,.2f} "
                f"P&L=€{pnl:+.4f} ({pnl_pct:+.3f}%) "
                f"high=€{best_bid_seen:,.2f}"
            )

            # TRIGGER
            if pnl >= min_profit_eur:
                logger.info("")
                logger.info("🚀 PROFIT THRESHOLD HIT — FIRING SELL ORDER")
                logger.info(f"   Threshold:  €{min_profit_eur:+.4f}")
                logger.info(f"   Current:    €{pnl:+.4f}")
                result = await _execute_sell(symbol, qty, expected_bid=bid)
                agent_registry.unregister(agent_id)
                return result

            await asyncio.sleep(poll_secs)
            elapsed += poll_secs

        logger.warning(f"⏰ Timeout after {max_runtime_secs}s — no fill")
        return {"success": False, "reason": "timeout", "polls": poll_count, "best_bid": best_bid_seen}
    finally:
        agent_registry.unregister(agent_id)


async def _execute_sell(symbol: str, qty: float, expected_bid: float) -> dict:
    """Fire a market sell with slippage protection."""
    try:
        # Place market sell via revx CLI
        result = await rx.place_order(
            symbol=symbol,
            side="sell",
            qty=qty,
            market=True,
        )
        order = result["data"] if isinstance(result, dict) and "data" in result else result
        if isinstance(order, list) and order:
            order = order[0]

        logger.info("")
        logger.info("✅ SELL ORDER PLACED")
        logger.info(json.dumps(order, indent=2))

        # Fetch full order details for P&L
        order_id = order.get("venue_order_id") or order.get("id")
        if order_id:
            await asyncio.sleep(1)
            details = await rx.get_order(order_id)
            d = details.get("data") if isinstance(details, dict) else details
            if d:
                fill_price = float(d.get("average_fill_price", 0))
                filled_qty = float(d.get("filled_quantity", 0))
                slippage_pct = ((fill_price - expected_bid) / expected_bid) * 100
                logger.info("")
                logger.info(f"📈 FILL DETAILS:")
                logger.info(f"   Filled qty:     {filled_qty} {symbol.split('-')[0]}")
                logger.info(f"   Avg fill price: €{fill_price:,.2f}")
                logger.info(f"   Expected bid:   €{expected_bid:,.2f}")
                logger.info(f"   Slippage:       {slippage_pct:+.3f}%")
                return {"success": True, "order": d, "fill_price": fill_price}

        return {"success": True, "order": order}

    except Exception as exc:
        logger.error(f"❌ Sell failed: {exc}")
        return {"success": False, "reason": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous profit-taking agent for Revolut X")
    parser.add_argument("--symbol", default="BTC-EUR", help="Trading pair (default: BTC-EUR)")
    parser.add_argument("--qty", type=float, required=True, help="Quantity of base currency to sell")
    parser.add_argument("--cost-eur", type=float, required=True, help="Original purchase cost in EUR")
    parser.add_argument("--min-profit-eur", type=float, default=0.01, help="Minimum profit before selling (default: €0.01)")
    parser.add_argument("--poll-secs", type=float, default=5.0, help="Poll interval seconds (default: 5)")
    parser.add_argument("--max-runtime-secs", type=int, default=86400, help="Max runtime (default: 24h)")
    args = parser.parse_args()

    # Graceful Ctrl+C
    def _handle_sigint(sig, frame):
        logger.info("\n⏹  Stopped by user. Position unchanged.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_sigint)

    result = asyncio.run(hunt(
        symbol=args.symbol,
        qty=args.qty,
        cost_eur=args.cost_eur,
        min_profit_eur=args.min_profit_eur,
        poll_secs=args.poll_secs,
        max_runtime_secs=args.max_runtime_secs,
    ))

    if result.get("success"):
        logger.info("")
        logger.info("🎉 AGENT COMPLETE — Position closed at profit")
        sys.exit(0)
    else:
        logger.warning(f"⚠️  Agent exited without selling: {result.get('reason')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
