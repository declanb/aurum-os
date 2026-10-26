"""Scout cron stages recommendations for human approval.

Broker placement stays on Approvals → Execute. These tests cover the
wiring in scout_tick, not the OpenAI call.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routers import cron as cron_router


def _rec(**overrides) -> dict:
    base = {
        "symbol": "BTC-EUR",
        "direction": "LONG",
        "entry_price": 100.0,
        "stop_price": 90.0,
        "target_price": 130.0,
        "thesis": "Higher low on the 4h trend.",
        "confidence_score": 82,
        "risk_reward": 3.0,
    }
    base.update(overrides)
    return base


def _session():
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    return session


def test_vercel_cron_schedules_scout_only():
    cfg = json.loads(Path("vercel.json").read_text())
    crons = cfg["crons"]
    assert [c["path"] for c in crons] == ["/api/cron/scout"]
    assert crons[0]["schedule"] == "*/15 * * * *"


def test_scout_requires_cron_secret_when_configured():
    cron_router._last_run.clear()
    with patch.object(cron_router.settings, "CRON_SECRET", "test-secret"):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(cron_router.scout_tick(authorization=None))
    assert exc.value.status_code == 401


def test_scout_disabled_does_not_stage():
    cron_router._last_run.clear()
    with patch.object(cron_router.settings, "AURUM_AGENTS_ENABLED", False), \
         patch.object(cron_router.settings, "CRON_SECRET", ""), \
         patch.object(cron_router.auto_approver, "stage_recommendation") as stage:
        result = asyncio.run(cron_router.scout_tick(authorization=None))
    assert result["status"] == "disabled"
    stage.assert_not_called()


def test_scout_stages_when_auto_approve_off():
    cron_router._last_run.clear()
    recs = [_rec(), _rec(symbol="SOL-EUR", entry_price=20.0, stop_price=18.0, target_price=26.0)]

    with patch.object(cron_router.settings, "AURUM_AGENTS_ENABLED", True), \
         patch.object(cron_router.settings, "AURUM_AUTO_APPROVE", False), \
         patch.object(cron_router.settings, "CRON_SECRET", ""), \
         patch.object(cron_router.settings, "SCOUT_SYMBOLS", "BTC-EUR,SOL-EUR"), \
         patch.object(cron_router.settings, "SCOUT_PLAYBOOK", "trend_follower"), \
         patch.object(cron_router, "Session", return_value=_session()), \
         patch.object(cron_router, "compute_edge_fingerprint", return_value=None), \
         patch.object(cron_router.ai_advisor, "generate_recommendations", new=AsyncMock(return_value=recs)), \
         patch.object(cron_router.auto_approver, "stage_recommendation", side_effect=[
             (True, "staged for review", 7),
             (True, "staged for review", 8),
         ]) as stage, \
         patch.object(cron_router.auto_approver, "try_auto_approve") as approve, \
         patch.object(cron_router.rx, "place_order", new=AsyncMock()) as place:
        result = asyncio.run(cron_router.scout_tick(authorization="Bearer test-secret"))

    assert stage.call_count == 2
    assert stage.call_args_list[0].args[1]["symbol"] == "BTC-EUR"
    assert stage.call_args_list[1].args[1]["symbol"] == "SOL-EUR"
    approve.assert_not_called()
    place.assert_not_called()
    assert result["status"] == "success"
    assert result["staged"] == 2
    assert result["staged_trade_ids"] == [7, 8]
    assert result["approved"] == 0
    assert result["auto_approve"] is False


def test_scout_auto_approve_still_does_not_place_orders():
    cron_router._last_run.clear()
    rec = _rec()

    with patch.object(cron_router.settings, "AURUM_AGENTS_ENABLED", True), \
         patch.object(cron_router.settings, "AURUM_AUTO_APPROVE", True), \
         patch.object(cron_router.settings, "CRON_SECRET", ""), \
         patch.object(cron_router.settings, "SCOUT_SYMBOLS", "BTC-EUR"), \
         patch.object(cron_router.settings, "SCOUT_PLAYBOOK", "trend_follower"), \
         patch.object(cron_router, "Session", return_value=_session()), \
         patch.object(cron_router, "compute_edge_fingerprint", return_value={"favourite_symbols": []}), \
         patch.object(cron_router.ai_advisor, "generate_recommendations", new=AsyncMock(return_value=[rec])), \
         patch.object(cron_router.auto_approver, "stage_recommendation", return_value=(True, "staged for review", 3)), \
         patch.object(cron_router.auto_approver, "evaluate", return_value=(True, "eligible")), \
         patch.object(cron_router.auto_approver, "try_auto_approve", return_value=(True, "auto-approved", 4)) as approve, \
         patch.object(cron_router.rx, "place_order", new=AsyncMock()) as place:
        result = asyncio.run(cron_router.scout_tick(authorization=None))

    approve.assert_called_once()
    place.assert_not_called()
    assert result["staged"] == 1
    assert result["approved"] == 1
    assert result["approved_symbols"] == ["BTC-EUR"]
    assert result["auto_approve"] is True
