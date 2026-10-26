"""Fleet cards and registry last-action notes."""

import json
from datetime import datetime, timedelta, timezone

from api.services import agent_registry
from api.services.fleet_board import build_fleet_cards, hints_from_rows


def _now() -> datetime:
    return datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _iso(minutes_ago: int) -> str:
    return (_now() - timedelta(minutes=minutes_ago)).isoformat()


def test_record_action_and_clear_one_row(tmp_path, monkeypatch):
    path = tmp_path / "agents.json"
    monkeypatch.setattr(agent_registry, "REGISTRY_PATH", path)
    agent_registry.register("scout", metadata={"playbook": "wyckoff"})
    agent_registry.record_action("scout", "Staged 1 BTC-EUR")
    agent_registry.record_action("guardian", "Passed BTC-EUR.")

    saved = json.loads(path.read_text())
    assert saved["scout"]["metadata"]["playbook"] == "wyckoff"
    assert saved["scout"]["metadata"]["last_action"] == "Staged 1 BTC-EUR"
    assert saved["_activity"]["guardian"]["summary"] == "Passed BTC-EUR."
    assert "guardian" not in agent_registry.get_all()

    assert agent_registry.clear_agent("scout") is True
    assert "scout" not in agent_registry.get_all()
    assert "scout" in agent_registry.get_activity()
    assert agent_registry.clear_agent("_global_paused") is False
    assert agent_registry.clear_agent("../etc/passwd") is False
    assert agent_registry.record_action("_activity", "nope") is None


def test_clean_stale_keeps_activity_and_pause(tmp_path, monkeypatch):
    path = tmp_path / "agents.json"
    monkeypatch.setattr(agent_registry, "REGISTRY_PATH", path)
    agent_registry.register("scout")
    agent_registry.record_action("scout", "Staged one")
    agent_registry.set_paused(True)
    saved = json.loads(path.read_text())
    saved["scout"]["last_heartbeat"] = _iso(10)
    path.write_text(json.dumps(saved))

    assert agent_registry.clean_stale() == 1
    assert agent_registry.get_all() == {}
    assert agent_registry.get_activity()["scout"]["summary"] == "Staged one"
    assert agent_registry.is_paused() is True


def test_live_cards_cover_the_real_fleet():
    fresh = _iso(0)
    stale = _iso(10)
    agents = {
        "scout": {
            "agent_id": "scout",
            "symbol": None,
            "status": "running",
            "last_heartbeat": fresh,
            "pid": 1,
            "metadata": {"playbook": "wyckoff", "symbols": ["BTC-EUR"], "poll_minutes": 15},
        },
        "profit_hunter_btc": {
            "agent_id": "profit_hunter_btc",
            "symbol": "BTC-EUR",
            "status": "running",
            "last_heartbeat": stale,
            "pid": 2,
            "metadata": {"qty": 0.01, "cost_eur": 2.0, "last_action": "Watching BTC-EUR.", "last_action_at": stale},
        },
    }
    activity = {
        "scout": {"summary": "Staged BTC-EUR LONG", "at": fresh},
        "guardian": {"summary": "Passed BTC-EUR.", "at": fresh},
    }
    hints = {
        "recommender": {"summary": "Ranked BTC-EUR LONG for review (Ready for Approval).", "at": fresh},
        "exit_brackets": {"summary": "1 armed (BTC-EUR).", "at": fresh},
    }
    cards = build_fleet_cards(
        agents,
        activity,
        paused=True,
        hints=hints,
        flags={"trend_scout": False},
        now=_now(),
    )
    by_id = {card["id"]: card for card in cards}
    assert {"scout", "recommender", "guardian", "trend_scout", "exit_brackets", "profit_hunter_btc"} <= set(by_id)
    assert by_id["scout"]["health"] == "healthy"
    assert by_id["scout"]["paused"] is True
    assert by_id["scout"]["last_action"] == "Staged BTC-EUR LONG"
    assert "wyckoff" in (by_id["scout"]["detail"] or "")
    assert by_id["guardian"]["health"] == "idle"
    assert by_id["guardian"]["last_action"] == "Passed BTC-EUR."
    assert by_id["recommender"]["last_action"].startswith("Ranked BTC-EUR")
    assert by_id["trend_scout"]["health"] == "off"
    assert by_id["exit_brackets"]["last_action"] == "1 armed (BTC-EUR)."
    hunter = by_id["profit_hunter_btc"]
    assert hunter["health"] == "stale"
    assert hunter["can_clear"] is True
    assert hunter["symbol"] == "BTC-EUR"
    assert hunter["paused"] is False
    assert "profit_hunter" not in by_id


def test_newer_hint_beats_an_older_note():
    cards = build_fleet_cards(
        {},
        {"scout": {"summary": "Old pass", "at": _iso(30)}},
        paused=False,
        hints={"scout": {"summary": "Staged SOL-EUR LONG (Ready for Approval).", "at": _iso(1)}},
        flags={"trend_scout": True},
        now=_now(),
    )
    scout = next(card for card in cards if card["id"] == "scout")
    trend = next(card for card in cards if card["id"] == "trend_scout")
    assert scout["last_action"].startswith("Staged SOL-EUR")
    assert scout["health"] == "idle"
    assert trend["health"] == "idle"
    assert "Flag is on" in trend["last_action"]


def test_idle_placeholder_when_no_hunter_is_running():
    cards = build_fleet_cards({}, {}, paused=False, hints={}, flags={"trend_scout": False}, now=_now())
    hunter = next(card for card in cards if card["id"] == "profit_hunter")
    assert hunter["health"] == "idle"
    assert "No position claimed" in hunter["last_action"]
    assert hunter["can_clear"] is False


def test_hints_from_staged_idea_and_bracket():
    hints = hints_from_rows(
        [
            {
                "symbol": "ETH-EUR",
                "direction": "LONG",
                "status": "Draft",
                "thesis": "A human note that is long enough to read.",
                "created_at": _iso(1),
                "updated_at": _iso(1),
            },
            {
                "symbol": "BTC-EUR",
                "direction": "LONG",
                "status": "Ready for Approval",
                "thesis": "[SCOUT] Range low held.",
                "created_at": _iso(5),
                "updated_at": _iso(4),
            },
        ],
        [
            {
                "symbol": "BTC-EUR",
                "status": "armed",
                "last_trigger": None,
                "last_checked_at": _iso(2),
                "updated_at": _iso(2),
            }
        ],
    )
    assert hints["scout"]["summary"] == "Staged BTC-EUR LONG (Ready for Approval)."
    assert hints["recommender"]["summary"].startswith("Ranked BTC-EUR")
    assert "1 armed (BTC-EUR)" in hints["exit_brackets"]["summary"]
