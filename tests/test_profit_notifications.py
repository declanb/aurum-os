"""Helm profit notifications: one ping per milestone, no broker sell."""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

import api.models  # noqa: F401
from api.core.config import settings
from api.core.db import get_session
from api.index import app
from api.models.trade import (
    ApprovalEvent,
    ExecutionTicket,
    ExitBracket,
    ProfitNotification,
    TradeIdea,
    TradeIdeaVersion,
)
from api.services.exit_bracket import arm_bracket, monitor_brackets
from api.services.live_positions import sale_pnl
from api.services.profit_notifications import (
    format_pnl,
    list_notifications,
    notify_exit_filled,
    notify_take_profit,
    position_key,
    record_open_positions,
    scan_exit_milestones,
    scan_profits,
)


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _session():
    return Session(_engine())


def _seed_long(session: Session, *, fill: float = 100, qty: float = 0.5, symbol: str = "BTC-EUR", target: float = 130):
    now = datetime.now(timezone.utc)
    trade = TradeIdea(
        user_id="seed_user",
        symbol=symbol,
        direction="LONG",
        entry_price=fill,
        stop_price=90,
        target_price=target,
        thesis="A long enough thesis for the structural guardian to accept this idea.",
        invalidation_notes="Invalidate on a lost higher low.",
        status="Sent",
        created_at=now,
        updated_at=now,
    )
    session.add(trade)
    session.flush()
    version = TradeIdeaVersion(
        user_id="seed_user",
        symbol=symbol,
        direction="LONG",
        entry_price=fill,
        stop_price=90,
        target_price=target,
        thesis=trade.thesis,
        invalidation_notes=trade.invalidation_notes,
        trade_idea_id=trade.id,
        version_number=1,
    )
    session.add(version)
    session.flush()
    approval = ApprovalEvent(
        trade_idea_id=trade.id,
        version_id=version.id,
        user_id="seed_user",
        snapshot_hash="abc",
    )
    session.add(approval)
    session.flush()
    ticket = ExecutionTicket(
        approval_event_id=approval.id,
        adapter_status="Filled",
        symbol=symbol,
        side="buy",
        fill_qty=qty,
        fill_price=fill,
        broker_order_id="ord-entry",
        filled_at=now,
    )
    session.add(ticket)
    session.flush()
    bracket = arm_bracket(session, ticket, trade)
    session.commit()
    return trade, ticket, bracket


def _ena(pnl: float, ticket_id: int = 11, bracket_id: int | None = None):
    return {
        "symbol": "ENA-EUR",
        "qty": 10.8716,
        "entry_price": 0.1837,
        "pnl_eur": pnl,
        "pnl_pct": (pnl / (10.8716 * 0.1837)) * 100,
        "bid": 0.19 if pnl > 0 else 0.1836,
        "entry_ticket_id": ticket_id,
        "broker_order_id": "ena-1",
        "exit": {"id": bracket_id} if bracket_id else None,
    }


def test_sale_pnl_matches_a_red_then_green_ena_fill():
    qty = 10.8716
    entry = 0.1837
    cost = qty * entry
    red, _ = sale_pnl(qty, 0.1836, cost)
    green, green_pct = sale_pnl(qty, 0.19, cost)
    assert red is not None and red < 0
    assert green is not None and green > 0
    assert green_pct is not None and green_pct > 0
    assert "€+" in format_pnl(green, green_pct)
    assert "Aurum" not in format_pnl(green, green_pct)


