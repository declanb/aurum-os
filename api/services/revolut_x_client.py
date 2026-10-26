"""
Revolut X client.

Vercel has no ``revx`` binary. When ``REVX_API_KEY`` and an Ed25519 private
key are set, calls go to the Revolut X HTTP API (Ed25519 request signing).
Otherwise, if ``revx`` is on PATH, calls shell out to the CLI the same way
as before (local ``~/.config/revolut-x/`` keys).

All write operations (order place/cancel/replace) MUST be gated by
Guardian + ApprovalEvent at the caller layer — this module is unaware
of approvals on purpose, so it can also be used for read-only ops.
Spot only: buy and sell. No margin, leverage, or perps.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any, Optional

from api.services import revolut_x_http as http

logger = logging.getLogger(__name__)

REVX_BIN = shutil.which("revx") or "revx"

# Re-export so existing ``from api.services.revolut_x_client import RevolutXError`` keeps working.
RevolutXError = http.RevolutXError


def _revx_bin() -> Optional[str]:
    return shutil.which("revx")


def select_transport() -> str:
    """``http`` when env keys are set, otherwise ``cli`` when ``revx`` exists.

    ``REVX_TRANSPORT=http|cli`` forces one path. ``auto`` (default) prefers
    HTTP whenever both the API key and a private key are present.
    """
    mode = http.transport_preference()
    if mode == "http":
        if not http.credentials_configured():
            raise RevolutXError(
                "REVX_TRANSPORT=http requires REVX_API_KEY and REVX_PRIVATE_KEY "
                "(or REVX_PRIVATE_KEY_B64).",
                command=["http"],
                stdout="",
                stderr="",
                returncode=1,
            )
        return "http"
    if mode == "cli":
        if _revx_bin() is None:
            raise RevolutXError(
                "REVX_TRANSPORT=cli but the revx binary is not on PATH.",
                command=["revx"],
                stdout="",
                stderr="",
                returncode=127,
            )
        return "cli"
    if mode != "auto":
        raise RevolutXError(
            f"REVX_TRANSPORT must be auto, http, or cli (got {mode!r}).",
            command=["revx"],
            stdout="",
            stderr="",
            returncode=1,
        )
    if http.credentials_configured():
        return "http"
    if _revx_bin() is not None:
        return "cli"
    raise RevolutXError(
        "Revolut X is not configured. Set REVX_API_KEY and an Ed25519 private key "
        "(REVX_PRIVATE_KEY or REVX_PRIVATE_KEY_B64) for the HTTP API, or install the revx CLI.",
        command=["revx"],
        stdout="",
        stderr="",
        returncode=127,
    )


def _use_http() -> bool:
    return select_transport() == "http"


async def _run(*args: str, timeout: float = 30.0) -> Any:
    """Run ``revx <args> --json`` and return parsed JSON.

    Adds --json automatically if not already present.
    Raises RevolutXError on non-zero exit, a missing binary, or unparseable output.
    """
    bin_path = _revx_bin() or REVX_BIN
    argv: list[str] = [bin_path, *args]
    if "--json" not in argv:
        argv.append("--json")

    logger.debug("revx exec: %s", " ".join(argv))

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RevolutXError(
            "revx CLI not found on PATH",
            command=argv,
            stdout="",
            stderr="",
            returncode=127,
        ) from exc
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
    """Lightweight liveness check. Never raises.

    HTTP: ``GET /api/1.0/balances``. CLI: ``revx account balances --all``.
    """
    try:
        transport = select_transport()
    except RevolutXError as exc:
        logger.warning("Revolut X is not configured")
        return {
            "connected": False,
            "status": "ERROR",
            "broker": "Revolut X",
            "transport": "unconfigured",
            "message": str(exc),
        }
    try:
        if transport == "http":
            data = await http.get_balances(include_zero=True, timeout=10.0)
        else:
            data = await _run("account", "balances", "--all", timeout=10.0)
        return {
            "connected": True,
            "status": "OK",
            "broker": "Revolut X",
            "transport": transport,
            "currencies": len(data) if isinstance(data, list) else 0,
        }
    except RevolutXError as exc:
        logger.warning("Revolut X status check failed")
        return {
            "connected": False,
            "status": "ERROR",
            "broker": "Revolut X",
            "transport": transport,
            "message": str(exc),
        }


# ── Account ──────────────────────────────────────────────────────────────

async def get_balances(currency: Optional[str] = None, include_zero: bool = False) -> Any:
    if _use_http():
        return await http.get_balances(currency, include_zero)
    args = ["account", "balances"]
    if currency:
        args.append(currency)
    if include_zero:
        args.append("--all")
    return await _run(*args)


# ── Market Data ──────────────────────────────────────────────────────────

async def get_ticker(symbol: str = "BTC-USD") -> Any:
    if _use_http():
        return await http.get_tickers([symbol])
    return await _run("market", "tickers", symbol)


async def list_tickers(symbols: Optional[list[str]] = None) -> Any:
    """All tickers, or the pairs in ``symbols``. Same shape as ``revx market tickers``."""
    if _use_http():
        return await http.get_tickers(symbols)
    if symbols:
        return await _run("market", "tickers", "--symbols", ",".join(symbols))
    return await _run("market", "tickers")


async def get_candles(symbol: str = "BTC-USD", interval: str = "60", since: Optional[str] = None) -> Any:
    if _use_http():
        return await http.get_candles(symbol, interval=interval, since=since)
    args = ["market", "candles", symbol, "--interval", interval]
    if since:
        args.extend(["--since", since])
    return await _run(*args)


async def get_orderbook(symbol: str = "BTC-USD", limit: int = 10) -> Any:
    if _use_http():
        return await http.get_orderbook(symbol, limit=limit)
    return await _run("market", "orderbook", symbol, "--limit", str(limit))


async def get_pair(symbol: str = "BTC-USD") -> Any:
    if _use_http():
        return await http.get_pair(symbol)
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
    """Place a spot order.

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

    if _use_http():
        logger.info("Placing Revolut X order via HTTP: %s %s", symbol, side)
        return await http.place_order(
            symbol,
            side,
            qty=qty,
            quote=quote,
            limit_price=limit_price,
            market=market,
            post_only=post_only,
            client_order_id=client_order_id,
        )

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
    if _use_http():
        return await http.get_order(order_id)
    return await _run("order", "get", order_id)


async def get_order_fills(order_id: str) -> Any:
    if _use_http():
        return await http.get_order_fills(order_id)
    return await _run("order", "fills", order_id)


async def list_open_orders(symbol: Optional[str] = None) -> Any:
    if _use_http():
        return await http.list_open_orders(symbol)
    args = ["order", "open"]
    if symbol:
        args.extend(["--symbols", symbol])
    return await _run(*args)


async def list_order_history(symbol: Optional[str] = None) -> Any:
    if _use_http():
        return await http.list_order_history(symbol)
    args = ["order", "history"]
    if symbol:
        args.extend(["--symbols", symbol])
    return await _run(*args)


async def cancel_order(order_id: str) -> Any:
    if _use_http():
        return await http.cancel_order(order_id)
    return await _run("order", "cancel", order_id)


async def cancel_all_orders() -> Any:
    if _use_http():
        return await http.cancel_all_orders()
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
    if _use_http():
        return await http.replace_order(order_id, limit_price=limit_price, qty=qty, quote=quote)
    args: list[str] = ["order", "replace", order_id]
    if limit_price is not None:
        args.extend(["--price", str(limit_price)])
    if qty is not None:
        args.extend(["--qty", str(qty)])
    if quote is not None:
        args.extend(["--quote", str(quote)])
    return await _run(*args)
