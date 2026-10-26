"""Live fleet cards for the Helm agents page.

The catalog is the fleet that already exists (scout, recommender, guardian,
trend scout, exit brackets, profit hunters). Heartbeats come from the agent
registry. Last action comes from ``record_action`` notes, with a fallback to
the newest staged idea or armed exit bracket when a serverless cron left no
process behind.

This module does not place, cancel, or approve orders.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from api.services.agent_registry import STALE_THRESHOLD_MINUTES

_STALE = timedelta(minutes=STALE_THRESHOLD_MINUTES)
_ARMED = {"armed", "exit_proposed", "closing"}

# Order matches the recommendation path a person sees in the product.
CATALOG: list[dict] = [
    {
        "id": "scout",
        "name": "Scout",
        "kind": "process",
        "blurb": "Polls the recommender and stages TradeIdeas. It never places an order.",
        "idle_action": "Not running. Start it locally, or wait for the scheduled pass.",
    },
    {
        "id": "recommender",
        "name": "Recommender",
        "kind": "on_demand",
        "blurb": "ai_advisor ranks spot setups and stops at a TradeIdea.",
        "idle_action": "Has not ranked a setup yet. Scout calls it on each pass.",
    },
    {
        "id": "guardian",
        "name": "Guardian",
        "kind": "on_demand",
        "blurb": "Checks reward/risk, thesis length, and invalidation before an idea can move on.",
        "idle_action": "Waiting for an idea to check.",
    },
    {
        "id": "trend_scout",
        "name": "Trend scout",
        "kind": "signal",
        "blurb": "Read-only public headlines for the advisor. Off unless AURUM_TREND_SCOUT=1.",
        "idle_action": "Flag is on. No bundle read has registered yet.",
        "off_action": "Switched off. Public headlines are not attached to recommendations.",
    },
    {
        "id": "exit_brackets",
        "name": "Exit brackets",
        "kind": "monitor",
        "blurb": "Watches stop, target, and trail. A breach stages an EXIT idea for you to approve.",
        "idle_action": "No bracket is armed. A filled spot long gets a stop, target, and trail.",
    },
]


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _health(entry: Optional[dict], now: datetime) -> str:
    if not entry:
        return "idle"
    heartbeat = _parse(entry.get("last_heartbeat"))
    if heartbeat is None or now - heartbeat >= _STALE:
        return "stale"
    status = entry.get("status") or ""
    if status == "stale":
        return "stale"
    if status in {"running", "paused"}:
        return "healthy"
    return "idle"


def _pick_action(candidates: list[Optional[dict]], fallback: str) -> tuple[str, Optional[str]]:
    best: Optional[dict] = None
    best_at: Optional[datetime] = None
    for item in candidates:
        if not item or not item.get("summary"):
            continue
        at = _parse(item.get("at"))
        if best is None or (at is not None and (best_at is None or at >= best_at)):
            best = item
            best_at = at
    if best is None:
        return fallback, None
    return str(best["summary"]), best.get("at")


def _meta_action(entry: Optional[dict]) -> Optional[dict]:
    if not entry:
        return None
    meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    summary = meta.get("last_action")
    if not summary:
        return None
    return {"summary": summary, "at": meta.get("last_action_at")}


def _detail(entry: Optional[dict]) -> Optional[str]:
    if not entry:
        return None
    meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    parts: list[str] = []
    if meta.get("playbook"):
        parts.append(f"Playbook {meta['playbook']}")
    if meta.get("poll_minutes"):
        parts.append(f"Every {meta['poll_minutes']} min")
    symbols = meta.get("symbols")
    if isinstance(symbols, list) and symbols:
        parts.append(", ".join(str(s) for s in symbols[:6]))
    if meta.get("qty") is not None:
        parts.append(f"Qty {meta['qty']}")
    if meta.get("cost_eur") is not None:
        try:
            parts.append(f"Cost €{float(meta['cost_eur']):.2f}")
        except (TypeError, ValueError):
            pass
    if meta.get("source_mode"):
        parts.append(f"Source {meta['source_mode']}")
    if meta.get("read_only") is True:
        parts.append("Read only")
    if not parts:
        return None
    return " · ".join(parts)


def _card(
    *,
    agent_id: str,
    name: str,
    kind: str,
    blurb: str,
    health: str,
    paused: bool,
    entry: Optional[dict],
    action: str,
    action_at: Optional[str],
    symbol: Optional[str] = None,
) -> dict:
    return {
        "id": agent_id,
        "name": name,
        "kind": kind,
        "blurb": blurb,
        "health": health,
        "paused": bool(paused) and health == "healthy",
        "symbol": symbol if symbol is not None else (entry.get("symbol") if entry else None),
        "last_action": action,
        "last_action_at": action_at,
        "last_heartbeat": entry.get("last_heartbeat") if entry else None,
        "can_clear": bool(entry) and health == "stale",
        "detail": _detail(entry),
    }


def _named(agent_id: str) -> str:
    return agent_id.replace("_", " ").strip().title()


def build_fleet_cards(
    agents: dict,
    activity: dict,
    *,
    paused: bool,
    hints: dict,
    flags: dict,
    now: datetime,
) -> list[dict]:
    """Merge the real fleet catalog with registry rows and last-action notes."""
    agents = agents or {}
    activity = activity or {}
    hints = hints or {}
    flags = flags or {}
    cards: list[dict] = []
    seen: set[str] = set()

    for spec in CATALOG:
        agent_id = spec["id"]
        seen.add(agent_id)
        entry = agents.get(agent_id) if isinstance(agents.get(agent_id), dict) else None
        health = _health(entry, now)
        if agent_id == "trend_scout" and not flags.get("trend_scout") and entry is None:
            health = "off"
        fallback = spec["off_action"] if health == "off" else spec["idle_action"]
        if health == "stale":
            fallback = "Heartbeat is older than 5 minutes. Clear it if the process is gone."
        summary, at = _pick_action(
            [
                activity.get(agent_id) if isinstance(activity.get(agent_id), dict) else None,
                _meta_action(entry),
                hints.get(agent_id) if isinstance(hints.get(agent_id), dict) else None,
            ],
            fallback,
        )
        cards.append(
            _card(
                agent_id=agent_id,
                name=spec["name"],
                kind=spec["kind"],
                blurb=spec["blurb"],
                health=health,
                paused=paused,
                entry=entry,
                action=summary,
                action_at=at,
            )
        )

    hunter_ids = sorted(key for key, value in agents.items() if key.startswith("profit_hunter_") and isinstance(value, dict))
    remembered = sorted(
        key
        for key, value in activity.items()
        if key.startswith("profit_hunter_") and isinstance(value, dict) and key not in hunter_ids
    )
    if not hunter_ids and not remembered:
        cards.append(
            _card(
                agent_id="profit_hunter",
                name="Profit hunter",
                kind="process",
                blurb="Exit watcher for one open spot long. Live mode signals only — it does not sell.",
                health="idle",
                paused=False,
                entry=None,
                action="No position claimed. An exit watcher registers when one is started for a held coin.",
                action_at=None,
            )
        )
    else:
        for agent_id in hunter_ids:
            entry = agents[agent_id]
            health = _health(entry, now)
            summary, at = _pick_action(
                [
                    activity.get(agent_id) if isinstance(activity.get(agent_id), dict) else None,
                    _meta_action(entry),
                ],
                "Watching the open long. Live mode does not sell.",
            )
            symbol = entry.get("symbol")
            cards.append(
                _card(
                    agent_id=agent_id,
                    name=f"Profit hunter{f' · {symbol}' if symbol else ''}",
                    kind="process",
                    blurb="Exit watcher for one open spot long. Live mode signals only — it does not sell.",
                    health=health,
                    paused=paused,
                    entry=entry,
                    action=summary,
                    action_at=at,
                    symbol=symbol,
                )
            )
        for agent_id in remembered:
            note = activity.get(agent_id) or {}
            cards.append(
                _card(
                    agent_id=agent_id,
                    name=_named(agent_id),
                    kind="process",
                    blurb="This watcher has unregistered. The last exit note is kept so you can see what it did.",
                    health="idle",
                    paused=False,
                    entry=None,
                    action=str(note.get("summary") or "Unregistered."),
                    action_at=note.get("at"),
                )
            )

    for agent_id, entry in agents.items():
        if agent_id in seen or agent_id.startswith("profit_hunter_") or not isinstance(entry, dict):
            continue
        health = _health(entry, now)
        summary, at = _pick_action(
            [
                activity.get(agent_id) if isinstance(activity.get(agent_id), dict) else None,
                _meta_action(entry),
            ],
            "Registered. No last action recorded yet.",
        )
        cards.append(
            _card(
                agent_id=agent_id,
                name=_named(agent_id),
                kind="process",
                blurb="Registered on the shared fleet registry.",
                health=health,
                paused=paused,
                entry=entry,
                action=summary,
                action_at=at,
            )
        )
    return cards


def hints_from_rows(trades: list[dict], brackets: list[dict]) -> dict[str, dict]:
    """Last-action hints from persisted ideas and brackets. No broker calls."""
    hints: dict[str, dict] = {}
    for trade in trades or []:
        thesis = trade.get("thesis") or ""
        if thesis.startswith("[SCOUT]") or thesis.startswith("[AUTO]"):
            when = trade.get("updated_at") or trade.get("created_at")
            symbol = trade.get("symbol") or "pair"
            direction = trade.get("direction") or "LONG"
            status = trade.get("status") or "staged"
            hints["scout"] = {
                "summary": f"Staged {symbol} {direction} ({status}).",
                "at": when,
            }
            hints["recommender"] = {
                "summary": f"Ranked {symbol} {direction} for review ({status}).",
                "at": trade.get("created_at") or when,
            }
            break

    rows = list(brackets or [])
    if rows:
        armed = [row for row in rows if row.get("status") in _ARMED]
        newest = max(rows, key=lambda row: row.get("last_checked_at") or row.get("updated_at") or "")
        symbols = ", ".join(str(row.get("symbol")) for row in armed[:4] if row.get("symbol")) or "none"
        trigger = newest.get("last_trigger")
        summary = f"{len(armed)} armed ({symbols})."
        if trigger:
            summary += f" Last trigger {trigger} on {newest.get('symbol')}."
        else:
            summary += f" Latest status {newest.get('status')} on {newest.get('symbol')}."
        hints["exit_brackets"] = {
            "summary": summary,
            "at": newest.get("last_checked_at") or newest.get("updated_at"),
        }
    return hints