def test_in_profit_is_once_per_position_and_skips_losses():
    with _session() as session:
        assert record_open_positions(session, [_ena(-0.002)]) == []
        assert record_open_positions(session, [_ena(0)]) == []
        first = record_open_positions(session, [_ena(0.04)])
        session.commit()
        assert len(first) == 1
        assert first[0].kind == "in_profit"
        assert first[0].dedupe_key == "in_profit:ticket:11"
        assert first[0].symbol == "ENA-EUR"
        assert "Helm" in first[0].body
        assert "Aurum" not in first[0].title
        assert "Aurum" not in first[0].body
        assert "approve" in first[0].body

        again = record_open_positions(session, [_ena(0.08)])
        session.commit()
        assert again == []
        rows = session.exec(select(ProfitNotification)).all()
        assert len(rows) == 1

        other = record_open_positions(session, [_ena(0.05, ticket_id=12)])
        session.commit()
        assert len(other) == 1
        assert other[0].dedupe_key == "in_profit:ticket:12"


def test_position_key_prefers_bracket_then_ticket_then_order():
    assert position_key(symbol="ENA-EUR", bracket_id=4, ticket_id=9, broker_order_id="x") == "bracket:4"
    assert position_key(symbol="ENA-EUR", ticket_id=9, broker_order_id="x") == "ticket:9"
    assert position_key(symbol="ENA-EUR", broker_order_id="x") == "order:x"
    assert position_key(symbol="ena-eur") == "held:ENA-EUR"


def test_take_profit_and_profitable_fill_are_separate_and_a_loss_is_silent():
    with _session() as session:
        _trade, _ticket, bracket = _seed_long(session)
        bracket.exit_trade_idea_id = 99
        bracket.exit_reason = "take_profit"
        session.add(bracket)
        session.commit()
        session.refresh(bracket)

        first = notify_take_profit(session, bracket, 130)
        session.commit()
        assert first is not None
        assert first.kind == "take_profit"
        assert first.dedupe_key == "take_profit:idea:99"
        assert "Helm" in first.body
        assert "execute" in first.body
        assert notify_take_profit(session, bracket, 131) is None

        bracket.exit_trade_idea_id = 100
        session.add(bracket)
        session.commit()
        session.refresh(bracket)
        second_idea = notify_take_profit(session, bracket, 130)
        session.commit()
        assert second_idea is not None
        assert second_idea.dedupe_key == "take_profit:idea:100"

        loss = notify_exit_filled(session, bracket, 89)
        assert loss is None
        bracket.status = "closed"
        bracket.closed_at = datetime.now(timezone.utc)
        session.add(bracket)
        session.commit()
        session.refresh(bracket)
        assert notify_exit_filled(session, bracket, 89) is None

        booked = notify_exit_filled(session, bracket, 130)
        session.commit()
        assert booked is not None
        assert booked.kind == "exit_filled"
        assert booked.pnl_eur is not None and booked.pnl_eur > 0
        assert "Helm" in booked.body
        assert notify_exit_filled(session, bracket, 131) is None

        kinds = {row.kind for row in session.exec(select(ProfitNotification)).all()}
        assert kinds == {"take_profit", "exit_filled"}


def test_milestone_scan_skips_old_fills_and_repeats():
    with _session() as session:
        _trade, _ticket, bracket = _seed_long(session)
        now = datetime.now(timezone.utc)
        idea = TradeIdea(
            user_id="seed_user",
            symbol="BTC-EUR",
            direction="EXIT",
            entry_price=130,
            stop_price=90,
            target_price=130,
            thesis="[EXIT take_profit] Helm bracket proposes a market sell of the spot long.",
            invalidation_notes="Reject to keep the long open.",
            status="Ready for Approval",
            created_at=now,
            updated_at=now,
        )
        session.add(idea)
        session.flush()
        bracket.exit_trade_idea_id = idea.id
        bracket.exit_reason = "take_profit"
        bracket.status = "exit_proposed"
        bracket.last_price = 130
        session.add(bracket)
        session.commit()

        created = scan_exit_milestones(session)
        session.commit()
        assert [row.kind for row in created] == ["take_profit"]
        assert scan_exit_milestones(session) == []

        bracket.status = "closed"
        bracket.closed_at = now - timedelta(days=10)
        bracket.last_price = 130
        session.add(bracket)
        session.commit()
        assert scan_exit_milestones(session) == []

        bracket.closed_at = now
        session.add(bracket)
        session.commit()
        fresh = scan_exit_milestones(session)
        session.commit()
        assert [row.kind for row in fresh] == ["exit_filled"]
        assert scan_exit_milestones(session) == []


