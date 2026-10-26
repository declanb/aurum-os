"""Helm exit brackets: ratchet maths, HITL proposals, paper auto-exit."""

from __future__ import annotations

import asyncio
import inspect
import os
import tempfile
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

import api.models  # noqa: F401  (register tables)
from api.core.config import settings
from api.core.db import get_session
from api.index import app
from api.models.trade import (
    ApprovalEvent,
    ExecutionTicket,
    ExitBracket,
    TradeIdea,
    TradeIdeaVersion,
)
from api.routers.approvals import _compute_snapshot_hash
from api.services import trade_executor
from api.services.exit_bracket import (
    _snapshot_hash,
    arm_bracket,
    evaluate_long_bracket,
    extract_bid,
    monitor_brackets,
)
from api.services.profit_hunter import _execute_sell


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _session():
    return Session(_engine())


def _seed_long(session: Session, *, direction: str = "LONG", stop: float = 90, target: float = 130, fill: float = 100, qty: float = 0.5, symbol: str = "BTC-EUR"):
    now = datetime.now(timezone.utc)
    trade = TradeIdea(
        user_id="seed_user",
        symbol=symbol,
        direction=direction,
        entry_price=fill,
        stop_price=stop,
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
        direction=direction,
        entry_price=fill,
        stop_price=stop,
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


def _eval(**overrides):
    base = dict(
        entry_price=100.0,
        initial_stop=90.0,
        stop_price=90.0,
        target_price=130.0,
        high_water=100.0,
        bid=100.0,
    )
    base.update(overrides)
    return evaluate_long_bracket(**base)


def test_snapshot_hash_matches_approvals_router():
    trade = TradeIdea(
        user_id="seed_user",
        symbol="BTC-EUR",
        direction="EXIT",
        entry_price=90,
        stop_price=90,
        target_price=130,
        thesis="exit",
        invalidation_notes="reject",
    )
    assert _snapshot_hash(trade) == _compute_snapshot_hash(trade)


def test_extract_bid_shapes():
    assert extract_bid([{"bid": "101.5"}]) == 101.5
    assert extract_bid({"data": [{"bid": 80}]}) == 80.0
    assert extract_bid({"bid": 0}) is None
    assert extract_bid({"bid": "nope"}) is None
    assert extract_bid(None) is None


def test_hard_stop_before_any_rally():
    view = _eval(bid=90)
    assert view.action == "hard_stop"
    assert view.stop_price == 90
    assert view.trail_armed is False


def test_gap_through_stop_is_not_a_target():
    view = _eval(bid=80)
    assert view.action == "hard_stop"


def test_no_trail_inside_one_r():
    view = _eval(bid=109)
    assert view.action == "hold"
    assert view.stop_price == 90
    assert view.trail_armed is False
    assert view.high_water_price == 109


def test_trail_arms_at_one_r_and_steps_only_quarter_r():
    armed = _eval(bid=110)
    assert armed.action == "hold"
    assert armed.trail_armed is True
    assert armed.stop_price == 100

    stepped = _eval(stop_price=100, high_water=110, bid=115)
    assert stepped.stop_price == 105
    assert stepped.action == "hold"

    # 116 is only 0.1R above the stop that 115 would set; from stop 105 the
    # candidate is 106, and 1.0 < 0.25R (2.5), so the stop stays.
    stuck = _eval(stop_price=105, high_water=115, bid=116)
    assert stuck.stop_price == 105
    assert stuck.action == "hold"


def test_stop_never_moves_down():
    view = _eval(stop_price=105, high_water=115, bid=112)
    assert view.stop_price == 105
    assert view.action == "hold"


def test_trailing_stop_when_bid_tags_the_ratchet():
    view = _eval(stop_price=105, high_water=115, bid=105)
    assert view.action == "trailing_stop"
    assert view.stop_price == 105


def test_take_profit_when_bid_reaches_target():
    view = _eval(bid=130)
    assert view.action == "take_profit"
    assert view.stop_price == 120  # high-water 130 trails 1R
    assert view.trail_armed is True


def test_zero_risk_disables_trail_but_keeps_the_hard_stop():
    view = _eval(entry_price=100, initial_stop=100, stop_price=100, bid=100, target_price=130)
    assert view.action == "hard_stop"
    assert view.trail_armed is False


def test_short_is_not_armed():
    with _session() as session:
        _trade, _ticket, bracket = _seed_long(session, direction="SHORT")
        assert bracket is None


def test_arm_is_idempotent():
    with _session() as session:
        trade, ticket, first = _seed_long(session)
        again = arm_bracket(session, ticket, trade)
        session.commit()
        rows = session.exec(select(ExitBracket)).all()
        assert first is not None and again is not None
        assert first.id == again.id
        assert len(rows) == 1


def test_live_trigger_proposes_exit_and_does_not_sell(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    calls = []

    async def seller(**kwargs):
        calls.append(kwargs)
        raise AssertionError("live monitor must not sell")

    with _session() as session:
        trade, _ticket, _bracket = _seed_long(session)
        summary = asyncio.run(monitor_brackets(session, {"BTC-EUR": 89}, paper=False, seller=seller))
        assert summary["mode"] == "live"
        assert summary["broker_orders_placed"] == 0
        assert calls == []
        assert len(summary["proposed"]) == 1
        assert summary["proposed"][0]["reason"] == "hard_stop"

        idea = session.get(TradeIdea, summary["proposed"][0]["exit_trade_idea_id"])
        assert idea is not None
        assert idea.direction == "EXIT"
        assert idea.status == "Ready for Approval"
        assert idea.thesis.startswith("[EXIT hard_stop]")
        events = session.exec(select(ApprovalEvent).where(ApprovalEvent.trade_idea_id == idea.id)).all()
        assert events == []
        entry = session.get(TradeIdea, trade.id)
        assert entry.status == "Sent"

        # Second tick must not open another idea while the first is waiting.
        again = asyncio.run(monitor_brackets(session, {"BTC-EUR": 88}, paper=False, seller=seller))
        assert again["proposed"] == []
        assert again["suppressed"] == 1
        exits = session.exec(select(TradeIdea).where(TradeIdea.direction == "EXIT")).all()
        assert len(exits) == 1


def test_rejection_waits_for_clear_and_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)

    async def seller(**kwargs):
        raise AssertionError("no sell")

    with _session() as session:
        _seed_long(session)
        first = asyncio.run(monitor_brackets(session, {"BTC-EUR": 80}, paper=False, seller=seller))
        idea_id = first["proposed"][0]["exit_trade_idea_id"]
        idea = session.get(TradeIdea, idea_id)
        idea.status = "Needs Work"
        session.add(idea)
        session.commit()

        suppressed = asyncio.run(monitor_brackets(session, {"BTC-EUR": 80}, paper=False, seller=seller))
        assert suppressed["proposed"] == []
        cancelled = session.get(TradeIdea, idea_id)
        assert cancelled.status == "Cancelled"
        bracket = session.exec(select(ExitBracket)).one()
        assert bracket.status == "armed"
        assert bracket.pending_clear is True

        held = asyncio.run(monitor_brackets(session, {"BTC-EUR": 100}, paper=False, seller=seller))
        assert held["held"] == 1
        bracket = session.exec(select(ExitBracket)).one()
        assert bracket.pending_clear is False
        assert bracket.cooldown_until is not None

        still = asyncio.run(monitor_brackets(session, {"BTC-EUR": 80}, paper=False, seller=seller))
        assert still["proposed"] == []
        exits = session.exec(select(TradeIdea).where(TradeIdea.direction == "EXIT")).all()
        assert len(exits) == 1

        bracket.cooldown_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.add(bracket)
        session.commit()
        fresh = asyncio.run(monitor_brackets(session, {"BTC-EUR": 80}, paper=False, seller=seller))
        assert len(fresh["proposed"]) == 1
        exits = session.exec(select(TradeIdea).where(TradeIdea.direction == "EXIT")).all()
        assert len(exits) == 2


def test_ratchet_persists_then_trails_out(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)

    async def seller(**kwargs):
        raise AssertionError("no sell")

    with _session() as session:
        _seed_long(session)
        asyncio.run(monitor_brackets(session, {"BTC-EUR": 110}, paper=False, seller=seller))
        bracket = session.exec(select(ExitBracket)).one()
        assert bracket.stop_price == 100
        assert bracket.trail_armed is True
        assert bracket.status == "armed"

        asyncio.run(monitor_brackets(session, {"BTC-EUR": 115}, paper=False, seller=seller))
        bracket = session.exec(select(ExitBracket)).one()
        assert bracket.stop_price == 105

        summary = asyncio.run(monitor_brackets(session, {"BTC-EUR": 104}, paper=False, seller=seller))
        assert summary["proposed"][0]["reason"] == "trailing_stop"


def test_paper_flag_without_setting_does_not_sell(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    calls = []

    async def seller(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    with _session() as session:
        _seed_long(session)
        summary = asyncio.run(monitor_brackets(session, {"BTC-EUR": 80}, paper=True, seller=seller))
        assert summary["mode"] == "live"
        assert calls == []
        assert len(summary["proposed"]) == 1


def test_paper_mode_auto_closes_without_broker(monkeypatch):
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
                "avg_fill_price": 89.0,
            },
        }

    async def boom(*args, **kwargs):
        raise AssertionError("broker write")

    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)

    with _session() as session:
        trade, _ticket, _bracket = _seed_long(session)
        summary = asyncio.run(monitor_brackets(session, {"BTC-EUR": 89}, paper=True, seller=seller))
        assert summary["mode"] == "paper"
        assert summary["broker_orders_placed"] == 0
        assert len(summary["paper_closed"]) == 1
        assert len(calls) == 1
        assert calls[0]["qty"] == 0.5
        assert calls[0]["symbol"] == "BTC-EUR"

        bracket = session.exec(select(ExitBracket)).one()
        assert bracket.status == "paper_closed"
        assert bracket.exit_reason == "hard_stop"
        exit_idea = session.get(TradeIdea, bracket.exit_trade_idea_id)
        assert exit_idea.status == "Closed"
        events = session.exec(
            select(ApprovalEvent).where(ApprovalEvent.trade_idea_id == exit_idea.id)
        ).all()
        assert len(events) == 1
        entry = session.get(TradeIdea, trade.id)
        assert entry.status == "Closed"
        sell = session.exec(select(ExecutionTicket).where(ExecutionTicket.side == "sell")).one()
        assert sell.adapter_status == "PaperFilled"
        assert sell.fill_qty == 0.5


