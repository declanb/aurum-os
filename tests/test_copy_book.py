"""Paper copy book: open, mark-to-market, and close without a broker order."""

from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

import api.models  # noqa: F401
import api.routers.copy_book as copy_router
import api.services.copy_book as copy_book
from api.core.config import Settings
from api.core.db import get_session
from api.index import app
from api.models.trade import ApprovalEvent, ExecutionTicket, TradeIdea
from api.services import market_data
from api.services.copy_book import (
    CopyBookRefused,
    rank_eur_gainers,
    smoke,
    start_session,
    tick_session,
)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _session():
    return Session(_engine())


def _idea(db: Session, **overrides) -> TradeIdea:
    now = datetime.now(timezone.utc)
    fields = dict(
        user_id="seed_user",
        symbol="UNI-EUR",
        direction="LONG",
        entry_price=2.0,
        stop_price=1.8,
        target_price=2.6,
        thesis="Paper copy of a staged long. Buyers defended the range low.",
        invalidation_notes="A close under 1.80.",
        status="Ready for Approval",
        created_at=now,
        updated_at=now,
    )
    fields.update(overrides)
    idea = TradeIdea(**fields)
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


def _quote(symbol: str, px: float, **extra) -> dict:
    row = {"symbol": symbol, "bid": px, "ask": px, "mid": px, "last": px}
    row.update(extra)
    return row


def _imports_and_calls(module) -> tuple[set[str], set[str]]:
    tree = ast.parse(inspect.getsource(module))
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    return imported, called


def test_modules_do_not_call_the_order_path():
    for module in (copy_book, copy_router):
        imported, called = _imports_and_calls(module)
        banned = " ".join(sorted(imported | called))
        assert "trade_executor" not in banned
        assert "place_order" not in banned
        assert "execute_trade" not in banned


def test_bankroll_env_alias(monkeypatch):
    monkeypatch.delenv("HELM_COPY_BANKROLL_EUR", raising=False)
    monkeypatch.setenv("AURUM_COPY_BANKROLL_EUR", "250")
    fresh = Settings(_env_file=None)
    assert fresh.HELM_COPY_BANKROLL_EUR == 250.0


def test_change_24h_uses_payload_or_open_and_skips_missing():
    assert market_data.change_24h_pct({"change_24h_pct": "4.5"}) == pytest.approx(4.5)
    assert market_data.change_24h_pct({"open": "1", "last_price": "1.1"}) == pytest.approx(10.0)
    assert market_data.change_24h_pct({"bid": 1, "ask": 2}) is None
    ranked = rank_eur_gainers(
        [
            {"symbol": "SOL/EUR", "change_24h_pct": 5, "mid": 10, "bid": 10, "ask": 10},
            {"symbol": "BTC-EUR", "change_24h_pct": 1, "mid": 20, "bid": 20, "ask": 20},
            {"symbol": "ETH-USD", "change_24h_pct": 30, "mid": 10, "bid": 10, "ask": 10},
            {"symbol": "DOGE-EUR", "change_24h_pct": -2, "mid": 1, "bid": 1, "ask": 1},
            {"symbol": "XRP-EUR", "bid": 1, "ask": 1, "mid": 1},
            {"symbol": "ADA/EUR", "open": 1, "last": 1.2, "bid": 1.2, "ask": 1.2, "mid": 1.2},
        ],
        limit=10,
    )
    assert [row["symbol"] for row in ranked] == ["ADA-EUR", "SOL-EUR", "BTC-EUR"]


def test_dry_run_cannot_be_turned_off():
    db = _session()
    with pytest.raises(CopyBookRefused):
        start_session(db, dry_run=False)
    assert db.exec(select(copy_book.CopySession)).first() is None


def test_paper_open_flat_mark_then_any_green_close():
    db = _session()
    idea = _idea(db)
    book = start_session(
        db, bankroll_eur=200, position_pct=0.10, max_notional_eur=40, sources=["trade_ideas"], strategy="any_green"
    )
    assert book.dry_run is True
    assert book.max_notional_eur == pytest.approx(40)

    flat = asyncio.run(tick_session(db, book.id, quotes=[_quote("UNI/EUR", 2.0)]))
    assert flat["live_orders"] is False
    assert flat["broker_writes"] is False
    assert flat["session"]["open_count"] == 1
    assert flat["session"]["cash_eur"] == pytest.approx(180)
    opened = flat["open_positions"][0]
    assert opened["symbol"] == "UNI-EUR"
    assert opened["entry_notional_eur"] == pytest.approx(20)
    assert opened["entry_price"] == pytest.approx(2.0)
    assert opened["trade_idea_id"] == idea.id
    assert opened["signal_source"] == "trade_idea"
    assert opened["stop_price"] == pytest.approx(1.8)
    assert opened["target_price"] == pytest.approx(2.6)
    assert opened["unrealized_pnl_eur"] < 0
    assert flat["tick"]["opened"][0]["symbol"] == "UNI-EUR"

    still = asyncio.run(tick_session(db, book.id, quotes=[_quote("UNI-EUR", 2.0)]))
    assert still["session"]["open_count"] == 1
    assert still["tick"]["opened"] == []

    closed = asyncio.run(tick_session(db, book.id, quotes=[_quote("UNI-EUR", 2.1)]))
    assert closed["session"]["open_count"] == 0
    assert closed["session"]["closed_count"] == 1
    assert closed["session"]["realized_pnl_eur"] > 0
    assert closed["closed_trades"][0]["exit_reason"] == "any_green"
    assert closed["session"]["session_pnl_eur"] == pytest.approx(closed["session"]["realized_pnl_eur"])
    db.refresh(idea)
    assert idea.status == "Ready for Approval"
    assert db.exec(select(ExecutionTicket)).all() == []
    assert db.exec(select(ApprovalEvent)).all() == []


