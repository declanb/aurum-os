"""
Agent Registry — shared coordination layer for the Aurum agent fleet.

Each agent (scout, profit_hunter, future agents) registers itself with:
  - agent_id (unique, e.g. "scout", "profit_hunter_btc")
  - symbol (if position-specific, else null)
  - status (running, paused, completed, error)
  - last_heartbeat (UTC timestamp)
  - metadata (free-form JSON for agent-specific state)

The registry lives at /tmp/aurum_agents.json.
Agents update their own entry on startup + every heartbeat.
Stale entries (no heartbeat for >5min) are marked as "stale".

Cross-agent coordination rules:
  - Scout checks for profit_hunter entries on a symbol before auto-approving.
  - All agents check the global AURUM_AGENTS_PAUSED flag (env or registry).
  - Max one scout agent at a time (enforced by agent_id uniqueness).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path("/tmp/aurum_agents.json")
STALE_THRESHOLD_MINUTES = 5


def _load() -> dict:
    """Load registry from disk. Returns empty dict if missing/corrupt."""
    if not REGISTRY_PATH.exists():
        return {}
    try:
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load agent registry: %s", exc)
        return {}


def _save(data: dict) -> None:
    """Persist registry to disk."""
    try:
        with open(REGISTRY_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        logger.error("Failed to save agent registry: %s", exc)


def register(agent_id: str, symbol: Optional[str] = None, metadata: Optional[dict] = None) -> None:
    """
    Register or update an agent's entry.
    Call this on startup and periodically (heartbeat).
    """
    data = _load()
    data[agent_id] = {
        "agent_id": agent_id,
        "symbol": symbol,
        "status": "running",
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "pid": os.getpid(),
    }
    _save(data)
    logger.info("Agent registered: %s (symbol=%s)", agent_id, symbol)


def heartbeat(agent_id: str) -> None:
    """Quick heartbeat update without changing other fields."""
    data = _load()
    if agent_id in data:
        data[agent_id]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        _save(data)


def unregister(agent_id: str) -> None:
    """Remove agent from registry (called on clean shutdown)."""
    data = _load()
    if agent_id in data:
        del data[agent_id]
        _save(data)
        logger.info("Agent unregistered: %s", agent_id)


def is_paused() -> bool:
    """Check if the global pause flag is active."""
    # Check env var first
    if os.getenv("AURUM_AGENTS_PAUSED") == "1":
        return True
    # Check registry-level flag
    data = _load()
    return data.get("_global_paused", False)


def set_paused(paused: bool) -> None:
    """Set global pause flag (affects all agents)."""
    data = _load()
    data["_global_paused"] = paused
    _save(data)
    logger.info("Global agent pause flag set to: %s", paused)


def is_symbol_claimed(symbol: str) -> bool:
    """Check if any running agent has already claimed this symbol."""
    data = _load()
    now = datetime.now(timezone.utc)
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("symbol") == symbol and entry.get("status") == "running":
            # Check staleness
            last = entry.get("last_heartbeat")
            if last:
                try:
                    hb_time = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    if now - hb_time < timedelta(minutes=STALE_THRESHOLD_MINUTES):
                        return True  # Fresh claim
                except Exception:
                    pass
    return False


def get_all() -> dict[str, dict]:
    """Return all registered agents, marking stale ones."""
    data = _load()
    now = datetime.now(timezone.utc)
    result = {}
    
    for agent_id, entry in data.items():
        if not isinstance(entry, dict) or agent_id.startswith("_"):
            continue
        
        last = entry.get("last_heartbeat")
        is_stale = False
        if last:
            try:
                hb_time = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if now - hb_time >= timedelta(minutes=STALE_THRESHOLD_MINUTES):
                    is_stale = True
                    entry["status"] = "stale"
            except Exception:
                is_stale = True
                entry["status"] = "stale"
        
        result[agent_id] = entry
    
    return result


def clean_stale() -> int:
    """Remove stale entries from the registry. Returns count removed."""
    data = _load()
    now = datetime.now(timezone.utc)
    to_remove = []
    
    for agent_id, entry in data.items():
        if not isinstance(entry, dict) or agent_id.startswith("_"):
            continue
        last = entry.get("last_heartbeat")
        if last:
            try:
                hb_time = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if now - hb_time >= timedelta(minutes=STALE_THRESHOLD_MINUTES):
                    to_remove.append(agent_id)
            except Exception:
                to_remove.append(agent_id)
    
    for agent_id in to_remove:
        del data[agent_id]
    
    if to_remove:
        _save(data)
        logger.info("Cleaned %d stale agent(s): %s", len(to_remove), to_remove)
    
    return len(to_remove)
