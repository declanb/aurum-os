"""Signed HTTP client for the Revolut X REST API.

Auth scheme (https://developer.revolut.com/docs/api/revolut-x-crypto-exchange):

Every authenticated request sends three headers:

- ``X-Revx-API-Key``
- ``X-Revx-Timestamp`` — Unix epoch milliseconds
- ``X-Revx-Signature`` — base64 Ed25519 signature

The signed message is the concatenation, with no separators, of:

    timestamp + METHOD + path + query + body

``path`` starts at ``/api`` (for example ``/api/1.0/orders``). ``query`` is the
URL query string without ``?``. ``body`` is minified JSON, or empty.

This module does not place orders on its own. Callers still go through
Guardian and an ApprovalEvent before any write.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.parse
import uuid
from decimal import Decimal
from typing import Any, Mapping, Optional

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://revx.revolut.com"
API_PREFIX = "/api/1.0"

# Named candle intervals the CLI accepts. The REST API wants minutes.
_CANDLE_INTERVALS = {
    "1": "1",
    "1m": "1",
    "5": "5",
    "5m": "5",
    "15": "15",
    "15m": "15",
    "30": "30",
    "30m": "30",
    "60": "60",
    "1h": "60",
    "240": "240",
    "4h": "240",
    "d": "1440",
    "1d": "1440",
    "1440": "1440",
    "w": "10080",
    "1w": "10080",
    "10080": "10080",
}

_key_cache: dict[str, Ed25519PrivateKey] = {}
_http_transport: Optional[httpx.BaseTransport] = None


class RevolutXError(RuntimeError):
    """Broker call failed (HTTP status, CLI exit, or unparseable payload)."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str],
        stdout: str,
        stderr: str,
        returncode: int,
    ):
        super().__init__(message)
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def set_http_transport(transport: Optional[httpx.BaseTransport]) -> None:
    """Install a custom httpx transport. Tests pass ``httpx.MockTransport``."""
    global _http_transport
    _http_transport = transport


def clear_key_cache() -> None:
    _key_cache.clear()


def build_query_string(params: Optional[Mapping[str, Any]]) -> str:
    """Query string matching the official client: sorted keys, JS-style encoding.

    ``encodeURIComponent`` encodes a comma as ``%2C`` and leaves ``-_.!~*'()``
    alone. The same string is used in the URL and in the signature.
    """
    if not params:
        return ""
    items: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        items.append((str(key), str(value)))
    items.sort(key=lambda pair: pair[0])

    def enc(text: str) -> str:
        return urllib.parse.quote(text, safe="-_.!~*'()")

    return "&".join(f"{enc(key)}={enc(value)}" for key, value in items)


def compact_json(body: Mapping[str, Any]) -> str:
    """Minified JSON. Key order is insertion order, matching ``JSON.stringify``."""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def signing_message(
    timestamp: str,
    method: str,
    path: str,
    query: str = "",
    body: str = "",
) -> bytes:
    return f"{timestamp}{method.upper()}{path}{query}{body}".encode("utf-8")


def sign_request(
    private_key: Ed25519PrivateKey,
    timestamp: str,
    method: str,
    path: str,
    query: str = "",
    body: str = "",
) -> str:
    signature = private_key.sign(signing_message(timestamp, method, path, query, body))
    return base64.b64encode(signature).decode("ascii")


def _b64decode(text: str) -> bytes:
    compact = "".join(text.split())
    padded = compact + ("=" * ((-len(compact)) % 4))
    try:
        return base64.b64decode(padded, validate=True)
    except Exception:
        return base64.urlsafe_b64decode(padded)


def load_ed25519_private_key(material: str) -> Ed25519PrivateKey:
    """Load a PKCS#8 PEM, a base64 PEM, a PKCS#8 DER, or a raw 32-byte seed."""
    cached = _key_cache.get(material)
    if cached is not None:
        return cached

    text = material.strip().strip('"').strip("'")
    if "\\n" in text:
        text = text.replace("\\n", "\n")

    key: Any
    try:
        if "BEGIN" in text:
            key = serialization.load_pem_private_key(text.encode("utf-8"), password=None)
        else:
            raw = _b64decode(text)
            if raw.startswith(b"-----BEGIN"):
                key = serialization.load_pem_private_key(raw, password=None)
            elif len(raw) == 32:
                key = Ed25519PrivateKey.from_private_bytes(raw)
            else:
                key = serialization.load_der_private_key(raw, password=None)
    except Exception:
        raise RevolutXError(
            "Ed25519 private key could not be parsed. Provide REVX_PRIVATE_KEY as a PKCS#8 PEM "
            "(literal \\n is accepted) or REVX_PRIVATE_KEY_B64 (PEM, PKCS#8 DER, or raw 32-byte seed).",
            command=["http"],
            stdout="",
            stderr="",
            returncode=1,
        ) from None

    if not isinstance(key, Ed25519PrivateKey):
        raise RevolutXError(
            "Revolut X signing requires an Ed25519 private key.",
            command=["http"],
            stdout="",
            stderr="",
            returncode=1,
        )
    if len(_key_cache) > 4:
        _key_cache.clear()
    _key_cache[material] = key
    return key


