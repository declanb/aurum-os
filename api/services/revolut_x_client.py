"""
Revolut X client — thin async subprocess wrapper around the official
`revx` CLI (https://github.com/revolut-engineering/revolut-x-api).

The CLI handles Ed25519 signing, key loading from ~/.config/revolut-x/,
and request idempotency. We just shell out, parse JSON, and surface errors.

All write operations (order place/cancel/replace) MUST be gated by
Guardian + ApprovalEvent at the caller layer — this module is unaware
of approvals on purpose, so it can also be used for read-only ops.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any, Optional

logger = logging.getLogger(__name__)

REVX_BIN = shutil.which("revx") or "revx"


class RevolutXError(RuntimeError):
    """Raised when the `revx` CLI exits non-zero or returns unparseable output."""

    def __init__(self, message: str, *, command: list[str], stdout: str, stderr: str, returncode: int):
        super().__init__(message)
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


async def _run(*args: str, timeout: float = 30.0) -> Any:
    """Run `revx <args> --json` and return parsed JSON.

    Adds --json automatically if not already present.
    Raises RevolutXError on non-zero exit or unparseable output.
    """
    argv: list[str] = [REVX_BIN, *args]
    if "--json" not in argv:
        argv.append("--json")

    logger.debug("revx exec: %s", " ".join(argv))

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RevolutXError(
            f"revx timed out after {timeout}s",
            command=argv, stdout="", stderr="", returncode=-1,
        )

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        raise RevolutXError(
            f"revx exited {proc.returncode}: {stderr or stdout}",
            command=argv, stdout=stdout, stderr=stderr, returncode=proc.returncode or 1,
        )

    if not stdout:
        return None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RevolutXError(
            f"revx returned non-JSON output: {exc}",
            command=argv, stdout=stdout, stderr=stderr, returncode=0,
        )
    # revx wraps most responses in {"data": ..., "metadata": {...}}.
    # Some commands (e.g. account balances) return a bare list. Unwrap if data envelope is present.
    if isinstance(parsed, dict) and "data" in parsed and isinstance(parsed["data"], (list, dict)):
        return parsed["data"]
    return parsed


# ── Connection / Auth ─────────────────────────────────────────────────────

async def get_status() -> dict:
    """Lightweight liveness check — calls `revx account balances --all`.

    Returns connection metadata or an error envelope. Never raises.
    """
    try:
        data = await _run("account", "balances", "--all", timeout=10.0)
        return {
            "connected": True,
            "status": "OK",
            "broker": "Revolut X",
            "currencies": len(data) if isinstance(data, list) else 0,
        }
    except RevolutXError as exc:
        logger.warning("Revolut X status check failed: %s", exc)
        return {
            "connected": False,
            "status": "ERROR",
            "broker": "Revolut X",
            "message": str(exc),
        }


# ── Account ──────────────────────────────────────────────────────────────

async def get_balances(currency: Optional[str] = None, include_zero: bool = False) -> Any:
    args = ["account", "balances"]
    if currency:
        args.append(currency)
    if include_zero:
        args.append("--all")
    return await _run(*args)


# ── Market Data ──────────────────────────────────────────────────────────

async def get_ticker(symbol: str = "BTC-USD") -> Any:
    return await _run("market", "tickers", symbol)


async def get_candles(symbol: str = "BTC-USD", interval: str = "60", since: Optional[str] = None) -> Any:
    args = ["market", "candles", symbol, "--interval", interval]
    if since:
        args.extend(["--since", since])
    return await _run(*args)


async def get_orderbook(symbol: str = "BTC-USD", limit: int = 10) -> Any:
    return await _run("market", "orderbook", symbol, "--limit", str(limit))


async def get_pair(symbol: str = "BTC-USD") -> Any:
    return await _run("market", "pairs", "--filter", symbol)


# ── Orders (write — caller must enforce Guardian approval) ───────────────

async def place_order(
    symbol: str,
    side: str,
    *,
    qty: Optional[float] = None,
    quote: Optional[float] = None,
    limit_price: Optional[float] = None,
    market: bool = False,
    post_only: bool = False,
    client_order_id: Optional[str] = None,
) -> Any:
    """Place an order via `revx order place`.

    Provide exactly one of qty/quote, and exactly one of market/limit_price.
    Caller MUST have already validated via Guardian + ApprovalEvent.
    """
    side = side.lower()
    if side not in {"buy", "sell"}:
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    if (qty is None) == (quote is None):
        raise ValueError("provide exactly one of qty or quote")
    if market == (limit_price is not None):
        raise ValueError("provide exactly one of market=True or limit_price")

    args: list[str] = ["order", "place", symbol, side]
    if qty is not None:
        args.extend(["--qty", str(qty)])
    if quote is not None:
        args.extend(["--quote", str(quote)])
    if market:
        args.append("--market")
    else:
        args.extend(["--limit", str(limit_price)])
    if post_only:
        args.append("--post-only")
    if client_order_id:
        args.extend(["--client-order-id", client_order_id])

    logger.info("Placing Revolut X order: %s", " ".join(args))
    return await _run(*args)


async def get_order(order_id: str) -> Any:
    return await _run("order", "get", order_id)


async def get_order_fills(order_id: str) -> Any:
    return await _run("order", "fills", order_id)


async def list_open_orders(symbol: Optional[str] = None) -> Any:
    args = ["order", "open"]
    if symbol:
        args.extend(["--symbols", symbol])
    return await _run(*args)


async def list_order_history(symbol: Optional[str] = None) -> Any:
    args = ["order", "history"]
    if symbol:
        args.extend(["--symbols", symbol])
    return await _run(*args)


async def cancel_order(order_id: str) -> Any:
    return await _run("order", "cancel", order_id)


async def cancel_all_orders() -> Any:
    return await _run("order", "cancel", "--all")


async def replace_order(
    order_id: str,
    *,
    limit_price: Optional[float] = None,
    qty: Optional[float] = None,
    quote: Optional[float] = None,
) -> Any:
    if all(v is None for v in (limit_price, qty, quote)):
        raise ValueError("replace_order requires at least one of limit_price, qty, quote")
    args: list[str] = ["order", "replace", order_id]
    if limit_price is not None:
        args.extend(["--price", str(limit_price)])
    if qty is not None:
        args.extend(["--qty", str(qty)])
    if quote is not None:
        args.extend(["--quote", str(quote)])
    return await _run(*args)
