"""Thin MetaApi (metaapi.cloud) REST client for Helm's commodities venue.

Reads: account information, positions, current price, candles.
Write: one market order with mandatory stopLoss/takeProfit (live mode only,
called solely from ``metaapi_venue.execute_live``).

Secrets: ``METAAPI_TOKEN`` is sent only as the ``auth-token`` header. It is never
logged, returned, or put in an exception message. Errors are redacted.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_REGION = "new-york"
TIMEOUT = 15.0


class MetaApiError(Exception):
    """Redacted MetaApi failure. Message never contains the token."""


def _token() -> str:
    return (os.getenv("METAAPI_TOKEN") or "").strip()


def _account_id() -> str:
    return (os.getenv("METAAPI_ACCOUNT_ID") or "").strip()


def configured() -> bool:
    return bool(_token() and _account_id())


def _region() -> str:
    return (os.getenv("METAAPI_REGION") or DEFAULT_REGION).strip()


def client_base() -> str:
    return f"https://mt-client-api-v1.{_region()}.agiliumtrade.ai"


def market_data_base() -> str:
    return f"https://mt-market-data-client-api-v1.{_region()}.agiliumtrade.ai"


def redact(text: Any) -> str:
    s = str(text)
    for secret in (_token(), _account_id()):
        if secret:
            s = s.replace(secret, "***")
    return s


async def _request(method: str, url: str, *, params: Optional[dict] = None, json: Optional[dict] = None) -> Any:
    if not configured():
        raise MetaApiError("MetaApi is not configured (METAAPI_TOKEN / METAAPI_ACCOUNT_ID unset)")
    headers = {"auth-token": _token(), "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.request(method, url, params=params, json=json, headers=headers)
    except httpx.HTTPError as exc:
        raise MetaApiError(redact(f"MetaApi transport error: {type(exc).__name__}")) from None
    if resp.status_code >= 400:
        body = redact(resp.text[:300])
        logger.warning("MetaApi %s %s -> %s", method, redact(url), resp.status_code)
        raise MetaApiError(f"MetaApi HTTP {resp.status_code}: {body}")
    if not resp.content:
        return None
    return resp.json()


def _acct_url(path: str, base: Optional[str] = None) -> str:
    return f"{base or client_base()}/users/current/accounts/{_account_id()}{path}"


async def get_account_information() -> dict:
    return await _request("GET", _acct_url("/account-information")) or {}


async def get_positions() -> list[dict]:
    return await _request("GET", _acct_url("/positions")) or []


async def get_current_price(symbol: str) -> dict:
    """Returns MetaApi price dict: {symbol, bid, ask, time, ...}."""
    return await _request("GET", _acct_url(f"/symbols/{symbol}/current-price")) or {}


async def get_candles(symbol: str, timeframe: str = "1h", limit: int = 100) -> list[dict]:
    url = _acct_url(
        f"/historical-market-data/symbols/{symbol}/timeframes/{timeframe}/candles",
        base=market_data_base(),
    )
    return await _request("GET", url, params={"limit": limit}) or []


async def place_market_order(
    *,
    symbol: str,
    direction: str,
    volume: float,
    stop_loss: float,
    take_profit: float,
    client_id: str,
    comment: str = "Helm",
) -> dict:
    """Live order. Callers must have passed every Helm gate first."""
    if stop_loss is None or take_profit is None:
        raise MetaApiError("Refusing order without stop-loss and take-profit")
    action = {"LONG": "ORDER_TYPE_BUY", "SHORT": "ORDER_TYPE_SELL"}.get(direction.upper())
    if not action:
        raise MetaApiError(f"Unsupported direction {direction}")
    body = {
        "actionType": action,
        "symbol": symbol,
        "volume": float(volume),
        "stopLoss": float(stop_loss),
        "takeProfit": float(take_profit),
        "clientId": client_id[:30],
        "comment": comment[:26],
    }
    return await _request("POST", _acct_url("/trade"), json=body) or {}