def _first_set(*names: str) -> str:
    """First non-empty process env var, otherwise the matching Settings field."""
    for name in names:
        if name in os.environ and os.environ[name].strip():
            return os.environ[name].strip()
    for name in names:
        value = str(getattr(settings, name, "") or "").strip()
        if value:
            return value
    return ""


def api_key() -> str:
    return _first_set("REVX_API_KEY", "REVOLUT_X_API_KEY")


def private_key_material() -> str:
    return _first_set("REVX_PRIVATE_KEY", "REVX_PRIVATE_KEY_B64")


def credentials_configured() -> bool:
    return bool(api_key() and private_key_material())


def transport_preference() -> str:
    mode = _first_set("REVX_TRANSPORT") or "auto"
    return mode.lower()


def base_url() -> str:
    raw = _first_set("REVX_API_BASE_URL") or DEFAULT_BASE_URL
    base = raw.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" and host not in {"localhost", "127.0.0.1"}:
        raise RevolutXError(
            "REVX_API_BASE_URL must use https.",
            command=["http"],
            stdout="",
            stderr="",
            returncode=1,
        )
    return base


def _decimal_str(value: float) -> str:
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"invalid decimal {value!r}") from exc
    if number <= 0:
        raise ValueError(f"order size and price must be positive, got {value!r}")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def client_order_uuid(value: Optional[str]) -> str:
    """Stable UUID for idempotency.

    The REST API requires ``client_order_id`` to be a UUID. Aurum's execute
    path sends ``AURUM-{trade_id}-{approval_id}``. Mapping that string with
    UUID5 keeps retries on the same id instead of placing a second order.
    """
    if value:
        try:
            return str(uuid.UUID(value))
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, f"aurum:revx:{value}"))
    return str(uuid.uuid4())


def candle_interval(interval: str) -> str:
    mapped = _CANDLE_INTERVALS.get(str(interval).strip().lower())
    if mapped:
        return mapped
    return str(interval).strip()


def _redact(text: str) -> str:
    redacted = text
    for secret in (api_key(), private_key_material()):
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted[:500]


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], (list, dict)):
        return payload["data"]
    return payload


def _alias_order(order: Any) -> Any:
    """Add the id / fee names ``trade_executor`` already reads from CLI JSON."""
    if not isinstance(order, dict):
        return order
    aliased = dict(order)
    if "venue_order_id" in aliased and "id" not in aliased:
        aliased["id"] = aliased["venue_order_id"]
    if "client_order_id" in aliased and "clientOrderId" not in aliased:
        aliased["clientOrderId"] = aliased["client_order_id"]
    if "total_fee" in aliased and "fee" not in aliased:
        aliased["fee"] = aliased["total_fee"]
    return aliased


def _alias_fill(fill: Any) -> Any:
    if not isinstance(fill, dict):
        return fill
    if "price" in fill or "p" not in fill:
        return fill
    aliased = dict(fill)
    aliased["price"] = fill.get("p")
    aliased["quantity"] = fill.get("q")
    return aliased


def _alias_book(book: Any) -> Any:
    if not isinstance(book, dict):
        return book

    def levels(side: str) -> list:
        rows = []
        for level in book.get(side) or []:
            if isinstance(level, dict) and "price" not in level and "p" in level:
                level = {**level, "price": level.get("p"), "quantity": level.get("q")}
            rows.append(level)
        return rows

    return {**book, "bids": levels("bids"), "asks": levels("asks")}


