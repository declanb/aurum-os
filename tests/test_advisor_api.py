"""HTTP surface for fleet cards, guru chat, and why-this-idea."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

from api.core.db import get_session
from api.index import app
from api.models.trade import ApprovalEvent, TradeIdea
from api.services import agent_registry


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_registry, "REGISTRY_PATH", tmp_path / "agents.json")
    monkeypatch.setattr("api.services.trading_guru._model_available", lambda: False)
    monkeypatch.setattr("api.routers.advisor._tape_configured", lambda: False)
    # A file DB is shared across the request thread. sqlite:// memory is per connection.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ideas.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session
    try:
        yield TestClient(app), engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def _stage(engine, **overrides) -> int:
    fields = dict(
        user_id="seed_user",
        symbol="BTC-EUR",
        direction="LONG",
        entry_price=100.0,
        stop_price=90.0,
        target_price=130.0,
        thesis="Demand held the range low and buyers stepped in.",
        invalidation_notes="A daily close below 90.",
        status="Ready for Approval",
    )
    fields.update(overrides)
    with Session(engine) as session:
        trade = TradeIdea(**fields)
        session.add(trade)
        session.commit()
        session.refresh(trade)
        return trade.id


def test_fleet_lists_real_agents_and_clears_stale(api):
    client, _engine = api
    agent_registry.register(
        "scout",
        metadata={"playbook": "wyckoff", "symbols": ["BTC-EUR"], "poll_minutes": 15},
    )
    agent_registry.record_action("scout", "Staged BTC-EUR LONG.")
    path = agent_registry.REGISTRY_PATH
    saved = json.loads(path.read_text())
    saved["scout"]["last_heartbeat"] = (datetime.now(timezone.utc) - timedelta(minutes=9)).isoformat()
    path.write_text(json.dumps(saved))

    board = client.get("/api/agent/fleet")
    assert board.status_code == 200
    body = board.json()
    assert body["cron_enabled"] is True
    by_id = {card["id"]: card for card in body["cards"]}
    for required in ("scout", "recommender", "guardian", "trend_scout", "exit_brackets"):
        assert required in by_id
    assert by_id["scout"]["health"] == "stale"
    assert by_id["scout"]["can_clear"] is True
    assert by_id["scout"]["last_action"] == "Staged BTC-EUR LONG."

    cleared = client.post("/api/agent/clear/scout")
    assert cleared.status_code == 200
    assert cleared.json()["removed"] is True
    again = client.get("/api/agent/fleet").json()
    scout = next(card for card in again["cards"] if card["id"] == "scout")
    assert scout["health"] == "idle"
    assert scout["can_clear"] is False
    assert client.post("/api/agent/clear/_paused").json()["removed"] is False


def test_guru_refuses_to_execute(api):
    client, _engine = api
    response = client.post(
        "/api/advisor/guru",
        json={"messages": [{"role": "user", "content": "place the order now"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["advisory"] is True
    assert body["can_execute"] is False
    assert "cannot" in body["reply"].lower()
    assert "execute" not in body or body["can_execute"] is False


def test_why_this_idea_followup_does_not_approve_or_execute(api):
    client, engine = api
    trade_id = _stage(engine)
    why = client.get(f"/api/advisor/idea/{trade_id}")
    assert why.status_code == 200
    explained = why.json()
    assert explained["can_execute"] is False
    assert explained["invalidation"] == "A daily close below 90."
    assert explained["levels"]["risk_reward"] == 3.0
    assert "BTC-EUR" in explained["headline"]

    asked = client.post(
        f"/api/advisor/idea/{trade_id}/ask",
        json={"question": "What invalidates this?"},
    )
    assert asked.status_code == 200
    reply = asked.json()
    assert reply["can_execute"] is False
    assert reply["trade_id"] == trade_id
    assert "A daily close below 90." in reply["reply"]
    assert "Advisory only" in reply["reply"]

    refused = client.post(
        f"/api/advisor/idea/{trade_id}/ask",
        json={"question": "execute this now"},
    )
    assert refused.status_code == 200
    assert refused.json()["can_execute"] is False
    assert "cannot approve" in refused.json()["reply"].lower()

    missing = client.get("/api/advisor/idea/9999")
    assert missing.status_code == 404
    assert client.post("/api/advisor/execute/1").status_code == 404

    with Session(engine) as session:
        trade = session.get(TradeIdea, trade_id)
        assert trade is not None
        assert trade.status == "Ready for Approval"
        assert session.exec(select(ApprovalEvent)).all() == []
