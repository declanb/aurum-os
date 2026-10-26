"""Public trend context stays read-only and advisory.

These tests never call the network. They lock the regime rule, the prompt
block, and the guarantee that a trend read cannot submit a broker order.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import httpx

from api.core.config import settings
from api.services import ai_advisor, trend_context
from api.services.agent_advisor import _build_instructions
from api.services.auto_approver import _regime_suffix
from api.services.playbooks import get_playbook

ROOT = Path(__file__).resolve().parents[1]

RSS = """<?xml version="1.0"?>
<rss><channel>
  <item><title>Bitcoin holds a range</title><link>https://example.com/btc</link></item>
  <item><title>Ether follows</title><link>https://example.com/eth</link></item>
</channel></rss>
"""


def _run(coro):
    return asyncio.run(coro)


def test_regime_rule_needs_both_inputs_and_ignores_dominance():
    assert trend_context.derive_regime(
        {"market_cap_change_24h_pct": 1.0, "fear_greed_value": 55, "btc_dominance_pct": 40}
    ) == "risk_on"
    assert trend_context.derive_regime(
        {"market_cap_change_24h_pct": -1.0, "fear_greed_value": 40}
    ) == "risk_off"
    assert trend_context.derive_regime(
        {"market_cap_change_24h_pct": 0.9, "fear_greed_value": 80, "btc_dominance_pct": 70}
    ) == "unclear"
    assert trend_context.derive_regime(
        {"market_cap_change_24h_pct": 3.0, "btc_dominance_pct": 60}
    ) == "unclear"
    assert trend_context.derive_regime({"btc_dominance_pct": 70}) == "unclear"


def test_format_block_omits_missing_metrics_and_forbids_orders():
    text = trend_context.format_block(
        {
            "as_of": "2026-10-26T00:00:00+00:00",
            "regime_hint": "unclear",
            "fear_greed_value": 42,
            "fear_greed_label": "Fear",
            "sources": ["fear_greed"],
            "unavailable": [{"source": "x_recent_search", "reason": "X_BEARER_TOKEN unset"}],
            "headlines": [],
            "x_posts": [],
        }
    )
    assert "BTC dominance:" not in text
    assert "24h total market-cap change:" not in text
    assert "Fear & Greed: 42 Fear" in text
    assert "Regime hint: unclear" in text
    assert "do not invent" in text
    assert "does not authorize a broker order" in text
    assert "X_BEARER_TOKEN unset" in text
    assert trend_context.format_block(None) == ""


def test_load_public_sources_are_get_only_and_set_risk_on(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == "GET"
        url = str(request.url)
        if "coingecko" in url:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "market_cap_percentage": {"btc": 57.4},
                        "market_cap_change_percentage_24h_usd": 2.1,
                    }
                },
            )
        if "alternative.me" in url:
            return httpx.Response(
                200,
                json={"data": [{"value": "70", "value_classification": "Greed"}]},
            )
        if "coindesk.com" in url:
            return httpx.Response(200, text=RSS)
        if "twitter.com" in url:
            assert request.headers["authorization"] == "Bearer test-token"
            return httpx.Response(
                200,
                json={"data": [{"id": "99", "text": "public post about bitcoin"}]},
            )
        return httpx.Response(404, text=url)

    transport = httpx.MockTransport(handler)

    async def _load():
        async with httpx.AsyncClient(transport=transport) as client:
            return await trend_context.load(client)

    ctx = _run(_load())
    assert ctx["regime_hint"] == "risk_on"
    assert ctx["btc_dominance_pct"] == 57.4
    assert ctx["market_cap_change_24h_pct"] == 2.1
    assert ctx["fear_greed_value"] == 70
    assert ctx["headlines"][0]["title"] == "Bitcoin holds a range"
    assert ctx["x_posts"][0]["url"] == "https://x.com/i/web/status/99"
    assert "coingecko_global" in ctx["sources"]
    assert "x_recent_search" in ctx["sources"]
    assert all(request.method == "GET" for request in seen)
    assert any("twitter.com" in str(request.url) for request in seen)


def test_x_is_skipped_without_a_token_and_errors_are_not_logged(monkeypatch, caplog):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    secret = "super-secret-token"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert "twitter.com" not in url
        assert request.method == "GET"
        if "coingecko" in url:
            return httpx.Response(401, text=f"denied {secret}")
        return httpx.Response(503, text=secret)

    transport = httpx.MockTransport(handler)

    async def _load():
        async with httpx.AsyncClient(transport=transport) as client:
            return await trend_context.load(client)

    with caplog.at_level("INFO"):
        ctx = _run(_load())

    assert ctx["regime_hint"] == "unclear"
    assert ctx["btc_dominance_pct"] is None
    assert any(item["source"] == "x_recent_search" for item in ctx["unavailable"])
    assert secret not in caplog.text
    assert "Bearer" not in caplog.text


def test_module_never_references_broker_writes():
    source = inspect.getsource(trend_context)
    for forbidden in ("place_order", "trade_executor", "revolut_x_client", "ExecutionTicket("):
        assert forbidden not in source
    assert "follow_redirects=False" in source
    assert "X_RECENT_SEARCH_URL" in source


def test_advisor_attaches_explicit_context_without_a_network_load(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    monkeypatch.setattr(settings, "AURUM_TREND_CONTEXT", False)
    monkeypatch.setattr(settings, "AURUM_TREND_SCOUT", False)

    async def boom():
        raise AssertionError("trend load should not run when context is provided")

    monkeypatch.setattr(ai_advisor, "load_trend_context", boom)
    ctx = {"regime_hint": "risk_off", "sources": ["fear_greed"], "fear_greed_value": 20}

    recs = _run(
        ai_advisor.generate_recommendations(
            symbols=["BTC-USD"],
            max_recommendations=1,
            trend_context=ctx,
        )
    )
    assert recs
    assert recs[0]["trend_regime"] == "risk_off"
    assert recs[0]["trend_sources"] == ["fear_greed"]


def test_advisor_skips_trend_load_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    monkeypatch.setattr(settings, "AURUM_TREND_CONTEXT", False)
    monkeypatch.setattr(settings, "AURUM_TREND_SCOUT", False)
    called = {"n": 0}

    async def boom():
        called["n"] += 1
        raise AssertionError("should not load")

    monkeypatch.setattr(ai_advisor, "load_trend_context", boom)
    recs = _run(ai_advisor.generate_recommendations(symbols=["SOL-USD"], max_recommendations=1))
    assert called["n"] == 0
    assert "trend_regime" not in recs[0]


def test_agent_instructions_include_trend_block_as_context_only():
    playbook = get_playbook("trend_follower")
    text = _build_instructions(
        playbook,
        None,
        {
            "as_of": "2026-10-26T00:00:00+00:00",
            "regime_hint": "risk_on",
            "market_cap_change_24h_pct": 2.0,
            "fear_greed_value": 60,
            "fear_greed_label": "Greed",
            "sources": ["coingecko_global", "fear_greed"],
            "headlines": [],
            "x_posts": [],
            "unavailable": [],
        },
    )
    assert "Regime hint: risk_on" in text
    assert "does not authorize a broker order" in text
    assert "direction=null" in text


def test_regime_suffix_only_for_known_labels():
    assert _regime_suffix({"trend_regime": "risk_on"}) == " · Regime risk_on"
    assert _regime_suffix({"trend_regime": "made_up"}) == ""
    assert _regime_suffix({}) == ""


def test_cron_scout_pause_does_not_generate(monkeypatch):
    from api.routers import cron

    monkeypatch.setattr(settings, "AURUM_AGENTS_ENABLED", True)
    monkeypatch.setattr(settings, "CRON_SECRET", "")
    monkeypatch.setenv("AURUM_AGENTS_PAUSED", "1")

    async def boom(*_args, **_kwargs):
        raise AssertionError("paused scout must not generate recommendations")

    monkeypatch.setattr(cron.ai_advisor, "generate_recommendations", boom)
    result = _run(cron.scout_tick(authorization=None))
    assert result["status"] == "paused"


def test_copilot_files_keep_hitl_rails():
    instructions = (ROOT / ".github/copilot-instructions.md").read_text()
    agent = (ROOT / ".github/agents/revolut-x-trend-expert.agent.md").read_text()
    guru = (ROOT / ".github/agents/trading-guru.agent.md").read_text()

    for phrase in (
        "ApprovalEvent",
        "ExecutionTicket",
        "AURUM_AGENTS_PAUSED",
        "AUTO_APPROVE_MAX_PER_DAY",
        "real funds",
        "profit_hunter",
    ):
        assert phrase in instructions

    assert "user-invocable: true" in agent
    assert "tools: [read, search, web]" in agent
    assert "Revolut X Trend Expert" in agent
    assert "ExecutionTicket" in agent
    assert "Do not write or edit code" in agent
    assert "NOT for writing code" in guru