def _pair_rows(payload: Any, symbol: Optional[str]) -> list:
    data = _unwrap(payload)
    rows: list[dict] = []
    if isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict)]
    elif isinstance(data, dict):
        if "base" in data or "symbol" in data:
            rows = [data]
        else:
            for key, value in data.items():
                if not isinstance(value, dict):
                    continue
                if "base" not in value and "quote" not in value:
                    continue
                row = dict(value)
                row.setdefault("symbol", str(key).replace("/", "-"))
                rows.append(row)
    if not symbol:
        return rows
    want = symbol.upper().replace("/", "-")
    matched = []
    for row in rows:
        pair = str(row.get("symbol") or "").upper().replace("/", "-")
        composed = f"{row.get('base', '')}-{row.get('quote', '')}".upper()
        if want in {pair, composed}:
            matched.append(row)
    return matched


def _filter_balances(rows: Any, currency: Optional[str], include_zero: bool) -> Any:
    if not isinstance(rows, list):
        return rows
    out = []
    want = currency.upper() if currency else None
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("currency") or "").upper()
        if want and code != want:
            continue
        if not include_zero and _balance_is_zero(row):
            continue
        out.append(row)
    return out


def _balance_is_zero(row: Mapping[str, Any]) -> bool:
    def amount(name: str) -> float:
        try:
            return float(row.get(name) or 0)
        except (TypeError, ValueError):
            return 0.0

    return all(amount(name) == 0 for name in ("available", "reserved", "staked", "total", "balance"))


async def request_json(
    method: str,
    path: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    body: Optional[Mapping[str, Any]] = None,
    timeout: float = 30.0,
) -> Any:
    """Signed request. ``path`` is relative to ``/api/1.0`` (for example ``/balances``)."""
    key = api_key()
    material = private_key_material()
    if not key or not material:
        raise RevolutXError(
            "Revolut X HTTP credentials are missing. Set REVX_API_KEY and "
            "REVX_PRIVATE_KEY or REVX_PRIVATE_KEY_B64.",
            command=[method.upper(), path],
            stdout="",
            stderr="",
            returncode=1,
        )
    private_key = load_ed25519_private_key(material)
    query = build_query_string(params)
    body_str = compact_json(body) if body is not None else ""
    full_path = f"{API_PREFIX}{path}"
    timestamp = str(int(time.time() * 1000))
    signature = sign_request(private_key, timestamp, method, full_path, query, body_str)
    headers = {
        "X-Revx-API-Key": key,
        "X-Revx-Timestamp": timestamp,
        "X-Revx-Signature": signature,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    url = f"{base_url()}{full_path}"
    if query:
        url = f"{url}?{query}"
    logger.debug("Revolut X HTTP %s %s", method.upper(), full_path)

    try:
        async with httpx.AsyncClient(transport=_http_transport, timeout=timeout) as client:
            response = await client.send(
                client.build_request(
                    method.upper(),
                    url,
                    headers=headers,
                    content=body_str.encode("utf-8") if body_str else None,
                ),
                follow_redirects=False,
            )
    except httpx.TimeoutException:
        # Do not chain the httpx error: its request holds the API key and signature.
        raise RevolutXError(
            f"Revolut X HTTP timed out after {timeout}s",
            command=[method.upper(), full_path],
            stdout="",
            stderr="",
            returncode=-1,
        ) from None
    except httpx.HTTPError as exc:
        raise RevolutXError(
            f"Revolut X HTTP request failed ({exc.__class__.__name__})",
            command=[method.upper(), full_path],
            stdout="",
            stderr="",
            returncode=1,
        ) from None

    text = response.text or ""
    if response.status_code in {301, 302, 303, 307, 308}:
        raise RevolutXError(
            f"Revolut X HTTP redirect {response.status_code} was not followed",
            command=[method.upper(), full_path],
            stdout="",
            stderr="",
            returncode=response.status_code,
        )
    if response.status_code >= 400:
        message = ""
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                message = str(parsed.get("message") or parsed.get("error") or "")
        except Exception:
            message = ""
        if not message:
            message = text
        message = _redact(message)
        raise RevolutXError(
            f"Revolut X HTTP {response.status_code}: {message}".strip(),
            command=[method.upper(), full_path],
            stdout=_redact(text),
            stderr="",
            returncode=response.status_code,
        )
    if response.status_code == 204 or not text.strip():
        return None
    try:
        parsed = response.json()
    except json.JSONDecodeError as exc:
        raise RevolutXError(
            f"Revolut X HTTP returned non-JSON output: {exc}",
            command=[method.upper(), full_path],
            stdout=_redact(text),
            stderr="",
            returncode=response.status_code,
        ) from exc
    return _unwrap(parsed)


async def get_balances(
    currency: Optional[str] = None,
    include_zero: bool = False,
    *,
    timeout: float = 30.0,
) -> Any:
    rows = await request_json("GET", "/balances", timeout=timeout)
    return _filter_balances(rows, currency, include_zero)


async def get_tickers(symbols: Optional[list[str]] = None, *, timeout: float = 30.0) -> Any:
    params: dict[str, Any] = {}
    if symbols:
        params["symbols"] = ",".join(symbols)
    return await request_json("GET", "/tickers", params=params, timeout=timeout)


async def get_candles(
    symbol: str,
    interval: str = "60",
    since: Optional[str] = None,
    *,
    timeout: float = 30.0,
) -> Any:
    params: dict[str, Any] = {"interval": candle_interval(interval)}
    if since:
        params["since"] = since
    return await request_json("GET", f"/candles/{_path_symbol(symbol)}", params=params, timeout=timeout)


async def get_orderbook(symbol: str, limit: int = 10, *, timeout: float = 30.0) -> Any:
    book = await request_json(
        "GET",
        f"/order-book/{_path_symbol(symbol)}",
        params={"limit": int(limit)},
        timeout=timeout,
    )
    return _alias_book(book)


async def get_pair(symbol: str, *, timeout: float = 30.0) -> Any:
    payload = await request_json("GET", "/configuration/pairs", timeout=timeout)
    return _pair_rows(payload, symbol)


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
    timeout: float = 30.0,
) -> Any:
    size: dict[str, str] = {}
    if qty is not None:
        size["base_size"] = _decimal_str(qty)
    if quote is not None:
        size["quote_size"] = _decimal_str(quote)
    if market:
        configuration: dict[str, Any] = {"market": size}
    else:
        if limit_price is None:
            raise ValueError("limit_price is required when market is false")
        limit: dict[str, Any] = {"price": _decimal_str(limit_price)}
        limit.update(size)
        if post_only:
            limit["execution_instructions"] = ["post_only"]
        configuration = {"limit": limit}
    body = {
        "client_order_id": client_order_uuid(client_order_id),
        "symbol": symbol,
        "side": side.lower(),
        "order_configuration": configuration,
    }
    placed = await request_json("POST", "/orders", body=body, timeout=timeout)
    return _alias_order(placed)


