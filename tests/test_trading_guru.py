"""Advisory Trading Guru replies. No broker, no approval writes."""

import asyncio
import inspect
from pathlib import Path

from api.services import trading_guru
from api.services.trading_guru import (
    answer,
    compose_local_reply,
    execution_request,
    explain_idea,
)


IDEA = {
    "id": 7,
    "symbol": "BTC-EUR",
    "direction": "LONG",
    "entry_price": 100.0,
    "stop_price": 90.0,
    "target_price": 130.0,
    "thesis": "Demand held the range low and buyers stepped in.",
    "invalidation_notes": "A daily close below 90.",
    "status": "Ready for Approval",
}


def test_module_has_no_broker_imports():
    source = Path(trading_guru.__file__).read_text()
    for forbidden in ("trade_executor", "revolut_x", "place_order", "ApprovalEvent"):
        assert forbidden not in source
    router = Path("api/routers/advisor.py").read_text()
    for forbidden in ("trade_executor", "revolut_x_client", "process_approval", "place_order"):
        assert forbidden not in router


def test_explain_idea_uses_stored_levels_and_invalidation():
    explained = explain_idea(IDEA)
    assert explained["headline"] == "Why BTC-EUR LONG"
    assert explained["levels"]["risk_reward"] == 3.0
    assert explained["invalidation"] == "A daily close below 90."
    assert "A daily close below 90." in explained["why"]
    assert explained["advisory"] is True
    assert explained["can_execute"] is False
    assert "Execute is a separate" in explained["spot_note"]


def test_explain_short_is_refused_as_a_spot_book():
    explained = explain_idea({**IDEA, "direction": "SHORT"})
    assert "spot-only" in explained["spot_note"]
    reply = compose_local_reply("Should I take this?", {**IDEA, "direction": "SHORT"})
    assert "Skip" in reply
    assert "spot-only" in reply


def test_followup_quotes_invalidation_and_stays_advisory():
    reply = compose_local_reply("What invalidates this?", IDEA)
    assert "A daily close below 90." in reply
    assert "Advisory only. This chat cannot approve or execute." in reply
    assert "Take small" in reply


def test_weak_idea_is_a_skip():
    weak = {**IDEA, "target_price": 101.0, "invalidation_notes": "", "thesis": "short"}
    reply = compose_local_reply("Is the reward/risk enough?", weak)
    assert "Skip" in reply
    assert "None recorded" in reply


def test_execution_request_detection():
    assert execution_request("place the order now")
    assert execution_request("Please execute this")
    assert execution_request("send it to revolut")
    assert not execution_request("What invalidates this?")
    assert not execution_request("Is the reward/risk enough?")


def test_answer_refuses_execution_without_a_model():
    result = asyncio.run(answer(
        [{"role": "user", "content": "execute this order now"}],
        idea=IDEA,
        allow_model=False,
    ))
    assert result["can_execute"] is False
    assert result["advisory"] is True
    assert result["source"] == "local"
    assert "cannot approve" in result["reply"].lower()
    assert "Revolut" in result["reply"]
    assert "Approvals" in result["reply"]


def test_answer_followup_without_a_model():
    result = asyncio.run(answer(
        [
            {"role": "assistant", "content": "Earlier note."},
            {"role": "user", "content": "What invalidates this?"},
        ],
        idea=IDEA,
        allow_model=False,
    ))
    assert result["can_execute"] is False
    assert "A daily close below 90." in result["reply"]


def test_answer_signature_cannot_be_mistaken_for_an_order_tool():
    params = inspect.signature(answer).parameters
    assert "execute" not in params
    assert "side" not in params
