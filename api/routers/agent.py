"""
Agents router — status and control for the Aurum agent fleet.

Replaces pgrep-based monitoring with a proper agent registry that tracks:
  - scout_agent (AI recommendations + auto-approve)
  - profit_hunter_* (one per position)
  - future agents

Each agent registers itself, sends heartbeats, and coordinates via /tmp/aurum_agents.json.
"""

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, HTTPException

from api.core.config import settings
from api.services import agent_registry
from api.services.fleet_board import build_fleet_cards, hints_from_rows

router = APIRouter(prefix="/agent", tags=["agents"])
logger = logging.getLogger(__name__)


def _load_hints() -> dict:
    """Newest staged idea and armed brackets. Empty when the database is unreachable."""
    try:
        from sqlmodel import Session, select

        from api.core.db import engine
        from api.models.trade import ExitBracket, TradeIdea

        def _iso(value):
            if value is None:
                return None
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return value.isoformat()
            return str(value)

        with Session(engine) as session:
            trades = session.exec(
                select(TradeIdea).order_by(TradeIdea.created_at.desc()).limit(20)  # type: ignore[attr-defined]
            ).all()
            brackets = session.exec(select(ExitBracket)).all()
        trade_rows = [
            {
                "symbol": trade.symbol,
                "direction": trade.direction,
                "status": trade.status,
                "thesis": trade.thesis,
                "created_at": _iso(trade.created_at),
                "updated_at": _iso(trade.updated_at),
            }
            for trade in trades
        ]
        bracket_rows = [
            {
                "symbol": bracket.symbol,
                "status": bracket.status,
                "last_trigger": bracket.last_trigger,
                "last_checked_at": _iso(bracket.last_checked_at),
                "updated_at": _iso(bracket.updated_at),
            }
            for bracket in brackets
        ]
        return hints_from_rows(trade_rows, bracket_rows)
    except Exception as exc:  # noqa: BLE001
        logger.info("Fleet hints unavailable: %s", type(exc).__name__)
        return {}


@router.get("/fleet")
async def get_fleet() -> dict:
    """Live cards for the real Helm fleet. Read-only."""
    now = datetime.now(timezone.utc)
    return {
        "paused": agent_registry.is_paused(),
        "paper_trading": bool(settings.PAPER_TRADING),
        "cron_enabled": bool(settings.AURUM_AGENTS_ENABLED),
        "cards": build_fleet_cards(
            agent_registry.get_all(),
            agent_registry.get_activity(),
            paused=agent_registry.is_paused(),
            hints=_load_hints(),
            flags={"trend_scout": bool(settings.AURUM_TREND_SCOUT)},
            now=now,
        ),
    }


@router.post("/clear/{agent_id}")
async def clear_one(agent_id: str) -> dict:
    """Remove one stale registry row. Does not pause, resume, or trade."""
    removed = agent_registry.clear_agent(agent_id)
    return {"success": True, "removed": removed, "agent_id": agent_id}


@router.get("/", response_model=Dict[str, dict])
async def get_agents() -> Dict[str, dict]:
    """List all registered agents with their current status."""
    return agent_registry.get_all()


@router.post("/pause")
async def pause_all() -> dict:
    """Set global pause flag — all agents will skip their next actions."""
    agent_registry.set_paused(True)
    return {"success": True, "paused": True}


@router.post("/resume")
async def resume_all() -> dict:
    """Clear global pause flag."""
    agent_registry.set_paused(False)
    return {"success": True, "paused": False}


@router.post("/clean")
async def clean_stale() -> dict:
    """Remove stale agent entries (no heartbeat for >5min)."""
    count = agent_registry.clean_stale()
    return {"success": True, "removed": count}


@router.get("/status")
async def get_status() -> dict:
    """Quick summary: agent count, paused state."""
    agents = agent_registry.get_all()
    running = sum(1 for a in agents.values() if a.get("status") == "running")
    stale = sum(1 for a in agents.values() if a.get("status") == "stale")
    paused = agent_registry.is_paused()
    return {
        "total_agents": len(agents),
        "running": running,
        "stale": stale,
        "paused": paused,
        "paper_trading": settings.PAPER_TRADING,
    }


# ── Legacy profit_hunter endpoints (for backward compat) ──


@router.get("/profit-hunter/status")
async def profit_hunter_status():
    """Check profit_hunter agent(s) via registry (legacy endpoint)."""
    agents = agent_registry.get_all()
    hunters = {k: v for k, v in agents.items() if k.startswith("profit_hunter_")}
    return {
        "running": len(hunters) > 0,
        "agents": hunters,
        "log_file": "/tmp/profit_hunter_*.log",
    }


@router.get("/profit-hunter/logs")
async def profit_hunter_logs(lines: int = 20):
    """Get the last N lines from a profit hunter log file."""
    # Try to find any profit_hunter log
    try:
        result = subprocess.run(
            ["sh", "-c", "ls -t /tmp/profit_hunter_*.log 2>/dev/null | head -1"],
            capture_output=True,
            text=True,
        )
        log_path = result.stdout.strip()
        
        if not log_path or not os.path.exists(log_path):
            return {
                "exists": False,
                "lines": [],
                "message": "No profit_hunter log files found",
            }
        
        tail_result = subprocess.run(
            ["tail", f"-{lines}", log_path],
            capture_output=True,
            text=True,
            check=True,
        )
        log_lines = tail_result.stdout.strip().split("\n") if tail_result.stdout.strip() else []
        
        return {
            "exists": True,
            "lines": log_lines,
            "count": len(log_lines),
            "file": log_path,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {e}")