async def get_order(order_id: str, *, timeout: float = 30.0) -> Any:
    return _alias_order(await request_json("GET", f"/orders/{_path_symbol(order_id)}", timeout=timeout))


async def get_order_fills(order_id: str, *, timeout: float = 30.0) -> Any:
    fills = await request_json("GET", f"/orders/fills/{_path_symbol(order_id)}", timeout=timeout)
    if isinstance(fills, list):
        return [_alias_fill(fill) for fill in fills]
    return fills


async def list_open_orders(symbol: Optional[str] = None, *, timeout: float = 30.0) -> Any:
    params: dict[str, Any] = {}
    if symbol:
        params["symbols"] = symbol
    return await request_json("GET", "/orders/active", params=params, timeout=timeout)


async def list_order_history(symbol: Optional[str] = None, *, timeout: float = 30.0) -> Any:
    params: dict[str, Any] = {}
    if symbol:
        params["symbols"] = symbol
    return await request_json("GET", "/orders/historical", params=params, timeout=timeout)


async def cancel_order(order_id: str, *, timeout: float = 30.0) -> Any:
    await request_json("DELETE", f"/orders/{_path_symbol(order_id)}", timeout=timeout)
    return {"cancelled": order_id}


async def cancel_all_orders(*, timeout: float = 30.0) -> Any:
    await request_json("DELETE", "/orders", timeout=timeout)
    return {"cancelled": "all"}


async def replace_order(
    order_id: str,
    *,
    limit_price: Optional[float] = None,
    qty: Optional[float] = None,
    quote: Optional[float] = None,
    timeout: float = 30.0,
) -> Any:
    body: dict[str, Any] = {"client_order_id": client_order_uuid(None)}
    if limit_price is not None:
        body["price"] = _decimal_str(limit_price)
    if qty is not None:
        body["base_size"] = _decimal_str(qty)
    if quote is not None:
        body["quote_size"] = _decimal_str(quote)
    replaced = await request_json("PUT", f"/orders/{_path_symbol(order_id)}", body=body, timeout=timeout)
    return _alias_order(replaced)


def _path_symbol(value: str) -> str:
    return urllib.parse.quote(str(value), safe="-_.~")
