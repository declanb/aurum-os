"""
Trade execution service \u2014 places, cancels, and inspects orders on the
Revolut X spot exchange via revolut_x_client (signed HTTP API, or the `revx` CLI).

Direction semantics:
  LONG  \u2192 buy   base currency (BTC in BTC-USD)
  SHORT \u2192 sell  base currency

Volume is interpreted as the base-asset quantity (e.g. 0.001 BTC).
For market buys you may instead pass `quote_amount` in api/routers to spend N USD.

ALL CALLERS must validate via Guardian + ApprovalEvent before invoking.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from api.core.config import settings
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


async def _paper_fill(
    symbol: str,
    side: str,
    qty: float,
    limit_price: Optional[float],
    is_market: bool,
    client_order_id: str,
) -> dict:
    """Simulate a fill against live mid-price. No broker call."""
    try:
        ticker = await rx.get_ticker(symbol)
        row = ticker[0] if isinstance(ticker, list) and ticker else (ticker or {})
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
        mid = float(row.get("mid") or 0)
        last = float(row.get("last_price") or row.get("last") or row.get("price") or 0)
        if mid:
            fill_price = mid
        elif bid and ask:
            fill_price = (bid + ask) / 2
        elif last:
            fill_price = last
        elif limit_price:
            fill_price = float(limit_price)
        else:
            fill_price = 0.0
    except Exception as exc:
        logger.warning("Paper fill: ticker lookup failed for %s (%s) — using limit price", symbol, exc)
        fill_price = float(limit_price or 0)

    # For LIMIT orders, only "fill" if mid crosses the limit (LONG fills at or below limit)
    if not is_market and limit_price:
        if side == "buy" and fill_price > float(limit_price) * 1.001:
            state = "PAPER_OPEN"  # rests, not crossed
            fill_price = 0.0
        elif side == "sell" and fill_price < float(limit_price) * 0.999:
            state = "PAPER_OPEN"
            fill_price = 0.0
        else:
            state = "PAPER_FILLED"
    else:
        state = "PAPER_FILLED"

    order_id = f"paper-{uuid.uuid4().hex[:12]}"
    logger.info(
        "📝 PAPER fill: %s %s qty=%s @ %s [%s] id=%s",
        side.upper(), symbol, qty, fill_price, state, order_id,
    )
    return {
        "id": order_id,
        "clientOrderId": client_order_id,
        "state": state,
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "filled_quantity": qty if state == "PAPER_FILLED" else 0,
        "avg_fill_price": fill_price if state == "PAPER_FILLED" else None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "paper": True,
    }


def paper_fill_from_result(result: dict) -> Optional[dict]:
    """Normalise a paper execute_trade result. Returns None for live results."""
    if not isinstance(result, dict):
        return None
    raw = result.get("raw") or {}
    if not isinstance(raw, dict):
        raw = {}
    code = str(result.get("string_code") or "").upper()
    if not (raw.get("paper") or code.startswith("PAPER")):
        return None
    state = str(raw.get("state") or code).upper()
    filled = state == "PAPER_FILLED" or code == "PAPER_FILLED"
    qty = raw.get("filled_quantity")
    price = raw.get("avg_fill_price")
    return {
        "paper": True,
        "filled": filled,
        "adapter_status": "PaperFilled" if filled else "PaperOpen",
        "fill_qty": float(qty) if qty else None,
        "fill_price": float(price) if price else None,
        "fees_eur": 0.0,
        "state": state,
        "error": None,
    }


async def execute_trade(
    symbol: str,
    direction: str,
    volume: float,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    comment: str = "AURUM OS",
    *,
    post_only: bool = False,
    client_order_id: Optional[str] = None,
    quote_eur: Optional[float] = None,
    side: Optional[str] = None,
) -> dict:
    """Place a spot order on Revolut X.

    Pass `quote_eur` to spend a fixed EUR amount (preferred for retail €-budget
    trading); otherwise `volume` is interpreted as base-asset quantity.

    `stop_loss` and `take_profit` are accepted for API compatibility but are
    not attached to the order. Revolut X spot has no native protective orders.
    Helm exit brackets (api.services.exit_bracket) own those exits after a fill.

    Pass `side="sell"` to close a spot long. Otherwise side is derived from
    direction (LONG → buy, SHORT → sell).

    When settings.PAPER_TRADING is true, the order is simulated against live
    mid-price and no real broker call is made.
    """
    if stop_loss is not None or take_profit is not None:
        logger.info(
            "stop_loss=%s take_profit=%s are not attached on Revolut X spot; "
            "ExitBracket owns protective exits for %s",
            stop_loss, take_profit, symbol,
        )
    if side:
        order_side = side.lower()
        if order_side not in {"buy", "sell"}:
            raise ValueError(f"Invalid side: {side}. Must be buy or sell.")
    else:
        order_side = _side_for(direction)
    is_market = not entry_price or entry_price == 0
    coid = client_order_id or comment
    use_quote = quote_eur is not None and quote_eur > 0 and order_side == "buy"

    # Paper-trading branch — simulate fill, never touch Revolut X
    if settings.PAPER_TRADING:
        order = await _paper_fill(
            symbol=symbol, side=order_side, qty=volume,
            limit_price=entry_price, is_market=is_market, client_order_id=coid,
        )
        state = order["state"]
        success = state in {"PAPER_FILLED", "PAPER_OPEN"}
        return {
            "success": success,
            "order_id": order["id"],
            "client_order_id": coid,
            "string_code": state,
            "numeric_code": 0 if success else 1,
            "message": "Paper trade — no broker call",
            "raw": order,
        }

    try:
        place_kwargs = dict(
            symbol=symbol,
            side=order_side,
            limit_price=None if is_market else entry_price,
            market=is_market,
            post_only=post_only and not is_market,
            client_order_id=coid,
        )
        if use_quote:
            place_kwargs["quote"] = quote_eur
        else:
            place_kwargs["qty"] = volume
        result = await rx.place_order(**place_kwargs)
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
    # pending_new is the exchange's "accepted, not yet on the book" state.
    success = state in {"NEW", "PENDING_NEW", "PARTIALLY_FILLED", "FILLED", "PENDING", "ACCEPTED", "OPEN"}

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


async def poll_for_fill(
    order_id: str,
    *,
    max_attempts: int = 8,
    delay_secs: float = 0.75,
) -> dict:
    """Poll `revx order get` until the order reaches a terminal state.

    Returns a normalised dict:
        {
            "order_id":   str,
            "state":      "FILLED" | "PARTIALLY_FILLED" | "CANCELLED" | "REJECTED" | "OPEN" | "UNKNOWN",
            "fill_qty":   float,    # base-asset filled
            "fill_price": float,    # avg fill price
            "fees_eur":   float,    # sum of fee amounts (best-effort, EUR)
            "raw":        dict,     # last order response
            "fills":      list,     # raw fills list
        }
    Never raises — on broker error returns success=False with state="UNKNOWN".
    """
    import asyncio

    terminal = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
    order: dict = {}
    state = "UNKNOWN"
    for attempt in range(max_attempts):
        try:
            resp = await rx.get_order(order_id)
            order = resp[0] if isinstance(resp, list) and resp else (resp if isinstance(resp, dict) else {})
            state = (order.get("state") or order.get("status") or "").upper()
        except RevolutXError as exc:
            logger.warning("poll_for_fill: get_order %s failed (attempt %d): %s", order_id, attempt + 1, exc)
        if state in terminal:
            break
        await asyncio.sleep(delay_secs)

    # Collect fills (best-effort)
    fills: list = []
    try:
        fr = await rx.get_order_fills(order_id)
        if isinstance(fr, list):
            fills = fr
        elif isinstance(fr, dict) and isinstance(fr.get("fills"), list):
            fills = fr["fills"]
    except RevolutXError as exc:
        logger.warning("poll_for_fill: get_order_fills %s failed: %s", order_id, exc)

    # Aggregate fill qty / price / fees from fills list if present, else from order summary
    def _f(v) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    fill_qty = 0.0
    notional = 0.0
    fees_eur = 0.0
    for f in fills:
        q = _f(f.get("quantity") or f.get("qty") or f.get("size") or f.get("filled_quantity"))
        p = _f(f.get("price") or f.get("avg_price") or f.get("fill_price"))
        fee = _f(f.get("fee") or f.get("fees") or f.get("commission"))
        fee_ccy = (f.get("fee_currency") or f.get("commission_currency") or "").upper()
        fill_qty += q
        notional += q * p
        if not fee_ccy or fee_ccy == "EUR":
            fees_eur += fee

    if fill_qty == 0:
        # Fall back to order-level summary fields
        fill_qty = _f(
            order.get("filled_quantity")
            or order.get("filledQuantity")
            or order.get("executed_qty")
        )
        avg = _f(
            order.get("avg_fill_price")
            or order.get("avgFillPrice")
            or order.get("average_price")
        )
        if fill_qty and avg:
            notional = fill_qty * avg
        order_fee = _f(order.get("fee") or order.get("fees"))
        fee_ccy = (order.get("fee_currency") or "").upper()
        if not fee_ccy or fee_ccy == "EUR":
            fees_eur = order_fee

    avg_price = (notional / fill_qty) if fill_qty else 0.0

    return {
        "order_id": order_id,
        "state": state or "UNKNOWN",
        "fill_qty": fill_qty,
        "fill_price": avg_price,
        "fees_eur": fees_eur,
        "raw": order,
        "fills": fills,
    }


async def resolve_fill(result: dict) -> dict:
    """Turn an execute_trade result into ticket fill fields.

    Paper results stay local. Live results poll the broker. On a poll error
    ``adapter_status`` is None so the caller can keep its provisional status.
    """
    paper = paper_fill_from_result(result)
    if paper:
        return paper
    if not result.get("success") or not result.get("order_id"):
        return {
            "paper": False,
            "filled": False,
            "adapter_status": "Rejected",
            "fill_qty": None,
            "fill_price": None,
            "fees_eur": None,
            "state": result.get("string_code") or "REJECTED",
            "error": None,
        }
    try:
        polled = await poll_for_fill(result["order_id"])
    except Exception as exc:  # noqa: BLE001
        return {
            "paper": False,
            "filled": False,
            "adapter_status": None,
            "fill_qty": None,
            "fill_price": None,
            "fees_eur": None,
            "state": None,
            "error": str(exc),
        }
    state = str(polled.get("state") or "").upper()
    status_map = {
        "FILLED": "Filled",
        "PARTIALLY_FILLED": "PartiallyFilled",
        "CANCELLED": "Cancelled",
        "REJECTED": "Rejected",
        "EXPIRED": "Expired",
        "NEW": "Open",
        "PENDING_NEW": "Open",
        "OPEN": "Open",
        "PENDING": "Open",
        "ACCEPTED": "Open",
    }
    # Unrecognised / empty poll states leave adapter_status unset so the caller
    # keeps the provisional status from order acceptance (same as before).
    adapter = status_map.get(state) if state and state != "UNKNOWN" else None
    return {
        "paper": False,
        "filled": state == "FILLED",
        "adapter_status": adapter,
        "fill_qty": polled.get("fill_qty") or None,
        "fill_price": polled.get("fill_price") or None,
        "fees_eur": polled.get("fees_eur"),
        "state": state,
        "error": None,
        "poll": polled,
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
    success = state in {"NEW", "PENDING_NEW", "PARTIALLY_FILLED", "FILLED", "PENDING", "ACCEPTED"}
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
            "Use the orders endpoint to replace a resting limit order. "
            "Protective exits live on the Helm ExitBracket (stop, target, trail)."
        ),
    }
