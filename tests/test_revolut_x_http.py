"""Revolut X HTTP signing and response parsing. No live keys and no network."""

import asyncio
import base64
import json
import logging

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.core.config import settings
from api.services import market_data, revolut_x_client as rx
from api.services import trade_executor
from api.services.revolut_x_client import RevolutXError
from api.services.revolut_x_http import (
    build_query_string,
    clear_key_cache,
    client_order_uuid,
    set_http_transport,
    sign_request,
    signing_message,
)

API_KEY = "test-revx-api-key"
ORDER_ID = "7a52e92e-8639-4fe1-abaa-68d3a2d5234b"


def _run(coro):
    return asyncio.run(coro)


def _seed_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def _pem(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _raw(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def _der(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _assert_signed(request: httpx.Request, key: Ed25519PrivateKey, api_key: str = API_KEY) -> None:
    assert request.headers["X-Revx-API-Key"] == api_key
    timestamp = request.headers["X-Revx-Timestamp"]
    assert timestamp.isdigit()
    signature = base64.b64decode(request.headers["X-Revx-Signature"])
    raw = request.url.raw_path.decode()
    path, _, query = raw.partition("?")
    body = request.content.decode()
    message = f"{timestamp}{request.method}{path}{query}{body}".encode()
    key.public_key().verify(signature, message)
    assert api_key.encode() not in message
    assert b"BEGIN PRIVATE KEY" not in request.content
    for header in request.headers.values():
        assert "BEGIN PRIVATE KEY" not in header


@pytest.fixture(autouse=True)
def _isolated_revx(monkeypatch):
    for name in (
        "REVX_API_KEY",
        "REVOLUT_X_API_KEY",
        "REVX_PRIVATE_KEY",
        "REVX_PRIVATE_KEY_B64",
        "REVX_API_BASE_URL",
        "REVX_TRANSPORT",
    ):
        monkeypatch.delenv(name, raising=False)
        if hasattr(settings, name):
            monkeypatch.setattr(settings, name, "" if name != "REVX_TRANSPORT" else "auto")
    monkeypatch.setattr(settings, "REVX_API_BASE_URL", "https://revx.revolut.com")
    monkeypatch.setattr(rx.shutil, "which", lambda name: None)
    clear_key_cache()

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected HTTP {request.method} {request.url}")

    set_http_transport(httpx.MockTransport(refuse))
    yield
    set_http_transport(None)
    clear_key_cache()


def _use_http(monkeypatch, key: Ed25519PrivateKey, *, material: str | None = None, api_key: str = API_KEY):
    monkeypatch.setenv("REVX_API_KEY", api_key)
    monkeypatch.setenv("REVX_PRIVATE_KEY", material if material is not None else _pem(key))


def test_signing_message_is_the_documented_concatenation():
    message = signing_message(
        "1700000000000",
        "get",
        "/api/1.0/orders/active",
        "limit=10",
        "",
    )
    assert message == b"1700000000000GET/api/1.0/orders/activelimit=10"


def test_signature_is_deterministic_and_verifies():
    key = _seed_key()
    first = sign_request(key, "1700000000000", "GET", "/api/1.0/balances")
    second = sign_request(key, "1700000000000", "get", "/api/1.0/balances")
    assert first == second
    with_query = sign_request(key, "1700000000000", "GET", "/api/1.0/balances", "limit=10", "")
    assert first != with_query
    key.public_key().verify(
        base64.b64decode(first),
        signing_message("1700000000000", "GET", "/api/1.0/balances"),
    )


def test_query_string_matches_javascript_encode_uri_component():
    query = build_query_string({"symbols": "BTC-EUR,ETH-EUR", "limit": 10, "skip": None})
    assert query == "limit=10&symbols=BTC-EUR%2CETH-EUR"


def test_private_key_pem_seed_and_der_sign_the_same():
    key = _seed_key()
    from api.services.revolut_x_http import load_ed25519_private_key

    pem_one_line = _pem(key).replace("\n", "\\n")
    loaded = [
        load_ed25519_private_key(_pem(key)),
        load_ed25519_private_key(pem_one_line),
        load_ed25519_private_key(base64.b64encode(_pem(key).encode()).decode()),
        load_ed25519_private_key(base64.b64encode(_raw(key)).decode()),
        load_ed25519_private_key(base64.b64encode(_der(key)).decode()),
    ]
    signatures = {
        sign_request(item, "1700000000000", "GET", "/api/1.0/balances") for item in loaded
    }
    assert signatures == {sign_request(key, "1700000000000", "GET", "/api/1.0/balances")}


def test_unconfigured_status_does_not_raise():
    status = _run(rx.get_status())
    assert status["connected"] is False
    assert status["transport"] == "unconfigured"
    assert "REVX_API_KEY" in status["message"]


def test_http_status_balances_and_redacted_error(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)
    calls = {"n": 0}
    balances = [
        {"currency": "EUR", "available": "5", "reserved": "0", "total": "5"},
        {"currency": "BTC", "available": "0", "reserved": "0", "total": "0"},
        {"currency": "ETH", "available": "0", "reserved": "0", "staked": "1", "total": "0"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        calls["n"] += 1
        if request.url.path != "/api/1.0/balances":
            raise AssertionError(request.url.path)
        if calls["n"] >= 4:
            return httpx.Response(401, json={"message": f"nope {API_KEY}"})
        return httpx.Response(200, json=balances)

    set_http_transport(httpx.MockTransport(handler))
    status = _run(rx.get_status())
    assert status["connected"] is True
    assert status["transport"] == "http"
    assert status["currencies"] == 3

    rows = _run(rx.get_balances())
    assert [row["currency"] for row in rows] == ["EUR", "ETH"]
    eur = _run(rx.get_balances(currency="eur"))
    assert len(eur) == 1 and eur[0]["currency"] == "EUR"

    with pytest.raises(RevolutXError) as caught:
        _run(rx.get_balances(include_zero=True))
    assert caught.value.returncode == 401
    assert API_KEY not in str(caught.value)
    assert API_KEY not in caught.value.stdout


def test_market_reads_parse_wire_shapes(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        path = request.url.path
        query = request.url.raw_path.decode().partition("?")[2]
        if path == "/api/1.0/tickers":
            assert "symbols=BTC-EUR" in query
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "symbol": "BTC/EUR",
                            "bid": "1.5",
                            "ask": "1.7",
                            "last_price": "1.6",
                            "mid": "1.6",
                        }
                    ],
                    "metadata": {"timestamp": 1},
                },
            )
        if path == "/api/1.0/candles/BTC-EUR":
            assert "interval=1440" in query
            return httpx.Response(
                200,
                json={"data": [{"start": 10, "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "3"}]},
            )
        if path == "/api/1.0/order-book/BTC-EUR":
            assert "limit=5" in query
            return httpx.Response(
                200,
                json={
                    "data": {
                        "bids": [{"p": "1.5", "q": "0.2"}],
                        "asks": [{"p": "1.7", "q": "0.3"}],
                    }
                },
            )
        if path == "/api/1.0/configuration/pairs":
            return httpx.Response(
                200,
                json={
                    "BTC/EUR": {
                        "base": "BTC",
                        "quote": "EUR",
                        "base_step": "0.00000001",
                        "quote_step": "0.01",
                        "min_order_size": "0.00001",
                        "max_order_size": "10",
                        "min_order_size_quote": "1",
                        "status": "active",
                    },
                    "ETH/EUR": {"base": "ETH", "quote": "EUR", "min_order_size": "0.001", "status": "active"},
                },
            )
        raise AssertionError(path)

    set_http_transport(httpx.MockTransport(handler))
    price = _run(market_data.get_price("BTC-EUR"))
    assert price["bid"] == 1.5
    assert price["ask"] == 1.7
    assert price["spread"] == pytest.approx(0.2)

    candles = _run(market_data.get_candles("BTC-EUR", "1d", count=10))
    assert candles[0]["close"] == 1.5
    assert candles[0]["tick_volume"] == 3

    book = _run(market_data.get_orderbook("BTC-EUR", limit=5))
    assert book["bids"] == [{"price": 1.5, "size": 0.2}]
    assert book["asks"][0]["price"] == 1.7

    spec = _run(market_data.get_symbol_specification("BTC-EUR"))
    assert spec["base_currency"] == "BTC"
    assert spec["quote_currency"] == "EUR"
    assert spec["min_volume"] == pytest.approx(0.00001)

    multi = _run(rx.list_tickers(["BTC-EUR", "ETH-EUR"]))
    assert multi[0]["symbol"] == "BTC/EUR"
    wire = _run(rx.list_tickers(["BTC-EUR", "ETH-EUR"]))
    assert wire[0]["bid"] == "1.5"


def test_ticker_query_encodes_commas(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        raw = request.url.raw_path.decode()
        assert "symbols=BTC-EUR%2CETH-EUR" in raw
        return httpx.Response(200, json={"data": []})

    set_http_transport(httpx.MockTransport(handler))
    assert _run(rx.list_tickers(["BTC-EUR", "ETH-EUR"])) == []


def test_place_order_signs_body_and_keeps_client_id(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        assert request.method == "POST"
        assert request.url.path == "/api/1.0/orders"
        body = json.loads(request.content)
        bodies.append(body)
        assert " " not in request.content.decode()
        return httpx.Response(
            200,
            json={
                "data": {
                    "venue_order_id": ORDER_ID,
                    "client_order_id": body["client_order_id"],
                    "state": "new",
                }
            },
        )

    set_http_transport(httpx.MockTransport(handler))
    first = _run(
        rx.place_order(
            "BTC-EUR",
            "BUY",
            qty=0.00003443,
            limit_price=95000,
            post_only=True,
            client_order_id="AURUM-12-3",
        )
    )
    second = _run(
        rx.place_order(
            "BTC-EUR",
            "buy",
            qty=0.00003443,
            limit_price=95000,
            post_only=True,
            client_order_id="AURUM-12-3",
        )
    )
    assert first["id"] == ORDER_ID
    assert first["venue_order_id"] == ORDER_ID
    assert first["state"] == "new"
    assert bodies[0]["client_order_id"] == bodies[1]["client_order_id"]
    assert bodies[0]["client_order_id"] == client_order_uuid("AURUM-12-3")
    assert bodies[0]["side"] == "buy"
    assert bodies[0]["order_configuration"]["limit"] == {
        "price": "95000",
        "base_size": "0.00003443",
        "execution_instructions": ["post_only"],
    }
    assert second["clientOrderId"] == bodies[0]["client_order_id"]


def test_execute_trade_reads_http_order_id(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        body = json.loads(request.content)
        assert body["symbol"] == "BTC-EUR"
        assert body["order_configuration"]["market"]["quote_size"] == "2"
        assert body["client_order_id"] == client_order_uuid("AURUM-9-4")
        return httpx.Response(
            200,
            json={
                "data": {
                    "venue_order_id": ORDER_ID,
                    "client_order_id": body["client_order_id"],
                    "state": "pending_new",
                }
            },
        )

    set_http_transport(httpx.MockTransport(handler))
    result = _run(
        trade_executor.execute_trade(
            symbol="BTC-EUR",
            direction="LONG",
            volume=0.0,
            quote_eur=2.0,
            client_order_id="AURUM-9-4",
        )
    )
    assert result["success"] is True
    assert result["order_id"] == ORDER_ID
    assert result["string_code"] == "PENDING_NEW"


def test_fill_poll_parses_order_and_wire_fills(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        if request.url.path == f"/api/1.0/orders/{ORDER_ID}":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": ORDER_ID,
                        "status": "filled",
                        "filled_quantity": "0.01",
                        "average_fill_price": "100",
                        "total_fee": "0.02",
                        "fee_currency": "EUR",
                    }
                },
            )
        if request.url.path == f"/api/1.0/orders/fills/{ORDER_ID}":
            return httpx.Response(
                200,
                json={"data": [{"p": "100", "q": "0.01", "tid": "abc"}]},
            )
        raise AssertionError(request.url.path)

    set_http_transport(httpx.MockTransport(handler))
    summary = _run(trade_executor.poll_for_fill(ORDER_ID, max_attempts=1))
    assert summary["state"] == "FILLED"
    assert summary["fill_qty"] == pytest.approx(0.01)
    assert summary["fill_price"] == pytest.approx(100)
    assert summary["fills"][0]["price"] == "100"
    assert summary["fills"][0]["quantity"] == "0.01"


def test_cancel_replace_and_redirect_are_not_followed(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        calls["n"] += 1
        if request.method == "DELETE" and request.url.path == f"/api/1.0/orders/{ORDER_ID}":
            return httpx.Response(204)
        if request.method == "DELETE" and request.url.path == "/api/1.0/orders":
            return httpx.Response(204)
        if request.method == "PUT":
            body = json.loads(request.content)
            assert body["price"] == "96000"
            assert body["base_size"] == "0.002"
            return httpx.Response(
                200,
                json={"data": {"venue_order_id": "11111111-1111-1111-1111-111111111111", "client_order_id": body["client_order_id"], "state": "new"}},
            )
        if request.method == "GET":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        raise AssertionError(request.method + " " + request.url.path)

    set_http_transport(httpx.MockTransport(handler))
    assert _run(rx.cancel_order(ORDER_ID)) == {"cancelled": ORDER_ID}
    assert _run(rx.cancel_all_orders()) == {"cancelled": "all"}
    replaced = _run(rx.replace_order(ORDER_ID, limit_price=96000, qty=0.002))
    assert replaced["id"] == "11111111-1111-1111-1111-111111111111"
    with pytest.raises(RevolutXError) as caught:
        _run(rx.get_order(ORDER_ID))
    assert caught.value.returncode == 302
    assert calls["n"] == 4


def test_open_orders_pass_symbol_filter(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        assert request.url.path == "/api/1.0/orders/active"
        assert "symbols=BTC-EUR" in request.url.raw_path.decode()
        return httpx.Response(200, json={"data": [{"id": ORDER_ID, "symbol": "BTC/EUR", "status": "new"}]})

    set_http_transport(httpx.MockTransport(handler))
    rows = _run(rx.list_open_orders("BTC-EUR"))
    assert rows[0]["id"] == ORDER_ID


def test_logs_omit_key_material(monkeypatch, caplog):
    key = _seed_key()
    _use_http(monkeypatch, key, material=_pem(key))
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    set_http_transport(httpx.MockTransport(handler))
    _run(rx.get_balances(include_zero=True))
    assert API_KEY not in caplog.text
    assert "BEGIN PRIVATE KEY" not in caplog.text
    assert "PRIVATE" not in caplog.text


def test_cli_fallback_unwraps_json_and_skips_http(monkeypatch):
    captured: dict = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b'{"data":[{"symbol":"BTC/EUR","bid":"9"}],"metadata":{"timestamp":1}}', b""

        def kill(self):
            pass

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        captured["argv"] = args
        return FakeProc()

    monkeypatch.setattr(rx.shutil, "which", lambda name: "/usr/bin/revx" if name == "revx" else None)
    monkeypatch.setattr(rx.asyncio, "create_subprocess_exec", fake_exec)
    rows = _run(rx.get_ticker("BTC-EUR"))
    assert rows == [{"symbol": "BTC/EUR", "bid": "9"}]
    assert captured["argv"][0] == "/usr/bin/revx"
    assert captured["argv"][1:4] == ("market", "tickers", "BTC-EUR")
    assert captured["argv"][-1] == "--json"


def test_cli_forced_when_keys_exist_but_transport_is_cli(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)
    monkeypatch.setenv("REVX_TRANSPORT", "cli")
    called = {"http": False, "cli": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["http"] = True
        return httpx.Response(200, json=[])

    class FakeProc:
        returncode = 0

        async def communicate(self):
            called["cli"] = True
            return b"[]", b""

        def kill(self):
            pass

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    set_http_transport(httpx.MockTransport(handler))
    monkeypatch.setattr(rx.shutil, "which", lambda name: "/usr/bin/revx" if name == "revx" else None)
    monkeypatch.setattr(rx.asyncio, "create_subprocess_exec", fake_exec)
    assert _run(rx.get_balances(include_zero=True)) == []
    assert called == {"http": False, "cli": True}


def test_http_preferred_over_cli_when_keys_are_set(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        return httpx.Response(200, json=[{"currency": "EUR", "available": "1", "reserved": "0", "total": "1"}])

    async def fail_exec(*args, **kwargs):
        raise AssertionError("revx should not be spawned when HTTP credentials are set")

    set_http_transport(httpx.MockTransport(handler))
    monkeypatch.setattr(rx.shutil, "which", lambda name: "/usr/bin/revx")
    monkeypatch.setattr(rx.asyncio, "create_subprocess_exec", fail_exec)
    rows = _run(rx.get_balances())
    assert rows[0]["currency"] == "EUR"


def test_missing_cli_binary_is_a_revolut_error(monkeypatch):
    monkeypatch.setenv("REVX_TRANSPORT", "cli")
    monkeypatch.setattr(rx.shutil, "which", lambda name: "/usr/bin/revx" if name == "revx" else None)

    async def missing(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "revx")

    monkeypatch.setattr(rx.asyncio, "create_subprocess_exec", missing)
    with pytest.raises(RevolutXError) as caught:
        _run(rx.get_balances())
    assert caught.value.returncode == 127
    assert "not found" in str(caught.value).lower()


def test_transport_errors_do_not_chain_the_signed_request(monkeypatch):
    key = _seed_key()
    _use_http(monkeypatch, key)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    set_http_transport(httpx.MockTransport(handler))
    with pytest.raises(RevolutXError) as caught:
        _run(rx.get_balances())
    assert caught.value.__cause__ is None
    assert API_KEY not in str(caught.value)
    assert "X-Revx" not in str(caught.value)


def test_bad_private_key_and_insecure_base_url(monkeypatch):
    monkeypatch.setenv("REVX_API_KEY", API_KEY)
    monkeypatch.setenv("REVX_PRIVATE_KEY", "not-a-key")
    with pytest.raises(RevolutXError) as caught:
        _run(rx.get_balances())
    assert "could not be parsed" in str(caught.value)
    assert "not-a-key" not in str(caught.value)

    monkeypatch.setenv("REVX_PRIVATE_KEY", _pem(_seed_key()))
    monkeypatch.setenv("REVX_API_BASE_URL", "http://evil.example")
    with pytest.raises(RevolutXError) as caught:
        _run(rx.get_balances())
    assert "https" in str(caught.value)


def test_revolut_x_api_key_alias_and_b64_seed(monkeypatch):
    key = _seed_key()
    monkeypatch.setenv("REVOLUT_X_API_KEY", API_KEY)
    monkeypatch.setenv("REVX_PRIVATE_KEY_B64", base64.b64encode(_raw(key)).decode())

    def handler(request: httpx.Request) -> httpx.Response:
        _assert_signed(request, key)
        return httpx.Response(200, json={"data": []})

    set_http_transport(httpx.MockTransport(handler))
    assert _run(rx.list_order_history("BTC-EUR")) == []
