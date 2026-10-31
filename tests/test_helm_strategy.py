"""Helm strategy change: symmetric brackets, conviction cap, stale expiry, paper week."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

import api.models  # noqa: F401
from api.core.config import settings
from api.core.db import get_session
from api.index import app
from api.models.trade import ExecutionTicket, TradeIdea
from api.services import auto_approver, copy_book, exit_bracket, helm_strategy
from api.services.copy_book import start_session, tick_session
from api.services.live_positions import TAKER_FEE, sale_pnl


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


def _session():
    return Session(_engine())


def _quote(symbol, px, **extra):
    row = {"symbol": symbol, "bid": px, "ask": px, "mid": px, "last": px}
    row.update(extra)
    return row


def _scout_idea(db, symbol, conf, created=None, status="Ready for Approval", direction="LONG"):
    now = created or datetime.now(timezone.utc)
    idea = TradeIdea(
        user_id="seed_user",
        symbol=symbol,
        direction=direction,
        entry_price=10.0,
        stop_price=9.0,
        target_price=13.0,
        thesis=f"[SCOUT] breakout held on volume · Lens: trend · Conf {conf} · R:R 3",
        invalidation_notes="Close under 9.",
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


# ── symmetric brackets ────────────────────────────────────────────────

def test_bracket_levels_are_net_of_the_sell_fee():
    stop, target = helm_strategy.bracket_levels(100.0, 3, 3)
    qty = 50.0 / 100.0
    win, _ = sale_pnl(qty, target, 50.0)
    loss, _ = sale_pnl(qty, stop, 50.0)
    assert win == pytest.approx(1.5, abs=1e-6)   # +3% of EUR 50 after fees
    assert loss == pytest.approx(-1.5, abs=1e-6)  # -3% of EUR 50 after fees
    assert target == pytest.approx(103.0 / (1 - TAKER_FEE))


def test_env_drives_tp_and_sl(monkeypatch):
    monkeypatch.setattr(settings, "HELM_TP_PCT", 4.0)
    monkeypatch.setattr(settings, "HELM_SL_PCT", 2.0)
    stop, target = helm_strategy.bracket_levels(100.0, fee=0)
    assert (stop, target) == (pytest.approx(98.0), pytest.approx(104.0))


def _rec(symbol, conf, entry=10.0):
    return {
        "symbol": symbol,
        "direction": "LONG",
        "entry_price": entry,
        "stop_price": entry * 0.9,
        "target_price": entry * 1.3,
        "thesis": "Higher low held and buyers stepped in on volume.",
        "invalidation": "Close under the higher low.",
        "confidence_score": conf,
        "risk_reward": 3,
    }


def test_stage_uses_symmetric_bracket_and_passes_guardian():
    db = _session()
    staged, msg, trade_id = auto_approver.stage_recommendation(db, _rec("SOL-EUR", 80))
    assert staged, msg
    idea = db.get(TradeIdea, trade_id)
    stop, target = helm_strategy.bracket_levels(10.0)
    assert idea.status == "Ready for Approval"  # HITL: still needs Approve then Execute
    assert idea.stop_price == pytest.approx(stop)
    assert idea.target_price == pytest.approx(target)
    assert db.exec(select(ExecutionTicket)).first() is None


def test_conviction_cap_keeps_top_two_by_score():
    db = _session()
    recs = helm_strategy.rank_recs([_rec("A-EUR", 60), _rec("B-EUR", 90), _rec("C-EUR", 75)])
    results = [auto_approver.stage_recommendation(db, rec) for rec in recs]
    staged = [r for r in results if r[0]]
    assert len(staged) == 2
    symbols = sorted(db.get(TradeIdea, r[2]).symbol for r in staged)
    assert symbols == ["B-EUR", "C-EUR"]
    assert "daily cap" in results[2][1]


def test_scout_exit_bracket_rebases_on_fill():
    trade = TradeIdea(
        user_id="seed_user", symbol="SOL-EUR", direction="LONG", entry_price=10, stop_price=9.7,
        target_price=10.3, thesis="[SCOUT] x · Conf 80", invalidation_notes="x", status="Approved",
    )
    stop, target = exit_bracket.default_levels(trade, 12.0)
    assert (stop, target) == helm_strategy.bracket_levels(12.0)
    manual = TradeIdea(
        user_id="seed_user", symbol="SOL-EUR", direction="LONG", entry_price=10, stop_price=9,
        target_price=14, thesis="Manual idea with its own levels", invalidation_notes="x", status="Approved",
    )
    assert exit_bracket.default_levels(manual, 12.0) == (9, 14)


# ── stale expiry ──────────────────────────────────────────────────────

def test_expire_stale_is_dry_run_by_default_and_skips_exits():
    db = _session()
    old = datetime.now(timezone.utc) - timedelta(hours=72)
    stale = _scout_idea(db, "OLD-EUR", 70, created=old)
    _scout_idea(db, "EXIT-EUR", 70, created=old, direction="EXIT")
    _scout_idea(db, "NEW-EUR", 70)
    preview = helm_strategy.expire_stale_ideas(db, 48)
    assert preview["dry_run"] is True and preview["matched"] == 1 and preview["expired"] == 0
    assert db.get(TradeIdea, stale.id).status == "Ready for Approval"
    done = helm_strategy.expire_stale_ideas(db, 48, dry_run=False)
    assert done["expired"] == 1
    db.refresh(stale)
    assert stale.status == "Cancelled"


# ── paper week ────────────────────────────────────────────────────────

def test_paper_week_defaults_and_top_two_daily_cap():
    db = _session()
    book = start_session(db)
    assert book.strategy == "symmetric" and book.any_green is False
    assert book.starting_bankroll_eur == pytest.approx(200)
    assert book.max_notional_eur == pytest.approx(50)
    assert book.max_new_per_day == 2
    _scout_idea(db, "A-EUR", 60)
    _scout_idea(db, "B-EUR", 90)
    _scout_idea(db, "C-EUR", 80)
    out = asyncio.run(
        tick_session(db, book.id, quotes=[_quote("A-EUR", 10), _quote("B-EUR", 10), _quote("C-EUR", 10)])
    )
    opened = sorted(row["symbol"] for row in out["tick"]["opened"])
    assert opened == ["B-EUR", "C-EUR"]
    assert all(row["entry_notional_eur"] == pytest.approx(50, abs=0.05) for row in out["tick"]["opened"])
    assert any(s["reason"] == "daily_cap" for s in out["tick"]["skipped"])


def test_paper_week_brackets_do_not_sell_on_green_and_summary():
    db = _session()
    book = start_session(db, max_new_per_day=2)
    _scout_idea(db, "B-EUR", 90)
    _scout_idea(db, "C-EUR", 80)
    asyncio.run(tick_session(db, book.id, quotes=[_quote("B-EUR", 10), _quote("C-EUR", 10)]))
    green = asyncio.run(tick_session(db, book.id, quotes=[_quote("B-EUR", 10.2), _quote("C-EUR", 10.1)]))
    assert green["session"]["open_count"] == 2  # +2% is not an exit any more
    stop, target = helm_strategy.bracket_levels(10.0)
    done = asyncio.run(
        tick_session(db, book.id, quotes=[_quote("B-EUR", target + 0.001), _quote("C-EUR", stop - 0.001)])
    )
    reasons = sorted(row["exit_reason"] for row in done["closed_trades"])
    assert reasons == ["hard_stop", "take_profit"]
    summary = done["summary"]
    assert summary["wins"] == 1 and summary["losses"] == 1
    assert summary["win_rate_pct"] == pytest.approx(50)
    assert summary["avg_win_eur"] == pytest.approx(1.5, abs=0.01)
    assert summary["avg_loss_eur"] == pytest.approx(-1.5, abs=0.01)
    assert summary["fees_eur"] > 0
    assert done["live_orders"] is False


def test_public_quotes_loader_is_used_when_flagged(monkeypatch):
    calls = []

    async def fake():
        calls.append(1)
        return [_quote("B/EUR", 10)]

    monkeypatch.setattr(copy_book, "fetch_public_tickers", fake)
    rows, err = asyncio.run(copy_book._load_quotes(None, True))
    assert calls and err is None and rows[0]["symbol"] == "B/EUR"


def test_http_status_summary_and_expire_endpoint():
    engine = _engine()

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        started = client.post("/api/copy/session", json={})
        assert started.status_code == 200
        assert started.json()["session"]["strategy"] == "symmetric"
        status = client.get("/api/copy/status").json()
        assert status["summary"]["win_rate_pct"] is None
        assert status["live_orders"] is False
        preview = client.post("/api/strategy/expire-stale", json={})
        assert preview.status_code == 200 and preview.json()["dry_run"] is True
        assert client.get("/api/strategy/rules").json()["any_green"] is False
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_fetch_public_tickers_maps_last_and_24h_open(monkeypatch):
    import httpx

    payload = {"data": [{"symbol": "FIL/EUR", "bid": "1.9", "ask": "2.1", "mid": "2", "last_price": "2.2", "price_change_24h": "0.2"}]}

    def handler(request):
        assert request.url.path.endswith("/public/tickers")
        assert "authorization" not in {k.lower() for k in request.headers}
        return httpx.Response(200, json=payload)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    rows = asyncio.run(copy_book.fetch_public_tickers())
    assert rows[0]["last"] == "2.2"
    from api.services import market_data
    assert market_data.change_24h_pct(rows[0]) == pytest.approx(10.0)
