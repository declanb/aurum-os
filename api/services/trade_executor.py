"""
Trade execution service \u2014 places, cancels, and inspects orders on the
Revolut X spot exchange via the `revx` CLI wrapper.

Direction semantics:
  LONG  \u2192 buy   base currency (BTC in BTC-USD)
  SHORT \u2192 sell  base currency

Volume is interpreted as the base-asset quantity (e.g. 0.001 BTC).
For market buys you may instead pass `quote_amount` in api/routers to spend N USD.

ALL CALLERS must validate via Guardian + ApprovalEvent before invoking.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.services import revolut_x_client as rx
from api.services.revolut_x_client import RevolutXError

logger = logging.getLogger(__name__)


def _side_for(direction: str) -> str:
    d = direction.upper()
    if d == "LONG":
        return "buy"
    if d == "SHORT":
        return "sell"
    raise ValueError(f"Invalid direction: {direction}. Must be LONG or SHORT.")


async def execute_trade(
    symbol: str,
    direction: str,
    volume: float,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,  # noqa: ARG001  (no native SL/TP on spot)
    take_profit: Optional[float] = None,  # noqa: ARG001
    comment: str = "AURUM OS",
    *,
    post_only: bool = False,
    client_order_id: Optional[str] = None,
) -> dict:
    """Place a spot order on Revolut X.

    `stop_loss` and `take_profit` are accepted for API compatibility with the
    legacy Vantage executor but are silently ignored \u2014 Revolut X spot does not
    support attached protective orders. Use bracket logic in your strategy layer.
    """
    side = _side_for(direction)
    is_market = not entry_price or entry_price == 0
    coid = client_order_id or comment

    try:
        result = await rx.place_order(
            symbol=symbol,
            side=side,
            qty=volume,
            limit_price=None if is_market else entry_price,
            market=is_market,
            post_only=post_only and not is_market,
            client_order_id=coid,
        )
    except RevolutXError as exc:
        logger.error("Revolut X order placement failed: %s", exc)
        return {
            "success": False,
            "order_id": None,
            "string_code": "REVX_ERROR",
            "numeric_code": exc.returncode,
            "message": str(exc),
        }

    order = result[0] if isinstance(result, list) and result else (result if isinstance(result, dict) else {})
    state = (order.get("state") or order.get("status") or "").upper()
    success = state in {"NEW", "PARTIALLY_FILLED", "FILLED", "PENDING", "ACCEPTED"}

    logger.info(
        "Revolut X order placed: %s %s %s qty=%s state=%s id=%s",
        direction, symbol, "MARKET" if is_market else f"LIMIT@{entry_price}",
        volume, state, order.get("id"),
    )

    return {
        "success": success,
        "order_id": order.get("id"),
        "client_order_id": order.get("clientOrderId") or coid,
        "string_code": state or "UNKNOWN",
        "numeric_code": 0 if success else 1,
        "message": order.get("reason") or order.get("rejectReason") or "",
        "raw": order,
    }


async def get_positions() -> list[dict]:
    """Revolut X is spot \u2014 there are no positions, only balances.

    We synthesise "positions" from non-zero crypto balances so the existing
    Aurum UI keeps working without modification.
    """
    balances = await rx.get_balances(include_zero=False)
    rows = balances if isinstance(balances, list) else []
    return [
        {
            "id": b.get("currency"),
            "symbol": f"{b.get('currency')}-USD",
            "type": "POSITION_TYPE_BUY",
            "direction": "LONG",
            "volume": float(b.get("total") or b.get("balance") or 0),
            "open_price": None,
            "current_price": None,
            "stop_loss": None,
            "take_profit": None,
            "profit": None,
            "swap": 0,
            "commission": 0,
            "comment": "spot balance",
            "open_time": None,
        }
        for b in rows
        if (b.get("currency") or "").upper() not in {"USD", "EUR", "GBP"}
        and float(b.get("total") or b.get("balance") or 0) > 0
    ]


async def get_orders() -> list[dict]:
    """List all open (active) orders on the Revolut X account."""
    raw = await rx.list_open_orders()
    orders = raw if isinstance(raw, list) else []
    return [
        {
            "id": o.get("id"),
            "symbol": o.get("symbol") or o.get("pair"),
            "type": (o.get("side") or "").upper(),
            "volume": float(o.get("quantity") or o.get("qty") or 0),
            "open_price": float(o.get("price") or o.get("limitPrice") or 0) or None,
            "stop_loss": None,
            "take_profit": None,
            "comment": o.get("clientOrderId", ""),
            "time": o.get("createdAt") or o.get("timestamp"),
        }
        for o in orders
    ]


async def close_position(position_id: str) -> dict:
    """For a spot balance, "closing" means selling the entire base balance at market."""
    balances = await rx.get_balances(currency=position_id)
    row = (balances[0] if isinstance(balances, list) and balances else balances) or {}
    available = float(row.get("available") or 0)
    if available <= 0:
        return {"success": False, "string_code": "NO_BALANCE", "numeric_code": 1, "message": f"No available {position_id} to sell."}

    symbol = f"{position_id}-USD"
    try:
        result = await rx.place_order(symbol=symbol, side="sell", qty=available, market=True, client_order_id=f"AURUM-CLOSE-{position_id}")
    except RevolutXError as exc:
        return {"success": False, "string_code": "REVX_ERROR", "numeric_code": exc.returncode, "message": str(exc)}

    order = result[0] if isinstance(result, list) and result else (result if isinstance(result, dict) else {})
    state = (order.get("state") or order.get("status") or "").upper()
    success = state in {"NEW", "PARTIALLY_FILLED", "FILLED", "PENDING", "ACCEPTED"}
    logger.info("Closed spot balance %s qty=%s state=%s", position_id, available, state)
    return {
        "success": success,
        "string_code": state or "UNKNOWN",
        "numeric_code": 0 if success else 1,
        "message": order.get("reason") or "",
    }


async def modify_position(
    position_id: str,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> dict:
    """Revolut X spot does not support attached SL/TP on a position.

    To "modify" you must replace the resting limit order via `cancel_order` +
    `place_order`, or use revolut_x_client.replace_order on an open order.
    """
    return {
        "success": False,
        "string_code": "NOT_SUPPORTED",
        "numeric_code": 1,
        "message": (
            "Revolut X spot does not support modifying SL/TP on a held position. "
            "Use the orders endpoint to replace a resting limit order, or implement "
            "bracket logic in the strategy layer."
        ),
    }
