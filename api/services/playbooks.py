"""
Trader playbooks — named strategies used as a "lens" for the LLM advisor.

Each playbook is a compact briefing distilled from a successful trader's
documented approach. The LLM is instructed to evaluate the current market
*through that lens*, biasing setup selection toward what that trader
would actually take.

Keep playbooks short and concrete — they are concatenated into the
system prompt, so token cost matters.
"""

from __future__ import annotations

from typing import TypedDict


class Playbook(TypedDict):
    id: str
    name: str
    trader: str
    style: str
    briefing: str


PLAYBOOKS: dict[str, Playbook] = {
    "wyckoff": {
        "id": "wyckoff",
        "name": "Wyckoff Accumulation / Distribution",
        "trader": "Richard Wyckoff",
        "style": "Structural / volume-based",
        "briefing": (
            "Read price as a story of composite-operator intent. Look for the four phases — "
            "accumulation, markup, distribution, markdown — and the classic events: PS, SC, AR, ST, "
            "Spring, Test, SOS, LPS (for accumulation), and BC, AR, ST, UT, UTAD, SOW, LPSY (for distribution). "
            "Take LONGs on a Spring + successful Test with rising volume into resistance. "
            "Take SHORTs on a UTAD followed by SOW. Reject setups in unclear ranges. "
            "Volume must confirm — effort vs result."
        ),
    },
    "ict_smc": {
        "id": "ict_smc",
        "name": "ICT / Smart Money Concepts",
        "trader": "Michael J. Huddleston (ICT)",
        "style": "Liquidity / order-flow",
        "briefing": (
            "Trade where institutions hunt liquidity. Identify the higher-timeframe bias (HTF draw on liquidity), "
            "mark equal highs/lows, prior day high/low, session highs/lows as liquidity pools. "
            "Wait for a liquidity sweep (stop run) into a Fair Value Gap (FVG) or Order Block (OB) on the LTF, "
            "then enter on the displacement back through the swept level. "
            "Stop beyond the OB/sweep wick. Target opposing liquidity. Skip if no clear sweep + FVG/OB confluence."
        ),
    },
    "trend_follower": {
        "id": "trend_follower",
        "name": "Turtle / Trend-Following",
        "trader": "Richard Dennis & Ed Seykota",
        "style": "Breakout / momentum",
        "briefing": (
            "The trend is your edge. Buy strength, sell weakness. Enter on a clean Donchian-style breakout "
            "(20-period high for LONG, 20-period low for SHORT) when the higher-timeframe trend agrees "
            "(price > SMA50 for LONG, price < SMA50 for SHORT). "
            "Stop = 2× ATR from entry. Target = open-ended trail, but minimum R:R 2.0 for the recommendation. "
            "Refuse mean-reversion or counter-trend setups — they're not in this playbook. "
            "Skip choppy ranges (low momentum, SMA20 ≈ SMA50)."
        ),
    },
    "macro": {
        "id": "macro",
        "name": "Top-Down Macro",
        "trader": "Stanley Druckenmiller / George Soros",
        "style": "Thematic / regime-driven",
        "briefing": (
            "Start with the regime: rates direction, dollar strength, risk-on vs risk-off, BTC dominance. "
            "Only take trades aligned with the dominant macro narrative for the asset class. "
            "For crypto: LONG bias in risk-on + falling-rate regimes with rising BTC dominance pause; "
            "SHORT bias in risk-off + USD-strength regimes. "
            "Size conviction by alignment: if 1H, 4H, and macro agree → high confidence. "
            "If macro is unclear from the data provided, set direction=null."
        ),
    },
    "livermore": {
        "id": "livermore",
        "name": "Pivotal-Point Reversal",
        "trader": "Jesse Livermore",
        "style": "Reversal at key levels",
        "briefing": (
            "Patience for the 'pivotal point' — a level the market has repeatedly respected. "
            "Enter LONG only after price reclaims resistance with conviction (close + retest hold). "
            "Enter SHORT only after price loses support with conviction. "
            "Never average down. Stop is tight, just beyond the pivotal point. "
            "Target is the next pivotal point on the chart, not an arbitrary R-multiple. "
            "If price is mid-range (no pivot in play), pass."
        ),
    },
}

DEFAULT_PLAYBOOK = "trend_follower"


def get_playbook(playbook_id: str | None) -> Playbook:
    """Return a playbook by id, falling back to the default if unknown."""
    if not playbook_id:
        return PLAYBOOKS[DEFAULT_PLAYBOOK]
    return PLAYBOOKS.get(playbook_id.lower(), PLAYBOOKS[DEFAULT_PLAYBOOK])


def list_playbooks() -> list[dict]:
    """Return summaries for the UI selector (no full briefings)."""
    return [
        {"id": pb["id"], "name": pb["name"], "trader": pb["trader"], "style": pb["style"]}
        for pb in PLAYBOOKS.values()
    ]


def format_briefing(playbook: Playbook) -> str:
    """Render a playbook as a system-prompt block."""
    return (
        f"## ACTIVE PLAYBOOK: {playbook['name']} ({playbook['trader']})\n"
        f"Style: {playbook['style']}\n"
        f"Rules:\n{playbook['briefing']}\n"
        f"You MUST evaluate the setup through this lens. "
        f"If the current market does not offer a setup that fits this playbook, "
        f"return direction=null rather than forcing a trade from a different style."
    )
