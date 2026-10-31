"""Helm strategy rules: symmetric brackets, conviction cap, stale-idea expiry.

Approved after the overnight paper test showed that "sell on any green" banked
pennies while losers drifted.

* Symmetric brackets. Take-profit at +HELM_TP_PCT and stop-loss at
  -HELM_SL_PCT of the entry notional, **net of the Revolut X sell taker fee**.
  Defaults are 3 and 3. Helm models no buy fee (same as the copy book), so the
  sell price that nets ``pct`` is ``entry * (1 + pct) / (1 - fee)``.
* Conviction cap. Scout stages at most HELM_MAX_IDEAS_PER_DAY ideas per UTC
  day, ranked by its existing ``confidence_score``.
* Stale expiry. Ready-for-Approval ideas older than HELM_STALE_IDEA_HOURS can
  be cancelled with ``expire_stale_ideas``. Dry run by default.

Nothing here approves an idea or sends a broker order. Buys still need a human
Approve, then Execute.

CLI::

    python -m api.services.helm_strategy levels --entry 2.0
    python -m api.services.helm_strategy expire-stale            # dry run
    python -m api.services.helm_strategy expire-stale --apply    # writes
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlmodel import Session, select

from api.core.config import settings
from api.models.trade import TradeIdea

SCOUT_TAG = "[SCOUT]"
STALE_STATUS = "Ready for Approval"
EXPIRED_STATUS = "Cancelled"
EXPIRED_NOTE = "Expired by Helm stale-idea sweep"
SYMMETRIC_MIN_RR = 1.0  # Guardian floor for Helm's own symmetric bracket
_CONF_RE = re.compile(r"Conf\s+(-?\d+(?:\.\d+)?)")


def taker_fee() -> float:
    # Lazy: live_positions imports exit_bracket, which imports this module.
    from api.services.live_positions import TAKER_FEE

    return float(TAKER_FEE)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pct(value, fallback: float) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(num) or num <= 0 or num >= 50:
        return fallback
    return num


def tp_pct() -> float:
    return _pct(settings.HELM_TP_PCT, 3.0)


def sl_pct() -> float:
    return _pct(settings.HELM_SL_PCT, 3.0)


def bracket_levels(
    entry: float,
    tp: Optional[float] = None,
    sl: Optional[float] = None,
    fee: Optional[float] = None,
) -> tuple[float, float]:
    """(stop, target) sell prices that net -sl% / +tp% of entry after the sell fee."""
    entry = float(entry)
    if not math.isfinite(entry) or entry <= 0:
        raise ValueError("entry must be positive")
    tp_frac = (tp_pct() if tp is None else _pct(tp, tp_pct())) / 100.0
    sl_frac = (sl_pct() if sl is None else _pct(sl, sl_pct())) / 100.0
    keep = 1.0 - float(taker_fee() if fee is None else fee)
    target = entry * (1.0 + tp_frac) / keep
    stop = entry * (1.0 - sl_frac) / keep
    return stop, target


def rec_score(rec: dict) -> float:
    try:
        num = float(rec.get("confidence_score") or 0)
    except (TypeError, ValueError):
        return 0.0
    return num if math.isfinite(num) else 0.0


def idea_score(idea: TradeIdea) -> float:
    """Scout writes ``Conf NN`` into the thesis. Missing means 0."""
    match = _CONF_RE.search(idea.thesis or "")
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def rank_recs(recs: Iterable[dict]) -> list[dict]:
    """Highest confidence first. Stable for ties."""
    return sorted(list(recs or []), key=lambda rec: -rec_score(rec))


def day_start(now: Optional[datetime] = None) -> datetime:
    moment = _aware(now) or utcnow()
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def scout_staged_today(session: Session, now: Optional[datetime] = None) -> int:
    since = day_start(now)
    rows = session.exec(select(TradeIdea).where(TradeIdea.created_at >= since)).all()
    return sum(1 for idea in rows if (idea.thesis or "").startswith(SCOUT_TAG))


def max_ideas_per_day() -> int:
    try:
        return max(0, int(settings.HELM_MAX_IDEAS_PER_DAY))
    except (TypeError, ValueError):
        return 2


def stale_ideas(session: Session, hours: Optional[float] = None, now: Optional[datetime] = None) -> list[TradeIdea]:
    cutoff_hours = float(settings.HELM_STALE_IDEA_HOURS if hours is None else hours)
    if not math.isfinite(cutoff_hours) or cutoff_hours < 1:
        raise ValueError("hours must be at least 1")
    cutoff = (_aware(now) or utcnow()) - timedelta(hours=cutoff_hours)
    rows = session.exec(select(TradeIdea).where(TradeIdea.status == STALE_STATUS)).all()
    out = []
    for idea in rows:
        if (idea.direction or "").upper() == "EXIT":
            continue  # exit proposals belong to a live bracket; leave them alone
        created = _aware(idea.created_at)
        if created is not None and created < cutoff:
            out.append(idea)
    out.sort(key=lambda idea: idea.id or 0)
    return out


def expire_stale_ideas(
    session: Session,
    hours: Optional[float] = None,
    dry_run: bool = True,
    now: Optional[datetime] = None,
) -> dict:
    """Cancel stale Ready-for-Approval ideas. Dry run unless ``dry_run=False``."""
    moment = _aware(now) or utcnow()
    ideas = stale_ideas(session, hours, moment)
    rows = [
        {
            "id": idea.id,
            "symbol": idea.symbol,
            "direction": idea.direction,
            "created_at": (_aware(idea.created_at) or moment).isoformat(),
        }
        for idea in ideas
    ]
    if not dry_run:
        for idea in ideas:
            idea.status = EXPIRED_STATUS
            idea.updated_at = moment
            session.add(idea)
        session.commit()
    return {
        "dry_run": bool(dry_run),
        "hours": float(settings.HELM_STALE_IDEA_HOURS if hours is None else hours),
        "matched": len(rows),
        "expired": 0 if dry_run else len(rows),
        "new_status": EXPIRED_STATUS,
        "note": EXPIRED_NOTE + ". No broker call.",
        "ideas": rows,
    }


def rules() -> dict:
    return {
        "tp_pct": tp_pct(),
        "sl_pct": sl_pct(),
        "net_of_fees": True,
        "fee_model": f"sell_taker_{taker_fee() * 100:.2f}pct",
        "symmetric_brackets": bool(settings.HELM_SYMMETRIC_BRACKETS),
        "max_ideas_per_day": max_ideas_per_day(),
        "stale_idea_hours": float(settings.HELM_STALE_IDEA_HOURS),
        "any_green": False,
        "hitl": "Buys still need Approve, then Execute.",
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Helm strategy rules. Never sends a broker order.")
    sub = parser.add_subparsers(dest="command", required=True)
    lv = sub.add_parser("levels", help="Print symmetric stop and target for an entry")
    lv.add_argument("--entry", type=float, required=True)
    sub.add_parser("rules", help="Print the active rules")
    ex = sub.add_parser("expire-stale", help="Cancel stale Ready-for-Approval ideas (dry run by default)")
    ex.add_argument("--hours", type=float, default=None)
    ex.add_argument("--apply", action="store_true", help="Actually write. Default is a dry run.")
    args = parser.parse_args(argv)
    if args.command == "levels":
        stop, target = bracket_levels(args.entry)
        out = {"entry": args.entry, "stop_price": stop, "target_price": target, **rules()}
    elif args.command == "rules":
        out = rules()
    else:
        from api.core.db import engine

        with Session(engine) as db:
            out = expire_stale_ideas(db, args.hours, dry_run=not args.apply)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