def test_hard_cap_and_ignored_symbols():
    db = _session()
    _idea(db, symbol="uni/eur")
    _idea(db, symbol="BTC-USD", thesis="A dollar pair must not enter the EUR paper book at all.")
    _idea(db, symbol="SOL-EUR", direction="SHORT", thesis="Shorts are not a spot copy. This row stays unfilled.")
    book = start_session(
        db,
        bankroll_eur=200,
        position_pct=0.25,
        max_notional_eur=500,
        sources=["trade_ideas"],
        max_positions=5,
    )
    assert book.max_notional_eur == pytest.approx(50)
    result = asyncio.run(
        tick_session(
            db,
            book.id,
            quotes=[_quote("UNI/EUR", 2), _quote("BTC-USD", 100), _quote("SOL-EUR", 20)],
        )
    )
    assert result["session"]["open_count"] == 1
    assert result["open_positions"][0]["symbol"] == "UNI-EUR"
    assert result["open_positions"][0]["entry_notional_eur"] == pytest.approx(50)
    assert result["session"]["cash_eur"] == pytest.approx(150)
    reasons = {row["reason"] for row in result["tick"]["skipped"]}
    assert "not_eur_spot" in reasons


def test_stop_beats_any_green_and_target_uses_bracket_ratchet():
    db = _session()
    _idea(db, symbol="BTC-EUR", entry_price=100, stop_price=90, target_price=130)
    book = start_session(db, bankroll_eur=200, sources=["trade_ideas"], any_green=True)
    asyncio.run(tick_session(db, book.id, quotes=[_quote("BTC-EUR", 100)]))
    stopped = asyncio.run(tick_session(db, book.id, quotes=[_quote("BTC-EUR", 89)]))
    assert stopped["closed_trades"][0]["exit_reason"] == "hard_stop"
    assert stopped["session"]["realized_pnl_eur"] < 0

    db2 = _session()
    _idea(db2, symbol="BTC-EUR", entry_price=100, stop_price=90, target_price=130)
    trailed = start_session(db2, bankroll_eur=200, sources=["trade_ideas"], any_green=False, strategy="any_green")
    asyncio.run(tick_session(db2, trailed.id, quotes=[_quote("BTC-EUR", 100)]))
    held = asyncio.run(tick_session(db2, trailed.id, quotes=[_quote("BTC-EUR", 120)]))
    assert held["session"]["open_count"] == 1
    assert held["open_positions"][0]["stop_price"] == pytest.approx(110)
    closed = asyncio.run(tick_session(db2, trailed.id, quotes=[_quote("BTC-EUR", 109)]))
    assert closed["closed_trades"][0]["exit_reason"] == "trailing_stop"


def test_gainers_are_paper_only_and_do_not_refill_a_copied_symbol():
    db = _session()
    book = start_session(
        db, bankroll_eur=200, sources=["gainers"], gainer_limit=1, position_pct=0.10, strategy="any_green"
    )
    first = asyncio.run(
        tick_session(
            db,
            book.id,
            quotes=[
                _quote("SOL/EUR", 10, change_24h_pct=5),
                _quote("BTC-EUR", 20, change_24h_pct=1),
                _quote("ETH-USD", 10, change_24h_pct=40),
            ],
        )
    )
    assert first["session"]["open_count"] == 1
    assert first["open_positions"][0]["symbol"] == "SOL-EUR"
    assert first["open_positions"][0]["signal_source"] == "gainer"
    assert first["open_positions"][0]["stop_price"] is None
    second = asyncio.run(tick_session(db, book.id, quotes=[_quote("SOL/EUR", 10, change_24h_pct=6)]))
    assert second["tick"]["opened"] == []
    assert second["session"]["open_count"] == 1