def test_hunt_cron_source_does_not_place_orders():
    import api.routers.cron as cron

    assert "place_order" not in inspect.getsource(cron.hunt_tick)


def test_profit_hunter_live_sell_is_signal_only(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)

    async def boom(*args, **kwargs):
        raise AssertionError("broker write")

    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)
    result = asyncio.run(_execute_sell("BTC-EUR", 0.1, 100))
    assert result["success"] is False
    assert result["reason"] == "hitl_required"


def test_profit_hunter_paper_uses_executor_not_broker(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    seen = []

    async def fake_execute(**kwargs):
        seen.append(kwargs)
        return {
            "success": True,
            "order_id": "paper-1",
            "string_code": "PAPER_FILLED",
            "raw": {"paper": True, "avg_fill_price": 100, "filled_quantity": kwargs["volume"]},
        }

    async def boom(*args, **kwargs):
        raise AssertionError("broker write")

    monkeypatch.setattr(trade_executor, "execute_trade", fake_execute)
    monkeypatch.setattr("api.services.profit_hunter.trade_executor.execute_trade", fake_execute)
    monkeypatch.setattr("api.services.revolut_x_client.place_order", boom)
    result = asyncio.run(_execute_sell("ETH-EUR", 1.5, 200))
    assert result["success"] is True
    assert result["paper"] is True
    assert seen[0]["side"] == "sell"
    assert seen[0]["volume"] == 1.5


def test_execute_exit_requires_approval_then_sells_bracket_qty(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    # File-backed so the TestClient thread sees the same schema. A bare
    # sqlite:// memory DB is per-connection and invisible across threads.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    calls = []

    async def fake_execute(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "order_id": "ord-exit",
            "string_code": "FILLED",
            "numeric_code": 0,
            "message": "",
            "raw": {"state": "FILLED"},
        }

    async def fake_resolve(result):
        return {
            "paper": False,
            "filled": True,
            "adapter_status": "Filled",
            "fill_qty": 0.5,
            "fill_price": 89.0,
            "fees_eur": 0.01,
            "state": "FILLED",
            "error": None,
            "poll": {"state": "FILLED", "fill_qty": 0.5, "fill_price": 89.0},
        }

    monkeypatch.setattr("api.routers.revolut_x.trade_executor.execute_trade", fake_execute)
    monkeypatch.setattr("api.routers.revolut_x.trade_executor.resolve_fill", fake_resolve)

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override
    try:
        with Session(engine) as session:
            trade, _ticket, bracket = _seed_long(session)
            # Turn the armed bracket into a proposed exit the way the monitor would,
            # but leave it unapproved so execute must refuse.
            now = datetime.now(timezone.utc)
            idea = TradeIdea(
                user_id="seed_user",
                symbol="BTC-EUR",
                direction="EXIT",
                entry_price=89,
                stop_price=90,
                target_price=130,
                thesis="[EXIT hard_stop] Helm bracket proposes a market sell of the spot long now.",
                invalidation_notes="Reject to keep the long open.",
                status="Ready for Approval",
                created_at=now,
                updated_at=now,
            )
            session.add(idea)
            session.flush()
            session.add(TradeIdeaVersion(
                user_id="seed_user",
                symbol="BTC-EUR",
                direction="EXIT",
                entry_price=89,
                stop_price=90,
                target_price=130,
                thesis=idea.thesis,
                invalidation_notes=idea.invalidation_notes,
                trade_idea_id=idea.id,
                version_number=1,
            ))
            bracket.exit_trade_idea_id = idea.id
            bracket.status = "exit_proposed"
            bracket.exit_reason = "hard_stop"
            session.add(bracket)
            session.commit()
            exit_id = idea.id
            entry_id = trade.id

        client = TestClient(app)
        refused = client.post(f"/api/revolut-x/execute/{exit_id}", json={"quote_eur": 25, "use_market": True})
        assert refused.status_code == 400
        assert calls == []

        approved = client.post(f"/api/approvals/{exit_id}", json={"action": "APPROVE", "reasoning": "cut it"})
        assert approved.status_code == 200

        sold = client.post(f"/api/revolut-x/execute/{exit_id}", json={"quote_eur": 25, "volume": 9, "use_market": True})
        assert sold.status_code == 200, sold.text
        body = sold.json()
        assert body["trade_status"] == "Closed"
        assert body["ticket"]["side"] == "sell"
        assert calls[0]["side"] == "sell"
        assert calls[0]["volume"] == 0.5
        assert "quote_eur" not in calls[0]
        assert body["exit_bracket"]["status"] == "closed"

        with Session(engine) as session:
            entry = session.get(TradeIdea, entry_id)
            assert entry.status == "Closed"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
        os.remove(path)


def test_cron_hunt_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AURUM_AGENTS_ENABLED", False)
    client = TestClient(app)
    res = client.get("/api/cron/hunt")
    assert res.status_code == 200
    assert res.json()["status"] == "disabled"
