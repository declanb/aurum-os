"""
Profit Hunter Agent — local poller for a held spot position.

The durable exit path is the Helm bracket monitor (`/api/cron/hunt` and
`api.services.exit_bracket`). This CLI is the same idea for one position:

  1. Polls Revolut X for the live bid.
  2. When --entry-price, --stop-price, and --target-price are set, applies the
     Helm ratchet (hard stop, take-profit, trailing stop).
  3. Otherwise watches the legacy euro profit floor.
  4. Live mode logs the signal and does NOT place a broker order. Approve the
     EXIT idea, then execute it. Paper mode (PAPER_TRADING=1) simulates the sell.

Usage:
    python -m api.services.profit_hunter \
        --symbol BTC-EUR \
        --qty 0.00003443 \
        --cost-eur 2.00 \
        --entry-price 60000 \
        --stop-price 58000 \
        --target-price 65000 \
        --poll-secs 5
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

from api.core.config import settings
from api.services import revolut_x_client as rx
from api.services import agent_registry
from api.services import trade_executor
from api.services.exit_bracket import evaluate_long_bracket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("profit_hunter")

TAKER_FEE_PCT = 0.0009  # 0.09% Revolut X taker fee


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _notify_macos(title: str, message: str, sound: str = "Glass") -> None:
    """Fire a macOS desktop notification via osascript. Silent on non-Mac / failure."""
    try:
        import subprocess
        # Escape double-quotes for AppleScript
        safe_title = title.replace('"', "'")
        safe_msg = message.replace('"', "'")
        script = (
            f'display notification "{safe_msg}" with title "{safe_title}" sound name "{sound}"'
        )
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Notification failed (non-fatal): %s", exc)


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
    entry_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    target_price: Optional[float] = None,
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
    agent_registry.record_action(
        agent_id,
        f"Watching {symbol} for a bracket or profit-floor exit. Live mode does not sell.",
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
    use_bracket = (
        entry_price is not None and stop_price is not None and target_price is not None
    )
    trail_stop = float(stop_price) if stop_price is not None else None
    trail_high = float(entry_price) if entry_price is not None else 0.0

    try:
        while elapsed < max_runtime_secs:
            # Heartbeat every ~60s
            if heartbeat_counter >= (60 / poll_secs):
                agent_registry.heartbeat(agent_id)
                agent_registry.record_action(
                    agent_id,
                    (
                        f"Watching {symbol}. Last bid €{best_bid_seen:,.2f}."
                        if best_bid_seen
                        else f"Watching {symbol}. Waiting for a bid."
                    ),
                )
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

            # TRIGGER — bracket levels outrank the euro profit floor.
            trigger = None
            if use_bracket and trail_stop is not None and entry_price is not None and stop_price is not None and target_price is not None:
                view = evaluate_long_bracket(
                    entry_price=float(entry_price),
                    initial_stop=float(stop_price),
                    stop_price=trail_stop,
                    target_price=float(target_price),
                    high_water=trail_high,
                    bid=bid,
                )
                trail_stop = view.stop_price
                trail_high = view.high_water_price
                if view.action != "hold":
                    trigger = view.action
                    logger.info(
                        "Bracket %s bid=%s stop=%s trail=%s",
                        view.action, bid, view.stop_price, view.trail_armed,
                    )
            if trigger is None and pnl >= min_profit_eur:
                trigger = "profit_floor"
                logger.info("Profit floor hit: €%+.4f (threshold €%+.4f)", pnl, min_profit_eur)

            if trigger:
                agent_registry.record_action(
                    agent_id,
                    f"Exit signal {trigger} on {symbol} at bid {bid}. Live mode does not sell.",
                )
                result = await _execute_sell(symbol, qty, expected_bid=bid)
                result["trigger"] = trigger
                agent_registry.unregister(agent_id)
                return result

            await asyncio.sleep(poll_secs)
            elapsed += poll_secs

        logger.warning(f"⏰ Timeout after {max_runtime_secs}s — no fill")
        return {"success": False, "reason": "timeout", "polls": poll_count, "best_bid": best_bid_seen}
    finally:
        agent_registry.unregister(agent_id)


async def _execute_sell(symbol: str, qty: float, expected_bid: float) -> dict:
    """Signal a spot sell. Live broker orders are not placed from this agent.

    Paper mode simulates the fill through trade_executor. Live mode returns
    ``hitl_required`` so a human ApprovalEvent stays in front of the broker.
    """
    base = symbol.split("-")[0]
    if not settings.PAPER_TRADING:
        logger.warning(
            "HITL exit signal for %s qty=%s bid=%s — live sell not sent. "
            "Approve the EXIT idea, then execute from Approvals.",
            symbol, qty, expected_bid,
        )
        _notify_macos(
            title=f"Helm: exit signal {base}",
            message="Live sell needs approval. No broker order was sent.",
        )
        return {
            "success": False,
            "reason": "hitl_required",
            "expected_bid": expected_bid,
            "symbol": symbol,
            "qty": qty,
        }

    try:
        result = await trade_executor.execute_trade(
            symbol=symbol,
            direction="LONG",
            side="sell",
            volume=qty,
            comment=f"PAPER-HUNT-{base}",
            client_order_id=f"PAPER-HUNT-{base}",
        )
        logger.info("Paper sell result: %s", json.dumps(result, default=str))
        raw = result.get("raw") or {}
        fill_price = raw.get("avg_fill_price") or expected_bid
        filled_qty = raw.get("filled_quantity") or qty
        _notify_macos(
            title=f"Helm: paper sell {base}",
            message=f"Simulated {filled_qty} {base} @ {fill_price}",
        )
        return {
            "success": bool(result.get("success")),
            "order": result,
            "fill_price": fill_price,
            "filled_qty": filled_qty,
            "paper": True,
        }
    except Exception as exc:
        logger.error("Paper sell failed: %s", exc)
        return {"success": False, "reason": str(exc), "paper": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous profit-taking agent for Revolut X")
    parser.add_argument("--symbol", default="BTC-EUR", help="Trading pair (default: BTC-EUR)")
    parser.add_argument("--qty", type=float, required=True, help="Quantity of base currency to sell")
    parser.add_argument("--cost-eur", type=float, required=True, help="Original purchase cost in EUR")
    parser.add_argument("--min-profit-eur", type=float, default=0.01, help="Legacy euro profit floor (default: €0.01)")
    parser.add_argument("--entry-price", type=float, default=None, help="Fill price used as R for the trailing ratchet")
    parser.add_argument("--stop-price", type=float, default=None, help="Hard stop from the approved idea")
    parser.add_argument("--target-price", type=float, default=None, help="Take-profit from the approved idea")
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
        entry_price=args.entry_price,
        stop_price=args.stop_price,
        target_price=args.target_price,
    ))

    if result.get("success"):
        logger.info("Paper exit filled.")
        sys.exit(0)
    if result.get("reason") == "hitl_required":
        logger.warning("Exit signal only. No live broker order was sent.")
        sys.exit(0)
    logger.warning("Agent exited without selling: %s", result.get("reason"))
    sys.exit(1)


if __name__ == "__main__":
    main()