def test_trade_idea_wins_over_gainer_and_lookback_skips_old_ideas():
    db = _session()
    old = _idea(
        db,
        symbol="ADA-EUR",
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
        thesis="This staged idea is older than the copy lookback and must stay untouched.",
    )
    book = start_session(db, bankroll_eur=200, sources=["trade_ideas", "gainers"], lookback_hours=24, gainer_limit=3)
    fresh = _idea(db, symbol="SOL-EUR", thesis="Fresh scout long that the paper book is allowed to mirror.")
    result = asyncio.run(
        tick_session(
            db,
            book.id,
            quotes=[
                _quote("SOL-EUR", 10, change_24h_pct=9),
                _quote("ADA-EUR", 1, change_24h_pct=8),
                _quote("XRP-EUR", 1, change_24h_pct=1),
            ],
        )
    )
    symbols = {row["symbol"]: row["signal_source"] for row in result["open_positions"]}
    assert symbols["SOL-EUR"] == "trade_idea"
    assert "ADA-EUR" not in symbols or symbols["ADA-EUR"] == "gainer"
    assert all(row["trade_idea_id"] != old.id for row in result["open_positions"])
    assert any(row["trade_idea_id"] == fresh.id for row in result["open_positions"])


def test_tick_reads_tickers_and_does_not_touch_order_helpers(monkeypatch):
    db = _session()
    _idea(db, symbol="UNI-EUR")
    book = start_session(db, bankroll_eur=200, sources=["trade_ideas"])

    def boom(*_args, **_kwargs):
        raise AssertionError("broker write was invoked from the paper book")

    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)
    monkeypatch.setattr("api.services.trade_executor.execute_trade", boom)

    async def fake_tickers(_symbols=None):
        return [_quote("UNI/EUR", 2.0)]

    monkeypatch.setattr("api.services.copy_book.market_data.get_tickers", fake_tickers)
    result = asyncio.run(tick_session(db, book.id))
    assert result["session"]["open_count"] == 1
    assert result["tick"]["quote_error"] is None


def test_smoke_open_mark_close():
    payload = smoke()
    assert payload["live_orders"] is False
    assert payload["dry_run"] is True
    assert payload["session"]["closed_count"] == 1
    assert payload["session"]["realized_pnl_eur"] > 0
    assert payload["closed_trades"][0]["symbol"] == "UNI-EUR"
    assert payload["closed_trades"][0]["exit_reason"] == "any_green"


@pytest.fixture()
def api(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'copy.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def _db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _db
    try:
        yield TestClient(app), engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_http_session_tick_and_close(api, monkeypatch):
    client, engine = api

    def boom(*_args, **_kwargs):
        raise AssertionError("broker write was invoked from the paper book")

    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)
    monkeypatch.setattr("api.services.trade_executor.execute_trade", boom)

    empty = client.get("/api/copy/status")
    assert empty.status_code == 200
    assert empty.json()["active"] is False
    assert empty.json()["live_orders"] is False

    refused = client.post("/api/copy/session", json={"dry_run": False, "bankroll_eur": 200})
    assert refused.status_code == 400

    started = client.post(
        "/api/copy/session",
        json={"bankroll_eur": 200, "sources": ["trade_ideas"], "any_green": True},
    )
    assert started.status_code == 200
    body = started.json()
    assert body["dry_run"] is True
    assert body["live_orders"] is False
    assert body["session"]["starting_bankroll_eur"] == 200
    session_id = body["session"]["id"]

    again = client.post("/api/copy/session", json={"bankroll_eur": 200})
    assert again.status_code == 409
    assert again.json()["detail"]["session_id"] == session_id

    with Session(engine) as db:
        _idea(db, symbol="UNI-EUR")

    ticked = client.post(
        "/api/copy/tick",
        json={"quotes": [_quote("UNI/EUR", 2.0)]},
    )
    assert ticked.status_code == 200
    assert ticked.json()["session"]["open_count"] == 1
    position_id = ticked.json()["open_positions"][0]["id"]

    listed = client.get("/api/copy/positions?status=open")
    assert listed.status_code == 200
    assert len(listed.json()["positions"]) == 1
    assert listed.json()["live_orders"] is False

    closed = client.post(
        f"/api/copy/positions/{position_id}/close",
        json={"quotes": [_quote("UNI-EUR", 2.2)]},
    )
    assert closed.status_code == 200
    assert closed.json()["session"]["open_count"] == 0
    assert closed.json()["closed_trades"][0]["exit_reason"] == "manual"
    assert closed.json()["session"]["realized_pnl_eur"] > 0

    status = client.get("/api/copy/status")
    assert status.json()["session"]["id"] == session_id
    assert status.json()["active"] is True

    stopped = client.post("/api/copy/stop", json={})
    assert stopped.status_code == 200
    assert stopped.json()["active"] is False
    assert stopped.json()["session"]["status"] == "stopped"
    assert stopped.json()["live_orders"] is False