def test_since_id_is_oldest_first_and_default_list_is_newest_first():
    with _session() as session:
        record_open_positions(session, [_ena(0.01, ticket_id=1), _ena(0.02, ticket_id=2)])
        session.commit()
        newest = list_notifications(session)
        assert [row["id"] for row in newest["notifications"]] == [2, 1]
        assert newest["unread_count"] == 2
        cursor = list_notifications(session, since_id=0)
        assert [row["id"] for row in cursor["notifications"]] == [1, 2]
        assert list_notifications(session, since_id=1)["notifications"][0]["id"] == 2


def test_scan_falls_back_to_bracket_bids_without_placing_an_order(monkeypatch):
    calls = []

    async def boom(*args, **kwargs):
        calls.append("place")
        raise AssertionError("broker write")

    async def down(_session):
        raise RuntimeError("account unavailable")

    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)
    monkeypatch.setattr("api.services.profit_notifications.build_live_positions", down)

    with _session() as session:
        _seed_long(session, fill=0.1837, qty=10.8716, symbol="ENA-EUR", target=0.25)
        summary = asyncio.run(scan_profits(session, bids={"ENA-EUR": 0.19}))
        assert summary["source"] == "brackets"
        assert summary["created"] == 1
        assert calls == []
        again = asyncio.run(scan_profits(session, bids={"ENA-EUR": 0.20}))
        assert again["created"] == 0
        rows = session.exec(select(ProfitNotification)).all()
        assert len(rows) == 1
        assert rows[0].symbol == "ENA-EUR"
        assert rows[0].pnl_eur is not None and rows[0].pnl_eur > 0


def test_live_take_profit_notifies_and_does_not_sell(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    calls = []

    async def seller(**kwargs):
        calls.append(kwargs)
        raise AssertionError("live monitor must not sell")

    async def boom(*args, **kwargs):
        raise AssertionError("broker write")

    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)

    with _session() as session:
        _seed_long(session)
        summary = asyncio.run(monitor_brackets(session, {"BTC-EUR": 130}, paper=False, seller=seller))
        assert summary["broker_orders_placed"] == 0
        assert calls == []
        assert summary["proposed"][0]["reason"] == "take_profit"
        notes = session.exec(select(ProfitNotification)).all()
        assert len(notes) == 1
        assert notes[0].kind == "take_profit"
        assert "Aurum" not in notes[0].body

        again = asyncio.run(monitor_brackets(session, {"BTC-EUR": 131}, paper=False, seller=seller))
        assert again["proposed"] == []
        assert len(session.exec(select(ProfitNotification)).all()) == 1


def test_hard_stop_loss_does_not_notify(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)

    async def seller(**kwargs):
        raise AssertionError("no sell")

    with _session() as session:
        _seed_long(session)
        summary = asyncio.run(monitor_brackets(session, {"BTC-EUR": 89}, paper=False, seller=seller))
        assert summary["proposed"][0]["reason"] == "hard_stop"
        assert session.exec(select(ProfitNotification)).all() == []


def test_paper_take_profit_books_a_ping_without_the_broker(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    calls = []

    async def seller(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "order_id": "paper-exit",
            "string_code": "PAPER_FILLED",
            "raw": {
                "paper": True,
                "state": "PAPER_FILLED",
                "filled_quantity": kwargs["qty"],
                "avg_fill_price": 130.0,
            },
        }

    async def boom(*args, **kwargs):
        raise AssertionError("broker write")

    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)

    with _session() as session:
        _seed_long(session)
        summary = asyncio.run(monitor_brackets(session, {"BTC-EUR": 130}, paper=True, seller=seller))
        assert summary["broker_orders_placed"] == 0
        assert len(calls) == 1
        assert calls[0]["symbol"] == "BTC-EUR"
        assert calls[0]["qty"] == 0.5
        kinds = sorted(row.kind for row in session.exec(select(ProfitNotification)).all())
        assert kinds == ["exit_filled", "take_profit"]


