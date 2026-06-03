"""
Personal edge — distill the user's *own* approved trade history into a
compact fingerprint that gets injected into the LLM advisor's prompt.

The premise: trades you approved through Guardian represent setups you
believed in enough to risk capital on. That's signal. Recommend more
of what looks like your past Approved trades; flag (don't suppress)
when a candidate diverges.

Status conventions used in this codebase: Draft -> Ready for Approval -> Approved.
We treat "Approved" as the edge signal.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from sqlmodel import Session, select

from api.models.trade import TradeIdea

logger = logging.getLogger(__name__)

# Minimum sample size before we bother feeding edge data to the LLM.
# Below this, the "fingerprint" is just noise.
MIN_SAMPLE = 3


def compute_edge_fingerprint(session: Session, user_id: Optional[str] = None) -> Optional[dict]:
    """
    Summarise the user's Approved TradeIdeas into a compact profile.

    Returns None if there isn't enough history to be useful.
    """
    stmt = select(TradeIdea).where(TradeIdea.status == "Approved")
    if user_id:
        stmt = stmt.where(TradeIdea.user_id == user_id)
    trades: list[TradeIdea] = list(session.exec(stmt))

    if len(trades) < MIN_SAMPLE:
        return None

    n = len(trades)
    long_count = sum(1 for t in trades if (t.direction or "").upper() == "LONG")
    short_count = n - long_count

    symbol_counts = Counter(t.symbol for t in trades).most_common(5)

    rrs: list[float] = []
    risk_pct: list[float] = []
    reward_pct: list[float] = []
    for t in trades:
        if not (t.entry_price and t.stop_price and t.target_price):
            continue
        risk = abs(t.entry_price - t.stop_price)
        reward = abs(t.target_price - t.entry_price)
        if risk <= 0 or t.entry_price <= 0:
            continue
        rrs.append(reward / risk)
        risk_pct.append((risk / t.entry_price) * 100)
        reward_pct.append((reward / t.entry_price) * 100)

    def _avg(xs: list[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "sample_size": n,
        "long_bias_pct": round((long_count / n) * 100, 1),
        "short_bias_pct": round((short_count / n) * 100, 1),
        "favourite_symbols": [{"symbol": s, "count": c} for s, c in symbol_counts],
        "avg_risk_reward": _avg(rrs),
        "avg_risk_pct": _avg(risk_pct),
        "avg_reward_pct": _avg(reward_pct),
    }


def format_edge_block(edge: Optional[dict]) -> str:
    """Render the edge fingerprint as a system-prompt block, or empty string."""
    if not edge:
        return ""

    fav = ", ".join(f"{s['symbol']} ({s['count']})" for s in edge["favourite_symbols"])
    return (
        f"## USER'S PERSONAL EDGE ({edge['sample_size']} approved trades on record)\n"
        f"- Directional bias: {edge['long_bias_pct']}% LONG, {edge['short_bias_pct']}% SHORT\n"
        f"- Favourite symbols: {fav}\n"
        f"- Typical R:R: {edge['avg_risk_reward']}\n"
        f"- Typical risk per trade: {edge['avg_risk_pct']}% of entry\n"
        f"- Typical reward target: {edge['avg_reward_pct']}% of entry\n"
        f"Prefer setups that resemble this profile. If your recommendation diverges "
        f"materially (e.g. opposite direction on a favourite symbol, R:R far outside the typical range, "
        f"or risk significantly higher than usual), say so explicitly in the `reasoning` field. "
        f"Do NOT suppress good setups just because they diverge — but flag the divergence."
    )


def score_match(rec: dict, edge: Optional[dict]) -> Optional[int]:
    """
    Score how well a recommendation matches the user's edge fingerprint (0-100).
    Returns None if no edge data is available.
    """
    if not edge:
        return None

    score = 50  # neutral baseline

    # Direction match vs bias
    direction = (rec.get("direction") or "").upper()
    if direction == "LONG":
        score += int((edge["long_bias_pct"] - 50) * 0.3)
    elif direction == "SHORT":
        score += int((edge["short_bias_pct"] - 50) * 0.3)

    # Favourite symbol bonus
    fav_symbols = {s["symbol"] for s in edge["favourite_symbols"]}
    if rec.get("symbol") in fav_symbols:
        score += 15

    # R:R closeness to user's typical
    if edge.get("avg_risk_reward") and rec.get("risk_reward"):
        diff = abs(rec["risk_reward"] - edge["avg_risk_reward"])
        # within 0.5 of typical -> +10, within 1.0 -> +5, beyond 2.0 -> -10
        if diff <= 0.5:
            score += 10
        elif diff <= 1.0:
            score += 5
        elif diff >= 2.0:
            score -= 10

    return max(0, min(100, score))
