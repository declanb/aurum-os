"""MetaApi commodities venue: paper ledger, Guardian gates, scout, redaction.

All broker calls are mocked. No network.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

import api.models  # noqa: F401
from api.core.db import get_session
from api.index import app
from api.models.metaapi import MetaApiPaperPosition
from api.models.trade import ApprovalEvent, ExecutionTicket, TradeIdea
from api.services import metaapi_client as mc
from api.services import metaapi_venue as venue
from api.services.guardian import guardian_service

TOKEN = "tok-SECRET-123"
ACCOUNT = "acct-SECRET-456"
Q = {"XAUUSD": {"bid": 2000.0, "ask": 2000.5}}


@pytest.fixture
def db(monkeypatch):
    for k in ("METAAPI_TOKEN", "METAAPI_ACCOUNT_ID", "HELM_METAAPI_MODE", "HELM_METAAPI_MAX_LOTS", "HELM_METAAPI_ALLOWED_SYMBOLS"):
        monkeypatch.delenv(k, raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(db):
    app.dependency_overrides[get_session] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _idea(db, **kw):
    args = dict(
        symbol="XAUUSD", direction="LONG", entry_price=2000.0, stop_price=1980.0, target_price=2040.0,
        thesis="Gold trend continuation above SMA20 with rising slope.", invalidation_notes="Close below 1980",
    )
    args.update(kw)
    return venue.create_idea(db, **args)


def _approve(client, trade_id):
    r = client.post(f"/api/approvals/{trade_id}", json={"action": "APPROVE"})
    assert r.status_code == 200, r.text


def _candles(trend=1.0, n=60):
    out, px = [], 2000.0
    for _ in range(n):
        px += trend
        out.append({"open": px - trend, "high": px + 2, "low": px - 2, "close": px})
    return out


def test_status_defaults_paper_and_no_secrets(client, monkeypatch):
    monkeypatch.setenv("METAAPI_TOKEN", TOKEN)
    monkeypatch.setenv("METAAPI_ACCOUNT_ID", ACCOUNT)
    r = client.get("/api/metaapi/status")
    body = r.json()
    assert body["mode"] == "paper" and body["live_orders"] is False
    assert body["max_lots"] == 0.01
    assert body["allowed_symbols"] == ["XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD"]
    assert TOKEN not in r.text and ACCOUNT not in r.text
    assert "CFD" in body["warning"]


def test_redact_and_error_hides_token(monkeypatch):
    monkeypatch.setenv("METAAPI_TOKEN", TOKEN)
    monkeypatch.setenv("METAAPI_ACCOUNT_ID", ACCOUNT)
    assert TOKEN not in mc.redact(f"bad {TOKEN} {ACCOUNT}")


def test_paper_execute_requires_approval_then_opens_and_marks(db, client, monkeypatch):
    trade, meta = _idea(db)
    r = client.post(f"/api/metaapi/execute/{trade.id}", json={"quotes": Q})
    assert r.status_code == 400  # not approved
    _approve(client, trade.id)

    called = []
    monkeypatch.setattr(mc, "place_market_order", lambda **kw: called.append(kw))
    r = client.post(f"/api/metaapi/execute/{trade.id}", json={"quotes": Q})
    assert r.status_code == 200, r.text
    pos = r.json()["position"]
    assert pos["entry_price"] == 2000.5  # paid the ask
    assert pos["spread_cost"] == pytest.approx(0.5 * 0.01 * 100)
    assert not called
    assert db.exec(select(ExecutionTicket)).first() is None

    r = client.post("/api/metaapi/paper/mark", json={"quotes": {"XAUUSD": {"bid": 2010.0, "ask": 2010.5}}})
    marked = r.json()["marked"][0]
    assert marked["unrealized_pnl"] == pytest.approx((2010.0 - 2000.5) * 0.01 * 100)

    r = client.post("/api/metaapi/paper/mark", json={"quotes": {"XAUUSD": {"bid": 2050.0, "ask": 2050.5}}})
    assert r.json()["closed"]
    led = client.get("/api/metaapi/paper").json()
    assert led["closed"][0]["exit_reason"] == "target"
    assert led["realized_pnl"] == pytest.approx((2040.0 - 2000.5) * 1.0, abs=0.01)


def test_swap_estimate_reduces_pnl(db):
    from datetime import datetime, timedelta, timezone

    pos = MetaApiPaperPosition(symbol="XAUUSD", direction="LONG", lots=0.01, contract_size=100, entry_price=2000,
                               stop_price=1900, target_price=2100, swap_rate_per_night=0.0002,
                               opened_at=datetime.now(timezone.utc) - timedelta(days=2))
    swap = venue._swap(pos, datetime.now(timezone.utc))
    assert swap == pytest.approx(2 * 0.0002 * 2000 * 1)
    assert venue._pnl(pos, 2000, swap) == pytest.approx(-swap)


def test_guardian_blocks_bad_brackets_lots_and_symbol(db, monkeypatch):
    with pytest.raises(venue.MetaApiVenueError):
        _idea(db, lots=0.05)
    with pytest.raises(venue.MetaApiVenueError):
        _idea(db, symbol="EURUSD")
    trade, meta = _idea(db, stop_price=2010.0)
    v = venue.guardian_check(trade, meta)
    assert not v["passed"] and any("stop < entry" in i for i in v["issues"])
    assert "CFD" in v["warnings"][0]


def test_generic_guardian_warns_cfd_only_for_mt_symbols(db):
    trade, _ = _idea(db)
    assert "warnings" in guardian_service.challenge_trade(trade)
    spot = TradeIdea(user_id="seed_user", symbol="BTC-EUR", direction="LONG", entry_price=1, stop_price=0.9,
                     target_price=1.3, thesis="x" * 30, invalidation_notes="y")
    assert "warnings" not in guardian_service.challenge_trade(spot)


def _live(monkeypatch, account):
    monkeypatch.setenv("HELM_METAAPI_MODE", "live")
    monkeypatch.setenv("METAAPI_TOKEN", TOKEN)
    monkeypatch.setenv("METAAPI_ACCOUNT_ID", ACCOUNT)

    async def info():
        return account

    orders = []

    async def place(**kw):
        orders.append(kw)
        return {"numericCode": 10009, "orderId": "777"}

    monkeypatch.setattr(mc, "get_account_information", info)
    monkeypatch.setattr(mc, "place_market_order", place)
    return orders


def test_live_requires_leveraged_ok(db, client, monkeypatch):
    orders = _live(monkeypatch, {"equity": 1000, "margin": 0, "marginLevel": None})
    trade, _ = _idea(db)
    _approve(client, trade.id)
    r = client.post(f"/api/metaapi/execute/{trade.id}")
    assert r.status_code == 400 and "leveraged_ok" in r.json()["detail"]
    assert not orders


def test_live_refuses_low_margin_level(db, client, monkeypatch):
    orders = _live(monkeypatch, {"equity": 1000, "margin": 500, "marginLevel": 200})
    trade, _ = _idea(db)
    _approve(client, trade.id)
    client.post(f"/api/metaapi/ideas/{trade.id}/ack", json={"leveraged_ok": True})
    r = client.post(f"/api/metaapi/execute/{trade.id}")
    assert r.status_code == 400 and "300" in r.json()["detail"]
    assert not orders


def test_live_happy_path_sends_sl_tp_and_max_lots(db, client, monkeypatch):
    orders = _live(monkeypatch, {"equity": 1000, "margin": 100, "marginLevel": 1000})
    trade, _ = _idea(db)
    _approve(client, trade.id)
    client.post(f"/api/metaapi/ideas/{trade.id}/ack", json={"leveraged_ok": True})
    r = client.post(f"/api/metaapi/execute/{trade.id}")
    assert r.status_code == 200, r.text
    assert r.json()["adapter_status"] == "Submitted"
    o = orders[0]
    assert o["stop_loss"] == 1980.0 and o["take_profit"] == 2040.0 and o["volume"] == 0.01
    assert TOKEN not in r.text


def test_revx_execute_refuses_metaapi_idea(db, client):
    trade, _ = _idea(db)
    _approve(client, trade.id)
    r = client.post(f"/api/revolut-x/execute/{trade.id}", json={})
    assert r.status_code == 400 and "MetaApi" in r.text


def test_scout_stages_ideas_once(db):
    candles = {"XAUUSD": _candles(1.0), "XAGUSD": _candles(-0.01), "XBRUSD": [], "XTIUSD": _candles(0.0)}
    out = asyncio.run(venue.run_scout(db, candles))
    syms = {s["symbol"]: s for s in out["staged"]}
    assert syms["XAUUSD"]["direction"] == "LONG"
    assert syms["XAGUSD"]["direction"] == "SHORT"
    trade = db.get(TradeIdea, syms["XAUUSD"]["trade_idea_id"])
    assert trade.status == "Ready for Approval" and trade.stop_price < trade.entry_price < trade.target_price
    assert venue.meta_for(db, trade.id).venue == "metaapi"
    again = asyncio.run(venue.run_scout(db, candles))
    assert not again["staged"]
    assert db.exec(select(ApprovalEvent)).first() is None