def test_live_positions_persist_one_green_ping(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    placed = []

    async def fake_account():
        return {
            "balances": [
                {"currency": "EUR", "balance": 20, "available": 20},
                {"currency": "ENA", "balance": 10.8716, "available": 10.8716},
            ]
        }

    async def fake_tickers(_symbols):
        return [{"symbol": "ENA-EUR", "bid": 0.19, "ask": 0.191}]

    async def boom(*args, **kwargs):
        placed.append("place")
        raise AssertionError("broker write")

    monkeypatch.setattr("api.services.live_positions.market_data.get_account_info", fake_account)
    monkeypatch.setattr("api.services.live_positions.market_data.get_tickers", fake_tickers)
    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override
    try:
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            session.add(ExecutionTicket(
                adapter_status="Filled",
                symbol="ENA-EUR",
                side="buy",
                fill_qty=10.8716,
                fill_price=0.1837,
                broker_order_id="ena-live",
                filled_at=now,
            ))
            session.commit()

        client = TestClient(app)
        first = client.get("/api/revolut-x/positions/live")
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["positions"][0]["symbol"] == "ENA-EUR"
        assert body["positions"][0]["pnl_eur"] > 0
        assert body["positions"][0]["entry_ticket_id"]
        assert placed == []

        second = client.get("/api/revolut-x/positions/live")
        assert second.status_code == 200

        listed = client.get("/api/notifications")
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["unread_count"] == 1
        note = payload["notifications"][0]
        assert note["kind"] == "in_profit"
        assert note["symbol"] == "ENA-EUR"
        assert note["pnl_eur"] > 0
        assert note["pnl_pct"] > 0
        assert "Helm" in note["body"]
        assert "Aurum" not in note["title"]
        assert "Aurum" not in note["body"]

        events = client.get("/api/notifications/events", params={"since_id": 0})
        assert events.status_code == 200
        assert events.json()["notifications"][0]["id"] == note["id"]

        read = client.post(f"/api/notifications/{note['id']}/read")
        assert read.status_code == 200
        assert read.json()["read"] is True
        assert client.get("/api/notifications").json()["unread_count"] == 0
        assert client.post("/api/notifications/read-all").status_code == 200
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
        os.remove(path)


def test_scan_endpoint_dedupes(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    async def fake_build(_session):
        return {"positions": [_ena(0.05, ticket_id=21)]}

    monkeypatch.setattr("api.services.profit_notifications.build_live_positions", fake_build)

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override
    try:
        client = TestClient(app)
        first = client.post("/api/notifications/scan")
        assert first.status_code == 200, first.text
        assert first.json()["created"] == 1
        assert first.json()["unread_count"] == 1
        second = client.post("/api/notifications/scan")
        assert second.status_code == 200
        assert second.json()["created"] == 0
        assert second.json()["unread_count"] == 1
        missing = client.post("/api/notifications/999/read")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
        os.remove(path)


def test_profit_notification_migration_creates_the_table(tmp_path):
    """Apply this revision on its own. The older sqlite batch migration is unrelated."""
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from api.alembic.versions.a1f6c8e94b27_add_profit_notification import (
        down_revision,
        revision,
        upgrade,
    )

    assert revision == "a1f6c8e94b27"
    assert down_revision == "e7c41b9a2d30"
    db = tmp_path / "helm.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            upgrade()
    with engine.connect() as connection:
        indexes = connection.exec_driver_sql("PRAGMA index_list('profitnotification')").all()
    unique_names = {row[1] for row in indexes if row[2]}
    assert "ix_profitnotification_dedupe_key" in unique_names
